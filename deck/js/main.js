// Sol deck: one voxel world, one camera, twelve stops. Boots the renderer, owns the route, the state tweens and the slide chrome.
import * as THREE from "three";
import { EffectComposer } from "three/addons/postprocessing/EffectComposer.js";
import { RenderPass } from "three/addons/postprocessing/RenderPass.js";
import { UnrealBloomPass } from "three/addons/postprocessing/UnrealBloomPass.js";
import { OutputPass } from "three/addons/postprocessing/OutputPass.js";
import { loadKit, makeKit, buildWorld, mats } from "./world.js";
import { createSky, applyTod } from "./sky.js";
import { createActors } from "./actors.js";
import { IN, compute, range, pesoK } from "./econ.js";
import { fillThumbs } from "./thumbs.js";

const $ = (s) => document.querySelector(s);
const Q = new URLSearchParams(location.search);
const STILL = Q.has("still");
if (STILL) document.head.append(Object.assign(document.createElement("style"), { textContent: "*{animation:none!important}" })); // frozen test captures
const clamp = (v, a = 0, b = 1) => Math.min(b, Math.max(a, v));
const lerp = (a, b, t) => a + (b - a) * t;
const easeIO = (t) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2);

/* ------------------------------------------------------------------ the route: camera, time of day, and what is happening at each stop */
// vshift lifts the subject clear of the copy card (fraction of the height).
// cam = [position, target, fov]. tod: 0 is 3 AM, 0.46 is sunrise, 1 is noon. shift pushes the subject right, clear of the copy card.
const ZERO = { coinsJ: 0, coinsO: 0, sellers: 0, wire: 0, roof3: 0, flowS: 0, flowX: 0, flowI: 0, pin: 0, ring: 0, plan: 0, planOut: 0, crew: 0, drop: 0, chat: 0, range: 0, weather: 0, apart: 0, layers: 0, passport: 0, seal: 0, reward: 0, city: 0, word: 0, solS: 0, dots: 0 }; // a clean slate for the appendix stops
const SOL = (x, y, z, s = 1.6) => ({ solX: x, solY: y, solZ: z, solS: s });
// via = extra camera stops before the last one: [pos, target, fov, share of the move at which it is reached]. dur overrides the travel time.
const STEPS = [
  // slide 0: a high, slow look over the sleeping street at 3 AM. The next stop drops to street level on the same night, so it reads as one shot.
  { id: "intro", cam: [[-170, 105, 190], [135, 8, -30], 40], tod: 0.0, shift: 0.26, vshift: -0.06, set: { ...SOL(100, 66, -10, 4.6) }, snap: ["solX", "solY", "solZ"] },
  { id: "hook", cam: [[-31, 25, 60], [-25, 28, -30], 40], tod: 0.04, shift: 0.2, set: { coinsJ: 1, coinsO: 1, solS: 0 }, delay: { coinsO: 3.4 } },
  { id: "compare", cam: [[198, 58, 240], [198, 14, 40], 38], tod: 0.2, shift: 0.22, vshift: 0.04, set: { sellers: 1, coinsJ: 1, coinsO: 1 } },
  { id: "understand", cam: [[296, 86, 124], [298, 22, -24], 40], tod: 0.3, shift: 0.17, set: { sellers: 0, wire: 1, roof3: 1, flowS: 1, flowX: 1, flowI: 1 }, delay: { flowS: 2.2, flowX: 5.2, flowI: 8.4 } },
  { id: "sol", cam: [[388, 122, 52], [390, 18, -40], 34], via: [[[392, 700, 60], [390, 0, -40], 30, 0.26]], dur: 11, tod: 0.46, shift: 0.13, vshift: 0.04,
    set: { wire: 0, flowS: 0, flowX: 0, flowI: 0, pin: 1, ring: 1, plan: 1, crew: 1, drop: 1, planOut: 0, chat: 0, ...SOL(338, 60, -30, 1.1) },
    delay: { pin: 7.4, ring: 8, plan: 9.2, crew: 9, drop: 12.8, solS: 0.4 }, snap: ["solX", "solY", "solZ"] },
  { id: "ask", cam: [[398, 52, 150], [398, 22, -30], 38], tod: 0.56, shift: -0.06, vshift: 0.06, set: { pin: 0, ring: 0, plan: 1, planOut: 1, crew: 0, drop: 1, chat: 1, dots: 0, ...SOL(422, 40, -14) }, delay: { chat: 0.6 } },
  { id: "range", cam: [[548, 118, 250], [548, 38, -37], 40], tod: 0.68, shift: 0, vshift: 0.14, set: { chat: 0, weather: 1, range: 1, dots: 0, ring: 0, plan: 0, planOut: 0, ...SOL(612, 104, -30, 1.4) } },
  // Sol picks: a parts catalog, then installer quotes (the cards are in index.html). Same street as the compare stop, pushed left of the card.
  { id: "match", cam: [[548, 70, 200], [548, 18, -30], 38], tod: 0.73, shift: -0.2, vshift: 0.08, set: { ...SOL(612, 104, -30, 1.4) } },
  { id: "sources", cam: [[720, 118, 92], [706, 58, -48], 36], tod: 0.78, shift: 0.14, vshift: 0.14, set: { layers: 1, apart: 1, weather: 0, solS: 0 }, delay: { apart: 1.2 } },
  { id: "passport", cam: [[926, 54, 232], [926, 26, 40], 36], tod: 0.88, shift: 0.1, vshift: 0.16,
    set: { passport: 1, seal: 1, reward: 1, layers: 0, apart: 0, ...SOL(960, 80, 0) }, delay: { seal: 1.8, reward: 4.6 } },
  // who it helps: the whole street gone solar, in full daylight
  { id: "impact", cam: [[440, 250, 400], [460, 4, 20], 42], tod: 1.0, shift: -0.2, vshift: 0.04,
    set: { ...ZERO, city: 1, passport: 0 }, delay: { city: 0.6 } },
  // appendix: the same street, reused. Every stop starts from a clean slate (ZERO) so nothing carries over by accident.
  { id: "how", cam: [[700, 300, 440], [700, 14, -20], 50], tod: 1.0, shift: -0.22, vshift: 0.07,
    set: { ...ZERO, chat: 1, pin: 1, ring: 1, layers: 1, apart: 1, weather: 1, range: 1, plan: 1, drop: 1, passport: 1, seal: 1, reward: 1, ...SOL(612, 104, -30, 1.4) },
    // the scene follows the steps list on this slide (its times are the data-at values in index.html)
    reset: ["chat", "pin", "ring", "layers", "apart", "weather", "range", "plan", "drop", "passport", "seal", "reward"],
    delay: { chat: 2.5, pin: 5.1, ring: 5.5, layers: 7.7, apart: 8.4, weather: 10.3, range: 12.9, plan: 15.5, drop: 15.9, passport: 18.1, seal: 18.9, reward: 19.3 } },
  { id: "limits", cam: [[396, 72, 126], [396, 18, -34], 38], tod: 1.0, shift: -0.1, vshift: 0.06,
    set: { ...ZERO, drop: 1, plan: 1, crew: 1, chat: 1 }, snap: ["drop", "plan", "crew", "chat"] },
  { id: "thanks", cam: [[470, 330, 470], [470, 4, 30], 40], tod: 1.0, shift: 0.06,
    set: { ...ZERO, passport: 1, seal: 1, reward: 1, city: 1, word: 1, ...SOL(470, 150, 70, 3) }, delay: { word: 2.4 } },
];
const DUR = { coinsJ: 3.2, coinsO: 3.8, sellers: 3.2, wire: 2.2, roof3: 2.6, flowS: 1.2, flowX: 1.2, flowI: 1.2, pin: 2.2, ring: 3.4, plan: 3.6, planOut: 2, crew: 1.2, drop: 5.5, chat: 1.2, range: 3.4, weather: 2.8, apart: 3.6, layers: 1.2, passport: 1.6, seal: 1.6, reward: 1.6, city: 7, word: 2.6, solS: 1.6, dots: 0.8, solX: 2.6, solY: 2.6, solZ: 2.6 };
const S = Object.fromEntries(Object.keys(DUR).map((k) => [k, 0]));
const stateAt = (i) => {
  const out = Object.fromEntries(Object.keys(DUR).map((k) => [k, 0]));
  for (let j = 0; j <= Math.min(i, STEPS.length - 1); j++) Object.assign(out, STEPS[j].set);
  return out;
};

