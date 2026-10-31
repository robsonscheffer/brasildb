import * as THREE from './vendor/three.module.min.js';

// Render only on interaction or resize, never an idle polling/animation loop.
export function createMap(host, cities, borders, onPick) {
  const renderer = new THREE.WebGLRenderer({antialias: true, alpha: true});
  renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
  renderer.setClearColor(0x000000, 0);
  host.append(renderer.domElement);
  const scene = new THREE.Scene();
  const camera = new THREE.OrthographicCamera(-24, 24, 22, -22, .1, 300);
  camera.position.set(0, -27, 62);
  camera.lookAt(0, 0, 0);
  const project = (lon, lat) => new THREE.Vector3(lon + 54, lat + 14, 0);
  const borderMaterial = new THREE.LineBasicMaterial({color: 0x789575, transparent: true, opacity: .28});
  for (const path of borders) {
    const geometry = new THREE.BufferGeometry().setFromPoints(path.map(([lon, lat]) => project(lon, lat)));
    scene.add(new THREE.Line(geometry, borderMaterial));
  }
  const material = new THREE.MeshBasicMaterial({color: 0xffffff});
  const mesh = new THREE.InstancedMesh(new THREE.SphereGeometry(1, 6, 4), material, cities.length);
  mesh.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
  scene.add(mesh);
  const dummy = new THREE.Object3D(), color = new THREE.Color();
  const selection = new THREE.Mesh(new THREE.RingGeometry(.45, .50, 40), new THREE.MeshBasicMaterial({color: 0xf5be77, side: THREE.DoubleSide}));
  selection.visible = false;
  scene.add(selection);
  let time = 1023;
  let selected = null;
  function update(minute, selectedId = selected) {
    time = minute; selected = selectedId;
    cities.forEach((city, index) => {
      const closed = city.closures.reduce((n, [m, count]) => n + (m < time ? count : 0), 0);
      const remaining = city.total - closed;
      const fraction = remaining / city.total;
      dummy.position.copy(project(city.lon, city.lat));
      dummy.position.z = remaining ? .08 + fraction * .22 : 0;
      const radius = remaining ? Math.min(.42, .065 + Math.sqrt(remaining) * .012) : .045;
      dummy.scale.setScalar(radius);
      dummy.updateMatrix(); mesh.setMatrixAt(index, dummy.matrix);
      color.set(remaining ? 0xd5f69a : 0x344c3c);
      if (remaining) color.multiplyScalar(.3 + .7 * Math.sqrt(fraction));
      mesh.setColorAt(index, color);
      if (city.id === selected) {
        selection.position.copy(project(city.lon, city.lat)); selection.position.z = .7;
      }
    });
    selection.visible = selected !== null;
    mesh.instanceMatrix.needsUpdate = true;
    mesh.instanceColor.needsUpdate = true;
    // Recompute after scaling instances so picking includes the full country.
    mesh.computeBoundingSphere();
    render();
  }
  function render() { renderer.render(scene, camera); }
  function resize() {
    const {width, height} = host.getBoundingClientRect();
    if (!width || !height) return;
    const aspect = width / height;
    const halfHeight = Math.max(22, 22 / aspect);
    camera.left = -halfHeight * aspect; camera.right = halfHeight * aspect;
    camera.top = halfHeight; camera.bottom = -halfHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(width, height, false); render();
  }
  const observer = new ResizeObserver(resize); observer.observe(host);
  const raycaster = new THREE.Raycaster();
  renderer.domElement.addEventListener('click', event => {
    const rect = renderer.domElement.getBoundingClientRect();
    raycaster.setFromCamera(new THREE.Vector2((event.clientX - rect.left) / rect.width * 2 - 1, -(event.clientY - rect.top) / rect.height * 2 + 1), camera);
    const hit = raycaster.intersectObject(mesh)[0];
    if (hit) onPick(cities[hit.instanceId].id);
  });
  renderer.domElement.addEventListener('webglcontextlost', event => {
    event.preventDefault();
    document.getElementById('map-fallback').hidden = false;
  });
  update(time); resize();
  return {update};
}
