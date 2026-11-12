import { LazyMotion, domAnimation, m } from "framer-motion";
import { Icon } from "./icons";

/**
 * Login3DPlaceholder
 *
 * Minimalist utilitarian placeholder viewport for 3D presentation / Spline / Three.js model.
 * Adheres strictly to /minimalist-ui (hairline #EAEAEA borders, warm bone #FAFAF9 canvas,
 * monospace metadata, muted pastel status tag) and /framer-motion (ambient float, transform only).
 *
 * When ready, swap the inner contents with your <Canvas /> or <Spline scene="..." />.
 */
export function Login3DPlaceholder({ className = "" }: { className?: string }) {
  return (
    <LazyMotion features={domAnimation}>
      <div
        className={`relative flex h-full w-full items-center justify-center overflow-hidden bg-[#FAFAF9] border-l border-[#EAEAEA] select-none ${className}`}
      >
        {/* ---------------- Isometric Technical Grid Background ---------------- */}
        <svg
          className="absolute inset-0 h-full w-full opacity-40 pointer-events-none"
          xmlns="http://www.w3.org/2000/svg"
        >
          <defs>
            <pattern
              id="iso-technical-grid"
              width="60"
              height="34.64"
              patternUnits="userSpaceOnUse"
              patternTransform="scale(1.2)"
            >
              <path
                d="M 60 0 L 0 0 30 17.32 Z M 30 17.32 L 60 34.64 0 34.64 Z"
                fill="none"
                stroke="#E5E5E4"
                strokeWidth="0.75"
              />
            </pattern>
          </defs>
          <rect width="100%" height="100%" fill="url(#iso-technical-grid)" />
        </svg>

        {/* Minimalist Top Status Bar */}
        <div className="absolute top-8 right-8 z-10 flex items-center gap-2">
          <span className="inline-flex items-center gap-1.5 rounded-full bg-[#EDF3EC] px-2.5 py-1 text-[11px] font-medium tracking-wide text-[#346538] border border-[#D5E5D4]">
            <span className="h-1.5 w-1.5 rounded-full bg-[#346538] animate-pulse" />
            3D Viewport Ready
          </span>
        </div>

        {/* ---------------- Centered 3D Slot Display with Ambient Float ---------------- */}
        <m.div
          animate={{ y: [0, -6, 0] }}
          transition={{ duration: 4.5, repeat: Infinity, ease: "easeInOut" }}
          className="relative z-10 flex flex-col items-center text-center p-8 max-w-[360px]"
        >
          {/* Isometric Cube Icon container */}
          <div className="relative flex h-16 w-16 items-center justify-center rounded-[12px] bg-white border border-[#EAEAEA] text-[#ea580c] shadow-[0_2px_8px_rgba(0,0,0,0.03)]">
            <span className="flex h-10 w-10 items-center justify-center text-[#ea580c]">
              {Icon.cube}
            </span>
            <span className="absolute -top-1 -right-1 flex h-2.5 w-2.5">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-[#ea580c] opacity-50" />
              <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-[#ea580c]" />
            </span>
          </div>

          <h3 className="mt-5 text-[15px] font-semibold tracking-tight text-[#111111]">
            3D Presentation Viewport
          </h3>
          <p className="mt-1.5 text-[12px] leading-relaxed text-[#787774]">
            Drop your Spline interactive presentation or Three.js solar model into this container.
          </p>

          {/* Technical component marker */}
          <div className="mt-5 flex items-center gap-2 rounded-[6px] bg-white px-3 py-1 text-[11px] font-mono text-[#787774] border border-[#EAEAEA] shadow-[0_1px_2px_rgba(0,0,0,0.02)]">
            <span className="h-1.5 w-1.5 rounded-full bg-[#ea580c]" />
            <span>&lt;Login3DPlaceholder /&gt;</span>
          </div>
        </m.div>

        {/* Minimalist Bottom Technical Metadata */}
        <div className="pointer-events-none absolute bottom-8 left-8 right-8 flex items-center justify-between text-[11px] font-mono text-[#A3A3A3]">
          <span>PERSPECTIVE: ISOMETRIC (30°, 45°)</span>
          <span>SOL 3D VIEWPORT · HACKATHON 2026</span>
        </div>
      </div>
    </LazyMotion>
  );
}
