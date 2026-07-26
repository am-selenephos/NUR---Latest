/**
 * The NUR hero object — a star-brain point cloud.
 *
 * The anatomy is NUR's own and already founder-approved: a golden-spiral cortex
 * shell folded into gyri with a longitudinal fissure, a finely striated
 * cerebellum, and a curved tapered brainstem. That geometry is what makes the
 * object recognisable in silhouette, which a sphere or a metaball never is.
 *
 * The generation math is ported faithfully from `v43StarBrainRuntime.js` so the
 * form is preserved exactly. What changes is everything around it:
 *
 *   - points are composited from cached sprites instead of allocating two
 *     radial gradients per star per frame;
 *   - the cloud is depth-sorted and shaded with atmospheric perspective, so far
 *     points recede in size, brightness and saturation instead of every point
 *     being equally sharp;
 *   - points carry a System assignment, so focusing a System makes the region of
 *     the brain that belongs to it resolve while the rest recedes. Particles
 *     organise around a semantic structure rather than drifting at random.
 *
 * The assignment is spatial, not clinical: it is a deterministic partition of
 * the point cloud used to give focus a visible target. It does not claim any
 * correspondence between a NUR System and a brain region, and nothing here
 * measures or infers anything about the owner's brain.
 */

import type { SpriteAtlas } from "../materials/SpriteAtlas";

export interface NeuralPoint {
  x: number;
  y: number;
  z: number;
  group: "cortex" | "cereb" | "stem";
  radius: number;
  colour: string;
  twinkle: number;
  twinkleSpeed: number;
  /** Index of the System this point belongs to; -1 before assignment. */
  system: number;
  /** Elastic displacement from the anatomical rest position. */
  ox: number;
  oy: number;
  oz: number;
  vx: number;
  vy: number;
  vz: number;
}

export interface ProjectedPoint {
  x: number;
  y: number;
  depth: number;
  scale: number;
  point: NeuralPoint;
}

/** Spectral distribution copied from the approved V43 palette. */
const SPECTRA: Record<string, number[][]> = {
  O: [[140, 160, 255], [158, 178, 255], [118, 148, 255]],
  B: [[172, 192, 255], [192, 208, 255], [162, 185, 255]],
  A: [[250, 253, 255], [255, 255, 255], [244, 251, 255]],
  F: [[255, 252, 215], [252, 248, 200], [255, 250, 188]],
  G: [[255, 244, 164], [255, 238, 138], [255, 230, 118]],
  K: [[255, 210, 78], [255, 195, 62], [255, 178, 48]],
  M: [[255, 152, 98], [255, 130, 68], [255, 108, 56]],
};

const DISTRIBUTION: Array<{ type: string; weight: number }> = [
  { type: "M", weight: 0.3 }, { type: "K", weight: 0.2 }, { type: "G", weight: 0.16 },
  { type: "F", weight: 0.12 }, { type: "A", weight: 0.1 }, { type: "B", weight: 0.08 },
  { type: "O", weight: 0.04 },
];

const random = (low: number, high: number): number => low + Math.random() * (high - low);

/**
 * Cheap smooth value noise, continuous in space and time.
 *
 * Independent per-point sinusoids produce static: every point does its own
 * thing, so the eye reads noise. Sampling a field that varies smoothly with
 * position means neighbouring points share a value, and the luminance change
 * travels across the mass as a slow wave — which is what reads as breathing.
 * This is the standard Perlin/simplex idea reduced to something affordable on
 * the hot path for ~1,000 points per frame.
 */
function coherentNoise(x: number, y: number, z: number, t: number): number {
  const a = Math.sin(x * 1.7 + t * 0.9) * Math.cos(y * 1.3 - t * 0.7);
  const b = Math.sin(z * 2.1 - t * 0.6) * Math.cos(x * 0.9 + y * 1.1);
  const c = Math.sin((x + z) * 1.1 + t * 0.4);
  return (a + b + c) / 3;
}

