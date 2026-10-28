import { type DragEvent, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api/client";
import { ErrorNote, toErrorInfo } from "../components/ErrorNote";
import { ProjectNav } from "../components/ProjectNav";
import { imageUrl, useProject } from "../hooks/useProject";

type Tab = "import" | "describe";
type Err = { message: string; hint: string | null } | null;

export function ReferencePage() {
  const { id = "" } = useParams();
  const { project, version, reload } = useProject(id);
  const [tab, setTab] = useState<Tab>("import");
  const [prompt, setPrompt] = useState("");
  const [count, setCount] = useState(4);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<Err>(null);
  const [dragging, setDragging] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);

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

  const upload = (file: File | undefined) => {
    if (!file) return;
    void run(() => api.uploadReference(id, file));
  };

  const onDrop = (ev: DragEvent) => {
    ev.preventDefault();
    setDragging(false);
    upload(ev.dataTransfer.files[0]);
  };

  if (!project) return <p className="muted">Chargement…</p>;
  const { candidates, status } = project.reference;
  const countValid = Number.isInteger(count) && count >= 1 && count <= 4;

  return (
    <div>
      <ProjectNav project={project} />
      <h1>Référence</h1>

      <div className="tabs" role="tablist">
        <button role="tab" aria-selected={tab === "import"} onClick={() => setTab("import")}>
          Importer
        </button>
        <button role="tab" aria-selected={tab === "describe"} onClick={() => setTab("describe")}>
          Décrire
        </button>
      </div>

      {tab === "import" ? (
        <div
          className={`dropzone${dragging ? " dragging" : ""}`}
          onDragOver={(e) => {
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={onDrop}
          onClick={() => fileInput.current?.click()}
        >
          Déposez une image PNG ou JPG ici, ou cliquez pour choisir.
          <input
            ref={fileInput}
            type="file"
            accept="image/png,image/jpeg"
            hidden
            data-testid="reference-file"
            onChange={(e) => {
              upload(e.target.files?.[0]);
              e.target.value = "";
            }}
          />
        </div>
      ) : (
        <div className="card form">
          <label>
            Description du personnage
            <textarea
              rows={3}
              value={prompt}
              placeholder="ex. un chevalier en armure bleue"
              onChange={(e) => setPrompt(e.target.value)}
            />
          </label>
          <label>
            Nombre de propositions (1–4)
            <input
              type="number"
              min={1}
              max={4}
              value={count}
              onChange={(e) => setCount(e.target.valueAsNumber)}
            />
          </label>
          <button
            disabled={busy || !prompt.trim() || !countValid}
            onClick={() => void run(() => api.generateReference(id, prompt.trim(), count))}
          >
            Générer
          </button>
        </div>
      )}
      <ErrorNote error={error} />

      {candidates.length > 0 && (
        <>
          <h2>Propositions</h2>
          <div className="grid">
            {candidates.map((key, i) => (
              <figure key={key} className="card tile">
                <img
                  className="pixelated"
                  alt={`Proposition ${i + 1}`}
                  src={imageUrl(`projects/${id}/reference/candidates/${i}.png`, version)}
                />
                <button
                  disabled={busy}
                  onClick={() => void run(async () => {
                    await api.selectReference(id, i);
                    await reload();
                  })}
                >
                  Utiliser celle-ci
                </button>
              </figure>
            ))}
          </div>
        </>
      )}

      {status === "validated" && (
        <div className="card validated">
          <h2>Référence validée</h2>
          <img
            className="pixelated"
            alt="Référence validée"
            src={imageUrl(`projects/${id}/reference/reference.png`, version)}
          />
          <div>
            <Link to={`/p/${id}/views`}>Passer aux vues</Link>
          </div>
        </div>
      )}
    </div>
  );
}
