// Sky dome, stars, moon and the time-of-day table. tod runs 0 (3 AM) to 1 (noon); the deck moves it forward.
import * as THREE from "three";

const C = (h) => new THREE.Color(h);
export const clamp01 = (v) => Math.min(1, Math.max(0, v));
const ss = (a, b, x) => { const t = clamp01((x - a) / (b - a)); return t * t * (3 - 2 * t); };
const rad = (d) => (d * Math.PI) / 180;

// keyframes, by tod. sky = zenith, hor = horizon, fog = distance colour, hemi = [sky, ground, intensity]
const KEYS = [
  { t: 0.0, sun: "#8fa8ff", sunI: 0.0, sky: "#07102a", hor: "#1b2f57", fog: "#13203c", fogD: 0.0009, hs: "#5d78c4", hg: "#26304a", hi: 1.7, ex: 1.15, bloom: 0.38 },
  { t: 0.3, sun: "#8aa0ee", sunI: 0.0, sky: "#122248", hor: "#3a517f", fog: "#26385e", fogD: 0.0009, hs: "#6a86cc", hg: "#2c3652", hi: 1.6, ex: 1.12, bloom: 0.38 },
  { t: 0.46, sun: "#ff9e5c", sunI: 1.1, sky: "#34507f", hor: "#ffb27a", fog: "#e8a67c", fogD: 0.0011, hs: "#8b9cc4", hg: "#5a463f", hi: 0.95, ex: 1.0, bloom: 0.4 },
  { t: 0.58, sun: "#ffd9a8", sunI: 2.2, sky: "#4a8bd0", hor: "#f2d9b8", fog: "#cfd9dc", fogD: 0.00085, hs: "#a8c9ee", hg: "#6b6a55", hi: 1.1, ex: 1.0, bloom: 0.38 },
  { t: 1.0, sun: "#fff3dc", sunI: 2.9, sky: "#3b86d8", hor: "#dcecf8", fog: "#d4e8f5", fogD: 0.00075, hs: "#b8d8f6", hg: "#7d805f", hi: 1.2, ex: 1.0, bloom: 0.3 },
];

const lerpKeys = (t) => {
  let i = 0;
  while (i < KEYS.length - 2 && t > KEYS[i + 1].t) i++;
  const a = KEYS[i], b = KEYS[i + 1];
  const k = clamp01((t - a.t) / (b.t - a.t));
  const mix = (p) => C(a[p]).lerp(C(b[p]), k);
  const num = (p) => a[p] + (b[p] - a[p]) * k;
  return { sun: mix("sun"), sunI: num("sunI"), sky: mix("sky"), hor: mix("hor"), fog: mix("fog"), fogD: num("fogD"), hs: mix("hs"), hg: mix("hg"), hi: num("hi"), ex: num("ex"), bloom: num("bloom") };
};

// sun elevation / azimuth by tod. azimuth 0 = east (+x), 90 = south (+z)
export function sunAngles(t) {
  const pts = [[0, -34], [0.3, -14], [0.46, -0.5], [0.5, 4], [0.58, 17], [0.8, 44], [1, 64]];
  let i = 0;
  while (i < pts.length - 2 && t > pts[i + 1][0]) i++;
  const k = clamp01((t - pts[i][0]) / (pts[i + 1][0] - pts[i][0]));
  const el = pts[i][1] + (pts[i + 1][1] - pts[i][1]) * k;
  return { el, az: 8 + 70 * clamp01((t - 0.4) / 0.6) };
}
const dirOf = (el, az) => new THREE.Vector3(Math.cos(rad(el)) * Math.cos(rad(az)), Math.sin(rad(el)), Math.cos(rad(el)) * Math.sin(rad(az)));

