import type { ReactNode } from "react";
import { Icon } from "./icons";
import { MenuItem, Popover } from "./ui";

/* Custom menus used by the roof map and the sketch canvas (instead of the browser's native <select>). */

/* ---- Site type (the shape of the surface the panels go on) ---- */

export const ROOF_TYPES = [
  { id: "flat", label: "Flat surface", hint: "No slope" },
  { id: "single_slope", label: "Single slope", hint: "One tilted side" },
  { id: "gable", label: "Gable", hint: "Two sloping sides" },
] as const;
export type RoofType = (typeof ROOF_TYPES)[number]["id"];

/** Tiny side-view drawing of each surface shape. */
export function RoofGlyph({ type }: { type: RoofType }) {
  const roof = type === "flat" ? "M3 9h18" : type === "single_slope" ? "M3 12l18-5" : "M3 11l9-6 9 6";
  const walls = type === "flat" ? "M5.5 9v9M18.5 9v9" : type === "single_slope" ? "M5.5 11.3V18M18.5 7.7V18" : "M5.5 10v8M18.5 10v8";
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" className="shrink-0">
      <path d={roof} />
      <path d={walls} opacity="0.5" />
    </svg>
  );
}

export function RoofTypePicker({
  value,
  onChange,
  className = "min-w-0 flex-[1.4]",
}: {
  value: RoofType;
  onChange: (v: RoofType) => void;
  /** Wrapper classes. The default suits the roof map's footer row; the sketch cards pass "w-full". */
  className?: string;
}) {
  const current = ROOF_TYPES.find((t) => t.id === value) ?? ROOF_TYPES[0];
  return (
    <div className={className}>
      <Popover
        label="Site type"
        placement="top-start"
        className="w-[230px] max-w-[calc(100vw-40px)]"
        trigger={({ open, toggle }) => (
          <button
            type="button"
            onClick={toggle}
            aria-haspopup="menu"
            aria-expanded={open}
            aria-label={`Site type: ${current.label}`}
            className={`flex h-10 w-full items-center justify-between gap-2 rounded-[10px] bg-white px-3 text-left text-[13px] text-[#111111] transition-colors hover:bg-[#fafaf9] ${
              open ? "shadow-[0_0_0_2px_#ea580c]" : "shadow-[0_0_0_1px_#d4d4d2]"
            }`}
          >
            <span className="flex min-w-0 items-center gap-2">
              <span className="text-[#ea580c]">
                <RoofGlyph type={current.id} />
              </span>
              <span className="truncate font-medium">{current.label}</span>
            </span>
            <span className={`shrink-0 text-[#787774] transition-transform ${open ? "rotate-180" : ""}`}>{Icon.chevronDown}</span>
          </button>
        )}
      >
        {(close) => (
          <div role="menu" aria-label="Site type">
            {ROOF_TYPES.map((t) => (
              <MenuItem
                key={t.id}
                checked={t.id === value}
                onSelect={() => {
                  onChange(t.id);
                  close();
                }}
              >
                <span className="flex items-center gap-2.5">
                  <span className="text-[#787774]">
                    <RoofGlyph type={t.id} />
                  </span>
                  <span className="min-w-0">
                    <span className="block text-[13px] font-medium text-[#111111]">{t.label}</span>
                    <span className="block text-[11px] text-[#787774]">{t.hint}</span>
                  </span>
                </span>
              </MenuItem>
            ))}
          </div>
        )}
      </Popover>
    </div>
  );
}

/* ---- Generic option menu (same look as the roof type menu) ---- */

export type PickerOption<T extends string | number> = { id: T; label: string; hint?: string; glyph?: ReactNode };

export function OptionPicker<T extends string | number>({
  value,
  options,
  onChange,
  label,
  placement = "top-start",
  disabled = false,
  className = "w-full",
}: {
  value: T;
  options: PickerOption<T>[];
  onChange: (v: T) => void;
  label: string;
  placement?: "top-start" | "bottom-start";
  disabled?: boolean;
  className?: string;
}) {
  const current = options.find((o) => o.id === value) ?? options[0];
  return (
    <div className={`min-w-0 ${className}`}>
      <Popover
        label={label}
        placement={placement}
        className="w-[230px] max-w-[calc(100vw-40px)]"
        trigger={({ open, toggle }) => (
          <button
            type="button"
            onClick={toggle}
            disabled={disabled}
            aria-haspopup="menu"
            aria-expanded={open}
            aria-label={`${label}: ${current?.label ?? "none"}`}
            className={`flex h-10 w-full items-center justify-between gap-2 rounded-[10px] bg-white px-3 text-left text-[13px] text-[#111111] transition-colors hover:bg-[#fafaf9] disabled:opacity-50 disabled:hover:bg-white ${
              open ? "shadow-[0_0_0_2px_#ea580c]" : "shadow-[0_0_0_1px_#d4d4d2]"
            }`}
          >
            <span className="flex min-w-0 items-center gap-2">
              {current?.glyph && <span className="text-[#ea580c]">{current.glyph}</span>}
              <span className="truncate font-medium">{current?.label ?? "—"}</span>
            </span>
            <span className={`shrink-0 text-[#787774] transition-transform ${open ? "rotate-180" : ""}`}>{Icon.chevronDown}</span>
          </button>
        )}
      >
        {(close) => (
          <div role="menu" aria-label={label} className="max-h-[260px] overflow-y-auto">
            {options.map((o) => (
              <MenuItem
                key={String(o.id)}
                checked={o.id === value}
                onSelect={() => {
                  onChange(o.id);
                  close();
                }}
              >
                <span className="flex items-center gap-2.5">
                  {o.glyph && <span className="text-[#787774]">{o.glyph}</span>}
                  <span className="min-w-0">
                    <span className="block text-[13px] font-medium text-[#111111]">{o.label}</span>
                    {o.hint && <span className="block text-[11px] text-[#787774]">{o.hint}</span>}
                  </span>
                </span>
              </MenuItem>
            ))}
          </div>
        )}
      </Popover>
    </div>
  );
}
