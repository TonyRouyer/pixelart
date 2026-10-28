import type {
  AnimationConfigIn,
  ApiErrorBody,
  Direction,
  ExportResult,
  HealthResponse,
  Job,
  Preview,
  Project,
  ProjectCreate,
  ProjectPatch,
  UploadResult,
} from "./types";

export class ApiError extends Error {
  code: string;
  hint: string | null;
  status: number;

  constructor(status: number, code: string, message: string, hint: string | null = null) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.hint = hint;
    this.status = status;
  }
}

const BASE = "/api";

export function fileUrl(key: string): string {
  return `${BASE}/files/${key.split("/").map(encodeURIComponent).join("/")}`;
}

async function toApiError(res: Response): Promise<ApiError> {
  try {
    const body = (await res.json()) as Partial<ApiErrorBody>;
    if (body.error && typeof body.error.code === "string") {
      return new ApiError(res.status, body.error.code, body.error.message, body.error.hint ?? null);
    }
  } catch {
    // not JSON: fall through
  }
  return new ApiError(res.status, `http_${res.status}`, res.statusText || `HTTP ${res.status}`);
}

async function request<T>(method: string, path: string, body?: unknown | FormData): Promise<T> {
  const init: RequestInit = { method };
  if (body instanceof FormData) {
    init.body = body;
  } else if (body !== undefined) {
    init.headers = { "Content-Type": "application/json" };
    init.body = JSON.stringify(body);
  }
  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, init);
  } catch (e) {
    throw new ApiError(0, "network", e instanceof Error ? e.message : "network error");
  }
  if (!res.ok) throw await toApiError(res);
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

function fileForm(file: Blob): FormData {
  const form = new FormData();
  form.append("file", file);
  return form;
}

const enc = encodeURIComponent;
const animPath = (pid: string, anim: string) => `/projects/${enc(pid)}/animations/${enc(anim)}`;

export const api = {
  listProjects: () => request<Project[]>("GET", "/projects"),
  createProject: (body: ProjectCreate) => request<Project>("POST", "/projects", body),
  getProject: (pid: string) => request<Project>("GET", `/projects/${enc(pid)}`),
  updateProject: (pid: string, patch: ProjectPatch) =>
    request<Project>("PATCH", `/projects/${enc(pid)}`, patch),
  deleteProject: (pid: string) => request<void>("DELETE", `/projects/${enc(pid)}`),

  uploadReference: (pid: string, file: Blob) =>
    request<UploadResult>("POST", `/projects/${enc(pid)}/reference/upload`, fileForm(file)),
  generateReference: (pid: string, prompt: string, n?: number) =>
    request<Job>("POST", `/projects/${enc(pid)}/reference/generate`, { prompt, n }),
  selectReference: (pid: string, index: number) =>
    request<Project>("POST", `/projects/${enc(pid)}/reference/select`, { index }),

  generateViews: (pid: string, direction?: Direction) =>
    request<Job>("POST", `/projects/${enc(pid)}/views/generate`, { direction }),
  validateView: (pid: string, direction: Direction) =>
    request<Project>("POST", `/projects/${enc(pid)}/views/${direction}/validate`),

  configureAnimations: (pid: string, configs: AnimationConfigIn[]) =>
    request<Project>("POST", `/projects/${enc(pid)}/animations`, configs),
  generateAnimation: (pid: string, anim: string, directions?: Direction[]) =>
    request<Job[]>("POST", `${animPath(pid, anim)}/generate`, { directions }),
  regenerateFrame: (pid: string, anim: string, direction: Direction, i: number) =>
    request<Job>("POST", `${animPath(pid, anim)}/${direction}/frames/${i}/regenerate`),
  setFrames: (pid: string, anim: string, direction: Direction, frames: string[]) =>
    request<Project>("PUT", `${animPath(pid, anim)}/${direction}/frames`, { frames }),
  importFrame: (pid: string, anim: string, direction: Direction, i: number, file: Blob) =>
    request<Project>("POST", `${animPath(pid, anim)}/${direction}/frames/${i}/import`, fileForm(file)),
  preview: (pid: string, anim: string, direction: Direction) =>
    request<Preview>("GET", `/projects/${enc(pid)}/preview/${enc(anim)}/${direction}`),

  exportProject: (pid: string) => request<ExportResult>("POST", `/projects/${enc(pid)}/export`),

  listJobs: (projectId?: string) =>
    request<Job[]>("GET", projectId ? `/jobs?project_id=${enc(projectId)}` : "/jobs"),
  cancelJob: (id: string) => request<Job>("DELETE", `/jobs/${enc(id)}`),

  health: () => request<HealthResponse>("GET", "/health"),
  palettePresets: () => request<Record<string, string[]>>("GET", "/presets/palettes"),
};
