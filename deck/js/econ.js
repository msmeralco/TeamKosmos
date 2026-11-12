// The 10-year comparison on slide 6. Every input sits here with its source, so the table can be checked and edited in one place.
// Illustrative: one household, a flat tariff, no upkeep. The live app runs the real hourly simulation.
export const IN = {
  loadKwhMonth: 450,                 // the illustrative household of slide 1
  retail: 15.0615,                   // Meralco typical household rate, Oct 2026 press release
  credit: 10.2005,                   // Meralco generation charge, Oct 2026 bill table; stands in for the export credit
  panels: 8, panelW: 550,            // 8 panels of 550 W, the layout on the roof in slide 4
  yieldKwhPerKwp: { bad: 1285, typical: 1349, good: 1429 }, // PVGIS-ERA5, Metro Manila 14.60N 120.98E, 2005-2020 worst, mean, best year; 14 deg tilt, south, 14% losses
  pricePerW: [45, 75],               // published installed range, 2026 (slide 2)
  battery: [89000, 155000],          // 10 kWh home battery list range, EcoFlow PH, before installation
  selfUse: { solar: 0.4, hybrid: 0.8 }, // ASSUMED: share of output used in the home as it is made
  years: 10,         // the user asked for 10 so the payback shows; no degradation, tariff growth or inverter swap is modelled
};

export function compute(i = IN) {
  const kwp = (i.panels * i.panelW) / 1000;
  const load = i.loadKwhMonth * 12;
  const bill = (self, yieldPerKwp) => {
    const made = kwp * yieldPerKwp, used = Math.min(self * made, load);
    return Math.max(0, (load - used) * i.retail - (made - used) * i.credit); // unused credit is not paid out
  };
  const up = (extra = 0) => i.pricePerW.map((p, k) => kwp * 1000 * p + (extra ? i.battery[k] : 0));
  const opt = (key, extra) => {
    const upfront = up(extra), best = bill(i.selfUse[key], i.yieldKwhPerKwp.good) * i.years, worst = bill(i.selfUse[key], i.yieldKwhPerKwp.bad) * i.years;
    return { upfront, bills: [best, worst], total: [upfront[0] + best, upfront[1] + worst] };
  };
  const grid = load * i.retail * i.years;
  return { kwp, grid, solar: opt("solar", 0), hybrid: opt("hybrid", 1) };
}

const k = (v) => "₱" + Math.round(v / 1000) + "k";
export const range = ([a, b]) => (Math.round(a / 1000) === Math.round(b / 1000) ? k(a) : `${k(a)} to ${k(b)}`);
export { k as pesoK };
