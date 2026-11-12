import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { SolMark } from "./SolMark";
import { useReducedMotion } from "./ui";

/* Animated Sol brand mascot (Three.js).
   - 12 rays drift, pulse and lean toward the cursor.
   - Face turns and eyes follow the cursor when it is near; otherwise Sol glances around on its own.
   - Blinks, breathes, bobs. Pauses when off-screen or the tab is hidden.
   - prefers-reduced-motion: renders one static frame. No WebGL: falls back to <SolMark />. */

const RAY_COUNT = 12;
const RAY_RING = 1.27;
const VIEW = 1.7; // half-extent of the orthographic view, in scene units

const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v));
const smoothstep = (a: number, b: number, v: number) => {
  const t = clamp((v - a) / (b - a), 0, 1);
  return t * t * (3 - 2 * t);
};

const VERT = /* glsl */ `
  varying vec3 vN;
  void main() {
    vN = normalize(normalMatrix * normal);
    gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
  }
`;

/* Soft, slightly translucent-looking ball: light centre, saturated rim, faint top-left sheen.
   The camera is orthographic, so the view direction is always +Z in view space.\n   Colours are kept as raw sRGB values and mixed in sRGB (no linear conversion) so they match the SVG mark. */
const FRAG = /* glsl */ `
  uniform vec3 uInner;
  uniform vec3 uOuter;
  uniform float uSheen;
  varying vec3 vN;
  void main() {
    vec3 n = normalize(vN);
    float rim = pow(1.0 - clamp(n.z, 0.0, 1.0), 1.7);
    vec3 col = mix(uInner, uOuter, rim);
    vec3 L = normalize(vec3(-0.45, 0.6, 0.65));
    col += vec3(1.0, 0.97, 0.82) * pow(clamp(dot(n, L), 0.0, 1.0), 5.0) * uSheen;
    col *= 0.94 + 0.06 * n.y;
    gl_FragColor = vec4(col, 1.0);
  }
`;

function ballMaterial(inner: string, outer: string, sheen: number) {
  return new THREE.ShaderMaterial({
    vertexShader: VERT,
    fragmentShader: FRAG,
    uniforms: {
      uInner: { value: new THREE.Color().setStyle(inner, THREE.LinearSRGBColorSpace) },
      uOuter: { value: new THREE.Color().setStyle(outer, THREE.LinearSRGBColorSpace) },
      uSheen: { value: sheen },
    },
  });
}

function radialTexture(stops: [number, string][]) {
  const c = document.createElement("canvas");
  c.width = c.height = 128;
  const g = c.getContext("2d");
  if (g) {
    const grad = g.createRadialGradient(64, 64, 0, 64, 64, 64);
    for (const [o, col] of stops) grad.addColorStop(o, col);
    g.fillStyle = grad;
    g.fillRect(0, 0, 128, 128);
  }
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.SRGBColorSpace;
  return t;
}

/* Put an object on the unit sphere at (x, y), facing outward. */
function place(obj: THREE.Object3D, x: number, y: number, lift = 0) {
  const z = Math.sqrt(Math.max(0, 1 - x * x - y * y));
  const n = new THREE.Vector3(x, y, z);
  obj.position.copy(n).multiplyScalar(1 + lift);
  obj.quaternion.setFromUnitVectors(new THREE.Vector3(0, 0, 1), n);
}

/* Face parts are drawn over the body without depth testing, in a fixed order. */
function faceMat<T extends THREE.Material>(m: T): T {
  m.depthTest = false;
  m.depthWrite = false;
  return m;
}

interface Options {
  size: number;
  followRadius: number;
  animate: boolean;
  /** Loader mode: rays spin fast, the face looks straight ahead and ignores the cursor. */
  loading: boolean;
  /** prefers-reduced-motion: the loader still turns, but slowly (same pace as the other spinners). */
  calm: boolean;
}

