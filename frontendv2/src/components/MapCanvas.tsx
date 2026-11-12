import { useState } from "react";
import { Icon } from "./icons";

export type SolarZone = {
  id: string;
  name: string;
  area: string;
  capacity: string;
  savings: string;
  priority: "High" | "Medium" | "Low" | "Review Required";
  color: string;
  borderColor: string;
  x: number;
  y: number;
  polygonPoints: string;
};

export const DEMO_ZONES: SolarZone[] = [
  {
    id: "zone-newark",
    name: "Newark Residential Sector",
    area: "84 m²",
    capacity: "9.2 kWp",
    savings: "₱9,800/mo",
    priority: "High",
    color: "rgba(234, 88, 12, 0.22)",
    borderColor: "rgba(234, 88, 12, 0.85)",
    x: 42,
    y: 52,
    polygonPoints: "40,42 48,44 51,56 47,62 39,60 36,49",
  },
  {
    id: "zone-east-orange",
    name: "East Orange Rooftop Cluster",
    area: "62 m²",
    capacity: "6.8 kWp",
    savings: "₱7,100/mo",
    priority: "Medium",
    color: "rgba(245, 158, 11, 0.18)",
    borderColor: "rgba(245, 158, 11, 0.75)",
    x: 41,
    y: 43,
    polygonPoints: "37,35 45,35 48,45 42,48 35,45 34,39",
  },
  {
    id: "zone-union",
    name: "Union Suburban Homes",
    area: "54 m²",
    capacity: "5.5 kWp",
    savings: "₱5,900/mo",
    priority: "Low",
    color: "rgba(245, 158, 11, 0.12)",
    borderColor: "rgba(245, 158, 11, 0.5)",
    x: 33,
    y: 62,
    polygonPoints: "29,56 37,56 40,65 35,71 27,69 26,60",
  },
  {
    id: "zone-morristown",
    name: "Morristown Valley",
    area: "48 m²",
    capacity: "4.9 kWp",
    savings: "₱4,800/mo",
    priority: "Low",
    color: "rgba(245, 158, 11, 0.12)",
    borderColor: "rgba(245, 158, 11, 0.5)",
    x: 13,
    y: 33,
    polygonPoints: "9,27 17,27 20,36 16,42 8,40 7,31",
  },
  {
    id: "zone-fort-lee",
    name: "Fort Lee Terraces",
    area: "110 m²",
    capacity: "12.4 kWp",
    savings: "₱14,200/mo",
    priority: "High",
    color: "rgba(234, 88, 12, 0.22)",
    borderColor: "rgba(234, 88, 12, 0.85)",
    x: 77,
    y: 23,
    polygonPoints: "72,17 80,18 84,27 79,33 71,31 69,22",
  },
  {
    id: "zone-bayonne",
    name: "Bayonne Waterfront District",
    area: "76 m²",
    capacity: "8.1 kWp",
    savings: "₱8,600/mo",
    priority: "Review Required",
    color: "rgba(234, 88, 12, 0.16)",
    borderColor: "rgba(234, 88, 12, 0.65)",
    x: 71,
    y: 54,
    polygonPoints: "66,48 74,47 78,57 73,64 65,62 63,52",
  },
  {
    id: "zone-queens",
    name: "Queens Sunny Ridge",
    area: "70 m²",
    capacity: "7.6 kWp",
    savings: "₱7,900/mo",
    priority: "Medium",
    color: "rgba(245, 158, 11, 0.18)",
    borderColor: "rgba(245, 158, 11, 0.75)",
    x: 84,
    y: 47,
    polygonPoints: "80,41 87,42 90,51 86,57 79,55 78,46",
  },
];

interface MapCanvasProps {
  onSelectZone?: (zone: SolarZone) => void;
  onClose?: () => void;
  selectedZoneId?: string | null;
}

