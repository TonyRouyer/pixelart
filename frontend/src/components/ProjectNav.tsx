import { Link } from "react-router-dom";
import type { Project } from "../api/types";

export function ProjectNav({ project }: { project: Project | null }) {
  return (
    <nav className="project-nav">
      <Link to="/">Projets</Link>
      {project && <strong>{project.name}</strong>}
      {project && (
        <>
          <Link to={`/p/${project.id}/reference`}>Référence</Link>
          <Link to={`/p/${project.id}/views`}>Vues</Link>
        </>
      )}
    </nav>
  );
}
