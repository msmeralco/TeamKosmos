import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ChangeEvent,
  type MouseEvent as ReactMouseEvent,
  type PointerEvent as ReactPointerEvent,
  type ReactNode,
} from "react";
import type { RoofSubmission } from "../lib/api";
import { closingCrosses, crossesItself, selfIntersects } from "../lib/geometry";
import { Icon } from "./icons";
import { OptionPicker, ROOF_TYPES, RoofGlyph, type PickerOption } from "./RoofTypePicker";
import { MenuItem, Popover, Spinner } from "./ui";

/* Blank-canvas roof sketch: click corners, see each edge in metres, correct the scale with one real measurement,
   set which way the top of the canvas points, then send it to the backend. */

const W = 560;
const H = 400;
const DEFAULT_PX_PER_M = 20;
type Pt = [number, number];

const FACINGS = ["auto", "N", "NE", "E", "SE", "S", "SW", "W", "NW"] as const;
const FACING_NAME: Record<string, string> = {
  N: "North",
  NE: "North-east",
  E: "East",
  SE: "South-east",
  S: "South",
  SW: "South-west",
  W: "West",
  NW: "North-west",
};
const COMPASS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"];

function area(points: Pt[]): number {
  let a = 0;
  for (let i = 0; i < points.length; i++) {
    const [x1, y1] = points[i];
    const [x2, y2] = points[(i + 1) % points.length];
    a += x1 * y2 - x2 * y1;
  }
  return Math.abs(a) / 2;
}

/** Small compass: shows where the top of the canvas points, measured clockwise from true north. Display only. */
function CompassDial({ deg }: { deg: number }) {
  return (
    <svg width="68" height="68" viewBox="0 0 68 68" className="shrink-0" role="img" aria-label={`Top of the canvas points ${deg} degrees from north`}>
      <circle cx="34" cy="34" r="30" fill="#fff" stroke="#e5e5e4" strokeWidth="1.5" />
      <circle cx="34" cy="34" r="22" fill="none" stroke="#f0f0ee" strokeWidth="1" />
      {[0, 90, 180, 270].map((a) => (
        <line key={a} x1="34" y1="6" x2="34" y2="11" stroke="#a3a3a3" strokeWidth="1.5" strokeLinecap="round" transform={`rotate(${a} 34 34)`} />
      ))}
      <text x="34" y="19" textAnchor="middle" fontSize="8" fontWeight="700" fill="#787774">N</text>
      <g transform={`rotate(${deg} 34 34)`}>
        <path d="M34 15 L40 38 L34 34 L28 38 Z" fill="#ea580c" />
        <circle cx="34" cy="34" r="2.2" fill="#fff" stroke="#ea580c" strokeWidth="1.2" />
      </g>
    </svg>
  );
}

/** One setting as a compact button (label + current value) that opens its controls in a small panel above it.
    The panel is 250px wide so it always fits inside even a narrow roof-map panel. */
