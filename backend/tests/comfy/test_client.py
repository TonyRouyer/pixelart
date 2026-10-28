import asyncio
import io
import json
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx
import pytest
from PIL import Image
from websockets.asyncio.server import serve

from pixelforge.comfy.client import ComfyError, HttpComfyClient
from pixelforge.comfy.fake import FakeComfyClient

PROMPT_ID = "p-123"
WORKFLOW = {
    "1": {"class_type": "LoadImage", "inputs": {"image": "a.png"}, "_meta": {"title": "x"}},
    "9": {"class_type": "SaveImage", "inputs": {"images": ["1", 0]}, "_meta": {"title": "b"}},
    "10": {"class_type": "SaveImage", "inputs": {"images": ["1", 0]}, "_meta": {"title": "a"}},
    "3": {"class_type": "PreviewImage", "inputs": {"images": ["1", 0]}, "_meta": {"title": "p"}},
}
COLORS = {"red.png": (255, 0, 0, 255), "blue.png": (0, 0, 255, 255), "prev.png": (0, 255, 0, 255)}


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def png_bytes(color) -> bytes:
    buf = io.BytesIO()
    Image.new("RGBA", (4, 4), color).save(buf, format="PNG")
    return buf.getvalue()


class FakeComfyServer:
    """HTTP side via httpx.MockTransport, WebSocket side via a real local websockets server."""

    def __init__(
        self,
        ws_messages: list,
        close: str | None = None,
        history_pending: int = 0,
        history_entry: dict | None = None,
    ):
        """``close``: "clean" or "abort" drops the socket after the messages.

        ``history_pending``: number of /history calls answered ``{}`` (prompt not finished)
        before ``history_entry`` (default: the outputs below) is returned.
        """
        self.ws_messages = ws_messages
        self.close = close
        self.history_pending = history_pending
        self.history_entry = history_entry
        self.history_calls = 0
        self.requests: list[httpx.Request] = []
        self.prompt_posted = asyncio.Event()
        self.ws_client_ids: list[str] = []
        self.transport = httpx.MockTransport(self.handle)

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = request.url.path
        if path == "/prompt":
            self.prompt_posted.set()
            return httpx.Response(200, json={"prompt_id": PROMPT_ID, "number": 0})
        if path == f"/history/{PROMPT_ID}":
            self.history_calls += 1
            if self.history_calls <= self.history_pending:
                return httpx.Response(200, json={})
            if self.history_entry is not None:
                return httpx.Response(200, json={PROMPT_ID: self.history_entry})
            outputs = {
                "10": {"images": [{"filename": "blue.png", "subfolder": "", "type": "output"}]},
                "9": {"images": [{"filename": "red.png", "subfolder": "pf", "type": "output"}]},
                "3": {"images": [{"filename": "prev.png", "subfolder": "", "type": "temp"}]},
            }
            return httpx.Response(200, json={PROMPT_ID: {"outputs": outputs}})
        if path == "/view":
            return httpx.Response(200, content=png_bytes(COLORS[request.url.params["filename"]]))
        return httpx.Response(404)

    async def ws_handler(self, ws):
        self.ws_client_ids.append(ws.request.path)
        await self.prompt_posted.wait()
        for msg in self.ws_messages:
            await ws.send(msg if isinstance(msg, bytes) else json.dumps(msg))
        if self.close == "clean":
            await ws.close()
        elif self.close == "abort":
            ws.transport.abort()
        else:
            await ws.wait_closed()


async def run_against(server: FakeComfyServer, progress: list[float], **client_kwargs):
    port = free_port()
    async with serve(server.ws_handler, "127.0.0.1", port):
        client = HttpComfyClient(
            f"http://127.0.0.1:{port}", client_id="cid", transport=server.transport, **client_kwargs
        )
        return await client.run(WORKFLOW, progress.append)


@pytest.fixture
def broken_system_proxy(monkeypatch):
    """Point every proxy variable at a closed port, without any localhost bypass."""
    dead = f"http://127.0.0.1:{free_port()}"
    for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "WS_PROXY", "WSS_PROXY"):
        monkeypatch.setenv(name, dead)
        monkeypatch.setenv(name.lower(), dead)
    for name in ("NO_PROXY", "no_proxy"):
        monkeypatch.delenv(name, raising=False)


def status(t: str, **data) -> dict:
    return {"type": t, "data": data}


