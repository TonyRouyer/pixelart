import { useCallback, useEffect, useState } from "react";
import { api, fileUrl } from "../api/client";
import type { Project, ServerEvent } from "../api/types";
import { useEvents } from "./useEvents";

/** The project after `event`: replaced by the event's project when it is for `id`, else unchanged. */
export function applyProjectEvent(
  current: Project | null,
  id: string,
  event: ServerEvent,
): Project | null {
  if (event.type === "project" && event.project.id === id) return event.project;
  return current;
}

/** URL of a stored image, with a cache-busting `?v=<version>`. */
export function imageUrl(key: string, version: number): string {
  return `${fileUrl(key)}?v=${version}`;
}

interface State {
  project: Project | null;
  version: number;
}

export interface UseProject {
  project: Project | null;
  /** Incremented on each applied project event; use it to bust image caches. */
  version: number;
  reload(): Promise<void>;
}

export function useProject(id: string): UseProject {
  const [state, setState] = useState<State>({ project: null, version: 0 });

  const reload = useCallback(async () => {
    try {
      const project = await api.getProject(id);
      setState((s) => ({ project, version: s.version + 1 }));
    } catch {
      setState((s) => ({ ...s, project: null }));
    }
  }, [id]);

  useEffect(() => {
    setState({ project: null, version: 0 });
    void reload();
  }, [reload]);

  useEvents(
    useCallback(
      (event: ServerEvent) => {
        setState((s) => {
          const project = applyProjectEvent(s.project, id, event);
          return project === s.project ? s : { project, version: s.version + 1 };
        });
      },
      [id],
    ),
  );

  return { project: state.project, version: state.version, reload };
}
