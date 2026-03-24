# 星上火点主判系统 (fire_satellite)

卫星端离线火点验证系统。接收卫星传感器火点坐标，基于本地 GIS 数据完成地物分析、假阳性检测、坐标修正及置信度融合，输出火点判定结果。系统无网络依赖，可运行在星载嵌入式环境。

## 特点

- **完全离线** — 无任何网络请求，GIS 数据本地存储
- **轻量级** — 无前端、无数据库、无缓存层
- **4 种假阳性检测** — 水体、城市热岛、太阳耀斑、海岸反射
- **螺旋搜索坐标修正** — 自动修正火点坐标到最近可燃区域
- **Headless API** — 纯 JSON API，适合星地链路对接

## 系统架构

```
输入 (经纬度 + 传感器参数)
        |
        v
   FastAPI /api/validate
        |
        v
   异步 Pipeline 编排器
        |
        +-- Phase 1 (并行) ---------+
        |   +-- 地物分析 (本地 GeoTIFF)
        |   +-- 环境因素 (日夜/太阳角/火灾季节)
        |
        +-- Phase 2 (并行, 依赖 Phase 1)
        |   +-- 假阳性检测 (4 种检测器)
        |   +-- 坐标修正 (螺旋搜索)
        |
        +-- Phase 3 (融合)
            +-- 置信度计算 (Bayesian Logit)
            +-- 判定 (TRUE_FIRE / FALSE_POSITIVE / UNCERTAIN)
            +-- 中文原因生成
```

## 置信度算法

```
logit(P) = logit(P_0) + ln(LR_landcover) + beta_env * env_score - total_penalty
```

| 参数 | 说明 | 默认值 |
| --- | --- | --- |
| P_0 | 初始置信度 (传感器 confidence/100 或 0.5) | 0.5 |
| LR_landcover | 地物火灾似然比 | 林地 2.5, 灌木 2.8, 草地 3.0, 农田 1.8, 建筑 0.2, 水体 0.01 |
| beta_env | 环境因素权重 | 0.2 |
| total_penalty | 假阳性惩罚 | 水体 3.0, 城市 1.5, 耀斑 1.0, 海岸 1.2 |

**判定阈值：**

- \>= 0.75 -> **TRUE_FIRE**
- < 0.35 -> **FALSE_POSITIVE**
- 0.35 ~ 0.75 -> **UNCERTAIN**

## 快速开始

```bash
# 安装依赖
pip install -r requirements.txt

# 配置环境变量（可选）
cp .env.example .env

# 放置 GIS 数据（见下文）

# 启动服务
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

> 详细部署步骤（GDAL 安装、systemd 配置、批量数据下载、故障排查等）参见 [DEPLOYMENT.md](DEPLOYMENT.md)。

## GIS 数据准备

将 ESA WorldCover 2021 v200 GeoTIFF 瓦片放入 `data/worldcover/` 目录：

```
data/worldcover/
  ESA_WorldCover_10m_2021_v200_N27E114_Map.tif
  ESA_WorldCover_10m_2021_v200_N27E115_Map.tif
  ...
```

文件命名格式：`ESA_WorldCover_10m_2021_v200_{grid_code}_Map.tif`

下载地址：https://viewer.esa.int/web/worldcover

按需下载覆盖目标区域的瓦片即可，无需全球数据。单个瓦片约 100-300MB。

## API

### POST /api/validate — 星上验证

**请求体：**

```json
{
  "points": [
    {
      "latitude": 28.5,
      "longitude": 116.3,
      "confidence": 80,
      "acquisition_time": "2026-03-08T06:00:00Z"
    }
  ]
}
```

**响应体：**

```json
{
  "results": [
    {
      "input_point": { "latitude": 28.5, "longitude": 116.3 },
      "verdict": "TRUE_FIRE",
      "final_confidence": 0.82,
      "reasons": [
        "地物类型为草地，属于高火灾风险区域",
        "未检测到假阳性特征"
      ],
      "summary": "星上分析判定为真实火点，最终置信度82.0%。",
      "coordinate_correction": { "correction_applied": true, "offset_m": 120.5 },
      "landcover": { "class_code": 30, "class_name": "草地", "likelihood_ratio": 3.0 },
      "false_positive": { "flags": [], "total_penalty": 0.0 },
      "environmental": { "is_daytime": true, "env_score": 0.15 },
      "confidence_breakdown": {
        "initial_confidence": 0.5,
        "landcover_contribution": 1.0986,
        "environmental_contribution": 0.03,
        "false_positive_penalty": 0.0,
        "final_confidence": 0.82
      },
      "processing_time_ms": 45.2
    }
  ],
  "total_points": 1,
  "true_fire_count": 1,
  "false_positive_count": 0,
  "uncertain_count": 0,
  "total_processing_time_ms": 45.2
}
```

### GET /api/health — 健康检查

```json
{ "status": "ok", "version": "1.0.0" }
```

## 项目结构

```
fire_satellite/
  app/
    main.py                  # FastAPI 入口 (headless, 无前端)
    config.py                # 配置 (SAT_ 前缀环境变量)
    api/
      routes.py              # POST /api/validate, GET /api/health
      schemas.py             # Pydantic 数据模型
    core/
      confidence.py          # Bayesian Logit 置信度引擎
      coordinator.py         # 螺旋搜索坐标修正
      pipeline.py            # 异步并行 Pipeline
    data/
      worldcover.py          # 本地 GeoTIFF 瓦片路径解析
    services/
      environmental.py       # 环境因素分析 (日夜/太阳角/季节)
      false_positive.py      # 假阳性检测 (水体/城市/耀斑/海岸)
      landcover.py           # ESA WorldCover 本地 GeoTIFF 读取
    utils/
      geo.py                 # 地理计算 (haversine, bbox, 太阳角等)
      reason_generator.py    # 中文原因生成
  data/
    worldcover/              # ESA WorldCover GeoTIFF 瓦片 (用户手动放置)
  tests/                     # 34 个单元测试
  requirements.txt
  pyproject.toml
  .env.example
```

## 配置项

所有配置通过环境变量设置，前缀 `SAT_`：

| 变量 | 说明 | 默认值 |
| --- | --- | --- |
| SAT_THRESHOLD_TRUE_FIRE | 真火点阈值 | 0.75 |
| SAT_THRESHOLD_FALSE_POSITIVE | 假阳性阈值 | 0.35 |
| SAT_INITIAL_CONFIDENCE | 初始置信度 | 0.5 |
| SAT_BETA_ENV | 环境因素权重 | 0.2 |
| SAT_CORRECTION_RADIUS_M | 坐标修正半径 (m) | 500.0 |
| SAT_CORRECTION_STEP_M | 坐标修正步长 (m) | 50.0 |
| SAT_WORLDCOVER_DIR | GeoTIFF 目录 | data/worldcover |

## 测试

```bash
python -m pytest tests/ -v
```

28 个测试覆盖：置信度引擎、地理计算、原因生成、数据模型验证。

## 与地面系统对接

星上系统输出的 JSON 结果可直接作为地面增强系统 (`fire_ground`) 的输入：

```
星上系统 /api/validate 输出
        |
        v (星地链路传输 JSON)
        |
        v
地面系统 POST /api/enhance 输入
```

地面系统不重复星上已完成的工作，只在星上结果基础上叠加网络依赖的增强分析（历史火点、工业设施、地理编码）。
