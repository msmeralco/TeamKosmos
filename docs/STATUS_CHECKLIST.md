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

## Tier 2: Full product

- [x] Goal- and budget-driven optimizer
- [x] Real ready-made packages (25 from 6 installers) with photos, published prices and links, shown under every analysis and on request; prices are re-checked against the live pages by `scripts/build_packages.py`
- [x] Every package has an image: real installer photos where they exist, drawn illustrations otherwise (PTG Solar, Triple30 and the samples)
- [x] Made-up sample packages fill gaps (grid-tied sizes, off-grid), always labeled _Sample_ and shown only where no real package fits
- [~] Live product price fetch with cache: scraper code exists, no retailer source is enabled, prices come from the seed catalog
- [x] 2D panel layout on the roof
- [x] Blank-canvas sketch with scale correction, floating tools, and an uploaded picture to trace by hand
- [x] Solar Passport: issue, sign, verify, shareable page, QR code
- [~] Install confirmation by an installer: no confirm flow (MVP). Only the seeded solar owner has an installed Passport; the installed fact (a sample installer, `sample: true`) is inside the signed record
- [x] Solar Rewards: sample voucher catalog (`backend/data/vouchers.json`), shown to the seeded owner; values are samples, nothing agreed with Meralco or any business
- [x] Voucher redeem (once only; the code appears after redeeming; a repeat returns 409)
- [x] Passport booklet UI (Passport entry in the sidebar, only for the owner): cover that opens, ID page with QR and verify seal, voucher page

## Tier 2b: Rules search

- [x] Document library (`backend/data/docs_corpus/`): 4 Meralco solar pages, DOE own-use rules summary, 5 general solar pages, PVGIS manual, 2 manufacturer pages, installer guidance, data notes
- [x] `search_docs` agent tool with source links (keyword search, works offline)
- [x] "Ask the rules" in chat, in both Gemini and rule-based modes
- [x] `scripts/build_corpus.py` downloads the listed pages, respecting robots.txt
- [x] DOE Solar PV Installer Registry in the library (Jan 31 and Jul 13, 2026 lists; 77 firms in Metro Manila, Central Luzon and CALABARZON), always shown as registered, not endorsed

## Tier 3: Stretch

- [~] Photo or blueprint auto-outline: you can trace over an uploaded picture by hand; automatic outlining is not built

## Other features

- [x] Sign up, login, logout, seeded demo users
- [x] Seeded solar owner `dela.cruz@sol.test` with a signed, installed Passport and 4 sample vouchers (`scripts/seed_owner.py`, run once per database after `seed_users.py`; migration `003_rewards.sql`). Demo accounts get the password `password` unless `SEED_PASSWORD` is set
- [x] Installer list rows show one contact (phone, else email, else website) instead of the DOE list badge
- [x] No goal question: once the budget is set the goal defaults to the biggest 10-year savings and Sol gives a summary with no question (the goal can still be changed)
- [x] Click a package: "Details & contacts" asks Sol, which shows price, parts, how it fits the budget and size, the installer's published phone, email, website and social links (checked against the installer's page), and questions to ask
- [x] Packages that fit the budget open in the side panel as soon as the budget and system type are set (before the numbers run), then refresh to the real design after the analysis
- [x] Installers and packages open in a side panel (like the map): cards with contact buttons and search for installers; photo cards with type filter and sort for packages; a link in the chat reopens them
- [x] Starter pills: Map my site, Recommend Installers (asks your area, then a DOE-registry table with contacts), Compare packages, Brief on Solar
- [x] Saved chats: recents list, new chat, delete
- [x] Suggestion pills only under the latest message; after a rules answer they offer new, answerable follow-up questions, and after an analysis they depend on its warnings
- [x] Bill photo reading in chat
- [x] Overview page: package comparison and math drawer
- [x] Saved Records page: Passport view and paste-to-verify
- [x] Assumptions register shown in the app (`ASSUMPTIONS.yaml`)
- [x] Mac and Windows dev scripts (`scripts/dev.sh`, `scripts/dev.ps1`)
