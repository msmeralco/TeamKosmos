import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { getRoofState, submitRoof, type RoofState, type RoofSubmission } from "../lib/api";
import { crossesItself, selfIntersects } from "../lib/geometry";
import { Icon } from "./icons";
import { SketchPad } from "./SketchPad";
import { RoofTypePicker } from "./RoofTypePicker";
import { btn, Spinner } from "./ui";

/* The right-hand "Roof Map" panel: satellite map with the roof outline and panel layout from the backend,
   a polygon drawing tool, and a blank-canvas sketch tool. Both send the roof to the backend session. */

const MANILA = { lat: 14.5995, lon: 120.9842, zoom: 12 };
const ESRI_KEY = (import.meta.env.VITE_ESRI_API_KEY as string | undefined) ?? "";
/* Esri now serves a "API KEY REQUIRED" watermark to anonymous requests, so the key is appended as a token. */
const SAT_URL =
  "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}" +
  (ESRI_KEY ? `?token=${ESRI_KEY}` : "");
const SAT_ATTR = "Tiles &copy; Esri &mdash; Source: Esri, Maxar, Earthstar Geographics, and the GIS User Community";
const OSM_URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png";
const OSM_ATTR = "&copy; OpenStreetMap contributors";
/* Esri reference overlays: road lines + street names, and place names. They use the same key as the imagery. */
const REF_BASE = "https://services.arcgisonline.com/arcgis/rest/services/Reference";
const REF_TOKEN = ESRI_KEY ? `?token=${ESRI_KEY}` : "";
const LABEL_URLS = [
  `${REF_BASE}/World_Transportation/MapServer/tile/{z}/{y}/{x}${REF_TOKEN}`,
  `${REF_BASE}/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}${REF_TOKEN}`,
];
const LABELS_ATTR = "Labels &copy; Esri";

type Tab = "map" | "sketch";
type Pt = [number, number]; // [lat, lng]
type UserLoc = { lat: number; lon: number; acc: number };
/** ask = consent card is showing; idle = nothing to show; locating / error = waiting for or failed browser lookup. */
type Consent = "ask" | "locating" | "error" | "idle";

/* The user's answer is remembered for this browser tab only, so reopening the map doesn't nag. */
const CONSENT_KEY = "sol.location.consent";
function readConsent(): "granted" | "declined" | null {
  try {
    const v = sessionStorage.getItem(CONSENT_KEY);
    return v === "granted" || v === "declined" ? v : null;
  } catch {
    return null;
  }
}
function writeConsent(v: "granted" | "declined") {
  try {
    sessionStorage.setItem(CONSENT_KEY, v);
  } catch {
    /* storage unavailable: the prompt will simply show again next time */
  }
}

/** Ground distance in metres between two [lat, lng] points. */
function metres(a: Pt, b: Pt): number {
  return L.latLng(a[0], a[1]).distanceTo(L.latLng(b[0], b[1]));
}

function formatMetres(m: number): string {
  return m < 10 ? `${m.toFixed(1)} m` : `${Math.round(m)} m`;
}

/** A small white pill showing a length, placed beside the middle of a drawn edge. */
function lengthLabel(a: Pt, b: Pt): L.Marker {
  const mid: Pt = [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2];
  const html =
    `<div style="transform:translate(-50%,-50%);white-space:nowrap;padding:1px 6px;border-radius:999px;` +
    `background:rgba(255,255,255,.95);color:#111;font:600 11px/16px system-ui,sans-serif;` +
    `box-shadow:0 1px 4px rgba(0,0,0,.4);border:1px solid #f59e0b">${formatMetres(metres(a, b))}</div>`;
  return L.marker(mid, {
    icon: L.divIcon({ className: "", html, iconSize: [0, 0] }),
    interactive: false,
    keyboard: false,
    zIndexOffset: 1000,
  });
}

/* ---- Roof result tiles (pure formatting, no map logic) ---- */

type RoofData = NonNullable<RoofState["roof"]>;

const COMPASS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"];
const compassLetters = (deg: number) => COMPASS[Math.round(deg / 45) % 8];

/** Display values for the four result tiles. azimuth_deg: 0 = north, clockwise. */
function roofStats(roof: RoofData, layout: RoofState["layout"]) {
  const degrees = ((Math.round(roof.azimuth_deg) % 360) + 360) % 360;
  return {
    area: `${Math.round(roof.area_m2)} m²`,
    usable: `${Math.round(roof.usable_area_m2)} m²`,
    letters: compassLetters(degrees),
    degrees,
    panels: layout ? String(layout.count) : "—",
  };
}

const CONFIDENCE_STYLE: Record<RoofData["confidence"], string> = {
  high: "bg-[#ecfdf5] text-[#047857]",
  medium: "bg-[#fffbeb] text-[#b45309]",
  low: "bg-[#fef2f2] text-[#b91c1c]",
};

/** Approximate ground area (m²) of an outline given as [lat, lng] corners: flat projection around its middle
    + shoelace formula. Plenty accurate for a roof-sized shape; the backend computes the official figure. */
