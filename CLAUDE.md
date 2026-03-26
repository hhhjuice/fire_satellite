# CLAUDE.md

本文件为 Claude Code（claude.ai/code）在此代码仓库中工作时提供指导。

## 概述

卫星载荷火点验证服务——无状态、离线、基于 GIS。运行于端口 8000。无数据库、无网络调用，所有推断均使用本地 ESA WorldCover GeoTIFF 瓦片。

## 常用命令

在 `fire_satellite/` 目录下运行：

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000

python -m pytest tests/ -v
python -m pytest tests/test_confidence.py -v   # 单个测试文件

ruff check app/ tests/
ruff format app/ tests/
```

Ruff 配置：Python 3.11，行长 120，规则 E/F/W/I（忽略 E501）。

## 流水线架构

`core/pipeline.py` 中使用 `asyncio.gather(return_exceptions=True)` 实现的**三阶段异步流水线**：

```text
第一阶段（并行）：
  services/landcover.py          → 读取本地 GeoTIFF 的地表覆盖类型
  services/environmental.py      → 纯数学计算太阳角度 + 季节

第二阶段（并行，在第一阶段之后）：
  services/false_positive.py     → 4 个检测器：水体、城市、太阳耀光、海岸
  core/coordinator.py            → 螺旋搜索可燃地表（最多 50 步）

第三阶段（融合）：
  core/confidence.py             → 贝叶斯 logit 融合 → 判决结果
  utils/reason_generator.py      → 生成中文原因说明 + 摘要
```

## 置信度模型（两阶段）

火点置信度经由两阶段修正流水线产生最终结果，详细策略见 `docs/confidence_strategy.md`。

### Stage 1 — 星上验证（本项目）

```text
logit(Pₛ) = logit(P₀) + ln(LR_landcover) + β_env·env_score − total_fp_penalty
Pₛ = sigmoid(logit_score) × 100
```

- 传感器输入置信度范围 **[50, 75]**，转换为 `P₀ = confidence / 100.0`。
- 初步判决（`core/confidence.py`）：`≥ 70 → TRUE_FIRE`，`< 50 → FALSE_POSITIVE`，否则 `UNCERTAIN`。

### Stage 2 — 地面验证（地面系统使用）

```text
logit(P_final) = logit(Pₛ/100) + ln(LR_firms) + Δ_industrial
P_final = sigmoid(logit(P_final)) × 100
```

- 计算逻辑在 `core/ground_confidence.py`，数据获取由地面系统负责。
- 最终判决阈值（`determine_final_verdict`）：`≥ 75 → TRUE_FIRE`，`< 50 → FALSE_POSITIVE`，否则 `UNCERTAIN`。
- 最终置信度范围：真实火点 **[75, 100]**，不确定 **[50, 75)**，假阳性 **< 50**。

**关键默认值**（可通过 `.env` 覆盖）：

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `SAT_THRESHOLD_TRUE_FIRE` | 70.0 | 星上初步阈值（真实火点） |
| `SAT_THRESHOLD_FALSE_POSITIVE` | 50.0 | 星上初步阈值（假阳性） |
| `SAT_THRESHOLD_TRUE_FIRE_FINAL` | 75.0 | 地面最终阈值（真实火点） |
| `SAT_THRESHOLD_FALSE_POSITIVE_FINAL` | 50.0 | 地面最终阈值（假阳性） |
| `SAT_BETA_ENV` | 0.5 | 环境分数权重 |
| `SAT_CORRECTION_RADIUS_M` | 500 | 螺旋搜索半径（米） |
| `SAT_CORRECTION_STEP_M` | 50 | 螺旋搜索步长（米） |
| `SAT_WORLDCOVER_DIR` | `data/worldcover` | GeoTIFF 瓦片目录 |
| `SAT_PIXEL_RESOLUTION_M` | 50.0 | 相机像元分辨率（米/像素） |
| `SAT_FIRMS_LR_EXACT_MATCH` | 4.0 | FIRMS 同位置同季节似然比 |
| `SAT_FIRMS_LR_NO_HISTORY` | 0.5 | FIRMS 无历史记录似然比 |
| `SAT_INDUSTRIAL_DELTA_WITHIN_500M` | -2.5 | 工业设施 500m 内 logit 修正 |

## 地表覆盖

**ESA WorldCover 分类代码及似然比**（定义于 `app/config.py`）：

| 代码 | 类别 | 似然比 |
| --- | --- | --- |
| 10 | 树木覆盖 | 3.0 |
| 20 | 灌木地 | 3.5 |
| 30 | 草地 | 4.0 |
| 40 | 耕地 | 2.0 |
| 50 | 建成区 | 0.2 |
| 60 | 裸地/稀疏植被 | 0.05 |
| 70 | 雪/冰 | 0.01 |
| 80 | 水体 | 0.01 |
| 90 | 草本湿地 | 1.5 |
| 95 | 红树林 | 1.2 |
| 100 | 地衣/苔藓 | 1.0 |

**可燃地表代码**（坐标校正器使用）：`{10, 20, 30, 40, 90, 95, 100}`

## GeoTIFF 瓦片规范

瓦片为 3°×3° ESA WorldCover 网格单元，命名格式：

```text
ESA_WorldCover_10m_2021_v200_{grid_code}_Map.tif
```

网格代码示例：`N27E114`、`S03W060`。分辨率：10 米/像素。

将瓦片放置于 `data/worldcover/`（或通过 `SAT_WORLDCOVER_DIR` 指定路径）。缺失瓦片会被优雅处理——地表覆盖返回 `None`，计算以中性似然比继续进行。

## 假阳性检测器

| 检测器 | 触发条件 | 惩罚值 |
| --- | --- | --- |
| 水体 | landcover == 80 | 3.0 |
| 城市热岛 | landcover == 50 | 1.5 |
| 海岸反射 | landcover in {90, 95} | 1.2 |
| 太阳耀光 | 太阳天顶角 ∈ [60°, 85°] | 1.0 |

## API 接口

- `POST /api/validate` — 接受 `ValidateRequest`（`FirePointInput` 列表），返回包含每点 `SatelliteValidationResult` 及批量统计的 `ValidateResponse`。`FirePointInput` 含可选字段 `fire_pixel`（像素数，≥1）；`SatelliteValidationResult` 含 `fire_area_m2`（火点估算面积 m²，公式：`fire_pixel × pixel_resolution_m²`，未传入时为 `null`）。
- `GET /api/health` — 返回服务状态和版本信息。

所有原因说明和摘要均以中文生成（`utils/reason_generator.py`）。
