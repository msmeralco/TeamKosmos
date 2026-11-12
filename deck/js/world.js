// The neighbourhood. Loads the Blender kit (world/kit.glb) and lays it out as one street, north side dense, south side open.
// Axes: x east, z south, y up. North is -z. Houses on the north side face south (+z), toward the street at z = 0.
import * as THREE from "three";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";

const UP = new THREE.Vector3(0, 1, 0);
export const T = 32;

export function rng(seed) {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

// materials shared by the whole world. win = windows and lamps (warm at night, glass by day). glow = always lit.
export const mats = {
  solid: new THREE.MeshStandardMaterial({ vertexColors: true, flatShading: true, roughness: 1, metalness: 0 }),
  cloud: new THREE.MeshStandardMaterial({ vertexColors: true, flatShading: true, roughness: 1, metalness: 0 }),
  win: new THREE.MeshBasicMaterial({ vertexColors: true, toneMapped: false }),
  glow: new THREE.MeshBasicMaterial({ vertexColors: true, toneMapped: false, color: new THREE.Color(1.6, 1.6, 1.6) }),
};

export async function loadKit(url, onProgress) {
  const gltf = await new GLTFLoader().loadAsync(url, onProgress);
  const geo = {};
  gltf.scene.traverse((o) => {
    if (o.isMesh) geo[o.name] = o.geometry;
  });
  return geo;
}

export function makeKit(geo) {
  const SUFFIX = [["", null], ["__e", mats.win], ["__g", mats.glow]];
  const parts = (name, solid) => SUFFIX.map(([s, m]) => [geo[name + s], m || solid]).filter(([g]) => g);
  const flags = (o, solid, cast, receive) => {
    o.frustumCulled = false;
    o.castShadow = solid && cast;
    o.receiveShadow = solid && receive;
  };
  return {
    has: (n) => !!geo[n],
    /** one movable object (a Group of up to three meshes) */
    group(name, { solid = mats.solid, cast = true, receive = true } = {}) {
      const g = new THREE.Group();
      g.name = name;
      for (const [geom, m] of parts(name, solid)) {
        const mesh = new THREE.Mesh(geom, m);
        flags(mesh, m === solid, cast, receive);
        g.add(mesh);
      }
      return g;
    },
    /** many copies of one model; matrices is an array of Matrix4 */
    instanced(name, matrices, { solid = mats.solid, cast = true, receive = true } = {}) {
      const g = new THREE.Group();
      g.name = name + "*";
      for (const [geom, m] of parts(name, solid)) {
        const im = new THREE.InstancedMesh(geom, m, matrices.length);
        matrices.forEach((mx, i) => im.setMatrixAt(i, mx));
        im.instanceMatrix.needsUpdate = true;
        flags(im, m === solid, cast, receive);
        g.add(im);
      }
      return g;
    },
  };
}

const FLAT = ["house_a", "house_b", "house_c", "house_d", "house_hero"];
const ALL_HOUSES = ["house_a", "house_b", "house_c", "house_d", "house_e", "house_f", "house_g"];
export const XI = [432, 832]; // N-S cross streets
const nearI = (x, pad = 0) => XI.some((i) => Math.abs(x - i) < 16 + pad);

export function buildWorld(scene, kit) {
  const R = rng(20261112);
  const W = { root: new THREE.Group(), roofs: [], lots: {}, lamps: [], poles: [], traffic: [], people: [], clouds: [], pools: null, wires: [] };
  scene.add(W.root);
  const list = {};
  const mat = (x, y, z, ry = 0, sx = 1, sy = sx, sz = sx) =>
    new THREE.Matrix4().compose(new THREE.Vector3(x, y, z), new THREE.Quaternion().setFromAxisAngle(UP, ry), new THREE.Vector3(sx, sy, sz));
  const put = (name, x, y, z, ry = 0, s = 1, sy = s) => (list[name] = list[name] || []).push(mat(x, y, z, ry, s, sy));
  const pick = (a) => a[Math.floor(R() * a.length)];

  /* ---------------------------------------------------------------- ground tiles */
  const inCourt = (x, z) => x > 688 && x < 752 && z > 48 && z < 112;
  const lot = (x, z) => x >= 112 && x <= 272 && (z === 32 || z === 64); // parking lot, south side
  const plaza = (x, z) => x >= 576 && x <= 672 && (z === 32 || z === 64);
  const stage = (x, z) => x >= 864 && x <= 1088 && (z === 32 || z === 64); // where the Passport and its chain stand (slide 8)
  for (let k = 0; k <= 38; k++) {
    const x = -96 + 32 * k;
    for (let z = -320; z <= 320; z += 32) {
      if (inCourt(x, z)) continue;
      let name = "grass_a", ry = 0;
      const vx = XI.find((i) => Math.abs(x - i) < 16);
      if (z === 0) name = vx ? "street_cross" : k % 7 === 3 ? "street_hx" : "street_h";
      else if (vx) { name = "street_h"; ry = Math.PI / 2; }
      else if (lot(x, z) || plaza(x, z) || stage(x, z)) name = "plaza";
      else {
        const r = R();
        name = r < 0.5 ? "grass_a" : r < 0.78 ? "grass_b" : "grass_c";
        ry = Math.floor(R() * 4) * (Math.PI / 2);
      }
      put(name, x, 0, z, ry);
    }
  }
  put("court", 720, 0, 80);

  /* ---------------------------------------------------------------- north lots: houses, gates, trees */
  const lots = [];
  for (let k = -2; k <= 19; k++) lots.push(26 + 52 * k);
  let prev = "";
  const SPECIAL = { 26: "house_c", 286: "house_a", 390: "house_hero", 494: "house_a", 546: "house_b", 598: "house_d" };
  for (const x of lots) {
    if (nearI(x, 26) || x === -26 || x === 702) continue;
    let name = SPECIAL[x];
    if (!name) { do name = pick(ALL_HOUSES); while (name === prev); }
    prev = name;
    const flat = FLAT.includes(name), floors = name === "house_e" || name === "house_f" ? 1 : 2;
    const hero = name === "house_hero", z = hero ? -40 : -37;   // the hero house is 48 x 32, so its centre sits further back to keep the same front line
    put(name, x, 0, z);
    put("gate", x, 0, -18);
    if (x !== 286) { put("fence", x + 10, 0, -18); put("fence", x - 10, 0, -18, Math.PI); } // lot 286 keeps its side open for the meter post
    const rec = { name, x, z, flat, floors, H: floors * 12 + 1, w: hero ? 48 : 32, d: hero ? 32 : 26 };
    W.lots[x] = rec;
    if (flat) W.roofs.push(rec);
    if (R() < 0.45) put(pick(["bush_f", "bush_a"]), x + pick([-14, 14]), 0, -21);
  }
  // trees in the gaps between houses and behind them
  const tree = (x, z) => {
    const r = R();
    if (((x > 348 && x < 452) || (x > 226 && x < 352)) && z > -70) return; // keep the hero house (x 390) and the meter house (x 286) visible from the street
    if (x > 840 && x < 1130 && z > 0) return; // the Passport stage
    if (r < 0.42) put(pick(["palm_a", "palm_b", "palm_c"]), x, 0, z, R() * 6.28);
    else if (r < 0.72) put(pick(["mango_a", "mango_b"]), x, 0, z, R() * 6.28);
    else if (r < 0.82) put("flame", x, 0, z, R() * 6.28);
    else if (r < 0.92) put("banana", x, 0, z, R() * 6.28);
    else put("bush_f", x, 0, z, R() * 6.28);
  };
  for (const x of lots) if (!nearI(x, 26) && x !== 26 && x !== 546 && x !== 286) tree(x + 26, -36 + (R() - 0.5) * 8);
  for (let x = -90; x < 1090; x += 18 + R() * 20) {
    if (nearI(x, 6)) continue;
    const z = -56 - R() * 70;
    if (z < -86 && z > -114 && ((x + 40) % 120 < 44)) continue; // midrise footprints below
    tree(x, z);
  }
  // mid-rises in the second row, for depth
  const mids = [];
  for (let x = -40; x < 1060; x += 120) {
    if (nearI(x, 30)) continue;
    const n = R() < 0.5 ? "midrise_a" : "midrise_b";
    put(n, x, 0, -100, 0);
    mids.push(x);
  }

  /* ---------------------------------------------------------------- south side: open, with a store, court, pavilion */
  put("sari_sari", 92, 0, 36, Math.PI);
  put("sedan_a", 62, 0, 26, Math.PI / 2);
  put("pavilion", 608, 0, 56);
  put("flag_ph", 664, 0, 24);
  put("hoop", 720, 0, 54, 0);
  put("hoop", 720, 0, 106, Math.PI);
  for (let x = -90; x < 1090; x += 16 + R() * 26) {
    if (nearI(x, 8) || (x > 100 && x < 290) || (x > 560 && x < 770)) continue;
    const z = 30 + R() * 90;
    if (x > 330 && x < 610 && z > 66) continue; // keep the wordmark clear
    tree(x, z);
  }
  for (let x = 40; x < 1000; x += 130) {
    if (nearI(x, 10) || (x > 100 && x < 290) || (x > 560 && x < 770)) continue;
    put("bench", x, 0, 20, Math.PI);
    put("bin", x + 18, 0, 19.5, 0);
  }

  /* ---------------------------------------------------------------- lamps and poles */
  for (let x = 0; x < 1100; x += 52) {
    if (nearI(x, 4)) continue;
    if (x + 26 !== 286) { put("lamp", x + 26, 0, -14, Math.PI); W.lamps.push([x + 26, 30, -14 + 8]); }
    put("lamp", x, 0, 14, 0);
    W.lamps.push([x, 30, 14 - 8]);
  }
  const poleXs = [];
  for (let x = -104; x < 1130; x += 104) {
    if (nearI(x, 3)) { x += 0; }
    poleXs.push(x);
    put("pole", x, 0, -14, 0);
    W.poles.push(x);
  }

  /* ---------------------------------------------------------------- far scenery */
  const hills = (n, x, z, ry, sx, sy) => put(n, x, -2, z, ry, sx, sy);
  [[-300, "hills_a"], [300, "hills_b"], [900, "hills_a"], [1500, "hills_b"]].forEach(([x, n]) => hills(n, x, -330, 0, 1.25, 1.25));
  hills("hills_a", 1300, -400, 0, 1.25, 1.25);
  hills("hills_b", 1380, 300, -Math.PI / 2, 1.2, 1.1);
  hills("hills_b", -560, 560, Math.PI / 2, 1.2, 1.1);
  put("skyline_a", -200, -2, -760, 0, 1.9, 1.9);
  put("skyline_b", 380, -2, -760, 0, 1.9, 1.9);
  put("skyline_a", 960, -2, -760, 0, 1.9, 1.9);
  put("skyline_b", 1480, -2, 40, -Math.PI / 2, 1.7, 1.7);
  put("skyline_a", 1480, -2, 640, -Math.PI / 2, 1.7, 1.7);

  /* ---------------------------------------------------------------- flush the lists into instanced meshes */
  const NOCAST = new Set(["grass_a", "grass_b", "grass_c", "street_h", "street_hx", "street_cross", "plaza", "court", "hills_a", "hills_b", "skyline_a", "skyline_b"]);
  const FAR = new Set(["hills_a", "hills_b", "skyline_a", "skyline_b"]);
  for (const [name, ms] of Object.entries(list)) {
    if (!kit.has(name)) { console.warn("missing model", name); continue; }
    const g = kit.instanced(name, ms, { cast: !NOCAST.has(name), receive: !FAR.has(name) });
    W.root.add(g);
  }

  // ground out to the horizon, so the tiled area never ends in a white band
  {
    const g = new THREE.Mesh(new THREE.PlaneGeometry(16000, 16000).rotateX(-Math.PI / 2), new THREE.MeshStandardMaterial({ color: 0x5f9a46, roughness: 1 }));
    g.position.set(500, -1, 0);
    g.receiveShadow = true;
    W.root.add(g);
  }

  /* ---------------------------------------------------------------- lamp pools (soft light on the ground at night) */
  {
    const c = document.createElement("canvas");
    c.width = c.height = 128;
    const x = c.getContext("2d"), gr = x.createRadialGradient(64, 64, 0, 64, 64, 64);
    gr.addColorStop(0, "rgba(255,196,110,0.85)");
    gr.addColorStop(0.45, "rgba(255,170,80,0.28)");
    gr.addColorStop(1, "rgba(255,160,60,0)");
    x.fillStyle = gr;
    x.fillRect(0, 0, 128, 128);
    const tex = new THREE.CanvasTexture(c);
    tex.colorSpace = THREE.SRGBColorSpace;
    W.poolMat = new THREE.MeshBasicMaterial({ map: tex, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, opacity: 0, toneMapped: false });
    const im = new THREE.InstancedMesh(new THREE.PlaneGeometry(1, 1).rotateX(-Math.PI / 2), W.poolMat, W.lamps.length);
    W.lamps.forEach((p, i) => im.setMatrixAt(i, mat(p[0], 1.6, p[2], 0, 46, 1, 46)));
    im.frustumCulled = false;
    W.root.add(im);
  }

  /* ---------------------------------------------------------------- power lines between the poles */
  {
    const wireMat = new THREE.MeshBasicMaterial({ color: 0x2a2f38, transparent: true, opacity: 0.8 });
    const offs = [[60, -11], [60, 11], [52, 0]];
    for (let i = 0; i < poleXs.length - 1; i++) {
      for (const [h, dz] of offs) {
        const a = poleXs[i] + 0.5, b = poleXs[i + 1] + 0.5, pts = [];
        for (let s = 0; s <= 10; s++) {
          const u = s / 10;
          pts.push(new THREE.Vector3(a + (b - a) * u, h + 3 - Math.sin(Math.PI * u) * 4.2, -14 - dz));
        }
        const m = new THREE.Mesh(new THREE.TubeGeometry(new THREE.CatmullRomCurve3(pts), 14, 0.11, 4), wireMat);
        m.frustumCulled = false;
        W.root.add(m);
      }
    }
  }

  /* ---------------------------------------------------------------- traffic and people */
  const addTraffic = (name, x, lane, speed, dir) => {
    const g = kit.group(name);
    g.position.set(x, 0, lane);
    g.rotation.y = dir > 0 ? 0 : Math.PI;
    scene.add(g);
    W.traffic.push({ g, speed: speed * dir, lane });
  };
  const kinds = ["jeepney_a", "jeepney_b", "tricycle_a", "sedan_b", "van"];
  for (let i = 0; i < 9; i++) {
    const dir = i % 2 ? -1 : 1;
    addTraffic(kinds[i % kinds.length], -100 + i * 140 + R() * 40, dir > 0 ? 5.5 : -5.5, 13 + R() * 9, dir);
  }
  const looks = ["person_a", "person_b", "person_c", "person_d", "person_e"];
  for (let i = 0; i < 18; i++) {
    const g = kit.group(looks[i % 5]);
    const side = i % 2 ? 14 : -14;
    g.position.set(-80 + i * 62 + R() * 30, 1, side + (R() - 0.5) * 3);
    const sp = (2.2 + R() * 2) * (R() < 0.5 ? -1 : 1);
    g.rotation.y = sp > 0 ? Math.PI / 2 : -Math.PI / 2;
    scene.add(g);
    W.people.push({ g, sp, ph: R() * 6 });
  }
  { const d = kit.group("dog"); d.position.set(60, 1, 13); d.rotation.y = Math.PI / 2; scene.add(d); W.people.push({ g: d, sp: 3.6, ph: 0 }); }

  /* ---------------------------------------------------------------- clouds that drift over */
  for (let i = 0; i < 12; i++) {
    const g = kit.group(pick(["cloud_a", "cloud_b", "cloud_c"]), { solid: mats.cloud, cast: false, receive: false });
    const s = 2.4 + R() * 2;
    g.scale.set(s, s * 0.8, s);
    g.position.set(-300 + R() * 1700, 190 + R() * 80, -420 + R() * 700);
    scene.add(g);
    W.clouds.push({ g, v: 1.2 + R() * 1.6 });
  }

  W.update = (dt, t, nightK) => {
    for (const c of W.traffic) {
      c.g.position.x += c.speed * dt;
      if (c.g.position.x > 1160) c.g.position.x = -140;
      if (c.g.position.x < -140) c.g.position.x = 1160;
    }
    for (const p of W.people) {
      p.g.position.x += p.sp * dt;
      p.g.position.y = 1 + Math.abs(Math.sin(t * 7 + p.ph)) * 0.5;
      if (p.g.position.x > 1120) p.g.position.x = -120;
      if (p.g.position.x < -120) p.g.position.x = 1120;
    }
    for (const c of W.clouds) {
      c.g.position.x += c.v * dt;
      if (c.g.position.x > 1500) c.g.position.x = -320;
    }
    W.poolMat.opacity = Math.min(1, nightK * 1.15);
  };
  return W;
}
