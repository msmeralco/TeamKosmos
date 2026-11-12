# Sol: Your Clean Energy Partner. Implementation Plan

Team Kosmos, IDOL Hackathon 2026. Challenge declared: **1, Clean Energy Adoption and Rewards**.
All times are Philippine time (PHT). H0 = 9:00 AM, Nov 12. Code window closes H24 = 9:00 AM, Nov 13. Submission closes 9:30 AM.

Status tags used below: **[DECIDED]** agreed in planning, **[PROPOSED]** my default, not yet confirmed by the team, **[VERIFY]** a fact not yet checked.

---

## 1. Goal, scope and success criteria

### 1.1 One-sentence product
Sol is a conversational agent that takes a Meralco household's roof, bill, budget and goal, then returns sized solar options, a 10-year cost comparison with honest ranges, and a Solar Passport: proof of going solar that earns vouchers and discounts once an installer confirms the install.

### 1.1b Who it serves **[DECIDED]**
Build the customer chat agent first. Three groups benefit, and the deck has a slide for each (slide 9, "Who it helps"):

| Group | What they get | Built or pitch |
|---|---|---|
| **Customers** | An honest range instead of one number, what net metering really credits, answers to rule questions with source links (RAG), and a Passport that earns vouchers and discounts for going solar. | Built |
| **Business owners** (installers and sellers) | The customer arrives with a layout, a priced package and the assumptions in one place. They open the same `/passport/{id}` link as a quote brief, confirm the install, and redeem vouchers with a code. | Built as part of the Passport page, install confirmation and redeem route; no installer accounts or dashboard. Partner funding is pitch only. |
| **Meralco** | Better-prepared customers who know how exports are credited and which grid pathway applies (DOE DC2026-08-0017), and a Passport to point to when referring a customer to an accredited installer. | Pitch only. No integration, no referral feature, and **no promise of any Meralco benefit**. |

There are no separate pages for installers or Meralco. The Passport page is the shared surface.

### 1.2 In scope
- Roof input by address (OpenStreetMap outline autofill) and by drawing on a satellite map. Later: blank-canvas sketch with manual scale, photo/blueprint auto-outline.
- Household load estimate from monthly kWh or bill.
- Hourly solar simulation (PVGIS-ERA5 data) with optional battery.
- Net-metering-correct billing with on/off toggle and editable export credit.
- ROI table: grid-only vs on-grid solar vs hybrid. Every figure uses a **10-year** horizon (the same as the deck). Payback is shown only if it falls inside it.
- Budget- and goal-driven optimizer producing the top 2 or 3 parts lists.
- Live equipment price search with cache fallback and source/timestamp on every price.
- **Solar Passport:** the customer's proof of going solar. Sol issues it with the plan (inputs, assumptions, package, results) and signs it. A listed installer confirms the install, and the confirmed Passport unlocks vouchers and discounts. Three stages: plan, installed, redeemed.
- **Solar Rewards:** vouchers and discounts issued once the install is confirmed, from a small static catalog (section 7.11b). Each voucher is tied to one Passport and redeems once. Reward values are sample values until a partner funds them.
- A chat agent over all of the above, with a "show the math" drawer.
- **RAG grounding:** local corpus (SQLite + embeddings, keyword fallback) of Meralco tariff and net-metering pages, DOE DC2026-08-0017, and product pages. `search_docs` returns passages with source URLs. Facts and citations only, never calculations.

### 1.3 Out of scope
- Recognition tiers, points, leaderboards, cash payouts and any promise of Meralco benefits. Installer accounts, referrals and a pathway classifier are not built (pitch only). Vouchers are in scope as of Nov 12 (changed from the earlier decision to leave rewards out); a voucher is a signed code, not money. **[DECIDED]**
- Electrical engineering sign-off (string design, protection, permits). Everything is labeled an estimate for a licensed installer to confirm.
- Real customer data. All demo data is synthetic and labeled.
- Multi-plane roof modeling and detailed shading (Tier 3 or later).
- User accounts, payments, production deployment.

### 1.4 Success criteria mapped to judging

| Criterion (weight) | What must be true at the pitch |
|---|---|
| Innovation (30) | Roof input by address/draw/sketch; ranges not single numbers; goal-driven optimizer; a Passport that earns vouchers and discounts once an installer confirms the install. |
| Functionality (25) | Live demo on 3 prepared addresses runs end to end with no manual fixes. Works even if the LLM or scraper fails. |
| Impact (20) | Real Meralco tariff, correct net-metering treatment, plain-language outputs, a "Who it helps" slide for customers, business owners and Meralco; vouchers that reward going solar; RAG answers with source links. |
| Technical Challenge (15) | Hourly simulation over 16 weather years, battery dispatch, constrained optimizer, signed Passports with one-time vouchers, tool-calling agent with number guard. |
| Presentation (10) | Rehearsed 10-minute script, backup video, answers to the likely questions in section 13. |

---

## 2. Design principles

1. **The app works without the LLM.** Forms and buttons drive the same API the agent uses. The agent is a layer on top. If the free-tier model rate-limits or fails, the demo still runs.
2. **The LLM never does math.** It calls tools. Results render as cards from structured JSON. The model only writes short explanatory text, checked by a number guard (section 7.9).
3. **Every number has a source.** Inputs, assumptions and prices carry source URL and "as of" date.
4. **Contract first.** JSON schemas are agreed in the first hour so frontend and backend build in parallel against mocks.
5. **Fail soft, never blank.** Each external dependency (geocoder, Overpass, PVGIS, scraper, LLM) has a cached or manual fallback.
6. **Cut from the bottom.** Tiers are ranked. At each gate we cut the lowest unfinished tier item, not randomly.

---

## 3. Architecture

```
                         Browser (React + TypeScript + Leaflet)
        Address search | Roof editor (satellite) | Forms | Chat | Cards | Math drawer | Passport view
                                          |  HTTPS / SSE
                                          v
                              FastAPI backend (Python)
   +------------+  +-------------+  +-----------+  +-----------+  +------------+  +-----------+
   | geo/roof   |  | load        |  | solar     |  | billing & |  | optimizer  |  | passport  |
   | layout     |  | estimator   |  | engine    |  | finance   |  |            |  | signer    |
   +------------+  +-------------+  +-----------+  +-----------+  +------------+  +-----------+
   +----------------------+   +--------------------------+   +-------------------------------+
   | scraper pipeline     |   | agent (tool-calling loop)|   | SQLite: catalog, cache, ledger|
   +----------------------+   +--------------------------+   +-------------------------------+
        |            |                    |
   Retailer sites   Nominatim / Overpass / Esri tiles / PVGIS-ERA5 / NASA POWER     Gemini API
```

### 3.1 Stack **[PROPOSED]**