/* ------------------------------------------------------------------ renderer */
const canvas = $("#gl");
let renderer;
try {
  renderer = new THREE.WebGLRenderer({ canvas, antialias: false, powerPreference: "high-performance" });
} catch (e) {
  fail("This browser could not start WebGL. Open the deck in a recent Chrome, Edge, Safari or Firefox.");
  throw e;
}
const LEVELS = [{ pr: 2, shadow: 4096 }, { pr: 1.35, shadow: 2048 }, { pr: 1, shadow: 0 }];
let level = Q.has("q") ? clamp(+Q.get("q"), 0, 2) : 0;
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;
renderer.toneMapping = THREE.NeutralToneMapping;
renderer.outputColorSpace = THREE.SRGBColorSpace;

const scene = new THREE.Scene();
scene.fog = new THREE.FogExp2(0x101828, 0.001);
const camera = new THREE.PerspectiveCamera(36, innerWidth / innerHeight, 1, 14000);
const hemi = new THREE.HemisphereLight(0xffffff, 0x445066, 1);
const key = new THREE.DirectionalLight(0xffffff, 1);
key.castShadow = true;
Object.assign(key.shadow.camera, { left: -170, right: 170, top: 170, bottom: -170, near: 10, far: 1100 });
key.shadow.bias = -0.0004;
key.shadow.normalBias = 0.5;
scene.add(hemi, key, key.target);
const sky = createSky(scene);

