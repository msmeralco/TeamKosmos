# Sol Pitch Deck: Script and Design Plan

10 minutes of pitch + 5 minutes Q&A. The pitch is built around a **live demo**, so the deck is a frame: it opens, bridges between demo steps, and closes.

## Build status (Nov 12, 2:50 AM)

The deck is built in `deck/` (see `deck/README.md`): 9 pitch slides and 4 Q&A slides, Blender stills (Tier A) plus a live three.js voxel view (Tier B), a PDF copy, and presenter notes with a timer. Decisions taken as recommended: both tiers, Sol the small sun companion kept, crisp render. Hallmark lint: 0 FAIL, 0 WARN.

Not done: the backup video of the live demo (needs the product), the paste-to-verify box (a product feature), and the coach question below. Differences from the plan: the problem slides are three (Hook, Compare, Understand); labels are placed from exported anchors; no stars in the sky (the theme forbids a starfield).

## 0. Rule check first (do this before building anything)

- Terms D.2 says source code, **design** and assembly work on the Project must happen between 9:00 AM Nov 12 and 9:00 AM Nov 13. A pitch deck is not clearly the Project, but it is HTML/CSS/JS, and 3D models made in advance could count as "additional assets" that need organizer approval.
- Action: ask a coach at check-in (7:30 to 8:15 AM Nov 12): "Can we prepare presentation slides and 3D visuals before 9:00 AM?" Until answered, do **planning only** (this file).
- Safe fallback: build the deck inside the window, in parallel with the product (section 5).

## 1. Inferred brief (Hallmark step 1, skipped fields inferred)

- **Material, real only:** Meralco typical-household rate (₱12.9508 in Jan 2026, ₱15.0615 in Oct 2026); Sol's own screenshots and outputs (captured from the running app later). No invented metrics, testimonials or logos.
- **Audience:** three judges: Networks Technology, Customer Care, Regulatory Legal.
- **Use:** judges remember Sol and the Passport as a record they can verify, and score Innovation, Functionality, Presentation.
- **Tone:** austere in layout, playful in the 3D details. One idea per slide, about 15 words.
- **Genre:** atmospheric (3D, AI tool). The final theme comes from Hallmark's `deal` at build time.

## 2. Concept: "Voxel Sunrise"

Everything in the 3D world is built from cubes. One small **voxel neighborhood on a floating chunk of ground** is the stage, seen through an **orthographic isometric camera**. Sol means sun, so the sun is the story clock: the deck runs **night to noon**.

- Each slide is a different scene in the same world. The camera moves between them, so the deck feels like one place being explored.
- The sun is built from voxels and rises across the deck. Its position doubles as a progress indicator, so no slide numbers.
- **Sol the companion:** from slide 2 on, a tiny glowing voxel sun floats beside the scene and reacts (spins, points). It is the agent, and it stays small.
- Data in the 3D is real or not shown. Where a shape stands for a number, it is drawn to scale and the scale is stated.

**Look:** flat-coloured cubes, no textures, hard-edged sun shadows, sky in stepped colour bands (night, dawn, day), single-cube stars, clusters of cubes as clouds. About ten palette colours with amber (the sun) as the only warm accent. No icons, photos, or purple-to-blue gradients. UI type stays clean (one family, large, sentence case, untracked); only the "SOL" wordmark is built from voxels.

## 3. Script and slide plan

Times are cumulative. "Cue" slides stay up about 15 seconds, then you switch to the live app.

