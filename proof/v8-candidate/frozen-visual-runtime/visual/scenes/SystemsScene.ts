/**
 * Slice 1 — the Laniakea Systems scene.
 *
 * Composition, from back to front:
 *
 *   far field  → cool, small, slow parallax
 *   mid field  → the body of the sky
 *   hero       → the NUR star-brain, depth-sorted, occluding what sits behind it
 *   arcs       → relationships between Systems that genuinely share an orbit
 *   nodes      → the seven Systems, anchored to the brain region they own
 *   near field → warm, large, fast parallax, drawn in front of everything
 *
 * Focusing a System resolves the region of the brain assigned to it and lets the
 * rest recede. Focus arrives identically from the pointer and from the canonical
 * keyboard buttons, so the spatial view and its accessible equivalent cannot
 * disagree.
 */

import { Motion, type MotionPrimitive } from "../MotionController";
import type { FrameContext, NURVisualRuntime, SceneComposite, VisualScene } from "../NURVisualRuntime";
import { withAlpha } from "../materials/SpriteAtlas";
import { orbitRelationships, type SystemNodeModel, type SystemsSceneModel } from "../DataBinding";
import { NeuralCloud } from "../objects/NeuralCloud";
import { DepthField } from "../objects/DepthField";

interface PlacedNode {
  model: SystemNodeModel;
  angle: number;
  orbit: number;
  x: number;
  y: number;
  screenRadius: number;
}

export class SystemsScene implements VisualScene {
  readonly id = "systems";

  private runtime: NURVisualRuntime | null = null;
  private model: SystemsSceneModel;
  private placed: PlacedNode[] = [];
  private relationships: Array<[number, number]> = [];
  private hero: NeuralCloud | null = null;
  private fields: DepthField[] = [];
  private width = 0;
  private height = 0;
  private centreX = 0;
  private centreY = 0;
  private extent = 0;
  private focusIndex = -1;
  private focusAmount = 0;
  private nucleate: Motion | null = null;
  private focusMotion: Motion | null = null;
  private yaw = 0.85;
  private pitch = -0.14;
  private onFocusChange: ((node: SystemNodeModel | null) => void) | null = null;
  private heroScale = 1;
  private pendingShock: { x: number; y: number; strength: number } | null = null;

  constructor(model: SystemsSceneModel) {
    this.model = model;
    this.relationships = orbitRelationships(model.nodes);
  }

  /**
   * Trails and bloom are what make this read as a lens looking at a real object
   * rather than a canvas drawing dots. Both are disabled under reduced motion by
   * the runtime.
   */
  composite(): SceneComposite {
    // Trail alpha 0.22 decays a trail in ~4 frames; 0.16 held it for ~6 and made
    // the field feel smeared. Bloom 0.26 is a lens halo, not a wash — it was 0.42
    // when the feedback loop white-washed the screen.
    return { trailAlpha: 0.22, bloom: 0.26, bloomRadius: 22 };
  }

  /** Queue a shockwave at a screen position — the click impulse. */
  strike(x: number, y: number, strength = 1): void {
    this.pendingShock = { x, y, strength };
  }

  setFocusListener(listener: (node: SystemNodeModel | null) => void): void {
    this.onFocusChange = listener;
  }

  mount(runtime: NURVisualRuntime): void {
    this.runtime = runtime;
    const tier = runtime.currentTier();
    const mobile = runtime.size().width < 780;

    this.hero = new NeuralCloud({ density: tier.particleScale, mobile });
    this.hero.assignSystems(this.model.nodes.length);

    // Mobile drops the near plane entirely: fewer, larger elements and one clear
    // subject, rather than the desktop field scaled down.
    const planes: Array<"far" | "mid" | "near"> = mobile ? ["far", "mid"] : ["far", "mid", "near"];
    this.fields = planes.map(plane => new DepthField(plane, tier.particleScale));

    this.nucleate = new Motion("NUCLEATE", runtime.isReducedMotion());
    this.nucleate.start(runtime.view.performance?.now?.() ?? 0);
  }

  resize(width: number, height: number): void {
    this.width = width;
    this.height = height;
    this.centreX = width / 2;
    this.centreY = height / 2;
    this.extent = Math.min(width, height) * 0.46;
    this.layout();
  }

  updateModel(model: SystemsSceneModel): void {
    this.model = model;
    this.relationships = orbitRelationships(model.nodes);
    this.hero?.assignSystems(model.nodes.length);
    this.layout();
  }

  private layout(): void {
    const count = this.model.nodes.length;
    this.placed = this.model.nodes.map((model, index) => {
      const angle = (index / Math.max(1, count)) * Math.PI * 2 - Math.PI / 2;
      // Movement pulls a System inward: higher progress sits closer to the core.
      const orbit = 0.96 - model.progress * 0.3;
      return { model, angle, orbit, x: 0, y: 0, screenRadius: 0 } satisfies PlacedNode;
    });
  }

