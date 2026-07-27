import { execFileSync } from "node:child_process";
import { statSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const output = path.join(root, "docs/completion/CODEX_REPOSITORY_HYGIENE.csv");

const files = execFileSync("git", ["-C", root, "ls-files", "-z"])
  .toString("utf8")
  .split("\0")
  .filter(Boolean)
  .sort();

const archiveNames = new Set([
  "SESSION_LOG.jsonl",
  "STATE.json",
  "PRE_EDIT_GIT_STATE.md",
]);
const binaryExtensions = new Set([
  ".7z", ".avi", ".bin", ".db", ".dump", ".gif", ".gz", ".jpeg", ".jpg",
  ".mov", ".mp3", ".mp4", ".onnx", ".pdf", ".pem", ".pkl", ".png", ".pt",
  ".safetensors", ".sqlite", ".tar", ".webm", ".weights", ".zip",
]);

function classify(file, bytes) {
  const base = path.basename(file);
  const ext = path.extname(file).toLowerCase();

  if (/(^|\/)(node_modules|\.venv|venv|dist|coverage|playwright-report|test-results|\.nur-runtime)(\/|$)/.test(file)) {
    return ["REMOVE_STALE", "generated runtime or dependency material must not be tracked"];
  }
  if (/(^|\/)\.env(\.|$)/.test(file) && !file.endsWith(".env.example") && base !== ".env.example") {
    return ["REMOVE_SECRET_RISK", "environment secret material must never ship"];
  }
  if (/\.(key|p12|pfx)$/i.test(file) || /(^|\/)(private[_-]?key|token-cache)(\/|$)/i.test(file)) {
    return ["REMOVE_SECRET_RISK", "credential-bearing filename is forbidden"];
  }
  if (file.startsWith("proof/")) {
    return bytes <= 512_000
      ? ["KEEP_SMALL_PROOF", "curated bounded visual proof"]
      : ["ARCHIVE_EXTERNAL", "large visual proof belongs outside the durable source tree"];
  }
  if (file.startsWith("evidence/") || file.startsWith("audit-output/")) {
    return ["ARCHIVE_EXTERNAL", "historical run evidence is useful but should not inflate the release tree"];
  }
  if (archiveNames.has(base) || /(^|\/)(BLOCKERS|NEXT_ACTION)\.md$/.test(file)) {
    return ["REMOVE_STALE", "construction-session state is superseded by final completion artifacts"];
  }
  if (binaryExtensions.has(ext) && bytes > 1_000_000) {
    return ["REMOVE_LARGE_BINARY", "large binary is not required to build or run NUR"];
  }
  if (/(^|\/)(__pycache__|\.pytest_cache|\.ruff_cache)(\/|$)/.test(file) || /\.(log|tmp|bak)$/i.test(file)) {
    return ["REMOVE_STALE", "cache log or temporary artifact"];
  }
  if (/(^|\/)(tests?|e2e|fixtures)(\/|$)/.test(file) || /\.(spec|test)\.(ts|tsx|js|jsx|py)$/.test(file)) {
    return ["KEEP_TEST", "executable product or release proof"];
  }
  if (file.startsWith("apps/") || file.startsWith("packages/") || file.startsWith("infra/")
      || file.startsWith(".github/") || file.startsWith("scripts/")
      || /(^|\/)(Dockerfile|compose\.ya?ml|package(-lock)?\.json|pyproject\.toml|requirements\.lock)$/.test(file)
      || ["RUN_NUR.sh", ".gitignore", ".dockerignore"].includes(file)) {
    return ["KEEP_PRODUCT", "runtime source migration configuration or operations code"];
  }
  if (file.startsWith("docs/") || /\.(md|csv|json)$/i.test(file)
      || ["README.md", "SECURITY_NOTES.md", "LICENSE"].includes(file)) {
    return ["KEEP_DURABLE_DOC", "bounded product architecture security or release documentation"];
  }
  return ["KEEP_PRODUCT", "small repository-owned source or configuration"];
}

function csv(value) {
  const text = String(value);
  return /[",\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
}

const rows = files.map(file => {
  const bytes = statSync(path.join(root, file)).size;
  const [classification, reason] = classify(file, bytes);
  const action = classification.startsWith("KEEP_") ? "retain"
    : classification === "ARCHIVE_EXTERNAL" ? "archive then remove from release branch"
      : "remove after recorded review";
  return [file, bytes, classification, reason, action].map(csv).join(",");
});

writeFileSync(
  output,
  [
    "path,bytes,classification,reason,action",
    ...rows,
  ].join("\n") + "\n",
);

const counts = new Map();
for (const row of rows) {
  const classification = row.split(",")[2];
  counts.set(classification, (counts.get(classification) ?? 0) + 1);
}
process.stdout.write(JSON.stringify({
  output: path.relative(root, output),
  tracked_files: files.length,
  classifications: Object.fromEntries([...counts].sort()),
}, null, 2) + "\n");
