/**
 * Device capability measurement for the NUR cinematic visual runtime.
 *
 * The tier is chosen from what the device reports and then corrected by what it
 * actually delivers. A phone that claims eight cores but drops to 30 FPS must
 * end up on the same tier as an honestly slow device, so `QualityGovernor`
 * downgrades from measured frame cost while the scene runs.
 */

import { matchesMedia } from "./MotionController";

export type QualityTierName = "low" | "medium" | "high";

export interface QualityTier {
  name: QualityTierName;
  /** Multiplier applied to every scene's particle budget. */
  particleScale: number;
  /** Upper bound on the canvas backing-store scale factor. */
  maxPixelRatio: number;
  /** Whether additive glow sprites are drawn behind nodes. */
  glow: boolean;
  /** Whether relationship arcs animate their trace offset. */
  animatedArcs: boolean;
  /** Target frame budget in milliseconds. */
  frameBudgetMs: number;
}

const TIERS: Record<QualityTierName, QualityTier> = {
  low: { name: "low", particleScale: 0.38, maxPixelRatio: 1, glow: false, animatedArcs: false, frameBudgetMs: 22 },
  medium: { name: "medium", particleScale: 0.68, maxPixelRatio: 1.25, glow: true, animatedArcs: true, frameBudgetMs: 18 },
  high: { name: "high", particleScale: 1, maxPixelRatio: 1.5, glow: true, animatedArcs: true, frameBudgetMs: 14 },
};

export function tierByName(name: QualityTierName): QualityTier {
  return TIERS[name];
}

/**
 * Initial tier from device signals only. Deliberately conservative: a wrong
 * guess upward costs the user a janky first impression, a wrong guess downward
 * costs a few particles that `QualityGovernor` restores within two seconds.
 */
export function detectQualityTier(view: Window): QualityTier {
  const nav = view.navigator as Navigator & { deviceMemory?: number };
  const cores = typeof nav.hardwareConcurrency === "number" ? nav.hardwareConcurrency : 4;
  const memory = typeof nav.deviceMemory === "number" ? nav.deviceMemory : 4;
  const coarse = matchesMedia(view, "(pointer: coarse)");
  const narrow = view.innerWidth < 820;

  if (coarse && narrow && (cores <= 4 || memory <= 3)) return TIERS.low;
  if (coarse || narrow || cores <= 4 || memory <= 4) return TIERS.medium;
  return TIERS.high;
}

/**
 * Corrects the tier from real frame cost.
 *
 * Downgrades quickly (three consecutive slow windows) because sustained jank is
 * the failure the founder can see; upgrades slowly (eight consecutive fast
 * windows) so the scene never oscillates between tiers in front of the user.
 */
export class QualityGovernor {
  private tier: QualityTier;
  private slowWindows = 0;
  private fastWindows = 0;
  private samples: number[] = [];
  private readonly onChange: (tier: QualityTier) => void;

  constructor(initial: QualityTier, onChange: (tier: QualityTier) => void) {
    this.tier = initial;
    this.onChange = onChange;
  }

  current(): QualityTier {
    return this.tier;
  }

  /** Feed one frame's duration in milliseconds. */
  sample(frameMs: number): void {
    this.samples.push(frameMs);
    if (this.samples.length < 45) return;

    const sorted = [...this.samples].sort((a, b) => a - b);
    const p75 = sorted[Math.floor(sorted.length * 0.75)] ?? 0;
    this.samples = [];

    if (p75 > this.tier.frameBudgetMs) {
      this.slowWindows += 1;
      this.fastWindows = 0;
    } else if (p75 < this.tier.frameBudgetMs * 0.55) {
      this.fastWindows += 1;
      this.slowWindows = 0;
    } else {
      this.slowWindows = 0;
      this.fastWindows = 0;
    }

    if (this.slowWindows >= 3) {
      this.slowWindows = 0;
      this.shift(-1);
    } else if (this.fastWindows >= 8) {
      this.fastWindows = 0;
      this.shift(1);
    }
  }

  private shift(direction: -1 | 1): void {
    const order: QualityTierName[] = ["low", "medium", "high"];
    const index = order.indexOf(this.tier.name);
    const next = order[index + direction];
    if (!next || next === this.tier.name) return;
    this.tier = TIERS[next];
    this.onChange(this.tier);
  }
}
