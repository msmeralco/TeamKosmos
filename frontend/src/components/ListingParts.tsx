import { useEffect, useId, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import { AnimatePresence, m, useDragControls, type PanInfo, type Variants } from "framer-motion";
import { Icon } from "./icons";

/* Shared pieces for the installers and packages panels: large-title header with an info popover,
   segmented control, sort menu, grouped-list styles and the bottom detail sheet.
   Motion uses only transform and opacity, with the app's named curves. */

export const EASE_ENTER = [0.22, 1, 0.36, 1] as const;
export const EASE_DRAWER = [0.32, 0.72, 0, 1] as const;

/** A row fades in and rises 8px; only the first few are staggered. */
export const rowVariants: Variants = {
  hidden: { opacity: 0, y: 8 },
  show: (i: number) => ({ opacity: 1, y: 0, transition: { duration: 0.35, ease: EASE_ENTER, delay: Math.min(i, 5) * 0.04 } }),
  exit: { opacity: 0, transition: { duration: 0.15 } },
};

/** Grouped list: one white rounded block with hairline separators (separators, not spacing). */
export const GROUP_CLS = "relative divide-y divide-black/[0.06] overflow-hidden rounded-[14px] bg-white ring-1 ring-black/[0.06]";
export const ROW_BTN_CLS =
  "flex w-full items-center gap-3 px-3.5 py-3 text-left transition-colors hover:bg-[#fafaf9] active:bg-[#f4f4f2] focus-visible:outline-offset-[-2px]";
export const PRIMARY_BTN_CLS =
  "press flex h-11 w-full items-center justify-center gap-1.5 rounded-[10px] bg-[#111111] px-4 text-[14px] font-medium text-white transition-colors hover:bg-[#333333]";
export const SECONDARY_BTN_CLS =
  "press flex h-11 w-full items-center justify-center gap-1.5 rounded-[10px] bg-black/[0.05] px-4 text-[14px] font-medium text-[#111111] transition-colors hover:bg-black/[0.08]";
export const SECTION_LABEL_CLS = "text-[12px] font-medium uppercase tracking-[0.05em] text-[#787774]";

/* ---------------------------------- popover ---------------------------------- */

function usePopover() {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const down = (e: PointerEvent) => {
      if (!ref.current?.contains(e.target as Node)) setOpen(false);
    };
    const key = (e: globalThis.KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("pointerdown", down);
    document.addEventListener("keydown", key);
    return () => {
      document.removeEventListener("pointerdown", down);
      document.removeEventListener("keydown", key);
    };
  }, [open]);
  return { open, setOpen, ref };
}

function Pop({ open, children, className = "" }: { open: boolean; children: ReactNode; className?: string }) {
  return (
    <AnimatePresence>
      {open && (
        <m.div
          initial={{ opacity: 0, scale: 0.98, y: -4 }}
          animate={{ opacity: 1, scale: 1, y: 0, transition: { duration: 0.2, ease: EASE_ENTER } }}
          exit={{ opacity: 0, transition: { duration: 0.12 } }}
          className={`absolute top-full z-30 mt-2 rounded-[12px] bg-white shadow-[0_8px_30px_rgba(0,0,0,0.08)] ring-1 ring-black/[0.06] ${className}`}
        >
          {children}
        </m.div>
      )}
    </AnimatePresence>
  );
}

/* ---------------------------------- header ---------------------------------- */

const ICON_BTN_CLS =
  "press flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-black/[0.05] text-[#6b6b66] transition-colors hover:bg-black/[0.08] hover:text-[#111111]";

