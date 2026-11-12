import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type MouseEvent as ReactMouseEvent,
  type PointerEvent as ReactPointerEvent,
} from "react";
import type { RoofSubmission } from "../lib/api";
import { closingCrosses, crossesItself, selfIntersects } from "../lib/geometry";
import { btn, Spinner } from "./ui";

/* Blank-canvas roof sketch: click corners, see each edge in metres, correct the scale with one real measurement,
   set which way the top of the canvas points, then send it to the backend. */

const W = 560;
const H = 400;
const DEFAULT_PX_PER_M = 20;
type Pt = [number, number];

const FACINGS = ["auto", "N", "NE", "E", "SE", "S", "SW", "W", "NW"] as const;

function area(points: Pt[]): number {
  let a = 0;
  for (let i = 0; i < points.length; i++) {
    const [x1, y1] = points[i];
    const [x2, y2] = points[(i + 1) % points.length];
    a += x1 * y2 - x2 * y1;
  }
  return Math.abs(a) / 2;
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
      ctx.lineWidth = 2;
      ctx.stroke();

      // edge labels in metres
      ctx.font = "12px ui-sans-serif, system-ui, sans-serif";
      ctx.textAlign = "center";
      edges.forEach((len, i) => {
        const [x1, y1] = points[i];
        const [x2, y2] = points[(i + 1) % points.length];
        const mx = (x1 + x2) / 2;
        const my = (y1 + y2) / 2;
        const label = `${i + 1}: ${(len / pxPerM).toFixed(1)} m`;
        const w = ctx.measureText(label).width + 8;
        ctx.fillStyle = "rgba(255,255,255,0.92)";
        ctx.fillRect(mx - w / 2, my - 9, w, 18);
        ctx.fillStyle = i === edgeIdx ? "#c2410c" : "#444";
        ctx.fillText(label, mx, my + 4);
      });
      points.forEach(([x, y], i) => {
        ctx.beginPath();
        ctx.arc(x, y, i === 0 ? 6 : 4, 0, Math.PI * 2);
        ctx.fillStyle = i === 0 ? "#ea580c" : "#fff";
        ctx.strokeStyle = "#ea580c";
        ctx.lineWidth = 2;
        ctx.fill();
        ctx.stroke();
      });
    }

    // north arrow: the top of the canvas points northDeg clockwise from true north
    ctx.save();
    ctx.translate(W - 34, 38);
    ctx.rotate((-northDeg * Math.PI) / 180);
    ctx.fillStyle = "#111";
    ctx.beginPath();
    ctx.moveTo(0, -20);
    ctx.lineTo(8, 10);
    ctx.lineTo(0, 4);
    ctx.lineTo(-8, 10);
    ctx.closePath();
    ctx.fill();
    ctx.restore();
    ctx.fillStyle = "#111";
    ctx.font = "bold 12px ui-sans-serif, system-ui, sans-serif";
    ctx.textAlign = "center";
    ctx.fillText("N", W - 34, 66);

    // scale bar (5 m)
    ctx.fillStyle = "#444";
    ctx.fillRect(14, H - 22, pxPerM * 5, 3);
    ctx.font = "11px ui-sans-serif, system-ui, sans-serif";
    ctx.textAlign = "left";
    ctx.fillText(measured ? "5 m (measured)" : "5 m (suggested scale)", 14, H - 28);
  }, [points, closed, pxPerM, northDeg, edges, edgeIdx, measured]);

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

  const field = "h-8 rounded-[8px] bg-white px-2 text-[13px] shadow-[0_0_0_1px_var(--hairline)] outline-none";

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto">
      <div className="overflow-hidden rounded-[12px] bg-white shadow-[0_0_0_1px_var(--hairline)]">
        <canvas
          ref={canvasRef}
          width={W}
          height={H}
          onClick={onClick}
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={onPointerUp}
          onPointerCancel={onPointerUp}
          className="block w-full cursor-crosshair touch-none"
          aria-label="Roof sketch canvas. Click to add corners; click the first corner to close the shape. Drag a corner to resize."
        />
      </div>

      <p className="text-[12px] text-[var(--label-2)]">
        {closed
          ? "Shape closed. Drag any corner to resize it, check the edge lengths, correct the scale if needed, then send it."
          : points.length < 3
            ? "Click the corners of your roof. Click the first (orange) corner again to close the shape."
            : "Keep clicking corners, or click the first (orange) corner to close the shape."}
        {areaM2 !== null && (
          <span className="font-medium text-[var(--fg)]">
            {" "}
            About {areaM2.toFixed(0)} m²{measured ? "." : " at the suggested scale (not measured yet)."}
          </span>
        )}
      </p>

      <div className="grid grid-cols-2 gap-2 max-sm:grid-cols-1">
        <label className="grid gap-1 text-[12px] text-[var(--label-2)]">
          Fix the scale: one real edge length
          <span className="flex gap-1.5">
            <select className={field} value={edgeIdx} onChange={(e) => setEdgeIdx(Number(e.target.value))} disabled={!edges.length}>
              {edges.map((_, i) => (
                <option key={i} value={i}>
                  Edge {i + 1}
                </option>
              ))}
            </select>
            <input
              className={`${field} w-20`}
              inputMode="decimal"
              placeholder="metres"
              value={edgeLen}
              onChange={(e) => setEdgeLen(e.target.value)}
              disabled={!edges.length}
            />
            <button type="button" className={`${btn.secondary} btn-sm`} onClick={applyMeasure} disabled={!edges.length || !edgeLen}>
              Set
            </button>
          </span>
        </label>

        <label className="grid gap-1 text-[12px] text-[var(--label-2)]">
          Top of the canvas points to {northDeg}° from north
          <input type="range" min={0} max={359} value={northDeg} onChange={(e) => setNorthDeg(Number(e.target.value))} />
        </label>

        <label className="grid gap-1 text-[12px] text-[var(--label-2)]">
          Roof faces
          <select className={field} value={facing} onChange={(e) => setFacing(e.target.value as (typeof FACINGS)[number])}>
            {FACINGS.map((f) => (
              <option key={f} value={f}>
                {f === "auto" ? "Not sure (guess from shape)" : f}
              </option>
            ))}
          </select>
        </label>

        <label className="grid gap-1 text-[12px] text-[var(--label-2)]">
          Roof type
          <select className={field} value={roofType} onChange={(e) => setRoofType(e.target.value as typeof roofType)}>
            <option value="flat">Flat</option>
            <option value="single_slope">Single slope</option>
            <option value="gable">Gable (two slopes)</option>
          </select>
        </label>
      </div>

      {!measured && points.length >= 2 && (
        <p className="rounded-[10px] bg-[var(--accent-soft)] px-3 py-2 text-[12px] text-[var(--accent-ink)]">
          The scale is only a suggestion (20 px = 1 m). Draw one edge, then enter its real length under &ldquo;Fix the
          scale&rdquo;. Without it the area and panel count can be far off and the roof is marked low confidence.
        </p>
      )}
      {error && <p className="text-[12px] text-red-600">{error}</p>}
      {sent && !error && (
        <p className="text-[12px] text-green-700" role="status">
          Roof sent to Sol. Change the sketch to send it again.
        </p>
      )}

      <div className="flex flex-wrap gap-2 pb-1">
        <button type="button" className={`${btn.secondary} btn-sm`} onClick={() => (closed ? setClosed(false) : setPoints((p) => p.slice(0, -1)))} disabled={!points.length}>
          Undo
        </button>
        <button type="button" className={`${btn.secondary} btn-sm`} onClick={reset} disabled={!points.length}>
          Clear
        </button>
        <button type="button" className={`${btn.secondary} btn-sm`} onClick={() => scaleShape(0.9)} disabled={points.length < 2} title="Shrink the outline">
          Smaller
        </button>
        <button type="button" className={`${btn.secondary} btn-sm`} onClick={() => scaleShape(1.1)} disabled={points.length < 2} title="Enlarge the outline">
          Larger
        </button>
        <span className="flex-1" />
        <button type="button" className={`${btn.primary} btn-sm`} onClick={submit} disabled={!closed || busy || disabled || sent}>
          {busy ? <Spinner /> : sent ? "Sent" : "Use this sketch"}
        </button>
      </div>
    </div>
  );
}
