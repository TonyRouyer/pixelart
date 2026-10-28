import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api/client";
import type { AnimationConfigIn, AnimationType } from "../api/types";
import { ErrorNote, toErrorInfo } from "../components/ErrorNote";
import { ProjectNav } from "../components/ProjectNav";
import { useProject } from "../hooks/useProject";

type Err = { message: string; hint: string | null } | null;

export const ANIMATION_LABEL: Record<AnimationType, string> = {
  idle: "Idle",
  walk: "Marche",
  attack_unarmed: "Attaque mains nues",
  attack_sword: "Attaque épée",
  attack_spear: "Attaque lance",
  attack_bow: "Attaque arc",
};

const TYPES = Object.keys(ANIMATION_LABEL) as AnimationType[];

const DEFAULTS: Record<AnimationType, { frames: number; fps: number }> = {
  idle: { frames: 4, fps: 6 },
  walk: { frames: 6, fps: 10 },
  attack_unarmed: { frames: 6, fps: 12 },
  attack_sword: { frames: 6, fps: 12 },
  attack_spear: { frames: 6, fps: 12 },
  attack_bow: { frames: 6, fps: 12 },
};

interface Row {
  enabled: boolean;
  frames: number;
  fps: number;
}

const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, Math.round(v) || lo));

function defaultRows(): Record<AnimationType, Row> {
  return Object.fromEntries(
    TYPES.map((t) => [t, { enabled: false, frames: DEFAULTS[t].frames, fps: DEFAULTS[t].fps }]),
  ) as Record<AnimationType, Row>;
}

export function AnimationsPage() {
  const { id = "" } = useParams();
  const { project, reload } = useProject(id);
  const [rows, setRows] = useState<Record<AnimationType, Row>>(defaultRows);
  const [loaded, setLoaded] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<Err>(null);
  const [notice, setNotice] = useState<string | null>(null);

  // Initialise the form once from the saved configuration.
  useEffect(() => {
    if (!project || loaded) return;
    const next = defaultRows();
    for (const a of project.animations) {
      next[a.type] = { enabled: true, frames: a.frame_count, fps: a.fps };
    }
    setRows(next);
    setLoaded(true);
  }, [project, loaded]);

  const run = async (action: () => Promise<unknown>, done?: string) => {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await action();
      if (done) setNotice(done);
    } catch (e) {
      setError(toErrorInfo(e));
    } finally {
      setBusy(false);
    }
  };

  if (!project) return <p className="muted">Chargement…</p>;

  const patch = (t: AnimationType, p: Partial<Row>) =>
    setRows((r) => ({ ...r, [t]: { ...r[t], ...p } }));
  const configs = (): AnimationConfigIn[] =>
    TYPES.filter((t) => rows[t].enabled).map((t) => ({
      type: t,
      frame_count: rows[t].frames,
      fps: rows[t].fps,
    }));
  const saved = new Set(project.animations.map((a) => a.type));

  const save = async () => {
    await api.configureAnimations(id, configs());
    await reload();
  };

  return (
    <div>
      <ProjectNav project={project} />
      <h1>Animations</h1>

      <table className="anim-table">
        <thead>
          <tr>
            <th>Animation</th>
            <th>Frames (2–16)</th>
            <th>FPS (1–60)</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {TYPES.map((t) => (
            <tr key={t} data-type={t}>
              <td>
                <label>
                  <input
                    type="checkbox"
                    checked={rows[t].enabled}
                    onChange={(e) => patch(t, { enabled: e.target.checked })}
                  />{" "}
                  {ANIMATION_LABEL[t]}
                </label>
              </td>
              <td>
                <input
                  type="number"
                  aria-label={`Frames ${ANIMATION_LABEL[t]}`}
                  min={2}
                  max={16}
                  value={rows[t].frames}
                  disabled={!rows[t].enabled}
                  onChange={(e) => patch(t, { frames: clamp(e.target.valueAsNumber, 2, 16) })}
                />
              </td>
              <td>
                <input
                  type="number"
                  aria-label={`FPS ${ANIMATION_LABEL[t]}`}
                  min={1}
                  max={60}
                  value={rows[t].fps}
                  disabled={!rows[t].enabled}
                  onChange={(e) => patch(t, { fps: clamp(e.target.valueAsNumber, 1, 60) })}
                />
              </td>
              <td>
                <button
                  disabled={busy || !saved.has(t)}
                  title={saved.has(t) ? undefined : "Enregistrez d'abord"}
                  onClick={() => void run(() => api.generateAnimation(id, t))}
                >
                  Générer
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <div className="toolbar">
        <button disabled={busy} onClick={() => void run(save, "Configuration enregistrée.")}>
          Enregistrer
        </button>
        <button
          disabled={busy || project.animations.length === 0}
          onClick={() =>
            void run(async () => {
              for (const a of project.animations) await api.generateAnimation(id, a.type);
            })
          }
        >
          Tout générer
        </button>
        <Link className="button" to={`/p/${id}/review`}>
          Revue
        </Link>
      </div>
      {notice && <p className="muted">{notice}</p>}
      <ErrorNote error={error} />
    </div>
  );
}
