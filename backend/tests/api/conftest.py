import pytest
from fastapi.testclient import TestClient

from pixelforge.api.app import create_app
from pixelforge.comfy.client import ComfyError
from pixelforge.comfy.sprite_fake import SpriteFakeComfyClient
from pixelforge.config import Settings


class DownComfy(SpriteFakeComfyClient):
    async def object_info(self) -> dict:
        raise ComfyError("unreachable", "connection refused")


@pytest.fixture
def settings(tmp_path):
    return Settings(_env_file=None, data_dir=tmp_path, grid_canvas=256)


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings, SpriteFakeComfyClient())) as c:
        yield c


@pytest.fixture
def client_down(settings):
    with TestClient(create_app(settings, DownComfy())) as c:
        yield c
