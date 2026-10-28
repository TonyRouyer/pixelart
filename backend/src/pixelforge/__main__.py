import uvicorn

from pixelforge.api.app import create_app
from pixelforge.config import get_settings


def main() -> None:
    uvicorn.run(create_app(get_settings()), host="127.0.0.1", port=8000)


if __name__ == "__main__":
    main()
