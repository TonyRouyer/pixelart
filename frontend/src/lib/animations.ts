import type { AnimationType } from "../api/types";

/** Saved animations missing from the ticked ones: saving deletes them with their frames. */
export function removedAnimations(saved: AnimationType[], enabled: AnimationType[]): AnimationType[] {
  const keep = new Set(enabled);
  return saved.filter((t) => !keep.has(t));
}

/** Confirmation text before deleting the animations labelled `labels`. */
export function removalPrompt(labels: string[]): string {
  return labels.length === 1
    ? `Supprimer l'animation ${labels[0]} et ses frames ?`
    : `Supprimer les animations ${labels.join(", ")} et leurs frames ?`;
}
