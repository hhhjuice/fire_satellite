import json
import sys
import types

import pytest

from app.config import get_settings
from app.data.worldcover import check_worldcover_readiness


class _FakeRasterioDataset:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def test_worldcover_readiness_uses_manifest(monkeypatch, tmp_path):
    worldcover_dir = tmp_path / "worldcover"
    worldcover_dir.mkdir()
    tile_code = "N18E096"
    tile_path = worldcover_dir / f"ESA_WorldCover_10m_2021_v200_{tile_code}_Map.tif"
    tile_path.write_text("stub", encoding="utf-8")

    manifest_path = tmp_path / "worldcover_manifest.json"
    manifest_path.write_text(json.dumps({"tiles": [tile_code]}), encoding="utf-8")

    fake_rasterio = types.SimpleNamespace(open=lambda _path: _FakeRasterioDataset())
    monkeypatch.setitem(sys.modules, "rasterio", fake_rasterio)
    monkeypatch.setenv("SAT_WORLDCOVER_DIR", str(worldcover_dir))
    monkeypatch.setenv("SAT_WORLDCOVER_MANIFEST_PATH", str(manifest_path))
    get_settings.cache_clear()

    try:
        report = check_worldcover_readiness()
    finally:
        get_settings.cache_clear()

    assert report["ready"] is True
    assert report["details"]["required_tiles"] == [tile_code]
    assert report["details"]["sample_tile"] == str(tile_path)


def test_worldcover_readiness_reports_invalid_manifest(monkeypatch, tmp_path):
    worldcover_dir = tmp_path / "worldcover"
    worldcover_dir.mkdir()
    manifest_path = tmp_path / "worldcover_manifest.json"
    manifest_path.write_text("{not-json", encoding="utf-8")

    monkeypatch.setenv("SAT_WORLDCOVER_DIR", str(worldcover_dir))
    monkeypatch.setenv("SAT_WORLDCOVER_MANIFEST_PATH", str(manifest_path))
    get_settings.cache_clear()

    try:
        report = check_worldcover_readiness()
    finally:
        get_settings.cache_clear()

    assert report["ready"] is False
    assert report["details"]["error"] == "manifest_unreadable"
    assert report["details"]["exception"] == "JSONDecodeError"


@pytest.mark.asyncio
async def test_readiness_endpoint_hides_internal_details(monkeypatch):
    from app.api import routes

    def fake_readiness():
        return {
            "ready": False,
            "details": {
                "worldcover_dir": "/secret/worldcover",
                "manifest": "/secret/worldcover_manifest.json",
                "required_tiles": ["N18E096"],
                "missing_tiles": ["N18E096"],
                "error": "required_tiles_missing",
                "exception": "PermissionError",
            },
        }

    monkeypatch.setattr(routes, "check_worldcover_readiness", fake_readiness)

    with pytest.raises(routes.HTTPException) as exc_info:
        await routes.readiness_check()

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == "WorldCover data unavailable"
    assert "/secret" not in str(exc_info.value.detail)
    assert "N18E096" not in str(exc_info.value.detail)
