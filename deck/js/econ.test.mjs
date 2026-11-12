// node js/econ.test.mjs
import assert from "node:assert/strict";
import { compute, range } from "./econ.js";

const r = compute();
assert.equal(Math.round(r.kwp * 10), 44);                       // 8 x 550 W
assert.equal(Math.round(r.grid), 813321);                       // 5400 kWh x 15.0615 x 10 years
for (const o of [r.solar, r.hybrid]) {
  assert.ok(o.upfront[0] < o.upfront[1] && o.total[0] < o.total[1], "low case is below high case");
  assert.ok(o.bills[0] <= o.bills[1] && o.bills[0] >= 0, "a bad weather year never costs less than a good one");
}
assert.ok(r.hybrid.upfront[0] > r.solar.upfront[1] - 1e5);      // a battery adds cost
console.log(range(r.solar.total), "|", range(r.hybrid.total), "| grid", Math.round(r.grid));
