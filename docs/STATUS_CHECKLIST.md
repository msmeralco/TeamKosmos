# Sol: Status Checklist

## Tier 1: Core

- [x] Address search and building outline (Nominatim, OpenStreetMap)
- [x] Draw the roof on a satellite map (drag corners, add corners, undo, no self-crossing)
- [x] Roof type, tilt and direction, usable area
- [x] Household load estimate from kWh or bill (3 templates)
- [x] Hourly solar simulation (PVGIS-ERA5, bundled Metro Manila data)
- [x] Net-metering billing, on/off toggle
- [x] ROI table: grid only, solar, solar with battery, with bad-year, expected and best-case ranges
- [x] 25-year cash flow, payback, NPV, IRR
- [x] System type choice: grid-tied, hybrid or off-grid, which changes what the optimizer builds (no battery, always a battery, most grid power replaced)
- [x] Chat agent with tool calls (Gemini, rule-based fallback)
- [x] Results block in chat: headline table, option comparison table, "Good to know" list
- [x] Number guard (the AI never states numbers the tools did not produce)
- [x] "Before you invest" checks on every option, from Meralco's four points:
  - [x] Right size: share of solar used at home, transformer hosting limit
  - [x] Right location: roof direction, outline confidence, sketch scale; structure and shading flagged for the installer
  - [x] Right provider: exact parts to quote, what to ask the installer
  - [x] Know the requirements: Net Metering steps and fees, or Micro Solar and Zero-Export when not exporting
  - [x] Off-grid systems get their own size and requirements text (no transformer limit, no Meralco application)
  - [x] Shown on the Overview page and in the chat "Good to know" list
  - [ ] Optimizer ranking uses the checks (today they only warn)
  - [ ] Show DOE-registered firms in the provider check (today only the chat can list them)

## Tier 2: Full product

- [x] Goal- and budget-driven optimizer
- [~] Live product price fetch with cache: scraper code exists, no retailer source is enabled, prices come from the seed catalog
- [x] 2D panel layout on the roof
- [x] Blank-canvas sketch with scale correction, floating tools, and an uploaded picture to trace by hand
- [x] Solar Passport: issue, sign, verify, shareable page, QR code
- [ ] Install confirmation by an installer (Passport stage: installed)
- [ ] Solar Rewards: voucher catalog and issue
- [ ] Voucher redeem (once only)
- [ ] Rewards UI on the Passport page

## Tier 2b: Rules search

- [x] Document library (`backend/data/docs_corpus/`): 4 Meralco solar pages, DOE own-use rules summary, 5 general solar pages, PVGIS manual, 2 manufacturer pages, installer guidance, data notes
- [x] `search_docs` agent tool with source links (keyword search, works offline)
- [x] "Ask the rules" in chat, in both Gemini and rule-based modes
- [x] `scripts/build_corpus.py` downloads the listed pages, respecting robots.txt
- [x] DOE Solar PV Installer Registry in the library (Jan 31 and Jul 13, 2026 lists; 77 firms in Metro Manila, Central Luzon and CALABARZON), always shown as registered, not endorsed
- [ ] Vetted installer list (the DOE registry is a start, but the DOE states it endorses no one; no prices, reviews or service checks)
- [ ] Real product specs and prices (the catalog is synthetic)
- [ ] Meralco forms and checklists (PDFs, not downloaded)
- [ ] Embedding search (keyword search only)
- [ ] Confirm live Gemini actually calls `search_docs` (only the rule-based mode was tested)

## Tier 3: Stretch

- [~] Photo or blueprint auto-outline: you can trace over an uploaded picture by hand; automatic outlining is not built
- [ ] Battery polish
- [ ] 3D view

## Other features

- [x] Sign up, login, logout, seeded demo users
- [x] Saved chats: recents list, new chat, delete
- [x] Suggestion pills only under the latest message; after a rules answer they offer new, answerable follow-up questions, and after an analysis they depend on its warnings
- [x] Bill photo reading in chat
- [x] Overview page: package comparison and math drawer
- [x] Saved Records page: Passport view and paste-to-verify
- [x] Assumptions register shown in the app (`ASSUMPTIONS.yaml`)
- [x] Mac and Windows dev scripts (`scripts/dev.sh`, `scripts/dev.ps1`)
- [ ] Fix `backend/scripts/demo_run.py`: the new system-type question stops it before the analysis
- [ ] Set a real `CONTACT_EMAIL` in `backend/.env` (address search fails with 403 until then)
- [ ] Fix the `frontendv2` mention in the root `README.md` (the folder is `frontend/`)
- [ ] Real bill photos in `tests/` (private repo only): replace with fake bills before the repo goes public
