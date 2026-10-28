import { useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import type { PixelSettings, Project } from "../api/types";
import { parsePaletteText } from "../lib/review";
import { ErrorNote, toErrorInfo } from "./ErrorNote";

type Err = { message: string; hint: string | null } | null;

const DEBOUNCE_MS = 300;
const MODE_LABEL = { auto: "Auto", preset: "Preset", custom: "Personnalisée" } as const;

export function PixelSettingsPanel({ project }: { project: Project }) {
  const [settings, setSettings] = useState<PixelSettings>(project.pixel_settings);
  const [size, setSize] = useState(project.output_size);
  const [presets, setPresets] = useState<string[]>([]);
  const [error, setError] = useState<Err>(null);
  const [fileNote, setFileNote] = useState<string | null>(null);
  const timers = useRef<{ settings?: ReturnType<typeof setTimeout>; size?: ReturnType<typeof setTimeout> }>({});
  const pid = project.id;

  useEffect(() => {
    api.palettePresets().then((p) => setPresets(Object.keys(p)), () => setPresets([]));
    const t = timers.current;
    return () => {
      clearTimeout(t.settings);
      clearTimeout(t.size);
    };
  }, []);

  const send = (key: "settings" | "size", patch: Parameters<typeof api.updateProject>[1]) => {
    clearTimeout(timers.current[key]);
    timers.current[key] = setTimeout(() => {
      api.updateProject(pid, patch).then(
        () => setError(null),
        (e) => setError(toErrorInfo(e)),
      );
    }, DEBOUNCE_MS);
  };

  const change = (next: PixelSettings) => {
    setSettings(next);
    const { mode, preset, custom_colors } = next.palette;
    const incomplete =
      (mode === "preset" && !preset) || (mode === "custom" && (custom_colors?.length ?? 0) < 2);
    // Wait for a preset / an imported palette before sending an invalid combination.
    if (incomplete) clearTimeout(timers.current.settings);
    else send("settings", { pixel_settings: next });
  };
  const palette = settings.palette;
  const setPalette = (p: Partial<PixelSettings["palette"]>) =>
    change({ ...settings, palette: { ...palette, ...p } });

  const importFile = async (file: File) => {
    const colors = parsePaletteText(await file.text());
    if (colors.length < 2) {
      setFileNote("Aucune couleur valide trouvée dans ce fichier.");
      return;
    }
    const used = colors.slice(0, 64);
    setFileNote(`${used.length} couleurs importées.`);
    setPalette({ mode: "custom", custom_colors: used, colors: used.length });
  };

  return (
    <section className="card pixel-settings" aria-label="Réglages pixel art">
      <h2>Pixel art</h2>
      <div className="form">
        <label>
          Mode de palette
          <select
            value={palette.mode}
            onChange={(e) => {
              const mode = e.target.value as PixelSettings["palette"]["mode"];
              setPalette({ mode, preset: mode === "preset" ? (palette.preset ?? presets[0] ?? null) : palette.preset });
            }}
          >
            {Object.entries(MODE_LABEL).map(([v, l]) => (
              <option key={v} value={v}>
                {l}
              </option>
            ))}
          </select>
        </label>
        {palette.mode === "auto" && (
          <label>
            Nombre de couleurs (2–64)
            <input
              type="number"
              min={2}
              max={64}
              value={palette.colors}
              onChange={(e) =>
                setPalette({ colors: Math.min(64, Math.max(2, e.target.valueAsNumber || 2)) })
              }
            />
          </label>
        )}
        {palette.mode === "preset" && (
          <label>
            Preset
            <select
              value={palette.preset ?? ""}
              onChange={(e) => setPalette({ preset: e.target.value || null })}
            >
              <option value="">—</option>
              {presets.map((p) => (
                <option key={p} value={p}>
                  {p}
                </option>
              ))}
            </select>
          </label>
        )}
        {palette.mode === "custom" && (
          <label>
            Importer .hex / .gpl
            <input
              type="file"
              accept=".hex,.gpl,.txt"
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) void importFile(f);
                e.target.value = "";
              }}
            />
            <span className="muted">
              {fileNote ?? `${palette.custom_colors?.length ?? 0} couleurs`}
            </span>
          </label>
        )}
        <label>
          <input
            type="checkbox"
            checked={settings.outline.enabled}
            onChange={(e) =>
              change({ ...settings, outline: { ...settings.outline, enabled: e.target.checked } })
            }
          />{" "}
          Contour
        </label>
        <label>
          Couleur du contour
          <input
            type="color"
            value={settings.outline.color}
            disabled={!settings.outline.enabled}
            onChange={(e) =>
              change({ ...settings, outline: { ...settings.outline, color: e.target.value } })
            }
          />
        </label>
        <label>
          Seuil alpha ({settings.alpha_threshold})
          <input
            type="range"
            min={0}
            max={255}
            value={settings.alpha_threshold}
            onChange={(e) => change({ ...settings, alpha_threshold: e.target.valueAsNumber })}
          />
        </label>
        <label>
          Taille de sortie (16–256 px)
          <input
            type="number"
            min={16}
            max={256}
            value={size}
            onChange={(e) => {
              const v = Math.min(256, Math.max(16, e.target.valueAsNumber || 16));
              setSize(v);
              send("size", { output_size: v });
            }}
          />
        </label>
      </div>
      <ErrorNote error={error} />
    </section>
  );
}
