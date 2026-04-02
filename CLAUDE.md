# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 概述

卫星载荷火点验证服务——无状态、离线、基于 GIS。运行于端口 8000。无数据库、无网络调用，所有推断均使用本地 ESA WorldCover GeoTIFF 瓦片。

## 常用命令

```bash
# 启动服务
uvicorn app.main:app --host 0.0.0.0 --port 8000

# 测试
python -m pytest tests/ -v
python -m pytest tests/test_confidence.py -v          # 单个测试文件
python -m pytest tests/test_confidence.py::test_initial_confidence_override -v  # 单个测试函数

# 代码检查
ruff check app/ tests/
ruff format app/ tests/
```

Ruff 配置：Python 3.11，行长 120，规则 E/F/W/I（忽略 E501）。

### 测试约定

- pytest-asyncio 配置为 `asyncio_mode = "auto"`，async 测试函数无需 `@pytest.mark.asyncio` 装饰器。
- `tests/conftest.py` 将 `SAT_WORLDCOVER_DIR` 设为 `/tmp/test_worldcover`，避免依赖真实 GeoTIFF 数据。
- 共享 fixtures：`grassland_result`、`water_result`、`water_flag_result`（定义于 `conftest.py`）。

## 流水线架构

`app/core/pipeline.py` 中使用 `asyncio.gather(return_exceptions=True)` 实现的**三阶段异步流水线**：

```text
第一阶段（并行）：
  app/services/landcover.py          → 读取本地 GeoTIFF 的地表覆盖类型
  app/services/environmental.py      → 纯数学计算太阳角度 + 季节

第二阶段（并行，在第一阶段之后）：
  app/services/false_positive.py     → 4 个检测器：水体、城市、太阳耀光、海岸
  app/core/coordinator.py            → 螺旋搜索可燃地表（最多 50 步）

第三阶段（融合）：
  app/core/confidence.py             → 贝叶斯 logit 融合 → 判决结果
  app/utils/reason_generator.py      → 生成中文原因说明 + 摘要
```

## 置信度模型（两阶段）

火点置信度经由两阶段修正流水线产生最终结果，详细策略见 `docs/confidence_strategy.md`。

### Stage 1 — 星上验证（本项目）

```text
logit(Pₛ) = logit(P₀) + ln(LR_landcover) + β_env·env_score − total_fp_penalty
Pₛ = sigmoid(logit_score) × 100
```

- 传感器输入置信度范围 **[50, 75]**，转换为 `P₀ = confidence / 100.0`。
- 初步判决（`app/core/confidence.py`）：`≥ 75 → TRUE_FIRE`，`< 50 → FALSE_POSITIVE`，否则 `UNCERTAIN`。

### Stage 2 — 地面验证（地面系统使用）

```text
logit(P_final) = logit(Pₛ/100) + ln(LR_firms) + Δ_industrial
P_final = sigmoid(logit(P_final)) × 100
```

- 计算逻辑在 `app/core/ground_confidence.py`（仅数学计算，无数据获取），数据获取由地面系统负责。
- 最终判决阈值（`determine_final_verdict`）：`≥ 75 → TRUE_FIRE`，`< 50 → FALSE_POSITIVE`，否则 `UNCERTAIN`。
- 最终置信度范围：真实火点 **[75, 100]**，不确定 **[50, 75)**，假阳性 **< 50**。

所有配置项定义于 `app/config.py`（`Settings` 类），环境变量前缀 `SAT_`，可通过 `.env` 覆盖。参见 `.env.example`。

## 地表覆盖与 GeoTIFF

- ESA WorldCover 分类代码、似然比（`landcover_lr`）、可燃地表代码均定义于 `app/config.py`。
- GeoTIFF 瓦片为 3°×3° 网格，命名：`ESA_WorldCover_10m_2021_v200_{grid_code}_Map.tif`，放置于 `data/worldcover/`。
- 缺失瓦片会被优雅处理——地表覆盖返回 `None`，计算以中性似然比继续。
- 使用 `rasterio` 读取 GeoTIFF（`app/services/landcover.py`），瓦片路径解析在 `app/data/worldcover.py`。

## 假阳性检测器

4 个检测器定义于 `app/services/false_positive.py`：水体、城市热岛、太阳耀光、海岸反射。惩罚值配置于 `app/config.py`（`fp_penalty_*` 字段）。

## API 接口

- `POST /api/validate` — 接受 `ValidateRequest`（`FirePointInput` 列表），返回包含每点 `SatelliteValidationResult` 及批量统计的 `ValidateResponse`。`FirePointInput` 含可选字段 `fire_pixel`（像素数，≥1）；`SatelliteValidationResult` 含 `fire_area_m2`（火点估算面积 m²，公式：`fire_pixel × pixel_resolution_m²`，未传入时为 `null`）。
- `GET /api/health` — 返回服务状态和版本信息。

所有原因说明和摘要均以中文生成（`app/utils/reason_generator.py`）。
