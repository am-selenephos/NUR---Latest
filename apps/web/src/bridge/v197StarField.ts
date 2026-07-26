/**
 * Deep-field stars behind the galaxy rig, on Entry and on the Universe.
 *
 * The canonical `#space3d` rig owns its own painting and cannot be edited, so
 * this adds a separate layer directly behind it.
 *
 * The field is painted **once** and then never touched again. It has no frame
 * loop at all.
 *
 * The first attempt animated a twinkling subset over a cached buffer at 24 fps.
 * Measured cost: Entry 66.7 -> 83.3 ms and Systems ~66 -> 133.4 ms per frame,
 * because each paint blits a full-viewport 2400x1350 buffer — 3.2 million pixels
 * — and clears the same area first. Behind a rig that is already animating, that
 * twinkle bought nothing a viewer could notice.
 *
 * Depth motion comes from three independently drifting layers — far, mid and
 * near — each a separate bitmap moving at a different speed and scale. Parallax
 * between them is what reads as volume rather than a flat sky. The motion is a
 * CSS transform animation, so the compositor moves the layers on the GPU and the
 * main thread does nothing at all per frame.
 *
 * It is also not a canvas at runtime. Measured on Entry, an extra full-viewport
 * `<canvas>` layer cost about eleven points of CPU in compositing alone even
 * though it never redrew (66.2% baseline -> 69.4% with the denser brain ->
 * 80.5% once the canvas layer was added). The field is therefore rasterised
 * once into an off-document canvas, exported as a data URI, and applied as a
 * plain CSS background on a div. The canvas is discarded immediately. A static
 * bitmap is the cheapest layer a compositor can carry.
 */

const FIELD_CANVAS_ID = "nur-deep-starfield";

interface FieldStar {
  x: number;
  y: number;
  radius: number;
  colour: string;
  alpha: number;
}

interface FieldController {
  layer: HTMLElement;
}

const controllers = new WeakMap<Document, FieldController>();

/** Distant planes stay cool and desaturated; the near plane carries the warmth. */
const COOL_PALETTE = [
  "rgb(150,178,220)", "rgb(178,200,238)", "rgb(206,222,248)",
  "rgb(196,214,244)", "rgb(168,190,228)", "rgb(222,234,252)",
];
const WARM_PALETTE = [
  "rgb(255,246,222)", "rgb(255,226,186)", "rgb(255,238,206)",
  "rgb(238,244,255)", "rgb(255,214,158)",
];

function seeded(seed: number): () => number {
  // Deterministic so a resize regenerates the same sky rather than reshuffling
  // the stars under the user.
  let state = seed >>> 0;
  return () => {
    state = (state * 1664525 + 1013904223) >>> 0;
    return state / 4294967296;
  };
}

function buildStars(
  width: number,
  height: number,
  count: number,
  planeIndex: number,
  plane: PlaneSpec,
): FieldStar[] {
  // Seeded per plane so each layer is its own sky, and so a resize regenerates
  // the same stars rather than reshuffling them under the viewer.
  const random = seeded(0x9e3779b9 + planeIndex * 0x85ebca6b);
  const field: FieldStar[] = [];
  const palette = plane.warm ? WARM_PALETTE : COOL_PALETTE;

  for (let index = 0; index < count; index += 1) {
    // Power bias: overwhelmingly small stars, a handful with presence.
    const size = (0.28 + random() ** 3.1 * 1.55) * plane.scale;
    field.push({
      x: random() * width,
      y: random() * height,
      radius: size,
      colour: palette[(random() * palette.length) | 0] ?? "rgb(206,222,248)",
      alpha: (0.16 + random() ** 1.7 * 0.5) * plane.alpha,
    });
  }
  return field;
}

interface PlaneSpec {
  /** Fraction of the total star budget this plane carries. */
  share: number;
  /** Size multiplier: distant stars are smaller. */
  scale: number;
  /** Opacity multiplier: distant stars are dimmer. */
  alpha: number;
  /** Seconds for one full drift cycle. Slower reads as further away. */
  driftSeconds: number;
  /** Pixels of travel across that cycle. */
  driftPx: number;
  /** Cool for far, warm for near. */
  warm: boolean;
  /** Scale at the near and far ends of the depth cycle. */
  depthNear: number;
  depthFar: number;
  /** Sparkle period in seconds, and the offset copy's period. */
  sparkSeconds: number;
  sparkOffset: number;
  sparkLow: number;
  sparkHigh: number;
}