  setFocus(index: number): void {
    const clamped = index >= 0 && index < this.placed.length ? index : -1;
    if (clamped === this.focusIndex) return;
    this.focusIndex = clamped;
    const primitive: MotionPrimitive = clamped >= 0 ? "FOCUS" : "RETURN_TO_CORE";
    this.focusMotion = new Motion(primitive, this.runtime?.isReducedMotion() ?? false);
    this.focusMotion.start(this.runtime?.view.performance?.now?.() ?? 0);
    this.onFocusChange?.(clamped >= 0 ? (this.placed[clamped]?.model ?? null) : null);
  }

  focusedIndex(): number {
    return this.focusIndex;
  }

  nodeAt(x: number, y: number): number {
    let best = -1;
    let bestDistance = Infinity;
    for (let index = 0; index < this.placed.length; index += 1) {
      const node = this.placed[index];
      if (!node) continue;
      const distance = Math.hypot(node.x - x, node.y - y);
      if (distance < Math.max(26, node.screenRadius * 2.6) && distance < bestDistance) {
        bestDistance = distance;
        best = index;
      }
    }
    return best;
  }

  render(frame: FrameContext): void {
    const { context, atlas, now, delta, tier, reducedMotion } = frame;

    const nucleation = this.nucleate?.sample(now).value ?? 1;
    const focusRun = this.focusMotion?.sample(now).value ?? 1;
    const focusTarget = this.focusIndex >= 0 ? 1 : 0;
    this.focusAmount += (focusTarget - this.focusAmount) * focusRun * 0.3;

    // Deliberate slow revolution only — no idle wobble, no camera drift.
    if (!reducedMotion) this.yaw += delta * 0.000045;

    const pointerX = frame.pointer.active ? (frame.pointer.x - this.centreX) / Math.max(1, this.width) : 0;
    const pointerY = frame.pointer.active ? (frame.pointer.y - this.centreY) / Math.max(1, this.height) : 0;

    const focused = this.focusIndex >= 0 ? this.placed[this.focusIndex] : null;
    const focusColour = focused?.model.colour ?? "#ffd9a0";

    context.save();
    context.globalCompositeOperation = "lighter";

    const fieldOptions = {
      width: this.width,
      height: this.height,
      now,
      delta,
      pointerX,
      pointerY,
      reducedMotion,
      dim: 1 - this.focusAmount * 0.42,
      nucleation,
      glow: tier.glow,
    };

    for (const field of this.fields) {
      if (field.plane !== "near") field.render(context, atlas, fieldOptions);
    }

    this.heroScale = this.extent * 0.86;

    // Physics before projection so the frame shows the settled state.
    if (!reducedMotion) {
      this.hero?.integrate(delta);
      if (frame.pointer.active) {
        this.hero?.repelFrom(frame.pointer.x, frame.pointer.y, this.extent * 0.42, 0.55, this.heroScale);
      }
      if (this.pendingShock) {
        this.hero?.shockwave(this.pendingShock.x, this.pendingShock.y, this.pendingShock.strength, this.heroScale);
        this.pendingShock = null;
      }
    }

    this.hero?.render(context, atlas, {
      centreX: this.centreX,
      centreY: this.centreY,
      scale: this.heroScale,
      yaw: this.yaw,
      pitch: this.pitch + pointerY * 0.12,
      now,
      reducedMotion,
      glow: tier.glow,
      focusSystem: this.focusIndex,
      focusAmount: this.focusAmount,
      focusColour,
      nucleation,
    });

    this.updatePositions(nucleation, pointerX, pointerY, reducedMotion);
    this.renderRelationships(frame, nucleation);
    this.renderNodes(frame, nucleation);

    for (const field of this.fields) {
      if (field.plane === "near") field.render(context, atlas, fieldOptions);
    }

    context.restore();

    if (tier.name !== "low") this.renderTelemetryRing(context, nucleation);
  }

  /**
   * Nodes are anchored to the centroid of the brain region they own, so a System
   * and its matter occupy the same place. When the region is behind the camera
   * the node falls back to its orbital position rather than jumping.
   */
  private updatePositions(nucleation: number, pointerX: number, pointerY: number, reducedMotion: boolean): void {
    const parallax = reducedMotion ? 0 : 16;
    for (let index = 0; index < this.placed.length; index += 1) {
      const node = this.placed[index];
      if (!node) continue;
      const focused = index === this.focusIndex;

      const orbitRadius = node.orbit * this.extent * nucleation * (focused ? 0.86 : 1);
      const angle = node.angle + this.yaw * 0.35;
      const orbitX = this.centreX + Math.cos(angle) * orbitRadius;
      const orbitY = this.centreY + Math.sin(angle) * orbitRadius * 0.62;

      const anchor = this.hero?.regionAnchor(index) ?? null;
      // Blend toward the region centroid; full snap would make nodes jitter with
      // the rotation, so the orbital position keeps them stable.
      const blend = anchor ? (focused ? 0.55 : 0.28) : 0;
      const targetX = anchor ? orbitX + (anchor.x - orbitX) * blend : orbitX;
      const targetY = anchor ? orbitY + (anchor.y - orbitY) * blend : orbitY;

      node.x = targetX - pointerX * parallax * node.orbit;
      node.y = targetY - pointerY * parallax * node.orbit;
      node.screenRadius = (6 + node.model.progress * 10) * (focused ? 1.5 : 1) * nucleation;
    }
  }

