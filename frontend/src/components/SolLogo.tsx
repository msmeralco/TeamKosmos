/* Sol brand logo (sun + wordmark). Source art: frontend/logo/Sol-testlogo.png,
   cropped to transparent PNG in /public/sol-logo.png (regenerate with logo/prep-logo.ps1). */

const SRC = `${import.meta.env.BASE_URL}sol-logo.png`;
const RATIO = 720 / 367; // width / height of the cropped artwork

export function SolLogo({ height = 32, className = "" }: { height?: number; className?: string }) {
  return (
    <img
      src={SRC}
      alt="Sol"
      width={Math.round(height * RATIO)}
      height={height}
      draggable={false}
      className={`block shrink-0 select-none ${className}`}
    />
  );
}