const composer = new EffectComposer(renderer, new THREE.WebGLRenderTarget(innerWidth, innerHeight, { type: THREE.HalfFloatType, samples: 4 }));
composer.addPass(new RenderPass(scene, camera));
const bloom = new UnrealBloomPass(new THREE.Vector2(innerWidth, innerHeight), 0.5, 0.4, 1.0);
composer.addPass(bloom);
composer.addPass(new OutputPass());

function applyLevel() {
  const L = LEVELS[level];
  renderer.setPixelRatio(Math.min(devicePixelRatio || 1, L.pr));
  renderer.shadowMap.enabled = L.shadow > 0;
  key.castShadow = L.shadow > 0;
  if (L.shadow && key.shadow.mapSize.x !== L.shadow) {
    key.shadow.mapSize.set(L.shadow, L.shadow);
    key.shadow.map?.dispose();
    key.shadow.map = null;
  }
  resize();
}
function resize() {
  const w = innerWidth, h = innerHeight;
  renderer.setSize(w, h, false);
  composer.setPixelRatio(renderer.getPixelRatio());
  composer.setSize(w, h);
  camera.aspect = w / h;
  camera.updateProjectionMatrix();
  fit();
}

/* ------------------------------------------------------------------ stage + slides */
const stage = $("#deckStage");
const slides = [...document.querySelectorAll(".slide")];
function fit() {
  const k = Math.min(innerWidth / 1920, innerHeight / 1080);
  stage.style.transform = `translate(${(innerWidth - 1920 * k) / 2}px, ${(innerHeight - 1080 * k) / 2}px) scale(${k})`;
  document.documentElement.style.setProperty("--k", k.toFixed(4));
}
const tags = [...document.querySelectorAll(".tag")];
const pills = [...document.querySelectorAll(".steps li")];

/* ------------------------------------------------------------------ tweens + camera */
let clock = 0, cur = -1, running = true, arrival = 0, shake = 0;
const tw = {}, camNow = { pos: new THREE.Vector3(), tgt: new THREE.Vector3(), fov: 36 };
let camTw = null;
const vals = { tod: 0, shift: 0, vshift: 0 };
function setTarget(k, to, dur, delay = 0) {
  const obj = k in vals ? vals : S;
  if (STILL || dur <= 0) { obj[k] = to; delete tw[k]; return; }
  tw[k] = { obj, from: obj[k], to, t0: clock + delay, dur };
}
function stepTweens() {
  for (const k in tw) {
    const t = tw[k];
    if (clock < t.t0) continue;
    const u = clamp((clock - t.t0) / t.dur);
    t.obj[k] = lerp(t.from, t.to, easeIO(u));
    if (u >= 1) delete tw[k];
  }
}
const camOf = (s) => ({ pos: new THREE.Vector3(...s.cam[0]), tgt: new THREE.Vector3(...s.cam[1]), fov: s.cam[2] });

