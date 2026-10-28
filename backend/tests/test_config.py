from pixelforge.config import Settings


def test_defaults(monkeypatch):
    monkeypatch.delenv("PIXELFORGE_COMFY_URL", raising=False)
    s = Settings()
    assert s.comfy_url == "http://127.0.0.1:8188"
    assert s.grid_canvas == 1024


def test_env_override(monkeypatch, tmp_path):
    monkeypatch.setenv("PIXELFORGE_DATA_DIR", str(tmp_path))
    assert Settings().data_dir == tmp_path