export function PanelHeader({ title, subtitle, info, onClose }: { title: string; subtitle: string; info?: ReactNode; onClose: () => void }) {
  const pop = usePopover();
  return (
    <header className="relative z-20 flex shrink-0 items-start gap-2 px-5 pb-3 pt-5">
      <div className="min-w-0 flex-1">
        <h2 className="text-[22px] font-semibold leading-tight tracking-[-0.02em] text-[#111111]">{title}</h2>
        <p className="mt-1 text-[13px] leading-snug text-[#787774]">{subtitle}</p>
      </div>
      {info && (
        <div ref={pop.ref} className="relative">
          <button
            type="button"
            onClick={() => pop.setOpen((v) => !v)}
            aria-label="About these prices and sources"
            aria-expanded={pop.open}
            title="About these prices and sources"
            className={ICON_BTN_CLS}
          >
            {Icon.help}
          </button>
          <Pop open={pop.open} className="right-0 w-[min(320px,calc(100vw-3rem))] p-4">
            <div role="dialog" aria-label="About this list" className="text-[12px] leading-relaxed text-[#52514e]">
              {info}
            </div>
          </Pop>
        </div>
      )}
      <button type="button" onClick={onClose} aria-label="Close panel" title="Close panel" className={ICON_BTN_CLS}>
        {Icon.close}
      </button>
    </header>
  );
}

/* ---------------------------------- segmented control and sort menu ---------------------------------- */

export function Segmented<T extends string>({
  value,
  options,
  onChange,
  label,
}: {
  value: T;
  options: { value: T; label: string }[];
  onChange: (v: T) => void;
  label: string;
}) {
  const id = useId();
  return (
    <div role="group" aria-label={label} className="inline-flex rounded-[10px] bg-black/[0.05] p-0.5">
      {options.map((o) => {
        const on = o.value === value;
        return (
          <button
            key={o.value}
            type="button"
            onClick={() => onChange(o.value)}
            aria-pressed={on}
            className="relative rounded-[8px] px-3 py-1.5 text-[12px] font-medium"
          >
            {on && (
              <m.span
                layoutId={id}
                className="absolute inset-0 rounded-[8px] bg-white shadow-[0_1px_2px_rgba(0,0,0,0.06)]"
                transition={{ type: "spring", stiffness: 520, damping: 42 }}
              />
            )}
            <span className={`relative transition-colors ${on ? "text-[#111111]" : "text-[#6b6b66]"}`}>{o.label}</span>
          </button>
        );
      })}
    </div>
  );
}

export function SortMenu<T extends string>({ value, options, onChange }: { value: T; options: { value: T; label: string }[]; onChange: (v: T) => void }) {
  const pop = usePopover();
  const current = options.find((o) => o.value === value)?.label ?? "";
  return (
    <div ref={pop.ref} className="relative ml-auto">
      <button
        type="button"
        onClick={() => pop.setOpen((v) => !v)}
        aria-haspopup="menu"
        aria-expanded={pop.open}
        className="press flex items-center gap-1.5 rounded-[8px] px-2 py-1.5 text-[12px] font-medium text-[#6b6b66] transition-colors hover:bg-black/[0.05] hover:text-[#111111]"
      >
        <span>Sort: {current}</span>
        {Icon.chevronDown}
      </button>
      <Pop open={pop.open} className="right-0 w-[200px] p-1">
        <div role="menu" aria-label="Sort by">
          {options.map((o) => (
            <button
              key={o.value}
              type="button"
              role="menuitemradio"
              aria-checked={o.value === value}
              onClick={() => {
                onChange(o.value);
                pop.setOpen(false);
              }}
              className="flex w-full items-center justify-between gap-3 rounded-[8px] px-3 py-2 text-left text-[13px] text-[#111111] transition-colors hover:bg-black/[0.05]"
            >
              {o.label}
              <span className={`text-[#ea580c] ${o.value === value ? "" : "invisible"}`}>{Icon.check}</span>
            </button>
          ))}
        </div>
      </Pop>
    </div>
  );
}

/* ---------------------------------- photo ---------------------------------- */

export function Photo({ src, alt, className = "" }: { src?: string | null; alt: string; className?: string }) {
  const [broken, setBroken] = useState(false);
  return (
    <div className={`relative shrink-0 overflow-hidden bg-[#f1f1ef] ${className}`}>
      {src && !broken ? (
        <img src={src} alt={alt} loading="lazy" referrerPolicy="no-referrer" onError={() => setBroken(true)} className="h-full w-full object-cover" />
      ) : (
        <div className="flex h-full w-full items-center justify-center text-[#a3a3a3]">{Icon.panel}</div>
      )}
    </div>
  );
}

