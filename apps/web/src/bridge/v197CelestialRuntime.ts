import * as THREE from "three";

export const V197_CELESTIAL_ENGINE = "three-webgl-coordinated-v1";
export const V197_SPECTRUM_NAMES = [
  "red",
  "orange",
  "yellow",
  "green",
  "blue",
  "indigo",
  "violet",
] as const;

const V197_SPECTRUM = [
  new THREE.Color(0xff526f),
  new THREE.Color(0xff9e4a),
  new THREE.Color(0xffde5c),
  new THREE.Color(0x7eed82),
  new THREE.Color(0x63e0ff),
  new THREE.Color(0x798fff),
  new THREE.Color(0xc28aff),
] as const;

const TAU = Math.PI * 2;
const GOLD = new THREE.Color(0xffd35a);
const IVORY = new THREE.Color(0xfffae8);

type PointSeed = {
  x: number;
  y: number;
  z: number;
  size: number;
  alpha: number;
  band: number;
  phase: number;
  speed: number;
  tissue?: "cortex" | "cerebellum" | "brainstem" | "dust";
};

type GalaxyDiagnostics = {
  total: number;
  transient: number;
  finite: number;
  invalid: number;
  minLife: null;
  maxLife: null;
  byKind: Record<string, number>;
  spectrumBands: readonly string[];
  spectrumCounts: Record<string, number>;
  engine: string;
  oneRafOwner: boolean;
  frameScheduled: boolean;
  frameCount: number;
  fps: number;
  shouldRender: boolean;
  stageId: string | null;
  stageClass: string | null;
  stageHidden: string | null;
  yaw: number;
  pitch: number;
  angularVelocityYaw: number;
  angularVelocityPitch: number;
  dragging: boolean;
  parallaxX: number;
  parallaxY: number;
};

type BrainDiagnostics = {
  reducedMotion: boolean;
  frameScheduled: boolean;
  staticFramePainted: boolean;
  stageVisible: boolean;
  pointCount: number;
  brainstemPointCount: number;
  spectrumBands: readonly string[];
  spectrumCounts: Record<string, number>;
  engine: string;
  oneRafOwner: boolean;
  frameCount: number;
  fps: number;
  yaw: number;
  pitch: number;
  angularVelocityYaw: number;
  angularVelocityPitch: number;
  dragging: boolean;
};

type GalaxyApi = {
  addEvent: (event: unknown) => void;
  burst: (x?: number, y?: number, intensity?: number) => void;
  setMode: (mode?: string) => void;
  setRotate: (enabled: boolean) => void;
  getParticleCount: () => number;
  getTransientParticleCount: () => number;
  getParticleDiagnostics: () => GalaxyDiagnostics;
  dispose: () => void;
};

type StarBrainApi = {
  storm: (power?: number) => void;
  absorb: () => void;
  shatter: () => void;
  firePulse: (from?: number) => void;
  dispose: () => void;
  getDiagnostics: () => BrainDiagnostics;
};

type CelestialWindow = Window & {
  nurGalaxy?: GalaxyApi;
  __nurGalaxy?: GalaxyApi;
  nurStarBrain?: StarBrainApi;
  nur3dBurst?: (x?: number, y?: number, intensity?: number) => void;
  nur3dWordmarkBurst?: (rect?: DOMRect | null) => void;
  nurGalaxyMode?: string;
  nurGalaxyRotate?: boolean;
};

type StarUniforms = {
  uTime: { value: number };
  uPointScale: { value: number };
  uRainbowStrength: { value: number };
  uEnergy: { value: number };
  uBurst: { value: number };
  uAbsorb: { value: number };
};

type CelestialController = {
  document: Document;
  frameWindow: CelestialWindow;
  brainHost: HTMLElement;
  galaxyCanvas: HTMLCanvasElement;
  galaxyContext: CanvasRenderingContext2D;
  brainCanvas: HTMLCanvasElement;
  brainContext: CanvasRenderingContext2D;
  renderCanvas: HTMLCanvasElement;
  renderer: THREE.WebGLRenderer;
  galaxyScene: THREE.Scene;
  galaxyCamera: THREE.PerspectiveCamera;
  galaxyGroup: THREE.Group;
  galaxyMaterial: THREE.ShaderMaterial & { uniforms: StarUniforms };
  brainScene: THREE.Scene;
  brainCamera: THREE.PerspectiveCamera;
  brainGroup: THREE.Group;
  brainMaterial: THREE.ShaderMaterial & { uniforms: StarUniforms };
  galaxyCounts: Record<string, number>;
  galaxySpectrumCounts: Record<string, number>;
  brainSpectrumCounts: Record<string, number>;
  galaxyPointCount: number;
  brainPointCount: number;
  brainstemPointCount: number;
  reducedMotion: boolean;
  stageVisible: boolean;
  stageVisibilityCheckedAt: number;
  raf: number | null;
  disposed: boolean;
  staticFramePainted: boolean;
  frameCount: number;
  measuredFps: number;
  fpsStartedAt: number;
  fpsFrames: number;
  lastPaintAt: number;
  lastAnimationAt: number;
  width: number;
  height: number;
  dpr: number;
  brainWidth: number;
  brainHeight: number;
  yaw: number;
  pitch: number;
  targetYaw: number;
  targetPitch: number;
  brainAngularVelocityYaw: number;
  brainAngularVelocityPitch: number;
  galaxyYaw: number;
  galaxyPitch: number;
  galaxyAngularVelocityYaw: number;
  galaxyAngularVelocityPitch: number;
  galaxyParallaxX: number;
  galaxyParallaxY: number;
  galaxyDepth: number;
  galaxyDepthVelocity: number;
  pointerX: number;
  pointerY: number;
  rotating: boolean;
  dragging: boolean;
  brainPointerId: number | null;
  dragMoved: number;
  suppressBrainClickUntil: number;
  lastPointerX: number;
  lastPointerY: number;
  galaxyDragging: boolean;
  galaxyPointerId: number | null;
  galaxyCaptureTarget: Element | null;
  galaxyLastPointerX: number;
  galaxyLastPointerY: number;
  energy: number;
  burst: number;
  absorb: number;
  mode: "live" | "shatter" | "absorb";
  modeStartedAt: number;
  galaxyApi: GalaxyApi | null;
  brainApi: StarBrainApi | null;
  teardown: Array<() => void>;
};

const controllers = new WeakMap<Document, CelestialController>();

function mulberry32(seed: number): () => number {
  let state = seed >>> 0;
  return () => {
    state += 0x6d2b79f5;
    let next = state;
    next = Math.imul(next ^ (next >>> 15), next | 1);
    next ^= next + Math.imul(next ^ (next >>> 7), next | 61);
    return ((next ^ (next >>> 14)) >>> 0) / 4_294_967_296;
  };
}

function normal(random: () => number): number {
  let u = 0;
  let v = 0;
  while (u === 0) u = random();
  while (v === 0) v = random();
  return Math.sqrt(-2 * Math.log(u)) * Math.cos(TAU * v);
}

function spectrumCounts(points: readonly PointSeed[]): Record<string, number> {
  const counts = Object.fromEntries(V197_SPECTRUM_NAMES.map(name => [name, 0]));
  for (const point of points) {
    const name = V197_SPECTRUM_NAMES[point.band % V197_SPECTRUM_NAMES.length];
    counts[name] += 1;
  }
  return counts;
}

