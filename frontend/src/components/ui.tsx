import {
  useCallback,
  useEffect,
  useRef,
  useState,
  useSyncExternalStore,
  type ReactNode,
  type RefObject,
} from "react";
import { Icon } from "./icons";

/* ------------------------------------------------------------------ */
/* Types                                                               */
/* ------------------------------------------------------------------ */

export type AgentStep = {
  id: string;
  label: string;
  status: "running" | "done";
};

export type Suggestion = {
  id: string;
  label: string;
  hint?: string;
  text: string;
};

/* ------------------------------------------------------------------ */
/* Class presets                                                       */
/* ------------------------------------------------------------------ */

export const btn = {
  primary: "btn btn-primary press",
  secondary: "btn btn-secondary press",
  ghost: "btn btn-ghost press",
  icon: "btn-icon press",
  chip: "chip-btn press",
};

/* ------------------------------------------------------------------ */
/* Hooks                                                               */
/* ------------------------------------------------------------------ */

const REDUCED_MOTION = "(prefers-reduced-motion: reduce)";

export function useReducedMotion() {
  return useSyncExternalStore(
    (cb) => {
      const m = window.matchMedia(REDUCED_MOTION);
      m.addEventListener("change", cb);
      return () => m.removeEventListener("change", cb);
    },
    () => window.matchMedia(REDUCED_MOTION).matches,
    () => false,
  );
}

export function useDismiss(open: boolean, ref: RefObject<HTMLElement | null>, onClose: () => void) {
  useEffect(() => {
    if (!open) return;
    const onDown = (e: PointerEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) onClose();
    };
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("pointerdown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("pointerdown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open, ref, onClose]);
}

/* ------------------------------------------------------------------ */
/* Sol Logo (Minimal Sun Disc & Rays)                                  */
/* ------------------------------------------------------------------ */

export function Logo({ size = 24, className = "" }: { size?: number; className?: string }) {
  return (
    <span
      className={`relative inline-flex shrink-0 items-center justify-center rounded-full ${className}`}
      style={{
        width: size,
        height: size,
        background: "linear-gradient(135deg, #f59e0b 0%, #ea580c 100%)",
        boxShadow: "0 0 0 1px rgba(234, 88, 12, 0.16)",
      }}
      aria-hidden="true"
    >
      <svg
        width={Math.round(size * 0.58)}
        height={Math.round(size * 0.58)}
        viewBox="0 0 24 24"
        fill="none"
        stroke="#ffffff"
        strokeWidth="2.1"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        <circle cx="12" cy="12" r="4.2" fill="#ffffff" stroke="none" />
        <path d="M12 2.5v2.2M12 19.3v2.2M5.28 5.28l1.55 1.55M17.17 17.17l1.55 1.55M2.5 12h2.2M19.3 12h2.2M5.28 18.72l1.55-1.55M17.17 6.83l1.55-1.55" />
      </svg>
    </span>
  );
}

/* ------------------------------------------------------------------ */
/* Spinners                                                            */
/* ------------------------------------------------------------------ */

export function Spinner({
  variant = "inline",
  size,
  label,
  className = "",
}: {
  variant?: "main" | "inline";
  size?: number;
  label?: string;
  className?: string;
}) {
  const a11y = label ? { role: "status" as const, "aria-label": label } : { "aria-hidden": true as const };
  if (variant === "main") {
    const s = size ?? 32;
    return (
      <span
        {...a11y}
        className={`spinner-main ${className}`}
        style={{ width: s, height: s, ["--w" as string]: `${Math.max(3, Math.round(s / 8))}px` }}
      />
    );
  }
  const s = size ?? 14;
  return <span {...a11y} className={`spinner-inline ${className}`} style={{ width: s, height: s }} />;
}

/* ------------------------------------------------------------------ */
/* Thinking stepper                                                    */
/* ------------------------------------------------------------------ */

