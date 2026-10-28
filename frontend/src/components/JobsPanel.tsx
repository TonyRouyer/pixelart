import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import type { Job, JobStatus, ServerEvent } from "../api/types";
import { useEvents } from "../hooks/useEvents";

const STATUS_LABEL: Record<JobStatus, string> = {
  queued: "En attente",
  running: "En cours",
  succeeded: "Terminé",
  failed: "Échec",
  cancelled: "Annulé",
};

const MAX_SHOWN = 20;

function isActive(job: Job): boolean {
  return job.status === "queued" || job.status === "running";
}

export function JobsPanel() {
  const [jobs, setJobs] = useState<Record<string, Job>>({});
  const [open, setOpen] = useState(true);

  const load = useCallback(() => {
    api
      .listJobs()
      .then((list) => setJobs(Object.fromEntries(list.map((j) => [j.id, j]))))
      .catch(() => {});
  }, []);

  useEffect(load, [load]);

  const onEvent = useCallback((e: ServerEvent) => {
    if (e.type === "job") setJobs((prev) => ({ ...prev, [e.job.id]: e.job }));
  }, []);
  useEvents(onEvent);

  const list = Object.values(jobs)
    .sort((a, b) => b.created_at.localeCompare(a.created_at))
    .slice(0, MAX_SHOWN);
  const activeCount = list.filter(isActive).length;

  return (
    <aside className="jobs-panel">
      <button className="jobs-toggle" onClick={() => setOpen(!open)}>
        Tâches ({activeCount} active{activeCount > 1 ? "s" : ""})
      </button>
      {open && (
        <ul className="jobs-list">
          {list.length === 0 && <li className="muted">Aucune tâche.</li>}
          {list.map((job) => (
            <li key={job.id} className={`job job-${job.status}`}>
              <div className="job-head">
                <span className="job-kind">{job.kind}</span>
                <span className="job-target muted">{job.target}</span>
                <span className="job-status">{STATUS_LABEL[job.status]}</span>
                {isActive(job) && (
                  <button onClick={() => api.cancelJob(job.id).catch(() => {})}>Annuler</button>
                )}
              </div>
              {job.status === "running" && (
                <progress value={job.progress} max={1} aria-label="Progression" />
              )}
              {job.status === "failed" && job.error && (
                <div className="job-error">
                  {job.error.message}
                  {job.error.hint && <div className="muted">{job.error.hint}</div>}
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </aside>
  );
}