let lastGo = 0, showTimers = [];
function go(i, instant = false) {
  i = clamp(Math.round(i), 0, slides.length - 1);
  if (i === cur) return;
  const now = performance.now();
  if (!instant && now - lastGo < 250) return;
  lastGo = now;
  const slide = slides[i], st = STEPS[i];
  slides.forEach((s, n) => {
    const on = n === i;
    if (!on && s.classList.contains("active")) { s.classList.add("leaving"); setTimeout(() => s.classList.remove("leaving"), 260); }
    s.classList.toggle("active", on);
    if (on) s.classList.remove("leaving");
  });
  document.body.dataset.tone = slide.dataset.tone || "day";
  tags.forEach((t) => t.classList.remove("show"));
  document.querySelectorAll(".msg").forEach((m) => m.classList.remove("show", "typing"));
  document.querySelectorAll("[data-show], [data-sel]").forEach((e) => e.classList.remove("show", "sel"));
  document.querySelectorAll(".flow li").forEach((li) => li.classList.remove("cur", "done"));
  showTimers.forEach(clearTimeout);
  showTimers = [];
  if (st) {
    const to = camOf(st);
    const from = cur < 0 || instant ? to : { pos: camNow.pos.clone(), tgt: camNow.tgt.clone(), fov: camNow.fov };
    const dist = from.pos.distanceTo(to.pos) + from.tgt.distanceTo(to.tgt);
    const dur = instant || STILL ? 0.0001 : st.dur || clamp(2.4 + dist / 230, 2.6, 6.2);
    if (instant || STILL) { camNow.pos.copy(to.pos); camNow.tgt.copy(to.tgt); camNow.fov = to.fov; camTw = null; }
    else camTw = { from, to, t0: clock, dur, lift: st.via ? 0 : Math.min(80, dist * 0.12), via: (st.via || []).map((v) => ({ pos: new THREE.Vector3(...v[0]), tgt: new THREE.Vector3(...v[1]), fov: v[2], at: v[3] })) };
    setTarget("shift", st.shift, instant ? 0 : dur * 0.8);
    setTarget("vshift", st.vshift || 0, instant ? 0 : dur * 0.8);
    setTarget("tod", st.tod, instant ? 0 : dur * 1.3);
    const target = stateAt(i);
    if (!instant && !STILL) for (const k of st.reset || []) { delete tw[k]; S[k] = 0; } // build the scene up from nothing, in step with the list
    for (const k in target) setTarget(k, target[k], instant || (st.snap && st.snap.includes(k)) ? 0 : DUR[k], (st.delay && st.delay[k]) || 0);
    arrival = instant ? 0 : dur;
    // each label shows at data-at seconds (default: as the camera settles) and, if it has data-until, goes again
    tags.forEach((t) => {
      if (t.dataset.for !== st.id) return;
      t.style.transitionDelay = "0s";
      if (instant || STILL) { if (!t.dataset.until) showTimers.push(setTimeout(() => t.classList.add("show"), 50)); return; }
      const at = t.dataset.at !== undefined ? +t.dataset.at : dur * 0.75 + 0.5;
      showTimers.push(setTimeout(() => t.classList.add("show"), at * 1000));
      if (t.dataset.until) showTimers.push(setTimeout(() => t.classList.remove("show"), +t.dataset.until * 1000));
    });
    // the catalog and quotes: data-show reveals an item, data-sel marks Sol's pick, both at the given second
    slide.querySelectorAll("[data-show], [data-sel]").forEach((e) => {
      const cls = e.dataset.show !== undefined ? "show" : "sel", at = instant || STILL ? 50 : +(e.dataset.show ?? e.dataset.sel) * 1000;
      showTimers.push(setTimeout(() => e.classList.add(cls), at));
    });
    // the chat: Sol's messages show three dots for a second, then the words
    slide.querySelectorAll(".msg").forEach((m) => {
      const at = +m.dataset.at * 1000, typing = m.classList.contains("sol") && !instant && !STILL;
      if (instant || STILL) { showTimers.push(setTimeout(() => m.classList.add("show"), 50)); return; }
      showTimers.push(setTimeout(() => m.classList.add("show", ...(typing ? ["typing"] : [])), typing ? at - 1000 : at));
      if (typing) showTimers.push(setTimeout(() => m.classList.remove("typing"), at));
    });
  }
  // the steps list: each step lights up at data-at; the ones before it turn to a tick. ?still shows them all done (or ?flow=N)
  const lis = [...slide.querySelectorAll(".flow li")];
  const setFlow = (n) => lis.forEach((li, k) => { li.classList.toggle("done", k < n - 1 || n > lis.length); li.classList.toggle("cur", k === n - 1); });
  if (lis.length) {
    if (instant || STILL) setFlow(+Q.get("flow") || lis.length + 1);
    else {
      lis.forEach((li, k) => showTimers.push(setTimeout(() => setFlow(k + 1), +li.dataset.at * 1000)));
      showTimers.push(setTimeout(() => setFlow(lis.length + 1), (+lis[lis.length - 1].dataset.at + 2.6) * 1000));
    }
  }
  cur = i;
  running = true;
  renderNotes();
  if (location.hash !== "#" + i) history.replaceState(null, "", "#" + i + location.search); // slide 0 is the intro, so the numbers match the old ones
}