function outlineAreaM2(points: Pt[]): number {
  if (points.length < 3) return 0;
  const lat0 = points.reduce((s, p) => s + p[0], 0) / points.length;
  const lng0 = points.reduce((s, p) => s + p[1], 0) / points.length;
  const mPerLat = 110574;
  const mPerLng = 111320 * Math.cos((lat0 * Math.PI) / 180);
  const xy = points.map((p) => [(p[1] - lng0) * mPerLng, (p[0] - lat0) * mPerLat] as const);
  let sum = 0;
  for (let i = 0; i < xy.length; i++) {
    const [x1, y1] = xy[i];
    const [x2, y2] = xy[(i + 1) % xy.length];
    sum += x1 * y2 - x2 * y1;
  }
  return Math.abs(sum) / 2;
}

/* ---- Undo / Check bar pinned to the map, just outside the outline ---- */

const ACTION_HALF_W = 44; // half the size of the little bar, in px
const ACTION_HALF_H = 22;

/** Pixel offset from the last corner that puts the bar just outside the outline: pushed away from the middle of
    the shape. If that would leave the visible map, try the opposite side, then the two sides. */
function actionOffset(map: L.Map, points: Pt[]): { x: number; y: number } {
  const last = map.latLngToContainerPoint(points[points.length - 1]);
  const size = map.getSize();
  const screen = points.map((p) => map.latLngToContainerPoint(p));
  const mx = screen.reduce((s, p) => s + p.x, 0) / screen.length;
  const my = screen.reduce((s, p) => s + p.y, 0) / screen.length;
  let ux = last.x - mx;
  let uy = last.y - my;
  let len = Math.hypot(ux, uy);
  if (points.length < 2 || len < 4) {
    ux = 1; // first corner (or a tiny shape): up and to the right
    uy = -1;
    len = Math.SQRT2;
  }
  ux /= len;
  uy /= len;
  // distance along (dx, dy) that clears the bar's box, plus a gap for the corner handle
  const reach = (dx: number, dy: number) =>
    Math.min(ACTION_HALF_W / Math.max(Math.abs(dx), 1e-3), ACTION_HALF_H / Math.max(Math.abs(dy), 1e-3)) + 18;
  const fits = (x: number, y: number) =>
    last.x + x - ACTION_HALF_W >= 8 &&
    last.x + x + ACTION_HALF_W <= size.x - 8 &&
    last.y + y - ACTION_HALF_H >= 8 &&
    last.y + y + ACTION_HALF_H <= size.y - 8;
  for (const [dx, dy] of [[ux, uy], [-ux, -uy], [uy, -ux], [-uy, ux]]) {
    const r = reach(dx, dy);
    if (fits(dx * r, dy * r)) return { x: dx * r, y: dy * r };
  }
  const r = reach(ux, uy);
  return { x: ux * r, y: uy * r };
}

function StatTile({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="min-w-0 rounded-[10px] border border-[#f0f0ee] bg-white px-3 py-2">
      <div className="text-[10px] font-medium uppercase tracking-wide text-[#a3a3a3]">{label}</div>
      <div className="mt-0.5 flex items-center gap-1.5 truncate text-[15px] font-semibold text-[#111111]">{children}</div>
    </div>
  );
}