function spectralColour(): string {
  let roll = Math.random();
  let cumulative = 0;
  for (const { type, weight } of DISTRIBUTION) {
    cumulative += weight;
    if (roll < cumulative) {
      const band = SPECTRA[type] ?? SPECTRA.G;
      const rgb = band?.[(Math.random() * band.length) | 0] ?? [255, 244, 164];
      return `rgb(${rgb[0]}, ${rgb[1]}, ${rgb[2]})`;
    }
  }
  roll = 0;
  return "rgb(255, 244, 164)";
}

export interface NeuralCloudOptions {
  /** Scales all three population counts; driven by the quality tier. */
  density: number;
  mobile: boolean;
}

export class NeuralCloud {
  readonly points: NeuralPoint[] = [];
  private projected: ProjectedPoint[] = [];

  constructor(options: NeuralCloudOptions) {
    const { density, mobile } = options;
    const cortexCount = Math.max(120, Math.round((mobile ? 529 : 794) * density));
    const cerebCount = Math.max(30, Math.round((mobile ? 110 : 161) * density));
    const stemCount = Math.max(20, Math.round((mobile ? 69 : 105) * density));

    this.buildCortex(cortexCount);
    this.buildCerebellum(cerebCount);
    this.buildStem(stemCount);
  }

  private push(x: number, y: number, z: number, group: NeuralPoint["group"]): void {
    this.points.push({
      x, y, z, group,
      radius: random(0.7, 2.1) * (group === "stem" ? 0.92 : 1),
      colour: spectralColour(),
      twinkle: random(0, Math.PI * 2),
      // Frequency is in radians per millisecond. The V43 original used
      // 0.010-0.032, which is 1.6-5.1 Hz — above the WCAG 2.3.1 limit of three
      // flashes per second once it is paired with a large luminance swing on a
      // black field. This range is 0.13-0.35 Hz: a breath, not a strobe.
      twinkleSpeed: random(0.0008, 0.0022),
      system: -1,
      ox: 0, oy: 0, oz: 0, vx: 0, vy: 0, vz: 0,
    });
  }

  /** Golden-spiral sphere deformed into a folded brain ellipsoid. */
  private buildCortex(count: number): void {
    for (let index = 0; index < count; index += 1) {
      const t = (index + 0.5) / count;
      const inclination = Math.acos(1 - 2 * t);
      const azimuth = Math.PI * (1 + Math.sqrt(5)) * index;
      let x = Math.sin(inclination) * Math.cos(azimuth);
      let y = Math.cos(inclination);
      let z = Math.sin(inclination) * Math.sin(azimuth);

      // Gyri: two interleaved wrinkle frequencies across the surface.
      let fold = 0.058 * Math.sin(azimuth * 7 + Math.sin(inclination * 4) * 1.8)
        + 0.036 * Math.sin(azimuth * 13 + inclination * 9);
      const nearFissure = Math.abs(x) < 0.12 && y > -0.15;
      if (nearFissure) fold = -0.05;

      const scale = 1 + fold;
      x *= scale; y *= scale; z *= scale;

      // Ellipsoid proportions.
      y *= 0.83; z *= 1.26;

      // Longitudinal fissure: push the hemispheres apart at the midline.
      if (Math.abs(x) < 0.11 && y > -0.12) {
        x = Math.sign(x || random(-1, 1)) * (0.11 + Math.abs(x) * 0.35);
      }
      // Frontal taper, flattened underside, temporal bulge.
      if (z > 0.55) x *= 1 - 0.16 * (z - 0.55);
      if (y < -0.42) y = -0.42 + (y + 0.42) * 0.45;
      if (y < -0.05 && Math.abs(x) > 0.52 && z > 0.1) y -= 0.07;

      this.push(x, y, z, "cortex");
    }
  }

  private buildCerebellum(count: number): void {
    for (let index = 0; index < count; index += 1) {
      const t = (index + 0.5) / count;
      const inclination = Math.acos(1 - 2 * t);
      const azimuth = Math.PI * (1 + Math.sqrt(5)) * index;
      const x = Math.sin(inclination) * Math.cos(azimuth);
      const y = Math.cos(inclination);
      const z = Math.sin(inclination) * Math.sin(azimuth);
      const stripe = 1 + 0.045 * Math.sin(inclination * 16);
      this.push(x * 0.55 * stripe, -0.55 + y * 0.3 * stripe, -0.8 + z * 0.42 * stripe, "cereb");
    }
  }