function pointGeometry(points: readonly PointSeed[]): THREE.BufferGeometry {
  const geometry = new THREE.BufferGeometry();
  const positions = new Float32Array(points.length * 3);
  const sizes = new Float32Array(points.length);
  const alphas = new Float32Array(points.length);
  const bands = new Float32Array(points.length);
  const phases = new Float32Array(points.length);
  const speeds = new Float32Array(points.length);

  points.forEach((point, index) => {
    positions[index * 3] = point.x;
    positions[index * 3 + 1] = point.y;
    positions[index * 3 + 2] = point.z;
    sizes[index] = point.size;
    alphas[index] = point.alpha;
    bands[index] = point.band;
    phases[index] = point.phase;
    speeds[index] = point.speed;
  });

  geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
  geometry.setAttribute("aSize", new THREE.BufferAttribute(sizes, 1));
  geometry.setAttribute("aAlpha", new THREE.BufferAttribute(alphas, 1));
  geometry.setAttribute("aBand", new THREE.BufferAttribute(bands, 1));
  geometry.setAttribute("aPhase", new THREE.BufferAttribute(phases, 1));
  geometry.setAttribute("aSpeed", new THREE.BufferAttribute(speeds, 1));
  geometry.computeBoundingSphere();
  return geometry;
}

const STAR_VERTEX_SHADER = `
  attribute float aSize;
  attribute float aAlpha;
  attribute float aBand;
  attribute float aPhase;
  attribute float aSpeed;
  uniform float uTime;
  uniform float uPointScale;
  uniform float uRainbowStrength;
  uniform float uEnergy;
  uniform float uBurst;
  uniform float uAbsorb;
  varying vec3 vColor;
  varying float vAlpha;
  varying float vTwinkle;

  vec3 spectrum(float band) {
    float slot = mod(band + 7.0, 7.0);
    float base = floor(slot);
    float blend = smoothstep(0.0, 1.0, fract(slot));
    vec3 a;
    vec3 b;
    if (base < 0.5) { a=vec3(1.0,.322,.435); b=vec3(1.0,.62,.29); }
    else if (base < 1.5) { a=vec3(1.0,.62,.29); b=vec3(1.0,.871,.361); }
    else if (base < 2.5) { a=vec3(1.0,.871,.361); b=vec3(.494,.929,.51); }
    else if (base < 3.5) { a=vec3(.494,.929,.51); b=vec3(.388,.878,1.0); }
    else if (base < 4.5) { a=vec3(.388,.878,1.0); b=vec3(.475,.561,1.0); }
    else if (base < 5.5) { a=vec3(.475,.561,1.0); b=vec3(.761,.541,1.0); }
    else { a=vec3(.761,.541,1.0); b=vec3(1.0,.322,.435); }
    return mix(a,b,blend);
  }

  void main() {
    float rhythm = sin(uTime*aSpeed+aPhase);
    float flicker = sin(uTime*(aSpeed*2.17)+aPhase*1.71);
    float twinkle = .62 + .25*rhythm + .13*flicker;
    float spectralDrift = aBand + uTime*.045 + .16*sin(aPhase+uTime*.09);
    vec3 prism = spectrum(spectralDrift);
    vec3 warmWhite = vec3(1.0,.965,.84);
    vColor = mix(warmWhite,prism,uRainbowStrength);
    vAlpha = aAlpha * (.72 + max(0.0,twinkle)*.38) * (1.0 + uEnergy*.28);
    vTwinkle = twinkle;

    vec3 transformed = position;
    float radialBurst = uBurst*(.08 + .22*sin(aPhase*1.9+uTime*.9));
    transformed += normalize(position+vec3(.0001))*radialBurst;
    transformed *= 1.0 - uAbsorb*.42;
    transformed.y += sin(uTime*.18+aPhase)*.007;

    vec4 mvPosition = modelViewMatrix * vec4(transformed,1.0);
    gl_Position = projectionMatrix * mvPosition;
    float perspective = clamp(6.0/max(1.1,-mvPosition.z),.65,2.4);
    gl_PointSize = clamp(aSize*uPointScale*perspective*(.9+twinkle*.16),1.0,18.0);
  }
`;

const STAR_FRAGMENT_SHADER = `
  precision highp float;
  varying vec3 vColor;
  varying float vAlpha;
  varying float vTwinkle;

  void main() {
    vec2 p = gl_PointCoord - vec2(.5);
    float d = length(p);
    float core = smoothstep(.19,.01,d);
    float body = smoothstep(.44,.12,d);
    float halo = smoothstep(.5,.04,d)*.32;
    float horizontal = exp(-abs(p.y)*34.0)*smoothstep(.51,.03,abs(p.x));
    float vertical = exp(-abs(p.x)*34.0)*smoothstep(.51,.03,abs(p.y));
    float diagonalA = exp(-abs(p.x-p.y)*26.0)*smoothstep(.49,.05,d);
    float diagonalB = exp(-abs(p.x+p.y)*26.0)*smoothstep(.49,.05,d);
    float spikes = horizontal*.55 + vertical*.72 + (diagonalA+diagonalB)*.12;
    float alpha = (body*.72 + halo + spikes*(.2+.12*max(vTwinkle,0.0)))*vAlpha;
    if (alpha < .012 || d > .5) discard;
    vec3 color = mix(vColor,vec3(1.0,.99,.94),core*.9);
    gl_FragColor = vec4(color,min(1.0,alpha));
  }
`;

function starMaterial(pointScale: number, rainbowStrength: number): THREE.ShaderMaterial & {
  uniforms: StarUniforms;
} {
  return new THREE.ShaderMaterial({
    uniforms: {
      uTime: { value: 0 },
      uPointScale: { value: pointScale },
      uRainbowStrength: { value: rainbowStrength },
      uEnergy: { value: 0 },
      uBurst: { value: 0 },
      uAbsorb: { value: 0 },
    },
    vertexShader: STAR_VERTEX_SHADER,
    fragmentShader: STAR_FRAGMENT_SHADER,
    transparent: true,
    depthWrite: false,
    depthTest: true,
    blending: THREE.AdditiveBlending,
  }) as THREE.ShaderMaterial & { uniforms: StarUniforms };
}

function createGalaxy(random: () => number, mobile: boolean, areaScale: number): {
  points: PointSeed[];
  counts: Record<string, number>;
} {
  const counts = mobile
    ? { galaxy: 720, far: 500, dust: 140, super: 40 }
    : {
        galaxy: Math.round(1_100 * areaScale),
        far: Math.round(900 * areaScale),
        dust: Math.round(340 * areaScale),
        super: Math.round(60 * areaScale),
      };
  const points: PointSeed[] = [];
  let index = 0;
  const push = (x: number, y: number, z: number, size: number, alpha: number) => {
    points.push({
      x,
      y,
      z,
      size,
      alpha,
      band: index % V197_SPECTRUM_NAMES.length,
      phase: random() * TAU,
      speed: .65 + random() * 1.7,
    });
    index += 1;
  };

  for (let i = 0; i < counts.galaxy; i += 1) {
    const arm = i % 4;
    const radius = .18 + Math.pow(random(), .62) * 2.15;
    const angle = arm * TAU / 4 + radius * 3.9 + normal(random) * .2;
    const depth = normal(random) * (.045 + radius * .06);
    push(
      Math.cos(angle) * radius * 1.55,
      depth + Math.sin(angle * 1.7) * radius * .035,
      Math.sin(angle) * radius * .76,
      1.25 + Math.pow(random(), 3.1) * 3.6,
      .42 + random() * .46,
    );
  }
  for (let i = 0; i < counts.far; i += 1) {
    push(
      (random() - .5) * 8.9,
      (random() - .5) * 5.4,
      -2.6 + random() * 3.5,
      .75 + Math.pow(random(), 4) * 2.8,
      .24 + random() * .42,
    );
  }
  for (let i = 0; i < counts.dust; i += 1) {
    const radius = Math.pow(random(), .75) * 2.55;
    const angle = random() * TAU;
    push(
      Math.cos(angle) * radius * 1.5,
      normal(random) * .16,
      Math.sin(angle) * radius * .8,
      .55 + random() * .72,
      .2 + random() * .28,
    );
  }
  for (let i = 0; i < counts.super; i += 1) {
    push(
      (random() - .5) * 7.8,
      (random() - .5) * 4.6,
      -1.8 + random() * 2.5,
      3.8 + random() * 4.6,
      .62 + random() * .34,
    );
  }
  return { points, counts };
}