| Time | Slide | On screen | 3D scene | Spoken line |
|---|---|---|---|---|
| 0:00 to 0:20 | **S1 Hook** | "₱12.95 to ₱15.06 per kWh, Jan to Oct 2026: +16%" and "450 kWh ≈ ₱6,780 a month (illustrative household)". Source lines. | **The coin towers.** Night street. Two towers of stacked voxel coins beside a dark house with one lit window. The October tower is taller, drawn to scale (1 voxel = ₱0.25, rounded: 52 and 60 voxels). | "A household using 450 kWh now pays about ₱6,780 a month. Meralco's typical rate is up 16 percent since January. Solar is the obvious answer, so people start asking." |
| 0:20 to 0:40 | **S1b Compare** | "Solar options are hard to compare." Two lines: "₱45 to ₱75 per watt: published installed prices" and "Buyers can't tell a qualified quote from a cheap one." Sources. | **The lineup.** Three identical voxel installer vans under street lamps in mist. Flags read ₱45/W on the left and ₱75/W on the right (both sourced); the middle flag is blank. You cannot tell them apart by looking. | "But the options are hard to compare. Published installed prices run from ₱45 to ₱75 a watt. Installers say buyers can't tell a qualified quote from a cheap one, and the DTI wants mandatory certification because of substandard products." |
| 0:40 to 1:00 | **S1c Understand** | "Hard to know what you'd actually get." Two lines: "Exports aren't credited at the retail rate." and "Without a REC meter, generation is estimated by formula." Sources. | **The meter.** Amber energy cubes stream from the roof along a wire into the wall meter. Fewer, smaller cubes come out the other side. No ratio is shown. A "?" sits on the empty REC-meter slot. | "And it's hard to understand what you'd get. Exported power is not credited at the retail rate, and without a REC meter your generation is estimated by formula. Sol is built to make both clear and checkable." |
| 1:00 to 1:30 | **S2 Sol** | "Sol. Your clean energy partner." Sub: "Your roof, your bill, your goal. One answer you can check." | **Sunrise.** The voxel sun climbs over the horizon, the sky steps from night to dawn, Sol the companion appears. The camera swings to top-down and roof-edge cubes light up one by one, tracing the outline. | "Meet Sol. Sol starts with your roof, not a form." |
| 1:30 to 2:45 | **LIVE** | (app) | | Type the address, show the satellite outline, adjust one corner. "Measured, not guessed." |
| 2:45 to 3:00 | **S3 Cue** | "Tell Sol your bill, budget, goal." | **Block drop.** Voxel panels fall from the sky and snap onto the roof grid one at a time. Sol shows three dots. | "Now we just talk to it." |
| 3:00 to 5:00 | **LIVE** | (app) | | Chat: bill, budget, goal. Product feed visible with sources. Three packages appear. "Prices come live from public listings, each with its source and time." |
| 5:00 to 5:15 | **S4 Cue** | "Grid, solar, hybrid. A range, not one number." | **Three skies.** Three identical houses under a stormy, a partly clear and a clear sky, standing for a bad, a typical and a good weather year. Three voxel wires run to them: grid only, solar, solar plus a battery block. | "Here's where most tools stop at one confident number." |
| 5:15 to 6:45 | **LIVE** | (app) | | ROI table. Flip the net-metering toggle. Show best-case and bad-year range and the 25-year cash flow. |
| 6:45 to 7:00 | **S5 Cue** | "Every number has a source." | **The cross-section.** The house and ground lift apart like a cutaway. Four strata sit below: weather, tariff, net-metering credit, prices. The camera dives through them. | "Now the part judges should check." |
| 7:00 to 7:45 | **LIVE** | (app) | | Open the math drawer: sources, assumptions, export credit approximation, scenario definitions. |
| 7:45 to 8:00 | **S6 Cue** | "A record anyone can verify." | **The seal.** A voxel document lands beside the house, a voxel seal stamps it, a green check appears. Behind it, a chain of linked blocks stretches into the distance. | "Sol doesn't just answer. It signs, so anyone can check." |
| 8:00 to 9:15 | **LIVE** | (app) | | Issue the Passport, scan the QR, open the verify page, show the green check. Optional tamper test: change one digit in the downloaded record, verify again, show it fail (needs a paste-to-verify box; see section 6). |
| 9:15 to 10:00 | **S7 Close** | "Sol. Your clean energy partner." Sub: "Compare honestly. Understand clearly. Verify openly." | **Noon.** The camera lifts to a full isometric view of the neighborhood in daylight, panels on a few roofs, Sol at the top, the voxel "SOL" wordmark standing in the foreground. | "Compare honestly. Understand clearly. Verify openly. Thank you." |
| Q&A (5 min) | **A1 to A4** | A1 assumptions and sources; A2 how Sol works (pipeline); A3 what Sol does not do; A4 verification flow | Static voxel stills | Answers from section 13 of the implementation plan. |

The impact slide is removed. Its minute is given back to the live demo (more time for the roof, chat, compare and Passport steps) plus a buffer at the close.

**Fallback:** a recorded video of the live segments, chaptered by the same cues. If anything fails, say so, play the chapter, return to the deck.

## 3a. Problem evidence (real sources, checked Nov 11, 2026)

The deck's problem slides cover two parts of the challenge statement: (1) compare solar options, (2) understand what you would get. The recognition and reward part of the challenge is left out by decision. Every figure on a slide must come from this table, with its source line shown.

### A. Why it matters now