function SettingChip({
  label,
  value,
  icon,
  dot,
  placement,
  children,
}: {
  label: string;
  value: ReactNode;
  icon?: ReactNode;
  /** small status dot color class, e.g. "bg-[#047857]" */
  dot?: string;
  placement: "top-start" | "top-end";
  children: (close: () => void) => ReactNode;
}) {
  return (
    <div className="min-w-0">
      <Popover
        label={label}
        placement={placement}
        className="w-[250px]"
        trigger={({ open, toggle }) => (
          <button
            type="button"
            onClick={toggle}
            aria-haspopup="dialog"
            aria-expanded={open}
            className={`flex h-12 w-full items-center gap-2 rounded-[10px] bg-white px-3 text-left transition-colors hover:bg-[#fafaf9] ${
              open ? "shadow-[0_0_0_2px_#ea580c]" : "shadow-[0_0_0_1px_#d4d4d2]"
            }`}
          >
            {icon && <span className="shrink-0 text-[#ea580c]">{icon}</span>}
            <span className="min-w-0 flex-1">
              <span className="block text-[10px] font-medium uppercase tracking-wide text-[#a3a3a3]">{label}</span>
              <span className="flex items-center gap-1.5 truncate text-[13px] font-medium text-[#111111]">
                {dot && <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${dot}`} />}
                <span className="truncate">{value}</span>
              </span>
            </span>
            <span className={`shrink-0 text-[#787774] transition-transform ${open ? "rotate-180" : ""}`}>{Icon.chevronDown}</span>
          </button>
        )}
      >
        {children}
      </Popover>
    </div>
  );
}

export function SketchPad({
  disabled,
  onSubmit,
}: {
  disabled: boolean;
  onSubmit: (body: RoofSubmission) => Promise<void>;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [points, setPoints] = useState<Pt[]>([]);
  const [closed, setClosed] = useState(false);
  const [pxPerM, setPxPerM] = useState(DEFAULT_PX_PER_M);
  const [measured, setMeasured] = useState(false);
  const [northDeg, setNorthDeg] = useState(0);
  const [facing, setFacing] = useState<(typeof FACINGS)[number]>("auto");
  const [roofType, setRoofType] = useState<"flat" | "single_slope" | "gable">("flat");
  const [edgeIdx, setEdgeIdx] = useState(0);
  const [edgeLen, setEdgeLen] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sent, setSent] = useState(false);
  const drag = useRef<{ idx: number; startX: number; startY: number; moved: boolean } | null>(null);
  const suppressClick = useRef(false);

  /* A picture (roof photo, plan, screenshot) to trace over. It only lives in this browser tab: it is drawn behind the
     grid and is never sent anywhere, so what gets submitted is still just the traced outline and its settings. */
  const fileRef = useRef<HTMLInputElement>(null);
  const bgUrl = useRef<string | null>(null);
  const [bg, setBg] = useState<HTMLImageElement | null>(null);

  const edges = useMemo(() => {
    const n = points.length;
    if (n < 2) return [] as number[];
    const count = closed ? n : n - 1;
    return Array.from({ length: count }, (_, i) => {
      const [x1, y1] = points[i];
      const [x2, y2] = points[(i + 1) % n];
      return Math.hypot(x2 - x1, y2 - y1);
    });
  }, [points, closed]);

  // Keep the edge picker pointing at a real edge after Undo, Clear or closing the shape.
  useEffect(() => {
    setEdgeIdx((i) => Math.min(i, Math.max(0, edges.length - 1)));
  }, [edges.length]);

  // Any change to the sketch or its settings means what was sent is no longer what is on screen.
  useEffect(() => {
    setSent(false);
  }, [points, closed, pxPerM, northDeg, facing, roofType]);

  const areaM2 = closed && points.length >= 3 ? area(points) / (pxPerM * pxPerM) : null;

  const draw = useCallback(() => {
    const c = canvasRef.current;
    const ctx = c?.getContext("2d");
    if (!c || !ctx) return;
    ctx.clearRect(0, 0, W, H);
    ctx.fillStyle = "#fbfbfa";
    ctx.fillRect(0, 0, W, H);

    // the picture to trace over: fitted inside the canvas, softened so the grid and the outline stay readable
    if (bg) {
      const s = Math.min(W / bg.width, H / bg.height);
      const dw = bg.width * s;
      const dh = bg.height * s;
      ctx.globalAlpha = 0.65;
      ctx.drawImage(bg, (W - dw) / 2, (H - dh) / 2, dw, dh);
      ctx.globalAlpha = 1;
    }

    // metre grid: thin every metre, stronger every 5 m
    const step = pxPerM;
    for (let x = 0, i = 0; x <= W; x += step, i++) {
      ctx.strokeStyle = i % 5 === 0 ? "rgba(0,0,0,0.14)" : "rgba(0,0,0,0.05)";
      ctx.beginPath();
      ctx.moveTo(x, 0);
      ctx.lineTo(x, H);
      ctx.stroke();
    }
    for (let y = 0, i = 0; y <= H; y += step, i++) {
      ctx.strokeStyle = i % 5 === 0 ? "rgba(0,0,0,0.14)" : "rgba(0,0,0,0.05)";
      ctx.beginPath();
      ctx.moveTo(0, y);
      ctx.lineTo(W, y);
      ctx.stroke();
    }

    if (points.length) {
      ctx.beginPath();
      points.forEach(([x, y], i) => (i ? ctx.lineTo(x, y) : ctx.moveTo(x, y)));
      if (closed) {
        ctx.closePath();
        ctx.fillStyle = "rgba(234,88,12,0.14)";
        ctx.fill();
      }
      ctx.strokeStyle = "#ea580c";
      ctx.lineWidth = 2.5;
      ctx.lineJoin = "round";
      ctx.stroke();

      // edge labels in metres, as small rounded pills
      ctx.font = "600 11px ui-sans-serif, system-ui, sans-serif";
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      edges.forEach((len, i) => {
        const [x1, y1] = points[i];
        const [x2, y2] = points[(i + 1) % points.length];
        const mx = (x1 + x2) / 2;
        const my = (y1 + y2) / 2;
        const label = `${i + 1}: ${(len / pxPerM).toFixed(1)} m`;
        const w = ctx.measureText(label).width + 12;
        ctx.beginPath();
        ctx.roundRect(mx - w / 2, my - 10, w, 20, 10);
        ctx.fillStyle = "rgba(255,255,255,0.96)";
        ctx.fill();
        ctx.lineWidth = 1;
        ctx.strokeStyle = i === edgeIdx ? "#ea580c" : "#e5e5e4";
        ctx.stroke();
        ctx.fillStyle = i === edgeIdx ? "#c2410c" : "#444";
        ctx.fillText(label, mx, my + 0.5);
      });

      // a soft ring around the first corner once the shape could be closed: "click here to close"
      if (points.length >= 3 && !closed) {
        ctx.beginPath();
        ctx.arc(points[0][0], points[0][1], 17, 0, Math.PI * 2);
        ctx.strokeStyle = "rgba(234,88,12,0.4)";
        ctx.lineWidth = 3;
        ctx.stroke();
      }

      // numbered corners; the first one is larger (it is where the outline starts and where it closes)
      ctx.font = "700 10px ui-sans-serif, system-ui, sans-serif";
      points.forEach(([x, y], i) => {
        ctx.beginPath();
        ctx.arc(x, y, i === 0 ? 10 : 9, 0, Math.PI * 2);
        ctx.fillStyle = i === 0 ? "#ea580c" : "#fff";
        ctx.strokeStyle = "#ea580c";
        ctx.lineWidth = 2;
        ctx.fill();
        ctx.stroke();
        ctx.fillStyle = i === 0 ? "#fff" : "#c2410c";
        ctx.fillText(String(i + 1), x, y + 0.5);
      });
      ctx.textBaseline = "alphabetic";
    }

    // north badge (bottom-right, clear of the floating tools): the top of the canvas points northDeg clockwise from true north
    const nx = W - 36;
    const ny = H - 62;
    ctx.beginPath();
    ctx.arc(nx, ny, 24, 0, Math.PI * 2);
    ctx.fillStyle = "rgba(255,255,255,0.92)";
    ctx.fill();
    ctx.strokeStyle = "#e5e5e4";
    ctx.lineWidth = 1;
    ctx.stroke();
    ctx.save();
    ctx.translate(nx, ny);
    ctx.rotate((-northDeg * Math.PI) / 180);
    ctx.fillStyle = "#111";
    ctx.beginPath();
    ctx.moveTo(0, -17);
    ctx.lineTo(7, 9);
    ctx.lineTo(0, 4);
    ctx.lineTo(-7, 9);
    ctx.closePath();
    ctx.fill();
    ctx.restore();
    ctx.fillStyle = "#111";
    ctx.font = "bold 11px ui-sans-serif, system-ui, sans-serif";
    ctx.textAlign = "center";
    ctx.fillText("N", nx, H - 24);

    // scale bar (5 m) with end caps
    const bar = pxPerM * 5;
    ctx.fillStyle = "#444";
    ctx.fillRect(14, H - 22, bar, 3);
    ctx.fillRect(14, H - 27, 2, 13);
    ctx.fillRect(14 + bar - 2, H - 27, 2, 13);
    ctx.font = "11px ui-sans-serif, system-ui, sans-serif";
    ctx.textAlign = "left";
    ctx.fillText(measured ? "5 m · measured" : "5 m · suggested scale", 14, H - 33);
  }, [points, closed, pxPerM, northDeg, edges, edgeIdx, measured, bg]);

  useEffect(draw, [draw]);

  /** Pointer position in canvas units (the canvas may be shown larger or smaller than W x H). */
  const toCanvas = (e: { clientX: number; clientY: number }, el: HTMLCanvasElement): Pt => {
    const rect = el.getBoundingClientRect();
    return [((e.clientX - rect.left) * W) / rect.width, ((e.clientY - rect.top) * H) / rect.height];
  };

  // ---- resize by dragging a corner ----------------------------------------------------------------------------------
  const onPointerDown = (e: ReactPointerEvent<HTMLCanvasElement>) => {
    if (disabled || !points.length) return;
    const [x, y] = toCanvas(e, e.currentTarget);
    let hit = -1;
    let best = 12;
    points.forEach(([px, py], i) => {
      const d = Math.hypot(x - px, y - py);
      if (d <= best) {
        best = d;
        hit = i;
      }
    });
    if (hit < 0) return;
    drag.current = { idx: hit, startX: e.clientX, startY: e.clientY, moved: false };
    e.currentTarget.setPointerCapture(e.pointerId);
  };

  const onPointerMove = (e: ReactPointerEvent<HTMLCanvasElement>) => {
    const d = drag.current;
    if (!d) return;
    if (!d.moved && Math.hypot(e.clientX - d.startX, e.clientY - d.startY) < 4) return; // still a click
    d.moved = true;
    const [x, y] = toCanvas(e, e.currentTarget);
    const nx = Math.round(Math.min(W, Math.max(0, x)));
    const ny = Math.round(Math.min(H, Math.max(0, y)));
    const next = points.map((p, i) => (i === d.idx ? ([nx, ny] as Pt) : p));
    if (selfIntersects(next, closed)) return; // keep the last valid position
    setError(null);
    setPoints(next);
  };

  const onPointerUp = () => {
    const d = drag.current;
    drag.current = null;
    if (d?.moved) suppressClick.current = true; // the click that follows a drag must not add a corner
  };

  /** Grow or shrink the whole outline around its centre. */
  const scaleShape = (factor: number) => {
    if (points.length < 2) return;
    const cx = points.reduce((s, p) => s + p[0], 0) / points.length;
    const cy = points.reduce((s, p) => s + p[1], 0) / points.length;
    const next = points.map(([x, y]) => [cx + (x - cx) * factor, cy + (y - cy) * factor] as Pt);
    if (next.some(([x, y]) => x < 0 || x > W || y < 0 || y > H)) {
      setError("The outline can't get any bigger on this canvas. Make the scale smaller, or shrink the outline.");
      return;
    }
    setError(null);
    setPoints(next);
  };

  const onClick = (e: ReactMouseEvent<HTMLCanvasElement>) => {
    if (suppressClick.current) {
      suppressClick.current = false;
      return;
    }
    if (closed || disabled) return;
    const [x, y] = toCanvas(e, e.currentTarget);
    // clicking the first point closes the shape
    if (points.length >= 3 && Math.hypot(x - points[0][0], y - points[0][1]) < 12) {
      if (closingCrosses(points)) {
        setError("Closing here would make the outline cross itself. Undo the last corner and place it differently.");
        return;
      }
      setError(null);
      setClosed(true);
      return;
    }
    const next: Pt = [Math.round(x), Math.round(y)];
    if (crossesItself(points, next)) {
      setError("That corner would make the outline cross itself. Click a different spot, or undo the last corner.");
      return;
    }
    setError(null);
    setPoints((p) => [...p, next]);
  };

  const applyMeasure = () => {
    const metres = parseFloat(edgeLen);
    if (!edges[edgeIdx] || !(metres > 0.3 && metres < 100)) {
      setError("Enter a real length between 0.3 and 100 metres for the chosen edge.");
      return;
    }
    setError(null);
    setPxPerM(edges[edgeIdx] / metres);
    setMeasured(true);
    setEdgeLen("");
  };

  const submit = async () => {
    if (!closed || points.length < 3) return;
    setBusy(true);
    setError(null);
    try {
      await onSubmit({
        mode: "sketch",
        points_px: points,
        px_per_m: pxPerM,
        scale_source: measured ? "user_measured" : "default_grid",
        north_deg: northDeg,
        facing,
        roof_type: roofType,
      });
      setSent(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not send the sketch.");
    } finally {
      setBusy(false);
    }
  };

  const reset = () => {
    setPoints([]);
    setClosed(false);
    setError(null);
  };

  const onPickImage = (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = ""; // allow choosing the same file again
    if (!file) return;
    if (!file.type.startsWith("image/")) {
      setError("Please choose a picture (JPG, PNG or WebP).");
      return;
    }
    if (file.size > 15 * 1024 * 1024) {
      setError("That picture is too large. Choose one under 15 MB.");
      return;
    }
    const url = URL.createObjectURL(file);
    const img = new Image();
    img.onload = () => {
      if (bgUrl.current) URL.revokeObjectURL(bgUrl.current);
      bgUrl.current = url;
      setBg(img);
      setError(null);
    };
    img.onerror = () => {
      URL.revokeObjectURL(url);
      setError("Couldn't read that picture. Try a JPG or PNG.");
    };
    img.src = url;
  };

  const removeImage = () => {
    if (bgUrl.current) URL.revokeObjectURL(bgUrl.current);
    bgUrl.current = null;
    setBg(null);
  };

  // free the temporary picture URL when the sketch tab closes
  useEffect(
    () => () => {
      if (bgUrl.current) URL.revokeObjectURL(bgUrl.current);
    },
    [],
  );

  /* ---------------------------------------------------------------------------------------------------------------
     Presentation only from here on. Same look as the roof map panel: hairline cards, icon tools, custom menus,
     one big orange action at the bottom.
     --------------------------------------------------------------------------------------------------------------- */

  const step = closed ? 3 : points.length >= 3 ? 2 : 1;
  const hint = disabled
    ? "Start a chat with Sol first"
    : step === 1
      ? bg
        ? "Click the corners of your installation site on the picture"
        : "Click the corners of your installation site"
      : step === 2
        ? "Click the first orange corner to close the shape"
        : measured
          ? "Looks good. Send it when ready"
          : "Set the scale below, then send";

  const toolBtn =
    "flex h-8 w-8 items-center justify-center rounded-[8px] bg-white text-[#111111] shadow-[0_0_0_1px_#e5e5e4,0_1px_3px_rgba(0,0,0,0.08)] transition-colors hover:bg-[#fafaf9] hover:text-[#ea580c] disabled:opacity-40 disabled:hover:bg-white disabled:hover:text-[#111111]";
  const inputCls =
    "h-10 w-full rounded-[10px] bg-white pl-3 pr-7 text-[13px] text-[#111111] shadow-[0_0_0_1px_#d4d4d2] outline-none placeholder:text-[#a3a3a3] focus-visible:shadow-[0_0_0_2px_#ea580c] disabled:opacity-50";

  const edgeOptions: PickerOption<number>[] = edges.map((len, i) => ({
    id: i,
    label: `Edge ${i + 1}`,
    hint: `${(len / pxPerM).toFixed(1)} m on the sketch now`,
  }));

  const cornersLeft = Math.max(0, 3 - points.length);
  const actionLabel = busy ? (
    <Spinner />
  ) : sent ? (
    "Sent"
  ) : disabled ? (
    "Start a chat first"
  ) : !closed ? (
    points.length < 3 ? (
      `Add ${cornersLeft} more corner${cornersLeft === 1 ? "" : "s"} to continue`
    ) : (
      "Close the shape to continue"
    )
  ) : (
    <>
      {Icon.check}
      Use this sketch
    </>
  );

  /* Nothing scrolls: the canvas measures the space left over (after the settings row and the action bar) and
     takes the biggest size with the canvas' own 560 x 400 shape that fits. Pointer maths is unchanged because
     the canvas element is shown at exactly that shape. */
  const fitRef = useRef<HTMLDivElement>(null);
  const [fit, setFit] = useState<{ w: number; h: number } | null>(null);
  useEffect(() => {
    const el = fitRef.current;
    if (!el) return;
    const measure = () => {
      const s = Math.min(el.clientWidth / W, el.clientHeight / H);
      if (s > 0) setFit({ w: Math.floor(W * s), h: Math.floor(H * s) });
    };
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const currentType = ROOF_TYPES.find((t) => t.id === roofType) ?? ROOF_TYPES[0];

  // With the extra upload button the tool column is taller than a small canvas, so short canvases get two columns.
  const compactTools = fit ? fit.h < 300 : false;

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      {/* Canvas: the focus. Hint on the left, tools on the right, both floating on it. */}
      <div className="relative min-h-[200px] flex-1">
        <div ref={fitRef} className="absolute inset-x-4 top-4 bottom-2 flex items-center justify-center">
          <div
            className="relative isolate overflow-hidden rounded-[12px] bg-white shadow-[0_0_0_1px_#e5e5e4]"
            style={fit ? { width: fit.w, height: fit.h } : { width: "100%", aspectRatio: `${W} / ${H}` }}
          >
            <canvas
              ref={canvasRef}
              width={W}
              height={H}
              onClick={onClick}
              onPointerDown={onPointerDown}
              onPointerMove={onPointerMove}
              onPointerUp={onPointerUp}
              onPointerCancel={onPointerUp}
              className="block h-full w-full cursor-crosshair touch-none"
              aria-label="Installation site sketch canvas. Click to add corners; click the first corner to close the shape. Drag a corner to resize."
            />

            <div
              className={`pointer-events-none absolute top-3 left-3 z-10 flex ${compactTools ? "max-w-[calc(100%-100px)]" : "max-w-[calc(100%-64px)]"} items-center gap-2 rounded-full border border-[#e5e5e4] bg-white px-3.5 py-1.5 text-[12px] font-medium text-[#111111] shadow-[0_2px_8px_rgba(0,0,0,0.08)]`}
              role="status"
              aria-live="polite"
            >
              <span className="flex shrink-0 items-center gap-1" aria-hidden="true">
                {[1, 2, 3].map((n) => (
                  <span key={n} className={`h-1.5 rounded-full transition-all ${n === step ? "w-4 bg-[#ea580c]" : n < step ? "w-1.5 bg-[#ea580c]" : "w-1.5 bg-[#d4d4d2]"}`} />
                ))}
              </span>
              <span className="truncate">{hint}</span>
              {areaM2 !== null && (
                <span className="shrink-0 rounded-full bg-[#fff7ed] px-2 py-0.5 text-[11px] font-semibold text-[#c2410c]">≈ {Math.round(areaM2)} m²</span>
              )}
            </div>

            {/* errors and the "sent" confirmation float on the canvas too, so the layout never grows */}
            {(error || sent) && (
              <div
                className={`absolute top-[52px] left-3 z-10 ${compactTools ? "max-w-[calc(100%-104px)]" : "max-w-[calc(100%-68px)]"} rounded-[10px] border px-3 py-1.5 text-[12px] font-medium shadow-[0_2px_8px_rgba(0,0,0,0.08)] ${
                  error ? "border-[#fecaca] bg-[#fef2f2] text-[#b91c1c]" : "border-[#a7f3d0] bg-[#ecfdf5] text-[#047857]"
                }`}
                role={error ? "alert" : "status"}
              >
                {error ?? "Installation site sent to Sol. Change the sketch to send it again."}
              </div>
            )}

            <div
              className={`absolute top-3 right-3 z-10 ${compactTools ? "grid grid-cols-2 gap-1.5" : "flex flex-col gap-2"}`}
              role="group"
              aria-label="Sketch tools"
            >
              <button
                type="button"
                className={toolBtn}
                onClick={() => (closed ? setClosed(false) : setPoints((p) => p.slice(0, -1)))}
                disabled={!points.length}
                title={closed ? "Reopen the shape" : "Undo last corner"}
                aria-label={closed ? "Reopen the shape" : "Undo last corner"}
              >
                {Icon.undo}
              </button>
              <button type="button" className={toolBtn} onClick={reset} disabled={!points.length} title="Clear the sketch" aria-label="Clear the sketch">
                {Icon.trash}
              </button>
              <button type="button" className={toolBtn} onClick={() => scaleShape(0.9)} disabled={points.length < 2} title="Shrink the outline" aria-label="Shrink the outline">
                {Icon.minus}
              </button>
              <button type="button" className={toolBtn} onClick={() => scaleShape(1.1)} disabled={points.length < 2} title="Enlarge the outline" aria-label="Enlarge the outline">
                {Icon.plus}
              </button>
              {/* Upload a picture (roof photo, plan, screenshot) to trace over. It stays in this browser tab. */}
              <button
                type="button"
                className={toolBtn}
                onClick={() => fileRef.current?.click()}
                title={bg ? "Replace the picture" : "Upload a picture to trace over"}
                aria-label={bg ? "Replace the picture" : "Upload a picture to trace over"}
              >
                {Icon.upload}
              </button>
              {bg && (
                <button type="button" className={toolBtn} onClick={removeImage} title="Remove the picture" aria-label="Remove the picture">
                  {Icon.close}
                </button>
              )}
              <input ref={fileRef} type="file" accept="image/*" className="hidden" onChange={onPickImage} />
            </div>
          </div>
        </div>
      </div>

      {/* Settings: one compact row (2 x 2 in a narrow panel). Each opens its controls in a panel above it. */}
      <div className="@container shrink-0 px-4 pb-3">
        <div className="grid grid-cols-2 gap-2 @lg:grid-cols-4">
          <SettingChip
            label="Scale"
            placement="top-start"
            dot={measured ? "bg-[#047857]" : "bg-[#d97706]"}
            value={measured ? "Measured" : "Suggested"}
            icon={
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <rect x="2.5" y="8" width="19" height="8" rx="1.5" />
                <path d="M6.5 8v3M10.5 8v4.5M14.5 8v3M18.5 8v4.5" />
              </svg>
            }
          >
            {() => (
              <div className="flex flex-col gap-2.5 p-1.5">
                <p className="text-[12px] leading-relaxed text-[#787774]">Pick one edge and type how long it really is, in metres.</p>
                <OptionPicker label="Edge" placement="bottom-start" value={edgeIdx} options={edgeOptions} onChange={setEdgeIdx} disabled={!edges.length} />
                <div className="flex gap-2">
                  <div className="relative min-w-0 flex-1">
                    <input
                      className={inputCls}
                      inputMode="decimal"
                      placeholder="0.0"
                      aria-label="Real length of the chosen edge, in metres"
                      value={edgeLen}
                      onChange={(e) => setEdgeLen(e.target.value)}
                      disabled={!edges.length}
                    />
                    <span className="pointer-events-none absolute top-1/2 right-3 -translate-y-1/2 text-[12px] text-[#a3a3a3]">m</span>
                  </div>
                  <button
                    type="button"
                    className="inline-flex h-10 shrink-0 items-center justify-center rounded-[10px] bg-[#111111] px-4 text-[13px] font-medium text-white transition-colors hover:bg-[#333333] disabled:opacity-40"
                    onClick={applyMeasure}
                    disabled={!edges.length || !edgeLen}
                  >
                    Set
                  </button>
                </div>
                {!measured && points.length >= 2 && (
                  <p className="rounded-[10px] bg-[#fffbeb] px-3 py-2 text-[12px] leading-relaxed text-[#b45309]">
                    The scale is only a suggestion ({DEFAULT_PX_PER_M} px = 1 m). Without a real length the area and panel count can be far
                    off and the roof is marked low confidence.
                  </p>
                )}
                {error && <p className="text-[12px] text-[#dc2626]">{error}</p>}
              </div>
            )}
          </SettingChip>

          <SettingChip label="Direction" placement="top-end" value={`${COMPASS[Math.round(northDeg / 45) % 8]} · ${northDeg}°`} icon={Icon.compass}>
            {() => (
              <div className="flex items-center gap-3 p-1.5">
                <CompassDial deg={northDeg} />
                <div className="min-w-0 flex-1">
                  <label htmlFor="sketch-north" className="block text-[12px] leading-snug text-[#787774]">
                    Top of the canvas points to {northDeg}° from north
                  </label>
                  <input
                    id="sketch-north"
                    type="range"
                    min={0}
                    max={359}
                    value={northDeg}
                    onChange={(e) => setNorthDeg(Number(e.target.value))}
                    className="mt-2 w-full accent-[#ea580c]"
                  />
                </div>
              </div>
            )}
          </SettingChip>

          <SettingChip
            label="Site faces"
            placement="top-start"
            value={facing === "auto" ? "Not sure" : FACING_NAME[facing]}
            icon={Icon.sun}
          >
            {(close) => (
              <div role="menu" aria-label="Site faces" className="max-h-[280px] overflow-y-auto">
                {FACINGS.map((f) => (
                  <MenuItem
                    key={f}
                    checked={f === facing}
                    onSelect={() => {
                      setFacing(f);
                      close();
                    }}
                  >
                    <span className="block text-[13px] font-medium text-[#111111]">{f === "auto" ? "Not sure" : f}</span>
                    <span className="block text-[11px] text-[#787774]">{f === "auto" ? "Guess from the shape" : FACING_NAME[f]}</span>
                  </MenuItem>
                ))}
              </div>
            )}
          </SettingChip>

          <SettingChip label="Site type" placement="top-end" value={currentType.label} icon={<RoofGlyph type={currentType.id} />}>
            {(close) => (
              <div role="menu" aria-label="Site type">
                {ROOF_TYPES.map((t) => (
                  <MenuItem
                    key={t.id}
                    checked={t.id === roofType}
                    onSelect={() => {
                      setRoofType(t.id);
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
          </SettingChip>
        </div>
      </div>

      {/* Action bar */}
      <div className="shrink-0 border-t border-[#f0f0ee] bg-white px-4 py-3">
        <button
          type="button"
          className="inline-flex h-11 w-full items-center justify-center gap-2 rounded-[10px] bg-[#ea580c] px-4 text-[14px] font-semibold text-white shadow-[0_1px_3px_rgba(234,88,12,0.4)] transition-colors hover:bg-[#c2410c] disabled:bg-[#ececea] disabled:text-[#a3a3a3] disabled:shadow-none"
          onClick={submit}
          disabled={!closed || busy || disabled || sent}
        >
          {actionLabel}
        </button>
      </div>
    </div>
  );
}
