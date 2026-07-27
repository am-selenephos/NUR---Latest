#!/usr/bin/env node
/**
 * Fails when disposable run evidence is committed.
 *
 * PR #8 reached 179.8 MB of tracked proof — 139 MB of PNG, 27.3 MB of it a
 * single Chromium performance trace — which made review impractical and every
 * clone expensive. Screenshots, videos and traces regenerate on demand and are
 * meaningless once the SHA moves, so they belong in Actions artifacts.
 * Compact summaries a human actually reads stay in the repository.
 */
import { execFileSync } from "node:child_process";
import { statSync } from "node:fs";

const MAX_SINGLE_FILE = 1_200_000;   // ordinary tracked evidence
const MAX_REVIEW_FILE = 2_600_000;   // a full-resolution founder-review capture

/*
 * Founder visual acceptance requires full-resolution captures of the running
 * interface, which a 1.2 MB cap cannot hold. These specific files have an
 * explicit retention purpose — they are what the founder reviews to accept or
 * reject the visual gate — so they get a higher ceiling. Everything else stays
 * at the ordinary limit; this is a named allowlist, not a relaxed rule.
 */
const FOUNDER_REVIEW = new Set([
  "proof/visual-acceptance/01-entry.png",
  "proof/visual-acceptance/02-today.png",
  "proof/visual-acceptance/03-talk.png",
  "proof/visual-acceptance/04-systems.png",
]);
const MAX_TOTAL_PROOF = 8_000_000;   // the whole reviewable evidence surface
const BANNED = /\.(webm|mp4|zip|trace)$|(^|\/)(test-results|playwright-report|videos?)\//i;

const tracked = execFileSync("git", ["ls-files", "proof"], { encoding: "utf8" })
  .split("\n").filter(Boolean);

const problems = [];
let total = 0;

for (const file of tracked) {
  let size = 0;
  try { size = statSync(file).size; } catch { continue; }
  total += size;
  if (BANNED.test(file)) {
    problems.push(`disposable artifact committed: ${file}`);
  } else {
    const cap = FOUNDER_REVIEW.has(file) ? MAX_REVIEW_FILE : MAX_SINGLE_FILE;
    if (size > cap) {
      problems.push(
        `oversized (${(size / 1048576).toFixed(1)} MB, cap ` +
        `${(cap / 1048576).toFixed(1)} MB): ${file}`,
      );
    }
  }
}

if (total > MAX_TOTAL_PROOF) {
  problems.push(
    `tracked proof is ${(total / 1048576).toFixed(1)} MB, over the ` +
    `${(MAX_TOTAL_PROOF / 1048576).toFixed(0)} MB budget`,
  );
}

if (problems.length) {
  console.error("proof-hygiene: FAIL");
  for (const p of problems) console.error(`  - ${p}`);
  console.error("\nPublish run output as a GitHub Actions artifact instead of committing it.");
  process.exit(1);
}

console.log(
  `proof-hygiene: PASS — ${tracked.length} tracked files, ` +
  `${(total / 1048576).toFixed(1)} MB, no disposable artifacts.`,
);
