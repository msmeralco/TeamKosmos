// Small pictures of kit models for the HTML cards: <img data-model="inverter" data-view="part|face" data-fit="1.3">.
// One throwaway renderer draws each model once, at boot; the picture is the canvas as a data URL.
import * as THREE from "three";

export function fillThumbs(kit) {
  const imgs = [...document.querySelectorAll("img[data-model]")].filter((i) => kit.has(i.dataset.model));
  if (!imgs.length) return;
  const S = 288, r = new THREE.WebGLRenderer({ alpha: true, antialias: true, preserveDrawingBuffer: true });
  r.setSize(S, S, false);
  r.setPixelRatio(1);
  r.setClearColor(0x000000, 0);
  r.toneMapping = THREE.NeutralToneMapping;
  r.outputColorSpace = THREE.SRGBColorSpace;
  const scene = new THREE.Scene(), cam = new THREE.PerspectiveCamera(28, 1, 1, 6000);
  const sun = new THREE.DirectionalLight(0xffffff, 2.4);
  sun.position.set(-3, 5, 4);
  scene.add(new THREE.HemisphereLight(0xffffff, 0x8a93a8, 1.5), sun);
  for (const img of imgs) {
    const g = kit.group(img.dataset.model, { cast: false, receive: false }), face = img.dataset.view === "face";
    scene.add(g);
    const b = new THREE.Box3().setFromObject(g), sz = b.getSize(new THREE.Vector3()), c = b.getCenter(new THREE.Vector3());
    // a face is the top slice of a figure; a part is the whole model. Models face +z in the web scene.
    const mid = face ? new THREE.Vector3(c.x, b.max.y - sz.y * 0.15, c.z) : c, size = face ? sz.y * 0.34 : Math.max(sz.x, sz.y, sz.z);
    const yaw = face ? 0.22 : 0.65, el = face ? 0.06 : 0.45, d = (size * (+img.dataset.fit || 1.3)) / (2 * Math.tan(THREE.MathUtils.degToRad(14)));
    cam.position.set(mid.x + Math.sin(yaw) * Math.cos(el) * d, mid.y + Math.sin(el) * d, mid.z + Math.cos(yaw) * Math.cos(el) * d);
    cam.lookAt(mid);
    r.render(scene, cam);
    img.src = r.domElement.toDataURL("image/png");
    scene.remove(g);
  }
  r.dispose();
  r.forceContextLoss();
}