| Layer | Choice | Why |
|---|---|---|
| Backend | Python 3.11, FastAPI, Pydantic v2, uvicorn | Fast to build, typed contracts, team ML/data strengths. |
| Numerics | numpy, pandas, scipy, shapely, pyproj, pvlib (>= 0.10) | Standard tools for geometry and PV. Pin versions; the azimuth convention changed between pvlib releases. |
| Storage | SQLite | Zero setup, single file, enough for catalog, cache and ledger. |
| Scraping | httpx, selectolax or BeautifulSoup; Playwright only if forced (Tier 3) | Static pages first. |
| Crypto | `cryptography` (Ed25519) | Signs the Passport so vouchers can't be forged. No blockchain. |
| Frontend | Vite, React, TypeScript, Leaflet + Leaflet-Geoman (polygon editing), Recharts, qrcode.react | Fast, well documented, satellite tiles trivial. |
| LLM | Gemini free tier via Google GenAI SDK, a Flash-class model with function calling and image input **[VERIFY tonight which model supports both on your key]** | Already available to you. |
| Run mode | Everything on one laptop: FastAPI serves the built frontend. Phone hotspot as network backup. | Venue wifi risk. |

### 3.2 External services and fallbacks

| Service | Used for | Limits to respect | Fallback |
|---|---|---|---|
| Nominatim | Address to coordinates | Max 1 request/second, descriptive User-Agent, no autocomplete-style hammering | Pre-saved coordinates for demo addresses; manual map click |
| Overpass | Building outline | Public servers can be slow or busy | Pre-saved outlines (dataset prepared tonight); hand-draw |
| Esri World Imagery tiles | Satellite basemap | Attribution required | OpenStreetMap standard tiles |
| PVGIS-ERA5 (v5_3 endpoint, verified for Manila) | Hourly irradiance/PV output, 2005 to latest available year **[VERIFY end year]** | Reasonable request rate | Pre-downloaded files; NASA POWER; bundled Metro Manila typical-year |
| NASA POWER | Fallback irradiance | Public API | Bundled data |
| Gemini API | Chat, image reading, messy page extraction | Free-tier rate limits | Forms path; deterministic extractors |
| Retailer sites | Prices | robots.txt and terms, polite rate | Cached + seed catalog |

Note: PVGIS-SARAH3 does **not** cover Metro Manila (tested). Use `PVGIS-ERA5`.

---

## 4. Repository layout (created after 9:00 AM Nov 12)

```
sol/
  README.md                 run instructions, data disclosure, limitations
  ASSUMPTIONS.yaml          every numeric assumption with value, unit, source URL, as_of
  .env.example              GEMINI_API_KEY, PASSPORT_SIGNING_KEY path
  backend/
    app/
      main.py  config.py  db.py  models.py   (Pydantic contracts)
      routes/ geo.py roof.py load.py products.py optimize.py simulate.py passport.py rewards.py agent.py
      services/
        geo.py            Nominatim + Overpass clients, caching
        roof.py           projection, area, azimuth guess, usable polygon
        layout.py         panel packing inside polygon
        load.py           monthly kWh to hourly profile
        irradiance.py     PVGIS/NASA fetch, cache, scale to kWp
        dispatch.py       hourly PV/battery/grid loop
        billing.py        net-metering monthly bill model
        finance.py        cash flow, payback, NPV, IRR, LCOE
        optimizer.py      candidate search by goal
        scraper/          fetch.py extract.py validate.py sources.yaml
        passport.py       canonical JSON, Ed25519 signature, install confirmation
        rewards.py        voucher catalog, eligibility, issue, redeem
        agent/            tools.py prompt.py loop.py guard.py
        rag.py            chunk, embed, search_docs (SQLite, keyword fallback)
    data/
      docs_corpus/
      rewards.yaml    voucher catalog (sample values, partner label, rule)
      seed_catalog.csv  demo_outlines.geojson  pvgis_cache/  load_templates.json
    tests/
  frontend/
    src/ main.tsx api.ts mocks/ state/
      components/ MapPanel RoofEditor BillForm GoalForm ChatPanel PackageCards
                  RoiTable CashflowChart DayProfileChart LayoutView MathDrawer
                  ProductCard PassportView RewardCards
      pages/ Home Passport
  scripts/ demo_run.py (runs the three demo scenarios end to end)
  docs/ contracts.md demo-script.md backup-video-checklist.md
```

**Git rule:** the first commit must be made after 9:00 AM Nov 12. Creating an empty remote repository tonight is fine. Do not commit scaffolds, boilerplate or code before the window opens. The commit history is visible and the rule is about when source code is written.

---

## 5. Data contracts (agree in H0 to H1)

Types are written TypeScript-style for readability; implement as Pydantic models and mirror in `api.ts`.