function createBrain(random: () => number, mobile: boolean): {
  points: PointSeed[];
  brainstemCount: number;
} {
  const cortexCount = mobile ? 900 : 1320;
  const cerebellumCount = mobile ? 190 : 280;
  const brainstemCount = mobile ? 120 : 180;
  const dustCount = mobile ? 430 : 760;
  const points: PointSeed[] = [];
  let index = 0;

  const push = (
    x: number,
    y: number,
    z: number,
    tissue: PointSeed["tissue"],
    sizeScale = 1,
    alphaScale = 1,
  ) => {
    const dust = tissue === "dust";
    points.push({
      x,
      y,
      z,
      tissue,
      size: (dust ? .42 + Math.pow(random(), 2.8) * .9 : .75 + Math.pow(random(), 2.2) * 2.8) * sizeScale,
      alpha: (dust ? .28 + random() * .28 : .58 + random() * .38) * alphaScale,
      band: index % V197_SPECTRUM_NAMES.length,
      phase: random() * TAU,
      speed: .72 + random() * 1.8,
    });
    index += 1;
  };

  for (let i = 0; i < cortexCount; i += 1) {
    const t = (i + .5) / cortexCount;
    const inclination = Math.acos(1 - 2 * t);
    const azimuth = Math.PI * (1 + Math.sqrt(5)) * i;
    let x = Math.sin(inclination) * Math.cos(azimuth);
    let y = Math.cos(inclination);
    let z = Math.sin(inclination) * Math.sin(azimuth);
    let fold = .058 * Math.sin(azimuth * 7 + Math.sin(inclination * 4) * 1.8)
      + .036 * Math.sin(azimuth * 13 + inclination * 9);
    const fissure = Math.abs(x) < .12 && y > -.15;
    if (fissure) fold = -.05;
    const folded = 1 + fold;
    x *= folded;
    y *= folded;
    z *= folded;
    x *= 1;
    y *= .83;
    z *= 1.26;
    if (Math.abs(x) < .11 && y > -.12) {
      x = Math.sign(x || random() - .5) * (.11 + Math.abs(x) * .35);
    }
    if (z > .55) x *= 1 - .16 * (z - .55);
    if (y < -.42) y = -.42 + (y + .42) * .45;
    if (y < -.05 && Math.abs(x) > .52 && z > .1) y -= .07;
    push(x, y, z, "cortex");
  }

  for (let i = 0; i < cerebellumCount; i += 1) {
    const t = (i + .5) / cerebellumCount;
    const inclination = Math.acos(1 - 2 * t);
    const azimuth = Math.PI * (1 + Math.sqrt(5)) * i;
    const x = Math.sin(inclination) * Math.cos(azimuth);
    const y = Math.cos(inclination);
    const z = Math.sin(inclination) * Math.sin(azimuth);
    const fold = 1 + .045 * Math.sin(inclination * 16);
    push(x * .55 * fold, -.55 + y * .3 * fold, -.8 + z * .42 * fold, "cerebellum", .92);
  }

  const stemAngle = Math.PI * (3 - Math.sqrt(5));
  for (let i = 0; i < brainstemCount; i += 1) {
    const t = (i + .5) / brainstemCount;
    const angle = i * stemAngle;
    const pons = Math.exp(-Math.pow((t - .28) / .17, 2));
    const shell = Math.sqrt(((i % 7) + .65) / 7);
    const radius = (.11 - .045 * t + .052 * pons) * shell;
    const centerX = .014 * Math.sin(t * Math.PI * 1.3);
    const centerY = -.4 - t * .62;
    const centerZ = -.38 + t * .22 - .045 * Math.sin(t * Math.PI);
    push(
      centerX + Math.cos(angle) * radius,
      centerY,
      centerZ + Math.sin(angle) * radius * .76,
      "brainstem",
      .96,
    );
  }

  for (let i = 0; i < dustCount; i += 1) {
    const t = (i + .5) / dustCount;
    const inclination = Math.acos(1 - 2 * t);
    const azimuth = Math.PI * (1 + Math.sqrt(5)) * i * 1.618;
    let x = Math.sin(inclination) * Math.cos(azimuth);
    let y = Math.cos(inclination);
    let z = Math.sin(inclination) * Math.sin(azimuth);
    const depth = .42 + Math.pow(random(), .6) * .62;
    x *= depth;
    y *= depth * .83;
    z *= depth * 1.26;
    if (Math.abs(x) < .1 && y > -.12) x = Math.sign(x || random() - .5) * (.1 + Math.abs(x) * .35);
    if (y < -.42) y = -.42 + (y + .42) * .45;
    push(x, y, z, "dust", 1, .78);
  }

  return { points, brainstemCount };
}

function brainConnections(points: readonly PointSeed[]): THREE.LineSegments {
  const structural = points
    .map((point, index) => ({ point, index }))
    .filter(({ point }) => point.tissue !== "dust");
  const positions: number[] = [];
  const colors: number[] = [];

  for (let sourceIndex = 0; sourceIndex < structural.length; sourceIndex += 1) {
    const source = structural[sourceIndex];
    let nearest: typeof source | null = null;
    let distance = Number.POSITIVE_INFINITY;
    for (let targetIndex = 0; targetIndex < structural.length; targetIndex += 1) {
      if (sourceIndex === targetIndex) continue;
      const target = structural[targetIndex];
      if (source.point.tissue !== target.point.tissue) continue;
      const dx = source.point.x - target.point.x;
      const dy = source.point.y - target.point.y;
      const dz = source.point.z - target.point.z;
      const nextDistance = dx * dx + dy * dy + dz * dz;
      if (nextDistance < distance) {
        distance = nextDistance;
        nearest = target;
      }
    }
    if (!nearest || nearest.index < source.index || distance > .08) continue;
    positions.push(
      source.point.x,
      source.point.y,
      source.point.z,
      nearest.point.x,
      nearest.point.y,
      nearest.point.z,
    );
    const sourceColor = V197_SPECTRUM[source.point.band % V197_SPECTRUM.length];
    const targetColor = V197_SPECTRUM[nearest.point.band % V197_SPECTRUM.length];
    const lineColor = sourceColor.clone().lerp(targetColor, .5).lerp(IVORY, .48);
    colors.push(lineColor.r, lineColor.g, lineColor.b, lineColor.r, lineColor.g, lineColor.b);
  }

  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
  geometry.setAttribute("color", new THREE.Float32BufferAttribute(colors, 3));
  const material = new THREE.LineBasicMaterial({
    vertexColors: true,
    transparent: true,
    opacity: .045,
    depthWrite: false,
    blending: THREE.AdditiveBlending,
  });
  return new THREE.LineSegments(geometry, material);
}