/* ---------------------------------- label and value rows ---------------------------------- */

export function Fact({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-4 px-4 py-3 text-[13px] leading-snug">
      <dt className="shrink-0 text-[#787774]">{label}</dt>
      <dd className="min-w-0 text-right text-[#111111]">{children}</dd>
    </div>
  );
}

/* ---------------------------------- bottom sheet ---------------------------------- */

const FOCUSABLE = 'a[href], button:not([disabled]), [tabindex]:not([tabindex="-1"])';

function SheetBody({ onClose, label, children, footer }: { onClose: () => void; label: string; children: ReactNode; footer?: ReactNode }) {
  const ref = useRef<HTMLDivElement>(null);
  const controls = useDragControls();

  // Move focus into the sheet, and give it back to the row that opened it.
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    // preventScroll: the sheet starts below the panel's edge, and a plain focus() would scroll the clipped panel up to reveal it.
    ref.current?.focus({ preventScroll: true });
    return () => previous?.focus?.({ preventScroll: true });
  }, []);

  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    if (e.key === "Escape") {
      e.stopPropagation();
      onClose();
      return;
    }
    if (e.key !== "Tab") return;
    const items = ref.current?.querySelectorAll<HTMLElement>(FOCUSABLE);
    if (!items || items.length === 0) return;
    const first = items[0];
    const last = items[items.length - 1];
    const active = document.activeElement;
    if (e.shiftKey && (active === first || active === ref.current)) {
      e.preventDefault();
      last.focus({ preventScroll: true });
    } else if (!e.shiftKey && active === last) {
      e.preventDefault();
      first.focus({ preventScroll: true });
    }
  };

  const onDragEnd = (_: unknown, info: PanInfo) => {
    if (info.offset.y > 100 || info.velocity.y > 500) onClose();
  };

  return (
    <div className="absolute inset-0 z-40 flex items-end">
      <m.div
        aria-hidden="true"
        onClick={onClose}
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        transition={{ duration: 0.25, ease: EASE_ENTER }}
        className="absolute inset-0 bg-black/25"
      />
      <m.div
        ref={ref}
        role="dialog"
        aria-modal="true"
        aria-label={label}
        tabIndex={-1}
        onKeyDown={onKeyDown}
        drag="y"
        dragControls={controls}
        dragListener={false}
        dragConstraints={{ top: 0, bottom: 0 }}
        dragElastic={{ top: 0, bottom: 0.6 }}
        onDragEnd={onDragEnd}
        initial={{ y: "100%", opacity: 0.6 }}
        animate={{ y: 0, opacity: 1 }}
        exit={{ y: "100%", opacity: 0.6 }}
        transition={{ duration: 0.38, ease: EASE_DRAWER }}
        className="relative flex max-h-[92%] w-full flex-col rounded-t-[22px] bg-[#f7f6f3] shadow-[0_-8px_30px_rgba(0,0,0,0.05)] outline-none"
      >
        <div onPointerDown={(e) => controls.start(e)} className="flex shrink-0 cursor-grab touch-none justify-center pb-2 pt-2.5">
          <span className="h-1 w-9 rounded-full bg-black/15" />
        </div>
        <button type="button" onClick={onClose} aria-label="Close details" title="Close details" className={`${ICON_BTN_CLS} absolute right-3 top-3 z-10`}>
          {Icon.close}
        </button>
        <div className="min-h-0 flex-1 overflow-y-auto px-5 pb-5 pt-1">{children}</div>
        {footer && <div className="flex shrink-0 flex-col gap-2 border-t border-black/[0.06] bg-[#f7f6f3] px-5 py-3">{footer}</div>}
      </m.div>
    </div>
  );
}

export function Sheet({ open, onClose, label, children, footer }: { open: boolean; onClose: () => void; label: string; children: ReactNode; footer?: ReactNode }) {
  return <AnimatePresence>{open && <SheetBody key="sheet" onClose={onClose} label={label} footer={footer}>{children}</SheetBody>}</AnimatePresence>;
}
