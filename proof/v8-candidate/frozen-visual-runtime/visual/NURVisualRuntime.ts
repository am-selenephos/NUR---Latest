/**
 * The single canvas owner and single requestAnimationFrame owner for the NUR
 * cinematic visual system.
 *
 * The current interface fails both of those invariants: the shipped V43 runtime
 * never calls `cancelAnimationFrame`, and the V199 prototype leaves three
 * superseded engines looping with their draw calls replaced by no-ops. This
 * runtime exists so that cannot recur — a scene is mounted, becomes the sole
 * consumer of one loop and one canvas, and is torn down deterministically.
 *
 * Invariants enforced here, and asserted by tests:
 *   1. At most one canvas element bearing CANVAS_ID exists per document.
 *   2. At most one rAF handle is outstanding.
 *   3. Every listener registered through `bindListener` is removed on destroy.
 *   4. The loop pauses when the page is hidden and resumes on visibility.
 */

import { QualityGovernor, detectQualityTier, type QualityTier } from "./QualityTier";
import { prefersReducedMotion } from "./MotionController";
import { SpriteAtlas } from "./materials/SpriteAtlas";

export const CANVAS_ID = "nur-visual-runtime-canvas";

export interface FrameContext {
  context: CanvasRenderingContext2D;
  atlas: SpriteAtlas;
  /** CSS pixels. */
  width: number;
  height: number;
  /** High-resolution timestamp. */
  now: number;
  /** Milliseconds since the previous frame, clamped to avoid post-tab-switch jumps. */
  delta: number;
  tier: QualityTier;
  reducedMotion: boolean;
  pointer: { x: number; y: number; active: boolean };
}

export interface SceneComposite {
  /** 0 = hard clear each frame; >0 leaves motion trails of that opacity. */
  trailAlpha: number;
  /** Additive bloom strength composited back over the frame. 0 disables it. */
  bloom: number;
  /** Blur radius in CSS px used for the bloom pass. */
  bloomRadius: number;
}

export interface VisualScene {
  readonly id: string;
  /** Optional per-scene composite settings; defaults are used if absent. */
  composite?(): SceneComposite;
  /** Called once when the scene becomes active. */
  mount(runtime: NURVisualRuntime): void;
  /** Called every frame while active. */
  render(frame: FrameContext): void;
  /** Called when the viewport size changes. */
  resize?(width: number, height: number): void;
  /** Must release every resource the scene created. */
  unmount(): void;
}

interface BoundListener {
  target: EventTarget;
  type: string;
  handler: EventListenerOrEventListenerObject;
  options?: AddEventListenerOptions;
}

export class NURVisualRuntime {
  readonly document: Document;
  readonly view: Window;

  private canvas: HTMLCanvasElement | null = null;
  private context: CanvasRenderingContext2D | null = null;
  private atlas: SpriteAtlas;
  private scene: VisualScene | null = null;
  private frameHandle: number | null = null;
  private listeners: BoundListener[] = [];
  private governor: QualityGovernor;
  private tier: QualityTier;
  private readonly reducedMotion: boolean;
  private lastFrameAt = 0;
  private width = 0;
  private height = 0;
  private pixelRatio = 1;
  private destroyed = false;
  private readonly pointer = { x: 0, y: 0, active: false };
  private resizeObserver: ResizeObserver | null = null;
  private resizeQueued = false;
  private renderFailures = 0;
  private bloomCanvas: HTMLCanvasElement | null = null;
  private bloomContext: CanvasRenderingContext2D | null = null;
  /** Off-screen buffer the scene draws into; trails accumulate here only. */
  private sceneCanvas: HTMLCanvasElement | null = null;
  private sceneContext: CanvasRenderingContext2D | null = null;

  constructor(document: Document, host: HTMLElement) {
    this.document = document;
    this.view = document.defaultView ?? window;
    this.reducedMotion = prefersReducedMotion(this.view);
    this.tier = detectQualityTier(this.view);
    this.governor = new QualityGovernor(this.tier, tier => {
      this.tier = tier;
      this.applyPixelRatio();
      this.atlas.clear();
    });
    this.atlas = new SpriteAtlas({ pixelRatio: this.tier.maxPixelRatio });
    this.createCanvas(host);
    this.bindEnvironment();
  }

  /**
   * Removes any canvas left over from a previous mount before creating its own,
   * so a hot reload or a repeated route application cannot produce two owners.
   */
  private createCanvas(host: HTMLElement): void {
    this.document.querySelectorAll(`#${CANVAS_ID}`).forEach(existing => existing.remove());

    const canvas = this.document.createElement("canvas");
    canvas.id = CANVAS_ID;
    canvas.setAttribute("aria-hidden", "true");
    canvas.style.cssText = [
      "position:absolute",
      "inset:0",
      "width:100%",
      "height:100%",
      "display:block",
      "pointer-events:none",
      "z-index:0",
    ].join(";");
    host.appendChild(canvas);

    const context = canvas.getContext("2d", { alpha: true });
    this.canvas = canvas;
    this.context = context;
    this.measure(host);
  }

