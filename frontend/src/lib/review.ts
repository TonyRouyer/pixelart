/** Raw file number of a frame name ("003.png" -> 3); this is what the frame routes expect. */
export function frameNumber(name: string): number {
  return Number.parseInt(name, 10);
}

const HEX = /^#?([0-9a-f]{6})$/i;
const GPL_LINE = /^(\d{1,3})\s+(\d{1,3})\s+(\d{1,3})(?:\s.*)?$/;

function toHex(n: number): string {
  return n.toString(16).padStart(2, "0");
}

/** Colors ("#rrggbb", lowercase, unique) of a `.hex` (one hex per line) or GIMP `.gpl` palette. */
export function parsePaletteText(text: string): string[] {
  const colors: string[] = [];
  for (const raw of text.split(/\r?\n/)) {
    const line = raw.trim();
    let color: string | null = null;
    const hex = HEX.exec(line);
    if (hex) {
      color = `#${hex[1].toLowerCase()}`;
    } else {
      const gpl = GPL_LINE.exec(line);
      if (gpl) {
        const rgb = [gpl[1], gpl[2], gpl[3]].map(Number);
        if (rgb.every((v) => v <= 255)) color = `#${rgb.map(toHex).join("")}`;
      }
    }
    if (color && !colors.includes(color)) colors.push(color);
  }
  return colors;
}
