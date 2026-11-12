# Sol: Your Clean Energy Partner (Team Kosmos, IDOL Hackathon 2026)

**Challenge declared:** 1, Clean Energy Adoption and Rewards

## Idea
An AI agent that helps a Meralco household compare solar options and verifies the result. The user describes a roof, gives a bill, a budget and a goal. The agent returns sized options, a 25-year ROI comparison and a verifiable record.

## Flow
1. **Roof input:** Type an address (outline autofilled from OpenStreetMap) and adjust it on a satellite map. If lookup fails, draw it by hand. Later: blank-canvas sketch with manual scale, and photo/blueprint auto-outline.
2. **Bill and goal:** Monthly kWh or bill, budget range, and a goal (cut bill by X%, max 10-year savings, fastest payback, blackout backup).
3. **Live equipment search:** Agent fetches prices from 3 to 5 static retailer sites. Falls back to cached prices. Each price shows source, timestamp and "confirm with the seller".
4. **Optimizer:** Builds the top 2 or 3 parts lists inside budget, goal and roof limits.
5. **Engine:** pvlib with PVGIS-ERA5 hourly data (NASA POWER fallback), simulated hour by hour against an estimated load.
6. **ROI table:** Grid-only vs on-grid solar vs hybrid with battery. Net-metering on/off toggle, editable buyback rate, 25-year profit after replacement reserves, cost per kWh produced, payback with best-case and bad-year range.
7. **Layout and record:** 2D panel layout, then the Solar Passport.

## Verification
The Solar Passport is a signed, hashed record (QR code) of inputs, assumptions and results, so anyone can check what Sol recommended, why, and that it has not been changed. No tiers, rewards or points.

## Trust rules
- The LLM never does math. It calls tools, and the math panel shows sources.
- Net-metering exports are credited at an approximate monthly generation charge (editable), not the full retail rate, with a lower-credit sensitivity.
- Eco ranking uses measurable fields. Embodied carbon is shown only if published, else "not disclosed".
- All results are estimates for a licensed installer to confirm. Demo data is synthetic.

## Build tiers (cut from the bottom)
| Tier | Target | Scope |
|---|---|---|
| 1 | Hour ~14 | Address lookup and drawing on satellite map, simulation, ROI table with ranges, agent chat via tool calls |
| 2 | Hour ~20 | Budget/goal optimizer, live product fetch with cache, 2D layout, Solar Passport, blank-canvas sketch |
| 3 | Stretch | Photo/blueprint auto-outline, battery polish, 3D view |

Feature freeze 6:00 AM. Code window ends 9:00 AM Nov 13. Submit repo link before 9:30 AM.

## Event rules to remember
- Code only between **9:00 AM Nov 12 and 9:00 AM Nov 13**. Planning, installs and data gathering beforehand are allowed.
- Arrive by **8:15 AM** (registration 7:30). Bring school IDs. All members present, one always at the venue.
- Pitch: 10 min plus 5 min Q&A, centered on a working demo.
- Judging: Innovation 30, Functionality 25, Impact 20, Technical Challenge 15, Presentation 10.
- Plagiarism and data privacy breaches are disqualification grounds. Use no real customer data.

## Tonight (no code)
- Create a Google AI Studio key and make one manual test call with an image and a function call.
- Pick 3 to 5 demo addresses and confirm OpenStreetMap has a building outline for each. Save the outlines as data.
- Shortlist 3 to 5 retailer sites with static pages and check robots.txt and terms by hand.
- Pull the latest Meralco generation charge and typical household rate.
- Hand-collect a small starter catalog of panels, inverters and batteries for the cache.
- Prepare a backup demo video plan in case venue wifi fails.

## Open
- Demo script not finalized. Proposed: hook, live address, results, math panel and Passport, live product search, close.
- Unverified: exact Meralco export-credit figure, free-tier Gemini image plus function-calling support, OSM coverage for chosen addresses.
