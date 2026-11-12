# Sol: Your Clean Energy Partner

Team Kosmos, IDOL Hackathon 2026, Challenge 1.

Sol is an AI agent that acts as your solar energy guide and adviser. It helps a Meralco household go solar: you give it your address, bill, budget and goal, and it measures your roof, compares your options over ten years, picks a package and a DOE-registered installer, and issues a Solar Passport that unlocks vouchers once the install is confirmed.

## The problem

- Meralco's typical household rate rose from ₱12.95 per kWh (January 2026) to about ₱15.06 (October 2026), roughly 16%. For a 200 kWh household that is a bill going from about ₱2,590 to about ₱3,010.
- Installed solar prices run from ₱45 to ₱75 per watt, and every installer sells different packages. The DTI has also warned about substandard solar products entering the market.
- Customers must choose between net metering, a zero-export system and a micro solar system, each with its own paperwork and rules, and then find a trusted installer near them.

## What Sol does

1. **Measures your site.** Sol outlines your building from OpenStreetMap on a satellite map, or you trace the roof over a blueprint or photo you upload. It computes the usable area, estimates direction and tilt, and drafts a panel layout.
2. **Asks about your household.** Your monthly bill, when your home is busiest, your budget and your main goal. Sol builds an hour-by-hour picture of your usage, because solar only saves money on power you use while the sun is out.
3. **Compares your options.** Grid only, solar, and solar with a battery (hybrid), with and without net metering. For each option you see upfront cost, yearly savings, payback, and savings over 10 years, with a bad year, a typical year and a good year.
4. **Picks packages and installers.** Sol matches your budget and system size to ready-made packages with published prices stored in its own data, and lists DOE-registered installers you can contact for a site visit and a formal quote.
5. **Answers from sources.** Questions about rules, fees and permits are answered from a library of source-linked documents (retrieval-augmented generation, BM25 keyword search), with a link to the source.
6. **Issues a Solar Passport.** A signed record of your plan. After an installer confirms the install, it unlocks vouchers and discounts.

## How it works

The AI never does the math. It calls tools, and a number guard blocks any figure in its reply that the tools did not produce.

| Step | What happens |
|---|---|
| Address | `geocode_address` turns the address into coordinates (Nominatim, Photon as backup). |
| Pin | `get_building_outline` fetches the building footprint from OpenStreetMap and measures it in square metres. |
| Load | The bill becomes kWh, then an 8,760-hour usage profile. |
| Simulate | Hourly solar output from PVGIS-ERA5 weather (pvlib), battery dispatch, net-metering billing, 25-year cash flow. |
| Compare | Net metering on and off, bad / typical / good year. |
| Optimize | Searches panel, inverter and battery combinations inside your budget and roof, ranked by your goal. |
| Passport | Hashes the plan into a chain of records and signs it with Ed25519. Each voucher redeems once. |

## Sources

The document library holds Meralco's net-metering guide and application process, its distributed energy resources FAQ, a summary of the DOE circular DC2026-08-0017, the DOE Solar PV Installer Registry (listed, not endorsed), and the PVGIS 5 manual. Hourly sunlight data comes from PVGIS-ERA5 (EU Joint Research Centre).

- Meralco, higher residential rates, October 2026: https://www.meralco.com.ph/media/articles/higher-residential-rates-october-2026
- Meralco, February 2026 rate advisory: https://www.meralco.com.ph/media/advisories/higher-residential-rates-february
- Meralco, Solar and Net Metering: https://www.meralco.com.ph/residential/energy-solutions/solar-and-renewables/solar-net-metering
- Meralco, Apply for Net Metering: https://www.meralco.com.ph/residential/energy-solutions/solar-and-renewables/re-net-metering-application
- Meralco, Distributed Energy Resources: https://www.meralco.com.ph/residential/energy-solutions/solar-and-renewables/distributed-energy-resources
- Rappler summary of the DOE circular: https://www.rappler.com/business/things-to-know-simplified-rules-solar-panels-department-energy/
- DOE Official Solar PV Installer Registry: https://doe.gov.ph/official-doe-solar-pv-installer-registry-updated-as-of-july-13-2026
- PVGIS 5 user manual: https://joint-research-centre.ec.europa.eu/pvgis-photovoltaic-geographical-information-system/getting-started-pvgis/pvgis-user-manual_en
- Installer prices and inclusions as published on PTG Solar, Triple30 Renewables and DevSolutions Solar websites, checked 12 November 2026.
- Price range: GoSolar PH (https://gosolarph.com/guides/best-solar-panel-brands-philippines/) and Tech Pilipinas (https://techpilipinas.com/solar-panel-cost-philippines/).
- DTI on solar product certification: https://business.inquirer.net/592097/dti-moves-to-regulate-solar-panel-systems

## Honest limits

- Households, demo roofs, the parts catalog and vouchers are synthetic. Voucher values are samples, have no cash value, and nothing is agreed with Meralco or any business.
- Every result is an estimate for a licensed installer to confirm. Shading, roof structure and permits are not solved.
- Installer confirmation of an install is not built yet. Only the seeded demo owner has an installed Passport.
- `backend/ASSUMPTIONS.yaml` lists every assumption. Entries marked `verified: false` are placeholders.

## Run the app

You need [Python 3.12 with uv](https://docs.astral.sh/uv/getting-started/installation/) and [Node.js](https://nodejs.org/).

### 1. One-time setup

Run these from the repo root.

**macOS / Linux**

```
uv venv --python 3.12 .venv
uv pip install -p .venv/bin/python -r backend/requirements.txt
cp backend/.env.example backend/.env
(cd frontend && npm install)
```

**Windows (PowerShell)**

```
uv venv --python 3.12 .venv
uv pip install -p .venv\Scripts\python.exe -r backend\requirements.txt
Copy-Item backend\.env.example backend\.env
cd frontend; npm install; cd ..
```

Then open `backend/.env` and fill in `GEMINI_API_KEY` and `CONTACT_EMAIL`. Use a real email: Nominatim rejects the placeholder, and address search fails without it. Without a Gemini key, Sol falls back to a rule-based agent. See `backend/README.md` for every setting.

### 2. Start Sol

One script starts the backend (port 8000) and the frontend together. Stop both with Ctrl+C.

**macOS / Linux**

```
./scripts/dev.sh
```

**Windows (PowerShell)**

```
.\scripts\dev.ps1
```

If PowerShell blocks the script, run `Set-ExecutionPolicy -Scope Process Bypass` first.

### 3. Open the app

Open the address Vite prints, usually http://localhost:5173. `http://127.0.0.1:8000/api/health` shows which database and agent mode are active.

## Run the pitch deck

```
cd deck
./start.command
```

The deck is a 3D voxel street. It opens in the browser, and the arrow keys move between slides. See `deck/README.md` for the controls.

## Docs

The plan, the pitch script and the Q&A guides are in `docs/`. Backend details, scripts and tests are in `backend/README.md`.