  private applyPixelRatio(): void {
    const raw = this.view.devicePixelRatio || 1;
    this.pixelRatio = Math.min(raw, this.tier.maxPixelRatio);
    if (!this.canvas || !this.context) return;
    this.canvas.width = Math.max(2, Math.round(this.width * this.pixelRatio));
    this.canvas.height = Math.max(2, Math.round(this.height * this.pixelRatio));
    this.context.setTransform(this.pixelRatio, 0, 0, this.pixelRatio, 0, 0);
  }

  private measure(host: HTMLElement): void {
    const rect = host.getBoundingClientRect();
    this.width = Math.max(2, Math.round(rect.width));
    this.height = Math.max(2, Math.round(rect.height));
    this.applyPixelRatio();
    this.scene?.resize?.(this.width, this.height);
  }

  /**
   * Resize is driven by ResizeObserver on the host only. The shipped engines
   * additionally recompute on every `scroll` event, and because resizing
   * reallocates the canvas backing store that is a per-scroll buffer
   * reallocation. This runtime deliberately does not listen to scroll.
   */
  private bindEnvironment(): void {
    const host = this.canvas?.parentElement ?? null;
    const ObserverCtor = (this.view as Window & { ResizeObserver?: typeof ResizeObserver }).ResizeObserver;
    if (host && typeof ObserverCtor === "function") {
      // Coalesced to one measurement per frame: resizing reallocates the canvas
      // backing store, so an unthrottled observer would thrash it.
      const observer = new ObserverCtor(() => {
        if (this.resizeQueued) return;
        this.resizeQueued = true;
        this.view.requestAnimationFrame(() => {
          this.resizeQueued = false;
          if (!this.destroyed) this.measure(host);
        });
      });
      observer.observe(host);
      this.resizeObserver = observer;
    }

    this.bindListener(this.document, "visibilitychange", () => {
      if (this.document.visibilityState === "hidden") this.pause();
      else this.resume();
    });

    if (host) {
      this.bindListener(this.document, "pointermove", event => {
        const rect = host.getBoundingClientRect();
        const pointerEvent = event as PointerEvent;
        this.pointer.x = pointerEvent.clientX - rect.left;
        this.pointer.y = pointerEvent.clientY - rect.top;
        this.pointer.active = true;
      }, { passive: true });
      this.bindListener(host, "pointerleave", () => {
        this.pointer.active = false;
      }, { passive: true });
    }
  }

  /** Every listener registered here is guaranteed to be removed on destroy. */
  bindListener(
    target: EventTarget,
    type: string,
    handler: EventListenerOrEventListenerObject,
    options?: AddEventListenerOptions,
  ): void {
    target.addEventListener(type, handler, options);
    this.listeners.push({ target, type, handler, options });
  }

  currentTier(): QualityTier {
    return this.tier;
  }

  isReducedMotion(): boolean {
    return this.reducedMotion;
  }

  size(): { width: number; height: number } {
    return { width: this.width, height: this.height };
  }

  spriteAtlas(): SpriteAtlas {
    return this.atlas;
  }

  setScene(scene: VisualScene | null): void {
    if (this.scene) {
      this.scene.unmount();
      this.scene = null;
    }
    this.scene = scene;
    if (scene) {
      scene.mount(this);
      scene.resize?.(this.width, this.height);
      this.start();
    } else {
      this.pause();
    }
  }

  activeSceneId(): string | null {
    return this.scene?.id ?? null;
  }

  /** Frames that threw during render; asserted to be 0 by the capture spec. */
  failedFrames(): number {
    return this.renderFailures;
  }

  /** Outstanding rAF handles; asserted to be 0 or 1 by tests. */
  pendingFrames(): number {
    return this.frameHandle === null ? 0 : 1;
  }

  private start(): void {
    if (this.destroyed || this.frameHandle !== null) return;
    this.lastFrameAt = 0;
    this.frameHandle = this.view.requestAnimationFrame(this.tick);
  }

  private pause(): void {
    if (this.frameHandle === null) return;
    this.view.cancelAnimationFrame(this.frameHandle);
    this.frameHandle = null;
  }

  private resume(): void {
    if (this.scene) this.start();
  }

