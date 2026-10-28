from pixelforge.config import Settings


def test_defaults(monkeypatch):
    monkeypatch.delenv("PIXELFORGE_COMFY_URL", raising=False)
    s = Settings()
    assert s.comfy_url == "http://127.0.0.1:8188"
    assert s.grid_canvas == 1024


def test_env_override(monkeypatch, tmp_path):
    monkeypatch.setenv("PIXELFORGE_DATA_DIR", str(tmp_path))
    assert Settings().data_dir == tmp_path


def test_fake_comfy_defaults_off_and_reads_env(monkeypatch):
    monkeypatch.delenv("PIXELFORGE_FAKE_COMFY", raising=False)
    assert Settings(_env_file=None).fake_comfy is False
    monkeypatch.setenv("PIXELFORGE_FAKE_COMFY", "1")
    assert Settings(_env_file=None).fake_comfy is True
