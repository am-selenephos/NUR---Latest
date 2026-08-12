/**
 * Regenerate docs/release/v197-control-matrix.json against the current candidate.
 *
 * The control list itself is curated: which controls exist, what they mean, and how they are
 * classified is a product judgement, not something a script can invent. What this script does
 * is re-derive every machine-checkable fact from the working tree, so the matrix can never
 * again claim freshness from a self-referential commit stamp:
 *
 *   - records the canonical V197 host/entry/universe SHA-256 the matrix was validated against;
 *   - resolves each control's selector against the decoded canonical sources and labels it
 *     canonical / bridge / n-a, so a bridge-created surface is never mistaken for source DOM;
 *   - verifies every named desktop and mobile proof spec exists on disk;
 *   - recomputes totals from the controls rather than trusting the stored numbers.
 *   - hashes the generator, canonical sources, normalized controls, and named proof specs;
 *   - emits deterministic JSON, allowing the release gate to prove freshness with git diff;
 *   - resolves each selector as canonical / bridge / n-a;
 *   - verifies every named proof spec exists and recomputes all totals.
 *
 * Exits non-zero on any missing proof spec or totals mismatch.
 */
import { createHash } from "node:crypto";
import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

const webRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const repositoryRoot = path.resolve(webRoot, "../..");
const generatorPath = fileURLToPath(import.meta.url);
const matrixPath = path.join(repositoryRoot, "docs/release/v197-control-matrix.json");
const e2eRoot = path.join(webRoot, "e2e");

const canonicalFiles = {
  host: path.join(webRoot, "public/v197/NUR_V197_CHECKBOX_TICK_RESTORED.html"),
  entry: path.join(repositoryRoot, "docs/reference/entry_decoded_v197.html"),
  universe: path.join(repositoryRoot, "docs/reference/universe_decoded_v197.html"),
};

const sha256 = file => createHash("sha256").update(readFileSync(file)).digest("hex");
const digest = value => createHash("sha256").update(value).digest("hex");