```ts
type LatLon = { lat: number; lon: number };

type RoofModel = {
  id: string;
  source: "osm" | "drawn" | "sketch" | "photo";
  polygon_lonlat: [number, number][];      // GeoJSON ring, WGS84
  polygon_m: [number, number][];           // local metres (UTM 51N projection), origin at centroid
  area_m2: number;
  roof_type: "flat" | "single_slope" | "gable";
  tilt_deg: number;                        // panel plane tilt
  azimuth_deg: number;                     // 180 = south (pvlib convention)
  setback_m: number;                       // inset from edges
  usable_fraction: number;                 // after setback and obstruction allowance
  usable_polygon_m: [number, number][];
  confidence: "high" | "medium" | "low";   // low when drawn without scale check
  notes: string[];
};

type LoadProfile = {
  monthly_kwh: number[12];
  hourly_kw: number[8760];                 // typical year, local time, non-leap
  template: "night_heavy" | "balanced" | "day_heavy";
  basis: "bill" | "kwh_input" | "persona";
  is_estimate: true;
};

type Product = {
  id: string;
  category: "panel" | "inverter" | "battery";
  brand: string; model: string;
  price_php: number;
  watts?: number;                          // panel Wp
  dims_m?: [number, number];               // panel length, width
  efficiency_pct?: number;
  degradation_pct_per_year?: number;
  warranty_years?: number;
  inverter_ac_kw?: number; max_dc_kw?: number; hybrid?: boolean;
  battery_kwh?: number; battery_max_kw?: number; chemistry?: string; cycles?: number;
  embodied_carbon_kg?: number | null;      // null = "not disclosed"
  source_url: string; fetched_at: string;  // ISO 8601
  method: "seed" | "jsonld" | "selector" | "llm";
  confidence: number;                      // 0..1
  stale: boolean;
};

type Package = {
  id: string; label: "Best value" | "Max savings" | "Backup-ready" | string;
  panel: Product; panel_count: number;
  inverter: Product; battery: Product | null; battery_count: number;
  kwp: number; capex_php: number;
  capex_breakdown: { equipment: number; installation: number; permits_misc: number };
};

type ScenarioResult = {
  name: "pessimistic" | "expected" | "optimistic";
  year1_generation_kwh: number;
  year1_self_consumption_pct: number;
  year1_export_kwh: number;
  year1_savings_php: number;
  payback_years: number | null;
  net_profit_10y_php: number;
  npv_php: number; irr_pct: number | null; lcoe_php_per_kwh: number;
  cashflow_cumulative_php: number[26];     // index 0 = -capex
  co2_avoided_t_10y: number;
};

type RoiTable = {
  grid_only: { monthly_bill_php: number };
  on_grid: ScenarioSet; hybrid: ScenarioSet | null;
  net_metering_off: { on_grid: ScenarioSet; hybrid: ScenarioSet | null };  // toggle data
};
type ScenarioSet = { package_id: string; scenarios: ScenarioResult[3] };

type Passport = {
  id: string; created_at: string; model_version: string; // git commit
  inputs: { roof: RoofModel; load: LoadProfile; budget_php: [number, number]; goal: string };
  assumptions: { key: string; value: number | string; unit: string; source_url: string; as_of: string }[];
  package: Package; results: RoiTable;
  status: "plan" | "installed";          // installed = an installer confirmed the install
  installer: { label: string; confirmed_at: string } | null; // demo installers are synthetic
  rewards_eligible: string[];            // reward ids this record qualifies for, inside the signed body
  signature: string;                     // Ed25519 over the canonical body (status and installer included)
};

type Voucher = {
  code: string;                           // short code derived from the signature
  passport_id: string;                    // the voucher is tied to this Passport
  reward_id: string; title: string; value_label: string; // "sample value" until a partner funds it
  partner_label: string;                  // for example "Sample installer"; never a real company unless agreed
  status: "issued" | "redeemed";          // issued only after the install is confirmed
  issued_at: string; redeemed_at: string | null; signature: string;
};
```

### 5.1 API surface

| Method and path | Purpose | Returns |
|---|---|---|
| `GET /api/health` | Status of each dependency | JSON map |
| `POST /api/geocode` `{q}` | Address candidates | list of `{label, lat, lon}` |
| `POST /api/roof/from-address` `{lat, lon}` | Overpass lookup | `RoofModel` (source `osm`) or 404 |
| `POST /api/roof/finalize` `{polygon_lonlat, roof_type, tilt, azimuth, setback_m}` | Compute metres, usable area | `RoofModel` |
| `POST /api/load/estimate` `{monthly_kwh or bill_php, template}` | Hourly load | `LoadProfile` |
| `POST /api/products/search` `{categories, budget}` | Live fetch | SSE stream of `Product` and progress events |
| `GET /api/products` | Cached catalog | list |
| `POST /api/optimize` `{roof, load, budget, goal, params}` | Top packages | `Package[]` + per-package quick stats |
| `POST /api/simulate` `{package, roof, load, overrides}` | Full 3-scenario result | `RoiTable` |
| `POST /api/agent/chat` `{session_id, message, attachments}` | Agent turn | SSE: text deltas, tool events, UI cards |
| `POST /api/passport` `{sim_id}` | Issue the Passport (status `plan`) | `Passport` |
| `POST /api/passport/{id}/confirm-install` `{installer_code}` | Demo installer confirms the install; status becomes `installed` and vouchers are issued | `Passport` |
| `GET /api/passport/{id}` and `GET /passport/{id}` | Fetch the Passport (JSON and shareable page) | `Passport` |
| `GET /api/rewards/{passport_id}` | Vouchers for a Passport | `Voucher[]` (empty until installed) |
| `POST /api/rewards/redeem` `{code}` | Mark one voucher redeemed (once only) | `Voucher` or error |
| `GET /api/assumptions` | Show every assumption | list |

---

## 6. Assumptions register (fill tonight)

Each row lives in `ASSUMPTIONS.yaml` with `value, unit, source_url, as_of`. Copy values into the file after 9:00 AM; research and spreadsheet work tonight is planning.

| Key | Meaning | Default / how to set | Source needed |
|---|---|---|---|
| `tariff_php_per_kwh` | All-in residential rate | Latest Meralco typical-household overall rate (Oct 2026 release gave about 15.06; refresh at kickoff) | Meralco monthly rate release |
| `tariff_fixed_php_month` | Non-offsettable monthly charge | Read from a typical-consumption bill table | Meralco published bill tables |
| `export_credit_php_per_kwh` | Net-metering credit | Latest Meralco generation charge as approximation of "monthly blended generation cost" | Meralco rate release **[VERIFY exact method]** |
| `tariff_growth_pct` | Yearly tariff escalation | 0 / 3 / 5 for pessimistic / expected / optimistic | Historical Meralco rate series (justify) |
| `export_credit_growth_pct` | Credit escalation | Same as tariff growth in expected; 0 in pessimistic | Judgement, disclosed |
| `degradation_pct_per_year` | Panel degradation | From catalog; default 0.5 | Datasheet |
| `system_losses_pct` | Wiring, soiling, mismatch, etc. | 14 (PVGIS default order of magnitude) | PVGIS docs |
| `inverter_efficiency_pct` | DC to AC | From datasheet; default 97 | Datasheet |
| `dc_ac_ratio_range` | Allowed array/inverter ratio | 1.0 to 1.4 | Common practice, disclosed |
| `battery_round_trip_eff_pct` | Charge/discharge efficiency | 90 | Datasheet |
| `battery_usable_dod_pct` | Usable depth of discharge | 90 | Datasheet |
| `battery_life_years` | Replacement timing | 12 | Datasheet cycles / 365 |
| `inverter_life_years` | Replacement timing | 12 | Datasheet |
| `inverter_replacement_pct_of_price` | Replacement cost | 100 | Judgement, disclosed |
| `om_pct_of_capex_per_year` | Maintenance | 1.0 | Industry norm, disclosed |
| `install_cost_php_per_kw` | Labor and BOS | From at least 3 public installer quotes | Quotes, URLs |
| `permits_misc_php` | Permits, net-metering application | From public LGU/DU info or flat estimate | Public sources |
| `discount_rate_pct` | For NPV and LCOE | 8 | Judgement, disclosed |
| `setback_m` | Edge inset on roof | 0.5 | Common practice, disclosed |
| `usable_fraction_obstruction` | Allowance for vents, water tanks | 0.9 on top of setback | Judgement, disclosed |
| `default_tilt_flat_deg` | Rack tilt on flat roofs | 12 (about Manila latitude) | Solar geometry |
| `default_tilt_pitched_deg` | Pitched roof | 20 unless user sets | Judgement |
| `grid_emission_factor_kg_per_kwh` | CO2 avoided | DOE National Grid Emission Factor, latest | DOE publication **[VERIFY]** |
| `net_metering_cap_kw` | Residential cap | 100 | Meralco net-metering page |