export function MapCanvas({
  conversationId,
  refreshKey,
  onSubmitted,
  onClose,
}: {
  conversationId: string | null;
  refreshKey: number;
  onSubmitted: (what: "drawn" | "sketch") => void;
  /** Optional: closes this panel (used by the "Back to chat" button when there is no conversation yet). */
  onClose?: () => void;
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
  const labelsRef = useRef<L.LayerGroup | null>(null);
  const overlayRef = useRef<L.LayerGroup | null>(null);
  const shapeRef = useRef<L.LayerGroup | null>(null);
  const handlesRef = useRef<L.LayerGroup | null>(null);
  const drawingRef = useRef(false);
  const lastFitRef = useRef<string>("");
  const [zoom, setZoom] = useState(MANILA.zoom);

  /* Location sharing: ask when the map opens (unless the user already answered in this session). */
  const [consent, setConsent] = useState<Consent>(() => (readConsent() === null ? "ask" : "idle"));
  const [userLoc, setUserLoc] = useState<UserLoc | null>(null);
  const [locError, setLocError] = useState<string | null>(null);
  const userLocRef = useRef<UserLoc | null>(null);
  const stateRef = useRef<RoofState | null>(null);

  const pointsRef = useRef<Pt[]>([]);
  pointsRef.current = points;
  drawingRef.current = drawing;
  userLocRef.current = userLoc;
  stateRef.current = state;

  /** silent = the user already agreed earlier: look it up in the background, never show the card. */
  const locate = useCallback((silent = false) => {
    if (!("geolocation" in navigator)) {
      setLocError("This browser can't share its location.");
      setConsent(silent ? "idle" : "error");
      return;
    }
    if (!silent) setConsent("locating");
    setLocError(null);
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        writeConsent("granted");
        setUserLoc({ lat: pos.coords.latitude, lon: pos.coords.longitude, acc: pos.coords.accuracy });
        setConsent("idle");
      },
      (err) => {
        setLocError(
          err.code === err.PERMISSION_DENIED
            ? "Location access is blocked. You can allow it in your browser's site settings, or keep going without it."
            : "Couldn't get your location. Check your connection and try again.",
        );
        setConsent(silent ? "idle" : "error");
      },
      { enableHighAccuracy: true, timeout: 10000, maximumAge: 60000 },
    );
  }, []);

  const declineLocation = useCallback(() => {
    writeConsent("declined");
    setConsent("idle");
  }, []);

  // Already agreed earlier this session: look the position up again without asking twice.
  useEffect(() => {
    if (readConsent() === "granted") locate(true);
  }, [locate]);

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
        if ((err as { name?: string })?.name !== "AbortError") setLoadError("Could not load the installation site from the server.");
      });
    return () => ctrl.abort();
  }, [conversationId, refreshKey]);

  // The agent just asked for a drawing: switch to the right tool by itself.
  useEffect(() => {
    setTabChoice(null);
    if (state?.roofMethod === "draw" && state.needsRoof) setDrawing(true);
    // Don't throw away an outline the user is in the middle of drawing (e.g. after they typed an address).
    if (state && !state.needsRoof && pointsRef.current.length === 0) setDrawing(false);
  }, [state?.roofMethod, state?.needsRoof]); // eslint-disable-line react-hooks/exhaustive-deps

  // ---- create the Leaflet map once ---------------------------------------------------------------------------
  useEffect(() => {
    if (tab !== "map" || !hostRef.current || mapRef.current) return;
    const map = L.map(hostRef.current, { zoomControl: false, maxZoom: 19, attributionControl: true }).setView(
      [MANILA.lat, MANILA.lon],
      MANILA.zoom,
    );
    L.control.zoom({ position: "bottomright" }).addTo(map); // floats on the map, away from the top-right buttons
    mapRef.current = map;
    overlayRef.current = L.layerGroup().addTo(map);
    shapeRef.current = L.layerGroup().addTo(map);
    handlesRef.current = L.layerGroup().addTo(map);
    map.on("zoomend", () => setZoom(map.getZoom()));
    map.on("click", (e: L.LeafletMouseEvent) => {
      if (!drawingRef.current) return;
      const next: Pt = [e.latlng.lat, e.latlng.lng];
      if (crossesItself(pointsRef.current, next)) {
        setSendError("That corner would make the outline cross itself. Click a different spot, or undo the last corner.");
        return;
      }
      setSendError(null);
      setPoints((p) => [...p, next]);
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
      shapeRef.current = null;
      handlesRef.current = null;
      lastFitRef.current = "";
    };
  }, [tab]);

  // ---- basemap (satellite by default, street map as a fallback) ----------------------------------------------------
  useEffect(() => {
    const map = mapRef.current;
    if (!map || tab !== "map") return;
    baseRef.current?.remove();
    labelsRef.current?.remove();
    labelsRef.current = null;
    const layer = street
      ? L.tileLayer(OSM_URL, { maxZoom: 19, maxNativeZoom: 19, attribution: OSM_ATTR })
      : L.tileLayer(SAT_URL, { maxZoom: 19, maxNativeZoom: 18, attribution: SAT_ATTR }); // Esri has no tiles past ~z18 in many PH areas; Leaflet upscales instead
    layer.addTo(map).bringToBack();
    baseRef.current = layer;
    if (!street) {
      // Street and place names over the satellite imagery (the street map already has its own labels).
      if (!map.getPane("labels")) {
        const pane = map.createPane("labels");
        pane.style.zIndex = "250";
        pane.style.pointerEvents = "none";
      }
      labelsRef.current = L.layerGroup(
        LABEL_URLS.map((url, i) =>
          L.tileLayer(url, {
            pane: "labels",
            maxZoom: 19,
            maxNativeZoom: 18,
            attribution: i === 0 ? LABELS_ATTR : "",
          }),
        ),
      ).addTo(map);
    }
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
      // No zoom animation: the roof outline is redrawn at the same moment, and a vector layer drawn while Leaflet
      // animates a zoom is scaled with the animation (thick, stretched outline) until it snaps back.
      map.fitBounds(L.latLngBounds(ll), { maxZoom: 20, padding: [40, 40], animate: false });
    } else if (state?.pin) {
      // An address was found: go to it, even if the user also shared their own location.
      map.invalidateSize();
      map.setView([state.pin.lat, state.pin.lon], Math.max(state.center.zoom, 18), { animate: false });
    } else if (state && !userLocRef.current) {
      map.setView([state.center.lat, state.center.lon], state.center.zoom, { animate: false });
    }
  }, [state, conversationId, tab]);

  // Center on the user once they share their location (a saved roof outline takes priority).
  useEffect(() => {
    const map = mapRef.current;
    if (!map || tab !== "map" || !userLoc || stateRef.current?.roof || stateRef.current?.pin) return;
    map.invalidateSize();
    map.setView([userLoc.lat, userLoc.lon], 18);
  }, [userLoc, tab]);

  // ---- draw roof, panels and the in-progress outline --------------------------------------------------------------
  useEffect(() => {
    const layer = overlayRef.current;
    if (!layer) return;
    layer.clearLayers();
    const roof = state?.roof;
    if (roof) {
      const ring = roof.polygon_lonlat.map(([lon, lat]) => [lat, lon] as Pt);
      // White underlay first, so the orange outline stays readable on dark roofs and on busy satellite imagery.
      L.polygon(ring, { color: "#ffffff", weight: 7, opacity: 0.9, fill: false, interactive: false }).addTo(layer);
      L.polygon(ring, { color: "#ea580c", weight: 3.5, fillColor: "#ea580c", fillOpacity: 0.14, interactive: false }).addTo(layer);
    }
    if (state?.pin) {
      // The address the user typed, pinned on the map.
      L.marker([state.pin.lat, state.pin.lon], {
        icon: L.divIcon({
          className: "",
          html: '<div style="width:22px;height:22px;border-radius:50% 50% 50% 0;background:#ea580c;border:2px solid #fff;box-shadow:0 1px 6px rgba(0,0,0,.45);transform:rotate(-45deg)"></div>',
          iconSize: [22, 22],
          iconAnchor: [11, 26],
        }),
        interactive: false,
        keyboard: false,
      }).addTo(layer);
    }
    // Room left on the roof beyond the chosen design: faint dashed outlines.
    for (const p of state?.layout?.spots_lonlat ?? []) {
      L.polygon(p.map(([lon, lat]) => [lat, lon] as Pt), {
        color: "#1d4ed8", weight: 1, dashArray: "3 3", fillColor: "#1d4ed8", fillOpacity: 0.08, opacity: 0.55, interactive: false,
      }).addTo(layer);
    }
    for (const p of state?.layout?.panels_lonlat ?? []) {
      // Thin white edge + a slightly stronger fill: panels stay distinct from each other and from dark roofs.
      L.polygon(p.map(([lon, lat]) => [lat, lon] as Pt), {
        color: "#ffffff", weight: 1.25, opacity: 0.95, fillColor: "#1d4ed8", fillOpacity: 0.78, interactive: false,
      }).addTo(layer);
    }
    if (userLoc) {
      const here: Pt = [userLoc.lat, userLoc.lon];
      if (userLoc.acc > 0 && userLoc.acc < 500) {
        L.circle(here, { radius: userLoc.acc, color: "#2563eb", weight: 1, fillColor: "#2563eb", fillOpacity: 0.1, interactive: false }).addTo(layer);
      }
      L.circleMarker(here, { radius: 7, color: "#ffffff", weight: 2, fillColor: "#2563eb", fillOpacity: 1, interactive: false }).addTo(layer);
    }
  }, [state, tab, userLoc]);

  /** Draws the in-progress outline and its side lengths. Called while dragging a corner too. */
  const drawShape = useCallback((pts: Pt[]) => {
    const layer = shapeRef.current;
    if (!layer) return;
    layer.clearLayers();
    if (!pts.length) return;
    if (pts.length >= 3) L.polygon(pts, { color: "#f59e0b", weight: 3, fillOpacity: 0.15, dashArray: "6 4", interactive: false }).addTo(layer);
    else L.polyline(pts, { color: "#f59e0b", weight: 3, interactive: false }).addTo(layer);
    const sides = pts.length >= 3 ? pts.length : pts.length - 1;
    for (let i = 0; i < sides; i++) lengthLabel(pts[i], pts[(i + 1) % pts.length]).addTo(layer);
  }, []);

  // ---- editable corners: drag a corner to resize; click a "+" on a side to add a corner ---------------------------------
  useEffect(() => {
    const handles = handlesRef.current;
    if (!handles) return;
    handles.clearLayers();
    drawShape(points);
    const dot = (size: number, first: boolean, plus: boolean, label = "") =>
      L.divIcon({
        className: "",
        iconSize: [size, size],
        iconAnchor: [size / 2, size / 2],
        html: plus
          ? `<div style="box-sizing:border-box;width:${size}px;height:${size}px;border-radius:50%;background:#f59e0b;color:#fff;font:700 12px/${size}px system-ui;text-align:center;opacity:.85;cursor:copy">+</div>`
          : `<div style="box-sizing:border-box;width:${size}px;height:${size}px;border-radius:50%;background:${first ? "#f59e0b" : "#fff"};color:${first ? "#fff" : "#92400e"};border:2px solid #f59e0b;box-shadow:0 1px 4px rgba(0,0,0,.5);cursor:grab;font:700 10px/${size - 4}px system-ui;text-align:center">${label}</div>`,
      });
    points.forEach((pt, i) => {
      // Numbered corners; the first one is larger (it is where the outline starts).
      const m = L.marker(pt, { icon: dot(i === 0 ? 22 : 18, i === 0, false, String(i + 1)), draggable: true, zIndexOffset: 2000, keyboard: false });
      const moved = () => {
        const ll = m.getLatLng();
        return pointsRef.current.map((p, k) => (k === i ? ([ll.lat, ll.lng] as Pt) : p));
      };
      m.on("drag", () => drawShape(moved()));
      m.on("dragend", () => {
        const next = moved();
        if (selfIntersects(next, next.length >= 3)) {
          setSendError("That corner would make the outline cross itself, so it went back.");
          setPoints([...pointsRef.current]); // new array: rebuilds the handles at the old position
          return;
        }
        setSendError(null);
        setPoints(next);
      });
      m.addTo(handles);
    });
    if (points.length >= 3) {
      points.forEach((a, i) => {
        const b = points[(i + 1) % points.length];
        const mid: Pt = [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2];
        L.marker(mid, { icon: dot(14, false, true), zIndexOffset: 1500, keyboard: false, title: "Add a corner here" })
          .on("click", () => {
            const next = [...pointsRef.current];
            next.splice(i + 1, 0, mid);
            setPoints(next);
          })
          .addTo(handles);
      });
    }
  }, [points, tab, drawShape]);

  // ---- outline actions: Undo / Check pinned to the map next to the last corner, just outside the shape -----------
  const [actionsEl, setActionsEl] = useState<HTMLDivElement | null>(null);
  useEffect(() => {
    const map = mapRef.current;
    if (!map || tab !== "map" || !drawing || points.length === 0) {
      setActionsEl(null);
      return;
    }
    const el = document.createElement("div");
    const { x, y } = actionOffset(map, points);
    el.style.position = "absolute";
    el.style.transform = `translate(calc(-50% + ${x}px), calc(-50% + ${y}px))`;
    // The bar sits on the map: stop clicks / drags on it from adding corners or panning the map.
    L.DomEvent.disableClickPropagation(el);
    el.addEventListener("pointerdown", (e) => e.stopPropagation());
    const marker = L.marker(points[points.length - 1], {
      icon: L.divIcon({ className: "", html: el, iconSize: [0, 0] }),
      keyboard: false,
      zIndexOffset: 3000,
    }).addTo(map);
    setActionsEl(el);
    return () => {
      marker.remove();
      setActionsEl(null);
    };
  }, [points, drawing, tab]);

  const submit = useCallback(
    async (body: RoofSubmission) => {
      if (!conversationId) throw new Error("Send Sol a message first, then draw your installation site.");
      await submitRoof(conversationId, body);
      setPoints([]);
      setDrawing(false);
      onSubmitted(body.mode === "sketch" ? "sketch" : "drawn");
    },
    [conversationId, onSubmitted],
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

  // ---- keyboard while outlining: Enter confirms (3+ corners), Escape cancels ------------------------------------
  const sendRef = useRef(sendDrawn);
  sendRef.current = sendDrawn;
  const sendingRef = useRef(false);
  sendingRef.current = sending;
  useEffect(() => {
    if (!drawing || tab !== "map") return;
    let menuWasOpen = false;
    // Capture phase = runs before every other key handler, so we can see whether a menu was open at that moment.
    const onKeyCapture = (e: KeyboardEvent) => {
      if (e.key === "Escape") menuWasOpen = !!document.querySelector('.popover[data-open="true"]');
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.defaultPrevented) return;
      const el = e.target as HTMLElement | null;
      if (el && (el.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(el.tagName))) return; // typing
      if (e.key === "Escape") {
        // The chat uses Escape to stop a running reply, and dialogs / menus use it to close. Wait until they have
        // handled the key (they mark it with preventDefault, or a menu was open), then cancel only if nobody did.
        window.setTimeout(() => {
          if (e.defaultPrevented || menuWasOpen) return;
          setDrawing(false);
          setPoints([]);
        }, 0);
      } else if (e.key === "Enter" && !e.repeat) {
        if (el && (el.tagName === "BUTTON" || el.tagName === "A")) return; // Enter on a focused button just presses it
        if (pointsRef.current.length >= 3 && !sendingRef.current) {
          e.preventDefault();
          void sendRef.current();
        }
      }
    };
    window.addEventListener("keydown", onKeyCapture, true);
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKeyCapture, true);
      window.removeEventListener("keydown", onKey);
    };
  }, [drawing, tab]);

  const roof = state?.roof;
  const stats = roof ? roofStats(roof, state?.layout ?? null) : null;
  const step = points.length >= 3 ? 3 : zoom < 18 ? 1 : 2; // which part of the outlining the user is at
  const drawnArea = outlineAreaM2(points);

  // What the map legend shows: only things that are actually on the map right now.
  const legend: { key: string; label: string; swatch: ReactNode }[] = [];
  if (roof) legend.push({ key: "roof", label: "Site", swatch: <span className="h-2.5 w-4 rounded-[3px] border-2 border-[#ea580c] bg-[#ea580c]/15" /> });
  if (state?.layout && state.layout.count > 0)
    legend.push({
      key: "panels",
      label: `Panels · ${state.layout.count}`,
      swatch: <span className="h-2.5 w-4 rounded-[2px] border border-white bg-[#1d4ed8] shadow-[0_0_0_1px_#0b3d91]" />,
    });
  if (userLoc)
    legend.push({
      key: "you",
      label: "You",
      swatch: <span className="h-2.5 w-2.5 rounded-full border-2 border-white bg-[#2563eb] shadow-[0_0_0_1px_#2563eb]" />,
    });
  if (drawing && points.length > 0)
    legend.push({ key: "draft", label: "Your outline", swatch: <span className="h-2.5 w-4 rounded-[3px] border-2 border-dashed border-[#f59e0b]" /> });
  const roofNotes = roof ? [...roof.warnings, ...roof.notes.filter((n) => /confirm|assumed/i.test(n))] : [];

  /* Same look as the sidebar and chat: flat, hairline borders, orange only for the active state. */
  const tabBtn = (t: Tab, long: string, short: string) => (
    <button
      type="button"
      onClick={() => setTabChoice(t)}
      aria-pressed={tab === t}
      aria-label={long}
      className={`h-8 rounded-[8px] px-3 text-[12px] font-medium transition-colors ${
        tab === t ? "bg-[#fafaf9] text-[#ea580c]" : "text-[#787774] hover:bg-[#fafaf9] hover:text-[#111111]"
      }`}
    >
      {/* short names when the panel is narrow (container query on the header) */}
      <span className="@sm:hidden">{short}</span>
      <span className="hidden @sm:inline">{long}</span>
    </button>
  );
  const floatBtn =
    "flex h-8 w-8 items-center justify-center rounded-[8px] bg-white text-[#111111] shadow-[0_0_0_1px_#e5e5e4,0_1px_3px_rgba(0,0,0,0.08)] transition-colors hover:bg-[#fafaf9] hover:text-[#ea580c]";
  /* The outlining buttons in the footer are the main action of this panel, so they are bigger (40px) than
     the rest of the controls, the main one is solid orange, and the disabled state is clearly grey. */
  const secondaryBig =
    "inline-flex h-10 min-w-0 flex-1 items-center justify-center rounded-[10px] bg-white px-3 text-[13px] font-medium text-[#111111] shadow-[0_0_0_1px_#d4d4d2] transition-colors hover:bg-[#fafaf9] disabled:opacity-40";
  const primaryBig =
    "inline-flex h-11 w-full items-center justify-center gap-2 rounded-[10px] bg-[#ea580c] px-4 text-[14px] font-semibold text-white shadow-[0_1px_3px_rgba(234,88,12,0.4)] transition-colors hover:bg-[#c2410c] disabled:bg-[#ececea] disabled:text-[#a3a3a3] disabled:shadow-none";
  const cornersLeft = Math.max(0, 3 - points.length);

  return (
    <div className="roofmap flex min-h-0 flex-1 flex-col bg-white">
      {/* Header: same height and hairline as the chat header, so the two panes line up */}
      <div className="@container flex h-12 shrink-0 items-center gap-1 border-b border-[#f0f0ee] px-3">
        {tabBtn("map", "Satellite map", "Map")}
        {tabBtn("sketch", "Sketch canvas", "Sketch")}
      </div>

      {tab === "sketch" ? (
        <div className="flex min-h-0 flex-1 flex-col">
          <SketchPad disabled={!conversationId} onSubmit={submit} />
        </div>
      ) : (
        <>
          {/* The map fills the panel edge to edge; its controls float on top of it */}
          <div className="relative isolate min-h-[260px] flex-1 overflow-hidden">
            <div ref={hostRef} className="absolute inset-0 bg-[#f4f4f2]" />

            <div className="absolute top-3 right-3 z-[1000] flex flex-col gap-2">
              {consent === "idle" && (
                <button
                  type="button"
                  className={floatBtn}
                  onClick={() => (userLoc ? setUserLoc({ ...userLoc }) : setConsent("ask"))}
                  title={userLoc ? "Re-center on my location" : "Share my location"}
                  aria-label={userLoc ? "Re-center on my location" : "Share my location"}
                >
                  {Icon.pin}
                </button>
              )}
            </div>

            {/* Step indicator while outlining: 1 zoom in, 2 click corners, 3 adjust and confirm */}
            {drawing && (
              <div
                className="pointer-events-none absolute top-3 left-1/2 z-[1000] flex max-w-[calc(100%-112px)] -translate-x-1/2 items-center gap-2 rounded-full border border-[#e5e5e4] bg-white px-3.5 py-1.5 text-[12px] font-medium text-[#111111] shadow-[0_2px_8px_rgba(0,0,0,0.08)]"
                role="status"
                aria-live="polite"
              >
                <span className="flex shrink-0 items-center gap-1" aria-hidden="true">
                  {[1, 2, 3].map((n) => (
                    <span key={n} className={`h-1.5 rounded-full transition-all ${n === step ? "w-4 bg-[#ea580c]" : n < step ? "w-1.5 bg-[#ea580c]" : "w-1.5 bg-[#d4d4d2]"}`} />
                  ))}
                </span>
                <span className="truncate">
                  {step === 1
                    ? "Zoom in on your house first"
                    : step === 2
                      ? "Click the corners of your installation site"
                      : "Drag corners to adjust, then confirm"}
                </span>
                {step === 3 && drawnArea > 0 && (
                  <span className="shrink-0 rounded-full bg-[#fff7ed] px-2 py-0.5 text-[11px] font-semibold text-[#c2410c]">
                    ≈ {Math.round(drawnArea)} m²
                  </span>
                )}
              </div>
            )}
            {/* Undo / Check sit on the map itself, just outside the outline (see the "outline actions" effect) */}
            {actionsEl &&
              createPortal(
                <div
                  className="flex items-center gap-1 rounded-full bg-white p-1 shadow-[0_0_0_1px_#e5e5e4,0_4px_14px_rgba(0,0,0,0.18)]"
                  role="group"
                  aria-label="Outline actions"
                >
                  <button
                    type="button"
                    onClick={() => setPoints((p) => p.slice(0, -1))}
                    disabled={!points.length}
                    title="Undo last corner"
                    aria-label="Undo last corner"
                    className="flex h-9 w-9 items-center justify-center rounded-full text-[#111111] transition-colors hover:bg-[#f4f4f2] disabled:opacity-35 disabled:hover:bg-transparent"
                  >
                    {Icon.undo}
                  </button>
                  <button
                    type="button"
                    onClick={sendDrawn}
                    disabled={points.length < 3 || sending}
                    title={points.length < 3 ? `Add ${3 - points.length} more corner${3 - points.length === 1 ? "" : "s"} first` : "Use this outline (Enter)"}
                    aria-label="Use this outline"
                    className="flex h-9 w-9 items-center justify-center rounded-full bg-[#ea580c] text-white transition-colors hover:bg-[#c2410c] disabled:bg-[#ececea] disabled:text-[#a3a3a3] [&_svg]:size-[18px]"
                  >
                    {sending ? <Spinner /> : Icon.check}
                  </button>
                </div>,
                actionsEl,
              )}
            {/* Bottom-left stack: nothing here blocks the map, so you can pan, zoom and draw while it is showing.
                Order, top to bottom: location question, "start a chat first" message, legend, Satellite/Street. */}
            <div className="absolute bottom-8 left-3 z-[1000] flex max-w-[min(320px,calc(100%-72px))] flex-col items-start gap-2">
              {consent !== "idle" && (
                <div
                  role="region"
                  aria-labelledby="loc-title"
                  className="w-full rounded-[12px] border border-[#e5e5e4] bg-white p-3 shadow-[0_4px_16px_rgba(0,0,0,0.14)]"
                >
                  <div className="flex items-start gap-2.5">
                    <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-[#fff7ed] text-[#ea580c]">{Icon.pin}</span>
                    <div className="min-w-0">
                      <h3 id="loc-title" className="text-[13px] font-semibold text-[#111111]">
                        Share your location?
                      </h3>
                      <p className="mt-0.5 text-[12px] leading-relaxed text-[#787774]">
                        Sol can center the map on you to help find your roof. It stays in your browser and isn't saved or sent to our server.
                      </p>
                    </div>
                  </div>
                  {consent === "error" && locError && <p className="mt-2 text-[12px] text-[#dc2626]">{locError}</p>}
                  <div className="mt-2.5 flex gap-2">
                    <button type="button" className={`${btn.secondary} btn-sm flex-1`} onClick={declineLocation} disabled={consent === "locating"}>
                      Not now
                    </button>
                    <button type="button" className={`${btn.primary} btn-sm flex-1`} onClick={() => locate()} disabled={consent === "locating"}>
                      {consent === "locating" ? <Spinner /> : consent === "error" ? "Try again" : "Share"}
                    </button>
                  </div>
                </div>
              )}

              {!conversationId && (
                <div className="w-full rounded-[12px] border border-[#e5e5e4] bg-white p-3 shadow-[0_4px_16px_rgba(0,0,0,0.12)]">
                  <div className="flex items-start gap-2.5">
                    <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-[#f4f4f2] text-[#787774]">{Icon.chat}</span>
                    <div className="min-w-0">
                      <p className="text-[13px] font-semibold text-[#111111]">Start with a message</p>
                      <p className="mt-0.5 text-[12px] leading-relaxed text-[#787774]">Tell Sol about your home in the chat, then trace your installation site here.</p>
                    </div>
                  </div>
                  {onClose && (
                    <button type="button" className={`${btn.secondary} btn-sm mt-2.5 w-full`} onClick={onClose}>
                      Back to chat
                    </button>
                  )}
                </div>
              )}

              {legend.length > 0 && (
                <ul className="flex flex-col gap-1 rounded-[10px] border border-[#e5e5e4] bg-white/95 px-2.5 py-1.5 text-[11px] font-medium text-[#111111] shadow-[0_2px_8px_rgba(0,0,0,0.1)]" aria-label="Map legend">
                  {legend.map((l) => (
                    <li key={l.key} className="flex items-center gap-2">
                      <span className="flex w-4 shrink-0 items-center justify-center">{l.swatch}</span>
                      {l.label}
                    </li>
                  ))}
                </ul>
              )}

              {/* Satellite / Street: both options visible, the current one highlighted */}
              <div className="flex rounded-[10px] bg-white p-0.5 shadow-[0_0_0_1px_#e5e5e4,0_2px_8px_rgba(0,0,0,0.1)]" role="group" aria-label="Map type">
                {(
                  [
                    { id: false, label: "Satellite", swatch: "bg-[linear-gradient(135deg,#3f5d3a,#8a7a58)]" },
                    { id: true, label: "Street", swatch: "bg-[linear-gradient(135deg,#ecebe6_45%,#f6c453_46%,#f6c453_54%,#ecebe6_55%)]" },
                  ] as const
                ).map((o) => (
                  <button
                    key={o.label}
                    type="button"
                    onClick={() => setStreet(o.id)}
                    aria-pressed={street === o.id}
                    className={`flex h-7 items-center gap-1.5 rounded-[8px] px-2 text-[11px] font-medium transition-colors ${
                      street === o.id ? "bg-[#fafaf9] text-[#ea580c]" : "text-[#787774] hover:bg-[#fafaf9] hover:text-[#111111]"
                    }`}
                  >
                    <span className={`h-3.5 w-3.5 shrink-0 rounded-[4px] shadow-[0_0_0_1px_rgba(0,0,0,0.15)] ${o.swatch}`} />
                    {o.label}
                  </button>
                ))}
              </div>
            </div>
          </div>

          {/* Footer: roof result tiles, messages and the drawing actions. @container: the panel width changes
              when the split divider is dragged, so the tiles respond to this box, not to the screen. */}
          <div className="@container flex shrink-0 flex-col gap-2.5 border-t border-[#f0f0ee] bg-white px-4 py-3">
            {roof && stats && !drawing && (
              <div className="flex flex-col gap-2">
                <div className="flex items-center justify-between gap-2">
                  <span className="text-[12px] font-semibold text-[#111111]">Your installation site</span>
                  <span className={`rounded-full px-2 py-0.5 text-[11px] font-medium ${CONFIDENCE_STYLE[roof.confidence]}`}>
                    {roof.confidence.charAt(0).toUpperCase() + roof.confidence.slice(1)} confidence
                  </span>
                </div>
                <div className="grid grid-cols-2 gap-2 @md:grid-cols-4">
                  <StatTile label="Site area">{stats.area}</StatTile>
                  <StatTile label="Usable">{stats.usable}</StatTile>
                  <StatTile label="Facing">
                    <svg
                      width="14"
                      height="14"
                      viewBox="0 0 24 24"
                      className="shrink-0 text-[#ea580c]"
                      style={{ transform: `rotate(${stats.degrees}deg)` }}
                      aria-hidden="true"
                    >
                      <path d="M12 3l6 15-6-3-6 3z" fill="currentColor" />
                    </svg>
                    <span>
                      {stats.letters} <span className="text-[12px] font-medium text-[#787774]">{stats.degrees}°</span>
                    </span>
                  </StatTile>
                  <StatTile label="Panels">{stats.panels}</StatTile>
                </div>
                {roofNotes.length > 0 && (
                  <div className="rounded-[10px] bg-[#fffbeb] px-3 py-2 text-[12px] leading-relaxed text-[#b45309]">
                    {roofNotes.map((w) => (
                      <p key={w}>{w}</p>
                    ))}
                  </div>
                )}
              </div>
            )}
            {state?.layout && !drawing && (
              <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-[#787774]">
                <span>
                  {state.layout.count}
                  {state.layout.capacity ? ` of ${state.layout.capacity}` : ""} panel spots used
                </span>
                {(state.layout.spots_lonlat?.length ?? 0) > 0 && (
                  <>
                    <span className="inline-flex items-center gap-1">
                      <span className="inline-block h-2.5 w-2.5 rounded-[2px] bg-[#1d4ed8]/70" /> in your design
                    </span>
                    <span className="inline-flex items-center gap-1">
                      <span className="inline-block h-2.5 w-2.5 rounded-[2px] border border-dashed border-[#1d4ed8]/70" /> room for{" "}
                      {state.layout.spots_lonlat?.length} more
                    </span>
                  </>
                )}
              </div>
            )}
            {loadError && <p className="text-[12px] text-[#dc2626]">{loadError}</p>}
            {sendError && <p className="text-[12px] text-[#dc2626]">{sendError}</p>}

            {!drawing ? (
              <button
                type="button"
                className={primaryBig}
                disabled={!conversationId}
                onClick={() => {
                  setDrawing(true);
                  setPoints([]);
                  setSendError(null);
                }}
              >
                {/* outline-a-shape icon */}
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                  <path d="M5 8l7-4 7 4-2 10H7z" />
                  <circle cx="5" cy="8" r="1.4" fill="currentColor" />
                  <circle cx="12" cy="4" r="1.4" fill="currentColor" />
                  <circle cx="19" cy="8" r="1.4" fill="currentColor" />
                  <circle cx="17" cy="18" r="1.4" fill="currentColor" />
                  <circle cx="7" cy="18" r="1.4" fill="currentColor" />
                </svg>
                {roof ? "Redraw site outline" : "Draw site outline"}
              </button>
            ) : (
              <div className="flex flex-col gap-2">
                <div className="flex gap-2">
                  <RoofTypePicker value={roofType} onChange={setRoofType} />
                  <button
                    type="button"
                    className={`${secondaryBig} @max-xs:w-10 @max-xs:flex-none @max-xs:px-0`}
                    onClick={() => {
                      setDrawing(false);
                      setPoints([]);
                    }}
                    title="Cancel outlining (Esc)"
                    aria-label="Cancel outlining"
                  >
                    {/* text in a wide panel, just an X in a narrow one */}
                    <span className="hidden @xs:inline">Cancel</span>
                    <span className="@xs:hidden">{Icon.close}</span>
                  </button>
                </div>
                <button type="button" className={primaryBig} onClick={sendDrawn} disabled={points.length < 3 || sending}>
                  {sending ? (
                    <Spinner />
                  ) : cornersLeft > 0 ? (
                    `Add ${cornersLeft} more corner${cornersLeft === 1 ? "" : "s"} to continue`
                  ) : (
                    <>
                      {Icon.check}
                      Use this outline
                    </>
                  )}
                </button>
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}