function stageIsVisible(controller: CelestialController, force = false): boolean {
  if (controller.document.hidden) {
    controller.stageVisible = false;
    return false;
  }
  const now = controller.frameWindow.performance.now();
  if (!force && now - controller.stageVisibilityCheckedAt < 250) return controller.stageVisible;
  controller.stageVisibilityCheckedAt = now;
  const stage = controller.frameWindow.frameElement as HTMLElement | null;
  if (!stage) {
    controller.stageVisible = true;
    return true;
  }
  if (stage.getAttribute("aria-hidden") === "true" || stage.classList.contains("is-exiting")) {
    controller.stageVisible = false;
    return false;
  }
  const rect = stage.getBoundingClientRect();
  if (rect.width < 2 || rect.height < 2) {
    controller.stageVisible = false;
    return false;
  }
  const view = stage.ownerDocument.defaultView;
  if (!view) {
    controller.stageVisible = true;
    return true;
  }
  const style = view.getComputedStyle(stage);
  controller.stageVisible = style.display !== "none"
    && style.visibility !== "hidden"
    && Number.parseFloat(style.opacity || "1") >= .02;
  return controller.stageVisible;
}

function bind<K extends keyof WindowEventMap>(
  target: Window,
  type: K,
  listener: (event: WindowEventMap[K]) => void,
  options?: AddEventListenerOptions,
): () => void;
function bind<K extends keyof HTMLElementEventMap>(
  target: HTMLElement,
  type: K,
  listener: (event: HTMLElementEventMap[K]) => void,
  options?: AddEventListenerOptions,
): () => void;
function bind(
  target: Window | HTMLElement,
  type: string,
  listener: EventListener,
  options?: AddEventListenerOptions,
): () => void {
  target.addEventListener(type, listener, options);
  return () => target.removeEventListener(type, listener, options);
}

function updateSizes(controller: CelestialController): void {
  const width = Math.max(2, controller.frameWindow.innerWidth);
  const height = Math.max(2, controller.frameWindow.innerHeight);
  const pixelBudget = 2_800_000;
  const dpr = Math.max(
    1,
    Math.min(
      controller.frameWindow.devicePixelRatio || 1,
      1.5,
      Math.sqrt(pixelBudget / Math.max(1, width * height)),
    ),
  );
  const bufferWidth = Math.max(2, Math.round(width * dpr));
  const bufferHeight = Math.max(2, Math.round(height * dpr));
  if (controller.width !== width || controller.height !== height || controller.dpr !== dpr) {
    controller.width = width;
    controller.height = height;
    controller.dpr = dpr;
    controller.renderer.setSize(bufferWidth, bufferHeight, false);
    controller.galaxyCanvas.width = bufferWidth;
    controller.galaxyCanvas.height = bufferHeight;
    controller.galaxyCanvas.style.width = `${width}px`;
    controller.galaxyCanvas.style.height = `${height}px`;
    controller.galaxyCamera.aspect = width / height;
    controller.galaxyCamera.updateProjectionMatrix();
    controller.galaxyMaterial.uniforms.uPointScale.value = dpr;
    controller.brainMaterial.uniforms.uPointScale.value = dpr * 1.12;
  }

  const brainRect = controller.brainHost.getBoundingClientRect();
  const brainWidth = Math.max(2, Math.round(brainRect.width * dpr));
  const brainHeight = Math.max(2, Math.round(brainRect.height * dpr));
  if (controller.brainWidth !== brainWidth || controller.brainHeight !== brainHeight) {
    controller.brainWidth = brainWidth;
    controller.brainHeight = brainHeight;
    controller.brainCanvas.width = brainWidth;
    controller.brainCanvas.height = brainHeight;
    controller.brainCanvas.style.width = `${Math.max(2, brainRect.width)}px`;
    controller.brainCanvas.style.height = `${Math.max(2, brainRect.height)}px`;
    controller.brainCamera.aspect = Math.max(.2, brainRect.width / Math.max(2, brainRect.height));
    controller.brainCamera.updateProjectionMatrix();
  }
}

function updateAnimation(controller: CelestialController, now: number): void {
  const seconds = now / 1_000;
  const elapsed = controller.lastAnimationAt ? now - controller.lastAnimationAt : 16.667;
  controller.lastAnimationAt = now;
  const frameScale = THREE.MathUtils.clamp(elapsed / 16.667, .25, 2.5);
  const brainEase = 1 - Math.pow(.72, frameScale);
  controller.yaw += (controller.targetYaw - controller.yaw) * brainEase;
  controller.pitch += (controller.targetPitch - controller.pitch) * brainEase;
  if (!controller.dragging && !controller.reducedMotion) {
    controller.targetYaw += controller.brainAngularVelocityYaw * frameScale;
    controller.targetPitch = THREE.MathUtils.clamp(
      controller.targetPitch + controller.brainAngularVelocityPitch * frameScale,
      -1.05,
      1.05,
    );
    const brainDamping = Math.pow(.88, frameScale);
    controller.brainAngularVelocityYaw *= brainDamping;
    controller.brainAngularVelocityPitch *= brainDamping;
    if (Math.abs(controller.brainAngularVelocityYaw) < .00008) {
      controller.brainAngularVelocityYaw = 0;
      controller.targetYaw += .00135 * frameScale;
    }
    if (Math.abs(controller.brainAngularVelocityPitch) < .00008) {
      controller.brainAngularVelocityPitch = 0;
      controller.targetPitch *= Math.pow(.994, frameScale);
    }
  }
  if (!controller.galaxyDragging && !controller.reducedMotion) {
    controller.galaxyYaw += controller.galaxyAngularVelocityYaw * frameScale;
    controller.galaxyPitch = THREE.MathUtils.clamp(
      controller.galaxyPitch + controller.galaxyAngularVelocityPitch * frameScale,
      -.88,
      .88,
    );
    controller.galaxyDepth += controller.galaxyDepthVelocity * frameScale;
    const galaxyDamping = Math.pow(.9, frameScale);
    controller.galaxyAngularVelocityYaw *= galaxyDamping;
    controller.galaxyAngularVelocityPitch *= galaxyDamping;
    controller.galaxyDepthVelocity *= Math.pow(.84, frameScale);
    controller.galaxyDepth *= Math.pow(.9, frameScale);
    if (controller.rotating && Math.abs(controller.galaxyAngularVelocityYaw) < .00006) {
      controller.galaxyAngularVelocityYaw = 0;
      controller.galaxyYaw += .00048 * frameScale;
    }
    if (Math.abs(controller.galaxyAngularVelocityPitch) < .00006) {
      controller.galaxyAngularVelocityPitch = 0;
    }
  }

  const parallaxEase = 1 - Math.pow(.94, frameScale);
  const targetParallaxX = controller.galaxyDragging ? 0 : controller.pointerX;
  const targetParallaxY = controller.galaxyDragging ? 0 : controller.pointerY;
  controller.galaxyParallaxX += (targetParallaxX - controller.galaxyParallaxX) * parallaxEase;
  controller.galaxyParallaxY += (targetParallaxY - controller.galaxyParallaxY) * parallaxEase;
  const parallaxYaw = controller.galaxyParallaxX * .065;
  const parallaxPitch = controller.galaxyParallaxY * .052;

  controller.galaxyGroup.rotation.y = controller.galaxyYaw + parallaxYaw;
  controller.galaxyGroup.rotation.x = .34 + controller.galaxyPitch + parallaxPitch;
  controller.galaxyGroup.rotation.z = -.11
    + Math.sin(seconds * .05) * .012
    + THREE.MathUtils.clamp(controller.galaxyAngularVelocityYaw * -.62, -.025, .025);
  controller.galaxyGroup.position.x = controller.galaxyParallaxX * .055;
  controller.galaxyGroup.position.y = controller.galaxyParallaxY * -.04;
  controller.galaxyCamera.position.z = 5.15 + THREE.MathUtils.clamp(controller.galaxyDepth, -.13, .13);
  controller.brainGroup.rotation.y = controller.yaw;
  controller.brainGroup.rotation.x = controller.pitch;
  controller.brainGroup.rotation.z = Math.sin(seconds * .12) * .018
    + THREE.MathUtils.clamp(controller.brainAngularVelocityYaw * -.42, -.035, .035);

  if (controller.mode === "shatter") {
    const elapsed = (now - controller.modeStartedAt) / 1_000;
    controller.burst = elapsed < .55
      ? Math.sin(Math.min(1, elapsed / .55) * Math.PI) * .9
      : Math.max(0, 1 - (elapsed - .55) / 1.35) * .32;
    if (elapsed > 1.9) controller.mode = "live";
  } else if (controller.mode === "absorb") {
    const elapsed = (now - controller.modeStartedAt) / 1_000;
    controller.absorb = elapsed < .48
      ? Math.sin(Math.min(1, elapsed / .48) * Math.PI) * .78
      : Math.max(0, 1 - (elapsed - .48) / .8) * .34;
    if (elapsed > 1.3) controller.mode = "live";
  } else {
    controller.burst *= .91;
    controller.absorb *= .9;
  }
  controller.energy *= .94;

  for (const material of [controller.galaxyMaterial, controller.brainMaterial]) {
    material.uniforms.uTime.value = seconds;
    material.uniforms.uEnergy.value = controller.energy;
  }
  controller.brainMaterial.uniforms.uBurst.value = controller.burst;
  controller.brainMaterial.uniforms.uAbsorb.value = controller.absorb;
}

