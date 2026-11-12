import { useId } from "react";

/* Static Sol brand mark: the same character as the animated <SolMascot />, drawn as SVG.
   Used in the navbar and as the fallback while the 3D mascot loads (or if WebGL is unavailable). */

const RAYS = Array.from({ length: 12 }, (_, i) => {
  const a = (i / 12) * Math.PI * 2;
  return { x: 50 + Math.sin(a) * 44.5, y: 50 - Math.cos(a) * 44.5 };
});

export function SolMark({ size = 32, className = "", spinning = false }: { size?: number; className?: string; spinning?: boolean }) {
  const uid = useId().replace(/:/g, "");
  const body = `sol-body-${uid}`;
  const ray = `sol-ray-${uid}`;
  const cheek = `sol-cheek-${uid}`;

  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 100 100"
      className={`shrink-0 ${className}`}
      role="img"
      aria-label="Sol"
    >
      <defs>
        <radialGradient id={body} cx="46%" cy="42%" r="62%">
          <stop offset="0" stopColor="#ffec8f" />
          <stop offset="0.6" stopColor="#fbd554" />
          <stop offset="1" stopColor="#f4b92f" />
        </radialGradient>
        <radialGradient id={ray} cx="42%" cy="38%" r="70%">
          <stop offset="0" stopColor="#fff3a8" />
          <stop offset="1" stopColor="#f8cf4e" />
        </radialGradient>
        <radialGradient id={cheek}>
          <stop offset="0" stopColor="#f0657c" stopOpacity="0.85" />
          <stop offset="1" stopColor="#f0657c" stopOpacity="0" />
        </radialGradient>
      </defs>

      {/* the rays turn around the centre when `spinning` (used as the loading indicator) */}
      <g className={spinning ? "sol-rays-spin" : undefined}>
        {RAYS.map((r, i) => (
          <circle key={i} cx={r.x} cy={r.y} r="4.6" fill={`url(#${ray})`} />
        ))}
      </g>

      <circle cx="50" cy="50" r="35.7" fill={`url(#${body})`} />

      <ellipse cx="33" cy="56" rx="7" ry="4.6" fill={`url(#${cheek})`} />
      <ellipse cx="67" cy="56" rx="7" ry="4.6" fill={`url(#${cheek})`} />

      <ellipse cx="34" cy="47" rx="5.2" ry="5.9" fill="#2b0e0a" />
      <ellipse cx="66" cy="47" rx="5.2" ry="5.9" fill="#2b0e0a" />
      <circle cx="32.4" cy="44.8" r="1.7" fill="#fff" />
      <circle cx="64.4" cy="44.8" r="1.7" fill="#fff" />
      <circle cx="35.8" cy="49.6" r="0.8" fill="#fff" />
      <circle cx="67.8" cy="49.6" r="0.8" fill="#fff" />

      <path
        d="M43 55.5 Q50 57 57 55.5 C56.5 62.5 53.5 65 50 65 C46.5 65 43.5 62.5 43 55.5 Z"
        fill="#4a1414"
      />
      <path d="M45.6 61.6 C47 59.6 53 59.6 54.4 61.6 C53.4 63.6 46.6 63.6 45.6 61.6 Z" fill="#ef6b7b" />
    </svg>
  );
}