  private buildStem(count: number): void {
    const stemAngle = Math.PI * (3 - Math.sqrt(5));
    for (let index = 0; index < count; index += 1) {
      const t = (index + 0.5) / count;
      const angle = index * stemAngle;
      const pons = Math.exp(-(((t - 0.28) / 0.17) ** 2));
      const shell = Math.sqrt(((index % 7) + 0.65) / 7);
      const reach = (0.11 - 0.045 * t + 0.052 * pons) * shell;
      const centreX = 0.014 * Math.sin(t * Math.PI * 1.3);
      const centreY = -0.4 - t * 0.62;
      const centreZ = -0.38 + t * 0.22 - 0.045 * Math.sin(t * Math.PI);
      this.push(centreX + Math.cos(angle) * reach, centreY, centreZ + Math.sin(angle) * reach * 0.76, "stem");
    }
  }

  /**
   * Deterministically partitions the cloud into `count` regions by angle around
   * the vertical axis, so focusing a System lights a coherent contiguous area
   * rather than scattered points. Cerebellum and stem stay unassigned: they read
   * as shared structure beneath every System.
   */
  assignSystems(count: number): void {
    if (count <= 0) {
      for (const point of this.points) point.system = -1;
      return;
    }
    for (const point of this.points) {
      if (point.group !== "cortex") {
        point.system = -1;
        continue;
      }
      const angle = Math.atan2(point.z, point.x) + Math.PI;
      point.system = Math.min(count - 1, Math.floor((angle / (Math.PI * 2)) * count));
    }
  }

  /**
   * Projects, depth-sorts and draws the cloud.
   *
   * Atmospheric perspective is applied per point: distance reduces size and
   * opacity and pulls the colour toward the cool background, which is what makes
   * the mass read as volume rather than as a flat scatter.
   */
  render(
    context: CanvasRenderingContext2D,
    atlas: SpriteAtlas,
    options: {
      centreX: number;
      centreY: number;
      scale: number;
      yaw: number;
      pitch: number;
      now: number;
      reducedMotion: boolean;
      glow: boolean;
      focusSystem: number;
      focusAmount: number;
      focusColour: string;
      nucleation: number;
    },
  ): void {
    const { centreX, centreY, scale, yaw, pitch, now, reducedMotion, glow } = options;
    const cosYaw = Math.cos(yaw);
    const sinYaw = Math.sin(yaw);
    const cosPitch = Math.cos(pitch);
    const sinPitch = Math.sin(pitch);

    if (this.projected.length !== this.points.length) {
      this.projected = this.points.map(point => ({ x: 0, y: 0, depth: 0, scale: 1, point }));
    }

    for (let index = 0; index < this.points.length; index += 1) {
      const point = this.points[index];
      const slot = this.projected[index];
      if (!point || !slot) continue;

      const px = point.x + point.ox;
      const py = point.y + point.oy;
      const pz = point.z + point.oz;
      const x1 = px * cosYaw - pz * sinYaw;
      const z1 = px * sinYaw + pz * cosYaw;
      const y1 = py * cosPitch - z1 * sinPitch;
      const z2 = py * sinPitch + z1 * cosPitch;

      // Weak perspective: enough for depth, never enough to distort the form.
      const perspective = 1 / (1 + z2 * 0.32);
      slot.x = centreX + x1 * scale * perspective;
      slot.y = centreY + y1 * scale * perspective;
      slot.depth = z2;
      slot.scale = perspective;
    }

    // Painter's order: far points first so near points occlude them.
    this.projected.sort((a, b) => a.depth - b.depth);

    const emergence = options.nucleation;
    for (const slot of this.projected) {
      const point = slot.point;
      // depth 0 = far, 1 = near
      const depth = Math.max(0, Math.min(1, (slot.depth + 1.4) / 2.8));
      // Luminance comes from one coherent field sampled at the point's own
      // position, so light travels across the mass as a wave instead of every
      // point flickering independently. Total swing is held to +/-10%, far below
      // a WCAG general flash, and the field's own frequency is ~0.06 Hz.
      const wave = reducedMotion ? 0 : coherentNoise(point.x, point.y, point.z, now * 0.00035) * 0.08;
      const breath = reducedMotion ? 0 : Math.sin(now * 0.00035) * 0.03;
      const twinkle = 0.9 + wave + breath;

      // The hero must dominate its own composition. Depth still modulates both
      // values, but from a floor high enough that the silhouette reads at a
      // glance rather than dissolving into the surrounding field.
      let alpha = (0.42 + depth * 0.58) * twinkle * emergence;
      let radius = point.radius * slot.scale * (0.9 + depth * 0.75);
      let colour = point.colour;

      if (options.focusAmount > 0.01) {
        const belongs = point.system === options.focusSystem;
        if (belongs) {
          colour = options.focusColour;
          alpha *= 1 + options.focusAmount * 0.55;
          radius *= 1 + options.focusAmount * 0.35;
        } else {
          // Siblings recede — they never vanish, so the whole form stays legible.
          alpha *= 1 - options.focusAmount * 0.62;
        }
      }

      if (glow && depth > 0.34) {
        atlas.draw(context, "glow", colour, slot.x, slot.y, radius * 4.4, alpha * 0.3);
      }
      atlas.draw(context, "core", colour, slot.x, slot.y, radius, alpha);
    }
  }