function paint(controller: CelestialController, now: number): void {
  updateSizes(controller);
  updateAnimation(controller, now);

  const renderWidth = controller.renderCanvas.width;
  const renderHeight = controller.renderCanvas.height;
  controller.renderer.setScissorTest(false);
  controller.renderer.setViewport(0, 0, renderWidth, renderHeight);
  controller.renderer.setClearColor(0x000000, 0);
  controller.renderer.clear(true, true, true);
  controller.renderer.render(controller.galaxyScene, controller.galaxyCamera);
  controller.galaxyContext.setTransform(1, 0, 0, 1, 0, 0);
  controller.galaxyContext.clearRect(0, 0, controller.galaxyCanvas.width, controller.galaxyCanvas.height);
  controller.galaxyContext.drawImage(
    controller.renderCanvas,
    0,
    0,
    renderWidth,
    renderHeight,
    0,
    0,
    controller.galaxyCanvas.width,
    controller.galaxyCanvas.height,
  );

  const hostRect = controller.brainHost.getBoundingClientRect();
  if (hostRect.width > 2 && hostRect.height > 2) {
    const brainWidth = Math.min(renderWidth, controller.brainWidth);
    const brainHeight = Math.min(renderHeight, controller.brainHeight);
    controller.renderer.setScissorTest(true);
    controller.renderer.setScissor(0, renderHeight - brainHeight, brainWidth, brainHeight);
    controller.renderer.setViewport(0, renderHeight - brainHeight, brainWidth, brainHeight);
    controller.renderer.setClearColor(0x000000, 0);
    controller.renderer.clear(true, true, true);
    controller.renderer.render(controller.brainScene, controller.brainCamera);
    controller.brainContext.setTransform(1, 0, 0, 1, 0, 0);
    controller.brainContext.clearRect(0, 0, controller.brainCanvas.width, controller.brainCanvas.height);
    controller.brainContext.drawImage(
      controller.renderCanvas,
      0,
      0,
      brainWidth,
      brainHeight,
      0,
      0,
      controller.brainCanvas.width,
      controller.brainCanvas.height,
    );
  }
  controller.renderer.setScissorTest(false);

  controller.frameCount += 1;
  controller.fpsFrames += 1;
  if (!controller.fpsStartedAt) controller.fpsStartedAt = now;
  const fpsWindow = now - controller.fpsStartedAt;
  if (fpsWindow >= 1_000) {
    controller.measuredFps = Math.round(controller.fpsFrames * 1_000 / fpsWindow * 10) / 10;
    controller.fpsStartedAt = now;
    controller.fpsFrames = 0;
  }
  controller.staticFramePainted = true;
}

function requestFrame(controller: CelestialController): void {
  if (controller.disposed || controller.raf !== null || !stageIsVisible(controller)) return;
  if (controller.reducedMotion && controller.staticFramePainted) return;
  if (controller.reducedMotion) {
    paint(controller, controller.frameWindow.performance.now());
    return;
  }
  controller.raf = controller.frameWindow.requestAnimationFrame(now => {
    controller.raf = null;
    if (controller.disposed || !stageIsVisible(controller)) return;
    const mobile = Math.max(controller.frameWindow.innerWidth, controller.frameWindow.parent.innerWidth || 0) < 700;
    const minimumGap = mobile ? 33 : 20;
    if (controller.lastPaintAt && now - controller.lastPaintAt < minimumGap) {
      requestFrame(controller);
      return;
    }
    controller.lastPaintAt = now;
    paint(controller, now);
    if (!controller.reducedMotion) requestFrame(controller);
  });
}

function syncStageAnimation(controller: CelestialController): void {
  controller.stageVisibilityCheckedAt = 0;
  if (!stageIsVisible(controller, true)) {
    if (controller.raf !== null) controller.frameWindow.cancelAnimationFrame(controller.raf);
    controller.raf = null;
    return;
  }
  controller.staticFramePainted = false;
  requestFrame(controller);
}

function disposeObject(object: THREE.Object3D): void {
  object.traverse(child => {
    const disposable = child as THREE.Object3D & {
      geometry?: THREE.BufferGeometry;
      material?: THREE.Material | THREE.Material[];
    };
    disposable.geometry?.dispose();
    const materials = Array.isArray(disposable.material) ? disposable.material : [disposable.material];
    materials.forEach(material => material?.dispose());
  });
}

function disposeController(controller: CelestialController): void {
  if (controller.disposed) return;
  controller.disposed = true;
  if (controller.raf !== null) controller.frameWindow.cancelAnimationFrame(controller.raf);
  controller.raf = null;
  controller.brainHost.classList.remove("is-grabbing");
  controller.document.documentElement.classList.remove("nur-galaxy-grabbing");
  controller.teardown.forEach(undo => {
    try { undo(); } catch { /* disposal is best effort */ }
  });
  controller.teardown.length = 0;
  disposeObject(controller.galaxyScene);
  disposeObject(controller.brainScene);
  controller.renderer.dispose();
  controller.renderCanvas.width = 0;
  controller.renderCanvas.height = 0;
  controller.brainCanvas.width = 0;
  controller.brainCanvas.height = 0;
  controller.brainCanvas.remove();
  controllers.delete(controller.document);
  if (controller.frameWindow.nurStarBrain === controller.brainApi) {
    delete controller.frameWindow.nurStarBrain;
  }
  if (controller.frameWindow.nurGalaxy === controller.galaxyApi) delete controller.frameWindow.nurGalaxy;
  if (controller.frameWindow.__nurGalaxy === controller.galaxyApi) delete controller.frameWindow.__nurGalaxy;
}

