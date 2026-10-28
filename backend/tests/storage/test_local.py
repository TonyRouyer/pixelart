import pytest
from PIL import Image

from pixelforge.storage import keys
from pixelforge.storage.local import LocalStorage


def test_atomic_write_leaves_no_temp(tmp_path):
    s = LocalStorage(tmp_path)
    s.write_json("a/b.json", {"x": 1})
    assert s.read_json("a/b.json") == {"x": 1}
    assert [p.name for p in (tmp_path / "a").iterdir()] == ["b.json"]


def test_overwrite_replaces(tmp_path):
    s = LocalStorage(tmp_path)
    s.write_bytes("f.bin", b"one")
    s.write_bytes("f.bin", b"two")
    assert s.read_bytes("f.bin") == b"two"
    assert [p.name for p in tmp_path.iterdir()] == ["f.bin"]


@pytest.mark.parametrize("key", ["../x", "a/../../x"])
def test_rejects_escape(tmp_path, key):
    s = LocalStorage(tmp_path)
    with pytest.raises(ValueError):
        s.write_bytes(key, b"")
    with pytest.raises(ValueError):
        s.path(key)


def test_image_roundtrip_rgba(tmp_path):
    s = LocalStorage(tmp_path)
    s.write_image("i/x.png", Image.new("RGB", (3, 2), (10, 20, 30)))
    img = s.read_image("i/x.png")
    assert img.mode == "RGBA" and img.size == (3, 2)
    assert img.getpixel((0, 0)) == (10, 20, 30, 255)


def test_exists_delete_list_delete_prefix(tmp_path):
    s = LocalStorage(tmp_path)
    for k in ["p/b/2.txt", "p/a.txt", "p/b/1.txt", "q/z.txt"]:
        s.write_bytes(k, b"x")
    assert s.exists("p/a.txt") and not s.exists("nope")
    assert s.list("p") == ["p/a.txt", "p/b/1.txt", "p/b/2.txt"]
    assert s.list("missing") == []
    s.delete("p/a.txt")
    s.delete("p/a.txt")  # idempotent
    assert not s.exists("p/a.txt")
    s.delete_prefix("p")
    s.delete_prefix("p")  # idempotent
    assert s.list("") == ["q/z.txt"]


def test_keys_match_spec():
    assert keys.project_json("p") == "projects/p/project.json"
    assert keys.reference_input("p") == "projects/p/reference/input.png"
    assert keys.reference_image("p") == "projects/p/reference/reference.png"
    assert keys.candidate("p", 2) == "projects/p/reference/candidates/2.png"
    assert keys.view_image("p", "down") == "projects/p/views/down.png"
    assert keys.raw_dir("p", "walk", "left") == "projects/p/animations/walk/left/raw"
    assert (
        keys.raw_frame("p", "walk", "left", "0.png") == "projects/p/animations/walk/left/raw/0.png"
    )
    assert (
        keys.processed_frame("p", "walk", "left", "0.png")
        == "projects/p/animations/walk/left/processed/0.png"
    )
    assert keys.export_zip("p", "20260101") == "projects/p/exports/20260101.zip"
