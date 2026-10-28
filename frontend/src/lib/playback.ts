/** Index of the frame to show `elapsedMs` after the start of playback. */
export function frameAt(elapsedMs: number, fps: number, count: number, loop: boolean): number {
  if (count <= 0) return 0;
  const index = Math.max(0, Math.floor((elapsedMs * fps) / 1000));
  return loop ? index % count : Math.min(index, count - 1);
}

/** A copy of `frames` with the item at `from` moved to position `to`. */
export function reorder(frames: string[], from: number, to: number): string[] {
  const inRange = (i: number) => Number.isInteger(i) && i >= 0 && i < frames.length;
  if (!inRange(from) || !inRange(to)) return frames;
  const next = [...frames];
  const [moved] = next.splice(from, 1);
  next.splice(to, 0, moved);
  return next;
}

/** A copy of `frames` without `index`; the list is returned unchanged if it would become empty. */
export function removeAt(frames: string[], index: number): string[] {
  if (frames.length <= 1 || index < 0 || index >= frames.length) return frames;
  return frames.filter((_, i) => i !== index);
}
