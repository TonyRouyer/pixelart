import { expect, test } from "vitest";
import { frameAt, removeAt, reorder } from "./playback";

test("frameAt loops", () => {
  expect(frameAt(1000, 6, 4, true)).toBe(2);
  expect(frameAt(0, 6, 4, true)).toBe(0);
});
test("frameAt clamps when not looping", () => {
  expect(frameAt(5000, 12, 6, false)).toBe(5);
});
test("frameAt handles an empty list", () => {
  expect(frameAt(1000, 6, 0, true)).toBe(0);
});
test("reorder moves", () => {
  expect(reorder(["a", "b", "c"], 0, 2)).toEqual(["b", "c", "a"]);
  expect(reorder(["a", "b", "c"], 2, 0)).toEqual(["c", "a", "b"]);
});
test("reorder ignores out-of-range indexes", () => {
  expect(reorder(["a", "b"], 0, 5)).toEqual(["a", "b"]);
});
test("removeAt removes one frame", () => {
  expect(removeAt(["a", "b", "c"], 1)).toEqual(["a", "c"]);
});
test("removeAt keeps last frame", () => {
  expect(removeAt(["a"], 0)).toEqual(["a"]);
});