async def test_http_client_unreachable():
    with pytest.raises(ComfyError) as e:
        await HttpComfyClient("http://127.0.0.1:9").object_info()
    assert e.value.kind == "unreachable"


async def test_http_client_run_unreachable():
    with pytest.raises(ComfyError) as e:
        await HttpComfyClient(f"http://127.0.0.1:{free_port()}").run(WORKFLOW, lambda p: None)
    assert e.value.kind == "unreachable"


async def test_http_client_run_flow():
    server = FakeComfyServer(
        [
            status("status", status={"exec_info": {"queue_remaining": 1}}),
            status("execution_start", prompt_id=PROMPT_ID),
            status("executing", node="1", prompt_id=PROMPT_ID),
            b"\x00\x00\x00\x01binary-preview",
            status("progress", value=1, max=2, prompt_id=PROMPT_ID, node="1"),
            status("progress", value=2, max=2, prompt_id=PROMPT_ID, node="1"),
            status("executing", node=None, prompt_id="other-prompt"),
            status("executing", node=None, prompt_id=PROMPT_ID),
        ]
    )
    progress: list[float] = []
    images = await run_against(server, progress)

    assert progress == [0.5, 1.0]
    # SaveImage nodes only, in node-id order ("9" before "10").
    assert [im.getpixel((0, 0)) for im in images] == [COLORS["red.png"], COLORS["blue.png"]]
    assert server.ws_client_ids == ["/ws?clientId=cid"]
    post = next(r for r in server.requests if r.url.path == "/prompt")
    assert json.loads(post.content) == {"prompt": WORKFLOW, "client_id": "cid"}
    view = next(r for r in server.requests if r.url.params.get("filename") == "red.png")
    assert dict(view.url.params) == {"filename": "red.png", "subfolder": "pf", "type": "output"}


async def test_oom_mapped():
    server = FakeComfyServer(
        [
            status(
                "execution_error",
                prompt_id=PROMPT_ID,
                node_id="16",
                exception_type="torch.OutOfMemoryError",
                exception_message="CUDA out of memory. Tried to allocate 2.00 GiB",
            )
        ]
    )
    with pytest.raises(ComfyError) as e:
        await run_against(server, [])
    assert e.value.kind == "oom"
    assert "out of memory" in e.value.message


async def test_oom_detected_from_message_only():
    server = FakeComfyServer(
        [
            status(
                "execution_error",
                prompt_id=PROMPT_ID,
                exception_type="RuntimeError",
                exception_message="CUDA out of memory.",
            )
        ]
    )
    with pytest.raises(ComfyError) as e:
        await run_against(server, [])
    assert e.value.kind == "oom"


async def test_execution_error_mapped():
    server = FakeComfyServer(
        [
            status(
                "execution_error",
                prompt_id=PROMPT_ID,
                exception_type="ValueError",
                exception_message="bad lora",
            )
        ]
    )
    with pytest.raises(ComfyError) as e:
        await run_against(server, [])
    assert e.value.kind == "execution" and "bad lora" in e.value.message


async def test_interrupted_mapped():
    server = FakeComfyServer([status("execution_interrupted", prompt_id=PROMPT_ID)])
    with pytest.raises(ComfyError) as e:
        await run_against(server, [])
    assert e.value.kind == "interrupted"


async def test_prompt_rejected_is_execution_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400,
            json={
                "error": {"type": "prompt_outputs_failed_validation", "message": "invalid"},
                "node_errors": {"3": {"errors": [{"message": "Value not in list"}]}},
            },
        )

    port = free_port()

    async def ws_handler(ws):
        await ws.wait_closed()

    async with serve(ws_handler, "127.0.0.1", port):
        client = HttpComfyClient(f"http://127.0.0.1:{port}", transport=httpx.MockTransport(handler))
        with pytest.raises(ComfyError) as e:
            await client.run(WORKFLOW, lambda p: None)
    assert e.value.kind == "execution" and "Value not in list" in e.value.message


