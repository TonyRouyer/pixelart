import pytest
from pydantic import ValidationError

from pixelforge.domain.models import (
    DIRECTION_ORDER,
    AnimationConfig,
    AnimationType,
    PaletteSettings,
    Project,
)


def make_project(**overrides) -> Project:
    fields = {"id": "p1", "name": "Hero", "seed": 42}
    fields.update(overrides)
    return Project(**fields)


def test_bounds():
    base = AnimationConfig.from_type(AnimationType.walk).model_dump()
    with pytest.raises(ValidationError):
        AnimationConfig.model_validate({**base, "frame_count": 1})
    with pytest.raises(ValidationError):
        AnimationConfig.model_validate({**base, "frame_count": 17})
    with pytest.raises(ValidationError):
        make_project(output_size=8)
    with pytest.raises(ValidationError):
        make_project(output_size=512)


def test_defaults_from_type():
    a = AnimationConfig.from_type(AnimationType.attack_bow)
    assert (a.frame_count, a.fps, a.loop) == (6, 12, False)
    assert list(a.directions) == list(DIRECTION_ORDER)
    assert a.id == "attack_bow"


def test_all_default_animations():
    got = {t: (c.frame_count, c.fps, c.loop) for t, c in
           ((t, AnimationConfig.from_type(t)) for t in AnimationType)}
    assert got[AnimationType.idle] == (4, 6, True)
    assert got[AnimationType.walk] == (6, 10, True)
    assert got[AnimationType.attack_sword] == (6, 12, False)


def test_directions_must_be_complete():
    base = AnimationConfig.from_type(AnimationType.idle).model_dump()
    del base["directions"]["up"]
    with pytest.raises(ValidationError):
        AnimationConfig.model_validate(base)


def test_palette_validation():
    with pytest.raises(ValidationError):
        PaletteSettings(mode="preset")
    with pytest.raises(ValidationError):
        PaletteSettings(mode="custom", custom_colors=["#fff"])
    with pytest.raises(ValidationError):
        PaletteSettings(mode="custom", custom_colors=["#ffffff", "red"])
    with pytest.raises(ValidationError):
        PaletteSettings(colors=1)
    assert PaletteSettings(mode="custom", custom_colors=["#000000", "#ffffff"])
    assert PaletteSettings(mode="preset", preset="pico8")


def test_anchor():
    assert make_project(output_size=64).anchor() == (32, 60)
    assert make_project(output_size=16).anchor() == (8, 15)


def test_defaults_and_animation_lookup():
    p = make_project()
    assert p.output_size == 64
    assert p.view == "topdown4"
    assert p.reference.status == "none"
    assert p.views == {d: "pending" for d in DIRECTION_ORDER}
    p.animations.append(AnimationConfig.from_type(AnimationType.idle))
    assert p.animation("idle").type == AnimationType.idle
    with pytest.raises(KeyError):
        p.animation("nope")


def test_no_shared_mutable_defaults():
    a, b = make_project(), make_project()
    a.animations.append(AnimationConfig.from_type(AnimationType.idle))
    a.reference.candidates.append("x.png")
    assert b.animations == [] and b.reference.candidates == []


def test_roundtrip_json():
    p = make_project()
    p.animations.append(AnimationConfig.from_type(AnimationType.walk))
    assert Project.model_validate_json(p.model_dump_json()) == p
