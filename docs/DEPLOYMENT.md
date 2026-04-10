# 星上火点主判系统 — 部署与使用文档

## 目录

1. [系统概述](#1-系统概述)
2. [环境要求](#2-环境要求)
3. [安装部署](#3-安装部署)
4. [GIS 数据准备](#4-gis-数据准备)
5. [配置说明](#5-配置说明)
6. [启动服务](#6-启动服务)
7. [API 使用](#7-api-使用)
8. [置信度算法说明](#8-置信度算法说明)
9. [故障排查](#9-故障排查)
10. [运维说明](#10-运维说明)

---

## 1. 系统概述

星上火点主判系统（`fire_satellite`）是部署于卫星载荷端的轻量级火点验证服务。它接收卫星传感器上报的火点坐标和观测参数，基于本地存储的 ESA WorldCover 地物分类数据，完成以下分析并输出判定结果：

- **地物覆盖分析**：读取本地 GeoTIFF，判定火点所在地物类型（林地、草地、水体等）
- **环境因素分析**：根据观测时间计算太阳天顶角、日夜状态、火灾季节系数
- **假阳性检测**：4 种检测器（水体、城市热岛、太阳耀斑、海岸反射）
- **坐标修正**：螺旋搜索将坐标修正至最近可燃区域
- **置信度融合**：Bayesian Logit 算法融合所有分析结果，输出 0–100 置信度
- **三级判定**：`TRUE_FIRE` / `UNCERTAIN` / `FALSE_POSITIVE`

系统为 **纯离线架构**，无任何网络依赖，输出结果可通过星地链路下传至地面增强系统。

### 与地面系统的关系

```
卫星传感器 → fire_satellite（主判）→ JSON → 星地链路 → fire_ground（增强）
```

星上系统是完整的第一道判定，地面系统不重复任何星上工作，只叠加历史火点、工业设施等网络依赖数据。

---

## 2. 环境要求

### 硬件最低要求

| 资源 | 最低                  | 推荐                      |
| ---- | --------------------- | ------------------------- |
| CPU  | 1 核                  | 2 核+                     |
| 内存 | 512 MB                | 1 GB+                     |
| 存储 | 1 GB（不含 GIS 数据） | 1 TB（含全球 WorldCover） |

### 软件要求

- Python **3.11+**
- GDAL（由 rasterio 自动安装，需系统已有 GDAL 动态库）
- 操作系统：Linux / macOS / Windows（推荐 Linux）

### GDAL 依赖说明

rasterio 读取 GeoTIFF 需要系统级 GDAL。各平台安装方式：

```bash
# Ubuntu / Debian
sudo apt-get install gdal-bin libgdal-dev

# CentOS / RHEL
sudo yum install gdal gdal-devel

# macOS (Homebrew)
brew install gdal

# Conda（推荐，自动解决依赖）
conda install -c conda-forge rasterio
```

---

## 3. 安装部署

### 3.1 方式一：pip 安装（推荐生产环境）

```bash
# 进入项目目录
cd fire_satellite

# 创建虚拟环境
python3 -m venv .venv
source .venv/bin/activate        # Linux / macOS
# .venv\Scripts\activate         # Windows

# 安装依赖
pip install -r requirements.txt
```

### 3.2 方式二：Conda 安装（推荐开发环境）

```bash
# 创建 Conda 环境
conda create -n fire python=3.11 -y
conda activate fire

# 安装 rasterio（Conda 渠道更稳定）
conda install -c conda-forge rasterio -y

# 安装其他依赖
pip install fastapi "uvicorn[standard]" pydantic pydantic-settings numpy pytest pytest-asyncio
```

### 3.3 验证安装

```bash
python -c "import rasterio, fastapi, pydantic; print('依赖安装成功')"
```

---

## 4. GIS 数据准备

### 4.1 数据说明

系统使用 **ESA WorldCover 2021 v200**，分辨率 10m，按 3°×3° 分幅存储为 GeoTIFF。

单个瓦片文件约 100–300 MB，全球共约 2600 个瓦片，总计约 300 GB。**按需下载目标区域瓦片即可**，无需全量数据。

### 4.2 文件命名规则

```
ESA_WorldCover_10m_2021_v200_{grid_code}_Map.tif
```

`grid_code` 由系统自动计算，规则为：纬度向下取整到 3 的倍数，经度向下取整到 3 的倍数。

| 坐标示例                   | 对应瓦片 grid_code |
| -------------------------- | ------------------ |
| 28.5°N, 116.3°E          | `N27E114`        |
| 39.9°N, 116.4°E（北京）  | `N39E114`        |
| 31.2°N, 121.5°E（上海）  | `N30E120`        |
| 22.5°N, 114.1°E（深圳）  | `N21E114`        |
| 1.3°N, 103.8°E（新加坡） | `N00E102`        |
| 35.6°N, 139.7°E（东京）  | `N33E138`        |

### 4.3 计算任意坐标对应的瓦片名

```python
import math

def get_tile_name(lat, lon):
    tile_lat = math.floor(lat / 3) * 3
    tile_lon = math.floor(lon / 3) * 3
    lat_p = "N" if tile_lat >= 0 else "S"
    lon_p = "E" if tile_lon >= 0 else "W"
    code = f"{lat_p}{abs(tile_lat):02d}{lon_p}{abs(tile_lon):03d}"
    return f"ESA_WorldCover_10m_2021_v200_{code}_Map.tif"

print(get_tile_name(28.5, 116.3))
# ESA_WorldCover_10m_2021_v200_N27E114_Map.tif
```

### 4.4 下载方式

**方式一：ESA WorldCover Viewer（推荐）**

访问 https://viewer.esa.int/web/worldcover ，在地图上框选目标区域后下载对应瓦片。

**方式二：直接拼接 URL 下载**

```bash
# 示例：下载 N27E114 瓦片
GRID_CODE="N27E114"
wget "https://esa-worldcover.s3.amazonaws.com/v200/2021/map/ESA_WorldCover_10m_2021_v200_${GRID_CODE}_Map.tif"
```

**方式三：批量下载脚本**

```bash
#!/bin/bash
# 下载中国区域常用瓦片（根据实际需求修改）
CODES=(
  "N21E108" "N21E111" "N21E114" "N21E117" "N21E120"
  "N24E108" "N24E111" "N24E114" "N24E117" "N24E120"
  "N27E108" "N27E111" "N27E114" "N27E117" "N27E120"
  "N30E108" "N30E111" "N30E114" "N30E117" "N30E120"
  "N33E108" "N33E111" "N33E114" "N33E117" "N33E120"
  "N36E108" "N36E111" "N36E114" "N36E117" "N36E120"
  "N39E108" "N39E111" "N39E114" "N39E117" "N39E120"
)

mkdir -p data/worldcover
for CODE in "${CODES[@]}"; do
  FILE="ESA_WorldCover_10m_2021_v200_${CODE}_Map.tif"
  if [ ! -f "data/worldcover/${FILE}" ]; then
    echo "下载 ${CODE}..."
    wget -q -O "data/worldcover/${FILE}" \
      "https://esa-worldcover.s3.amazonaws.com/v200/2021/map/${FILE}"
  fi
done
echo "下载完成"
```

### 4.5 存放位置

将下载好的 `.tif` 文件放入：

```
fire_satellite/
└── data/
    └── worldcover/
        ├── ESA_WorldCover_10m_2021_v200_N27E114_Map.tif
        ├── ESA_WorldCover_10m_2021_v200_N27E117_Map.tif
        └── ...
```

> **目录路径可通过环境变量 `SAT_WORLDCOVER_DIR` 自定义**，默认为项目根目录下的 `data/worldcover`。

### 4.6 验证数据文件

```bash
python -c "
import rasterio
from pathlib import Path

tif = list(Path('data/worldcover').glob('*.tif'))
print(f'发现 {len(tif)} 个瓦片文件')
if tif:
    with rasterio.open(tif[0]) as ds:
        print(f'CRS: {ds.crs}')
        print(f'分辨率: {ds.res}')
        print(f'范围: {ds.bounds}')
"
```

---

## 5. 配置说明

### 5.1 创建配置文件

```bash
cp .env.example .env
```

### 5.2 配置项详解

编辑 `.env` 文件：

```ini
# ── 判定阈值 ──────────────────────────────────────────────
# 最终置信度 >= 此值 → TRUE_FIRE
SAT_THRESHOLD_TRUE_FIRE=75.0

# 最终置信度 < 此值 → FALSE_POSITIVE
SAT_THRESHOLD_FALSE_POSITIVE=50.0

# 初始先验置信度（当传感器未提供 confidence 字段时使用）
SAT_INITIAL_CONFIDENCE=0.5

# ── 环境因素权重 ───────────────────────────────────────────
# 环境评分（日夜、季节等）在 logit 空间的贡献权重
SAT_BETA_ENV=0.5

# ── 坐标修正参数 ───────────────────────────────────────────
# 螺旋搜索最大半径（米）
SAT_CORRECTION_RADIUS_M=500.0

# 螺旋搜索步长（米）
SAT_CORRECTION_STEP_M=50.0

# ── GIS 数据路径 ───────────────────────────────────────────
# WorldCover GeoTIFF 存储目录（绝对路径或相对于项目根目录的路径）
SAT_WORLDCOVER_DIR=data/worldcover

# ── 相机参数 ───────────────────────────────────────────────
# 像元分辨率（米/像素），用于由 fire_pixel 计算火点面积
SAT_PIXEL_RESOLUTION_M=50.0

# ── 与地面阶段共享的兼容配置（当前 /api/validate 不直接使用） ──
# 这些参数保留在同一份 Settings 中，用于与地面增强阶段共享契约/数学定义
SAT_THRESHOLD_TRUE_FIRE_FINAL=75.0
SAT_THRESHOLD_FALSE_POSITIVE_FINAL=50.0
SAT_FIRMS_LR_EXACT_MATCH=4.0
SAT_FIRMS_LR_NEARBY=2.5
SAT_FIRMS_LR_REGIONAL=1.5
SAT_FIRMS_LR_NO_HISTORY=0.5
SAT_INDUSTRIAL_DELTA_WITHIN_500M=-2.5
SAT_INDUSTRIAL_DELTA_WITHIN_2KM=-1.5
SAT_INDUSTRIAL_DELTA_WITHIN_5KM=-0.8
SAT_INDUSTRIAL_DELTA_NONE=0.3
```

### 5.3 环境变量优先级

系统按以下顺序读取配置（后者覆盖前者）：

1. 代码中的默认值
2. `.env` 文件
3. 系统环境变量（`export SAT_THRESHOLD_TRUE_FIRE=75.0`）

---

## 6. 启动服务

### 6.1 开发模式（自动热重载）

```bash
cd fire_satellite
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 6.2 生产模式（多 Worker）

```bash
# 根据 CPU 核数调整 workers（推荐 CPU 核数 × 2 + 1）
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

### 6.3 后台运行（systemd）

创建服务文件 `/etc/systemd/system/fire-satellite.service`：

```ini
[Unit]
Description=星上火点主判系统
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/opt/fire_satellite
EnvironmentFile=/opt/fire_satellite/.env
ExecStart=/opt/fire_satellite/.venv/bin/uvicorn app.main:app \
    --host 0.0.0.0 --port 8000 --workers 2
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable fire-satellite
sudo systemctl start fire-satellite
sudo systemctl status fire-satellite
```

### 6.4 容器运行时镜像（仓库自带）

仓库还提供了运行时镜像定义：`docker/Dockerfile.runtime` + `docker/start.sh`。

特点：

- 镜像只安装运行依赖，不内置项目代码
- 默认要求将项目目录挂载到 `/workspace/fire_satellite`
- 默认启动命令为单进程 `uvicorn app.main:app --host $HOST --port $PORT`
- 若 `data/worldcover/` 缺失，只会打印警告；可通过 `SAT_WORLDCOVER_DIR` 指向外部挂载数据目录

构建示例：

```bash
docker build \
  -f docker/Dockerfile.runtime \
  --build-arg BASE_IMAGE=python:3.11-slim \
  -t fire-satellite-runtime .
```

运行示例：

```bash
docker run --rm -p 8000:8000 \
  -v "$(pwd)":/workspace/fire_satellite \
  -e HOST=0.0.0.0 \
  -e PORT=8000 \
  fire-satellite-runtime
```

可选覆盖环境变量：

- `CODE_DIR`：代码目录（默认 `/workspace/fire_satellite`）
- `APP_MODULE`：ASGI 入口（默认 `app.main:app`）
- `HOST`：监听地址（默认 `0.0.0.0`）
- `PORT`：监听端口（默认 `8000`）

### 6.5 验证启动成功

```bash
curl http://localhost:8000/api/health
# 期望输出：{"status":"ok","version":"1.0.0"}
```

启动日志示例（不同 uvicorn 版本格式可能略有差异）：

```
INFO     app.main: Starting Satellite Fire Validation System...
INFO     app.main: System ready.
INFO     uvicorn: Application startup complete.
```

---

## 7. API 使用

### 7.1 POST /api/validate — 验证火点

**完整请求示例：**

```bash
curl -X POST http://localhost:8000/api/validate \
  -H "Content-Type: application/json" \
  -d '{
    "points": [
      {
        "latitude": 30.114329,
        "longitude": 120.017562,
        "confidence": 80,
        "acquisition_time": "2026-03-11T12:50:00Z",
        "fire_pixel":50
      }
    ]
  }'
```

**最简请求（仅坐标，其他字段均为 Optional）：**

```bash
curl -X POST http://localhost:8000/api/validate \
  -H "Content-Type: application/json" \
  -d '{"points": [{"latitude": 30.114329, "longitude": 120.017562}]}'
```

> 说明：若省略 `confidence`，系统使用 `SAT_INITIAL_CONFIDENCE` 作为先验；若省略 `acquisition_time`，系统使用服务端当前 UTC 时间，因此环境因素相关结果会随时间变化。

**批量验证（多火点并发处理）：**

```bash
curl -X POST http://localhost:8000/api/validate \
  -H "Content-Type: application/json" \
  -d '{
    "points": [
      {"latitude": 30.114329, "longitude": 120.017562, "confidence": 80},
      {"latitude": 30.192207, "longitude": 120.136157, "confidence": 60},
      {"latitude": 30.189506, "longitude": 120.195067}
    ]
  }'
```

**请求字段说明：**

| 字段                 | 类型   | 必填 | 范围         | 说明                                     |
| -------------------- | ------ | ---- | ------------ | ---------------------------------------- |
| `latitude`         | float  | ✅   | -90 ~ 90     | 纬度，正北为正                           |
| `longitude`        | float  | ✅   | -180 ~ 180   | 经度，正东为正                           |
| `confidence`       | float  | 否   | 0 ~ 100      | 传感器原始置信度。若提供，则按 `confidence / 100` 作为初始先验 P₀；若未提供，则使用 `SAT_INITIAL_CONFIDENCE`（默认 0.5） |
| `acquisition_time` | string | 否   | ISO 8601 UTC | 观测时间，影响日夜状态和太阳角计算；若未提供，则服务端使用当前 UTC 时间 |
| `fire_pixel`       | int    | 否   | ≥ 1         | 火点像素大小（像素数），用于计算火点面积 |

**响应字段说明：**

```json
{
  "results": [
    {
      "input_point": { ... },              // 原始输入参数
      "verdict": "TRUE_FIRE",              // 判定结果
      "final_confidence": 84.0,            // 最终置信度（0~100）
      "fire_area_m2": 30000.0,             // 火点估算面积（m²），fire_pixel 为 null 时此字段也为 null
      "reasons": [ "..." ],               // 中文判定原因列表
      "summary": "星上主判结果为...",      // 综合摘要
      "coordinate_correction": {
        "original_lat": 28.5,
        "original_lon": 116.3,
        "corrected_lat": 28.5012,
        "corrected_lon": 116.3018,
        "offset_m": 185.3,                // 偏移距离（米）
        "correction_applied": true,       // 是否实际修正了坐标
        "reason": "修正至最近可燃区域(草地)"
      },
      "landcover": {
        "class_code": 30,                 // ESA WorldCover 地物编码
        "class_name": "草地",
        "likelihood_ratio": 4.0,          // 火灾似然比
        "description": "ESA WorldCover 2021: 草地 (编码30)"
      },
      "false_positive": {
        "flags": [
          { "detector": "water_body",    "triggered": false, "penalty": 0.0 },
          { "detector": "urban_heat",    "triggered": false, "penalty": 0.0 },
          { "detector": "sun_glint",     "triggered": false, "penalty": 0.0 },
          { "detector": "coastal_reflection", "triggered": false, "penalty": 0.0 }
        ],
        "total_penalty": 0.0,
        "is_likely_false_positive": false
      },
      "environmental": {
        "is_daytime": true,
        "solar_zenith_angle": 42.3,       // 太阳天顶角（度）
        "fire_season_factor": 1.2,        // 火灾季节系数
        "env_score": 0.15,
        "detail": "白天观测，夏季北半球，火灾季节系数1.2"
      },
      "confidence_breakdown": {
        "initial_confidence": 50.0,       // 初始置信度（0~100）
        "landcover_contribution": 1.3863, // ln(LR_landcover)
        "environmental_contribution": 0.075,
        "false_positive_penalty": 0.0,
        "final_confidence": 84.0          // 最终置信度（0~100）
      },
      "processing_time_ms": 38.5
    }
  ],
  "total_points": 1,
  "true_fire_count": 1,
  "false_positive_count": 0,
  "uncertain_count": 0,
  "total_processing_time_ms": 38.5
}
```

**地物编码对照表（ESA WorldCover 2021）：**

| 编码 | 地物类型      | 火灾似然比 | 说明           |
| ---- | ------------- | ---------- | -------------- |
| 10   | 林地          | 3.0        | 高风险         |
| 20   | 灌木地        | 3.5        | 高风险         |
| 30   | 草地          | 4.0        | 最高风险       |
| 40   | 农田          | 2.0        | 中等风险       |
| 50   | 建筑用地      | 0.2        | 城市热岛假阳性 |
| 60   | 裸地/稀疏植被 | 0.05       | 低风险         |
| 70   | 冰雪          | 0.01       | 极低风险       |
| 80   | 水体          | 0.01       | 水面反射假阳性 |
| 90   | 草本湿地      | 1.5        | 海岸反射风险   |
| 95   | 红树林        | 1.2        | 海岸反射风险   |
| 100  | 苔藓/地衣     | 1.0        | 中性           |

**假阳性检测器说明：**

| 检测器                 | 触发条件                     | 惩罚值 |
| ---------------------- | ---------------------------- | ------ |
| `water_body`         | 地物编码 == 80               | 3.0    |
| `urban_heat`         | 地物编码 == 50               | 1.5    |
| `coastal_reflection` | 地物编码 == 90 或 95         | 1.2    |
| `sun_glint`          | 太阳天顶角在 60°–85° 之间 | 1.0    |

### 7.2 GET /api/health — 健康检查

```bash
curl http://localhost:8000/api/health
```

```json
{"status": "ok", "version": "1.0.0"}
```

### 7.3 Swagger 交互式文档

浏览器访问 `http://localhost:8000/docs`，可在页面上直接构造请求并查看完整响应模型。

---

## 8. 置信度算法说明

### 核心公式

```
logit(P_final) = logit(P₀)
               + ln(LR_landcover)
               + β_env × env_score
               - total_fp_penalty
```

各项含义：

| 项                      | 公式                      | 说明                                          |
| ----------------------- | ------------------------- | --------------------------------------------- |
| `logit(P₀)`          | `ln(P₀ / (1-P₀))`     | 初始先验（传感器 confidence/100，或默认 0.5） |
| `ln(LR_landcover)`    | 见地物表                  | 林地+1.10，草地+1.39，水体-4.61               |
| `β_env × env_score` | β=0.5，score∈[-0.5,0.5] | 白天夏季加分，夜间冬季减分                    |
| `total_fp_penalty`    | 各触发检测器惩罚之和      | 水体-3.0，城市-1.5，海岸-1.2，耀斑-1.0        |

最终通过 sigmoid 函数将 logit 分数映射回 [0, 100]：

```
confidence = sigmoid(logit_score) × 100
           = 100 / (1 + e^(-logit_score))
```

### 判定阈值

```
confidence >= 75  →  TRUE_FIRE      （真实火点）
confidence <  50  →  FALSE_POSITIVE  （假阳性）
50 <= confidence < 75  →  UNCERTAIN  （待确认）
```

---

## 9. 故障排查

### 问题：landcover 字段返回 null

**原因：** 对应坐标的 WorldCover 瓦片文件不存在。

**排查：**

```bash
# 查看日志，确认缺少哪个瓦片
# 日志格式：WARNING app.services.landcover: WorldCover tile not found: data/worldcover/ESA_...tif

# 计算需要的瓦片名
python -c "
import math
lat, lon = 28.5, 116.3  # 替换为实际坐标
tl = math.floor(lat/3)*3
tn = math.floor(lon/3)*3
print(f'ESA_WorldCover_10m_2021_v200_{\"N\" if tl>=0 else \"S\"}{abs(tl):02d}{\"E\" if tn>=0 else \"W\"}{abs(tn):03d}_Map.tif')
"
```

**解决：** 下载对应瓦片放入 `data/worldcover/` 目录。

---

### 问题：rasterio 导入报错 `cannot load library libgdal`

**原因：** 系统缺少 GDAL 动态链接库。

**解决：**

```bash
# Ubuntu
sudo apt-get install -y libgdal-dev

# 或使用 Conda（自动包含 GDAL）
conda install -c conda-forge rasterio
```

---

### 问题：服务启动报 `Address already in use`

**原因：** 端口 8000 被占用。

**解决：**

```bash
# 查找占用进程
lsof -i :8000

# 换端口启动
uvicorn app.main:app --host 0.0.0.0 --port 8001
```

---

### 问题：所有火点返回 UNCERTAIN，置信度约 50

**原因：** 缺少 WorldCover 数据（landcover 为 null），导致只有初始先验生效，无地物似然比贡献。

**排查：** 检查响应中 `confidence_breakdown.landcover_contribution` 是否为 0，确认 `landcover` 是否为 null。

**解决：** 补充对应区域的 WorldCover GeoTIFF 瓦片文件至 `data/worldcover/` 目录。

---

## 10. 运维说明

### 日志管理

服务日志输出到 stdout，格式为：

```
2026-03-11 06:00:01,234 INFO app.main: Starting Satellite Fire Validation System...
2026-03-11 06:00:01,235 INFO app.main: System ready.
2026-03-11 06:00:01,256 WARNING app.services.landcover: WorldCover tile not found: data/worldcover/ESA_...tif
```

生产环境建议重定向到文件并配置日志轮转：

```bash
uvicorn app.main:app ... 2>&1 | tee -a /var/log/fire-satellite.log
```

### 运行测试

```bash
cd fire_satellite
python -m pytest tests/ -v
# 期望：45 passed
```

### 性能基准

| 条件                             | 典型响应时间 |
| -------------------------------- | ------------ |
| 无 WorldCover 数据（仅环境分析） | < 5 ms       |
| 有 WorldCover 数据（含磁盘 I/O） | 20–100 ms   |
| 含坐标修正（螺旋搜索）           | 50–500 ms   |

> 坐标修正最多采样 50 个候选点，每个点做一次 GeoTIFF 读取，是主要耗时来源。可通过增大 `SAT_CORRECTION_STEP_M`（步长）减少采样次数来降低延迟。
