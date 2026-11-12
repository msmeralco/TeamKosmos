# Sol pitch deck

One continuous voxel world. The camera flies down a single Philippine street from 3 AM to noon, and each stop is a slide. Slide 0 is the title (Sol, the IDOL Hackathon and Team Kosmos); then Hook (1), Compare, Understand, Sol, Ask, Range (10 years), Sol picks (7: ready-made packages that installers publish, Sol picks the one that fits the size, budget and goal), Sources (with the RAG note), Passport (9: install confirmed, then vouchers and discounts) and Who it helps (10: customers, business owners, Meralco). Slide 5 (Ask) shows a chat between the owner and Sol. Slides 11 and 12 are Q&A backups (how Sol works, limits), shot in the same 3D street. Slide 11 plays the app's steps one by one (address, pin, loading, simulate, compare, optimize, passport) while the scene builds up. Slide 13 is the Thank you, with the Sol banner (press End to jump to it).

## Run it

```
./start.command          # or: python3 -m http.server 8123, then open http://127.0.0.1:8123
```

It needs a local server (the model loads as a file), a GPU-capable browser (Chrome, Edge, Safari, Firefox) and no network. Fonts and three.js are vendored.

| Key | Action |
|---|---|
| Arrows, space, page up/down | Move between slides |
| N | Presenter notes and timer |
| T / R | Start or stop the timer / reset it |
| Q | Cycle quality (the deck drops a level by itself under 28 fps) |
| F | Full screen |

URL options: `#6` or `?s=6` starts on slide 6, `?q=0-2` sets quality, `?still` freezes transitions (for screenshots), `?tod=0.5` sets time of day, `?cam=px,py,pz,tx,ty,tz,fov` sets the camera, `?set=ring:1,layers:1` sets scene state.

## How it is built

- `blender/kit/*.py` build the models as voxels in Blender. `voxlib.py` culls hidden faces and bakes ambient occlusion into vertex colours. Mesh name suffixes: none = lit by the sun, `__e` = windows and lamps (warm at night, glass by day), `__g` = always glowing.
- `world/kit.glb` is the exported kit (107 meshes). `blender/sol_world.blend` is the scene file.
- `js/world.js` lays the kit out as the street. `js/actors.js` animates the story (coins, vans, roof ring, panels, layers, passport, seal, vouchers). `js/sky.js` handles time of day. `js/main.js` holds the route (`STEPS`), the slides and the controls.
- 1 cell = 0.25 m. Models face -Y in Blender, which is +Z in the web scene.

## Rebuild the kit

Open Blender with the MCP add-on, then run:

```python
exec(open("<path>/deck/blender/kit/build_kit.py").read())
objs, stats, rows, secs = build()
export(objs)
```

It takes a few seconds and rewrites `world/kit.glb`.

## Editing the story

Each stop in `STEPS` (`js/main.js`) has `cam`, `tod` (0 = 3 AM, 1 = noon), `shift` and `vshift` (push the subject right and up, clear of the copy card) and a `set` patch of scene state. Appendix stops start from the `ZERO` state so nothing carries over from earlier slides. A tag can take `data-side`, `data-dx` and `data-dy` (px at 1600 wide); tags are clamped to the screen. Labels are `.tag` elements in `index.html`, keyed by `data-for` (step id) and `data-anchor`. Spoken lines are in each slide's `data-say` and in `../context/PITCH_DECK_PLAN.md`.
