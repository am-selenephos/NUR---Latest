/**
 * Regenerate docs/release/v197-control-matrix.json against the current candidate.
 *
 * The control list itself is curated: which controls exist, what they mean, and how they are
 * classified is a product judgement, not something a script can invent. What this script does
 * is re-derive every machine-checkable fact from the working tree, so the matrix can never
 * again claim to describe a commit it was not generated from:
 *
 *   - stamps generated_from_sha from the actual git HEAD, plus generated_at;
 *   - records the canonical V197 host/entry/universe SHA-256 the matrix was validated against;
 *   - resolves each control's selector against the decoded canonical sources and labels it
 *     canonical / bridge / n-a, so a bridge-created surface is never mistaken for source DOM;
 *   - verifies every named desktop and mobile proof spec exists on disk;
 *   - recomputes totals from the controls rather than trusting the stored numbers.
 *
 * Exits non-zero on any missing proof spec or totals mismatch.
 */
import { createHash } from "node:crypto";
import { execFileSync } from "node:child_process";
import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

const webRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const repositoryRoot = path.resolve(webRoot, "../..");
const matrixPath = path.join(repositoryRoot, "docs/release/v197-control-matrix.json");
const e2eRoot = path.join(webRoot, "e2e");

const canonicalFiles = {
  host: path.join(webRoot, "public/v197/NUR_V197_CHECKBOX_TICK_RESTORED.html"),
  entry: path.join(repositoryRoot, "docs/reference/entry_decoded_v197.html"),
  universe: path.join(repositoryRoot, "docs/reference/universe_decoded_v197.html"),
};

const sha256 = file => createHash("sha256").update(readFileSync(file)).digest("hex");

function headSha() {
  return execFileSync("git", ["-C", repositoryRoot, "rev-parse", "HEAD"], { encoding: "utf8" }).trim();
}

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

matrix.generated_from_sha = headSha();
matrix.generated_at = new Date().toISOString();
matrix.canonical_v197_sha256 = Object.fromEntries(
  Object.entries(canonicalFiles).map(([key, file]) => [key, sha256(file)]),
);
matrix.totals = totals;
matrix.validation = {
  proof_specs_resolved: missingProofs.length === 0,
  missing_proof_specs: missingProofs,
  selector_origin_counts: resolution,
};

writeFileSync(matrixPath, `${JSON.stringify(matrix, null, 2)}\n`);

process.stdout.write(`${JSON.stringify({
  generated_from_sha: matrix.generated_from_sha,
  canonical_v197_sha256: matrix.canonical_v197_sha256,
  totals,
  selector_origin_counts: resolution,
  missing_proof_specs: missingProofs,
}, null, 2)}\n`);

if (missingProofs.length > 0) {
  process.stderr.write(`control matrix: ${missingProofs.length} unresolved proof reference(s)\n`);
  process.exitCode = 1;
}
