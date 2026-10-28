import { afterEach, expect, test, vi } from "vitest";
import { ApiError, api, fileUrl } from "./client";

afterEach(() => vi.restoreAllMocks());

test("api error is parsed", async () => {
  globalThis.fetch = vi.fn().mockResolvedValue(
    new Response(JSON.stringify({ error: { code: "conflict", message: "busy", hint: null } }), { status: 409 }),
  );
  await expect(api.getProject("x")).rejects.toMatchObject({ code: "conflict", status: 409 });
  await expect(api.getProject("x")).rejects.toBeInstanceOf(ApiError);
});

test("non-json error falls back to http_<status>", async () => {
  globalThis.fetch = vi.fn().mockResolvedValue(new Response("boom", { status: 502 }));
  await expect(api.listProjects()).rejects.toMatchObject({ code: "http_502", status: 502, hint: null });
});

test("network failure becomes an ApiError", async () => {
  globalThis.fetch = vi.fn().mockRejectedValue(new TypeError("fetch failed"));
  await expect(api.listProjects()).rejects.toMatchObject({ code: "network", status: 0 });
});

test("JSON body and method are sent", async () => {
  const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ id: "p" }), { status: 201 }));
  globalThis.fetch = fetchMock;
  await api.createProject({ name: "Hero", output_size: 32 });
  const [url, init] = fetchMock.mock.calls[0];
  expect(url).toBe("/api/projects");
  expect(init.method).toBe("POST");
  expect(JSON.parse(init.body)).toEqual({ name: "Hero", output_size: 32 });
  expect(init.headers["Content-Type"]).toBe("application/json");
});

test("uploads use multipart field file", async () => {
  const fetchMock = vi.fn().mockResolvedValue(new Response("{}", { status: 202 }));
  globalThis.fetch = fetchMock;
  await api.uploadReference("p1", new Blob(["x"]));
  const [url, init] = fetchMock.mock.calls[0];
  expect(url).toBe("/api/projects/p1/reference/upload");
  expect(init.body).toBeInstanceOf(FormData);
  expect((init.body as FormData).has("file")).toBe(true);
  expect(init.headers).toBeUndefined();
});

test("204 responses resolve to undefined", async () => {
  globalThis.fetch = vi.fn().mockResolvedValue(new Response(null, { status: 204 }));
  await expect(api.deleteProject("p")).resolves.toBeUndefined();
});

test("frame routes use the raw file number", async () => {
  const fetchMock = vi.fn().mockResolvedValue(new Response("{}", { status: 202 }));
  globalThis.fetch = fetchMock;
  await api.regenerateFrame("p", "walk", "down", 3);
  expect(fetchMock.mock.calls[0][0]).toBe("/api/projects/p/animations/walk/down/frames/3/regenerate");
});

test("fileUrl encodes each segment", () => {
  expect(fileUrl("projects/a b/001.png")).toBe("/api/files/projects/a%20b/001.png");
});
