import { type FormEvent, useCallback, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api/client";
import type { Project } from "../api/types";
import { ErrorNote, toErrorInfo } from "../components/ErrorNote";
import { useEvents } from "../hooks/useEvents";
import { imageUrl } from "../hooks/useProject";

const MIN_SIZE = 16;
const MAX_SIZE = 256;

export function ProjectsPage() {
  const navigate = useNavigate();
  const [projects, setProjects] = useState<Project[]>([]);
  const [name, setName] = useState("");
  const [size, setSize] = useState(64);
  const [style, setStyle] = useState("");
  const [error, setError] = useState<{ message: string; hint: string | null } | null>(null);

  const load = useCallback(() => {
    api.listProjects().then(setProjects).catch((e) => setError(toErrorInfo(e)));
  }, []);
  useEffect(load, [load]);

  useEvents(
    useCallback((e) => {
      if (e.type !== "project") return;
      setProjects((list) =>
        list.some((p) => p.id === e.project.id)
          ? list.map((p) => (p.id === e.project.id ? e.project : p))
          : list,
      );
    }, []),
  );

  const sizeValid = Number.isInteger(size) && size >= MIN_SIZE && size <= MAX_SIZE;

  const create = async (ev: FormEvent) => {
    ev.preventDefault();
    setError(null);
    try {
      const p = await api.createProject({
        name: name.trim(),
        output_size: size,
        style_prompt: style.trim() || null,
      });
      navigate(`/p/${p.id}/reference`);
    } catch (e) {
      setError(toErrorInfo(e));
    }
  };

  const remove = async (p: Project) => {
    if (!window.confirm(`Supprimer le projet « ${p.name} » ? Cette action est définitive.`)) return;
    try {
      await api.deleteProject(p.id);
      setProjects((list) => list.filter((x) => x.id !== p.id));
    } catch (e) {
      setError(toErrorInfo(e));
    }
  };

  return (
    <div>
      <h1>Projets</h1>
      <form className="card form" onSubmit={create}>
        <h2>Nouveau projet</h2>
        <label>
          Nom
          <input value={name} onChange={(e) => setName(e.target.value)} required />
        </label>
        <label>
          Taille (px, {MIN_SIZE}–{MAX_SIZE})
          <input
            type="number"
            min={MIN_SIZE}
            max={MAX_SIZE}
            value={size}
            onChange={(e) => setSize(e.target.valueAsNumber)}
          />
        </label>
        <label>
          Style
          <input
            value={style}
            placeholder="ex. pixel art fantasy, 16 couleurs"
            onChange={(e) => setStyle(e.target.value)}
          />
        </label>
        <button type="submit" disabled={!name.trim() || !sizeValid}>
          Créer
        </button>
        <ErrorNote error={error} />
      </form>

      {projects.length === 0 && <p className="muted">Aucun projet pour l'instant.</p>}
      <ul className="project-list">
        {projects.map((p) => (
          <li key={p.id} className="card project-item">
            <div className="thumb">
              {p.reference.status === "validated" ? (
                <img
                  className="pixelated"
                  alt={`Référence de ${p.name}`}
                  src={imageUrl(`projects/${p.id}/reference/reference.png`, 0)}
                />
              ) : (
                <span className="muted">Pas de référence</span>
              )}
            </div>
            <div className="grow">
              <Link to={`/p/${p.id}/reference`}>
                <strong>{p.name}</strong>
              </Link>
              <div className="muted">{p.output_size} px</div>
            </div>
            <button onClick={() => void remove(p)}>Supprimer</button>
          </li>
        ))}
      </ul>
    </div>
  );
}
