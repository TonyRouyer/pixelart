import { expect, test } from "vitest";
import type { Project, ServerEvent } from "../api/types";
import { applyProjectEvent } from "./useProject";

function project(id: string, name: string): Project {
  return { id, name } as Project;
}

test("useProject applies matching project events only", () => {
  const current = project("a", "old");

  const other: ServerEvent = { type: "project", project: project("b", "other") };
  expect(applyProjectEvent(current, "a", other)).toBe(current);

  const matching: ServerEvent = { type: "project", project: project("a", "new") };
  expect(applyProjectEvent(current, "a", matching)?.name).toBe("new");
  expect(applyProjectEvent(null, "a", matching)?.name).toBe("new");
});

test("useProject ignores job events", () => {
  const current = project("a", "old");
  const job = { type: "job", job: { project_id: "a" } } as ServerEvent;
  expect(applyProjectEvent(current, "a", job)).toBe(current);
});
