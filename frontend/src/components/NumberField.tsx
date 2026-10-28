import { useEffect, useState } from "react";
import { clampInt } from "../lib/review";

interface Props {
  value: number;
  min: number;
  max: number;
  label: string;
  disabled?: boolean;
  /** Called with an in-range value while typing, and with the clamped value on blur. */
  onCommit(value: number): void;
}

/** Integer input that keeps the raw text while typing and only clamps on blur. */
export function NumberField({ value, min, max, label, disabled, onCommit }: Props) {
  const [raw, setRaw] = useState(String(value));

  useEffect(() => {
    setRaw((r) => (r.trim() !== "" && Number(r) === value ? r : String(value)));
  }, [value, min, max]);

  return (
    <input
      type="text"
      inputMode="numeric"
      aria-label={label}
      title={`${min}–${max}`}
      value={raw}
      disabled={disabled}
      onChange={(e) => {
        setRaw(e.target.value);
        const n = Number(e.target.value);
        if (/^\s*\d+\s*$/.test(e.target.value) && n >= min && n <= max) onCommit(n);
      }}
      onBlur={() => {
        const v = clampInt(raw, min, max, value);
        setRaw(String(v));
        onCommit(v);
      }}
    />
  );
}