export function createSky(scene) {
  const U = { uTop: { value: new THREE.Color() }, uHor: { value: new THREE.Color() }, uSun: { value: new THREE.Vector3() }, uMoon: { value: new THREE.Vector3() }, uNight: { value: 1 }, uGlow: { value: new THREE.Color() } };
  const dome = new THREE.Mesh(
    new THREE.SphereGeometry(9000, 32, 20),
    new THREE.ShaderMaterial({
      uniforms: U, side: THREE.BackSide, depthWrite: false, fog: false,
      vertexShader: "varying vec3 vD; void main(){ vD = normalize(position); gl_Position = projectionMatrix*modelViewMatrix*vec4(position,1.0); }",
      fragmentShader: `precision highp float; uniform vec3 uTop,uHor,uSun,uMoon,uGlow; uniform float uNight; varying vec3 vD;
        float h3(vec3 p){ p = fract(p*0.3183099+.1); p *= 17.0; return fract(p.x*p.y*p.z*(p.x+p.y+p.z)); }
        void main(){
          vec3 d = normalize(vD);
          float h = clamp(d.y, 0.0, 1.0);
          vec3 col = mix(uHor, uTop, pow(h, 0.5));
          if (d.y < 0.0) col = uHor;
          float sd = max(dot(d, uSun), 0.0);
          col += uGlow * (pow(sd, 5.0)*0.30 + pow(sd, 60.0)*0.55);
          // stars
          vec3 sp = floor(d*210.0);
          float s = step(0.9972, h3(sp));
          col += vec3(1.0,0.96,0.88) * s * uNight * smoothstep(0.02,0.25,d.y) * (0.6 + 0.4*h3(sp+7.0));
          // moon: a square disc, in keeping with the voxel look
          vec3 up = vec3(0.,1.,0.); vec3 r = normalize(cross(up, uMoon)); vec3 u2 = cross(uMoon, r);
          vec2 q = vec2(dot(d, r), dot(d, u2));
          float m = step(max(abs(q.x), abs(q.y)), 0.045) * step(0.0, dot(d, uMoon));
          col = mix(col, vec3(0.93,0.95,1.0), m * uNight);
          col += vec3(0.5,0.6,0.9) * pow(max(dot(d,uMoon),0.0), 40.0) * 0.35 * uNight;
          gl_FragColor = vec4(col, 1.0);
        }`,
    }),
  );
  dome.frustumCulled = false;
  dome.renderOrder = -10;
  scene.add(dome);
  return { dome, U };
}

// applies tod to lights, fog, sky and the shared materials. returns the sun direction (for the voxel sun)
export function applyTod(t, env) {
  const { sky, key, hemi, scene, renderer, bloom, mats, camTarget } = env;
  const L = lerpKeys(t);
  const s = sunAngles(t);
  const dSun = dirOf(s.el, s.az);
  const dMoon = dirOf(48 - 30 * clamp01(t / 0.46), 150);
  const day = ss(-3, 7, s.el);
  const dir = dMoon.clone().lerp(dSun, day).normalize();
  key.color.copy(C("#8fa8ff")).lerp(L.sun, day);
  key.intensity = 1.7 * (1 - day) + L.sunI * day;
  key.position.copy(camTarget).addScaledVector(dir, 420);
  key.target.position.copy(camTarget);
  key.target.updateMatrixWorld();
  hemi.color.copy(L.hs);
  hemi.groundColor.copy(L.hg);
  hemi.intensity = L.hi;
  scene.fog.color.copy(L.fog);
  scene.fog.density = L.fogD;
  sky.U.uTop.value.copy(L.sky);
  sky.U.uHor.value.copy(L.hor);
  sky.U.uSun.value.copy(dSun);
  sky.U.uMoon.value.copy(dMoon);
  sky.U.uNight.value = 1 - ss(0.3, 0.5, t);
  sky.U.uGlow.value.copy(L.sun).multiplyScalar(0.5 + 0.5 * (1 - day));
  renderer.toneMappingExposure = L.ex;
  bloom.strength = L.bloom;
  const night = 1 - ss(0.34, 0.5, t);
  // windows and lamps: warm at night, plain glass by day
  mats.win.color.copy(C("#9cc7e2")).lerp(C("#ffc46a"), night).multiplyScalar(1 + night * 0.55);
  mats.cloud.color.copy(C("#ffffff")).lerp(C("#5e6a90"), night);
  return { night, day, dSun, el: s.el };
}
