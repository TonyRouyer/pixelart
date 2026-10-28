import { useState } from "react";
import { useParams } from "react-router-dom";
import { api } from "../api/client";
import { DIRECTIONS } from "../api/types";
import { ErrorNote, toErrorInfo } from "../components/ErrorNote";
import { ProjectNav } from "../components/ProjectNav";
import { useProject } from "../hooks/useProject";

type Err = { message: string; hint: string | null } | null;

export function ExportPage() {
  const { id = "" } = useParams();
  const { project } = useProject(id);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<Err>(null);
  const [exported, setExported] = useState<string | null>(null);

  if (!project) return <p className="muted">Chargement…</p>;

  // Same rule as the backend: "<animation>_<direction>" is ready when its status is "ready".
  const entries = project.animations.flatMap((a) =>
    DIRECTIONS.map((d) => ({
      name: `${a.id}_${d}`,
      ready: a.directions[d].status === "ready",
    })),
  );
  const missing = entries.filter((e) => !e.ready);

  const doExport = async () => {
    setBusy(true);
    setError(null);
    setExported(null);
    try {
      const { url, key } = await api.exportProject(id);
      const link = document.createElement("a");
      link.href = url;
      link.download = key.split("/").pop() ?? "export.zip";
      document.body.appendChild(link);
      link.click();
      link.remove();
      setExported(link.download);
    } catch (e) {
      // For "export_incomplete" the backend message already lists the missing "<anim>_<dir>".
      setError(toErrorInfo(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div>
      <ProjectNav project={project} />
      <h1>Export</h1>
      <div className="export-lists">
        <section className="card">
          <h2>Prêtes</h2>
          <ul data-testid="ready-list">
            {entries.filter((e) => e.ready).map((e) => (
              <li key={e.name}>{e.name}</li>
            ))}
          </ul>
        </section>
        <section className="card">
          <h2>Manquantes</h2>
          <ul data-testid="missing-list">
            {missing.map((e) => (
              <li key={e.name}>{e.name}</li>
            ))}
          </ul>
          {missing.length === 0 && <p className="muted">Rien ne manque.</p>}
        </section>
      </div>
      <button disabled={busy || project.animations.length === 0} onClick={() => void doExport()}>
        Exporter
      </button>
      {exported && <p className="muted">Téléchargement lancé : {exported}</p>}
      <ErrorNote error={error} />
    </div>
  );
}
