import { useEffect, useRef } from "react";
import { frameAt } from "../lib/playback";

interface Props {
  /** Image URLs, in playback order. */
  frames: string[];
  fps: number;
  loop: boolean;
  scale: 1 | 4;
}

export function SpritePlayer({ frames, fps, loop, scale }: Props) {
  const canvas = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const el = canvas.current;
    const ctx = el?.getContext("2d");
    if (!el || !ctx || frames.length === 0) return;
    let cancelled = false;
    let raf = 0;
    const images = frames.map((src) => {
      const img = new Image();
      img.src = src;
      return img;
    });
    const start = performance.now();

    const draw = () => {
      if (cancelled) return;
      const img = images[frameAt(performance.now() - start, fps, images.length, loop)];
      if (img.complete && img.naturalWidth > 0) {
        const w = img.naturalWidth * scale;
        const h = img.naturalHeight * scale;
        if (el.width !== w || el.height !== h) {
          el.width = w;
          el.height = h;
        }
        ctx.imageSmoothingEnabled = false;
        ctx.clearRect(0, 0, w, h);
        ctx.drawImage(img, 0, 0, w, h);
      }
      raf = requestAnimationFrame(draw);
    };
    raf = requestAnimationFrame(draw);
    return () => {
      cancelled = true;
      cancelAnimationFrame(raf);
    };
  }, [frames, fps, loop, scale]);

  return <canvas ref={canvas} className="sprite-player" data-scale={scale} />;
}
