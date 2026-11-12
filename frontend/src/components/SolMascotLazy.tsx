import { lazy, Suspense } from "react";
import { SolMark } from "./SolMark";
import type { SolMascotProps } from "./SolMascot";

/* three.js is large; load it only when the animated mascot is actually shown. */
const SolMascot = lazy(() => import("./SolMascot"));

export function AnimatedSol({ size = 120, ...rest }: SolMascotProps) {
  return (
    <Suspense fallback={<SolMark size={size} className={rest.className} spinning={rest.loading} />}>
      <SolMascot size={size} {...rest} />
    </Suspense>
  );
}
