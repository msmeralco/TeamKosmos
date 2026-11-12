// The story pieces. Everything here is driven by the scalar state S (see main.js), so a step only has to say what it wants.
import * as THREE from "three";
import { mats } from "./world.js";

const cl = (v, a = 0, b = 1) => Math.min(b, Math.max(a, v));
const seg = (v, a, b) => cl((v - a) / (b - a));
const lerp1 = (a, b, t) => a + (b - a) * t;
const ease = (t) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2);
const outBack = (t) => 1 + 2.4 * Math.pow(t - 1, 3) + 1.4 * Math.pow(t - 1, 2);
const amberMat = () => new THREE.MeshBasicMaterial({ color: new THREE.Color(1.7, 1.05, 0.3), toneMapped: false });

// places the panels of a roof. cols x rows, tilted toward the street
const PANEL_SLOTS = [-10, 0, 10].flatMap((dx) => [8, 1].map((dz) => [dx, dz]));
const HERO_SLOTS = [9, 2].flatMap((dz) => [-15.75, -5.25, 5.25, 15.75].map((dx) => [dx, dz])); // 4 x 2 panels on the wide hero roof

const HDR = (r, g, b) => new THREE.MeshBasicMaterial({ color: new THREE.Color(r, g, b), toneMapped: false });
const WIRE = { amber: [0.9, 0.56, 0.14], cyan: [0.16, 0.62, 0.85] };
const COL = { amber: [1.7, 1.05, 0.3], cyan: [0.35, 1.35, 1.8], green: [0.4, 1.7, 0.6], red: [2.0, 0.35, 0.3], wire: [0.78, 0.82, 0.92] };

export const POS = {
  jan: [-38, -30], oct: [-12, -30],               // coin towers
  sellers: [160, 198, 236], sellerZ: 50, rackZ: 34, // the three sellers and the solar they sell
  meterHouse: 286, stand: [299, -13], pole: [312.5, -14.5], // meter story: house, meter post, Meralco pole
  solarHouse: 390,                               // the hero house: map, blueprint, install, chat
  range: [494, 546, 598],                        // three weather years
  strata: [702, -48],
  passport: [888, 44], // the Passport stage
  word: [470, 104],
};

/** a wire drawn as a row of small cubes along a polyline; set(f) reveals the first f of it */
function makeWire(pts, mat, thick = 1.1) {
  const vs = pts.map((p) => new THREE.Vector3(...p)), pos = [];
  for (let i = 0; i < vs.length - 1; i++) {
    const n = Math.max(1, Math.round(vs[i].distanceTo(vs[i + 1]) / (thick * 0.85)));
    for (let k = 0; k < n; k++) pos.push(vs[i].clone().lerp(vs[i + 1], k / n));
  }
  pos.push(vs[vs.length - 1].clone());
  const im = new THREE.InstancedMesh(new THREE.BoxGeometry(thick, thick, thick), mat, pos.length);
  pos.forEach((p, i) => im.setMatrixAt(i, new THREE.Matrix4().makeTranslation(p.x, p.y, p.z)));
  im.frustumCulled = false;
  im.count = 0;
  return { mesh: im, n: pos.length, vs, set(f) { im.count = Math.floor(cl(f) * pos.length + (f >= 1 ? 1 : 0)); im.visible = im.count > 0; } };
}
const pathLen = (vs) => vs.slice(1).reduce((a, p, i) => a + p.distanceTo(vs[i]), 0);
const along = (vs, u) => {
  const lens = vs.slice(1).map((p, i) => p.distanceTo(vs[i]));
  let d = cl(u) * lens.reduce((a, b) => a + b, 0), i = 0;
  while (i < lens.length - 1 && d > lens[i]) d -= lens[i++];
  return new THREE.Vector3().lerpVectors(vs[i], vs[i + 1], cl(d / lens[i]));
};
const cat = (...paths) => paths.reduce((a, p) => a.concat(a.length ? p.slice(1) : p), []);

