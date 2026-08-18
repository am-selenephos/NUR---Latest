import INSIGHTS_CSS from "../styles/v197-insights.css?raw";
import type { V197BridgeSnapshot, V197Insights } from "./v197ApiClient";
import { claimV197SurfaceHost, releaseV197SurfaceHost } from "./v197SurfaceHost";

const ROOT_ID = "nur-insights-root";
const STYLE_ID = "nur-insights-style";

export const INSIGHTS_ROUTE = "/universe/insights";

type InsightRow = Record<string, unknown>;

function el<K extends keyof HTMLElementTagNameMap>(
  document: Document,
  tag: K,
  className?: string,
  content?: string,
): HTMLElementTagNameMap[K] {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (content !== undefined) node.textContent = content;
  return node;
}

function ensureStyle(document: Document): void {
  if (document.getElementById(STYLE_ID)) return;
  const style = document.createElement("style");
  style.id = STYLE_ID;
  style.textContent = INSIGHTS_CSS;
  document.head.append(style);
}

function text(row: InsightRow | null | undefined, keys: string[], fallback: string): string {
  for (const key of keys) {
    const value = row?.[key];
    if (typeof value === "string" && value.trim()) return value.trim();
  }
  return fallback;
}

function number(value: unknown, fallback = 0): number {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

function rows(insights: V197Insights | null): InsightRow[] {
  if (!insights) return [];
  if (insights.dedicated_insights?.length) return insights.dedicated_insights;
  return insights.claims;
}

function list(
  document: Document,
  title: string,
  source: InsightRow[],
  keys: string[],
  empty: string,
): HTMLElement {
  const section = el(document, "section", "nur-insights-review-section");
  section.append(el(document, "h3", "nur-insights-review-title", title));
  if (!source.length) {
    section.append(el(document, "p", "nur-insights-empty", empty));
    return section;
  }
  const items = el(document, "ul", "nur-insights-review-list");
  for (const row of source.slice(0, 4)) {
    const item = el(document, "li", "nur-insights-review-item");
    item.append(el(document, "span", "nur-insights-review-mark", "*"));
    item.append(el(document, "span", "", text(row, keys, "Persisted record awaiting review.")));
    items.append(item);
  }
  section.append(items);
  return section;
}

function countOf(insights: V197Insights | null, key: string, source: InsightRow[]): number {
  return number(insights?.counts[key], source.length);
}

export function renderV197Insights(
  document: Document,
  route: string,
  snapshot: V197BridgeSnapshot | null,
): boolean {
  if (route !== INSIGHTS_ROUTE) {
    document.getElementById(ROOT_ID)?.remove();
    releaseV197SurfaceHost(document);
    return false;
  }

  ensureStyle(document);
  const host = claimV197SurfaceHost(document);
  if (!host) {
    releaseV197SurfaceHost(document);
    return false;
  }

  const insights = snapshot?.insights ?? null;
  const claims = rows(insights);
  let selected = 0;

  const root = el(document, "div");
  root.id = ROOT_ID;
  root.dataset.v197NativeAdjunct = "true";
  root.dataset.insightsLoaded = "true";
  root.dataset.nurBrainSurface = "none";

  const shell = el(document, "div", "nur-insights-shell");
  const header = el(document, "header", "nur-insights-header");
  const heading = el(document, "div", "nur-insights-heading");
  heading.append(el(document, "p", "nur-insights-kicker", "OWNER INTERPRETATION FIELD"));
  heading.append(el(document, "h1", "", "Insights"));
  heading.append(el(
    document,
    "p",
    "nur-insights-subtitle",
    "Patterns, tensions and possible futures held against persisted owner evidence.",
  ));
  const provenance = el(
    document,
    "p",
    "nur-insights-provenance",
    insights?.provenance_label ?? "owner ledger unavailable",
  );
  header.append(heading, provenance);

  const counts = el(document, "div", "nur-insights-counts");
  const countData = [
    ["Candidate claims", countOf(insights, "claims", claims)],
    ["Open tensions", countOf(insights, "open_contradictions", insights?.contradictions ?? [])],
    ["Predictions", countOf(insights, "predictions", insights?.predictions ?? [])],
    ["Awaiting review", countOf(insights, "review_queue", insights?.review_queue ?? [])],
  ] as const;
  for (const [label, value] of countData) {
    const count = el(document, "div", "nur-insights-count");
    count.append(el(document, "strong", "", String(value)));
    count.append(el(document, "span", "", label));
    counts.append(count);
  }

  const zones = el(document, "div", "nur-insights-zones");
  const navigator = el(document, "nav", "nur-insights-pane nur-insights-nav");
  navigator.setAttribute("aria-label", "Persisted insights");
  navigator.append(el(document, "h2", "nur-insights-pane-title", "Interpretations"));
  const navList = el(document, "div", "nur-insights-nav-list");

  const detail = el(document, "main", "nur-insights-pane nur-insights-detail");
  const renderDetail = (): void => {
    detail.replaceChildren();
    const row = claims[selected] ?? null;
    if (!row) {
      detail.append(el(document, "p", "nur-insights-detail-kicker", "EVIDENCE STATE"));
      detail.append(el(document, "h2", "nur-insights-detail-title", "No reliable insight yet."));
      detail.append(el(
        document,
        "p",
        "nur-insights-detail-copy",
        "NUR needs persisted evidence across time or domains before it surfaces an interpretation.",
      ));
      return;
    }
    const confidence = number(row.confidence, -1);
    const domains = Array.isArray(row.source_domains)
      ? row.source_domains.filter(value => typeof value === "string").join(" / ")
      : "Source domains not recorded";
    detail.append(el(
      document,
      "p",
      "nur-insights-detail-kicker",
      `${text(row, ["truth_status", "epistemic_state"], "CANDIDATE")} / ${text(row, ["time_scale"], "OPEN HORIZON")}`,
    ));
    detail.append(el(
      document,
      "h2",
      "nur-insights-detail-title",
      text(row, ["claim_text", "title", "claim"], "Persisted candidate insight"),
    ));
    detail.append(el(
      document,
      "p",
      "nur-insights-detail-copy",
      confidence >= 0
        ? `${Math.round(confidence * 100)}% confidence from the current owner evidence.`
        : "Confidence has not been measured.",
    ));

    const evidence = el(document, "div", "nur-insights-evidence");
    const evidenceRows = [
      ["Source domains", domains],
      ["Evidence records", String(Array.isArray(row.evidence) ? row.evidence.length : 0)],
      ["What NUR may be wrong about", text(
        row,
        ["what_nur_may_be_wrong_about"],
        "This interpretation is limited to what the owner has recorded.",
      )],
      ["Suggested next move", text(row, ["suggested_action"], "No action has been proposed.")],
    ] as const;
    for (const [label, value] of evidenceRows) {
      const field = el(document, "div", "nur-insights-field");
      field.append(el(document, "span", "", label));
      field.append(el(document, "p", "", value));
      evidence.append(field);
    }
    detail.append(evidence);
  };

  if (!claims.length) {
    navList.append(el(document, "p", "nur-insights-empty", "No candidate interpretation has been persisted."));
  } else {
    claims.forEach((row, index) => {
      const button = el(
        document,
        "button",
        "nur-insights-nav-item",
        text(row, ["title", "claim_text", "claim"], `Insight ${index + 1}`),
      );
      button.type = "button";
      button.setAttribute("aria-pressed", index === selected ? "true" : "false");
      button.addEventListener("click", () => {
        selected = index;
        navList.querySelectorAll("button").forEach((control, controlIndex) => {
          control.setAttribute("aria-pressed", controlIndex === selected ? "true" : "false");
        });
        renderDetail();
      });
      navList.append(button);
    });
  }
  navigator.append(navList);

  const review = el(document, "aside", "nur-insights-pane nur-insights-review");
  review.append(el(document, "h2", "nur-insights-pane-title", "Review state"));
  review.append(list(
    document,
    "Open tensions",
    insights?.contradictions ?? [],
    ["description", "claim_text", "title"],
    "No open contradiction is persisted.",
  ));
  review.append(list(
    document,
    "Possible futures",
    insights?.predictions ?? [],
    ["prediction_text", "description", "title"],
    "No unresolved prediction is persisted.",
  ));
  review.append(list(
    document,
    "Owner review",
    insights?.review_queue ?? [],
    ["title", "claim_text", "description"],
    "Nothing is waiting for owner review.",
  ));

  renderDetail();
  zones.append(navigator, detail, review);
  shell.append(header, counts, zones);
  root.append(shell);
  host.replaceChildren(root);
  return true;
}