const GALAXY_INTERACTION_BLOCKERS = [
  "button",
  "a",
  "input",
  "textarea",
  "select",
  "label",
  "summary",
  "[contenteditable='true']",
  "[role='button']",
  "[role='tab']",
  "[role='slider']",
  "[data-action]",
  "[data-system]",
  "[data-system-slug]",
  ".nur-rail",
  ".nur-topbar",
  ".talk-chamber",
  ".journal-pad",
  ".universe-insight-panel",
  "#nur-map-root",
  "#nur-orbit-root",
  "#nur-timeline-root",
  ".nur-insights-pane",
].join(",");

function eventElement(target: EventTarget | null): Element | null {
  if (!target) return null;
  const candidate = target as Partial<Element>;
  return typeof candidate.closest === "function" && typeof candidate.contains === "function"
    ? target as Element
    : null;
}

function canStartGalaxyDrag(controller: CelestialController, event: PointerEvent): boolean {
  if (!event.isPrimary || (event.pointerType === "mouse" && event.button !== 0)) return false;
  const target = eventElement(event.target);
  if (!target || controller.brainHost.contains(target)) return false;
  if (target.closest(GALAXY_INTERACTION_BLOCKERS)) return false;
  for (const node of event.composedPath()) {
    const element = eventElement(node);
    if (!element || element === controller.document.body) break;
    if ((element as HTMLElement).onclick || controller.frameWindow.getComputedStyle(element).cursor === "pointer") {
      return false;
    }
  }
  return true;
}

function installInteractions(controller: CelestialController): void {
  const { brainCanvas, frameWindow } = controller;
  controller.teardown.push(bind(frameWindow, "pointermove", event => {
    controller.pointerX = event.clientX / Math.max(1, controller.width) - .5;
    controller.pointerY = event.clientY / Math.max(1, controller.height) - .5;
    if (!controller.galaxyDragging || event.pointerId !== controller.galaxyPointerId) return;
    event.preventDefault();
    const dx = event.clientX - controller.galaxyLastPointerX;
    const dy = event.clientY - controller.galaxyLastPointerY;
    controller.galaxyLastPointerX = event.clientX;
    controller.galaxyLastPointerY = event.clientY;
    controller.galaxyYaw += dx * .0044;
    controller.galaxyPitch = THREE.MathUtils.clamp(controller.galaxyPitch + dy * .0037, -.88, .88);
    controller.galaxyAngularVelocityYaw = THREE.MathUtils.lerp(
      controller.galaxyAngularVelocityYaw,
      dx * .00075,
      .58,
    );
    controller.galaxyAngularVelocityPitch = THREE.MathUtils.lerp(
      controller.galaxyAngularVelocityPitch,
      dy * .00065,
      .58,
    );
    controller.galaxyDepthVelocity = Math.min(.012, Math.hypot(dx, dy) * .00042);
    controller.staticFramePainted = false;
    requestFrame(controller);
  }, { passive: false }));

  controller.teardown.push(bind(frameWindow, "pointerdown", event => {
    if (!canStartGalaxyDrag(controller, event)) return;
    controller.galaxyDragging = true;
    controller.galaxyPointerId = event.pointerId;
    controller.galaxyLastPointerX = event.clientX;
    controller.galaxyLastPointerY = event.clientY;
    controller.galaxyAngularVelocityYaw = 0;
    controller.galaxyAngularVelocityPitch = 0;
    const target = eventElement(event.target) ?? controller.galaxyCanvas;
    controller.galaxyCaptureTarget = target;
    try { target.setPointerCapture?.(event.pointerId); } catch { /* active window handlers retain ownership */ }
    controller.document.documentElement.classList.add("nur-galaxy-grabbing");
    event.preventDefault();
  }, { passive: false }));

  const endGalaxyDrag = (event: PointerEvent) => {
    if (!controller.galaxyDragging || event.pointerId !== controller.galaxyPointerId) return;
    const capture = controller.galaxyCaptureTarget;
    try {
      if (capture?.hasPointerCapture?.(event.pointerId)) capture.releasePointerCapture(event.pointerId);
    } catch { /* release is best effort after a route or target transition */ }
    controller.galaxyDragging = false;
    controller.galaxyPointerId = null;
    controller.galaxyCaptureTarget = null;
    controller.document.documentElement.classList.remove("nur-galaxy-grabbing");
  };
  controller.teardown.push(bind(frameWindow, "pointerup", endGalaxyDrag));
  controller.teardown.push(bind(frameWindow, "pointercancel", endGalaxyDrag));

  controller.teardown.push(bind(brainCanvas, "pointerdown", event => {
    if (!event.isPrimary || (event.pointerType === "mouse" && event.button !== 0)) return;
    event.preventDefault();
    event.stopPropagation();
    controller.dragging = true;
    controller.brainPointerId = event.pointerId;
    controller.dragMoved = 0;
    controller.lastPointerX = event.clientX;
    controller.lastPointerY = event.clientY;
    controller.brainAngularVelocityYaw = 0;
    controller.brainAngularVelocityPitch = 0;
    try { brainCanvas.setPointerCapture?.(event.pointerId); } catch { /* active canvas handlers retain ownership */ }
    controller.brainHost.classList.add("is-grabbing");
  }));
  controller.teardown.push(bind(brainCanvas, "pointermove", event => {
    event.stopPropagation();
    controller.pointerX = event.clientX / Math.max(1, controller.width) - .5;
    controller.pointerY = event.clientY / Math.max(1, controller.height) - .5;
    if (!controller.dragging || event.pointerId !== controller.brainPointerId) return;
    event.preventDefault();
    const dx = event.clientX - controller.lastPointerX;
    const dy = event.clientY - controller.lastPointerY;
    controller.lastPointerX = event.clientX;
    controller.lastPointerY = event.clientY;
    controller.dragMoved += Math.abs(dx) + Math.abs(dy);
    controller.targetYaw += dx * .0062;
    controller.targetPitch = THREE.MathUtils.clamp(controller.targetPitch + dy * .0048, -1.05, 1.05);
    controller.brainAngularVelocityYaw = THREE.MathUtils.lerp(
      controller.brainAngularVelocityYaw,
      dx * .0011,
      .68,
    );
    controller.brainAngularVelocityPitch = THREE.MathUtils.lerp(
      controller.brainAngularVelocityPitch,
      dy * .0009,
      .68,
    );
    controller.staticFramePainted = false;
    requestFrame(controller);
  }));
  const endDrag = (event: PointerEvent) => {
    event.stopPropagation();
    if (!controller.dragging || event.pointerId !== controller.brainPointerId) return;
    try {
      if (brainCanvas.hasPointerCapture?.(event.pointerId)) brainCanvas.releasePointerCapture(event.pointerId);
    } catch { /* release is best effort after a route or target transition */ }
    if (controller.dragMoved > 8) {
      controller.suppressBrainClickUntil = controller.frameWindow.performance.now() + 400;
    }
    controller.dragMoved = 0;
    controller.dragging = false;
    controller.brainPointerId = null;
    controller.brainHost.classList.remove("is-grabbing");
  };
  controller.teardown.push(bind(brainCanvas, "pointerup", endDrag));
  controller.teardown.push(bind(brainCanvas, "pointercancel", endDrag));
  controller.teardown.push(bind(brainCanvas, "click", event => {
    if (controller.frameWindow.performance.now() < controller.suppressBrainClickUntil) {
      event.preventDefault();
      event.stopPropagation();
      event.stopImmediatePropagation();
    }
  }));
  controller.teardown.push(bind(brainCanvas, "wheel", event => {
    event.preventDefault();
    const next = controller.brainCamera.position.z + (event.deltaY > 0 ? .22 : -.22);
    controller.brainCamera.position.z = THREE.MathUtils.clamp(next, 3.8, 6.2);
    requestFrame(controller);
  }, { passive: false }));
  controller.teardown.push(bind(brainCanvas, "dblclick", event => {
    event.stopPropagation();
    controller.energy = Math.min(1.7, controller.energy + 1.25);
    requestFrame(controller);
  }));
  controller.teardown.push(bind(frameWindow, "blur", () => {
    controller.dragging = false;
    controller.brainPointerId = null;
    controller.galaxyDragging = false;
    controller.galaxyPointerId = null;
    controller.galaxyCaptureTarget = null;
    controller.brainHost.classList.remove("is-grabbing");
    controller.document.documentElement.classList.remove("nur-galaxy-grabbing");
  }));
}

