import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

export const V197_HASHES = {
  host: "397c302579472e60f5bd667546a96b6e3f262aa40bd932d10c1946e13b046dd2",
  entry: "cdeac0c8574333c7261be2bc410357ecc5407ee0dd5b1b8089630f3914026030",
  universe: "f83ebff9b6cb8abfc0e8e75af3e2ac45d68a0b018505c7157ae6b5df82bb04dc",
} as const;

export type V197IntegrityResult = {
  pass: boolean;
  files: Record<keyof typeof V197_HASHES, { path: string; expected: string; actual: string; pass: boolean }>;
};

function hash(path: string): string {
  return createHash("sha256").update(readFileSync(path)).digest("hex");
}

export function checkV197Integrity(repositoryRoot = process.cwd()): V197IntegrityResult {
  const files = {
    host: resolve(repositoryRoot, "apps/web/public/v197/NUR_V197_CHECKBOX_TICK_RESTORED.html"),
    entry: resolve(repositoryRoot, "docs/reference/entry_decoded_v197.html"),
    universe: resolve(repositoryRoot, "docs/reference/universe_decoded_v197.html"),
  } as const;
  const result = Object.fromEntries(
    Object.entries(files).map(([key, path]) => {
      const expected = V197_HASHES[key as keyof typeof V197_HASHES];
      const actual = hash(path);
      return [key, { path, expected, actual, pass: expected === actual }];
    }),
  ) as V197IntegrityResult["files"];
  return { files: result, pass: Object.values(result).every(file => file.pass) };
}

// Keep this CLI guard CommonJS-compatible: the integrity launcher compiles this
// isolated verifier without inheriting the web package's ESM package boundary.
if (process.argv[1]?.endsWith("check-v197-integrity.js") || process.argv[1]?.endsWith("check-v197-integrity.ts")) {
  const result = checkV197Integrity();
  process.stdout.write(`${JSON.stringify(result, null, 2)}\n`);
  if (!result.pass) process.exitCode = 1;
}