/* ------------------------------------------------------------------ notes, timer, keys */
const notes = $("#notesPanel"), hint = $("#hint");
let t0 = 0, elapsed = 0, timing = false, tick = null;
const fmt = (s) => `${Math.floor(s / 60)}:${("0" + Math.floor(s % 60)).slice(-2)}`;
const renderClock = () => ($("#notesClock").textContent = fmt(elapsed + (timing ? (Date.now() - t0) / 1000 : 0)));
function toggleTimer() {
  if (timing) { elapsed += (Date.now() - t0) / 1000; timing = false; clearInterval(tick); }
  else { t0 = Date.now(); timing = true; tick = setInterval(renderClock, 500); }
  renderClock();
}
function renderNotes() {
  const s = slides[cur], n = slides[cur + 1];
  $("#notesWhen").textContent = `${s.dataset.time || ""}  ${s.dataset.title || ""}`;
  $("#notesSay").textContent = s.dataset.say || "";
  $("#notesNext").textContent = n ? "Next: " + (n.dataset.title || "") : "End of deck";
}
addEventListener("keydown", (e) => {
  if (e.metaKey || e.ctrlKey || e.altKey) return;
  const k = e.key;
  if (["ArrowRight", "ArrowDown", "PageDown", " "].includes(k)) { e.preventDefault(); go(cur + 1); }
  else if (["ArrowLeft", "ArrowUp", "PageUp"].includes(k)) { e.preventDefault(); go(cur - 1); }
  else if (k === "Home") go(0);
  else if (k === "End") go(slides.length - 1);
  else if (k === "n" || k === "N") { notes.hidden = !notes.hidden; renderNotes(); }
  else if (k === "t" || k === "T") toggleTimer();
  else if (k === "r" || k === "R") { elapsed = 0; t0 = Date.now(); renderClock(); }
  else if (k === "q" || k === "Q") { level = (level + 1) % LEVELS.length; applyLevel(); }
  else if (k === "f" || k === "F") document.fullscreenElement ? document.exitFullscreen() : document.documentElement.requestFullscreen?.();
  hint.classList.add("gone");
});
canvas.addEventListener("click", () => go(cur + 1));
let sx = null;
addEventListener("touchstart", (e) => (sx = e.touches[0].clientX), { passive: true });
addEventListener("touchend", (e) => { if (sx === null) return; const dx = e.changedTouches[0].clientX - sx; if (Math.abs(dx) > 50) go(cur + (dx < 0 ? 1 : -1)); sx = null; }, { passive: true });
let wheelLock = 0;
addEventListener("wheel", (e) => { const n = Date.now(); if (n - wheelLock < 800 || Math.abs(e.deltaY) < 20) return; wheelLock = n; go(cur + (e.deltaY > 0 ? 1 : -1)); }, { passive: true });
addEventListener("hashchange", () => { const n = parseInt(location.hash.slice(1), 10); if (!isNaN(n) && n !== cur) go(n, true); });
addEventListener("resize", resize);

