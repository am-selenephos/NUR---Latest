/**
 * Named motion primitives for the NUR cinematic visual system.
 *
 * Every animated transition in a scene must be expressed as one of these, so
 * timing stays coherent across routes instead of each surface inventing its own
 * easing. Reduced motion is handled here once rather than at every call site:
 * `duration` collapses to a near-instant state change and camera travel is
 * removed, but the state change itself still happens.
 */

export type MotionPrimitive =
  | "NUCLEATE"
  | "ORBIT"
  | "BREATHE"
  | "COHERE"
  | "DISPERSE"
  | "TRACE"
  | "REVEAL"
  | "FOCUS"
  | "ENTER_SYSTEM"
  | "RETURN_TO_CORE";

export interface MotionSpec {
  /** Milliseconds at full motion. */
  durationMs: number;
  /** Cubic-bezier control points. */
  easing: readonly [number, number, number, number];
  /** Whether the primitive moves the camera; removed under reduced motion. */
  camera: boolean;
  /** Semantic use — documented so a primitive is not reused decoratively. */
  meaning: string;
}

export const MOTION: Record<MotionPrimitive, MotionSpec> = {
  NUCLEATE: {
    durationMs: 820,
    easing: [0.16, 1, 0.3, 1],
    camera: false,
    meaning: "A scene's matter gathers from dispersed particles into its first coherent form.",
  },
  ORBIT: {
    durationMs: 0,
    easing: [0, 0, 1, 1],
    camera: false,
    meaning: "Continuous ambient revolution. Never a transition — it is the resting state.",
  },
  BREATHE: {
    durationMs: 5200,
    easing: [0.37, 0, 0.63, 1],
    camera: false,
    meaning: "Slow scale and luminance oscillation signalling the interface is live, not frozen.",
  },
  COHERE: {
    durationMs: 640,
    easing: [0.22, 1, 0.36, 1],
    camera: false,
    meaning: "Scattered elements resolve into structure when data arrives.",
  },
  DISPERSE: {
    durationMs: 480,
    easing: [0.5, 0, 0.75, 0],
    camera: false,
    meaning: "Structure releases back into particles when its data leaves scope.",
  },
  TRACE: {
    durationMs: 900,
    easing: [0.65, 0, 0.35, 1],
    camera: false,
    meaning: "A relationship line draws along its path to assert a connection between two nodes.",
  },
  REVEAL: {
    durationMs: 520,
    easing: [0.16, 1, 0.3, 1],
    camera: false,
    meaning: "Typography and data layers arrive after the spatial layer has settled.",
  },
  FOCUS: {
    durationMs: 560,
    easing: [0.22, 1, 0.36, 1],
    camera: true,
    meaning: "One node becomes the subject; siblings recede without disappearing.",
  },
  ENTER_SYSTEM: {
    durationMs: 880,
    easing: [0.16, 1, 0.3, 1],
    camera: true,
    meaning: "The world transforms into another system rather than being replaced by one.",
  },
  RETURN_TO_CORE: {
    durationMs: 700,
    easing: [0.22, 1, 0.36, 1],
    camera: true,
    meaning: "The inverse of ENTER_SYSTEM, returning the viewer to the living core.",
  },
};

function bezier([, y1, , y2]: readonly [number, number, number, number], t: number): number {
  // Cheap approximation adequate for canvas easing; avoids a solver on the hot path.
  const inv = 1 - t;
  return 3 * inv * inv * t * y1 + 3 * inv * t * t * y2 + t * t * t;
}

export interface MotionRun {
  /** 0..1 eased progress. */
  value: number;
  done: boolean;
}

/**
 * A single running motion. Scenes hold these rather than tracking raw timestamps,
 * which keeps reduced-motion handling in one place.
 */
export class Motion {
  private startedAt = 0;
  private readonly spec: MotionSpec;
  private readonly durationMs: number;
  private running = false;

  constructor(primitive: MotionPrimitive, reducedMotion: boolean) {
    this.spec = MOTION[primitive];
    this.durationMs = reducedMotion ? Math.min(this.spec.durationMs, 90) : this.spec.durationMs;
  }

  start(now: number): void {
    this.startedAt = now;
    this.running = true;
  }

  isRunning(): boolean {
    return this.running;
  }

  sample(now: number): MotionRun {
    if (!this.running) return { value: 1, done: true };
    if (this.durationMs <= 0) return { value: 1, done: true };
    // Clamped at both ends. A rAF timestamp can be marginally earlier than the
    // performance.now() captured when the motion started, and an unclamped
    // negative progress propagates into negative radii — which throws out of
    // canvas arc() and silently kills the frame loop.
    const raw = Math.max(0, Math.min(1, (now - this.startedAt) / this.durationMs));
    const value = bezier(this.spec.easing, raw);
    if (raw >= 1) this.running = false;
    return { value, done: raw >= 1 };
  }
}

/**
 * Defensive: the scene runs inside the canonical V197 iframe, whose defaultView
 * is not guaranteed to expose `matchMedia`. A missing media API must degrade to
 * full motion, never take the bridge down with it.
 */
export function prefersReducedMotion(view: Window): boolean {
  return matchesMedia(view, "(prefers-reduced-motion: reduce)");
}

export function matchesMedia(view: Window, query: string): boolean {
  if (typeof view.matchMedia !== "function") return false;
  try {
    return view.matchMedia(query).matches;
  } catch {
    return false;
  }
}