export function MapCanvas({ onSelectZone, onClose, selectedZoneId }: MapCanvasProps) {
  const [zoom, setZoom] = useState(1);
  const [activeZone, setActiveZone] = useState<SolarZone | null>(
    DEMO_ZONES.find((z) => z.id === selectedZoneId) || null
  );
  const [searchQuery, setSearchQuery] = useState("");
  const [activeFilter, setActiveFilter] = useState<string | null>(null);

  const handleZoneClick = (zone: SolarZone) => {
    setActiveZone(zone);
    if (onSelectZone) onSelectZone(zone);
  };

  const handleZoomIn = () => setZoom((z) => Math.min(z + 0.15, 1.6));
  const handleZoomOut = () => setZoom((z) => Math.max(z - 0.15, 0.8));

  return (
    <div className="relative flex h-full w-full flex-col overflow-hidden bg-[#fafaf9] select-none">
      {/* ---------------- Top Floating Search & Tool Controls ---------------- */}
      <div className="pointer-events-none absolute top-4 right-4 left-4 z-20 flex items-center justify-between gap-3">
        {/* Search Capsule (Clean two-tone, minimal outlines) */}
        <div className="pointer-events-auto flex h-10 w-[360px] max-w-[55vw] items-center gap-2.5 rounded-[12px] bg-white px-3.5 shadow-[0_2px_12px_rgba(0,0,0,0.04)] backdrop-blur-md transition-all focus-within:ring-1 focus-within:ring-[#ea580c]">
          <span className="text-[#ea580c]">{Icon.search}</span>
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search locations and observations"
            className="flex-1 bg-transparent text-[13px] text-[#111111] placeholder-[#a3a3a3] outline-none"
          />
          {searchQuery && (
            <button
              type="button"
              onClick={() => setSearchQuery("")}
              className="text-[#a3a3a3] hover:text-[#111111]"
            >
              {Icon.close}
            </button>
          )}
        </div>

        {/* Action Tool Island (Minimal two-tone) */}
        <div className="pointer-events-auto flex items-center gap-1.5">
          <div className="flex h-10 items-center rounded-[12px] bg-white p-1 shadow-[0_2px_12px_rgba(0,0,0,0.04)]">
            <button
              type="button"
              onClick={() => setActiveFilter(activeFilter === "sliders" ? null : "sliders")}
              title="Filters"
              className={`flex h-8 w-8 items-center justify-center rounded-[8px] transition-colors ${
                activeFilter === "sliders" ? "bg-[#ea580c] text-white" : "text-[#787774] hover:bg-[#fafaf9] hover:text-[#111111]"
              }`}
            >
              {Icon.sliders}
            </button>
            <button
              type="button"
              onClick={() => setActiveFilter(activeFilter === "calendar" ? null : "calendar")}
              title="Calendar & Date"
              className={`flex h-8 w-8 items-center justify-center rounded-[8px] transition-colors ${
                activeFilter === "calendar" ? "bg-[#ea580c] text-white" : "text-[#787774] hover:bg-[#fafaf9] hover:text-[#111111]"
              }`}
            >
              {Icon.calendar}
            </button>
            <button
              type="button"
              onClick={() => setActiveFilter(activeFilter === "split" ? null : "split")}
              title="Split View"
              className={`flex h-8 w-8 items-center justify-center rounded-[8px] transition-colors ${
                activeFilter === "split" ? "bg-[#ea580c] text-white" : "text-[#787774] hover:bg-[#fafaf9] hover:text-[#111111]"
              }`}
            >
              {Icon.split}
            </button>
            <button
              type="button"
              onClick={() => setActiveFilter(activeFilter === "compass" ? null : "compass")}
              title="Compass & Orientation"
              className={`flex h-8 w-8 items-center justify-center rounded-[8px] transition-colors ${
                activeFilter === "compass" ? "bg-[#ea580c] text-white" : "text-[#787774] hover:bg-[#fafaf9] hover:text-[#111111]"
              }`}
            >
              {Icon.compass}
            </button>
          </div>

          {/* Close Map view button */}
          {onClose && (
            <button
              type="button"
              onClick={onClose}
              title="Close map view"
              className="flex h-10 w-10 items-center justify-center rounded-[12px] bg-white text-[#787774] shadow-[0_2px_12px_rgba(0,0,0,0.04)] hover:text-[#ea580c] transition-colors"
            >
              {Icon.close}
            </button>
          )}
        </div>
      </div>

      {/* ---------------- Vector Cartography Map Base (Minimalist Two-Tone) ---------------- */}
      <div
        className="relative h-full w-full flex-1 transition-transform duration-200"
        style={{ transform: `scale(${zoom})`, transformOrigin: "center center" }}
      >
        <svg
          viewBox="0 0 1000 650"
          className="h-full w-full object-cover"
          preserveAspectRatio="none"
        >
          {/* Base Warm Land Fill */}
          <rect width="1000" height="650" fill="#fcfcfb" />

          {/* Soft Neutral-Water Bay Elements */}
          <path
            d="M 640 0 C 640 100, 630 180, 600 240 C 580 280, 560 320, 560 380 C 560 440, 500 480, 480 500 C 460 520, 400 520, 370 560 C 350 590, 360 630, 360 650 L 1000 650 L 1000 0 Z"
            fill="#eef2f3"
            opacity="0.95"
          />

          {/* Secondary river & estuaries */}
          <path
            d="M 600 240 C 650 250, 720 280, 750 330 C 760 350, 720 400, 720 430 C 720 480, 800 520, 840 550 C 900 600, 960 620, 1000 640 L 1000 0 Z"
            fill="#e5eced"
            opacity="0.8"
          />

          {/* Waterway channels */}
          <path
            d="M 440 370 C 470 380, 480 430, 470 460 C 450 490, 400 500, 370 550"
            fill="none"
            stroke="#d4dedf"
            strokeWidth="3"
            strokeDasharray="4,3"
          />

          {/* Road Grid lines (Clean subtle white/gray) */}
          <g stroke="#ffffff" strokeWidth="2.5" opacity="0.95">
            <line x1="0" y1="110" x2="600" y2="120" />
            <line x1="0" y1="210" x2="600" y2="230" />
            <line x1="0" y1="310" x2="580" y2="340" />
            <line x1="0" y1="420" x2="500" y2="440" />
            <line x1="0" y1="520" x2="400" y2="530" />

            <line x1="140" y1="0" x2="160" y2="650" />
            <line x1="280" y1="0" x2="310" y2="650" />
            <line x1="420" y1="0" x2="450" y2="550" />
            <line x1="520" y1="0" x2="550" y2="400" />
            <line x1="720" y1="0" x2="740" y2="350" />
            <line x1="880" y1="0" x2="890" y2="500" />
          </g>

          {/* Secondary thin street capillaries */}
          <g stroke="#f0efed" strokeWidth="1.2">
            <line x1="40" y1="60" x2="300" y2="60" />
            <line x1="80" y1="160" x2="400" y2="160" />
            <line x1="20" y1="260" x2="500" y2="270" />
            <line x1="50" y1="370" x2="480" y2="380" />
            <line x1="70" y1="480" x2="420" y2="490" />
            <line x1="220" y1="30" x2="230" y2="400" />
            <line x1="360" y1="20" x2="380" y2="500" />
          </g>

          {/* Two-Tone Solar Potential Cluster Zones (Warm Amber/Orange Tiers) */}
          {DEMO_ZONES.map((zone) => {
            const isSelected = activeZone?.id === zone.id;
            return (
              <g
                key={zone.id}
                onClick={() => handleZoneClick(zone)}
                className="cursor-pointer transition-opacity hover:opacity-90"
              >
                <polygon
                  points={zone.polygonPoints
                    .split(" ")
                    .map((p) => {
                      const [px, py] = p.split(",").map(Number);
                      return `${px * 10},${py * 6.5}`;
                    })
                    .join(" ")}
                  fill={zone.color}
                  stroke={zone.borderColor}
                  strokeWidth={isSelected ? "2.5" : "1"}
                  className="transition-all duration-200"
                />
              </g>
            );
          })}

          {/* City / Region Typography Labels */}
          <g
            fill="#262626"
            fontFamily="var(--font-sans, -apple-system, sans-serif)"
            fontWeight="600"
            fontSize="14"
            letterSpacing="-0.02em"
          >
            <text x="580" y="340" fontSize="22" fontWeight="700">
              New York
            </text>
            <text x="720" y="70" fontSize="18" fontWeight="600">
              Yonkers
            </text>
            <text x="830" y="75" fontSize="13" fill="#8c8c88">
              New Rochelle
            </text>
            <text x="420" y="325" fontSize="17" fontWeight="600">
              Newark
            </text>
            <text x="80" y="240" fontSize="15">
              Morristown
            </text>
            <text x="368" y="210" fontSize="13">
              Montclair
            </text>
            <text x="425" y="75" fontSize="13">
              Paterson
            </text>
            <text x="548" y="115" fontSize="13">
              Hackensack
            </text>
            <text x="445" y="145" fontSize="13">
              Clifton
            </text>
            <text x="648" y="175" fontSize="13">
              Fort Lee
            </text>
            <text x="560" y="240" fontSize="13">
              North Bergen
            </text>
            <text x="580" y="295" fontSize="13">
              Hoboken
            </text>
            <text x="328" y="375" fontSize="13">
              Union
            </text>
            <text x="380" y="420" fontSize="13">
              Elizabeth
            </text>
            <text x="488" y="415" fontSize="13">
              Bayonne
            </text>
            <text x="145" y="515" fontSize="14">
              Plainfield
            </text>
            <text x="270" y="540" fontSize="14">
              Woodbridge Township
            </text>
            <text x="175" y="620" fontSize="14">
              Edison
            </text>
            <text x="310" y="640" fontSize="14">
              Perth Amboy
            </text>
          </g>
        </svg>

        {/* ---------------- Two-Tone Circular Solar Pins ---------------- */}
        {DEMO_ZONES.map((zone) => {
          const isSelected = activeZone?.id === zone.id;
          return (
            <button
              key={`marker-${zone.id}`}
              type="button"
              onClick={() => handleZoneClick(zone)}
              style={{ top: `${zone.y}%`, left: `${zone.x}%` }}
              className={`group absolute -translate-x-1/2 -translate-y-1/2 cursor-pointer transition-transform duration-200 ${
                isSelected ? "scale-125 z-10" : "hover:scale-110 z-0"
              }`}
            >
              {/* Clean Two-Tone Solar Pin */}
              <span className="flex h-7 w-7 items-center justify-center rounded-full bg-white text-[#ea580c] shadow-[0_2px_8px_rgba(0,0,0,0.08)] ring-1 ring-[#ea580c]/30">
                <span className="flex h-4 w-4 items-center justify-center rounded-full bg-[#ea580c] text-white">
                  <span className="h-1.5 w-1.5 rounded-full bg-white" />
                </span>
              </span>

              {/* Tooltip on hover / selected */}
              <div
                className={`pointer-events-none absolute bottom-full left-1/2 mb-1.5 -translate-x-1/2 whitespace-nowrap rounded-[8px] bg-white px-2.5 py-1 text-left shadow-[0_4px_16px_rgba(0,0,0,0.08)] transition-all ${
                  isSelected ? "opacity-100 scale-100" : "opacity-0 scale-95 group-hover:opacity-100 group-hover:scale-100"
                }`}
              >
                <p className="text-[11px] font-semibold text-[#111111]">{zone.name}</p>
                <p className="text-[10px] text-[#787774]">
                  {zone.area} roof · <span className="font-semibold text-[#ea580c]">{zone.capacity}</span> · {zone.savings}
                </p>
              </div>
            </button>
          );
        })}
      </div>

      {/* ---------------- Bottom-Right Two-Tone Legend Card & Zoom ---------------- */}
      <div className="pointer-events-none absolute right-4 bottom-4 z-20 flex items-end gap-3">
        {/* Floating Priority Legend Card (Two-Tone, No Outlines) */}
        <div className="pointer-events-auto rounded-[12px] bg-white p-3 shadow-[0_4px_16px_rgba(0,0,0,0.05)]">
          <p className="text-[11px] font-semibold text-[#111111] uppercase tracking-wider">Solar Potential</p>
          <ul className="mt-2 grid gap-1.5 text-[11px] text-[#404040]">
            <li className="flex items-center gap-2">
              <span className="h-2 w-2 rounded-full bg-[#ea580c]" />
              <span>High (≥ 8.5 kWp)</span>
            </li>
            <li className="flex items-center gap-2">
              <span className="h-2 w-2 rounded-full bg-[#f59e0b]" />
              <span>Medium (5 – 8 kWp)</span>
            </li>
            <li className="flex items-center gap-2">
              <span className="h-2 w-2 rounded-full bg-[#fcd34d]" />
              <span>Low (&lt; 5 kWp)</span>
            </li>
            <li className="flex items-center gap-2">
              <span className="h-2 w-2 rounded-full bg-[#a3a3a3]" />
              <span>Review Required</span>
            </li>
          </ul>
        </div>

        {/* Floating Zoom Pill */}
        <div className="pointer-events-auto flex flex-col rounded-[10px] bg-white shadow-[0_4px_16px_rgba(0,0,0,0.05)]">
          <button
            type="button"
            onClick={handleZoomIn}
            className="flex h-8 w-8 items-center justify-center text-[#111111] hover:text-[#ea580c] transition-colors"
            title="Zoom In"
          >
            {Icon.plus}
          </button>
          <div className="h-[1px] w-full bg-[#f0f0ee]" />
          <button
            type="button"
            onClick={handleZoomOut}
            className="flex h-8 w-8 items-center justify-center text-[#111111] hover:text-[#ea580c] transition-colors"
            title="Zoom Out"
          >
            {Icon.minus}
          </button>
        </div>
      </div>
    </div>
  );
}