  private readonly tick = (now: number): void => {
    this.frameHandle = null;
    if (this.destroyed || !this.context || !this.scene) return;

    const delta = this.lastFrameAt === 0 ? 16.7 : Math.min(48, now - this.lastFrameAt);
    this.lastFrameAt = now;

    const startedAt = this.view.performance?.now?.() ?? now;
    const composite = this.scene.composite?.() ?? { trailAlpha: 0, bloom: 0, bloomRadius: 0 };
    const trails = composite.trailAlpha > 0 && !this.reducedMotion;

    // The scene draws into its own buffer. This is not an optimisation — it is
    // required for correctness. Bloom composites additively, and trails
    // deliberately do not fully clear, so if bloom were written onto the same
    // surface the scene persists in, every frame would re-amplify the previous
    // frame's bloom. That feedback loop saturates to solid white within a
    // second. Scene and bloom must be combined onto a surface that is wiped
    // every frame.
    const target = trails ? this.ensureSceneBuffer() : this.context;
    if (!target) return;

    if (trails) {
      target.globalCompositeOperation = "source-over";
      target.fillStyle = `rgba(0, 0, 0, ${composite.trailAlpha})`;
      target.fillRect(0, 0, this.width, this.height);
    } else {
      target.clearRect(0, 0, this.width, this.height);
    }
    try {
        this.scene.render({
        context: target,
        atlas: this.atlas,
        width: this.width,
        height: this.height,
        now,
        delta,
        tier: this.tier,
        reducedMotion: this.reducedMotion,
        pointer: this.pointer,
      });
    } catch (error) {
      // One bad frame must not blank the stage forever. Before this guard a
      // single negative radius threw out of the loop and nothing ever drew
      // again — the canvas simply stayed empty with no visible failure.
      this.renderFailures += 1;
      if (this.renderFailures === 1) console.error("NUR visual scene render failed", error);
      if (this.renderFailures >= 30) {
        console.error("NUR visual scene disabled after repeated render failures");
        this.setScene(null);
        return;
      }
    }
    if (trails && this.sceneCanvas) {
      this.context.setTransform(1, 0, 0, 1, 0, 0);
      this.context.globalCompositeOperation = "source-over";
      this.context.globalAlpha = 1;
      this.context.clearRect(0, 0, this.canvas?.width ?? 0, this.canvas?.height ?? 0);
      this.context.drawImage(this.sceneCanvas, 0, 0);
      this.context.setTransform(this.pixelRatio, 0, 0, this.pixelRatio, 0, 0);
    }

    if (composite.bloom > 0 && this.tier.glow && !this.reducedMotion) {
      this.applyBloom(composite.bloom, composite.bloomRadius, trails ? this.sceneCanvas : this.canvas);
    }

    const endedAt = this.view.performance?.now?.() ?? now;
    this.governor.sample(endedAt - startedAt);

    this.frameHandle = this.view.requestAnimationFrame(this.tick);
  };

  /**
   * Real bloom, cheaply: downsample the frame to a quarter, blur it, composite
   * it back additively. Bright regions bleed light into their surroundings the
   * way a lens does. Quarter resolution keeps the blur affordable and, because
   * bloom is inherently low-frequency, costs nothing visually.
   */
  private applyBloom(strength: number, radius: number, source: HTMLCanvasElement | null): void {
    if (!this.context || !this.canvas || !source) return;
    const width = Math.max(2, Math.round(this.width / 4));
    const height = Math.max(2, Math.round(this.height / 4));

    if (!this.bloomCanvas) {
      this.bloomCanvas = this.document.createElement("canvas");
      this.bloomContext = this.bloomCanvas.getContext("2d", { alpha: true });
    }
    const bloom = this.bloomContext;
    if (!this.bloomCanvas || !bloom) return;
    if (this.bloomCanvas.width !== width || this.bloomCanvas.height !== height) {
      this.bloomCanvas.width = width;
      this.bloomCanvas.height = height;
    }

    bloom.setTransform(1, 0, 0, 1, 0, 0);
    bloom.clearRect(0, 0, width, height);
    bloom.filter = `blur(${Math.max(1, radius / 4)}px)`;
    bloom.drawImage(source, 0, 0, width, height);
    bloom.filter = "none";

    this.context.save();
    this.context.setTransform(1, 0, 0, 1, 0, 0);
    this.context.globalCompositeOperation = "lighter";
    this.context.globalAlpha = strength;
    this.context.drawImage(this.bloomCanvas, 0, 0, this.canvas.width, this.canvas.height);
    this.context.restore();
  }

  /** Lazily sized off-screen buffer matching the canvas backing store. */
  private ensureSceneBuffer(): CanvasRenderingContext2D | null {
    if (!this.canvas) return null;
    if (!this.sceneCanvas) {
      this.sceneCanvas = this.document.createElement("canvas");
      this.sceneContext = this.sceneCanvas.getContext("2d", { alpha: true });
    }
    if (!this.sceneCanvas || !this.sceneContext) return null;
    if (this.sceneCanvas.width !== this.canvas.width || this.sceneCanvas.height !== this.canvas.height) {
      this.sceneCanvas.width = this.canvas.width;
      this.sceneCanvas.height = this.canvas.height;
      this.sceneContext.setTransform(this.pixelRatio, 0, 0, this.pixelRatio, 0, 0);
    }
    return this.sceneContext;
  }

  destroy(): void {
    if (this.destroyed) return;
    this.destroyed = true;
    this.pause();
    if (this.scene) {
      this.scene.unmount();
      this.scene = null;
    }
    this.resizeObserver?.disconnect();
    this.resizeObserver = null;
    for (const entry of this.listeners) {
      entry.target.removeEventListener(entry.type, entry.handler, entry.options);
    }
    this.listeners = [];
    this.atlas.clear();
    this.bloomCanvas = null;
    this.bloomContext = null;
    this.sceneCanvas = null;
    this.sceneContext = null;
    this.canvas?.remove();
    this.canvas = null;
    this.context = null;
  }
}
