import * as THREE from './vendor/three.module.min.js';
import { move } from './state.mjs';

const M = (color, extra = {}) => new THREE.MeshStandardMaterial({ color, roughness: .92, ...extra });
const boxGeometry = new THREE.BoxGeometry(1, 1, 1);
function block(parent, material, x, y, z, w, h, d) {
  const mesh = new THREE.Mesh(boxGeometry, material);
  mesh.position.set(x, y, z); mesh.scale.set(w, h, d);
  mesh.castShadow = true; mesh.receiveShadow = true; parent.add(mesh); return mesh;
}
function round(parent, material, x, y, z, radius, detail = 1) {
  const mesh = new THREE.Mesh(new THREE.IcosahedronGeometry(radius, detail), material);
  mesh.position.set(x, y, z); mesh.castShadow = true; mesh.receiveShadow = true; parent.add(mesh); return mesh;
}
function cylinder(parent, material, x, y, z, r1, r2, h, sides = 8) {
  const mesh = new THREE.Mesh(new THREE.CylinderGeometry(r1, r2, h, sides), material);
  mesh.position.set(x, y, z); mesh.castShadow = true; mesh.receiveShadow = true; parent.add(mesh); return mesh;
}
function texture(width, height, paint) {
  const canvas = document.createElement('canvas'); canvas.width = width; canvas.height = height;
  paint(canvas.getContext('2d'), width, height);
  const result = new THREE.CanvasTexture(canvas); result.colorSpace = THREE.SRGBColorSpace; return result;
}
function sign(parent, text, x, y, z, w, h, bg = '#ebe1c9', fg = '#285862') {
  const map = texture(768, 192, (ctx, width, height) => {
    ctx.fillStyle = bg; ctx.fillRect(0, 0, width, height);
    ctx.fillStyle = fg; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
    ctx.font = '600 48px sans-serif'; ctx.fillText(text, width / 2, height / 2, width - 40);
  });
  const mesh = new THREE.Mesh(new THREE.PlaneGeometry(w, h), new THREE.MeshStandardMaterial({map, roughness: 1}));
  mesh.position.set(x, y, z); parent.add(mesh); return mesh;
}
function person({skin, shirt, pants, hair, phone = false, bag = false}) {
  const group = new THREE.Group(), body = new THREE.Group(); group.add(body);
  const skinM = M(skin), shirtM = M(shirt), pantsM = M(pants), hairM = M(hair), shoesM = M('#35312e');
  cylinder(body, shirtM, 0, 1.07, 0, .22, .18, .53);
  round(body, skinM, 0, 1.62, 0, .22, 2).scale.set(.86, 1.12, .91);
  const hairCap = new THREE.Mesh(new THREE.SphereGeometry(.222, 9, 5, 0, Math.PI * 2, 0, Math.PI * .56), hairM);
  hairCap.position.set(0, 1.69, -.015); body.add(hairCap);
  block(body, skinM, 0, 1.35, 0, .12, .15, .12);
  for (const x of [-.074, .074]) round(body, M('#312d29'), x, 1.64, .181, .016, 0);
  const arms = [], legs = [];
  for (const side of [-1, 1]) {
    const arm = new THREE.Group(); arm.position.set(side * .27, 1.25, 0); body.add(arm);
    cylinder(arm, shirtM, 0, -.13, 0, .085, .075, .28);
    cylinder(arm, skinM, 0, -.36, 0, .062, .055, .25);
    round(arm, skinM, 0, -.51, 0, .064); arms.push(arm);
    const leg = new THREE.Group(); leg.position.set(side * .115, .84, 0); body.add(leg);
    cylinder(leg, pantsM, 0, -.29, 0, .105, .076, .59);
    block(leg, shoesM, 0, -.68, .055, .18, .13, .31); legs.push(leg);
  }
  if (phone) { arms[1].rotation.x = -1.05; block(arms[1], M('#242b2d'), 0, -.49, .05, .10, .19, .024); }
  if (bag) {
    block(body, M('#765440'), 0, 1.05, -.22, .36, .43, .18);
    for (const x of [-.15, .15]) block(body, M('#b49e7c'), x, 1.13, .17, .038, .4, .035);
  }
  return {group, body, arms, legs, phone};
}

