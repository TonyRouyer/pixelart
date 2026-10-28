import { expect, test } from "vitest";
import { removalPrompt, removedAnimations } from "./animations";

test("removedAnimations lists saved animations that are no longer ticked", () => {
  expect(removedAnimations(["idle", "walk", "attack_bow"], ["walk"])).toEqual(["idle", "attack_bow"]);
  expect(removedAnimations(["idle"], ["idle", "walk"])).toEqual([]);
  expect(removedAnimations([], [])).toEqual([]);
});

test("removalPrompt names the animations to delete", () => {
  expect(removalPrompt(["Marche"])).toBe("Supprimer l'animation Marche et ses frames ?");
  expect(removalPrompt(["Idle", "Marche"])).toBe(
    "Supprimer les animations Idle, Marche et leurs frames ?",
  );
});
