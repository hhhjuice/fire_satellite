# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Satellite onboard fire point validation service — stateless, offline, GIS-based. Runs on port 8000. No database, no network calls; all inference uses local ESA WorldCover GeoTIFF tiles.

## Commands

Run from `fire_satellite/`:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000

python -m pytest tests/ -v
python -m pytest tests/test_confidence.py -v   # single file

ruff check app/ tests/
ruff format app/ tests/
```

Ruff: Python 3.11 target, line length 120, rules E/F/W/I (E501 ignored).

## Pipeline Architecture

**3-phase async pipeline** in `core/pipeline.py` using `asyncio.gather(return_exceptions=True)`:

```
Phase 1 (parallel):
  services/landcover.py          → rasterio read of local GeoTIFF
  services/environmental.py      → pure-math solar angle + season

Phase 2 (parallel, after Phase 1):
  services/false_positive.py     → 4 detectors: water, urban, sun_glint, coastal
  core/coordinator.py            → spiral search for combustible landcover (max 50 steps)

Phase 3 (fusion):
  core/confidence.py             → Bayesian logit fusion → verdict
  utils/reason_generator.py      → Chinese-language reasons + summary
```

## Confidence Model

```
logit(P_final) = logit(P₀) + ln(LR_landcover) + β_env·env_score + brightness_bonus + frp_bonus − total_fp_penalty
P_final = sigmoid(logit_score)
```

- Input sensor confidence (0–100) is converted to `P₀ = confidence / 100.0` before entering logit space.
- Verdicts: `≥ 0.75 → TRUE_FIRE`, `< 0.35 → FALSE_POSITIVE`, else `UNCERTAIN`.
- All thresholds and weights live in `app/config.py` (env prefix `SAT_`).

**Key defaults** (override via `.env`):

| Variable | Default | Effect |
|---|---|---|
| `SAT_THRESHOLD_TRUE_FIRE` | 0.75 | Verdict cutoff |
| `SAT_THRESHOLD_FALSE_POSITIVE` | 0.35 | Verdict cutoff |
| `SAT_BETA_ENV` | 0.2 | Environmental score weight |
| `SAT_BRIGHTNESS_BONUS` | 0.3 | Applied if brightness ≥ 340 K |
| `SAT_FRP_BONUS` | 0.3 | Applied if FRP ≥ 20 MW |
| `SAT_CORRECTION_RADIUS_M` | 500 | Spiral search radius |
| `SAT_CORRECTION_STEP_M` | 50 | Spiral search step |
| `SAT_WORLDCOVER_DIR` | `data/worldcover` | GeoTIFF tile directory |

## Land Cover

**ESA WorldCover class codes and likelihood ratios** (defined in `app/config.py`):

| Code | Class | LR |
|---|---|---|
| 10 | Tree cover | 2.5 |
| 20 | Shrubland | 2.8 |
| 30 | Grassland | 3.0 |
| 40 | Cropland | 1.8 |
| 50 | Built-up | 0.2 |
| 60 | Bare/sparse | 0.05 |
| 70 | Snow/ice | 0.01 |
| 80 | Water | 0.01 |
| 90 | Herbaceous wetland | 1.5 |
| 95 | Mangrove | 1.2 |
| 100 | Lichen/moss | 1.0 |

**Combustible codes** (used by coordinate corrector): `{10, 20, 30, 40, 90, 95, 100}`

## GeoTIFF Tile Convention

Tiles are 3°×3° ESA WorldCover grid cells. File naming:
```
ESA_WorldCover_10m_2021_v200_{grid_code}_Map.tif
```
Grid code examples: `N27E114`, `S03W060`. Resolution: 10 m/pixel.

Place tiles in `data/worldcover/` (or set `SAT_WORLDCOVER_DIR`). Missing tiles are gracefully handled — landcover returns `None` and computation continues with neutral LR.

## False Positive Detectors

| Detector | Trigger | Penalty |
|---|---|---|
| Water body | landcover == 80 | 3.0 |
| Urban heat | landcover == 50 | 1.5 |
| Coastal reflection | landcover in {90, 95} | 1.2 |
| Sun glint | solar zenith ∈ [60°, 85°] | 1.0 |

## API

- `POST /api/validate` — accepts `ValidateRequest` (list of `FirePointInput`), returns `ValidateResponse` with per-point `SatelliteValidationResult` and batch statistics.
- `GET /api/health` — returns status and version.

All reasons and summaries are generated in Chinese (`utils/reason_generator.py`).
