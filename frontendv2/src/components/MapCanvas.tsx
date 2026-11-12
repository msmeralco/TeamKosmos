import { useCallback, useEffect, useRef, useState } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { getRoofState, submitRoof, type RoofState, type RoofSubmission } from "../lib/api";
import { SketchPad } from "./SketchPad";
import { btn, Spinner } from "./ui";

/* The right-hand "Roof Map" panel: satellite map with the roof outline and panel layout from the backend,
   a polygon drawing tool, and a blank-canvas sketch tool. Both send the roof to the backend session. */

const MANILA = { lat: 14.5995, lon: 120.9842, zoom: 12 };
const SAT_URL = "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}";
const SAT_ATTR = "Tiles &copy; Esri &mdash; Source: Esri, Maxar, Earthstar Geographics, and the GIS User Community";
const OSM_URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png";
const OSM_ATTR = "&copy; OpenStreetMap contributors";

type Tab = "map" | "sketch";
type Pt = [number, number]; // [lat, lng]

export function MapCanvas({
  conversationId,
  personaId,
  refreshKey,
  onSubmitted,
}: {
  conversationId: string | null;
  personaId: string;
  refreshKey: number;
  onSubmitted: (what: "drawn" | "sketch") => void;
}) {
  const [state, setState] = useState<RoofState | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [tabChoice, setTabChoice] = useState<Tab | null>(null);
  const [street, setStreet] = useState(false);
  const [drawing, setDrawing] = useState(false);
  const [points, setPoints] = useState<Pt[]>([]);
  const [roofType, setRoofType] = useState<"flat" | "single_slope" | "gable">("flat");
  const [sending, setSending] = useState(false);
  const [sendError, setSendError] = useState<string | null>(null);

  const hostRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<L.Map | null>(null);
  const baseRef = useRef<L.TileLayer | null>(null);
  const overlayRef = useRef<L.LayerGroup | null>(null);
  const drawingRef = useRef(false);
  const lastFitRef = useRef<string>("");
  const [zoom, setZoom] = useState(MANILA.zoom);

  drawingRef.current = drawing;

  const autoTab: Tab = state?.roofMethod === "sketch" && state.needsRoof ? "sketch" : "map";
  const tab: Tab = tabChoice ?? autoTab;

  // ---- load roof state from the backend ------------------------------------------------------------------
  useEffect(() => {
    if (!conversationId) {
      setState(null);
      return;
    }
    const ctrl = new AbortController();
    getRoofState(conversationId, ctrl.signal)
      .then((s) => {
        setState(s);
        setLoadError(null);
      })
      .catch((err: unknown) => {
        if ((err as { name?: string })?.name !== "AbortError") setLoadError("Could not load the roof from the server.");
      });
    return () => ctrl.abort();
  }, [conversationId, refreshKey]);

  // The agent just asked for a drawing: switch to the right tool by itself.
  useEffect(() => {
    setTabChoice(null);
    if (state?.roofMethod === "draw" && state.needsRoof) setDrawing(true);
    if (state && !state.needsRoof) setDrawing(false);
  }, [state?.roofMethod, state?.needsRoof]); // eslint-disable-line react-hooks/exhaustive-deps

  // ---- create the Leaflet map once ---------------------------------------------------------------------------
  useEffect(() => {
    if (tab !== "map" || !hostRef.current || mapRef.current) return;
    const map = L.map(hostRef.current, { zoomControl: true, maxZoom: 21, attributionControl: true }).setView(
      [MANILA.lat, MANILA.lon],
      MANILA.zoom,
    );
    mapRef.current = map;
    overlayRef.current = L.layerGroup().addTo(map);
    map.on("zoomend", () => setZoom(map.getZoom()));
    map.on("click", (e: L.LeafletMouseEvent) => {
      if (drawingRef.current) setPoints((p) => [...p, [e.latlng.lat, e.latlng.lng]]);
    });
    // The panel animates its width from 0, so Leaflet must re-measure whenever the box size changes.
    const ro = new ResizeObserver(() => map.invalidateSize());
    ro.observe(hostRef.current);
    return () => {
      ro.disconnect();
      map.remove();
      mapRef.current = null;
      baseRef.current = null;
      overlayRef.current = null;
      lastFitRef.current = "";
    };
  }, [tab]);

  // ---- basemap (satellite by default, street map as a fallback) ----------------------------------------------------
  useEffect(() => {
    const map = mapRef.current;
    if (!map || tab !== "map") return;
    baseRef.current?.remove();
    const layer = street
      ? L.tileLayer(OSM_URL, { maxZoom: 21, maxNativeZoom: 19, attribution: OSM_ATTR })
      : L.tileLayer(SAT_URL, { maxZoom: 21, maxNativeZoom: 19, attribution: SAT_ATTR });
    layer.addTo(map).bringToBack();
    baseRef.current = layer;
  }, [street, tab]);

  // ---- move the camera ----------------------------------------------------------------------------------------------------
  useEffect(() => {
    const map = mapRef.current;
    if (!map || tab !== "map") return;
    const key = `${conversationId}|${state?.roof?.id ?? "none"}|${state ? `${state.center.lat},${state.center.lon}` : "x"}`;
    if (key === lastFitRef.current) return;
    lastFitRef.current = key;
    if (state?.roof) {
      const ll = state.roof.polygon_lonlat.map(([lon, lat]) => [lat, lon] as Pt);
      map.invalidateSize();
      map.fitBounds(L.latLngBounds(ll), { maxZoom: 20, padding: [40, 40] });
    } else if (state) {
      map.setView([state.center.lat, state.center.lon], state.center.zoom);
    }
  }, [state, conversationId, tab]);

  // ---- draw roof, panels and the in-progress outline --------------------------------------------------------------
  useEffect(() => {
    const layer = overlayRef.current;
    if (!layer) return;
    layer.clearLayers();
    const roof = state?.roof;
    if (roof) {
      const ring = roof.polygon_lonlat.map(([lon, lat]) => [lat, lon] as Pt);
      L.polygon(ring, { color: "#ea580c", weight: 3, fillColor: "#ea580c", fillOpacity: 0.12 }).addTo(layer);
    }
    for (const p of state?.layout?.panels_lonlat ?? []) {
      L.polygon(p.map(([lon, lat]) => [lat, lon] as Pt), {
        color: "#0b3d91", weight: 1, fillColor: "#1d4ed8", fillOpacity: 0.65,
      }).addTo(layer);
    }
    if (points.length) {
      if (points.length >= 3) L.polygon(points, { color: "#f59e0b", weight: 3, fillOpacity: 0.15, dashArray: "6 4" }).addTo(layer);
      else L.polyline(points, { color: "#f59e0b", weight: 3 }).addTo(layer);
      points.forEach((pt, i) =>
        L.circleMarker(pt, { radius: i === 0 ? 7 : 5, color: "#f59e0b", fillColor: "#fff", fillOpacity: 1, weight: 2 }).addTo(layer),
      );
    }
  }, [state, points, tab]);

  const submit = useCallback(
    async (body: RoofSubmission) => {
      if (!conversationId) throw new Error("Send Sol a message first, then draw your roof.");
      await submitRoof(conversationId, personaId, body);
      setPoints([]);
      setDrawing(false);
      onSubmitted(body.mode === "sketch" ? "sketch" : "drawn");
    },
    [conversationId, personaId, onSubmitted],
  );

  const sendDrawn = async () => {
    if (points.length < 3) return;
    setSending(true);
    setSendError(null);
    try {
      await submit({ mode: "drawn", polygon_lonlat: points.map(([lat, lng]) => [lng, lat] as [number, number]), roof_type: roofType });
    } catch (err) {
      setSendError(err instanceof Error ? err.message : "Could not send the outline.");
    } finally {
      setSending(false);
    }
  };

  const roof = state?.roof;
  const compass = (deg: number) => ["N", "NE", "E", "SE", "S", "SW", "W", "NW"][Math.round(deg / 45) % 8];
  const tabBtn = (t: Tab, label: string) => (
    <button
      type="button"
      onClick={() => setTabChoice(t)}
      aria-pressed={tab === t}
      className={`row-btn press h-7 rounded-[8px] px-3 text-[13px] font-medium ${tab === t ? "bg-[var(--brand-soft)] text-[var(--brand)]" : "text-[var(--label-2)]"}`}
    >
      {label}
    </button>
  );

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-3 p-4">
      <div className="flex items-center gap-1">
        {tabBtn("map", "Satellite map")}
        {tabBtn("sketch", "Sketch canvas")}
        <span className="flex-1" />
        {tab === "map" && (
          <button type="button" className={`${btn.secondary} btn-sm`} onClick={() => setStreet((s) => !s)}>
            {street ? "Satellite" : "Street map"}
          </button>
        )}
      </div>

      {tab === "sketch" ? (
        <SketchPad disabled={!conversationId} onSubmit={submit} />
      ) : (
        <>
          <div className="relative min-h-[260px] flex-1 overflow-hidden rounded-[14px] shadow-[0_0_0_1px_var(--hairline)]">
            <div ref={hostRef} className="absolute inset-0 bg-[var(--fill)]" />
            {drawing && (
              <div className="pointer-events-none absolute top-3 left-1/2 z-[1000] -translate-x-1/2 rounded-full bg-white/95 px-3 py-1.5 text-[12px] font-medium shadow-[0_1px_6px_rgba(0,0,0,0.18)]">
                {zoom < 18
                  ? "Zoom in on your house first, then click its corners"
                  : points.length < 3
                    ? "Click the corners of your roof"
                    : "Add more corners or press “Use this outline”"}
              </div>
            )}
            {!conversationId && (
              <div className="absolute inset-x-3 bottom-3 z-[1000] rounded-[10px] bg-white/95 px-3 py-2 text-[12px] shadow-[0_1px_6px_rgba(0,0,0,0.18)]">
                Send Sol a message first, then trace your roof here.
              </div>
            )}
          </div>

          {roof && !drawing && (
            <div className="rounded-[12px] bg-white px-3 py-2 text-[12px] shadow-[0_0_0_1px_var(--hairline)]">
              <span className="font-medium text-[var(--fg)]">{roof.area_m2.toFixed(0)} m²</span> roof · faces{" "}
              {compass(roof.azimuth_deg)} ({roof.azimuth_deg.toFixed(0)}°) · {roof.usable_area_m2.toFixed(0)} m² usable ·{" "}
              {roof.confidence} confidence
              {state?.layout ? ` · ${state.layout.count} panels placed` : ""}
              {[...roof.warnings, ...roof.notes.filter((n) => /confirm|assumed/i.test(n))].map((w) => (
                <div key={w} className="mt-1 text-[var(--accent-ink)]">{w}</div>
              ))}
            </div>
          )}
          {loadError && <p className="text-[12px] text-red-600">{loadError}</p>}
          {sendError && <p className="text-[12px] text-red-600">{sendError}</p>}

          <div className="flex flex-wrap items-center gap-2">
            {!drawing ? (
              <button
                type="button"
                className={`${btn.primary} btn-sm`}
                disabled={!conversationId}
                onClick={() => {
                  setDrawing(true);
                  setPoints([]);
                  setSendError(null);
                }}
              >
                {roof ? "Redraw roof outline" : "Draw roof outline"}
              </button>
            ) : (
              <>
                <select
                  className="h-8 rounded-[8px] bg-white px-2 text-[13px] shadow-[0_0_0_1px_var(--hairline)] outline-none"
                  value={roofType}
                  onChange={(e) => setRoofType(e.target.value as typeof roofType)}
                  aria-label="Roof type"
                >
                  <option value="flat">Flat roof</option>
                  <option value="single_slope">Single slope</option>
                  <option value="gable">Gable</option>
                </select>
                <button type="button" className={`${btn.secondary} btn-sm`} onClick={() => setPoints((p) => p.slice(0, -1))} disabled={!points.length}>
                  Undo
                </button>
                <button
                  type="button"
                  className={`${btn.secondary} btn-sm`}
                  onClick={() => {
                    setDrawing(false);
                    setPoints([]);
                  }}
                >
                  Cancel
                </button>
                <span className="flex-1" />
                <button type="button" className={`${btn.primary} btn-sm`} onClick={sendDrawn} disabled={points.length < 3 || sending}>
                  {sending ? <Spinner /> : "Use this outline"}
                </button>
              </>
            )}
          </div>
        </>
      )}
    </div>
  );
}
