/* Shared, deterministic drawing code for the Sol reels.
   Every function is a pure function of time (seconds) plus seeded data built once at load, so any frame can be rendered in any order. */
(function () {
  const TAU = Math.PI * 2;
  const COL = { night: "#12100e", cream: "#fafaf9", paper: "#f4f4f2", ink: "#111111", orange: "#ea580c", sun: "#fbd554", sunDeep: "#f4b92f", blue: "#1d4ed8", skyBlue: "#60a5fa", teal: "#2f7f78", tealDark: "#235f5a" };

  function rng(seed) {
    let a = seed >>> 0;
    return function () {
      a |= 0; a = (a + 0x6d2b79f5) | 0;
      let t = Math.imul(a ^ (a >>> 15), 1 | a);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }
  const clamp = (x, a = 0, b = 1) => Math.min(b, Math.max(a, x));
  const lerp = (a, b, t) => a + (b - a) * t;
  const prog = (s, a, b) => clamp((s - a) / (b - a));
  const E = {
    outCubic: (t) => 1 - Math.pow(1 - t, 3),
    inCubic: (t) => t * t * t,
    inOutCubic: (t) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2),
    inOutSine: (t) => -(Math.cos(Math.PI * t) - 1) / 2,
    outExpo: (t) => (t >= 1 ? 1 : 1 - Math.pow(2, -10 * t)),
    outBack: (t) => { const c1 = 1.70158, c3 = c1 + 1; return 1 + c3 * Math.pow(t - 1, 3) + c1 * Math.pow(t - 1, 2); },
  };
  function hex(c) { return [parseInt(c.slice(1, 3), 16), parseInt(c.slice(3, 5), 16), parseInt(c.slice(5, 7), 16)]; }
  function mix(c1, c2, t) { const a = hex(c1), b = hex(c2); return `rgb(${Math.round(lerp(a[0], b[0], t))},${Math.round(lerp(a[1], b[1], t))},${Math.round(lerp(a[2], b[2], t))})`; }
  function shade(rgbStr, f) { const m = rgbStr.match(/\d+/g).map(Number); return `rgb(${Math.round(m[0] * f)},${Math.round(m[1] * f)},${Math.round(m[2] * f)})`; }
  function pad(n, w) { return String(Math.floor(n)).padStart(w, "0"); }
  function timecode(t, fps) { const f = Math.floor(t * fps + 1e-6); return `${pad(0, 2)}:${pad(Math.floor(f / (fps * 60)), 2)}:${pad(Math.floor(f / fps) % 60, 2)}:${pad(f % fps, 2)}`; }
  function group(n, sep = ",") { return String(Math.round(n)).replace(/\B(?=(\d{3})+(?!\d))/g, sep); }

  /* ---- 1. Squash and stretch: a ball dropped on a surface ------------------------------------------------------------- */
  const BOUNCE = { g: 5200, e: 0.62, t0: 0.12 };
  /** Height above the ground (px), vertical speed, bounce number and time since the last impact, at local time s. */
  function bounceState(s, H) {
    const { g, e, t0 } = BOUNCE;
    let t = s - t0;
    if (t < 0) return { y: H, vy: 0, n: 1, since: -1 };
    const tf = Math.sqrt((2 * H) / g);
    if (t < tf) return { y: H - 0.5 * g * t * t, vy: -g * t, n: 1, since: -1 };
    t -= tf;
    let v = g * tf * e, n = 1;
    for (;;) {
      const air = (2 * v) / g;
      if (air < 0.06 || n > 8) return { y: 0, vy: 0, n, since: t };
      if (t < air) return { y: v * t - 0.5 * g * t * t, vy: v - g * t, n: n + 1, since: t };
      t -= air; v *= e; n++;
    }
  }
  function bounceArcs(H) {
    const { g, e, t0 } = BOUNCE; const arcs = []; const tf = Math.sqrt((2 * H) / g);
    arcs.push({ a: t0, b: t0 + tf, v: 0, base: H, first: true });
    let t = t0 + tf, v = g * tf * e;
    for (let n = 0; n < 8; n++) { const air = (2 * v) / g; if (air < 0.06) break; arcs.push({ a: t, b: t + air, v, base: 0 }); t += air; v *= e; }
    return arcs;
  }
  function bounceEnd(H) { const arcs = bounceArcs(H); return arcs[arcs.length - 1].b; }
  /** Draws the ground line, dotted trajectories and impact rings; returns the ball's screen state for the DOM mascot.
   *  Options: light (dark ink on a light ground), labels (readout text, default on), alpha, x0 / vx (horizontal start and speed). */
  function bounceScene(ctx, w, h, s, o = {}) {
    const size = o.size || h * 0.15, H = o.drop || h * 0.55, ground = h * (o.ground || 0.8), x0 = o.x0 ?? w * 0.16, vx = o.vx ?? w * 0.17;
    const light = !!o.light, labels = o.labels !== false, line = light ? "17,17,17" : "250,250,249";
    ctx.clearRect(0, 0, w, h);
    const u = h / 1080, arcs = bounceArcs(H), tEnd = arcs[arcs.length - 1].b, sm = Math.min(s, tEnd);
    ctx.globalAlpha = o.alpha ?? 1;
    // ground: a roof line with panel ticks
    const gx0 = w * (o.span ? 0.5 - o.span / 2 : 0.06), gx1 = w * (o.span ? 0.5 + o.span / 2 : 0.94);
    ctx.strokeStyle = `rgba(${line},0.85)`; ctx.lineWidth = 2 * u; ctx.beginPath(); ctx.moveTo(gx0, ground); ctx.lineTo(gx1, ground); ctx.stroke();
    ctx.strokeStyle = `rgba(${line},0.2)`; ctx.lineWidth = 1 * u;
    for (let x = gx0; x <= gx1; x += 24 * u) { ctx.beginPath(); ctx.moveTo(x, ground); ctx.lineTo(x - 14 * u, ground + 14 * u); ctx.stroke(); }
    if (labels) { ctx.fillStyle = `rgba(${line},0.55)`; ctx.font = `${Math.max(9, 17 * u)}px Menlo, monospace`; ctx.fillText("ROOF  y = 0", gx0, ground + 38 * u); }
    // trajectories (dotted), drawn up to the current time
    for (const a of arcs) {
      if (s < a.a) continue;
      const end = Math.min(s, a.b);
      for (let t = a.a; t <= end; t += 0.022) {
        const lt = t - a.a; const y = a.first ? H - 0.5 * BOUNCE.g * lt * lt : a.v * lt - 0.5 * BOUNCE.g * lt * lt;
        const x = x0 + vx * (t - BOUNCE.t0);
        ctx.fillStyle = a.first ? "rgba(244,185,47,0.95)" : "rgba(234,88,12,0.8)";
        ctx.beginPath(); ctx.arc(x, ground - y - size * 0.5, 2.8 * u, 0, TAU); ctx.fill();
      }
    }
    // impact rings
    for (const a of arcs) {
      const hit = a.first ? a.b : a.a; if (s < hit) continue;
      const age = s - hit; if (age > 0.5) continue;
      const x = x0 + vx * (hit - BOUNCE.t0);
      ctx.strokeStyle = `rgba(234,88,12,${1 - age / 0.5})`; ctx.lineWidth = 2.4 * u;
      ctx.beginPath(); ctx.ellipse(x, ground, (30 + age * 260) * u, (6 + age * 40) * u, 0, 0, TAU); ctx.stroke();
    }
    const st = bounceState(s, H);
    const x = x0 + vx * Math.max(0, sm - BOUNCE.t0);
    // shadow
    const sh = 1 - clamp(st.y / H) * 0.65;
    ctx.fillStyle = light ? `rgba(17,17,17,${0.2 * sh})` : `rgba(0,0,0,${0.45 * sh})`; ctx.beginPath(); ctx.ellipse(x, ground + 4 * u, size * 0.5 * sh, size * 0.09 * sh, 0, 0, TAU); ctx.fill();
    const by = ground - st.y - size * 0.5;
    if (labels) {
      ctx.strokeStyle = `rgba(${line},0.35)`; ctx.setLineDash([4 * u, 5 * u]); ctx.beginPath(); ctx.moveTo(x, by); ctx.lineTo(x, ground); ctx.stroke(); ctx.setLineDash([]);
      ctx.fillStyle = COL.orange; ctx.font = `bold ${Math.max(9, 20 * u)}px Menlo, monospace`;
      ctx.fillText(`#${st.n} / Y:${(st.y + size * 0.5 + (o.offsetY || 0)).toFixed(2)}`, x + size * 0.62, by - 8 * u);
    }
    ctx.globalAlpha = 1;
    // squash and stretch for the DOM mascot
    let sx = 1, sy = 1;
    if (st.since >= 0 && st.since < 0.1) { const k = Math.sin((Math.PI * st.since) / 0.1) * 0.46; sy = 1 - k; sx = 1 + k * 0.85; }
    else { const k = clamp(Math.abs(st.vy) / 9500, 0, 0.2); sy = 1 + k; sx = 1 / Math.sqrt(sy); }
    const tilt = (clamp(st.vy / 9000, -0.25, 0.25) * 0.9 + (sm - BOUNCE.t0) * 0.06) * (s < tEnd ? 1 : 0);
    return { x, bottom: ground - st.y, size, sx, sy, tilt, state: st, tEnd };
  }

  /* ---- 2. Crosses and dots that morph into an isometric grid of pillars with a rolling sun orb ------------------------ */
  const GRID = (function () {
    const cols = 24, rows = 14, r = rng(77); const cells = [];
    for (let j = 0; j < rows; j++) for (let i = 0; i < cols; i++) cells.push({ i, j, blue: r() < 0.14, tall: r() < 0.08 ? 0.5 + r() * 0.5 : 0, ph: r() * TAU });
    return { cols, rows, cells };
  })();
  function cellHeight(c, s, cx, cy) {
    const { i, j } = c;
    const wave = 0.5 + 0.5 * Math.sin(i * 0.46 + s * 1.7) * Math.cos(j * 0.58 - s * 1.2);
    const d = Math.hypot(i - cx, j - cy); const ring = 0.5 + 0.5 * Math.cos(d * 0.7 - s * 3.2);
    return clamp(0.12 + 0.5 * wave * 0.7 + 0.35 * ring * Math.exp(-d / 12) + c.tall * 0.55, 0, 1);
  }
  function gridScene(ctx, w, h, s, o = {}) {
    const { cols, rows, cells } = GRID; const u = h / 1080;
    ctx.clearRect(0, 0, w, h);
    const k = E.inOutCubic(prog(s, o.morphA ?? 1.35, o.morphB ?? 2.3)); // 0 = flat field of crosses, 1 = isometric pillars
    const tw = w * 0.034, th = tw * 0.5, isoOx = w * 0.5 - ((cols - rows) / 2) * (tw / 2), isoOy = h * 0.335;
    const top = (i, j) => [w * 0.07 + (i * w * 0.86) / (cols - 1), h * 0.16 + (j * h * 0.68) / (rows - 1)];
    const iso = (i, j) => [isoOx + (i - j) * (tw / 2), isoOy + (i + j) * (th / 2)];
    const pos = (i, j) => { const a = top(i, j), b = iso(i, j); return [lerp(a[0], b[0], k), lerp(a[1], b[1], k)]; };
    const amp = h * 0.235 * Math.pow(k, 1.4);
    const sphere = (() => { // the sun orb rolls diagonally over the terrain
      const u2 = prog(s, o.orbA ?? 1.75, o.orbB ?? 3.0); if (u2 <= 0 || u2 >= 1) return null;
      const gi = lerp(2, cols - 3, E.inOutSine(u2)), gj = 2 + (rows - 5) * (0.5 + 0.5 * Math.sin(u2 * 3.4 - 0.6));
      return { gi, gj, u2 };
    })();
    const order = cells.slice().sort((a, b) => a.i + a.j - (b.i + b.j));
    let sphereDrawn = false; const sd = sphere ? Math.round(sphere.gi + sphere.gj) : -1;
    const drawSphere = () => {
      sphereDrawn = true; const c = cells[Math.round(sphere.gj) * cols + Math.round(sphere.gi)];
      const hh = cellHeight(c, s, cols / 2, rows / 2) * amp; const p = pos(sphere.gi, sphere.gj);
      const r = h * 0.035; const bounce = Math.abs(Math.sin(sphere.u2 * 22)) * 22 * u; const y = p[1] - hh - r - bounce;
      ctx.fillStyle = `rgba(0,0,0,${0.35 - bounce / 120})`; ctx.beginPath(); ctx.ellipse(p[0], p[1] - hh, r * 0.9, r * 0.32, 0, 0, TAU); ctx.fill();
      const g = ctx.createRadialGradient(p[0] - r * 0.3, y - r * 0.3, r * 0.1, p[0], y, r * 2.4);
      g.addColorStop(0, "rgba(255,243,168,1)"); g.addColorStop(0.35, "rgba(251,213,84,0.95)"); g.addColorStop(0.5, "rgba(234,88,12,0.35)"); g.addColorStop(1, "rgba(234,88,12,0)");
      ctx.fillStyle = g; ctx.beginPath(); ctx.arc(p[0], y, r * 2.4, 0, TAU); ctx.fill();
      ctx.fillStyle = COL.sun; ctx.beginPath(); ctx.arc(p[0], y, r, 0, TAU); ctx.fill();
    };
    for (const c of order) {
      if (sphere && !sphereDrawn && c.i + c.j > sd) drawSphere();
      const [px, py] = pos(c.i, c.j); const dist = Math.hypot(c.i - cols / 2, c.j - rows / 2);
      const pulse = 0.55 + 0.45 * Math.sin(s * TAU * 2 - dist * 0.42); // one pulse per beat at 120 BPM
      if (k < 1) { // crosses and dots
        const a = (1 - k) * (0.28 + 0.6 * pulse * pulse);
        ctx.strokeStyle = pulse > 0.82 ? `rgba(234,88,12,${a * 1.4})` : `rgba(250,250,249,${a})`; ctx.fillStyle = ctx.strokeStyle; ctx.lineWidth = 1.6 * u;
        if ((c.i + c.j) % 2 === 0) { const L = (4 + 7 * pulse) * u * (1 - k * 0.6); ctx.beginPath(); ctx.moveTo(px - L, py); ctx.lineTo(px + L, py); ctx.moveTo(px, py - L); ctx.lineTo(px, py + L); ctx.stroke(); }
        else { ctx.beginPath(); ctx.arc(px, py, (1.6 + 2.2 * pulse) * u, 0, TAU); ctx.fill(); }
      }
      if (k > 0.02) { // pillars
        const hn = cellHeight(c, s, cols / 2 + Math.sin(s) * 3, rows / 2), H = hn * amp, hw = lerp(3 * u, tw / 2, k), hh = lerp(2 * u, th / 2, k);
        const base = c.blue ? mix("#1e3a8a", COL.skyBlue, hn) : hn < 0.5 ? mix("#4a2c1a", COL.orange, hn / 0.5) : mix(COL.orange, COL.sun, (hn - 0.5) / 0.5);
        ctx.globalAlpha = clamp(k * 1.6);
        ctx.fillStyle = shade(base, 0.62); ctx.beginPath(); ctx.moveTo(px - hw, py); ctx.lineTo(px, py + hh); ctx.lineTo(px, py + hh - H); ctx.lineTo(px - hw, py - H); ctx.closePath(); ctx.fill();
        ctx.fillStyle = shade(base, 0.42); ctx.beginPath(); ctx.moveTo(px + hw, py); ctx.lineTo(px, py + hh); ctx.lineTo(px, py + hh - H); ctx.lineTo(px + hw, py - H); ctx.closePath(); ctx.fill();
        ctx.fillStyle = base; ctx.beginPath(); ctx.moveTo(px, py - hh - H); ctx.lineTo(px + hw, py - H); ctx.lineTo(px, py + hh - H); ctx.lineTo(px - hw, py - H); ctx.closePath(); ctx.fill();
        ctx.globalAlpha = 1;
      }
    }
    if (sphere && !sphereDrawn) drawSphere();
    return { k };
  }

  /* ---- 3. Particles: a sun ring bursts apart, drifts, then reforms as a looping helix --------------------------------- */
  function makeParticles(n, seed) {
    const r = rng(seed); const P = { n, ang: new Float32Array(n), spd: new Float32Array(n), ring: new Float32Array(n), u: new Float32Array(n), dly: new Float32Array(n), col: new Uint8Array(n), size: new Float32Array(n), ph: new Float32Array(n) };
    for (let i = 0; i < n; i++) {
      P.ang[i] = r() * TAU; P.spd[i] = 260 + Math.pow(r(), 1.5) * 1500; P.ring[i] = 0.82 + r() * 0.36; P.u[i] = (i / n) * TAU; P.dly[i] = r() * 0.4;
      const c = r(); P.col[i] = c < 0.5 ? 0 : c < 0.8 ? 1 : 2; P.size[i] = 1.3 + r() * 2.3; P.ph[i] = r() * TAU;
    }
    return P;
  }
  const PCOL = ["rgba(250,250,249,0.8)", "rgba(234,88,12,0.85)", "rgba(96,165,250,0.85)"];
  function particleScene(ctx, w, h, s, P, o = {}) {
    ctx.clearRect(0, 0, w, h);
    const u = h / 1080, cx = w * 0.5, cy = h * 0.5, R0 = h * 0.17, a = w * (o.loop || 0.27);
    const tBurst = 0.5, tReform = 1.25;
    const free = (i, t) => { // sun ring, then burst and drift
      const ang = P.ang[i] + (t < tBurst ? t * 1.6 : tBurst * 1.6 + (t - tBurst) * 0.35); const r0 = R0 * P.ring[i];
      if (t < tBurst) return [cx + Math.cos(ang) * r0, cy + Math.sin(ang) * r0];
      const d = P.spd[i] * u * (1 - Math.exp(-(t - tBurst) * 1.9)); const sw = Math.sin((t - tBurst) * 2 + P.ph[i]) * 14 * u;
      return [cx + Math.cos(ang) * (r0 + d) + sw, cy + Math.sin(ang) * (r0 + d) * 0.62 + Math.cos((t - tBurst) * 1.7 + P.ph[i]) * 14 * u];
    };
    const loop = (i, t) => { // lemniscate with a twisting helix depth
      const th = P.u[i] + t * 0.5, den = 1 + Math.sin(th) * Math.sin(th);
      const tube = (10 + 26 * P.ring[i] * P.ring[i]) * u * (0.5 + 0.5 * Math.sin(P.ph[i] * 3.1)), tw = P.ph[i] + th * 2 + t * 2.2;
      let X = (a * Math.cos(th)) / den, Y = (a * Math.sin(th) * Math.cos(th)) / den * 1.25 + Math.cos(tw) * tube, Z = a * 0.32 * Math.sin(2 * th + t * 3.0) + Math.sin(tw) * tube;
      const yaw = 0.55 * Math.sin(t * 1.1); const x2 = X * Math.cos(yaw) + Z * Math.sin(yaw), z2 = -X * Math.sin(yaw) + Z * Math.cos(yaw);
      const pr = 1100 / (1100 - z2); return [cx + x2 * pr, cy + Y * pr, pr];
    };
    ctx.globalCompositeOperation = "lighter";
    for (let c = 0; c < 3; c++) {
      ctx.fillStyle = PCOL[c];
      for (let i = 0; i < P.n; i++) {
        if (P.col[i] !== c) continue;
        let x, y, sz = P.size[i] * u;
        if (s < tReform) { const p = free(i, s); x = p[0]; y = p[1]; }
        else {
          const q = E.inOutCubic(clamp((s - tReform - P.dly[i]) / 0.75)); const f = free(i, tReform), l = loop(i, s);
          x = lerp(f[0], l[0], q); y = lerp(f[1], l[1], q); sz *= lerp(1, l[2], q);
        }
        ctx.fillRect(x, y, sz, sz);
      }
    }
    ctx.globalCompositeOperation = "source-over";
  }

  window.Reel = { TAU, COL, rng, clamp, lerp, prog, E, mix, timecode, group, bounceScene, bounceEnd, gridScene, makeParticles, particleScene, BOUNCE };
})();
