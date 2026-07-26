/**
 * Three-plane particle field providing real spatial depth behind and in front of
 * the hero object.
 *
 * A single scatter of equal points reads as a flat texture no matter how many
 * points it contains — that was the failure in the first Slice 1 attempt. Depth
 * comes from separating the field into planes that differ in **four** correlated
 * ways at once: parallax rate, size, brightness and colour temperature. The far
 * plane is small, dim and cool; the near plane is larger, brighter and drifts
 * noticeably faster under pointer movement.
 *
 * The near plane draws *after* the hero object so it passes in front of it,
 * which is what sells the brain as sitting inside a volume rather than on top of
 * a backdrop.
 */

import type { SpriteAtlas } from "../materials/SpriteAtlas";

export type FieldPlane = "far" | "mid" | "near";

interface FieldParticle {
  /** Normalised position; -0.5..0.5 across the stage. */
  x: number;
  y: number;
  size: number;
  phase: number;
  speed: number;
  colour: string;
  drift: number;
}

interface PlaneConfig {
  count: number;
  parallax: number;
  sizeLow: number;
  sizeHigh: number;
  alpha: number;
  palette: string[];
}

/** Cool and desaturated with distance; warmer and brighter up close. */
const PLANES: Record<FieldPlane, PlaneConfig> = {
  far: {
    count: 260,
    parallax: 0.18,
    sizeLow: 0.35,
    sizeHigh: 0.8,
    alpha: 0.3,
    palette: ["#5f7ba8", "#6f8fc0", "#7d9ec9", "#8fa8cc"],
  },
  mid: {
    count: 150,
    parallax: 0.52,
    sizeLow: 0.7,
    sizeHigh: 1.5,
    alpha: 0.55,
    palette: ["#c4defc", "#8fc5ff", "#e4ecf8", "#b8cdf0"],
  },
  near: {
    count: 42,
    parallax: 1.25,
    sizeLow: 1.4,
    sizeHigh: 3.1,
    alpha: 0.72,
    palette: ["#fff4d8", "#ffd9a0", "#ffffff", "#f4f6fc"],
  },
};

export class DepthField {
  private readonly particles: FieldParticle[] = [];
  private readonly config: PlaneConfig;
  readonly plane: FieldPlane;

  constructor(plane: FieldPlane, density: number) {
    this.plane = plane;
    this.config = PLANES[plane];
    const count = Math.max(8, Math.round(this.config.count * density));
    for (let index = 0; index < count; index += 1) {
      // The hero object owns the centre. Fields are pushed outside its silhouette
      // so they frame the brain instead of dissolving it — a field that overlaps
      // the subject reads as noise and destroys the very depth it is meant to
      // create.
      const angle = Math.random() * Math.PI * 2;
      const spread = 0.46 + Math.random() ** 0.7 * 0.44;
      this.particles.push({
        x: Math.cos(angle) * spread,
        y: Math.sin(angle) * spread * 0.7,
        size: this.config.sizeLow + Math.random() * (this.config.sizeHigh - this.config.sizeLow),
        phase: Math.random() * Math.PI * 2,
        speed: 0.0004 + Math.random() * 0.0011,
        colour: this.config.palette[(Math.random() * this.config.palette.length) | 0] ?? "#ffffff",
        drift: (Math.random() - 0.5) * 0.00004,
      });
    }
  }

  render(
    context: CanvasRenderingContext2D,
    atlas: SpriteAtlas,
    options: {
      width: number;
      height: number;
      now: number;
      delta: number;
      pointerX: number;
      pointerY: number;
      reducedMotion: boolean;
      dim: number;
      nucleation: number;
      glow: boolean;
    },
  ): void {
    const { width, height, now, pointerX, pointerY, reducedMotion, dim, nucleation } = options;
    const centreX = width / 2;
    const centreY = height / 2;
    const extent = Math.min(width, height);
    // Parallax offset is in pixels and scales with the plane's distance.
    const offsetX = -pointerX * 26 * this.config.parallax;
    const offsetY = -pointerY * 20 * this.config.parallax;

    for (const particle of this.particles) {
      if (!reducedMotion) particle.x += particle.drift * options.delta;
      if (particle.x > 0.85) particle.x = -0.85;
      if (particle.x < -0.85) particle.x = 0.85;

      const x = centreX + particle.x * extent + offsetX;
      const y = centreY + particle.y * extent + offsetY;
      // Was 0.55 +/- 0.45 — an 82% swing. Slow enough not to breach the flash
      // threshold, but deep enough to read as unease rather than depth.
      const twinkle = reducedMotion ? 0.86 : 0.86 + Math.sin(now * particle.speed + particle.phase) * 0.12;
      const alpha = this.config.alpha * twinkle * dim * nucleation;

      if (options.glow && this.plane === "near") {
        atlas.draw(context, "glow", particle.colour, x, y, particle.size * 6, alpha * 0.3);
      }
      atlas.draw(context, "core", particle.colour, x, y, particle.size, alpha);
    }
  }

  dispose(): void {
    this.particles.length = 0;
  }
}
