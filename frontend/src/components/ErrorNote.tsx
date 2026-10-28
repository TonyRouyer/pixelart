import { ApiError } from "../api/client";

/** Turn a thrown value into the message to show inline. */
export function toErrorInfo(e: unknown): { message: string; hint: string | null } {
  if (e instanceof ApiError) return { message: e.message, hint: e.hint };
  return { message: e instanceof Error ? e.message : "Erreur inconnue", hint: null };
}

export function ErrorNote({ error }: { error: { message: string; hint: string | null } | null }) {
  if (!error) return null;
  return (
    <div className="error-note" role="alert">
      {error.message}
      {error.hint && <div className="muted">{error.hint}</div>}
    </div>
  );
}