function createSol(container: HTMLElement, { size, followRadius, animate, loading, calm }: Options) {
  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: "low-power" });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  renderer.setSize(size, size);
  renderer.setClearColor(0x000000, 0);
  renderer.domElement.style.display = "block";
  renderer.domElement.style.pointerEvents = "none";
  container.appendChild(renderer.domElement);

  const scene = new THREE.Scene();
  const camera = new THREE.OrthographicCamera(-VIEW, VIEW, VIEW, -VIEW, 0.1, 10);
  camera.position.z = 5;

  scene.add(new THREE.AmbientLight(0xffffff, 1.4));
  const key = new THREE.DirectionalLight(0xffffff, 2.4);
  key.position.set(-1, 1.2, 2);
  scene.add(key);

  const root = new THREE.Group();
  scene.add(root);

  /* soft halo behind everything */
  const glow = new THREE.Mesh(
    new THREE.PlaneGeometry(VIEW * 2, VIEW * 2),
    new THREE.MeshBasicMaterial({
      map: radialTexture([
        [0, "rgba(255,214,90,0.4)"],
        [0.5, "rgba(255,214,90,0.16)"],
        [0.78, "rgba(255,214,90,0.06)"],
        [1, "rgba(255,214,90,0)"],
      ]),
      transparent: true,
      depthWrite: false,
    }),
  );
  glow.position.z = -2;
  root.add(glow);

  /* rays */
  const rayGeo = new THREE.SphereGeometry(0.13, 24, 16);
  const rayMat = ballMaterial("#fff3a8", "#f8cf4e", 0.05);
  const rayRing = new THREE.Group();
  const rays: THREE.Mesh[] = [];
  for (let i = 0; i < RAY_COUNT; i++) {
    const m = new THREE.Mesh(rayGeo, rayMat);
    rayRing.add(m);
    rays.push(m);
  }
  root.add(rayRing);

  /* body */
  const bodyGeo = new THREE.SphereGeometry(1, 64, 48);
  const bodyMat = ballMaterial("#ffec8f", "#f4b92f", 0.08);
  const body = new THREE.Mesh(bodyGeo, bodyMat);
  root.add(body);

  /* face (turns as one piece) */
  const face = new THREE.Group();
  root.add(face);

  const cheekTex = radialTexture([
    [0, "rgba(240,101,124,0.9)"],
    [0.55, "rgba(240,101,124,0.55)"],
    [1, "rgba(240,101,124,0)"],
  ]);
  const cheekGeo = new THREE.PlaneGeometry(0.34, 0.22);
  for (const sx of [-1, 1]) {
    const c = new THREE.Mesh(cheekGeo, faceMat(new THREE.MeshBasicMaterial({ map: cheekTex, transparent: true })));
    c.renderOrder = 1;
    place(c, sx * 0.56, -0.2, 0.004);
    face.add(c);
  }

  /* mouth: open smile with a tongue */
  const mouth = new THREE.Group();
  place(mouth, 0, -0.2, 0.006);
  face.add(mouth);
  const mouthShape = new THREE.Shape();
  mouthShape.moveTo(-0.17, 0.07);
  mouthShape.quadraticCurveTo(0, 0.1, 0.17, 0.07);
  mouthShape.bezierCurveTo(0.15, -0.1, 0.06, -0.13, 0, -0.13);
  mouthShape.bezierCurveTo(-0.06, -0.13, -0.15, -0.1, -0.17, 0.07);
  const mouthMesh = new THREE.Mesh(
    new THREE.ShapeGeometry(mouthShape, 20),
    faceMat(new THREE.MeshBasicMaterial({ color: "#4a1414" })),
  );
  mouthMesh.renderOrder = 2;
  mouth.add(mouthMesh);
  const tongueShape = new THREE.Shape();
  tongueShape.absellipse(0, -0.088, 0.062, 0.036, 0, Math.PI * 2, false, 0);
  const tongue = new THREE.Mesh(
    new THREE.ShapeGeometry(tongueShape, 20),
    faceMat(new THREE.MeshBasicMaterial({ color: "#ef6b7b" })),
  );
  tongue.renderOrder = 3;
  tongue.position.z = 0.001;
  mouth.add(tongue);

  /* eyes */
  const eyeGeo = new THREE.SphereGeometry(0.15, 32, 24);
  const eyeMat = faceMat(new THREE.MeshStandardMaterial({ color: "#2b0e0a", roughness: 0.3, metalness: 0 }));
  const sheenGeo = new THREE.CircleGeometry(0.1, 32);
  const sheenMat = faceMat(
    new THREE.MeshBasicMaterial({
      map: radialTexture([
        [0, "rgba(160,78,50,0.8)"],
        [1, "rgba(160,78,50,0)"],
      ]),
      transparent: true,
    }),
  );
  const hiGeoBig = new THREE.CircleGeometry(0.042, 24);
  const hiGeoSmall = new THREE.CircleGeometry(0.02, 20);
  const hiMat = faceMat(new THREE.MeshBasicMaterial({ color: "#ffffff", transparent: true }));

  const eyes: { g: THREE.Group; base: THREE.Vector3 }[] = [];
  for (const sx of [-1, 1]) {
    const g = new THREE.Group();
    place(g, sx * 0.45, 0.09, 0.006);
    const ball = new THREE.Mesh(eyeGeo, eyeMat);
    ball.scale.set(1, 1.12, 0.6);
    ball.renderOrder = 4;
    const sheen = new THREE.Mesh(sheenGeo, sheenMat);
    sheen.position.set(0, -0.055, 0.092);
    sheen.renderOrder = 5;
    const hiBig = new THREE.Mesh(hiGeoBig, hiMat);
    hiBig.position.set(-0.045, 0.058, 0.098);
    hiBig.renderOrder = 6;
    const hiSmall = new THREE.Mesh(hiGeoSmall, hiMat);
    hiSmall.position.set(0.05, -0.055, 0.098);
    hiSmall.renderOrder = 6;
    g.add(ball, sheen, hiBig, hiSmall);
    face.add(g);
    eyes.push({ g, base: g.position.clone() });
  }

  const render = () => renderer.render(scene, camera);

  /* ---------------- animation state ---------------- */
  const pointer = { x: 0, y: 0, has: false };
  const gaze = new THREE.Vector2();
  const idle = { x: 0, y: 0, until: 0 };
  let nextBlink = 1.5 + Math.random() * 2;
  let blinkStart = -1;

  const frame = (t: number, dt: number) => {
    /* where is the cursor relative to Sol? */
    let w = 0;
    let cgx = 0;
    let cgy = 0;
    if (pointer.has) {
      const r = container.getBoundingClientRect();
      const dx = pointer.x - (r.left + r.width / 2);
      const dy = pointer.y - (r.top + r.height / 2);
      w = 1 - smoothstep(followRadius * 0.55, followRadius, Math.hypot(dx, dy));
      cgx = clamp(dx / (size * 1.1), -1, 1);
      cgy = clamp(-dy / (size * 1.1), -1, 1);
    }

    /* idle glances when nobody is near */
    if (t > idle.until) {
      const look = !loading && Math.random() < 0.65; // a loader keeps its eyes on the front
      idle.x = look ? (Math.random() * 2 - 1) * 0.55 : 0;
      idle.y = look ? (Math.random() * 2 - 1) * 0.4 : 0;
      idle.until = t + 1.6 + Math.random() * 2.6;
    }
    const tx = idle.x + (cgx - idle.x) * w;
    const ty = idle.y + (cgy - idle.y) * w;
    const k = 1 - Math.exp(-dt * (w > 0.05 ? 9 : 4));
    gaze.x += (tx - gaze.x) * k;
    gaze.y += (ty - gaze.y) * k;

    /* body language */
    root.position.x = gaze.x * 0.04;
    root.position.y = Math.sin(t * 1.4) * 0.025 + gaze.y * 0.03;
    root.rotation.z = -gaze.x * 0.05;
    const breathe = 1 + Math.sin(t * 1.4 + 0.6) * 0.012;
    body.scale.setScalar(breathe);

    face.rotation.y = gaze.x * 0.34;
    face.rotation.x = -gaze.y * 0.26;
    for (const e of eyes) {
      e.g.position.set(e.base.x + gaze.x * 0.025, e.base.y + gaze.y * 0.02, e.base.z);
    }

    /* blink */
    if (blinkStart < 0 && t > nextBlink) blinkStart = t;
    let eyeY = 1;
    if (blinkStart >= 0) {
      const p = (t - blinkStart) / 0.18;
      if (p >= 1) {
        blinkStart = -1;
        nextBlink = t + 2.2 + Math.random() * 3.5;
      } else {
        eyeY = 1 - Math.sin(p * Math.PI) * 0.92;
      }
    }
    for (const e of eyes) e.g.scale.set(1, eyeY, 1);

    /* mouth: gentle "talk", bigger grin when the cursor is close */
    const grin = 1 + Math.sin(t * 2.2) * 0.05 + w * 0.12;
    mouth.scale.set(1 + w * 0.08, grin, 1);

    /* rays: slow spin, ripple, lean toward the cursor */
    const spin = loading ? -t * (calm ? 2.6 : 7) : t * 0.14 + Math.sin(t * 0.5) * 0.12; // loader: clockwise, ~1 turn/s (2.4 s when calm)
    rayRing.rotation.z = spin;
    const toCursor = Math.atan2(cgy, cgx);
    for (let i = 0; i < RAY_COUNT; i++) {
      const a = (i / RAY_COUNT) * Math.PI * 2;
      const pulse = Math.sin(t * (loading ? 5 : 1.9) + i * 0.9);
      let r = RAY_RING + pulse * 0.04;
      let s = 1 + pulse * 0.1;
      if (w > 0.01) {
        const align = Math.max(0, Math.cos(a + spin - toCursor));
        r += align * align * 0.11 * w;
        s += align * align * 0.28 * w;
      }
      const ray = rays[i];
      if (!ray) continue;
      ray.position.set(Math.cos(a) * r, Math.sin(a) * r, 0);
      ray.scale.setScalar(s);
    }
  };

  /* ---------------- run loop ---------------- */
  let raf = 0;
  let last = 0;
  let onScreen = true;
  let tabVisible = !document.hidden;
  const loop = (now: number) => {
    raf = requestAnimationFrame(loop);
    const t = now / 1000;
    const dt = Math.min(0.05, last ? t - last : 0.016);
    last = t;
    frame(t, dt);
    render();
  };
  const sync = () => {
    const shouldRun = animate && onScreen && tabVisible;
    if (shouldRun && !raf) {
      last = 0;
      raf = requestAnimationFrame(loop);
    } else if (!shouldRun && raf) {
      cancelAnimationFrame(raf);
      raf = 0;
    }
  };

  const onMove = (e: PointerEvent) => {
    pointer.x = e.clientX;
    pointer.y = e.clientY;
    pointer.has = true;
  };
  const onLeave = () => {
    pointer.has = false;
  };
  const onVis = () => {
    tabVisible = !document.hidden;
    sync();
  };
  let io: IntersectionObserver | null = null;

  if (animate) {
    if (!loading) {
      window.addEventListener("pointermove", onMove, { passive: true });
      document.documentElement.addEventListener("pointerleave", onLeave);
    }
    document.addEventListener("visibilitychange", onVis);
    io = new IntersectionObserver(([entry]) => {
      onScreen = entry ? entry.isIntersecting : true;
      sync();
    });
    io.observe(container);
    sync();
  } else {
    frame(0.5, 0.016);
    render();
  }

  return () => {
    if (raf) cancelAnimationFrame(raf);
    window.removeEventListener("pointermove", onMove);
    document.documentElement.removeEventListener("pointerleave", onLeave);
    document.removeEventListener("visibilitychange", onVis);
    io?.disconnect();
    scene.traverse((o) => {
      if (o instanceof THREE.Mesh) {
        const mats = Array.isArray(o.material) ? o.material : [o.material];
        for (const m of mats) {
          if ("map" in m && m.map instanceof THREE.Texture) m.map.dispose();
          m.dispose();
        }
      }
    });
    for (const g of [rayGeo, bodyGeo, cheekGeo, eyeGeo, sheenGeo, hiGeoBig, hiGeoSmall]) g.dispose();
    glow.geometry.dispose();
    mouthMesh.geometry.dispose();
    tongue.geometry.dispose();
    cheekTex.dispose();
    renderer.dispose();
    renderer.domElement.remove();
  };
}

export interface SolMascotProps {
  size?: number;
  className?: string;
  /** Distance (px) from the mascot within which it looks at the cursor. */
  followRadius?: number;
  /** Use as a loading indicator: the rays spin fast and the face looks straight ahead. */
  loading?: boolean;
}

export default function SolMascot({ size = 120, className = "", followRadius, loading = false }: SolMascotProps) {
  const ref = useRef<HTMLDivElement>(null);
  const reduced = useReducedMotion();
  const [failed, setFailed] = useState(false);
  const radius = followRadius ?? Math.max(260, size * 2.5);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    try {
      // A loader keeps moving even with reduced motion (just slowly); the normal mascot freezes on one frame.
      return createSol(el, { size, followRadius: radius, animate: loading || !reduced, loading, calm: reduced });
    } catch {
      setFailed(true);
    }
  }, [size, radius, reduced, loading]);

  if (failed) return <SolMark size={size} className={className} spinning={loading} />;

  return (
    <div
      ref={ref}
      className={`shrink-0 ${className}`}
      style={{ width: size, height: size }}
      role="img"
      aria-label="Sol"
    />
  );
}
