import { expect, test } from "vitest";
import { clampInt, frameNumber, parsePaletteText } from "./review";

test("frameNumber parses the raw file number", () => {
  expect(frameNumber("003.png")).toBe(3);
  expect(frameNumber("000.png")).toBe(0);
  expect(frameNumber("012.png")).toBe(12);
});

test("parsePaletteText reads hex lines with or without #", () => {
  expect(parsePaletteText("#FF0000\n00ff00\n\n  0000FF  \n")).toEqual([
    "#ff0000",
    "#00ff00",
    "#0000ff",
  ]);
});

test("parsePaletteText ignores comments and invalid lines", () => {
  expect(parsePaletteText("; comment\n// other\n# not a color\nzzzzzz\n123456")).toEqual(["#123456"]);
});

test("parsePaletteText reads GIMP palettes", () => {
  const gpl = "GIMP Palette\nName: Test\nColumns: 4\n#\n255   0   0\tRed\n  0 128 255 Sky blue\n300 0 0 bad\n";
  expect(parsePaletteText(gpl)).toEqual(["#ff0000", "#0080ff"]);
});

test("parsePaletteText removes duplicates, keeping order", () => {
  expect(parsePaletteText("ff0000\nFF0000\n00ff00")).toEqual(["#ff0000", "#00ff00"]);
});

test("clampInt clamps to the bounds", () => {
  expect(clampInt("1", 16, 256, 64)).toBe(16);
  expect(clampInt("128", 16, 256, 64)).toBe(128);
  expect(clampInt("999", 16, 256, 64)).toBe(256);
  expect(clampInt(" 12 ", 2, 16, 4)).toBe(12);
});

test("clampInt uses the fallback for non-numbers", () => {
  expect(clampInt("", 2, 16, 4)).toBe(4);
  expect(clampInt("abc", 2, 16, 4)).toBe(4);
  expect(clampInt("1.5", 2, 16, 4)).toBe(4);
  expect(clampInt("", 2, 16, 40)).toBe(16);
});
