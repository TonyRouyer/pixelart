import json
import zipfile

import pytest
from helpers import anim, colored_frames, project_with

from pixelforge.domain.models import Direction
from pixelforge.export.json_atlas import (
    ExportIncomplete,
    JsonAtlasExporter,
    build_animation_json,
    build_character_json,
)


def test_uneven_row_frame_tags():
    frames = colored_frames(per_dir=6, size=32)
    frames[Direction.up] = frames[Direction.up][:4]
    data = build_animation_json(anim("walk", fps=10), frames, 32, 0, (16, 30), "walk.png")
    up = next(t for t in data["meta"]["frameTags"] if t["name"] == "walk_up")
    assert (up["from"], up["to"]) == (18, 21)
    assert data["meta"]["size"] == {"w": 192, "h": 128}
    assert "walk_up_4" not in data["frames"]


def test_json_fields():
    data = build_animation_json(
        anim("attack_sword", fps=12, loop=False),
        colored_frames(6, 64),
        64,
        0,
        (32, 60),
        "attack_sword.png",
    )
    assert data["frames"]["attack_sword_down_0"] == {
        "frame": {"x": 0, "y": 0, "w": 64, "h": 64},
        "duration": 83,
    }
    assert data["frames"]["attack_sword_right_5"]["frame"] == {"x": 320, "y": 128, "w": 64, "h": 64}
    meta = data["meta"]
    assert meta["image"] == "attack_sword.png"
    assert meta["size"] == {"w": 384, "h": 256}
    assert meta["frameTags"][0] == {
        "name": "attack_sword_down",
        "from": 0,
        "to": 5,
        "direction": "forward",
    }
    assert meta["x_autosprite"] == {
        "animation": "attack_sword",
        "fps": 12,
        "loop": False,
        "frame_size": 64,
        "anchor": {"x": 32, "y": 60},
        "rows": ["down", "left", "right", "up"],
    }


def test_json_padding_offsets():
    data = build_animation_json(anim("walk"), colored_frames(2, 16), 16, 2, (8, 15), "walk.png")
    assert data["frames"]["walk_left_1"]["frame"] == {"x": 18, "y": 18, "w": 16, "h": 16}
    assert data["meta"]["size"] == {"w": 34, "h": 70}


def test_character_json():
    proj = project_with(anim("walk", fps=10), anim("idle", fps=6, loop=True, frame_count=4))
    data = build_character_json(proj, proj.animations)
    assert data == {
        "name": "Chevalier",
        "view": "topdown4",
        "frame_size": 64,
        "anchor": {"x": 32, "y": 60},
        "directions": ["down", "left", "right", "up"],
        "animations": [
            {
                "name": "walk",
                "image": "walk.png",
                "data": "walk.json",
                "fps": 10,
                "loop": True,
                "frame_count": 6,
            },
            {
                "name": "idle",
                "image": "idle.png",
                "data": "idle.json",
                "fps": 6,
                "loop": True,
                "frame_count": 4,
            },
        ],
    }


def test_export_zip_layout(tmp_path):
    proj = project_with(anim("walk"))
    path = JsonAtlasExporter().export(proj, {"walk": colored_frames(6, 64)}, tmp_path / "x.zip")
    with zipfile.ZipFile(path) as z:
        names = set(z.namelist())
        assert {
            "chevalier/walk.png",
            "chevalier/walk.json",
            "chevalier/character.json",
            "chevalier/godot/load_spriteframes.gd",
        } <= names
        assert json.loads(z.read("chevalier/walk.json"))["meta"]["image"] == "walk.png"
        assert json.loads(z.read("chevalier/character.json"))["animations"][0]["name"] == "walk"
        gd = z.read("chevalier/godot/load_spriteframes.gd").decode()
        assert "static func build(json_path: String) -> SpriteFrames" in gd


def test_export_slugifies_folder(tmp_path):
    proj = project_with(anim("walk"), name="Élan Bleu!")
    path = JsonAtlasExporter().export(proj, {"walk": colored_frames(2, 64)}, tmp_path / "x.zip")
    assert "elan-bleu/walk.png" in zipfile.ZipFile(path).namelist()


def test_export_rejects_incomplete(tmp_path):
    proj = project_with(anim("walk", statuses={Direction.up: "stale"}))
    with pytest.raises(ExportIncomplete) as e:
        JsonAtlasExporter().export(proj, {"walk": colored_frames(6, 64)}, tmp_path / "x.zip")
    assert e.value.missing == ["walk_up"]
    assert not (tmp_path / "x.zip").exists()


def test_export_missing_lists_all_in_order(tmp_path):
    proj = project_with(
        anim("idle", statuses={Direction.right: "empty", Direction.down: "generating"}),
        anim("walk", statuses={Direction.up: "stale"}),
    )
    with pytest.raises(ExportIncomplete) as e:
        JsonAtlasExporter().export(proj, {}, tmp_path / "x.zip")
    assert e.value.missing == ["idle_down", "idle_right", "walk_up"]


def test_export_ready_status_without_frames_is_missing(tmp_path):
    proj = project_with(anim("walk"))
    proj.animations[0].directions[Direction.left].frames = []
    with pytest.raises(ExportIncomplete) as e:
        JsonAtlasExporter().export(proj, {"walk": colored_frames(6, 64)}, tmp_path / "x.zip")
    assert e.value.missing == ["walk_left"]


def test_export_requires_an_animation(tmp_path):
    with pytest.raises(ExportIncomplete) as e:
        JsonAtlasExporter().export(project_with(), {}, tmp_path / "x.zip")
    assert e.value.missing == []
    assert "no animation" in str(e.value).lower()


def test_export_ready_animation_absent_from_processed_is_value_error(tmp_path):
    with pytest.raises(ValueError, match="walk"):
        JsonAtlasExporter().export(project_with(anim("walk")), {}, tmp_path / "x.zip")