  /**
   * Spring-damper integration of the elastic displacement.
   *
   * Every point is tethered to its anatomical rest position. Forces push it
   * away; the spring pulls it home. This is what makes the mass feel like matter
   * rather than a picture — it has weight, it overshoots slightly, it settles.
   */
  integrate(delta: number): void {
    const step = Math.min(2.2, delta / 16.7);
    const stiffness = 0.055 * step;
    const damping = Math.pow(0.90, step);
    for (const point of this.points) {
      point.vx = (point.vx - point.ox * stiffness) * damping;
      point.vy = (point.vy - point.oy * stiffness) * damping;
      point.vz = (point.vz - point.oz * stiffness) * damping;
      point.ox += point.vx * step;
      point.oy += point.vy * step;
      point.oz += point.vz * step;
    }
  }

  /**
   * Repels points away from a screen-space position with a soft falloff.
   * The cursor becomes a physical presence pushing through the mass.
   */
  repelFrom(screenX: number, screenY: number, radius: number, strength: number, scale: number): void {
    // Forces arrive in screen pixels; displacement lives in model units. Without
    // this conversion a 100px push becomes 100 model units and the cloud
    // detonates.
    const toModel = 1 / Math.max(1, scale);
    const radiusSquared = radius * radius;
    for (const slot of this.projected) {
      const dx = slot.x - screenX;
      const dy = slot.y - screenY;
      const distanceSquared = dx * dx + dy * dy;
      if (distanceSquared > radiusSquared || distanceSquared < 0.01) continue;
      const falloff = 1 - distanceSquared / radiusSquared;
      const distance = Math.sqrt(distanceSquared);
      const push = (falloff * falloff * strength * toModel) / distance;
      slot.point.vx += dx * push;
      slot.point.vy += dy * push;
      slot.point.vz += falloff * strength * toModel * 0.4;
    }
  }

  /** A radial impulse through the whole cloud — the click shockwave. */
  shockwave(screenX: number, screenY: number, strength: number, scale: number): void {
    const toModel = 1 / Math.max(1, scale);
    for (const slot of this.projected) {
      const dx = slot.x - screenX;
      const dy = slot.y - screenY;
      const distance = Math.max(12, Math.hypot(dx, dy));
      const impulse = (strength * toModel * 60) / distance;
      slot.point.vx += (dx / distance) * impulse;
      slot.point.vy += (dy / distance) * impulse;
      slot.point.vz += (Math.random() - 0.35) * impulse * 0.6;
    }
  }

  /** Screen position of a System's region centroid, for anchoring its node. */
  regionAnchor(system: number): { x: number; y: number } | null {
    let sumX = 0;
    let sumY = 0;
    let count = 0;
    for (const slot of this.projected) {
      if (slot.point.system !== system) continue;
      sumX += slot.x;
      sumY += slot.y;
      count += 1;
    }
    return count === 0 ? null : { x: sumX / count, y: sumY / count };
  }

  dispose(): void {
    this.points.length = 0;
    this.projected = [];
  }
}