/**
 * Three planes at correlated differences in size, brightness and drift rate.
 * Changing only one of those reads as a bug; changing all three reads as depth.
 */
const PLANES: PlaneSpec[] = [
  {
    share: 0.56, scale: 0.72, alpha: 0.60, driftSeconds: 260, driftPx: 26, warm: false,
    depthNear: 1.04, depthFar: 1.10, sparkSeconds: 88, sparkOffset: 61, sparkLow: 0.72, sparkHigh: 1,
  },
  {
    share: 0.32, scale: 1.00, alpha: 0.85, driftSeconds: 170, driftPx: 52, warm: false,
    depthNear: 1.05, depthFar: 1.16, sparkSeconds: 64, sparkOffset: 47, sparkLow: 0.62, sparkHigh: 1,
  },
  {
    share: 0.12, scale: 1.45, alpha: 1.00, driftSeconds: 110, driftPx: 88, warm: true,
    depthNear: 1.06, depthFar: 1.26, sparkSeconds: 48, sparkOffset: 33, sparkLow: 0.5, sparkHigh: 1,
  },
];

const KEYFRAMES_ID = "nur-deep-starfield-motion";

function ensureFieldKeyframes(document: Document): void {
  if (document.getElementById(KEYFRAMES_ID)) return;
  const style = document.createElement("style");
  style.id = KEYFRAMES_ID;
  // Transform-only animation: the compositor can run this without ever waking
  // the main thread, which is why the field can move and still cost nothing.
  style.textContent = `
/* Depth travel: each plane drifts AND breathes toward the viewer on its own
   cycle. Pairing translation with a scale change is what reads as moving
   through a volume rather than sliding a flat picture. */
@keyframes nurFieldDrift {
  0%   { transform: translate3d(0, 0, 0) scale(var(--nur-depth-near)); }
  50%  { transform: translate3d(var(--nur-drift-x), var(--nur-drift-y), 0) scale(var(--nur-depth-far)); }
  100% { transform: translate3d(0, 0, 0) scale(var(--nur-depth-near)); }
}

/* Sparkle: opacity pulse on its own, deliberately unrelated period, so the
   planes never blink in step. Held well inside the WCAG flash threshold — the
   slowest is 0.011 Hz and the fastest 0.021 Hz, against a limit of 3. */
@keyframes nurFieldSparkle {
  0%, 100% { opacity: var(--nur-spark-low); }
  50%      { opacity: var(--nur-spark-high); }
}
#${FIELD_CANVAS_ID} > i {
  position: absolute;
  inset: -8%;
  display: block;
  background-repeat: repeat;
  will-change: transform, opacity;
  animation:
    nurFieldDrift var(--nur-drift-seconds) ease-in-out infinite,
    nurFieldSparkle var(--nur-spark-seconds) ease-in-out infinite;
}

/* A second, offset copy of each plane at a different sparkle phase. Two layers
   twinkling out of step is what makes individual stars appear to catch light,
   and it costs one more composited bitmap rather than any per-frame work. */
#${FIELD_CANVAS_ID} > i::after {
  content: "";
  position: absolute;
  inset: 0;
  background: inherit;
  animation: nurFieldSparkle var(--nur-spark-offset) ease-in-out infinite reverse;
}
@media (prefers-reduced-motion: reduce) {
  #${FIELD_CANVAS_ID} > i,
  #${FIELD_CANVAS_ID} > i::after { animation: none; opacity: var(--nur-spark-high); }
}`;
  (document.head ?? document.body).append(style);
}

function paintStar(
  context: CanvasRenderingContext2D,
  star: FieldStar,
  alpha: number,
): void {
  if (alpha <= 0.01) return;
  context.globalAlpha = alpha;
  context.fillStyle = star.colour;
  context.beginPath();
  context.arc(star.x, star.y, star.radius, 0, 6.2832);
  context.fill();

  // A faint cross only on the few stars large enough to earn one.
  if (star.radius > 1.25) {
    const reach = star.radius * 3.4;
    context.globalAlpha = alpha * 0.3;
    context.strokeStyle = star.colour;
    context.lineWidth = 0.5;
    context.beginPath();
    context.moveTo(star.x - reach, star.y);
    context.lineTo(star.x + reach, star.y);
    context.moveTo(star.x, star.y - reach * 0.8);
    context.lineTo(star.x, star.y + reach * 0.8);
    context.stroke();
  }
  context.globalAlpha = 1;
}

