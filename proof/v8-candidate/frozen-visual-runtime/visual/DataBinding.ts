/**
 * Maps real owner data onto visual properties.
 *
 * The binding rules here are deliberately literal. A visual property may only
 * encode a quantity the backend actually reports, and the meaning recorded in
 * `docs/v8/VISUAL_DATA_BINDING_MATRIX.csv` must match this file. Nothing in the
 * scene may imply an inference the product does not make: node size is action
 * completion, not motivation; warmth is recency of movement, not mood.
 */

import type { V197SystemSnapshot, V197SystemsSnapshot } from "../bridge/v197ApiClient";

/** Spectral identity per System. Fixed, so a System is recognisable by colour. */
const SYSTEM_COLOURS: Record<string, string> = {
  "quiet-ambition": "#ffd27a",
  rebuild: "#ff9f6b",
  study: "#8fc5ff",
  money: "#f4e08a",
  body: "#7fe0b4",
  connection: "#c9b6ff",
  creation: "#ffb3d1",
};

const FALLBACK_COLOUR = "#c4defc";

export interface SystemNodeModel {
  slug: string;
  title: string;
  definition: string;
  orbitId: string;
  /** 0..1 — drives orbital radius and node radius. Source: progress_percent. */
  progress: number;
  /** Source: progress_sources.formula — shown verbatim, never paraphrased. */
  progressFormula: string;
  completedActions: number;
  totalActions: number;
  /** Source: active_goal_count — drives satellite count, capped for legibility. */
  goalCount: number;
  blockerCount: number;
  colour: string;
  /** Source: next_move.title — the one action offered for this System. */
  nextMove: string;
  hasData: boolean;
}

export interface SystemsSceneModel {
  nodes: SystemNodeModel[];
  provenanceLabel: string;
  /** True when the snapshot carried no Systems at all. */
  empty: boolean;
}

function clamp01(value: number): number {
  if (!Number.isFinite(value)) return 0;
  return Math.max(0, Math.min(1, value));
}

function readNextMove(system: V197SystemSnapshot): string {
  const move = system.next_move as { title?: unknown } | null | undefined;
  const title = move && typeof move.title === "string" ? move.title.trim() : "";
  return title;
}

export function buildSystemsModel(snapshot: V197SystemsSnapshot | null | undefined): SystemsSceneModel {
  const systems = snapshot?.systems ?? [];
  const nodes = systems.map(system => {
    const sources = system.progress_sources;
    return {
      slug: system.slug,
      title: system.title,
      definition: system.definition,
      orbitId: system.orbit_id,
      progress: clamp01((system.progress_percent ?? 0) / 100),
      progressFormula: sources?.formula ?? "",
      completedActions: sources?.completed_actions ?? 0,
      totalActions: sources?.total_actions ?? 0,
      goalCount: Math.max(0, system.active_goal_count ?? 0),
      blockerCount: Array.isArray(system.blockers) ? system.blockers.length : 0,
      colour: SYSTEM_COLOURS[system.slug] ?? FALLBACK_COLOUR,
      nextMove: readNextMove(system),
      hasData: (sources?.total_actions ?? 0) > 0 || (system.active_goal_count ?? 0) > 0,
    } satisfies SystemNodeModel;
  });

  return {
    nodes,
    provenanceLabel: snapshot?.provenance_label ?? "",
    empty: nodes.length === 0,
  };
}

/**
 * Systems sharing an orbit are genuinely related in the data model, so an arc
 * between them asserts something true. No other arcs are drawn — a line that
 * merely looked good would be a fabricated relationship.
 */
export function orbitRelationships(nodes: SystemNodeModel[]): Array<[number, number]> {
  const pairs: Array<[number, number]> = [];
  for (let a = 0; a < nodes.length; a += 1) {
    for (let b = a + 1; b < nodes.length; b += 1) {
      const first = nodes[a];
      const second = nodes[b];
      if (first && second && first.orbitId && first.orbitId === second.orbitId) {
        pairs.push([a, b]);
      }
    }
  }
  return pairs;
}