  private renderRelationships(frame: FrameContext, nucleation: number): void {
    const { context, tier, now } = frame;
    if (this.relationships.length === 0) return;
    context.lineWidth = 1;
    for (const [a, b] of this.relationships) {
      const first = this.placed[a];
      const second = this.placed[b];
      if (!first || !second) continue;
      const involved = this.focusIndex === a || this.focusIndex === b;
      const alpha = (involved ? 0.46 : 0.13 - this.focusAmount * 0.08) * nucleation;
      if (alpha <= 0.01) continue;
      const span = Math.hypot(second.x - first.x, second.y - first.y);
      const midX = (first.x + second.x) / 2;
      const midY = (first.y + second.y) / 2 - span * 0.24;
      context.strokeStyle = withAlpha(first.model.colour, alpha);
      context.setLineDash([5, 11]);
      context.lineDashOffset = tier.animatedArcs ? -((now * 0.012) % 64) : 0;
      context.beginPath();
      context.moveTo(first.x, first.y);
      context.quadraticCurveTo(midX, midY, second.x, second.y);
      context.stroke();
    }
    context.setLineDash([]);
  }

  private renderNodes(frame: FrameContext, nucleation: number): void {
    const { context, atlas, tier, now, reducedMotion } = frame;

    for (let index = 0; index < this.placed.length; index += 1) {
      const node = this.placed[index];
      if (!node) continue;
      const focused = index === this.focusIndex;
      const recede = focused ? 1 : 1 - this.focusAmount * 0.5;
      const colour = node.model.colour;
      const radius = node.screenRadius;

      if (tier.glow) {
        atlas.draw(context, "glow", colour, node.x, node.y, radius * (focused ? 5 : 3.3), 0.42 * recede * nucleation);
      }

      // A System with no recorded activity is drawn hollow. Absence of data must
      // look like absence, never like a low score.
      if (node.model.hasData) {
        atlas.draw(context, "core", colour, node.x, node.y, radius, 0.92 * recede * nucleation);
      } else {
        context.strokeStyle = withAlpha(colour, 0.46 * recede * nucleation);
        context.lineWidth = 1.2;
        context.beginPath();
        context.arc(node.x, node.y, radius * 0.74, 0, Math.PI * 2);
        context.stroke();
      }

      if (focused) atlas.draw(context, "spark", "#ffffff", node.x, node.y, radius * 2.4, 0.46);

      // One satellite per active goal, capped so a busy System stays readable.
      const satellites = Math.min(12, node.model.goalCount);
      if (satellites > 0) {
        const ring = radius * 2.6;
        const spin = reducedMotion ? 0 : now * 0.00019 * (index % 2 === 0 ? 1 : -1);
        for (let satellite = 0; satellite < satellites; satellite += 1) {
          const angle = (satellite / satellites) * Math.PI * 2 + spin;
          atlas.draw(
            context, "core", colour,
            node.x + Math.cos(angle) * ring,
            node.y + Math.sin(angle) * ring * 0.72,
            1.6, 0.6 * recede * nucleation,
          );
        }
      }
    }
  }

  /** Thin technical ring: telemetry, drawn precisely rather than bloomed. */
  private renderTelemetryRing(context: CanvasRenderingContext2D, nucleation: number): void {
    const radius = this.extent * 1.04 * nucleation;
    context.save();
    context.strokeStyle = "rgba(196, 222, 252, 0.09)";
    context.lineWidth = 1;
    context.beginPath();
    context.ellipse(this.centreX, this.centreY, radius, radius * 0.62, 0, 0, Math.PI * 2);
    context.stroke();

    for (let index = 0; index < this.placed.length; index += 1) {
      const node = this.placed[index];
      if (!node) continue;
      const angle = node.angle + this.yaw * 0.35;
      const focused = index === this.focusIndex;
      const outer = focused ? 1.07 : 1.025;
      context.strokeStyle = withAlpha(node.model.colour, focused ? 0.55 : 0.2);
      context.beginPath();
      context.moveTo(
        this.centreX + Math.cos(angle) * radius * 0.985,
        this.centreY + Math.sin(angle) * radius * 0.62 * 0.985,
      );
      context.lineTo(
        this.centreX + Math.cos(angle) * radius * outer,
        this.centreY + Math.sin(angle) * radius * 0.62 * outer,
      );
      context.stroke();
    }
    context.restore();
  }

  unmount(): void {
    this.hero?.dispose();
    this.hero = null;
    for (const field of this.fields) field.dispose();
    this.fields = [];
    this.placed = [];
    this.relationships = [];
    this.onFocusChange = null;
    this.nucleate = null;
    this.focusMotion = null;
    this.runtime = null;
  }
}