function createController(
  document: Document,
  frameWindow: CelestialWindow,
  brainHost: HTMLElement,
): CelestialController | null {
  const galaxyCanvas = document.querySelector<HTMLCanvasElement>("#space3d");
  if (!galaxyCanvas) return null;
  const galaxyContext = galaxyCanvas.getContext("2d", { alpha: true });
  if (!galaxyContext) return null;

  const legacyGalaxy = frameWindow.nurGalaxy;
  try { legacyGalaxy?.dispose?.(); } catch { /* the new owner still mounts */ }
  try { frameWindow.nurStarBrain?.dispose?.(); } catch { /* the new owner still mounts */ }

  document.getElementById("nur-brain-canvas")?.remove();
  const brainCanvas = document.createElement("canvas");
  brainCanvas.id = "nur-brain-canvas";
  brainCanvas.dataset.nurRenderer = V197_CELESTIAL_ENGINE;
  brainHost.append(brainCanvas);
  const brainContext = brainCanvas.getContext("2d", { alpha: true });
  if (!brainContext) {
    brainCanvas.remove();
    return null;
  }

  const renderCanvas = document.createElement("canvas");
  let renderer: THREE.WebGLRenderer;
  try {
    renderer = new THREE.WebGLRenderer({
      canvas: renderCanvas,
      alpha: true,
      antialias: true,
      powerPreference: "high-performance",
      premultipliedAlpha: true,
      preserveDrawingBuffer: true,
    });
  } catch (error) {
    brainHost.dataset.nurCelestialError = error instanceof Error ? error.message : "webgl-unavailable";
    brainCanvas.remove();
    return null;
  }
  renderer.setPixelRatio(1);
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.NoToneMapping;
  renderer.autoClear = false;

  const mobile = Math.max(frameWindow.innerWidth, frameWindow.parent.innerWidth || 0) < 700;
  const areaScale = Math.min(1.35, Math.max(1, (frameWindow.innerWidth * frameWindow.innerHeight) / 1_600_000));
  const galaxyRandom = mulberry32(0x197c0de);
  const brainRandom = mulberry32(0x43b7a11);
  const galaxy = createGalaxy(galaxyRandom, mobile, areaScale);
  const brain = createBrain(brainRandom, mobile);

  const galaxyScene = new THREE.Scene();
  const galaxyCamera = new THREE.PerspectiveCamera(55, 1, .1, 30);
  galaxyCamera.position.set(0, 0, 5.15);
  const galaxyGroup = new THREE.Group();
  const galaxyMaterial = starMaterial(1, .78);
  galaxyGroup.add(new THREE.Points(pointGeometry(galaxy.points), galaxyMaterial));
  galaxyScene.add(galaxyGroup);

  const brainScene = new THREE.Scene();
  const brainCamera = new THREE.PerspectiveCamera(35, 1, .1, 20);
  brainCamera.position.set(0, -.04, 4.55);
  const brainGroup = new THREE.Group();
  const brainMaterial = starMaterial(1.34, .88);
  brainGroup.add(new THREE.Points(pointGeometry(brain.points), brainMaterial));
  brainGroup.add(brainConnections(brain.points));
  brainScene.add(brainGroup);

  const reducedMotion = frameWindow.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const controller: CelestialController = {
    document,
    frameWindow,
    brainHost,
    galaxyCanvas,
    galaxyContext,
    brainCanvas,
    brainContext,
    renderCanvas,
    renderer,
    galaxyScene,
    galaxyCamera,
    galaxyGroup,
    galaxyMaterial,
    brainScene,
    brainCamera,
    brainGroup,
    brainMaterial,
    galaxyCounts: galaxy.counts,
    galaxySpectrumCounts: spectrumCounts(galaxy.points),
    brainSpectrumCounts: spectrumCounts(brain.points),
    galaxyPointCount: galaxy.points.length,
    brainPointCount: brain.points.length,
    brainstemPointCount: brain.brainstemCount,
    reducedMotion,
    stageVisible: false,
    stageVisibilityCheckedAt: 0,
    raf: null,
    disposed: false,
    staticFramePainted: false,
    frameCount: 0,
    measuredFps: 0,
    fpsStartedAt: 0,
    fpsFrames: 0,
    lastPaintAt: 0,
    lastAnimationAt: 0,
    width: 0,
    height: 0,
    dpr: 0,
    brainWidth: 0,
    brainHeight: 0,
    yaw: .72,
    pitch: -.12,
    targetYaw: .72,
    targetPitch: -.12,
    brainAngularVelocityYaw: 0,
    brainAngularVelocityPitch: 0,
    galaxyYaw: .08,
    galaxyPitch: 0,
    galaxyAngularVelocityYaw: 0,
    galaxyAngularVelocityPitch: 0,
    galaxyParallaxX: 0,
    galaxyParallaxY: 0,
    galaxyDepth: 0,
    galaxyDepthVelocity: 0,
    pointerX: 0,
    pointerY: 0,
    rotating: true,
    dragging: false,
    brainPointerId: null,
    dragMoved: 0,
    suppressBrainClickUntil: 0,
    lastPointerX: 0,
    lastPointerY: 0,
    galaxyDragging: false,
    galaxyPointerId: null,
    galaxyCaptureTarget: null,
    galaxyLastPointerX: 0,
    galaxyLastPointerY: 0,
    energy: 0,
    burst: 0,
    absorb: 0,
    mode: "live",
    modeStartedAt: 0,
    galaxyApi: null,
    brainApi: null,
    teardown: [],
  };
  controllers.set(document, controller);

  const diagnosticsBase = () => {
    const stage = frameWindow.frameElement;
    return {
      spectrumBands: V197_SPECTRUM_NAMES,
      engine: V197_CELESTIAL_ENGINE,
      oneRafOwner: true,
      frameScheduled: controller.raf !== null,
      frameCount: controller.frameCount,
      fps: controller.measuredFps,
      shouldRender: stageIsVisible(controller),
      stageId: stage?.id ?? null,
      stageClass: stage instanceof Element ? stage.className : null,
      stageHidden: stage?.getAttribute("aria-hidden") ?? null,
    };
  };

  const burst = (intensity = 1) => {
    controller.energy = Math.min(1.7, controller.energy + Math.max(.08, intensity));
    controller.burst = Math.min(1, controller.burst + intensity * .18);
    requestFrame(controller);
  };
  const galaxyApi: GalaxyApi = {
    addEvent: () => burst(.18),
    burst: (_x, _y, intensity = .18) => burst(intensity),
    setMode: mode => { frameWindow.nurGalaxyMode = mode || "today"; },
    setRotate: enabled => { controller.rotating = enabled; frameWindow.nurGalaxyRotate = enabled; },
    getParticleCount: () => controller.galaxyPointCount,
    getTransientParticleCount: () => 0,
    getParticleDiagnostics: () => ({
      total: controller.galaxyPointCount,
      transient: 0,
      finite: 0,
      invalid: 0,
      minLife: null,
      maxLife: null,
      byKind: { ...controller.galaxyCounts },
      spectrumCounts: { ...controller.galaxySpectrumCounts },
      yaw: controller.galaxyYaw,
      pitch: controller.galaxyPitch,
      angularVelocityYaw: controller.galaxyAngularVelocityYaw,
      angularVelocityPitch: controller.galaxyAngularVelocityPitch,
      dragging: controller.galaxyDragging,
      parallaxX: controller.galaxyParallaxX,
      parallaxY: controller.galaxyParallaxY,
      ...diagnosticsBase(),
    }),
    dispose: () => disposeController(controller),
  };
  const brainApi: StarBrainApi = {
    storm: (power = 1) => burst(power),
    absorb: () => {
      controller.mode = "absorb";
      controller.modeStartedAt = performance.now();
      controller.staticFramePainted = false;
      requestFrame(controller);
    },
    shatter: () => {
      controller.mode = "shatter";
      controller.modeStartedAt = performance.now();
      controller.staticFramePainted = false;
      requestFrame(controller);
    },
    firePulse: () => burst(.32),
    dispose: () => disposeController(controller),
    getDiagnostics: () => ({
      reducedMotion,
      frameScheduled: controller.raf !== null,
      staticFramePainted: controller.staticFramePainted,
      stageVisible: stageIsVisible(controller),
      pointCount: controller.brainPointCount,
      brainstemPointCount: controller.brainstemPointCount,
      spectrumBands: V197_SPECTRUM_NAMES,
      spectrumCounts: { ...controller.brainSpectrumCounts },
      engine: V197_CELESTIAL_ENGINE,
      oneRafOwner: true,
      frameCount: controller.frameCount,
      fps: controller.measuredFps,
      yaw: controller.yaw,
      pitch: controller.pitch,
      angularVelocityYaw: controller.brainAngularVelocityYaw,
      angularVelocityPitch: controller.brainAngularVelocityPitch,
      dragging: controller.dragging,
    }),
  };
  controller.galaxyApi = galaxyApi;
  controller.brainApi = brainApi;
  frameWindow.nurGalaxy = galaxyApi;
  frameWindow.__nurGalaxy = galaxyApi;
  frameWindow.nurStarBrain = brainApi;
  frameWindow.nur3dBurst = (_x, _y, intensity = .18) => burst(intensity);
  frameWindow.nur3dWordmarkBurst = rect => { if (rect) burst(.34); };

  brainHost.dataset.nurPointCount = String(controller.brainPointCount);
  brainHost.dataset.nurDustCount = String(mobile ? 430 : 760);
  brainHost.dataset.nurStemPointCount = String(controller.brainstemPointCount);
  brainHost.dataset.nurSparkleProfile = "three-stellar-shader-seven-spectrum";
  brainHost.dataset.nurGalaxyPaint = "three-coordinated-celestial-rig-v1";
  brainHost.dataset.nurAnatomy = "cortex-cerebellum-brainstem";
  brainHost.dataset.nurOpacityProfile = "crisp-dimensional-v2";
  brainHost.dataset.nurRenderProfile = "one-raf-two-canonical-canvases-v1";
  brainHost.dataset.nurInteractionProfile = "independent-3d-drag-inertia-v1";
  brainHost.dataset.nurSpectrumBands = V197_SPECTRUM_NAMES.join(",");
  brainHost.dataset.nurSpectrumBandCount = String(V197_SPECTRUM_NAMES.length);
  brainHost.dataset.nurEngine = V197_CELESTIAL_ENGINE;
  galaxyCanvas.dataset.nurGalaxyRig = "three-v197-seven-spectrum-3d";
  galaxyCanvas.dataset.nurGalaxyLayers = "far-dust-galaxy-super";
  galaxyCanvas.dataset.nurSpectrumBands = V197_SPECTRUM_NAMES.join(",");
  galaxyCanvas.dataset.nurSpectrumBandCount = String(V197_SPECTRUM_NAMES.length);
  galaxyCanvas.dataset.nurEngine = V197_CELESTIAL_ENGINE;
  galaxyCanvas.dataset.nurInteractionProfile = "spatial-drag-inertia-parallax-v1";

  installInteractions(controller);
  controller.teardown.push(bind(frameWindow, "resize", () => {
    controller.width = 0;
    syncStageAnimation(controller);
  }, { passive: true }));
  const onVisibilityChange = () => {
    syncStageAnimation(controller);
  };
  document.addEventListener("visibilitychange", onVisibilityChange, { passive: true });
  controller.teardown.push(() => document.removeEventListener("visibilitychange", onVisibilityChange));
  const ResizeObserverCtor = document.defaultView?.ResizeObserver ?? ResizeObserver;
  const resizeObserver = new ResizeObserverCtor(() => {
    controller.brainWidth = 0;
    syncStageAnimation(controller);
  });
  resizeObserver.observe(brainHost);
  controller.teardown.push(() => resizeObserver.disconnect());
  const stage = frameWindow.frameElement;
  if (stage) {
    const MutationObserverCtor = stage.ownerDocument.defaultView?.MutationObserver ?? MutationObserver;
    const stageObserver = new MutationObserverCtor(() => {
      syncStageAnimation(controller);
    });
    stageObserver.observe(stage, { attributes: true, attributeFilter: ["class", "aria-hidden"] });
    controller.teardown.push(() => stageObserver.disconnect());
  }
  const wakeTimer = frameWindow.setInterval(() => {
    controller.stageVisibilityCheckedAt = 0;
    if (
      stageIsVisible(controller, true)
      && controller.raf === null
      && (!controller.reducedMotion || !controller.staticFramePainted)
    ) requestFrame(controller);
  }, 750);
  controller.teardown.push(() => frameWindow.clearInterval(wakeTimer));

  updateSizes(controller);
  syncStageAnimation(controller);
  return controller;
}

export function ensureV197CelestialRuntime(
  document: Document,
  brainHost: HTMLElement,
): HTMLCanvasElement | null {
  const frameWindow = document.defaultView as CelestialWindow | null;
  if (!frameWindow) return null;
  const existing = controllers.get(document);
  if (existing && !existing.disposed) {
    existing.brainHost = brainHost;
    if (existing.brainCanvas.parentElement !== brainHost) brainHost.append(existing.brainCanvas);
    existing.staticFramePainted = false;
    requestFrame(existing);
    return existing.brainCanvas;
  }
  return createController(document, frameWindow, brainHost)?.brainCanvas ?? null;
}

export function disposeV197CelestialRuntime(document: Document): boolean {
  const controller = controllers.get(document);
  if (!controller) return false;
  disposeController(controller);
  return true;
}

export function getV197CelestialSpectrum(): readonly THREE.Color[] {
  return V197_SPECTRUM;
}

export function getV197CelestialAccent(): { gold: THREE.Color; ivory: THREE.Color } {
  return { gold: GOLD, ivory: IVORY };
}
