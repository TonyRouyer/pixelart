import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api/client";
import { DIRECTIONS, type Direction } from "../api/types";
import { ErrorNote, toErrorInfo } from "../components/ErrorNote";
import { ProjectNav } from "../components/ProjectNav";
import { imageUrl, useProject } from "../hooks/useProject";

type Err = { message: string; hint: string | null } | null;

const LABEL: Record<Direction, string> = {
  down: "Bas",
  left: "Gauche",
  right: "Droite",
  up: "Haut",
};

export function ViewsPage() {
  const { id = "" } = useParams();
  const { project, version, reload } = useProject(id);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<Err>(null);

  const run = async (action: () => Promise<unknown>) => {
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
  const ready = DIRECTIONS.every((d) => project.views[d] !== "pending");

  return (
    <div>
      <ProjectNav project={project} />
      <h1>Vues</h1>

      <div className="toolbar">
        <button disabled={busy} onClick={() => void run(() => api.generateViews(id))}>
          Générer les 4 vues
        </button>
        <label>
          <input
            type="checkbox"
            checked={project.mirror_right}
            onChange={(e) =>
              void run(async () => {
                await api.updateProject(id, { mirror_right: e.target.checked });
                await reload();
              })
            }
          />{" "}
          right = miroir de left
        </label>
      </div>
      <ErrorNote error={error} />

      <div className="grid">
        {DIRECTIONS.map((d) => {
          const status = project.views[d];
          return (
            <figure key={d} className="card tile" data-direction={d}>
              <figcaption>
                {LABEL[d]} <span className={`badge badge-${status}`}>{status}</span>
              </figcaption>
              <div className="thumb">
                {status === "pending" ? (
                  <span className="muted">Pas encore générée</span>
                ) : (
                  <img
                    className="pixelated"
                    alt={`Vue ${d}`}
                    src={imageUrl(`projects/${id}/views/${d}.png`, version)}
                  />
                )}
              </div>
              <div className="row">
                <button disabled={busy} onClick={() => void run(() => api.generateViews(id, d))}>
                  Régénérer
                </button>
                <button
                  disabled={busy || status !== "generated"}
                  onClick={() => void run(async () => {
                    await api.validateView(id, d);
                    await reload();
                  })}
                >
                  Valider
                </button>
              </div>
            </figure>
          );
        })}
      </div>

      {ready ? (
        <Link className="button" to={`/p/${id}/animations`}>
          Passer aux animations
        </Link>
      ) : (
        <button disabled>Passer aux animations</button>
      )}
    </div>
  );
}