/* ------------------------------------------------------------------ labels */
const _v = new THREE.Vector3();
function updateTags(A) {
  const id = STEPS[cur]?.id, k = parseFloat(getComputedStyle(document.documentElement).getPropertyValue("--k")) || 1;
  for (const t of tags) {
    const mine = t.dataset.for === id;
    t.classList.toggle("on", mine);
    if (!mine) continue;
    const a = A.anchors[t.dataset.anchor];
    if (!a) continue;
    _v.copy(a()).project(camera);
    const x = (_v.x * 0.5 + 0.5) * innerWidth, y = (-_v.y * 0.5 + 0.5) * innerHeight, lead = 26 * k;
    const side = t.dataset.side, w = t.offsetWidth, h = t.offsetHeight, dx = (parseFloat(t.dataset.dx) || 0) * k, dy = (parseFloat(t.dataset.dy) || 0) * k;
    let l = side === "below" ? x - w / 2 : side === "right" ? x + 20 * k : side === "left" ? x - 20 * k - w : x - w / 2;
    let tp = side === "below" ? y + lead * 0.7 : side === "right" || side === "left" ? y - h / 2 : y - lead - h;
    l = clamp(l + dx, 16, Math.max(16, innerWidth - w - 16)); tp = clamp(tp + dy, 16, Math.max(16, innerHeight - h - 16)); // keep every tag on screen
    t.style.transform = `translate(${l}px, ${tp}px)`;
    t.style.visibility = _v.z < 1 ? "visible" : "hidden";
  }
}

/* ------------------------------------------------------------------ frame loop */
let W, A, last = performance.now(), frames = 0, acc = 0, prevSeal = 0;
const sway = new THREE.Vector3();
function updateCamera() {
  if (camTw) {
    const u = clamp((clock - camTw.t0) / camTw.dur);
    if (camTw.via.length) {
      // a journey with stops: each leg eases in and out, and height changes by a constant factor so a long descent feels like a zoom
      const pts = [camTw.from, ...camTw.via, camTw.to], at = [0, ...camTw.via.map((v) => v.at), 1];
      let k = 0;
      while (k < pts.length - 2 && u > at[k + 1]) k++;
      const e = easeIO(clamp((u - at[k]) / (at[k + 1] - at[k]))), a = pts[k], b = pts[k + 1];
      camNow.pos.lerpVectors(a.pos, b.pos, e);
      if (a.pos.y > 40 && b.pos.y > 40) camNow.pos.y = a.pos.y * Math.pow(b.pos.y / a.pos.y, e);
      camNow.tgt.lerpVectors(a.tgt, b.tgt, e);
      camNow.fov = lerp(a.fov, b.fov, e);
    } else {
      const e = easeIO(u);
      camNow.pos.lerpVectors(camTw.from.pos, camTw.to.pos, e);
      camNow.pos.y += Math.sin(Math.PI * e) * camTw.lift;
      camNow.tgt.lerpVectors(camTw.from.tgt, camTw.to.tgt, e);
      camNow.fov = lerp(camTw.from.fov, camTw.to.fov, e);
    }
    if (u >= 1) camTw = null;
  }
  const calm = STILL || matchMedia("(prefers-reduced-motion: reduce)").matches;
  const k = calm ? 0 : 0.5;
  sway.set(Math.sin(clock * 0.31) * k, Math.sin(clock * 0.23 + 1) * k * 0.5, Math.cos(clock * 0.19) * k);
  if (shake > 0.001) { sway.x += (Math.random() - 0.5) * shake * 2.2; sway.y += (Math.random() - 0.5) * shake * 2.2; shake *= 0.9; }
  camera.position.copy(camNow.pos).add(sway);
  camera.lookAt(camNow.tgt);
  camera.fov = camNow.fov;
  const w = innerWidth, h = innerHeight;
  camera.aspect = w / h;
  if (Math.abs(vals.shift) + Math.abs(vals.vshift) > 1e-4) camera.setViewOffset(w, h, -vals.shift * w, vals.vshift * h, w, h);
  else camera.clearViewOffset();
  camera.updateProjectionMatrix();
  camera.updateMatrixWorld();
}
function frame(now) {
  requestAnimationFrame(frame);
  if (!running) return;
  const dt = Math.min((now - last) / 1000, 0.1);
  last = now;
  clock += dt;
  stepTweens();
  updateCamera();
  const env = applyTod(vals.tod, { sky, key, hemi, scene, renderer, bloom, mats, camTarget: camNow.tgt });
  scene.fog.density /= 1 + Math.max(0, camera.position.y - 300) / 120; // from the map view the air is clear
  W.update(dt, clock, env.night);
  A.update(dt, clock, S, camera, env.dSun, env.el);
  if (S.seal > 0.62 && prevSeal <= 0.62 && !STILL) shake = 1.4;
  prevSeal = S.seal;
  updateTags(A);
  for (const li of pills) li.classList.toggle("on", S[li.dataset.k] > +li.dataset.t);
  composer.render();
  // drop a quality level if the machine cannot hold about 28 fps
  frames++;
  acc += dt;
  if (!Q.has("q") && frames % 150 === 0) {
    if (acc / 150 > 1 / 28 && level < LEVELS.length - 1) { level++; applyLevel(); }
    acc = 0;
  }
}

