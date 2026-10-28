from typing import Any

import pytest

from pixelforge.comfy.workflows import (
    WORKFLOW_NAMES,
    MissingBinding,
    bind,
    load_workflow,
    params,
    required_nodes,
)

IMAGE_PARAMS = {"reference_image", "pose_image", "source_image", "mask_image"}
INT_PARAMS = {"seed", "width", "height", "batch"}

SAMPLER_PARAMS = {"checkpoint", "lora", "lora_strength", "positive", "negative", "seed"}
GUIDED_PARAMS = SAMPLER_PARAMS | {"controlnet", "ipadapter_preset", "reference_image", "pose_image"}
LATENT_PARAMS = {"width", "height", "batch"}

EXPECTED_PARAMS = {
    "txt2img": SAMPLER_PARAMS | LATENT_PARAMS,
    "remove_bg": {"source_image"},
    "turnaround": GUIDED_PARAMS | LATENT_PARAMS,
    "pose_grid": GUIDED_PARAMS | LATENT_PARAMS,
    "pose_inpaint": GUIDED_PARAMS | {"source_image", "mask_image"},
}


def sample_value(param: str) -> Any:
    if param in IMAGE_PARAMS:
        return f"{param}.png"
    if param in INT_PARAMS:
        return 7
    if param == "lora_strength":
        return 0.75
    return f"value-of-{param}"


def defaults(wf: dict) -> dict[str, Any]:
    return {p: sample_value(p) for p in params(wf)}


def node_by_title(wf: dict, title: str) -> dict:
    return next(n for n in wf.values() if n["_meta"]["title"] == title)


def nodes_of(wf: dict, class_type: str) -> list[dict]:
    return [n for n in wf.values() if n["class_type"] == class_type]


@pytest.mark.parametrize(
    "name", ["txt2img", "remove_bg", "turnaround", "pose_grid", "pose_inpaint"]
)
def test_workflows_load_and_bind(name):
    wf = load_workflow(name)
    bound = bind(wf, {p: sample_value(p) for p in params(wf)})
    assert not any(str(v).startswith("IN:") for n in bound.values() for v in n["inputs"].values())


def test_bind_sets_field():
    wf = load_workflow("txt2img")
    out = bind(wf, {**defaults(wf), "seed": 42})
    ks = next(n for n in out.values() if n["_meta"]["title"] == "IN:seed:seed")
    assert ks["inputs"]["seed"] == 42 and wf != out


def test_bind_missing_raises():
    with pytest.raises(MissingBinding):
        bind(load_workflow("txt2img"), {})


def test_bind_unknown_value_raises():
    wf = load_workflow("remove_bg")
    with pytest.raises(MissingBinding):
        bind(wf, {"source_image": "a.png", "seed": 1})


def test_bind_does_not_mutate_template():
    wf = load_workflow("txt2img")
    bind(wf, defaults(wf))
    assert node_by_title(wf, "IN:seed:seed")["inputs"]["seed"] == "IN:seed:seed"


def test_unknown_workflow_rejected():
    with pytest.raises(ValueError):
        load_workflow("../config")


def test_workflow_names():
    assert WORKFLOW_NAMES == ("txt2img", "remove_bg", "turnaround", "pose_grid", "pose_inpaint")


@pytest.mark.parametrize("name", WORKFLOW_NAMES)
def test_params(name):
    assert params(load_workflow(name)) == EXPECTED_PARAMS[name]


@pytest.mark.parametrize("name", WORKFLOW_NAMES)
def test_api_format_and_links(name):
    wf = load_workflow(name)
    titles = []
    for node_id, node in wf.items():
        assert isinstance(node_id, str) and node_id.isdigit()
        assert set(node) == {"class_type", "inputs", "_meta"}
        titles.append(node["_meta"]["title"])
        for value in node["inputs"].values():
            if isinstance(value, list):
                src, idx = value
                assert src in wf and isinstance(idx, int) and idx >= 0
    bound_titles = [t for t in titles if t.startswith("IN:")]
    assert len(bound_titles) == len(set(bound_titles))
    for title in bound_titles:
        _, _, field = title.split(":")
        assert node_by_title(wf, title)["inputs"][field] == title
    assert nodes_of(wf, "SaveImage")


def test_required_nodes():
    assert required_nodes(load_workflow("remove_bg")) == {"LoadImage", "RMBG", "SaveImage"}
    guided = required_nodes(load_workflow("pose_grid"))
    assert {
        "CheckpointLoaderSimple",
        "LoraLoader",
        "IPAdapterUnifiedLoader",
        "IPAdapterAdvanced",
        "ControlNetLoader",
        "ControlNetApplyAdvanced",
        "KSampler",
    } <= guided
    assert {"InpaintModelConditioning", "LoadImageMask"} <= required_nodes(
        load_workflow("pose_inpaint")
    )


def test_sampler_and_guidance_defaults():
    for name in ("txt2img", "turnaround", "pose_grid", "pose_inpaint"):
        ks = nodes_of(load_workflow(name), "KSampler")[0]["inputs"]
        assert (ks["steps"], ks["cfg"], ks["sampler_name"], ks["scheduler"], ks["denoise"]) == (
            25,
            6.0,
            "dpmpp_2m",
            "karras",
            1.0,
        )
    wf = load_workflow("pose_grid")
    cn = nodes_of(wf, "ControlNetApplyAdvanced")[0]["inputs"]
    assert cn["strength"] == 0.9 and cn["end_percent"] == 0.9
    assert nodes_of(wf, "IPAdapterAdvanced")[0]["inputs"]["weight"] == 0.8
    assert nodes_of(load_workflow("remove_bg"), "RMBG")[0]["inputs"]["model"] == "RMBG-2.0"


def test_bound_values_reach_their_nodes():
    wf = load_workflow("pose_grid")
    out = bind(wf, {**defaults(wf), "width": 1024, "lora_strength": 0.6})
    latent = nodes_of(out, "EmptyLatentImage")[0]["inputs"]
    width_src = out[latent["width"][0]]
    assert width_src["inputs"]["value"] == 1024
    lora = nodes_of(out, "LoraLoader")[0]["inputs"]
    assert out[lora["strength_model"][0]]["inputs"]["value"] == 0.6
    assert lora["strength_model"] == lora["strength_clip"]


def test_inpaint_sampler_fed_by_inpaint_conditioning():
    wf = load_workflow("pose_inpaint")
    ids = {nid for nid, n in wf.items() if n["class_type"] == "InpaintModelConditioning"}
    ks = nodes_of(wf, "KSampler")[0]["inputs"]
    assert ks["positive"][0] in ids and ks["negative"][0] in ids and ks["latent_image"][0] in ids
    assert not nodes_of(wf, "EmptyLatentImage")
