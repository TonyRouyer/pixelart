"""ComfyUI client protocol and HTTP + WebSocket implementation."""

import io
import json
import uuid
from collections.abc import Callable
from typing import Any, Literal, Protocol

import httpx
from PIL import Image
from websockets.asyncio.client import connect
from websockets.exceptions import WebSocketException

ComfyErrorKind = Literal["unreachable", "oom", "execution", "interrupted"]

_OOM_MARKERS = ("outofmemory", "out of memory")


class ComfyError(Exception):
    def __init__(self, kind: ComfyErrorKind, message: str = "") -> None:
        super().__init__(f"{kind}: {message}" if message else kind)
        self.kind: ComfyErrorKind = kind
        self.message = message


class ComfyClient(Protocol):
    async def upload_image(self, img: Image.Image, name: str) -> str: ...

    async def run(self, workflow: dict, on_progress: Callable[[float], None]) -> list[Image.Image]:
        """Execute ``workflow``; return the images of every SaveImage node, by node id."""
        ...

    async def interrupt(self) -> None: ...

    async def object_info(self) -> dict: ...

    async def models(self, folder: str) -> list[str]: ...


def _node_order(node_id: str) -> tuple[int, int | str]:
    return (0, int(node_id)) if node_id.isdigit() else (1, node_id)


def _execution_error(data: dict[str, Any]) -> ComfyError:
    exc_type = str(data.get("exception_type", ""))
    exc_message = str(data.get("exception_message", ""))
    text = f"{exc_type} {exc_message}".lower()
    kind: ComfyErrorKind = "oom" if any(m in text for m in _OOM_MARKERS) else "execution"
    node = data.get("node_id")
    where = f" (node {node})" if node is not None else ""
    return ComfyError(kind, f"{exc_type}: {exc_message}{where}".strip(": "))


def _prompt_rejection(response: httpx.Response) -> ComfyError:
    try:
        body = response.json()
    except ValueError:
        return ComfyError("execution", f"prompt rejected ({response.status_code})")
    details = [body.get("error", {}).get("message", "prompt rejected")]
    for node_id, node in (body.get("node_errors") or {}).items():
        for err in node.get("errors", []):
            details.append(f"node {node_id}: {err.get('message', '')} {err.get('details', '')}")
    return ComfyError("execution", "; ".join(d.strip() for d in details))


class HttpComfyClient:
    def __init__(
        self,
        base_url: str,
        client_id: str | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout: float = 30.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.client_id = client_id or uuid.uuid4().hex
        self._transport = transport
        self._timeout = timeout

    @property
    def ws_url(self) -> str:
        scheme, _, rest = self.base_url.partition("://")
        ws_scheme = "wss" if scheme == "https" else "ws"
        return f"{ws_scheme}://{rest}/ws?clientId={self.client_id}"

    async def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        try:
            async with httpx.AsyncClient(
                base_url=self.base_url, transport=self._transport, timeout=self._timeout
            ) as http:
                return await http.request(method, path, **kwargs)
        except httpx.TransportError as exc:
            raise ComfyError("unreachable", f"{self.base_url}: {exc}") from exc

    async def _json(self, method: str, path: str, **kwargs: Any) -> Any:
        response = await self._request(method, path, **kwargs)
        if response.is_error:
            raise ComfyError("execution", f"{method} {path} -> HTTP {response.status_code}")
        return response.json()

    async def upload_image(self, img: Image.Image, name: str) -> str:
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        body = await self._json(
            "POST",
            "/upload/image",
            files={"image": (name, buf.getvalue(), "image/png")},
            data={"overwrite": "true"},
        )
        subfolder = body.get("subfolder") or ""
        return f"{subfolder}/{body['name']}" if subfolder else body["name"]

    async def interrupt(self) -> None:
        await self._request("POST", "/interrupt")

    async def object_info(self) -> dict:
        return await self._json("GET", "/object_info")

    async def models(self, folder: str) -> list[str]:
        return await self._json("GET", f"/models/{folder}")

    async def run(self, workflow: dict, on_progress: Callable[[float], None]) -> list[Image.Image]:
        try:
            async with connect(self.ws_url, max_size=None) as ws:
                prompt_id = await self._queue(workflow)
                async for raw in ws:
                    if isinstance(raw, bytes):
                        continue  # binary frames are live previews
                    if self._handle(json.loads(raw), prompt_id, on_progress):
                        break
                else:
                    raise ComfyError("unreachable", "websocket closed before the prompt finished")
        except (OSError, WebSocketException) as exc:
            raise ComfyError("unreachable", f"{self.ws_url}: {exc}") from exc
        return await self._collect(workflow, prompt_id)

    async def _queue(self, workflow: dict) -> str:
        response = await self._request(
            "POST", "/prompt", json={"prompt": workflow, "client_id": self.client_id}
        )
        if response.is_error:
            raise _prompt_rejection(response)
        return response.json()["prompt_id"]

    @staticmethod
    def _handle(message: dict, prompt_id: str, on_progress: Callable[[float], None]) -> bool:
        """Process one WS message; return True once the prompt has finished."""
        kind, data = message.get("type"), message.get("data") or {}
        if data.get("prompt_id", prompt_id) != prompt_id:
            return False
        if kind == "progress" and data.get("max"):
            on_progress(data["value"] / data["max"])
        elif kind == "executing":
            return data.get("node") is None and data.get("prompt_id") == prompt_id
        elif kind == "execution_error":
            raise _execution_error(data)
        elif kind == "execution_interrupted":
            raise ComfyError("interrupted", "generation interrupted")
        return False

    async def _collect(self, workflow: dict, prompt_id: str) -> list[Image.Image]:
        history = await self._json("GET", f"/history/{prompt_id}")
        outputs = history.get(prompt_id, {}).get("outputs", {})
        save_nodes = sorted(
            (nid for nid, n in workflow.items() if n.get("class_type") == "SaveImage"),
            key=_node_order,
        )
        images: list[Image.Image] = []
        for node_id in save_nodes:
            for ref in outputs.get(node_id, {}).get("images", []):
                images.append(await self._view(ref))
        return images

    async def _view(self, ref: dict) -> Image.Image:
        response = await self._request(
            "GET",
            "/view",
            params={
                "filename": ref["filename"],
                "subfolder": ref.get("subfolder", ""),
                "type": ref.get("type", "output"),
            },
        )
        if response.is_error:
            raise ComfyError("execution", f"cannot download {ref['filename']}")
        with Image.open(io.BytesIO(response.content)) as img:
            return img.convert("RGBA")