/* ------------------------------------------------------------------ the 10-year table on the Range slide, filled from econ.js */
function fillEcon() {
  const r = compute(), top = 900000, pct = (v) => (100 * v) / top + "%";
  const set = (sel, v) => document.querySelectorAll(sel).forEach((el) => (el.textContent = v));
  set("[data-econ=grid-total]", pesoK(r.grid));
  for (const key of ["solar", "hybrid"]) {
    set(`[data-econ=${key}-up]`, range(r[key].upfront));
    set(`[data-econ=${key}-bills]`, range(r[key].bills));
    set(`[data-econ=${key}-total]`, range(r[key].total));
    const bar = $(`[data-bar=${key}]`);
    if (bar) { bar.style.left = pct(r[key].total[0]); bar.style.width = pct(r[key].total[1] - r[key].total[0]); }
  }
  const gb = $("[data-bar=grid]");
  if (gb) gb.style.left = pct(r.grid);
  document.querySelectorAll("[data-gridline]").forEach((el) => (el.style.left = pct(r.grid)));
  set("[data-econ=kwp]", r.kwp.toFixed(1));
  set("[data-econ=yield]", `${IN.yieldKwhPerKwp.bad.toLocaleString()} to ${IN.yieldKwhPerKwp.good.toLocaleString()}`);
}

/* ------------------------------------------------------------------ boot */
function fail(msg) {
  const f = $("#fail");
  f.hidden = false;
  f.innerHTML = msg;
}
const setProg = (p, t) => { $("#lbar").style.width = Math.round(p * 100) + "%"; if (t) $("#ltxt").textContent = t; };
const tickRaf = () => new Promise((r) => requestAnimationFrame(() => r()));
async function boot() {
  setProg(0.04, "Loading the model kit…");
  let geo;
  try {
    geo = await loadKit("world/kit.glb", (e) => e.total && setProg(0.04 + 0.6 * (e.loaded / e.total)));
  } catch (e) {
    fail("The 3D model kit could not load. Serve this folder instead of opening the file directly:<br><code>python3 -m http.server 8000</code>, then open <code>http://localhost:8000</code>.");
    throw e;
  }
  setProg(0.7, "Building the street…");
  await tickRaf();
  const kit = makeKit(geo);
  fillThumbs(kit);
  W = buildWorld(scene, kit);
  setProg(0.88, "Placing the story…");
  await tickRaf();
  A = createActors(scene, kit, W);
  fillEcon();
  applyLevel();
  const start = clamp(parseInt(Q.get("s") || location.hash.slice(1), 10) || 0, 0, slides.length - 1);
  go(start, true);
  for (const k in tw) { tw[k].obj[k] = tw[k].to; delete tw[k]; }
  if (Q.get("tod")) vals.tod = parseFloat(Q.get("tod"));
  if (Q.get("cam")) { const a = Q.get("cam").split(",").map(Number); camTw = null; camNow.pos.set(a[0], a[1], a[2]); camNow.tgt.set(a[3], a[4], a[5]); if (a[6]) camNow.fov = a[6]; }
  if (Q.get("set")) Q.get("set").split(",").forEach((kv) => { const [k, v] = kv.split(":"); S[k] = parseFloat(v); });
  window.__deck = { go, S, vals, camera, camNow, scene, renderer, get cur() { return cur; }, A, W, THREE };
  setProg(1, "Ready");
  last = performance.now();
  requestAnimationFrame(frame);
  await new Promise((r) => setTimeout(r, STILL ? 500 : 800));
  $("#loader").classList.add("gone");
  if (STILL) $("#loader").style.display = "none"; // test captures skip the fade
  setTimeout(() => hint.classList.add("gone"), 6000);
  document.body.dataset.ready = "1";
}
fit();
boot().catch((e) => { console.error(e); if ($("#fail").hidden) fail("Something went wrong while building the world.<br><code>" + (e && e.message ? e.message : e) + "</code>"); });