---

## 7. Module specifications

### 7.1 Geocoding and roof lookup (`services/geo.py`, `routes/geo.py`, `routes/roof.py`)

1. `POST /api/geocode`: call Nominatim with `countrycodes=ph`, limit 5, User-Agent `Sol-Hackathon/1.0 (contact email)`. Cache by query for 24 hours. Rate-limit client to 1 request per second.
2. `POST /api/roof/from-address`: Overpass query:
   `[out:json][timeout:15]; way(around:25,{lat},{lon})["building"]; out geom;`
   Choose the way that contains the point; otherwise the nearest centroid. Convert to polygon.
3. Failure behavior: timeout (8 s), no way found, or invalid geometry returns 404 with a hint. The UI then switches to "draw your roof" mode centered on the geocoded point.
4. Demo addresses are looked up from `demo_outlines.geojson` first, before the network call.

### 7.2 Roof model and projection (`services/roof.py`)

1. Project polygon to UTM zone 51N (`EPSG:32651`) with pyproj. Translate so the centroid is the origin. Use Shapely for area.
2. Validate: simple polygon, area between 8 and 1500 m². Otherwise warn and set `confidence = "low"`.
3. **Azimuth guess:** compute the minimum rotated rectangle. The long axis defines the ridge direction for gable roofs. The roof plane faces perpendicular to the long axis. Choose the perpendicular direction closest to south (180°).
4. **Tilt and azimuth by roof type:**
   - `flat`: racks tilted at `default_tilt_flat_deg`, azimuth 180. Row spacing accounted by a fixed 0.3 m gap between rows.
   - `single_slope`: azimuth from step 3, tilt from user (default 20).
   - `gable`: single-plane approximation: use the south-leaning slope, half the footprint area.
   - `shortcut: one plane per roof, upgrade to multi-plane when time allows`.
5. **Usable polygon:** `polygon.buffer(-setback_m)` then multiply allowed area by `usable_fraction_obstruction` when reporting capacity (the packing step uses the geometry; the factor is applied as a cap on panel count).
6. User always sees the editable outline over the satellite view with area and "assumed direction" displayed, and can override tilt, azimuth and roof type.

### 7.3 Panel layout (`services/layout.py`)