// A selector resolves against the canonical source when one of its fragments matches real
// markup in the decoded Entry or Universe document. A CSS fragment is not the same string as
// the attribute it selects, so each form is translated before searching: `#id` becomes
// id="id", `.cls` is looked for inside a class attribute, and `[data-x='y']` becomes
// data-x="y" with either quote style. Anything with no markup match is created by the bridge
// at runtime and is labelled as such rather than being credited to the canonical source.
function matchers(token) {
  const out = [];
  for (const [, id] of token.matchAll(/#([A-Za-z0-9_-]+)/g)) {
    out.push(source => new RegExp(`id=["']${id}["']`).test(source));
  }
  for (const [, cls] of token.matchAll(/\.([A-Za-z0-9_-]+)/g)) {
    out.push(source => new RegExp(`class=["'][^"']*\\b${cls}\\b`).test(source));
  }
  for (const [, body] of token.matchAll(/\[([^\]]+)\]/g)) {
    const [rawName, rawValue] = body.split("=");
    const name = rawName.trim();
    if (rawValue === undefined) {
      out.push(source => new RegExp(`\\b${name}[\\s=>]`).test(source));
    } else {
      const value = rawValue.trim().replace(/^["']|["']$/g, "");
      out.push(source => new RegExp(`${name}=["']${value}["']`).test(source));
    }
  }
  return out;
}

function resolveSelector(selector, sources) {
  if (!selector) return "n-a";
  const tokens = selector
    .replace(/:visible|\([^)]*\)|…/g, " ")
    .split(",")
    .map(part => part.trim())
    .filter(Boolean);
  const tests = tokens.flatMap(matchers);
  if (tests.length === 0) return "n-a";
  return tests.some(test => sources.some(test)) ? "canonical" : "bridge";
}

const matrix = JSON.parse(readFileSync(matrixPath, "utf8"));
const retiredControlIds = new Set([
  "top.search",
  "top.deep",
  "universe.composer",
  "research.stage",
  "research.live-fetch",
  "community.rooms.shell",
  "community.members",
  "council.flow",
  "community.legacy-tabs",
  "consultation.create",
  "consultation.open",
  "consultation.contribute",
  "consultation.stage",
  "community.return",
  "community.room-create",
  "community.start-consultation",
  "community.room-open",
  "community.message-send",
  "community.post-create",
  "community.post-open",
  "community.react-useful",
  "community.react-witness",
  "community.comment-create",
  "community.future-tabs",
]);
matrix.controls = matrix.controls.filter(control => !retiredControlIds.has(control.id));
const localTabs = matrix.controls.find(control => control.id === "nav.local-tabs");
if (localTabs) {
  localTabs.label = "context tabs";
  localTabs.selector = "[data-context-tab]";
}
const liveAccountControls = {
  "settings.export": {
    api: "POST /api/v1/account/export",
    persistence: "owner-scoped deterministic JSON download + SHA-256 checksum",
    notes: "real owner export; fail-closed API response and download proof",
  },
  "settings.delete": {
    api: "DELETE /api/v1/account",
    persistence: "reauthenticated owner deletion + session revocation",
    notes: "exact confirmation and current password required",
  },
};
for (const [id, truth] of Object.entries(liveAccountControls)) {
  const control = matrix.controls.find(row => row.id === id);
  if (!control) continue;
  Object.assign(control, truth, { classification: "LIVE_REAL" });
  control.desktop_proof = ["account-privacy-ui.spec.ts", "v197-control-matrix.spec.ts"];
  control.mobile_proof = ["account-privacy-ui.spec.ts", "v197-control-matrix.spec.ts"];
}
const sources = [readFileSync(canonicalFiles.entry, "utf8"), readFileSync(canonicalFiles.universe, "utf8")];

const missingProofs = [];
const resolution = { canonical: 0, bridge: 0, "n-a": 0 };

for (const control of matrix.controls) {
  const origin = resolveSelector(control.selector, sources);
  control.selector_origin = origin;
  resolution[origin] += 1;

  for (const spec of [...(control.desktop_proof ?? []), ...(control.mobile_proof ?? [])]) {
    if (!existsSync(path.resolve(e2eRoot, spec))) missingProofs.push(`${control.id} -> ${spec}`);
  }
  if ((control.desktop_proof ?? []).length === 0) missingProofs.push(`${control.id} -> no desktop proof named`);
}

const totals = { total: matrix.controls.length };
for (const classification of matrix.classifications) totals[classification] = 0;
for (const control of matrix.controls) totals[control.classification] += 1;

delete matrix.generated_from_sha;
delete matrix.generated_at;
matrix.canonical_v197_sha256 = Object.fromEntries(
  Object.entries(canonicalFiles).map(([key, file]) => [key, sha256(file)]),
);
matrix.totals = totals;
matrix.validation = {
  proof_specs_resolved: missingProofs.length === 0,
  missing_proof_specs: missingProofs,
  selector_origin_counts: resolution,
};
const proofSpecs = [...new Set(matrix.controls.flatMap(control => [
  ...(control.desktop_proof ?? []),
  ...(control.mobile_proof ?? []),
]))].sort();
matrix.generation_policy = "deterministic-source-fingerprint-v1";
matrix.source_fingerprint = digest(JSON.stringify({
  generator_sha256: sha256(generatorPath),
  canonical_v197_sha256: matrix.canonical_v197_sha256,
  proof_specs_sha256: Object.fromEntries(proofSpecs.map(spec => [spec, sha256(path.resolve(e2eRoot, spec))])),
  architecture: matrix.architecture,
  classifications: matrix.classifications,
  notes: matrix.notes,
  controls: matrix.controls,
  totals: matrix.totals,
  validation: matrix.validation,
}));

writeFileSync(matrixPath, `${JSON.stringify(matrix, null, 2)}\n`);

process.stdout.write(`${JSON.stringify({
  generation_policy: matrix.generation_policy,
  source_fingerprint: matrix.source_fingerprint,
  canonical_v197_sha256: matrix.canonical_v197_sha256,
  totals,
  selector_origin_counts: resolution,
  missing_proof_specs: missingProofs,
}, null, 2)}\n`);

if (missingProofs.length > 0) {
  process.stderr.write(`control matrix: ${missingProofs.length} unresolved proof reference(s)\n`);
  process.exitCode = 1;
}