export function ThinkingSteps({ steps, done }: { steps: AgentStep[]; done: boolean }) {
  const [expanded, setExpanded] = useState(false);
  const open = !done || expanded;
  const n = steps.length;
  const running = steps.find((s) => s.status === "running");
  const headline = running ? `Working on it — ${running.label.charAt(0).toLowerCase()}${running.label.slice(1)}…` : "Working on it…";

  return (
    <div className="w-full max-w-[560px]">
      <button
        type="button"
        disabled={!done}
        onClick={() => setExpanded((e) => !e)}
        aria-expanded={open}
        className="row-btn press -ml-1.5 flex min-h-9 items-center gap-3 rounded-[10px] px-1.5 text-left disabled:cursor-default"
      >
        <span className="flex h-6 w-6 shrink-0 items-center justify-center text-[var(--brand)]">
          <Swap
            active={done ? 1 : 0}
            items={[
              <Spinner key="s" variant="main" size={24} />,
              <span key="c" className="flex h-6 w-6 items-center justify-center rounded-full bg-[var(--brand-soft)] [&_svg]:size-3.5">
                {Icon.check}
              </span>,
            ]}
          />
        </span>
        <Swap
          active={done ? 1 : 0}
          className="justify-items-start text-[14px] text-[var(--label-2)]"
          items={[
            <span key="w" className="shimmer">
              {headline}
            </span>,
            <span key="d">
              Completed {n} step{n === 1 ? "" : "s"}
            </span>,
          ]}
        />
        <span className={`chev text-[var(--label-3)] ${done ? "opacity-100" : "opacity-0"}`} data-open={expanded} aria-hidden="true">
          {Icon.chevronRight}
        </span>
      </button>

      <div className="disclosure" data-open={open}>
        <div>
          <ol className="ml-[7px] pt-2 pb-1">
            {steps.map((s, i) => {
              const isDone = s.status === "done";
              const last = i === n - 1;
              return (
                <li key={s.id} className="enter relative flex items-center gap-3 pb-4 last:pb-1">
                  {!last && (
                    <span
                      aria-hidden="true"
                      className={`absolute top-11 bottom-0 left-[17px] border-l-2 border-dotted transition-colors duration-300 ${
                        isDone ? "border-[var(--brand)]" : "border-[var(--fill-2)]"
                      }`}
                    />
                  )}
                  <span
                    className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-white text-[13px] font-medium tabular-nums shadow-[0_0_0_1.5px_var(--hairline)] transition-colors duration-300 ${
                      isDone ? "text-[var(--brand)]" : "text-[var(--label-2)]"
                    }`}
                  >
                    {i + 1}
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className={`block truncate text-[14px] font-medium ${isDone ? "" : "shimmer"}`}>{s.label}</span>
                    <span className="block text-[13px] text-[var(--label-3)]">{isDone ? "Done" : "Working…"}</span>
                  </span>
                  <span className="flex h-5 w-5 shrink-0 items-center justify-center text-[var(--label-3)] [&_svg]:size-4">
                    <Swap active={isDone ? 1 : 0} items={[<Spinner key="s" size={16} />, <span key="c" className="text-[var(--brand)]">{Icon.check}</span>]} />
                  </span>
                </li>
              );
            })}
          </ol>
        </div>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Confirmation dialog                                                 */
/* ------------------------------------------------------------------ */

export function ConfirmDialog({
  open,
  title,
  body,
  confirmLabel,
  cancelLabel = "Cancel",
  onConfirm,
  onCancel,
}: {
  open: boolean;
  title: string;
  body: ReactNode;
  confirmLabel: string;
  cancelLabel?: string;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  const panelRef = useRef<HTMLDivElement>(null);
  const cancelRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) return;
    const prev = document.activeElement as HTMLElement | null;
    cancelRef.current?.focus({ preventScroll: true });
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        onCancel();
        return;
      }
      if (e.key !== "Tab" || !panelRef.current) return;
      const items = panelRef.current.querySelectorAll<HTMLElement>("button");
      const first = items[0];
      const last = items[items.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      prev?.focus({ preventScroll: true });
    };
  }, [open, onCancel]);

  return (
    <div className="dialog-root fixed inset-0 z-[80] flex items-center justify-center p-6" data-open={open} inert={!open}>
      <div className="dialog-backdrop absolute inset-0 bg-black/15 backdrop-blur-[2px]" onClick={onCancel} aria-hidden="true" />
      <div
        ref={panelRef}
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="confirm-title"
        aria-describedby="confirm-body"
        className="dialog-panel relative w-full max-w-[320px] rounded-[20px] bg-white/95 px-6 pt-6 pb-4 text-center shadow-[0_0_0_0.5px_rgba(0,0,0,0.08),0_20px_50px_rgba(0,0,0,0.12)] backdrop-blur-xl"
      >
        <h2 id="confirm-title" className="text-[16px] font-semibold tracking-tight">
          {title}
        </h2>
        <p id="confirm-body" className="mt-1.5 text-[13px] leading-snug text-[var(--label-2)]">
          {body}
        </p>
        <div className="mt-5 grid grid-cols-2 gap-2">
          <button
            ref={cancelRef}
            type="button"
            onClick={onCancel}
            className="press h-10 rounded-[12px] bg-[var(--fill)] text-[14px] font-medium hover:bg-[var(--fill-2)]"
          >
            {cancelLabel}
          </button>
          <button type="button" onClick={onConfirm} className="press h-10 rounded-[12px] bg-[var(--fg)] text-[14px] font-medium text-white hover:bg-[#262626]">
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Primitives                                                          */
/* ------------------------------------------------------------------ */

export function Swap({ active, items, className = "" }: { active: number; items: ReactNode[]; className?: string }) {
  return (
    <span className={`swap ${className}`}>
      {items.map((item, i) => (
        <span key={i} data-active={i === active} aria-hidden={i !== active} className="flex items-center justify-center gap-1.5">
          {item}
        </span>
      ))}
    </span>
  );
}

export function Group({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <div className={`card overflow-hidden ${className}`}>{children}</div>;
}

export function Separator({ inset = true }: { inset?: boolean }) {
  return <div aria-hidden="true" className={`${inset ? "ml-4" : ""} h-px bg-[var(--hairline)]`} />;
}

export function Popover({
  trigger,
  children,
  placement = "bottom-end",
  label,
  className = "",
}: {
  trigger: (p: { open: boolean; toggle: () => void }) => ReactNode;
  children: (close: () => void) => ReactNode;
  placement?: "bottom-end" | "bottom-start" | "top-start" | "top-end" | "right-start" | "right-end";
  label: string;
  className?: string;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const close = useCallback(() => setOpen(false), []);
  useDismiss(open, ref, close);

  const pos = {
    "bottom-end": "top-full right-0 mt-2",
    "bottom-start": "top-full left-0 mt-2",
    "top-start": "bottom-full left-0 mb-2",
    "top-end": "bottom-full right-0 mb-2",
    "right-start": "left-full top-0 ml-3",
    "right-end": "left-full bottom-0 ml-3",
  }[placement];

  return (
    <div ref={ref} className="relative">
      {trigger({ open, toggle: () => setOpen((o) => !o) })}
      <div
        role="dialog"
        aria-label={label}
        data-open={open}
        data-placement={placement}
        className={`popover absolute z-50 ${pos} rounded-2xl bg-white p-1.5 shadow-[0_0_0_1px_var(--hairline),0_12px_32px_rgba(0,0,0,0.1)] ${className}`}
      >
        {children(close)}
      </div>
    </div>
  );
}

export function MenuItem({
  children,
  onSelect,
  checked,
  disabled,
}: {
  children: ReactNode;
  onSelect?: () => void;
  checked?: boolean;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      role="menuitemradio"
      aria-checked={checked}
      disabled={disabled}
      onClick={onSelect}
      className="row-btn flex w-full items-center gap-2 rounded-[10px] px-2.5 py-2 text-left text-[14px] disabled:opacity-40"
    >
      <span className="min-w-0 flex-1">{children}</span>
      {checked !== undefined && <span className={`text-[var(--brand)] ${checked ? "opacity-100" : "opacity-0"}`}>{Icon.check}</span>}
    </button>
  );
}