export function createWorld(host, {onContextLost, reducedMotion = false} = {}) {
  const renderer = new THREE.WebGLRenderer({antialias: true, powerPreference: 'high-performance'});
  renderer.setPixelRatio(Math.min(devicePixelRatio, 1.6));
  renderer.shadowMap.enabled = true; renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  renderer.toneMapping = THREE.ACESFilmicToneMapping; renderer.toneMappingExposure = 1.15;
  host.append(renderer.domElement);
  renderer.domElement.setAttribute('aria-label', 'Pátio de escola fictícia em três dimensões. Seu personagem já votou.');
  const scene = new THREE.Scene(); scene.background = new THREE.Color('#cfbf9f');
  scene.fog = new THREE.Fog('#cfbf9f', 38, 88);
  const camera = new THREE.PerspectiveCamera(51, 1, .08, 110);
  const hemi = new THREE.HemisphereLight('#dce2db', '#746251', 2.2); scene.add(hemi);
  const sun = new THREE.DirectionalLight('#ffe1ab', 3.4); sun.position.set(-20, 17, 12);
  sun.castShadow = true; sun.shadow.mapSize.set(1536, 1536);
  Object.assign(sun.shadow.camera, {left: -25, right: 25, top: 25, bottom: -25, near: .5, far: 75});
  sun.shadow.normalBias = .04; sun.shadow.bias = -.0003; scene.add(sun);

  const materials = {
    cream: M('#d6c6a4'), blue: M('#40777b'), darkBlue: M('#355a63'), roof: M('#9f573a'), roofRib: M('#a75d3e'),
    concrete: M('#aaa28c'), metal: M('#455151'), wood: M('#816144'), trim: M('#e0d8bf'),
    leaf: M('#64784c'), leafLight: M('#83915d'), trunk: M('#705645'), line: M('#dbcfaa'),
  };
  let seed = 706;
  const random = () => { seed = (1664525 * seed + 1013904223) >>> 0; return seed / 4294967296; };
  const groundMap = texture(512, 512, (ctx, w, h) => {
    ctx.fillStyle = '#aaa18a'; ctx.fillRect(0, 0, w, h);
    for (let i = 0; i < 13000; i++) { const c = Math.floor(120 + random() * 80); ctx.fillStyle = `rgba(${c},${c-6},${c-16},.17)`; ctx.fillRect(random()*w, random()*h, 1+random()*3, 1+random()*3); }
    ctx.strokeStyle = '#8d8675'; ctx.lineWidth = 1; ctx.strokeRect(0, 0, w, h);
    ctx.beginPath(); ctx.moveTo(30, 400); ctx.lineTo(90, 340); ctx.lineTo(120, 345); ctx.stroke();
  });
  groundMap.wrapS = groundMap.wrapT = THREE.RepeatWrapping; groundMap.repeat.set(8, 8);
  const groundM = M('#ffffff', {map: groundMap});
  block(scene, groundM, 0, -.12, 2, 27, .2, 29);
  block(scene, M('#7c8076'), 0, -.17, 20, 80, .15, 12);
  block(scene, materials.concrete, 0, -.08, 15.2, 80, .16, 2.2);
  for (let x = -32; x < 36; x += 6) block(scene, M('#d8ca9e'), x, -.075, 21, 2.5, .01, .1);

  const obstacles = [], occluders = [];
  const collider = (minX, maxX, minZ, maxZ) => obstacles.push({minX, maxX, minZ, maxZ});
  function wall(mat, x, y, z, w, h, d) { const obj = block(scene, mat, x, y, z, w, h, d); occluders.push(obj); return obj; }
  wall(materials.cream, 0, 2, -10, 27, 4, 6);
  wall(materials.blue, 0, .65, -6.97, 27, 1.3, .06);
  collider(-14, 14, -14, -7);
  for (const x of [-7.4, 6.4]) {
    block(scene, materials.darkBlue, x, 1.23, -6.87, 1.65, 2.46, .14);
    block(scene, materials.trim, x - .9, 1.3, -6.78, .08, 2.6, .1);
    block(scene, materials.trim, x + .9, 1.3, -6.78, .08, 2.6, .1);
    cylinder(scene, materials.metal, x + .55, 1.14, -6.74, .035, .035, .13).rotation.x = Math.PI / 2;
    sign(scene, x < 0 ? 'SALA A · SUA SEÇÃO' : 'SALA B · OUTRA SEÇÃO', x, 2.83, -6.88, 3, .45);
  }
  for (const x of [-11, -3.4, 2, 10.4]) {
    block(scene, M('#8b9e96'), x, 2, -6.86, 1.9, 1.25, .08);
    for (let i = 0; i < 6; i++) block(scene, materials.darkBlue, x-.84+i*.34, 2, -6.78, .035, 1.28, .04);
  }
  sign(scene, 'ESCOLA DO BAIRRO', 0, 3.5, -6.87, 5.4, .5);
  // Original simplified roof, no official building or voting equipment is reconstructed.
  for (const side of [-1, 1]) {
    const roof = block(scene, materials.roof, 0, 4.2, -10 + side*1.7, 28, .18, 3.7);
    roof.rotation.x = side * -.17;
    for (let x=-13; x<=13; x+=.5) {
      const rib = block(scene, materials.roofRib, x, 4.3, -10 + side*1.7, .035, .07, 3.7);
      rib.rotation.x = side * -.17;
    }
  }
  const awning = wall(materials.trim, 0, 3.25, -5.45, 27, .16, 3);
  for (const x of [-12, -4, 4, 12]) {
    block(scene, materials.blue, x, 1.6, -4.15, .13, 3.2, .13); collider(x-.1, x+.1, -4.25, -4.05);
  }
  for (const side of [-1, 1]) {
    wall(materials.cream, side*13.25, 1.1, 2.5, .45, 2.2, 20);
    wall(materials.blue, side*13.24, .45, 2.5, .47, .9, 20);
    collider(side < 0 ? -14 : 13, side < 0 ? -13 : 14, -14, 13);
    const x = side * 7.65;
    wall(materials.cream, x, .65, 12, 11.3, 1.3, .35);
    wall(materials.blue, x, .25, 12.02, 11.3, .5, .38);
    collider(side < 0 ? -14 : 2, side < 0 ? -2 : 14, 11.82, 12.2);
    for (let bx = side < 0 ? -13 : 2.2; bx < (side < 0 ? -2 : 13); bx += .32) block(scene, materials.metal, bx, 1.85, 12, .04, 1.2, .04);
    block(scene, materials.metal, x, 2.4, 12, 11.2, .05, .05);
    block(scene, materials.blue, side*2.05, 1.4, 12, .3, 2.8, .4);
    const gate = new THREE.Group(); gate.position.set(side*2, 0, 12); gate.rotation.y = side * -1.22; scene.add(gate);
    for(let i=0; i<7; i++) block(gate, materials.metal, side * -i*.27, 1.3, 0, .045, 2.5, .045);
    block(gate, materials.metal, side*-.85, 2.5, 0, 1.8, .06, .06);
    block(gate, materials.metal, side*-.85, .1, 0, 1.8, .06, .06);
  }
  // A real opening leads to the street and ending; no hidden exit collider.
  const court = M('#677e7a');
  block(scene, court, 0, -.005, 1, 14, .014, 8.7);
  for (const z of [-3.35, 5.35]) block(scene, materials.line, 0, .012, z, 14, .012, .055);
  for (const x of [-7, 7]) block(scene, materials.line, x, .012, 1, .055, .012, 8.7);
  block(scene, materials.line, 0, .012, 1, .055, .012, 8.7);
  const ring = new THREE.Mesh(new THREE.RingGeometry(1.38, 1.43, 48), new THREE.MeshStandardMaterial({color:'#d5c69e', side:THREE.DoubleSide, roughness:1}));
  ring.rotation.x = -Math.PI/2; ring.position.set(0,.017,1); scene.add(ring);
  for(const x of [-6.5, 6.5]) {
    const z = x < 0 ? -2.8 : 4.8;
    cylinder(scene, materials.metal, x, 1.5, z, .065, .065, 3);
    block(scene, materials.trim, x, 2.9, z, 1.55, .86, .08);
    const hoop = new THREE.Mesh(new THREE.TorusGeometry(.27,.025,5,16), M('#9d573a')); hoop.rotation.x = Math.PI/2; hoop.position.set(x,2.6,z+.36); scene.add(hoop);
  }

  function bench(x,z,rotation=0) {
    const group = new THREE.Group(); group.position.set(x,0,z); group.rotation.y=rotation;scene.add(group);
    for(const bx of [-.85,.85]) { block(group,materials.metal,bx,.25,0,.1,.5,.5); block(group,materials.metal,bx,.75,-.22,.08,.8,.08); }
    for(let i=0;i<3;i++) block(group,materials.wood,0,.52,-.22+i*.19,2.25,.09,.15);
    for(let i=0;i<2;i++) block(group,materials.wood,0,.83+i*.18,-.25,2.25,.13,.08);
  }
  bench(-6,2.3);collider(-7.2,-4.8,1.9,2.7);
  bench(8,7,Math.PI/2);collider(7.65,8.35,5.8,8.2);
  bench(-4.5,8.6);collider(-5.7,-3.3,8.2,9);
  for (const [x,z,size] of [[-10,1,1.6],[10,-1,1.7],[-10,8.5,1.4],[10,9,1.5]]) {
    block(scene, M('#9a8a68'), x, .13, z, 2.5, .26, 2.5); collider(x-1.2,x+1.2,z-1.2,z+1.2);
    cylinder(scene,materials.trunk,x,1.7,z,.13,.23,3.4);
    for(let i=0;i<7;i++) { const angle=i*2.4; const leaf=round(scene,i%2?materials.leaf:materials.leafLight,x+Math.cos(angle)*size*.6,3.7+random()*.9,z+Math.sin(angle)*size*.6,size*.9,1);leaf.scale.set(1,.7,1); }
  }
  // Public notices are illustrative, not fabricated official election records.
  block(scene,materials.wood,-.7,1.85,-6.68,2.1,1.25,.12);
  sign(scene,'AVISOS · ACESSO ÀS SALAS',-.7,2.12,-6.59,1.9,.3,'#d6cba9','#575a48');
  for(let i=0;i<3;i++) {block(scene,materials.trim,-1.25+i*.55,1.65,-6.58,.42,.5,.015);}
  block(scene,M('#aeb3a7'),11.7,.6,-5.2,.8,1.2,.55); collider(11.2,12.2,-5.7,-4.7);
  cylinder(scene,materials.metal,11.7,1.28,-5.2,.34,.34,.08);
  block(scene,M('#3f6970'),-11.7,.45,-5.6,.6,.9,.6);
  // Street details and original background homes keep the school situated.
  cylinder(scene,materials.metal,8,1.7,15.3,.055,.055,3.4);
  const busSign=sign(scene,'ÔNIBUS',8,3.15,15.4,1,.4,'#356274','#eee4c8');
  for(let i=0;i<9;i++) {
    const x=-32+i*8; const h=3+random()*3;
    block(scene,M(['#bfa480','#b4b2a0','#b28e73','#9da8a0'][i%4]),x,h/2,31,6.8,h,7);
    block(scene,materials.roof,x,h+.05,31,7.2,.18,7.2);
    for(const dx of [-1.6,1.6]) block(scene,materials.darkBlue,x+dx,1.8,27.46,.9,1.2,.05);
  }
  for(const x of [-16,16]) {
    cylinder(scene,materials.wood,x,5.5,16.2,.12,.18,11);
    for(const off of [-.4,0,.4]) {
      const curve = new THREE.QuadraticBezierCurve3(new THREE.Vector3(-16,10.5,16.2+off),new THREE.Vector3(0,8.9,16.2+off),new THREE.Vector3(16,10.5,16.2+off));
      if(x<0) scene.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(curve.getPoints(30)),new THREE.LineBasicMaterial({color:'#55524b'})));
    }
  }

  const player = person({skin:'#9b7154',shirt:'#d1b891',pants:'#4f5d5c',hair:'#342d29',bag:true});
  player.group.position.set(0,0,5.7);player.group.rotation.y=Math.PI;player.group.userData.dynamic=true;scene.add(player.group);
  const actors = [
    {id:'lia',x:-4,z:1.5,colors:{skin:'#92674f',shirt:'#816573',pants:'#535a4a',hair:'#302a27',phone:true}},
    {id:'davi',x:3.3,z:8.2,colors:{skin:'#bc8f6d',shirt:'#6c8792',pants:'#a59576',hair:'#4a3b30',phone:true}},
    {id:'celia',x:-6.4,z:-5.15,colors:{skin:'#795744',shirt:'#d7cdb2',pants:'#506b70',hair:'#3d3029'}},
  ];
  const npcs=actors.map(actor=>{const model=person(actor.colors);model.group.position.set(actor.x,0,actor.z);model.group.userData.dynamic=true;scene.add(model.group);return {...actor,model};});
  // Batch repeated static geometry; retain the original static world matrices for camera rays.
  scene.updateMatrixWorld(true);
  const batches=new Map();
  scene.traverse(obj=>{
    if(!obj.isMesh||obj.geometry!==boxGeometry)return;
    for(let parent=obj;parent;parent=parent.parent)if(parent.userData.dynamic)return;
    if(!batches.has(obj.material))batches.set(obj.material,[]);
    batches.get(obj.material).push(obj);
  });
  for(const [material,meshes] of batches){
    if(meshes.length<2)continue;
    const batch=new THREE.InstancedMesh(boxGeometry,material,meshes.length);
    meshes.forEach((mesh,index)=>{batch.setMatrixAt(index,mesh.matrixWorld);mesh.removeFromParent();});
    batch.castShadow=true;batch.receiveShadow=true;scene.add(batch);
  }
  for(const npc of npcs)collider(npc.x-.24,npc.x+.24,npc.z-.24,npc.z+.24);
  const hotspots = [
    ...actors.map(({id,x,z})=>({id,x,z,label:`Conversar com ${id==='lia'?'Lia':id==='davi'?'Davi':'Célia'}`,radius:2.15})),
    {id:'corridor',x:4.5,z:-5.2,label:'Observar o corredor',radius:2.2},
    {id:'notice',x:-.7,z:-5.7,label:'Examinar o mural',radius:1.9},
    {id:'bench',x:-4.5,z:7.5,label:'Sentar e esperar a carona',radius:1.9},
    {id:'gate',x:0,z:12.6,label:'Sair pelo portão',radius:2.1},
  ];
  let yaw=0, pitch=.04, step=0, walkDistance=0;
  let selected=null;
  const cameraTarget=new THREE.Vector3(), desired=new THREE.Vector3(), lookTarget=new THREE.Vector3();
  const raycaster=new THREE.Raycaster();
  const minBoundary=[{minX:-60,maxX:-13,minZ:-20,maxZ:18},{minX:13,maxX:60,minZ:-20,maxZ:18}];
  obstacles.push(...minBoundary);
  const marker=new THREE.Mesh(new THREE.RingGeometry(.42,.46,48),new THREE.MeshBasicMaterial({color:'#f6dfad',side:THREE.DoubleSide,transparent:true,opacity:.65}));
  marker.rotation.x=-Math.PI/2;marker.position.y=.035;scene.add(marker);marker.visible=false;

  function resize() { const {width,height}=host.getBoundingClientRect();if(!width||!height)return;renderer.setSize(width,height,false);camera.aspect=width/height;camera.updateProjectionMatrix();render(); }
  const observer=new ResizeObserver(resize);observer.observe(host);
  function setLook(dx,dy) {yaw-=dx*.005;pitch=THREE.MathUtils.clamp(pitch+dy*.002,-.12,.45);}
  function update(dt, input, elapsed) {
    const direction={x:Math.cos(yaw)*input.x-Math.sin(yaw)*input.z,z:-Math.sin(yaw)*input.x-Math.cos(yaw)*input.z};
    const steps=Math.max(1,Math.ceil(dt/.04));
    let pos={x:player.group.position.x,z:player.group.position.z,distance:0},distance=0;
    for(let i=0;i<steps;i++){pos=move(pos,direction,dt/steps,obstacles);distance+=pos.distance;}
    pos.distance=distance;
    player.group.position.x=pos.x;player.group.position.z=pos.z;
    if(pos.distance>.0001){player.group.rotation.y=Math.atan2(direction.x,direction.z);step+=pos.distance*4.4;walkDistance+=pos.distance;}
    const walking=pos.distance>.0001;
    player.legs.forEach((leg,i)=>leg.rotation.x=walking?Math.sin(step+i*Math.PI)*.48:0);
    player.arms.forEach((arm,i)=>arm.rotation.x=walking?Math.sin(step+i*Math.PI)*-.35:0);
    if(!reducedMotion)player.body.position.y=walking?Math.abs(Math.sin(step))*.025:0;
    npcs.forEach((npc,i)=>{
      const dx=pos.x-npc.x,dz=pos.z-npc.z;
      const near=Math.hypot(dx,dz)<4;
      if(near)npc.model.group.rotation.y=Math.atan2(dx,dz);
      else npc.model.group.rotation.y=i===1?Math.PI:.2;
      if(!reducedMotion)npc.model.body.position.y=Math.sin(elapsed*1.4+i)*.012;
    });
    selected=hotspots.filter(h=>Math.hypot(h.x-pos.x,h.z-pos.z)<h.radius).sort((a,b)=>Math.hypot(a.x-pos.x,a.z-pos.z)-Math.hypot(b.x-pos.x,b.z-pos.z))[0]||null;
    marker.visible=!!selected;
    if(selected){marker.position.x=selected.x;marker.position.z=selected.z;}
    lookTarget.set(pos.x,1.45,pos.z);
    desired.set(pos.x+Math.sin(yaw)*6.1,3.1+pitch*3,pos.z+Math.cos(yaw)*6.1);
    const delta=desired.clone().sub(lookTarget);raycaster.set(lookTarget,delta.clone().normalize());raycaster.far=delta.length();
    const hit=raycaster.intersectObjects(occluders,false)[0];
    if(hit&&hit.distance<delta.length()){desired.copy(lookTarget).add(delta.normalize().multiplyScalar(Math.max(1.1,hit.distance-.35)));}
    camera.position.lerp(desired,reducedMotion?1:1-Math.exp(-dt*10));
    camera.lookAt(lookTarget);
    return {near:selected,walkDistance,exiting:pos.z>14.25};
  }
  function render(){renderer.render(scene,camera);}
  function projectNPC(id){const npc=npcs.find(n=>n.id===id);if(!npc)return null;const v=new THREE.Vector3(npc.x,2.1,npc.z).project(camera);return {x:(v.x*.5+.5)*host.clientWidth,y:(-v.y*.5+.5)*host.clientHeight,visible:v.z<1&&Math.abs(v.x)<1&&Math.abs(v.y)<1&&Math.hypot(npc.x-player.group.position.x,npc.z-player.group.position.z)<7};}
  function setLater(){sun.position.set(-24,9,14);sun.intensity=2.3;sun.color.set('#ffd09b');hemi.intensity=1.75;scene.background.set('#b6ab95');scene.fog.color.set('#b6ab95');}
  function returnToCourtyard(){player.group.position.set(0,0,10);yaw=0;}
  function dispose(){observer.disconnect();renderer.dispose();scene.traverse(obj=>{if(obj.geometry&&obj.geometry!==boxGeometry)obj.geometry.dispose();});}
  renderer.domElement.addEventListener('webglcontextlost',event=>{event.preventDefault();onContextLost?.();});
  update(.016,{x:0,z:0},0);camera.position.copy(desired);resize();
  return {update,render,setLook,projectNPC,setLater,returnToCourtyard,dispose,canvas:renderer.domElement};
}