async def test_small_endpoints():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path == "/upload/image":
            return httpx.Response(200, json={"name": "ref.png", "subfolder": "", "type": "input"})
        if request.url.path == "/object_info":
            return httpx.Response(200, json={"KSampler": {"input": {}}})
        if request.url.path == "/models/loras":
            return httpx.Response(200, json=["pixel-art-xl.safetensors"])
        if request.url.path == "/interrupt":
            return httpx.Response(200)
        return httpx.Response(404)

    client = HttpComfyClient("http://comfy.test", transport=httpx.MockTransport(handler))
    name = await client.upload_image(Image.new("RGBA", (2, 2), (1, 2, 3, 255)), "ref.png")
    assert name == "ref.png"
    upload = seen[-1]
    assert upload.method == "POST"
    body = upload.content
    assert b'name="image"; filename="ref.png"' in body and b'name="overwrite"' in body
    assert b"\x89PNG" in body

    assert await client.object_info() == {"KSampler": {"input": {}}}
    assert await client.models("loras") == ["pixel-art-xl.safetensors"]
    await client.interrupt()
    assert seen[-1].method == "POST" and seen[-1].url.path == "/interrupt"


async def test_fake_client_records_and_returns():
    img = Image.new("RGBA", (2, 2))
    progress: list[float] = []
    fake = FakeComfyClient(lambda wf: [img])
    assert await fake.run({"1": {}}, progress.append) == [img]
    assert fake.workflows == [{"1": {}}] and progress == [1.0]
    assert await fake.upload_image(img, "a.png") == "a.png" and fake.uploads == {"a.png": img}
    assert not fake.interrupted
    await fake.interrupt()
    assert fake.interrupted
    assert "RMBG" in await fake.object_info()
    assert await fake.models("unknown") == []


async def test_fake_client_propagates_responder_error():
    def boom(wf):
        raise ComfyError("oom", "CUDA out of memory")

    with pytest.raises(ComfyError) as e:
        await FakeComfyClient(boom).run({}, lambda p: None)
    assert e.value.kind == "oom"


class _ObjectInfoHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = json.dumps({"KSampler": {}}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


async def test_http_requests_ignore_system_proxy(broken_system_proxy):
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), _ObjectInfoHandler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        client = HttpComfyClient(f"http://127.0.0.1:{httpd.server_address[1]}")
        assert await client.object_info() == {"KSampler": {}}
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join()


async def test_websocket_ignores_system_proxy(broken_system_proxy):
    server = FakeComfyServer([status("executing", node=None, prompt_id=PROMPT_ID)])
    images = await run_against(server, [])
    assert [im.getpixel((0, 0)) for im in images] == [COLORS["red.png"], COLORS["blue.png"]]


@pytest.mark.parametrize("close", ["clean", "abort"])
async def test_websocket_drop_falls_back_to_history(close):
    server = FakeComfyServer(
        [status("progress", value=1, max=4, prompt_id=PROMPT_ID)], close=close, history_pending=2
    )
    progress: list[float] = []
    images = await run_against(server, progress, history_poll_interval=0.01)
    assert progress == [0.25]
    assert [im.getpixel((0, 0)) for im in images] == [COLORS["red.png"], COLORS["blue.png"]]
    assert server.history_calls == 3  # 2 polls while running, then the finished entry


async def test_websocket_drop_history_error_mapped():
    error = {
        "exception_type": "torch.OutOfMemoryError",
        "exception_message": "CUDA out of memory",
        "node_id": "16",
    }
    entry = {
        "outputs": {},
        "status": {
            "status_str": "error",
            "completed": False,
            "messages": [["execution_start", {}], ["execution_error", error]],
        },
    }
    server = FakeComfyServer([], close="clean", history_entry=entry)
    with pytest.raises(ComfyError) as e:
        await run_against(server, [], history_poll_interval=0.01)
    assert e.value.kind == "oom" and "node 16" in e.value.message


async def test_websocket_drop_history_interrupted_mapped():
    entry = {
        "outputs": {},
        "status": {"status_str": "error", "messages": [["execution_interrupted", {}]]},
    }
    server = FakeComfyServer([], close="clean", history_entry=entry)
    with pytest.raises(ComfyError) as e:
        await run_against(server, [], history_poll_interval=0.01)
    assert e.value.kind == "interrupted"


async def test_websocket_drop_without_history_is_unreachable():
    server = FakeComfyServer([], close="abort", history_pending=10**6)
    with pytest.raises(ComfyError) as e:
        await run_against(server, [], history_poll_interval=0.01, history_timeout=0.1)
    assert e.value.kind == "unreachable"
    assert 5 <= server.history_calls <= 20
