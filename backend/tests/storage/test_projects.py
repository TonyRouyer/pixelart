import pytest

from pixelforge.storage.local import LocalStorage
from pixelforge.storage.projects import ProjectNotFound, ProjectRepository


def test_create_get_list_delete(tmp_path):
    repo = ProjectRepository(LocalStorage(tmp_path))
    p = repo.create("Chevalier Bleu")
    assert p.id.startswith("chevalier-bleu-")
    assert repo.get(p.id) == p and [x.id for x in repo.list()] == [p.id]
    repo.delete(p.id)
    with pytest.raises(ProjectNotFound):
        repo.get(p.id)
    assert repo.list() == []


def test_create_options_and_defaults(tmp_path):
    repo = ProjectRepository(LocalStorage(tmp_path))
    p = repo.create("Élan!! ", output_size=32, style_prompt="custom")
    assert p.id.startswith("elan-") and len(p.id) == len("elan-") + 4
    assert p.output_size == 32 and p.style_prompt == "custom"
    assert set(p.views.values()) == {"pending"}
    assert repo.create("???").id.startswith("project-")


def test_save_persists_changes(tmp_path):
    repo = ProjectRepository(LocalStorage(tmp_path))
    p = repo.create("a")
    p.mirror_right = True
    repo.save(p)
    assert repo.get(p.id).mirror_right is True


def test_list_ignores_other_files_and_sorts(tmp_path):
    s = LocalStorage(tmp_path)
    repo = ProjectRepository(s)
    a, b = repo.create("a"), repo.create("b")
    s.write_bytes(f"projects/{a.id}/reference/input.png", b"x")
    assert [x.id for x in repo.list()] == sorted([a.id, b.id])