Input: usable polygon, panel dimensions `(L, W)` from the chosen catalog panel.
Algorithm (greedy grid in the roof's principal frame):
1. Rotate the usable polygon so its long axis aligns to X (minimum rotated rectangle angle).
2. For orientation in {portrait, landscape}: lay a grid of rectangles with 0.02 m panel spacing and 0.3 m row spacing (flat roofs), starting at the bounding-box corner. Keep rectangles fully contained in the polygon (`polygon.contains(rect)`).
3. Try 4 grid offsets (0 and half-pitch in X and Y) and keep the arrangement with the most panels.
4. Return panel rectangles in metres, rotated back, and count. Cap at `floor(count * usable_fraction_obstruction)`.
5. Output also converts panels to lon/lat for overlay on the map (inverse projection).
Complexity is trivial (hundreds of rectangles). `shortcut: greedy grid, upgrade to row-optimized packing if needed`.

### 7.4 Load estimation (`services/load.py`)

1. Inputs: `monthly_kwh` (direct) or `bill_php` (convert: `(bill - fixed) / tariff`).
2. Monthly distribution: base monthly kWh with seasonal multipliers (hotter months higher; default multipliers stored in `load_templates.json`, labeled as assumptions).
3. Hourly shape: three templates (24-value weekday and weekend shapes each), normalized to sum to monthly kWh:
   - `night_heavy`: evening peak, low daytime (out-of-home during day).
   - `balanced`: morning and evening peaks, moderate daytime.
   - `day_heavy`: work-from-home with daytime air-conditioning.
4. Add small deterministic noise (seeded) so profiles are not perfectly smooth. Always flagged `is_estimate: true`.
5. Output 8760 hourly kW for a non-leap year, aligned with PVGIS timestamps (convert PVGIS UTC to PHT, UTC+8, before matching).
Demo personas (synthetic): "Ate Maria" 250 kWh/month night-heavy, "Reyes Family" 450 kWh balanced, "WFH Couple" 700 kWh day-heavy.

### 7.5 Solar engine (`services/irradiance.py`, `services/dispatch.py`)

**Fetching:** call PVGIS through `pvlib.iotools.get_pvgis_hourly` with `raddatabase="PVGIS-ERA5"`, `pvcalculation=True`, `peakpower=1.0`, `loss=system_losses_pct`, `surface_tilt`, `surface_azimuth` (check the convention for the installed pvlib; 180 = south in recent versions), `start=2005`, `end=<latest available>`, and pass `url` for the v5_3 endpoint if the default fails. Result column `P` is watts per 1 kWp, hourly.
- Key insight: output scales linearly with kWp, so fetch **once per (lat, lon, tilt, azimuth)** and multiply by system kWp. Cache to `pvgis_cache/{hash}.parquet`.
- Split by calendar year: get N year-series of 8760 values (drop Feb 29).
- Derive yearly yield (kWh/kWp) for each year; select **median year** and **low-decile year** (P10) and **high-decile year** (P90).
- Fallback chain: cache hit, PVGIS live, bundled pre-downloaded file for nearest demo location, NASA POWER (then pvlib model), bundled Metro Manila typical year labeled "approximate".

**Inverter model:** `pv_ac = min(pv_dc * inverter_efficiency, inverter_ac_kw)`. DC input also limited by `max_dc_kw`.

**Dispatch loop (hourly, per year):**
```
for each hour t:
  direct = min(pv_ac[t], load[t])
  surplus = pv_ac[t] - direct          # available to charge or export
  deficit = load[t] - direct           # must come from battery or grid
  if battery:
     charge   = min(surplus, (cap - soc)/eff_c, max_charge_kw);   soc += charge*eff_c;  surplus -= charge
     discharge= min(deficit, (soc - soc_min)*eff_d, max_discharge_kw); soc -= discharge/eff_d; deficit -= discharge
  export[t] = surplus ; import[t] = deficit
```
Vectorize across years where no battery. With a battery, loop in Python for the final top packages; use `numba.njit` for optimizer speed if installed.

**Outputs per year:** monthly import kWh, monthly export kWh, generation, self-consumption share, battery throughput.

### 7.6 Billing and net metering (`services/billing.py`)

Monthly, year-by-year:
```
r_y = tariff * (1+g)^(y-1)        e_y = export_credit * (1+g_e)^(y-1)
baseline_bill[m] = fixed + load_kwh[m] * r_y
with solar and net metering ON:
   credit_available = bank[m-1] + export_kwh[m] * e_y
   energy_charge    = import_kwh[m] * r_y
   applied          = min(credit_available, energy_charge)
   bill[m]          = fixed + energy_charge - applied
   bank[m]          = credit_available - applied      # banked, no cash payout
with net metering OFF: export credit = 0
```
Assumptions disclosed in the UI: the credit is modeled as offsetting energy charges only; fixed charges are not offset; credits are banked month to month with no cash-out (matches the program description). `[VERIFY]` the exact method with the Meralco net-metering page and a bill example.

Cap check: system AC size above `net_metering_cap_kw` is rejected by the optimizer.

### 7.7 Finance (`services/finance.py`)

Per scenario, over the model horizon (`analysis_years`; users see the first 10 years):
- Yearly generation = year-1 generation × `(1 - degradation)^(y-1)`.
- Savings_y = baseline_bill_y − solar_bill_y.
- Costs: O&M = `om_pct * capex` each year; inverter replacement at `inverter_life_years` (cost `pct * inverter_price`); battery replacement at `battery_life_years`.
- Net cash flow_y = savings_y − O&M_y − replacements_y. Cumulative starts at `-capex`.
- **Payback:** first year cumulative ≥ 0, linearly interpolated; `null` if not within the model horizon; shown to users only when it falls within 10 years.
- **NPV:** at `discount_rate_pct`. **IRR:** `scipy.optimize.brentq` on NPV(r); `null` if no sign change.
- **LCOE:** `(capex + PV(O&M + replacements)) / PV(generation)`.
- **CO2 avoided:** total kWh generated times `grid_emission_factor_kg_per_kwh` / 1000, in tonnes.

**Scenario definitions (documented in UI):**

| Scenario | Weather year | Tariff growth | Export credit growth |
|---|---|---|---|
| Pessimistic | Low-decile yield year | 0% | 0% |
| Expected | Median year | 3% | 3% |
| Optimistic | High-decile yield year | 5% | 5% |

### 7.8 Optimizer (`services/optimizer.py`)

**Decision variables:** panel product `p`, panel count `n` (1 to max layout capacity), inverter `i` (auto-picked: smallest catalog inverter with AC kW such that `DC/AC` within range and `max_dc_kw` ok), battery `b` in {none} ∪ catalog, battery count in {1, 2, 3}.

**Hard constraints:** `capex <= budget_max`, `n <= layout capacity`, AC kW <= cap, for a backup goal: `usable battery kWh >= essential_load_kw * backup_hours` (defaults 0.6 kW and 4 h, editable).

**Search:** enumerate `n` in steps of 2 for each panel model and battery option (a few hundred candidates). Evaluate each candidate with only the **median and low-decile years**, expected tariff growth. Then refine around the best 5 by evaluating `n ± 1`.

**Objective by goal:**
| Goal | Objective |
|---|---|
| Cut bill by X% | Minimize capex among candidates with first-year bill reduction ≥ X% |
| Maximize 10-year savings | Maximize 10-year cumulative net cash flow |
| Fastest payback | Minimize payback years (tie-break: higher 10-year profit) |
| Blackout backup | Minimize capex among candidates meeting the backup constraint; tie-break on savings |

**Output:** the best candidate labeled by goal, plus up to two diverse alternatives (for example, with and without battery). Then run the full 16-year, 3-scenario simulation only on those 2 or 3 finalists.

### 7.9 Scraper (`services/scraper/`)

1. `sources.yaml`: for each of 3 to 5 shortlisted sites: base URL, listing/search URL pattern per category, selectors (if used), robots.txt status, date checked, notes. Sites chosen tonight by hand for static HTML and permissive terms.
2. **Fetch** (`fetch.py`): `httpx.AsyncClient`, identifying User-Agent, respects robots.txt, 1 to 2 requests/second per site, 8 s timeout, 1 retry, concurrent across sites. Stores raw HTML hash for dedupe.
3. **Extract** (`extract.py`), in order: (a) JSON-LD `Product` schema.org data, (b) CSS selectors from `sources.yaml`, (c) LLM extraction with strict JSON schema (only when a/b fail, one call per page, truncated text). Each returns `method` and `confidence`.
4. **Validate** (`validate.py`): reject if price outside category range (for example, a 300 to 700 W panel priced outside a sane ₱/W window), watts missing for panels, or duplicate model. Normalize currency to PHP and compute ₱/W or ₱/kWh.
5. **Store:** SQLite `products` table with `source_url`, `fetched_at`, `method`, `confidence`. TTL for "fresh" is 24 hours; older rows are flagged `stale`.
6. **Progress:** `/api/products/search` streams SSE events (`source_started`, `product_found`, `source_failed`, `done`) so the UI shows a live feed during the demo.
7. **Fallback:** if a source fails or returns nothing, serve its cached rows with a "cached, last checked ..." chip. The seed catalog (hand-collected tonight) is loaded at startup with `method: "seed"`.
8. UI always shows: "Suggested prices from public listings. Confirm with the seller."

### 7.10 Agent (`services/agent/`)

**Tools** (all deterministic, thin wrappers over the services above):
`geocode_address`, `get_building_outline`, `set_roof_polygon`, `estimate_load`, `search_products`, `optimize_system`, `simulate_system`, `compare_net_metering`, `explain_assumptions`, `search_docs` (RAG: passages with source links, facts only), `issue_passport` (also returns the Passport's vouchers).

**State (session):** `roof`, `load`, `budget`, `goal`, `packages`, `sim_id`. The agent asks for any missing slot, one question at a time, and accepts image attachments (roof photo, bill photo) for the vision step.

**Loop:** user message → model with tool declarations → execute tool calls (max 4 per turn) → tool results to model → final text. Streaming text and tool events to the UI via SSE. Tool results that carry UI payload (packages, ROI table, layout, passport) are sent to the frontend as **cards**, independent of the model's text.

**System prompt rules** (short, to save tokens): you are Sol; never compute or invent numbers; call tools; quote values only from tool results; always mention estimates and the installer-confirmation note; reply in the user's language (English or Taglish).

**Number guard (`guard.py`)**: extract numeric tokens from the model's final text; each must match (after rounding) a value in this turn's tool results or in the user's message. If any fails, replace the text with a template summary generated from the cards. Log the event. `Tier 2`.

**Vision:** photo/blueprint to a draft outline (Tier 3): crop the satellite tile or accept an upload, ask the model for a polygon in normalized image coordinates plus a "visible scale reference" field, show it over the image for the user to correct. Scale always comes from the map or a user-entered measured dimension, never from the model.

**Rate-limit handling:** one retry with backoff; on repeated 429, the chat shows "Sol is busy, use the form" and the forms path keeps working. Cache identical (prompt, tool-results) pairs for 10 minutes. Keep the free model for conversation and extraction only.

### 7.11 Solar Passport (`services/passport.py`)

The Passport is the customer's proof of going solar, in three stages.

1. **Plan:** `issue_passport` builds the body (inputs, assumptions with sources, package, results) with `status: "plan"`, canonicalizes it (sorted keys, no whitespace, UTF-8, fixed float precision), signs it with Ed25519 (key generated at first run, private key excluded from git), and stores it in SQLite. A QR code encodes `/passport/{id}`.
2. **Installed:** `confirm-install` takes a demo installer code (from `data/installers.yaml`, synthetic and labeled), sets `status: "installed"` and `installer`, re-signs the body, and issues the vouchers. In the demo the code is typed by the presenter. A real flow would have a listed installer, or Meralco after net-metering approval, confirm it. That is a next step.
3. **Redeemed:** a business redeems a voucher with its code (section 7.11b).
4. **Passport page `/passport/{id}`:** the layout, ROI, assumptions with sources, status badge, installer label, vouchers. An installer can open it as a quote brief.
5. Disclosure printed on every Passport: demo data is synthetic, every result is an estimate for a licensed installer to confirm, and Sol cannot verify the household's real roof or usage.

### 7.11b Solar Rewards (`services/rewards.py`, `data/rewards.yaml`)

Vouchers and discounts reward going solar and give the Passport a purpose. Small by design.

1. **Catalog** (`rewards.yaml`, static): each entry has `id`, `title`, `value_label`, `partner_label`, `rule`, `stage`. All values are labeled "sample" and partner names are generic ("Sample installer", "Sample appliance store") until a real partner agrees. Starter set:
   - `site_survey`: a free site survey from a listed installer. Rule: any Passport.
   - `install_offer`: an installer discount on the package Sol recommended. Rule: the package fits the budget.
   - `usage_reward`: a reward once real generation is reported. Stage: **next step**. Shown locked in the demo.
2. **Eligibility** is computed from the Passport inputs by rules in code, and the eligible ids go inside the signed body (`rewards_eligible`).
3. **Issue:** vouchers are created when the install is confirmed, one per eligible, non-locked reward: `code = base32(first 8 bytes of Ed25519 signature over passport_id || reward_id)`, `status: issued`. Before that, `GET /api/rewards/{id}` returns an empty list.
4. **Redeem:** `POST /api/rewards/redeem {code}` checks the Passport is `installed` and its signature is valid, then marks the voucher `redeemed` once. A second try returns an error.
5. **Later (not built):** a monthly generation reading from a REC meter unlocks `usage_reward`. Partner funding and Meralco-backed incentives need agreements; Sol promises none.
6. Disclosure on every voucher: sample value, no cash value, not an offer from Meralco.

### 7.12 Frontend (`frontend/`)

**Layout:** two panes on desktop, tabs on mobile. Left: map and forms. Right: chat and result cards. Math drawer slides from the bottom.

**Screens and components:**
1. **Roof step:** `MapPanel` (Leaflet, Esri imagery, attribution), address search box, `RoofEditor` using Leaflet-Geoman to edit/draw a polygon; shows area, assumed direction arrow, roof-type selector, tilt and azimuth sliders, "usable area" overlay. Tier 2: `Sketch canvas` tab with manual scale input.
2. **Household step:** monthly kWh or bill field, household template (3 cards), budget range slider, goal selector (4 cards). Demo persona buttons prefill.
3. **Results:** `PackageCards` (2 or 3, each with capex, kWp, payback range, 10-year profit range), `RoiTable` with net-metering toggle and editable export rate, `CashflowChart` (three scenario lines with shaded band), `DayProfileChart` (typical day: load, solar, battery, grid), `LayoutView` (panels overlaid on the roof map).
4. **Products:** `ProductCard` with brand, model, ₱, ₱/W, efficiency, degradation, warranty, embodied carbon or "not disclosed", source link, freshness chip (live, cached), confidence dot. Live feed list while scraping.
5. **Math drawer:** formulas, inputs, assumptions with source links, scenario definitions, data sources (PVGIS-ERA5 modeled estimate), and the disclaimer.
6. **Passport and rewards:** `PassportView` with QR, status badge (plan or installed), installer label, link to `/passport/{id}`, "Download JSON", and a "Confirm install" box for the demo installer code. `RewardCards` shows each voucher (title, sample value, code, status, locked ones greyed) and a redeem box.
7. **Chat:** `ChatPanel` with streaming text, tool-activity chips ("fetching roof outline...", "simulating 16 weather years..."), quick-reply buttons, image upload.
8. **Offline/mock mode:** `?mock=1` runs against `src/mocks/*.json` for UI work and as a last-resort demo.

**Quality:** mobile-first, keyboard-navigable forms, color contrast AA, loading and error states for every async step, units always shown (₱, kWh, kWp, %).
**3D (Tier 3):** three.js extrusion of the usable polygon with panel boxes and a sun-path animation, reusing the same layout data.

---

## 8. Test plan (small, targeted)

Per the "no untested non-trivial logic" rule, a handful of tests, run before each gate:

| Test | What it proves | How |
|---|---|---|
| `test_billing.py` | Net-metering banking | Hand-calculated 3-month example with known imports, exports, rates; assert bills and bank balances to the centavo. |
| `test_finance.py` | Payback, NPV, LCOE | Constant cash flow case with a known closed-form payback and NPV. |
| `test_layout.py` | Panel packing | Rectangle roof 10 m × 6 m, 2.28 × 1.13 m panels: assert count within the expected range and no panel outside the polygon. |
| `test_dispatch.py` | Energy balance | For random inputs: `generation = direct + charge_in + export` and `load = direct + discharge + import` each hour. |
| `test_passport.py` | Signing | Round trip verifies; changing one byte of the body fails the signature; confirming the install changes status and re-signs. |
| `test_rewards.py` | Vouchers | No vouchers before install is confirmed; a voucher redeems once; a second redeem fails; `rewards_eligible` is inside the signed body. |

---

## 9. Timeline (H0 = 9:00 AM Nov 12) **[PROPOSED]**

### 9.1 Schedule

| PHT | Hour | Work | Gate |
|---|---|---|---|
| 7:30 to 8:15 | before | Register, school IDs, choose **Challenge 1**, settle seats and power. Ask a coach about the submission channel for the repo link, and about pretrained/third-party assets. | |
| 9:00 to 10:00 | H0 to H1 | Kickoff. Create repo, first commit. Finalize contracts (section 5) as Pydantic models and mock JSON. Environment setup. Everyone starts on their branch. | Contracts merged |
| 10:00 to 13:00 | H1 to H4 | Irradiance fetch and cache, load estimator, dispatch (no battery), billing. FastAPI skeleton, geocode and Overpass routes with demo-outline fallback, SQLite, seed catalog loader. Map with address search and polygon editing, bill and goal forms against mocks. `ASSUMPTIONS.yaml`, three personas, hand-calculated expected results for tests. | Roof from address works |
| 13:00 to 17:00 | H4 to H8 | Finance and three-scenario output, battery dispatch. Roof finalize and layout endpoint, `/simulate`, `/optimize` stub, agent tool wrappers. ROI table, cash-flow chart, day-profile chart wired to the real API. QA of numbers against hand calculations, README skeleton, pitch outline. Stagger meals. | Forms path end to end |
| 17:00 to 23:00 | H8 to H14 | Agent loop with tools, Gemini integration, streaming. Chat route, SSE, tests. Chat UI, package cards, math drawer. Rehearse agent flows, log bad answers, refine prompts. | **Gate G1 (23:00):** Tier 1 works on all 3 demo addresses; record a rough backup video now. |
| 23:00 to 5:00 | H14 to H20 | Tier 2: optimizer by goal; scraper pipeline and live feed; Passport, install confirmation and vouchers; layout overlay, product cards with freshness chips, sketch canvas; product-source QA, Passport copy, draft slides. Sleep blocks of about 3 hours, staggered, in the designated area only; quiet hours are 12 AM to 6 AM, so no calls at the table. | **Gate G2 (5:00):** Tier 2 works or the cut list is applied. |
| 6:00 | H21 | **Feature freeze.** Only bug fixes after this. | |
| 6:00 to 8:00 | H21 to H23 | Bug fixes, `demo_run.py` green, refresh cache, README final, record **final backup video**, rehearse the pitch twice with a timer. | |
| 8:30 | H23.5 | Tag release, push to GitHub, submit repo link through the organizers' channel. Verify the link opens from another account. | |
| 9:00 | H24 | **Code window closes.** No further commits. | |
| before 9:30 | | Final submission confirmation. Deadline is firm; late submissions are not accepted. | |

### 9.2 Cut list (applied at gates, in order)
1. 3D view (never started unless everything else is green)
2. Photo/blueprint auto-outline
3. Battery polish (keep simple battery, drop optimizer variants)
4. Blank-canvas sketch
5. Number guard (fall back to cards-only text)
6. Live scraping (fall back to cache and seed catalog, labeled as such)
7. Layout overlay (keep panel count only)
Never cut: address/draw roof input, simulation, ROI table with ranges, Passport.

---

## 10. Risk register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Free-tier LLM rate limit mid-demo | Medium | High | Forms path works without LLM; cache; backup video |
| Venue wifi fails | Medium | High | Run locally; phone hotspot; pre-downloaded PVGIS; cached outlines; backup video |
| Overpass/Nominatim slow or down | Medium | Medium | Demo outlines preloaded; draw mode |
| PVGIS slow or rate limited | Low | High | Cache by orientation; pre-downloaded files; NASA fallback |
| Scraped prices wrong or missing | High | Medium | Validation ranges; confidence; seed catalog; "confirm with seller" |
| Scraping blocked or terms issue | Medium | Medium | Only shortlisted static sites, polite rates, robots.txt respected |
| Numbers disputed by judges | Medium | High | Math drawer, sources, scenario ranges, hand-calculated tests |
| Net-metering credit method misunderstood | Medium | High | Editable credit, sensitivity row, disclosed approximation |
| Vouchers read as a real offer or a Meralco promise | Medium | High | Every voucher says "sample value"; generic partner names; Q&A answer ready; no Meralco logo or claim |
| Scope creep | High | High | Tier gates and cut list |
| Integration breakage late | Medium | High | Contract-first, daily `demo_run.py`, freeze at 6:00 |
| Team exhaustion | High | Medium | Staggered sleep, meals, no all-nighters for the same person on the same critical path |
| Rule violation (code before window, asset use) | Low | Critical | First commit after 9:00; no copied code; ask coach about any extra asset |
| Submission channel unclear | Medium | Critical | Ask a coach at 8:15 AM; submit by 8:30 AM next day, not 9:25 |

---

## 11. Demo script (10 minutes) **[PROPOSED]**

1. **0:00 to 1:00, hook and problem.** Rate up 16% since January, the 450 kWh household, then two gaps: solar options are hard to compare, and hard to understand. Three short slides, each with a source line.
2. **1:00 to 2:45, Sol.** Introduce Sol. Type an address (prepared). Satellite map shows the roof outline; adjust one corner.
3. **2:45 to 5:00, ask and answer.** Chat: bill amount, budget, goal. Sol fetches products live (feed visible), optimizes, shows 3 packages.
4. **5:00 to 6:45, compare.** ROI table: grid-only vs on-grid vs hybrid over 10 years. Flip the net-metering toggle. Show best-case and bad-year range, then payback within 10 years.
5. **6:45 to 7:45, show the math and the sources.** Open the drawer: sources, assumptions, export credit approximation, scenario definitions. Ask Sol one rule question (for example how exports are credited) and show the RAG answer with its source link. This is the "verifiable" moment.
6. **7:45 to 9:00, Passport and rewards.** Issue the Passport and show its QR. Enter the demo installer code to confirm the install; the status flips to installed and the vouchers appear. Redeem one with its code. Say the programme is our proposal.
7. **9:00 to 9:35, who it helps.** Deck slide: customers, business owners, Meralco. Say which parts are built and which are our pitch.
8. **9:35 to 10:00, close.** "Compare honestly. Understand clearly. Go solar, get rewarded."
9. **Q&A (5 min).** See section 13.

Backup: if live fails at any point, say so and switch to the recorded video at the same step. Keep the video chaptered by the same steps.

---

## 12. Tonight's preparation (no code)

Planning, installs and data gathering are allowed before the window. Writing code, prompts committed to a repo, or generating scaffolds is not.

**Accounts and tools**
- [ ] Create a Google AI Studio key. Make one manual test call that includes an image and a function call. Note which free model works.
- [ ] Install Python 3.11, Node, git, and the editors. Test that packages download over a hotspot.
- [ ] Create an **empty** GitHub repository (no commits). Add all four teammates.
- [ ] Charge laptops; bring extension cords, a phone hotspot, tumbler, medicines, extra clothes. No single-use plastics.

**Data (datasets, allowed in advance)**
- [ ] Pick 3 demo addresses. Confirm OpenStreetMap has a building outline for each (look in a browser). Save outlines as GeoJSON files.
- [ ] Hand-download PVGIS-ERA5 hourly data for each demo address (tilt and azimuth you expect to use), plus one Metro Manila centroid. Keep files as data.
- [ ] Hand-collect a seed catalog: about 15 to 25 products (panels, inverters, batteries) in a spreadsheet with source URL and date.
- [ ] Shortlist 3 to 5 retailer sites with static pages. Read their robots.txt and terms; record the result.
- [ ] Gather Meralco inputs: latest typical-household rate, generation charge, fixed charges, bill table, net-metering page text, DOE grid emission factor, installer cost per kW (3 or more public quotes).

**Plan**
- [ ] Each person reads this plan and the contracts (section 5). Flag any disagreement before 9:00 AM.
- [ ] Decide who submits the final link, and confirm the submission channel with a coach at check-in.

**Check-in (Nov 12, 7:30 to 8:15)**
- [ ] Bring school IDs, arrive by 8:15 AM, receive the challenge statements, declare **Challenge 1**.

---

## 13. Likely judge questions and short answers

| Question | Answer |
|---|---|
| Isn't this just a solar calculator? | Calculators give one number from a form. Sol takes a roof from an address or drawing, simulates hourly against the household load over 16 weather years, optimizes parts to a budget and goal, and issues a verifiable record. |
| How do you handle net-metering credit? | Exports earn a monthly credit based on blended generation cost, not the full retail rate, and credits are banked. We approximate it with the published generation charge, show it as editable, and display a sensitivity. |
| Where do the prices come from? | Public listings on shortlisted sites, fetched live, validated, and shown with source and time. If a fetch fails we show cached prices labeled as cached. Always "confirm with the seller". |
| What stops the AI from making up numbers? | It can't compute. Numbers come from deterministic tools and render as cards. A guard checks the model's text against tool results. |
| How accurate is the irradiance data? | PVGIS-ERA5 is a modeled reanalysis dataset, labeled as such. We show a pessimistic and optimistic range instead of a single number. |
| Is this safe with customer data? | The demo uses synthetic data only. Uploaded images and bills are processed per session and not kept. |
| What is the Passport? | Your proof of going solar. Sol issues it with your plan and signs it. An installer confirms the install, and then it unlocks vouchers and discounts. It does not prove your real roof or usage; those are inputs. |
| Is anything real-world verified? | Not in the demo. Results are modeled estimates on synthetic households, and the Passport says so. Real meter data would be a later step. |
| What can't it do? | Electrical design, shading analysis, multi-plane roofs, permitting. It tells users an installer must confirm. |
| What was technically hard? | Hourly dispatch over 16 years with a battery, a goal-driven optimizer under budget and roof constraints, resilient live scraping, and a signed Passport with install confirmation and one-time vouchers. |
| What are the vouchers? | Signed codes tied to one Passport, issued after the install is confirmed. They reward going solar, for example a site survey or an installer discount. Values are samples until a partner funds them. They have no cash value and Meralco is not involved. |
| Can someone fake or reuse a voucher? | The code comes from Sol's signature, so it can't be made up. It is only issued after the install is confirmed, and it redeems once. |
| Why would installers fund vouchers? | They get a customer who arrives with a layout, a price and the assumptions already checked. That's a pitch, not an agreement. |
| How does this help Meralco? | Customers arrive knowing how exports are credited and which grid pathway applies, and there is a record to point to in referrals. This is a next step. Sol promises no Meralco benefit. |
| Why 10 years? | Ten years is the horizon for every figure, so the comparison is easy to read. A payback longer than 10 years shows as "not within 10 years". |
| Does the battery pay for itself? | Not within 10 years in the deck's illustrative case. It buys backup power. Sol shows the numbers and lets you decide. |
| What would you build next? | Multi-plane roofs and shading from imagery, real meter integration, and installer-side quotes. |

---

## 14. Rule compliance matrix

| Rule | Plan |
|---|---|
| Code only 9:00 AM Nov 12 to 9:00 AM Nov 13 | First commit after 9:00. Only planning, data and installs before. |
| Public libraries, assets and APIs are allowed; others need organizer approval | Only open-source libraries and public APIs. Ask a coach before using anything else. |
| Submission before 9:30 AM with all files and a repo link | Submit by 8:30 AM. Confirm the channel at check-in. |
| One entry per team, one challenge | One repo, **Challenge 1** declared. |
| No plagiarism | All code written in the window by the team. No copied code or text. Ideas are our own design. |
| Data ethics and privacy | Synthetic demo data. No stored uploads. Labels on every estimate. |
| All members physically present; one stays at the venue | Schedule shifts so at least one member is always present. |
| Devices stay if you leave | Leave project laptops at the table. |
| Quiet hours 12:00 AM to 6:00 AM, sleep in designated areas | Staggered sleeping in assigned areas; silent collaboration. |
| No alcohol, smoking, illegal substances; no single-use plastics | Bring a tumbler. |
| Pitch: 10 minutes plus 5 minutes Q&A, centered on a working demo | Script in section 11. |

---

## 15. Definition of done

- [ ] `demo_run.py` passes on all three personas with no errors.
- [ ] Address → roof → bill → budget/goal → packages → ROI → Passport, install confirmed, live, in under about 90 seconds of interaction.
- [ ] Forms path works with the LLM disabled.
- [ ] The Passport shows no vouchers until the install is confirmed; then vouchers appear and one redeems once.
- [ ] Rewards say "sample value" everywhere.
- [ ] Scraper path works live and falls back to cache with the right label.
- [ ] Math drawer lists every assumption with a source and date.
- [ ] README explains how to run, what is synthetic, limitations and data sources.
- [ ] Backup video recorded and tested on the presentation laptop.
- [ ] Repo link submitted and opened from a second account before 9:30 AM.

---

## 16. Open items and unverified facts

- **[VERIFY]** Exact Meralco net-metering export-credit method and current figure; the generation charge is used as an approximation.
- **[VERIFY]** Free-tier Gemini model that supports image input with function calling together on your key, and its rate limits.
- **[VERIFY]** Latest available year in PVGIS-ERA5 and pvlib's azimuth convention for the version installed.
- **[VERIFY]** DOE grid emission factor value and year.
- **[VERIFY]** OpenStreetMap coverage for each chosen demo address.
- **[VERIFY]** Robots.txt and terms of each shortlisted retail site.
- **[VERIFY]** Where and how the repo link is submitted.
- **[VERIFY]** Whether the hackathon rules say anything about reward or incentive features (the guidelines PDF has no text layer, so it could not be searched; read it by hand and ask a coach at check-in).
- **[PROPOSED]** Reward catalog (three entries) and the 10-year headline horizon.
- **[PROPOSED]** Schedule, demo script, and stack choices were not formally confirmed.
