from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PIXELFORGE_", env_file=".env", extra="ignore")

    comfy_url: str = "http://127.0.0.1:8188"
    data_dir: Path = Path("data")
    checkpoint: str = "sd_xl_base_1.0.safetensors"
    lora: str = "pixel-art-xl.safetensors"
    lora_strength: float = 1.0
    controlnet_openpose: str = "controlnet-openpose-sdxl-1.0.safetensors"
    ipadapter_preset: str = "PLUS (high strength)"
    grid_canvas: int = 1024
    fake_comfy: bool = False  # demo mode: no GPU, ComfyUI replaced by SpriteFakeComfyClient
    cors_origins: list[str] = ["http://localhost:5173"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
