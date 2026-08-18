import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

export const V197_HASHES = {
  host: "c4699091db9f1ebc3a6e2076d483a3d41303d3e261ace0111c9411322f7ea3a5",
  entry: "cdeac0c8574333c7261be2bc410357ecc5407ee0dd5b1b8089630f3914026030",
  universe: "1b060c30414dca554c96fadfd50316e0d9c6e13c9ab2b163f8d8c785b07b8fc8",
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
