// Mirrors the Pydantic models of backend/src/pixelforge (snake_case field names).

export type Direction = "down" | "left" | "right" | "up";
export const DIRECTIONS: readonly Direction[] = ["down", "left", "right", "up"];

export type AnimationType =
  | "idle"
  | "walk"
  | "attack_unarmed"
  | "attack_sword"
  | "attack_spear"
  | "attack_bow";

export interface PaletteSettings {
  mode: "auto" | "preset" | "custom";
  colors: number;
  preset: string | null;
  custom_colors: string[] | null;
}

export interface OutlineSettings {
  enabled: boolean;
  color: string;
}

export interface PixelSettings {
  palette: PaletteSettings;
  outline: OutlineSettings;
  alpha_threshold: number;
  padding: number;
}

export interface DirectionState {
  frames: string[];
  status: "empty" | "generating" | "ready" | "stale";
}

export interface AnimationConfig {
  id: string;
  type: AnimationType;
  frame_count: number;
  fps: number;
  loop: boolean;
  directions: Record<Direction, DirectionState>;
}

export interface ReferenceState {
  status: "none" | "candidates" | "validated";
  candidates: string[];
}

export type ViewStatus = "pending" | "generated" | "validated";

export interface Project {
  id: string;
  name: string;
  view: "topdown4";
  style_prompt: string;
  seed: number;
  output_size: number;
  pixel_settings: PixelSettings;
  reference: ReferenceState;
  views: Record<Direction, ViewStatus>;
  mirror_right: boolean;
  animations: AnimationConfig[];
}

export type JobStatus = "queued" | "running" | "succeeded" | "failed" | "cancelled";

export interface JobError {
  code: string;
  message: string;
  hint?: string | null;
}

export interface Job {
  id: string;
  kind: string;
  project_id: string;
  target: string;
  status: JobStatus;
  progress: number;
  error: JobError | null;
  created_at: string;
  finished_at: string | null;
}

export interface ComfyHealth {
  comfy_reachable: boolean;
  missing_nodes: string[];
  missing_models: string[];
  ok: boolean;
}

export interface HealthResponse {
  backend: string;
  comfy: ComfyHealth;
}

export interface ApiErrorBody {
  error: { code: string; message: string; hint: string | null };
}

// Request bodies
export interface ProjectCreate {
  name: string;
  output_size?: number;
  style_prompt?: string | null;
}

export interface ProjectPatch {
  name?: string;
  style_prompt?: string | null;
  output_size?: number;
  pixel_settings?: PixelSettings;
  mirror_right?: boolean;
}

export interface AnimationConfigIn {
  type: AnimationType;
  frame_count: number;
  fps: number;
}

// Responses
export interface UploadResult {
  project: Project;
  job: Job;
}

export interface Preview {
  fps: number;
  loop: boolean;
  frames: string[];
}

export interface ExportResult {
  key: string;
  url: string;
}

export type ServerEvent =
  | { type: "job"; job: Job }
  | { type: "project"; project: Project };