| # | Figure | Source | Used on |
|---|---|---|---|
| 1 | Meralco typical-household rate ₱12.9508/kWh (Jan 2026) and ₱15.0615/kWh (Oct 2026): **+16.3%** (our arithmetic). Dialogue Earth also reports "a 16% increase from January". | Meralco press releases: [Feb 2026](https://www.meralco.com.ph/media/articles/higher-residential-rates-february-2026) (gives the January figure), [Oct 2026](https://www.meralco.com.ph/media/articles/higher-residential-rates-october-2026) | S1 |
| 2 | The median Filipino household spends about 12% of monthly income on electricity. | Reuters, June 2026, as reported by [Dialogue Earth via Reccessary](https://www.reccessary.com/en/news/philippines-solar-surge-leaves-many-filipinos-behind). Secondary report; say "Reuters reported". | Q&A |
| 3 | Highest residential power price in Southeast Asia: ₱12.43/kWh (June 2026), ₱0.09 above Singapore. | DOE Undersecretary Guevara via [Philippine Star, Jul 21, 2026](https://www.philstar.com/headlines/2026/07/21/2543545/doe-philippines-power-rates-now-highest-sea) | Q&A |

### B. Solar options are hard to compare

| # | Figure | Source | Used on |
|---|---|---|---|
| 4 | Published installed cost ₱45 to ₱75 per watt (a spread of about 1.7×, our arithmetic); 5 kW systems ₱250,000 to ₱400,000. The author notes some sites quote ₱120,000 and others ₱750,000 without explaining why, and that quotes may leave out batteries, panel upgrades and interconnection fees. | [Tech Pilipinas, 2026](https://techpilipinas.com/solar-panel-cost-philippines/). A tech publication compiling installer data, not an official source; say "published installer ranges". | S1b |
| 5 | Buyers "have no reliable way to tell a qualified installer from a cheap one"; sales fall through when customers choose the cheapest quote or cannot pay upfront; most installers convert a quarter or fewer of inquiries. | New Energy Nexus Philippines research via [pv magazine, Nov 10, 2026](https://www.pv-magazine.com/2026/11/10/price-wars-emerge-as-biggest-challenge-for-philippines-solar-installers/) | S1b |
| 6 | The DTI proposed mandatory certification of solar products to protect consumers from low-quality and potentially unsafe products (comments open until Jul 25, 2026). | [GMA News, Jun 3, 2026](https://www.gmanetwork.com/news/topstories/nation/990024/dti-eyes-mandatory-certification-for-solar-power-products/story/) | S1b |
| 7 | Installing solar "can seem overwhelming" because of permits, cost and safety; households may turn to unregistered installers. Cites an April 23 Agile Data Solutions survey: 87% of Filipinos considering solar, with cost, maintenance and durability as top concerns. | Column by Meralco VP Joe Zaldarriaga, [Philippine Star, Jun 18, 2026](https://www.philstar.com/business/2026/06/18/2535931/powering-solar-protecting-homes-and-businesses). The survey is cited second-hand; say "as cited by Meralco's Zaldarriaga". | Q&A |

### C. Hard to understand what you would get

| # | Figure | Source | Used on |
|---|---|---|---|
| 8 | An exported kWh "is not exchanged one-for-one at the full retail rate"; the credit uses the monthly blended generation cost. Meralco publishes a FAQ on exactly this question. | [Meralco, Solar and Net Metering](https://www.meralco.com.ph/residential/energy-solutions/solar-and-renewables/solar-net-metering) | S1c |
| 9 | REC meters are voluntary; without one, generation is estimated by formula (Meralco requires an affidavit and waiver). | Same Meralco page; [pv magazine, Sep 15, 2025](https://www.pv-magazine.com/2025/09/15/philippines-updates-net-metering-rules-to-ease-adoption-for-17000-users/) | S1c |
| 10 | ERC chair: net-metering remains slow partly because requirements differ across utilities. | pv magazine, Sep 15, 2025 (link above) | Q&A |

### Gaps, do not fill with guesses
- No survey found on how many customers understand their bill or net-metering terms.
- No data found on how often quotes are misleading or oversized.
- Ember's payback estimate (4.0 to 3.1 years) is an estimate; label it. Our own results come from Sol only.

---

## 4. Environment and design spec

- **Stage:** fixed 16:9, scales to the screen, keyboard and clicker navigation, presenter notes with the spoken lines and timings. Text lower-left, 3D scene fills the rest. About 15 words per slide.
- **Camera:** orthographic isometric (about 35° elevation, 45° azimuth), moving between eight named positions, 1 second ease.
- **Lighting:** one directional sun that moves per slide, hard shadows, flat ambient fill. Faces are shaded by direction (top lightest, sides darker), which gives the voxel look without textures.
- **Palette (tokens at `:root`, final values from Hallmark):** sky-night, sky-dawn, sky-day; ground, wall, roof; panel, metal; sun-amber (the only warm accent); ink for text. About ten colours in total.
- **Motion:** transform and opacity only in the page; voxel animation (drops, streams, rises) lives in the clips or the live scene. A `prefers-reduced-motion` fallback shows static stills. Content visible with scripting off.
- **Offline:** everything in one local folder, no CDN, tested without wifi.

### Voxel assets

| Asset | Used in | Note |
|---|---|---|
| House (flat roof) | all scenes | Roof is an editable grid so panels snap to it |
| Panels (~10 slabs), battery block, wall meter | S3, S4, S1c | Separate objects so they can animate |
| Coin tower | S1 | Two stacks, heights to scale |
| Installer van (x3 identical) | S1b | Price flags are separate objects |
| Energy cube (amber) | S1c | Streams along a path |
| Weather sky sets (storm, partial, clear) | S4 | Cloud clusters of cubes |
| Strata blocks (4 layers) | S5 | Labels added in the page, not in 3D |
| Document, seal, check, chain blocks | S6 | Chain links echo the real hash chain |
| Sun (large) and Sol (tiny companion) | S2 onward | Same shape, two sizes |
| Neighborhood (~20 houses, trees, street) | S7 | Reuses the house model with variations |
| Wordmark "SOL" in voxels | S7 | The only voxel text |

### 3D delivery: two tiers

- **Tier A (baseline, low risk):** build in Blender, render eight short camera-move clips and eight stills; the deck plays them. No WebGL at runtime.
- **Tier B (upgrade if time):** the same voxel data drives a live scene in the browser with three.js (local copy) using instanced cubes, one state per slide. Voxel scenes are light, so this is cheaper than a normal 3D model. Keep Tier A stills as the fallback when WebGL fails. Render on demand and cap device pixel ratio at 2.

## 5. Build plan

1. **Rule check** (section 0).
2. **Install the slides skill:** clone `github.com/zarazhangrui/frontend-slides` into the skills directory. Use its fixed-stage CSS, HTML template, animation patterns and PDF export script. Skip its style-preview step; Hallmark sets the direction. Where the two overlap on design, Hallmark's floor wins; on deck mechanics (scaling, navigation), the slides skill wins.
3. **Voxel pipeline in Blender via the connected MCP** (checked: connected, default scene only, file unsaved). Save the `.blend` first, then:
   - Define each model as a small voxel grid in code (position to palette colour) in one shared file, `voxel_models.json`. This file is the single source for Blender and, in Tier B, the web scene.
   - Build one mesh per colour with hidden internal faces removed, so scenes stay light.
   - Assemble the eight scenes as separate collections with named camera positions; keyframe drops, streams and the sun arc.
   - Render stills and clips (Eevee, flat colours, hard shadows) at 1920×1080.
4. **Hallmark:** run its deal and picks block for the theme and tokens; write the deck; run `sloplint --render` and fix every FAIL.
5. **Deck assembly:** seven slides plus the problem slides, four appendix slides, notes, timing. Rehearse with a timer.
6. **After the product runs (around hour 20):** capture real screenshots for slots (map step, packages, ROI table, math drawer, Passport verify) and replace stand-ins. Export a PDF backup.

### Suggested timing inside the window

- H2 to H6: voxel models and scenes in Blender, stills and clips (independent of the product).
- H14 to H18: deck skeleton, clips integrated, script in notes.
- H21 to H23: real screenshots in, rehearsal, PDF export, backup video.

## 6. Open decisions

1. Tier A only, or Tier A plus Tier B for S2, S5 and S7? (Voxels make Tier B cheap.)
2. Keep Sol the tiny companion sun, or drop it for a plainer scene?
3. Crisp voxel render, or a low-resolution "pixelated" look (render small, scale up)?
4. Add a paste-to-verify box in the product so the tamper test works in the live demo? It is small but not in the implementation plan yet.
5. Will you ask the coach about advance preparation?

## 7. Notes

- "≈ ₱6,780" is arithmetic: 450 kWh × ₱15.0615/kWh = ₱6,777.68, rounded. The household is an illustration, not a real customer. Keep the "illustrative" label.
- The coin towers use 1 voxel = ₱0.25, rounded to whole voxels (52 and 60). That makes the October tower 15.4% taller, against a true 16.3%, so say "drawn to scale, rounded to the nearest voxel".
- The S1b middle flag stays blank because only the ₱45 and ₱75 ends are sourced. Do not invent a middle price.
- No numbers from Sol's own results go on slides until they come from the real app.
- Unverified: the slides skill's current file layout and export script, Blender version and render time on this machine, and Hallmark's handling of slide-sized pages.