/**
 * Mounts the deep field into a document, behind the canonical rig.
 * Safe to call repeatedly: an existing field is reused rather than duplicated.
 */
export function ensureV197StarField(document: Document): HTMLElement | null {
  const view = document.defaultView;
  const body = document.body;
  if (!view || !body) return null;
  if (controllers.has(document)) {
    return document.getElementById(FIELD_CANVAS_ID);
  }

  const rig = document.getElementById("space3d") as HTMLCanvasElement | null;
  if (!rig) return null;

  document.querySelectorAll(`#${FIELD_CANVAS_ID}`).forEach(node => node.remove());

  const layer = document.createElement("div");
  layer.id = FIELD_CANVAS_ID;
  layer.setAttribute("aria-hidden", "true");
  const rigZ = Number.parseInt(view.getComputedStyle(rig).zIndex || "0", 10);
  layer.style.cssText = [
    "position:fixed",
    "inset:0",
    "pointer-events:none",
    "overflow:hidden",
    // Directly behind the canonical rig so the rig's own stars stay dominant.
    `z-index:${Number.isFinite(rigZ) ? rigZ - 1 : -1}`,
  ].join(";");
  rig.parentElement?.insertBefore(layer, rig);

  ensureFieldKeyframes(document);

  let lastKey = "";

  const paint = (): void => {
    const width = Math.max(2, view.innerWidth);
    const height = Math.max(2, view.innerHeight);
    const key = `${width}x${height}`;
    if (key === lastKey) return;
    lastKey = key;

    layer.textContent = "";

    // Total budget scales with area so a large monitor is not sparse and a phone
    // is not overloaded; each plane takes its share.
    const budget = Math.round(Math.min(1600, Math.max(300, (width * height) / 1900)));
    // Rendered at 0.75x and stretched. The stars are soft points, so the
    // resampling is invisible while each texture carries 44% fewer pixels.
    const scale = 0.75;

    PLANES.forEach((plane, index) => {
      const buffer = document.createElement("canvas");
      buffer.width = Math.round(width * scale);
      buffer.height = Math.round(height * scale);
      const context = buffer.getContext("2d", { alpha: true });
      if (!context) return;
      context.setTransform(scale, 0, 0, scale, 0, 0);

      const stars = buildStars(width, height, Math.round(budget * plane.share), index, plane);
      for (const star of stars) paintStar(context, star, star.alpha);

      const plate = document.createElement("i");
      plate.style.backgroundImage = `url(${buffer.toDataURL("image/png")})`;
      plate.style.backgroundSize = `${width}px ${height}px`;
      plate.style.setProperty("--nur-drift-seconds", `${plane.driftSeconds}s`);
      // Opposing directions between planes make the parallax legible.
      const direction = index % 2 === 0 ? 1 : -1;
      plate.style.setProperty("--nur-drift-x", `${plane.driftPx * direction}px`);
      plate.style.setProperty("--nur-drift-y", `${plane.driftPx * 0.42 * direction}px`);
      plate.style.setProperty("--nur-depth-near", String(plane.depthNear));
      plate.style.setProperty("--nur-depth-far", String(plane.depthFar));
      plate.style.setProperty("--nur-spark-seconds", `${plane.sparkSeconds}s`);
      plate.style.setProperty("--nur-spark-offset", `${plane.sparkOffset}s`);
      plate.style.setProperty("--nur-spark-low", String(plane.sparkLow));
      plate.style.setProperty("--nur-spark-high", String(plane.sparkHigh));
      layer.append(plate);
      // Only the bitmap survives; the canvas is discarded with this scope.
    });
  };

  let resizeQueued = false;
  const onResize = (): void => {
    if (resizeQueued) return;
    resizeQueued = true;
    view.requestAnimationFrame(() => {
      resizeQueued = false;
      paint();
    });
  };

  paint();
  view.addEventListener("resize", onResize, { passive: true });


  controllers.set(document, { layer });
  return layer;
}
