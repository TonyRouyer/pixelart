import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, fileUrl } from "../api/client";
import type { AnimationConfig, Direction, Preview } from "../api/types";
import { DIRECTIONS } from "../api/types";
import { ErrorNote, toErrorInfo } from "../components/ErrorNote";
import { PixelSettingsPanel } from "../components/PixelSettingsPanel";
import { ProjectNav } from "../components/ProjectNav";
import { SpritePlayer } from "../components/SpritePlayer";
import { useProject } from "../hooks/useProject";
import { removeAt, reorder } from "../lib/playback";
import { frameNumber } from "../lib/review";
import { ANIMATION_LABEL } from "./AnimationsPage";

type Err = { message: string; hint: string | null } | null;
type Run = (action: () => Promise<unknown>) => Promise<void>;

const DIRECTION_LABEL: Record<Direction, string> = {
  down: "Bas",
  left: "Gauche",
  right: "Droite",
  up: "Haut",
};

interface CellProps {
  pid: string;
  anim: AnimationConfig;
  direction: Direction;
  version: number;
  busy: boolean;
  run: Run;
  reload(): Promise<void>;
}

function DirectionCell({ pid, anim, direction, version, busy, run, reload }: CellProps) {
  const state = anim.directions[direction];
  const [preview, setPreview] = useState<Preview | null>(null);
  const [dragFrom, setDragFrom] = useState<number | null>(null);

  // Processed frames change with the project version; refetch then.
  useEffect(() => {
    if (state.status === "empty") {
      setPreview(null);
      return;
    }
    let cancelled = false;
    api.preview(pid, anim.id, direction).then(
      (p) => !cancelled && setPreview(p),
      () => !cancelled && setPreview(null),
    );
    return () => {
      cancelled = true;
    };
  }, [pid, anim.id, direction, version, state.status]);

  const urls = preview ? preview.frames.map((k) => `${fileUrl(k)}?v=${version}`) : [];
  const locked = busy || state.status === "generating";
  const names = state.frames;

  const apply = (next: string[]) =>
    run(async () => {
      await api.setFrames(pid, anim.id, direction, next);
      await reload();
    });

  return (
    <div className="card review-cell" data-testid={`cell-${anim.id}-${direction}`}>
      <div className="review-head">
        <strong>{DIRECTION_LABEL[direction]}</strong>{" "}
        <span className={`badge badge-${state.status}`}>
          {state.status === "stale" ? "à régénérer" : state.status}
        </span>
      </div>
      {state.status === "empty" ? (
        <p className="muted">Pas encore générée</p>
      ) : (
        <>
          <div className="players">
            <SpritePlayer frames={urls} fps={anim.fps} loop={anim.loop} scale={1} />
            <SpritePlayer frames={urls} fps={anim.fps} loop={anim.loop} scale={4} />
          </div>
          <ol className="strip">
            {names.map((name, i) => (
              <li
                key={name}
                className="frame"
                draggable={!locked}
                onDragStart={() => setDragFrom(i)}
                onDragOver={(e) => e.preventDefault()}
                onDrop={(e) => {
                  e.preventDefault();
                  if (dragFrom !== null && dragFrom !== i) void apply(reorder(names, dragFrom, i));
                  setDragFrom(null);
                }}
              >
                {urls[i] && <img className="pixelated" src={urls[i]} alt={`Frame ${name}`} />}
                <span className="muted">{name}</span>
                <div className="frame-actions">
                  <button
                    disabled={locked}
                    title="Régénérer"
                    onClick={() =>
                      void run(() => api.regenerateFrame(pid, anim.id, direction, frameNumber(name)))
                    }
                  >
                    ↻
                  </button>
                  <button
                    disabled={locked || names.length <= 1}
                    title="Supprimer"
                    onClick={() => void apply(removeAt(names, i))}
                  >
                    ✕
                  </button>
                  <label className={`button${locked ? " disabled" : ""}`} title="Importer">
                    ⤒
                    <input
                      type="file"
                      accept="image/*"
                      hidden
                      disabled={locked}
                      onChange={(e) => {
                        const f = e.target.files?.[0];
                        e.target.value = "";
                        if (f)
                          void run(async () => {
                            await api.importFrame(pid, anim.id, direction, frameNumber(name), f);
                            await reload();
                          });
                      }}
                    />
                  </label>
                </div>
              </li>
            ))}
          </ol>
        </>
      )}
    </div>
  );
}

export function ReviewPage() {
  const { id = "" } = useParams();
  const { project, version, reload } = useProject(id);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<Err>(null);

  const run: Run = async (action) => {
    setBusy(true);
    setError(null);
    try {
      await action();
    } catch (e) {
      setError(toErrorInfo(e));
    } finally {
      setBusy(false);
    }
  };

  if (!project) return <p className="muted">Chargement…</p>;

  return (
    <div>
      <ProjectNav project={project} />
      <h1>Revue</h1>
      <ErrorNote error={error} />
      <div className="review-layout">
        <div className="review-main">
          {project.animations.length === 0 && (
            <p className="muted">
              Aucune animation configurée. <Link to={`/p/${id}/animations`}>Configurer</Link>
            </p>
          )}
          {project.animations.map((anim) => (
            <section key={anim.id} data-animation={anim.id}>
              <h2>{ANIMATION_LABEL[anim.type]}</h2>
              <div className="review-grid">
                {DIRECTIONS.map((d) => (
                  <DirectionCell
                    key={d}
                    pid={id}
                    anim={anim}
                    direction={d}
                    version={version}
                    busy={busy}
                    run={run}
                    reload={reload}
                  />
                ))}
              </div>
            </section>
          ))}
          <Link className="button" to={`/p/${id}/export`}>
            Passer à l'export
          </Link>
        </div>
        <PixelSettingsPanel project={project} />
      </div>
    </div>
  );
}
