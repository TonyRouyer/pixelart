import os
import shutil
import subprocess
import zipfile
from pathlib import Path

import pytest
from helpers import anim, colored_frames, project_with

from pixelforge.export.json_atlas import JsonAtlasExporter

RUNNER = Path(__file__).resolve().parents[1] / "godot" / "run_loader.gd"


@pytest.mark.godot
def test_godot_loader(tmp_path):
    godot = os.environ.get("GODOT_BIN")
    if not godot:
        pytest.skip("GODOT_BIN not set")
    proj = project_with(anim("walk"))
    zpath = JsonAtlasExporter().export(proj, {"walk": colored_frames(6, 64)}, tmp_path / "x.zip")
    out = tmp_path / "unzipped"
    with zipfile.ZipFile(zpath) as z:
        z.extractall(out)
    export_dir = out / "chevalier"
    # Godot needs a project to run scripts headless
    project_dir = tmp_path / "gd"
    project_dir.mkdir()
    (project_dir / "project.godot").write_text("config_version=5\n")
    shutil.copy(RUNNER, project_dir / "run_loader.gd")
    shutil.copy(export_dir / "godot" / "load_spriteframes.gd", project_dir / "load_spriteframes.gd")
    result = subprocess.run(
        [
            godot,
            "--headless",
            "--path",
            str(project_dir),
            "--script",
            "run_loader.gd",
            "--",
            str(export_dir),
        ],
        capture_output=True,
        check=False,
        text=True,
        timeout=120,
    )
    assert "animations=4" in result.stdout, result.stdout + result.stderr
