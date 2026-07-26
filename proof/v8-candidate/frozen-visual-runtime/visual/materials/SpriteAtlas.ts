/**
 * Pre-rendered emissive sprites for the NUR visual runtime.
 *
 * The existing V43 star engine calls `createRadialGradient` twice per star per
 * frame. At ~1,400 nodes and 60 FPS that is roughly 168,000 gradient objects a
 * second, which is the dominant source of allocation jitter in the current
 * interface. Every glow here is rasterised once into an offscreen canvas and
 * afterwards composited with `drawImage`, so the per-frame cost becomes a blit
 * with no allocation.
 *
 * Sprites are cached by colour and radius bucket. Bucketing to 8 radii keeps the
 * atlas small while remaining visually continuous, because the blit is scaled.
 */

export interface SpriteAtlasOptions {
  /** Backing-store scale so sprites stay crisp on HiDPI displays. */
  pixelRatio: number;
}

type SpriteKind = "glow" | "core" | "spark";

const RADII = [4, 8, 14, 22, 34, 52, 78, 116] as const;

function bucket(radius: number): number {
  for (const candidate of RADII) {
    if (radius <= candidate) return candidate;
  }
  return RADII[RADII.length - 1];
}

function createSurface(size: number): HTMLCanvasElement {
  const surface = document.createElement("canvas");
  surface.width = size;
  surface.height = size;
  return surface;
}

export class SpriteAtlas {
  private readonly cache = new Map<string, HTMLCanvasElement>();
  private readonly pixelRatio: number;

  constructor(options: SpriteAtlasOptions) {
    this.pixelRatio = Math.max(1, options.pixelRatio);
  }

  /** Number of distinct rasterised sprites; asserted by tests as a leak guard. */
  size(): number {
    return this.cache.size;
  }

  clear(): void {
    this.cache.clear();
  }

  /**
   * Returns a sprite whose natural radius is the bucketed radius. Callers draw
   * it centred and scaled to the exact radius they need.
   */
  sprite(kind: SpriteKind, colour: string, radius: number): HTMLCanvasElement {
    const bucketed = bucket(radius);
    const key = `${kind}:${colour}:${bucketed}`;
    const cached = this.cache.get(key);
    if (cached) return cached;

    const size = Math.ceil(bucketed * 2 * this.pixelRatio);
    const surface = createSurface(size);
    const context = surface.getContext("2d");
    if (!context) return surface;

    const centre = size / 2;
    const outer = size / 2;

    if (kind === "glow") {
      const gradient = context.createRadialGradient(centre, centre, 0, centre, centre, outer);
      gradient.addColorStop(0, withAlpha(colour, 0.55));
      gradient.addColorStop(0.28, withAlpha(colour, 0.22));
      gradient.addColorStop(0.62, withAlpha(colour, 0.06));
      gradient.addColorStop(1, withAlpha(colour, 0));
      context.fillStyle = gradient;
      context.fillRect(0, 0, size, size);
    } else if (kind === "core") {
      const gradient = context.createRadialGradient(centre, centre, 0, centre, centre, outer);
      gradient.addColorStop(0, withAlpha("#ffffff", 0.96));
      gradient.addColorStop(0.35, withAlpha(colour, 0.9));
      gradient.addColorStop(1, withAlpha(colour, 0));
      context.fillStyle = gradient;
      context.beginPath();
      context.arc(centre, centre, outer, 0, Math.PI * 2);
      context.fill();
    } else {
      // Four-point stellar spike, drawn once. Used sparsely at focal points only.
      context.fillStyle = withAlpha(colour, 0.85);
      context.beginPath();
      const inner = outer * 0.09;
      for (let index = 0; index < 8; index += 1) {
        const angle = (Math.PI / 4) * index - Math.PI / 2;
        const reach = index % 2 === 0 ? outer : inner;
        const x = centre + Math.cos(angle) * reach;
        const y = centre + Math.sin(angle) * reach;
        if (index === 0) context.moveTo(x, y);
        else context.lineTo(x, y);
      }
      context.closePath();
      context.fill();
    }

    this.cache.set(key, surface);
    return surface;
  }

  /** Draw a cached sprite centred on (x, y) at an exact radius. */
  draw(
    target: CanvasRenderingContext2D,
    kind: SpriteKind,
    colour: string,
    x: number,
    y: number,
    radius: number,
    alpha: number,
  ): void {
    if (alpha <= 0.004 || radius <= 0.2) return;
    const sprite = this.sprite(kind, colour, radius);
    const previous = target.globalAlpha;
    target.globalAlpha = previous * Math.min(1, alpha);
    target.drawImage(sprite, x - radius, y - radius, radius * 2, radius * 2);
    target.globalAlpha = previous;
  }
}

/** Accepts `#rgb`, `#rrggbb` and `rgb()`; returns an `rgba()` string. */
export function withAlpha(colour: string, alpha: number): string {
  const value = colour.trim();
  if (value.startsWith("#")) {
    const hex = value.slice(1);
    const full = hex.length === 3 ? hex.split("").map(character => character + character).join("") : hex;
    const red = Number.parseInt(full.slice(0, 2), 16);
    const green = Number.parseInt(full.slice(2, 4), 16);
    const blue = Number.parseInt(full.slice(4, 6), 16);
    return `rgba(${red}, ${green}, ${blue}, ${alpha})`;
  }
  const numbers = value.match(/[\d.]+/g);
  if (numbers && numbers.length >= 3) {
    return `rgba(${numbers[0]}, ${numbers[1]}, ${numbers[2]}, ${alpha})`;
  }
  return value;
}
