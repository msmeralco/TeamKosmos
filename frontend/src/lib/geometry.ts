/* Small 2D helpers shared by the map drawing tool and the sketch canvas. Points are [a, b] pairs in any
   consistent plane (lat/lng or canvas pixels); only relative geometry matters. */

export type Pt2 = [number, number];

/** True when segment a-b properly crosses segment c-d. */
export function segmentsCross(a: Pt2, b: Pt2, c: Pt2, d: Pt2): boolean {
  const orient = (p: Pt2, q: Pt2, r: Pt2) => (q[1] - p[1]) * (r[0] - q[0]) - (q[0] - p[0]) * (r[1] - q[1]);
  const o1 = orient(a, b, c);
  const o2 = orient(a, b, d);
  const o3 = orient(c, d, a);
  const o4 = orient(c, d, b);
  return o1 * o2 < 0 && o3 * o4 < 0;
}

/** Would adding `next` make the outline cross itself (including the closing side back to the first corner)? */
export function crossesItself(points: Pt2[], next: Pt2): boolean {
  const n = points.length;
  if (n < 2) return false;
  const last = points[n - 1];
  // New side (last -> next) against every earlier side except the one touching `last`.
  for (let i = 0; i < n - 2; i++) if (segmentsCross(points[i], points[i + 1], last, next)) return true;
  // Closing side (next -> first) against every side except the ones touching `next` or the first corner.
  for (let i = 1; i < n - 1; i++) if (segmentsCross(points[i], points[i + 1], next, points[0])) return true;
  return false;
}

/** Would closing the outline (last -> first) cross any other side? */
export function closingCrosses(points: Pt2[]): boolean {
  const n = points.length;
  if (n < 4) return false;
  const last = points[n - 1];
  const first = points[0];
  for (let i = 1; i < n - 2; i++) if (segmentsCross(points[i], points[i + 1], last, first)) return true;
  return false;
}

/** Does any side of the outline cross another non-adjacent side? `closed` adds the side from last to first. */
export function selfIntersects(points: Pt2[], closed: boolean): boolean {
  const n = points.length;
  const sides = closed ? n : n - 1;
  for (let i = 0; i < sides; i++) {
    for (let j = i + 1; j < sides; j++) {
      if (j === i + 1) continue; // neighbours share a corner
      if (closed && i === 0 && j === sides - 1) continue;
      if (segmentsCross(points[i], points[(i + 1) % n], points[j], points[(j + 1) % n])) return true;
    }
  }
  return false;
}