export function createActors(scene, kit, W) {
  const A = { anchors: {} };
  let Sref = { solX: 0, solY: 0, solZ: 0 }; // latest scene state, for anchors that follow Sol
  const root = new THREE.Group();
  scene.add(root);
  const _m = new THREE.Matrix4(), _q = new THREE.Quaternion(), _e = new THREE.Euler(), _p = new THREE.Vector3(), _s = new THREE.Vector3();
  const setM = (im, i, x, y, z, rx, ry, rz, sx, sy = sx, sz = sx) => {
    _e.set(rx, ry, rz, "YXZ");
    _q.setFromEuler(_e);
    _m.compose(_p.set(x, y, z), _q, _s.set(sx, sy, sz));
    im.setMatrixAt(i, _m);
  };
  const hide = (g, on) => (g.visible = on);
  const setCount = (g, n) => g.children.forEach((c) => (c.count = n));

  /* ---------------------------------------------------------------- 1. coin towers (1 voxel = ₱0.35 of the kWh rate) */
  const tower = (n, x, z) => {
    const ms = Array.from({ length: n }, (_, i) => new THREE.Matrix4().compose(new THREE.Vector3(x, i, z), new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0, 1, 0), i * 0.5), new THREE.Vector3(1, 0.5, 1)));
    const g = kit.instanced("coin", ms);
    root.add(g);
    return { g, n, x, z };
  };
  const jan = tower(37, POS.jan[0], POS.jan[1]);
  const oct = tower(43, POS.oct[0], POS.oct[1]);
  const coinLight = new THREE.PointLight(0xffc36a, 0, 190, 2);   // a warm light on the towers, so they are the first thing you see
  coinLight.position.set((jan.x + oct.x) / 2, 34, jan.z + 26);
  root.add(coinLight);
  A.anchors.jan = () => new THREE.Vector3(jan.x, 41, jan.z);
  A.anchors.oct = () => new THREE.Vector3(oct.x, 47, oct.z);

  /* ---------------------------------------------------------------- 2. three sellers, with the same solar rack behind each */
  const SELL = ["seller_a", "seller_b", "seller_c"];
  const sellers = POS.sellers.map((x, i) => {
    const rack = kit.group("solar_rack"), p = kit.group(SELL[i]);
    rack.scale.setScalar(1);
    rack.position.set(x, 0, POS.rackZ);
    p.scale.setScalar(0.8);
    p.position.set(x, 0, POS.sellerZ);
    root.add(rack, p);
    A.anchors["talk" + i] = () => new THREE.Vector3(x, 31, POS.sellerZ);
    A.anchors["price" + i] = () => new THREE.Vector3(x, 0.5, POS.sellerZ + 13);
    return { rack, p };
  });

  const stageLight = new THREE.PointLight(0xffd9a0, 0, 230, 2);   // warm light on the three sellers
  stageLight.position.set(190, 46, 92);
  root.add(stageLight);

  /* ---------------------------------------------------------------- 3. the meter story: panels, meter post, pole and the power that moves between them */
  const [SPX, SPZ] = POS.stand, [POX, POZ] = POS.pole;
  const stand = kit.group("meter_stand");
  stand.scale.setScalar(0.8);
  stand.position.set(SPX, 0, SPZ);
  root.add(stand);
  const recQ = kit.group("word_q");                       // the "?" on the empty REC meter slot
  recQ.scale.setScalar(0.34);
  recQ.position.set(SPX, 13.2, SPZ + 3.3);
  root.add(recQ);
  const wDC = makeWire([[278, 29.9, -33], [SPX, 29.9, -33], [SPX, 29.9, SPZ - 2.6], [SPX, 36, SPZ - 2.6]], HDR(...WIRE.amber), 1.5);
  const wHome = makeWire([[SPX - 4.9, 7.6, SPZ - 1.5], [POS.meterHouse + 5.5, 7.6, SPZ - 1.5], [POS.meterHouse + 5.5, 7.6, -21.6]], HDR(...WIRE.amber), 1.5);
  const wGrid = makeWire([[SPX + 4.9, 7.6, SPZ - 1.5], [POX - 1.9, 7.6, SPZ - 1.5], [POX - 1.9, 61.5, SPZ - 1.5], [POX + 70, 61.5, SPZ - 1.5]], HDR(...WIRE.cyan), 1.5);
  root.add(wDC.mesh, wHome.mesh, wGrid.mesh);
  const rev = (w) => [...w.vs].reverse();
  const pSolar = wDC.vs, pHome = wHome.vs, pOut = wGrid.vs, pIn = cat(rev({ vs: pOut }), pHome);
  const mkFlow = (n, mat) => { const im = new THREE.InstancedMesh(new THREE.BoxGeometry(1, 1, 1), mat, n); im.frustumCulled = false; root.add(im); return im; };
  const fSolar = mkFlow(10, HDR(...COL.amber)), fHome = mkFlow(5, HDR(...COL.amber)), fOut = mkFlow(4, HDR(...COL.amber)), fIn = mkFlow(11, HDR(...COL.cyan));
  A.anchors.panels3 = () => new THREE.Vector3(POS.meterHouse, 36, -33);
  A.anchors.inverter = () => new THREE.Vector3(SPX + 5.5, 26.6, SPZ + 1);
  A.anchors.recm = () => new THREE.Vector3(SPX + 5.5, 17.2, SPZ + 1);
  A.anchors.netm = () => new THREE.Vector3(SPX + 5.5, 8, SPZ + 1);
  A.anchors.home = () => new THREE.Vector3(POS.meterHouse - 14, 14, -23);
  A.anchors.gridPole = () => new THREE.Vector3(POX + 2, 55, POZ);

  /* ---------------------------------------------------------------- 4. the hero house: map pin, roof outline, blueprint, crew, install */
  const HR = W.lots[POS.solarHouse], RH = HR.H + 4.6, RX = HR.x, RZ = HR.z;
  const ringPts = [];
  {
    const hx = HR.w / 2 + 0.5, hz = HR.d / 2 + 0.5, step = 2.2;
    const corners = [[-hx, hz], [hx, hz], [hx, -hz], [-hx, -hz], [-hx, hz]];
    for (let c = 0; c < 4; c++) {
      const [ax, az] = corners[c], [bx, bz] = corners[c + 1];
      const n = Math.floor(Math.hypot(bx - ax, bz - az) / step);
      for (let i = 0; i < n; i++) ringPts.push([RX + ax + ((bx - ax) * i) / n, RZ + az + ((bz - az) * i) / n]);
    }
  }
  const ring = new THREE.InstancedMesh(new THREE.BoxGeometry(1.1, 1.1, 1.1), HDR(0.8, 0.52, 0.15), ringPts.length);
  ring.frustumCulled = false;
  ringPts.forEach((p, i) => setM(ring, i, p[0], RH, p[1], 0, 0, 0, 1));
  root.add(ring);

  const pin = kit.group("map_pin", { cast: false, receive: false });
  root.add(pin);
  let pinScale = 1;
  A.anchors.pin = () => new THREE.Vector3(RX, 31 + 34 * pinScale, RZ);

  // the blueprint laid on the roof, drawn into a canvas
  const BW = HR.w - 2, BD = HR.d - 2, CW = 1104, CH = Math.round((CW * BD) / BW);
  const planCv = Object.assign(document.createElement("canvas"), { width: CW, height: CH });
  const px = CW / BW;
  const planTex = new THREE.CanvasTexture(planCv);
  planTex.colorSpace = THREE.SRGBColorSpace;
  planTex.anisotropy = 8;
  const planMat = new THREE.MeshBasicMaterial({ map: planTex, transparent: true, depthWrite: false, toneMapped: false });
  const plan = new THREE.Mesh(new THREE.PlaneGeometry(BW, BD).rotateX(-Math.PI / 2), planMat);
  plan.position.set(RX, HR.H + 0.35, RZ);
  plan.renderOrder = 5;
  root.add(plan);
  const ctx = planCv.getContext("2d");
  const FONT = '"Figtree", "Instrument Sans", system-ui, sans-serif';
  let planKey = "";
  const slotRect = ([dx, dz]) => [(dx + BW / 2 - 5) * px, (dz + BD / 2 - 3) * px, 10 * px, 6 * px];
  const drawPlan = (p, landed) => {
    const key = Math.round(p * 160) + ":" + landed.map((l) => (l > 0.98 ? 1 : 0)).join("");
    if (key === planKey) return;
    planKey = key;
    ctx.clearRect(0, 0, CW, CH);
    if (p <= 0.001) { planTex.needsUpdate = true; return; }
    ctx.fillStyle = "rgba(14,52,122,0.78)";
    ctx.fillRect(0, 0, CW, CH);
    ctx.globalAlpha = ease(seg(p, 0.04, 0.3)) * 0.34;
    ctx.strokeStyle = "#cfe6ff";
    ctx.lineWidth = 1.5;
    for (let x = 0; x <= BW; x += 2) { ctx.beginPath(); ctx.moveTo(x * px, 0); ctx.lineTo(x * px, CH); ctx.stroke(); }
    for (let y = 0; y <= BD; y += 2) { ctx.beginPath(); ctx.moveTo(0, y * px); ctx.lineTo(CW, y * px); ctx.stroke(); }
    ctx.globalAlpha = 1;
    // the roof edge, drawn on
    const per = 2 * (CW + CH), f = ease(seg(p, 0.2, 0.5));
    ctx.strokeStyle = "#f3f8ff";
    ctx.lineWidth = 9;
    ctx.setLineDash([per * f, per]);
    ctx.strokeRect(5, 5, CW - 10, CH - 10);
    ctx.setLineDash([]);
    // dimensions
    const dimA = ease(seg(p, 0.42, 0.6));
    ctx.globalAlpha = dimA;
    ctx.fillStyle = ctx.strokeStyle = "#f3f8ff";
    ctx.lineWidth = 4;
    ctx.font = `500 46px ${FONT}`;
    ctx.textAlign = "center";
    ctx.beginPath(); ctx.moveTo(40, CH - 46); ctx.lineTo(CW - 40, CH - 46); ctx.stroke();
    ctx.fillText(`${(BW * 0.25).toFixed(1)} m`, CW / 2, CH - 60);
    ctx.save(); ctx.translate(46, CH / 2); ctx.rotate(-Math.PI / 2);
    ctx.beginPath(); ctx.moveTo(-CH / 2 + 46, 0); ctx.lineTo(CH / 2 - 46, 0); ctx.stroke();
    ctx.fillText(`${(BD * 0.25).toFixed(1)} m`, 0, -14);
    ctx.restore();
    ctx.textAlign = "left";
    ctx.font = `500 40px ${FONT}`;
    ctx.fillText("ROOF LAYOUT  ·  8 PANELS", 110, 74);
    ctx.globalAlpha = 1;
    // panel outlines
    HERO_SLOTS.forEach((sl, k) => {
      const g = ease(seg(p, 0.52 + k * 0.045, 0.6 + k * 0.045));
      if (g <= 0.001) return;
      const [x, y, w, h] = slotRect(sl);
      ctx.globalAlpha = g;
      if (landed[k] > 0.98) {
        ctx.fillStyle = "rgba(70,210,190,0.38)";
        ctx.fillRect(x, y, w, h);
        ctx.strokeStyle = "#8ff0dc";
        ctx.setLineDash([]);
      } else {
        ctx.strokeStyle = "#f3f8ff";
        ctx.setLineDash([22, 14]);
      }
      ctx.lineWidth = 6;
      ctx.strokeRect(x + 4, y + 4, w - 8, h - 8);
      ctx.setLineDash([]);
      ctx.fillStyle = landed[k] > 0.98 ? "#e8fff9" : "#f3f8ff";
      ctx.textAlign = "center";
      ctx.font = `500 54px ${FONT}`;
      ctx.fillText(String(k + 1), x + w / 2, y + h / 2 + 19);
    });
    ctx.globalAlpha = 1;
    planTex.needsUpdate = true;
  };

  // panels: lowered onto their outlines one by one, each landing throws a few sparks
  const makePanels = (roofs, delayOf, slots = PANEL_SLOTS) => {
    const items = [];
    roofs.forEach((r) => slots.forEach(([dx, dz], k) => items.push({ x: r.x + dx, z: r.z + dz, y: r.H + 0.3, k, d: delayOf(r, k, items.length) })));
    const g = kit.instanced("panel", items.map(() => new THREE.Matrix4()));
    g.children.forEach((c) => (c.castShadow = true));
    root.add(g);
    const im = g.children[0];
    return {
      g, items, last: -1, land: items.map(() => 0),
      update(v) {
        if (Math.abs(v - this.last) < 1e-4) return;
        this.last = v;
        this.items.forEach((it, i) => {
          const p = seg(v * 1.6, it.d, it.d + 0.5);
          this.land[i] = p;
          if (p <= 0) setM(im, i, it.x, -50, it.z, 0, 0, 0, 0.001);
          else setM(im, i, it.x, it.y + Math.max(0, 1 - outBack(p)) * 95 * (p < 1 ? 1 : 0), it.z, 0.27, 0, 0, 1);
        });
        im.instanceMatrix.needsUpdate = true;
        g.visible = v > 0;
      },
    };
  };
  const demo = makePanels([HR], (r, k) => k * 0.09, HERO_SLOTS);
  const rangeSets = makePanels([W.lots[POS.range[1]], W.lots[POS.range[2]]], (r, k, n) => (n % 12) * 0.05);
  const cityRoofs = W.roofs.filter((r) => r.x !== POS.solarHouse && !POS.range.includes(r.x));
  const city = makePanels(cityRoofs, (r, k) => (r.x / 1100) * 0.55 + k * 0.03);
  const roof3 = makePanels([W.lots[POS.meterHouse]], (r, k) => k * 0.08);
  A.anchors.house = () => new THREE.Vector3(RX, RH + 14, RZ);
  A.anchors.layout = () => new THREE.Vector3(RX + 6, RH - 1, RZ + 17);

  const NSP = 8 * HERO_SLOTS.length;
  const sparks = new THREE.InstancedMesh(new THREE.BoxGeometry(1, 1, 1), amberMat(), NSP);
  sparks.frustumCulled = false;
  root.add(sparks);
  // a soft teal glow on every landed panel, so the solar is what the eye goes to
  const glowMat = new THREE.MeshBasicMaterial({ color: new THREE.Color(0.2, 0.85, 1.0), transparent: true, opacity: 0.4, blending: THREE.AdditiveBlending, depthWrite: false, toneMapped: false });
  const glow = new THREE.InstancedMesh(new THREE.BoxGeometry(9.6, 0.2, 5.8), glowMat, HERO_SLOTS.length);
  glow.frustumCulled = false;
  root.add(glow);
  const crewA = kit.group("installer_a"), crewB = kit.group("installer_b");
  crewA.scale.setScalar(0.42);
  crewB.scale.setScalar(0.42);
  crewA.position.set(RX - 15.75, HR.H, RZ + 13.4);
  root.add(crewA, crewB);
  A.anchors.crew = () => new THREE.Vector3(crewA.position.x, HR.H + 12, crewA.position.z);
  A.anchors.gate = () => new THREE.Vector3(RX, 14, RZ + 19);

  /* ---------------------------------------------------------------- 5. the homeowner who talks to Sol */
  const owner = kit.group("owner");
  owner.scale.setScalar(0.7);
  owner.position.set(RX - 14, 0, -10);
  root.add(owner);
  A.anchors.owner = () => new THREE.Vector3(RX - 14, 27, -10);
  A.anchors.chat = () => new THREE.Vector3(Sref.solX + 1, Sref.solY + 14, Sref.solZ);
  A.anchors.chip0 = () => new THREE.Vector3(RX - 20, 44, RZ + 6);
  A.anchors.chip1 = () => new THREE.Vector3(RX, 52, RZ + 6);
  A.anchors.chip2 = () => new THREE.Vector3(RX + 20, 46, RZ + 6);

  /* ---------------------------------------------------------------- 6. three skies */
  const storm = kit.group("storm_a", { solid: mats.cloud, cast: false, receive: false });
  storm.scale.setScalar(2.3);
  storm.position.set(POS.range[0], 82, -34);
  root.add(storm);
  const cloudMid = kit.group("cloud_b", { solid: mats.cloud, cast: false, receive: false });
  cloudMid.scale.setScalar(1.9);
  cloudMid.position.set(POS.range[1] + 4, 94, -40);
  root.add(cloudMid);
  const RN = 160;
  const rain = new THREE.InstancedMesh(new THREE.BoxGeometry(0.45, 5, 0.45), new THREE.MeshBasicMaterial({ color: 0xa9cdf0, transparent: true, opacity: 0.85 }), RN);
  rain.frustumCulled = false;
  const rdrop = Array.from({ length: RN }, (_, i) => ({ x: (Math.random() - 0.5) * 50, z: (Math.random() - 0.5) * 34, ph: Math.random(), sp: 70 + Math.random() * 30 }));
  root.add(rain);
  const shadow = new THREE.Mesh(new THREE.CircleGeometry(30, 28).rotateX(-Math.PI / 2), new THREE.MeshBasicMaterial({ color: 0x0b1020, transparent: true, opacity: 0, depthWrite: false }));
  shadow.position.set(POS.range[0], 1.8, -37);
  root.add(shadow);
  const batt = kit.group("battery"), inv = kit.group("inverter");
  batt.position.set(POS.range[2] - 30, 0, -27);
  inv.position.set(POS.range[2] - 21, 0, -27);
  root.add(batt, inv);
  A.anchors.grid = () => new THREE.Vector3(POS.range[0], 52, -30);
  A.anchors.solar = () => new THREE.Vector3(POS.range[1], 52, -30);
  A.anchors.skyL = () => new THREE.Vector3(POS.range[0], 98, -30);
  A.anchors.parts = () => new THREE.Vector3(POS.range[2] - 25, 18, -27);
  A.anchors.hybrid = () => new THREE.Vector3(POS.range[2], 52, -30);

  /* ---------------------------------------------------------------- 7. the strata */
  const [SX, SZ] = POS.strata;
  const layers = ["prices", "credit", "tariff", "weather"].map((n, i) => {
    const g = kit.group("layer_" + n);
    root.add(g);
    return { g, base: i * 5, lift: i * 24, name: n };
  });
  const plotHouse = kit.group("house_e");
  root.add(plotHouse);
  A.anchors.weather = () => new THREE.Vector3(SX + 22, layers[3].g.position.y + 4, SZ + 14);
  A.anchors.tariff = () => new THREE.Vector3(SX + 22, layers[2].g.position.y + 4, SZ + 14);
  A.anchors.credit = () => new THREE.Vector3(SX + 22, layers[1].g.position.y + 4, SZ + 14);
  A.anchors.prices = () => new THREE.Vector3(SX + 22, layers[0].g.position.y + 4, SZ + 14);

  /* ---------------------------------------------------------------- 8. the Passport: the seal is the installer's confirmation, the vouchers are what it unlocks */
  const [PX, PZ] = POS.passport;
  const pass = kit.group("passport");
  pass.scale.setScalar(1.3);
  pass.position.set(PX, 0, PZ);
  root.add(pass);
  const seal = kit.group("seal");
  root.add(seal);
  // three vouchers the Passport unlocks: voxel tickets (amber body, white tear-off stub, notches)
  const vouch = new THREE.Group(), ticketMat = [HDR(0.95, 0.6, 0.16), HDR(0.9, 0.88, 0.8)];
  for (let i = 0; i < 3; i++) {
    const tk = new THREE.Group();
    const body = new THREE.Mesh(new THREE.BoxGeometry(22, 11, 1.6), ticketMat[0]), stub = new THREE.Mesh(new THREE.BoxGeometry(5, 11, 1.8), ticketMat[1]);
    stub.position.x = 8.5;
    tk.add(body, stub);
    for (const y of [-5.5, 5.5]) { const n = new THREE.Mesh(new THREE.BoxGeometry(2.4, 2.4, 2.4), HDR(0.05, 0.08, 0.14)); n.position.set(6, y, 0); tk.add(n); }
    tk.position.set((i - 1) * 4, i * 13, -i * 2); tk.rotation.z = [0.07, -0.08, 0.05][i];
    vouch.add(tk);
  }
  vouch.position.set(PX + 54, 6, PZ + 12); vouch.userData.s = 0.9;
  root.add(vouch);
  A.anchors.reward = () => new THREE.Vector3(PX + 54, 44, PZ + 12);
  A.anchors.passport = () => new THREE.Vector3(PX, 62, PZ);
  A.anchors.seal = () => new THREE.Vector3(PX + 13, 36, PZ + 7);

  /* ---------------------------------------------------------------- 9. the word, and Sol */
  const word = kit.group("word_sol");
  word.position.set(POS.word[0], 0, POS.word[1]);
  word.scale.setScalar(2.4);
  root.add(word);
  const sol = kit.group("sol");
  root.add(sol);
  A.anchors.sol = () => new THREE.Vector3(sol.position.x, sol.position.y + 11 * sol.scale.x, sol.position.z);
  const dots = new THREE.InstancedMesh(new THREE.BoxGeometry(1.4, 1.4, 1.4), amberMat(), 3);
  dots.frustumCulled = false;
  root.add(dots);
  const sunMat = mats.glow.clone();
  sunMat.fog = false;
  const sun = kit.group("sun_big");
  sun.traverse((o) => o.isMesh && (o.material = sunMat));
  sun.scale.setScalar(13);
  scene.add(sun);

  /* ================================================================ per-frame */
  A.update = (dt, t, S, cam, sunDir, el) => {
    // coin towers: the newest coin drops in
    for (const [tw, v] of [[jan, S.coinsJ], [oct, S.coinsO]]) {
      const f = v * tw.n, n = Math.floor(f);
      setCount(tw.g, Math.min(tw.n, n + 1));
      tw.g.visible = v > 0.001;
      // the coin that was dropping goes back to rest exactly where it belongs, so no coin is left hanging mid-air or hidden
      if (tw.last !== undefined && tw.last !== n && tw.last < tw.n) tw.g.children.forEach((im) => { setM(im, tw.last, tw.x, tw.last, tw.z, 0, tw.last * 0.5, 0, 1, 0.5, 1); im.instanceMatrix.needsUpdate = true; });
      tw.last = n;
      if (v > 0.001 && n < tw.n) {
        const fr = f - n;
        tw.g.children.forEach((im) => { setM(im, n, tw.x, n + (1 - ease(fr)) * 14, tw.z, 0, n * 0.5, 0, 1, 0.5, 1); im.instanceMatrix.needsUpdate = true; });
      }
    }
    Sref = S;
    coinLight.intensity = 3200 * Math.max(S.coinsJ, S.coinsO);
    stageLight.intensity = 5200 * ease(S.sellers);
    // sellers pop in one after another
    sellers.forEach((o, i) => {
      const k = outBack(seg(S.sellers * 1.7, i * 0.25, i * 0.25 + 0.5));
      o.rack.visible = o.p.visible = S.sellers > 0.01;
      o.rack.scale.setScalar(Math.max(0.001, k));
      o.p.scale.setScalar(0.8 * Math.max(0.001, k));
      o.p.rotation.y = Math.sin(t * 0.9 + i * 2) * 0.12;
      o.p.position.y = Math.max(0, Math.sin(t * 2.2 + i) * 0.35);
    });
    // the meter story: wires draw on, then three streams of cubes start one after the other
    {
      const w = ease(S.wire);
      stand.visible = recQ.visible = S.wire > 0.01;
      stand.scale.setScalar(0.8 * Math.max(0.001, ease(seg(S.wire, 0, 0.5))));
      wDC.set(seg(w, 0.1, 0.55)); wHome.set(seg(w, 0.4, 0.8)); wGrid.set(seg(w, 0.6, 1));
      recQ.position.y = 13.2 + Math.sin(t * 2) * 0.5;
      recQ.scale.setScalar(0.34 * Math.max(0.001, ease(seg(S.wire, 0.4, 0.8))));
      const stream = (im, path, n, speed, size, k) => {
        im.visible = k > 0.01;
        for (let i = 0; i < n; i++) {
          const u = (t * speed + i / n) % 1, p = along(path, u), e = u > 0.94 ? (1 - u) / 0.06 : u < 0.04 ? u / 0.04 : 1;
          setM(im, i, p.x, p.y, p.z, t, t * 0.7, 0, size * k * e);
        }
        im.instanceMatrix.needsUpdate = true;
      };
      stream(fSolar, pSolar, 10, 0.16, 2.8, S.flowS);
      stream(fHome, pHome, 5, 0.2, 2.8, S.flowS);
      stream(fOut, pOut, 4, 0.1, 1.9, S.flowX);
      stream(fIn, pIn, 11, 0.12, 2.8, S.flowI);
    }
    // the map pin: stays the same size on screen, then lets go as the camera comes in
    {
      const d = cam.position.distanceTo(new THREE.Vector3(RX, 30, RZ));
      pinScale = Math.max(0.1, d * 0.0017) * S.pin;
      pin.visible = S.pin > 0.01;
      pin.scale.setScalar(Math.max(0.001, pinScale));
      pin.position.set(RX, 31 + Math.sin(t * 2.4) * 2 * pinScale, RZ);
      pin.rotation.y = t * 1.2;
    }
    // roof outline, blueprint, panels, crew, sparks
    ring.count = Math.floor(S.ring * ringPts.length);
    ring.visible = ring.count > 0;
    demo.update(S.drop);
    rangeSets.update(S.range);
    city.update(S.city);
    roof3.update(S.roof3);
    {
      const done = demo.land.reduce((a, l) => a + (l >= 1 ? 1 : 0), 0) / demo.land.length;
      plan.visible = S.plan > 0.01 && S.planOut < 0.98;
      planMat.opacity = 1 - 0.9 * ease(S.planOut);
      drawPlan(S.plan, demo.land);
      // the crew: one walks along the row being filled, the other watches the lift
      const cur = Math.min(demo.land.length - 1, demo.land.findIndex((l) => l < 1) < 0 ? demo.land.length - 1 : demo.land.findIndex((l) => l < 1));
      const [sx, sz] = HERO_SLOTS[cur];
      const ck = Math.max(0.001, ease(S.crew));
      crewA.visible = crewB.visible = S.crew > 0.01;
      crewA.scale.setScalar(0.42 * ck);
      crewB.scale.setScalar(0.42 * ck);
      crewA.position.set(RX + lerp1(crewA.position.x - RX, sx, 0.06), HR.H, RZ + 13.4);
      crewB.position.set(RX - 19 + Math.sin(t * 0.7) * 3, HR.H, RZ - 2 + Math.cos(t * 0.5) * 2);
      crewA.position.y = HR.H + Math.max(0, Math.sin(t * 6)) * 0.4;
      crewB.rotation.y = Math.sin(t * 0.7) * 0.5;
      sparks.visible = S.drop > 0.01 && S.drop < 0.999;
      demo.items.forEach((it, i) => {
        const lt = seg(S.drop * 1.6, it.d + 0.44, it.d + 0.7);
        for (let j = 0; j < 8; j++) {
          const an = (j / 8) * Math.PI * 2, r = lt * 7, on = lt > 0 && lt < 1;
          setM(sparks, i * 8 + j, it.x + Math.cos(an) * r, it.y + 1.5 + lt * 5 * (1 - lt) * 3, it.z + Math.sin(an) * r * 0.7, 0, 0, 0, on ? 0.9 * (1 - lt) : 0.001);
        }
      });
      sparks.instanceMatrix.needsUpdate = true;
      demo.items.forEach((it, i) => {
        const pop = Math.sin(Math.PI * seg(S.drop * 1.6, it.d + 0.5, it.d + 0.95));
        setM(glow, i, it.x, it.y + 1.7, it.z, 0.27, 0, 0, demo.land[i] >= 1 ? 1 + 0.4 * pop : 0.001);
      });
      glow.instanceMatrix.needsUpdate = true;
      glow.visible = S.drop > 0.01;
      glowMat.opacity = 0.32 + 0.1 * Math.sin(t * 2.2);
      owner.visible = S.chat > 0.01;
      owner.scale.setScalar(0.7 * Math.max(0.001, ease(S.chat)));
      owner.position.y = Math.max(0, Math.sin(t * 2.6)) * 0.5;
    }
    // weather
    {
      const k = S.weather;
      storm.visible = cloudMid.visible = k > 0.01;
      storm.scale.setScalar(2.3 * k);
      cloudMid.scale.setScalar(1.9 * k);
      storm.position.x = POS.range[0] + Math.sin(t * 0.3) * 3;
      cloudMid.position.x = POS.range[1] + 4 + Math.sin(t * 0.2 + 1) * 4;
      rain.visible = k > 0.5;
      rdrop.forEach((d, i) => {
        const y = 80 - (((t * d.sp + d.ph * 78) % 78) + 0);
        setM(rain, i, POS.range[0] + d.x, y, -37 + d.z, 0, 0, 0, 1);
      });
      rain.instanceMatrix.needsUpdate = true;
      shadow.material.opacity = 0.32 * k;
      batt.visible = inv.visible = S.range > 0.5;
    }
    // strata
    {
      const a = ease(S.apart);
      layers.forEach((l) => {
        l.g.position.set(SX, l.base + l.lift * a, SZ);
        l.g.rotation.y = a * 0.28;
      });
      plotHouse.position.set(SX, 20 + 72 * a, SZ);
      plotHouse.rotation.y = a * 0.28;
      const lk = Math.max(0.001, ease(S.layers));
      layers.forEach((l) => { l.g.visible = S.layers > 0.01; l.g.scale.setScalar(lk); });
      plotHouse.visible = S.layers > 0.01;
      plotHouse.scale.setScalar(lk);
    }
    // passport, then the installer's seal, then the vouchers
    {
      const pk = ease(S.passport);
      pass.visible = pk > 0.01;
      pass.scale.setScalar(1.3 * Math.max(0.001, pk));
      pass.position.y = (1 - pk) * -6;
      const sp = seg(S.seal, 0, 1), e = outBack(sp);
      seal.visible = sp > 0.01;
      seal.position.set(PX + 9, 14 + Math.max(0, 1 - e) * 60, PZ + 5 + (1 - sp) * 8);
      seal.scale.setScalar(1.3 + (1 - sp) * 1.4);
      seal.rotation.y = (1 - sp) * 0.6;
      const rp = seg(S.reward, 0, 1), re = outBack(rp);
      vouch.visible = rp > 0.01;
      vouch.scale.setScalar(Math.max(0.001, re) * vouch.userData.s);
      vouch.position.y = 7 + Math.sin(t * 1.6) * 0.8;
      vouch.rotation.y = (1 - rp) * 1.2 + Math.sin(t * 0.7) * 0.05;
    }
    // wordmark
    word.visible = S.word > 0.01;
    word.scale.set(2.4, 2.4 * Math.max(0.01, ease(S.word)), 2.4);
    // Sol
    {
      sol.visible = S.solS > 0.02;
      sol.position.set(S.solX, S.solY + Math.sin(t * 1.6) * 1.6, S.solZ);
      sol.scale.setScalar(Math.max(0.001, S.solS));
      sol.rotation.y = Math.atan2(cam.position.x - sol.position.x, cam.position.z - sol.position.z);
      sol.rotation.z = Math.sin(t * 1.1) * 0.08;
      dots.visible = S.dots > 0.01;
      for (let i = 0; i < 3; i++) setM(dots, i, S.solX + 8 + i * 3.4, S.solY + 8 + Math.max(0, Math.sin(t * 5 - i * 0.9)) * 2, S.solZ, 0, 0, 0, S.dots);
      dots.instanceMatrix.needsUpdate = true;
    }
    // the voxel sun, kept at the same direction as the real light
    sun.visible = el > -6;
    sun.position.copy(cam.position).addScaledVector(sunDir, 3200);
    sun.quaternion.copy(cam.quaternion);
  };
  A.pass = pass;
  A.seal = seal;
  return A;
}
