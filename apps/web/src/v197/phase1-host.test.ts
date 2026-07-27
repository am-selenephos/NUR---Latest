import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

const repositoryRoot = resolve(process.cwd(), "../..");
const source = (path: string) => readFileSync(resolve(repositoryRoot, path), "utf8");
const hash = (path: string) => createHash("sha256").update(readFileSync(resolve(repositoryRoot, path))).digest("hex");

describe("V197 cleaned canonical host", () => {
  it("keeps the rebuilt host and decoded documents byte-checked", () => {
    expect(hash("apps/web/public/v197/NUR_V197_CHECKBOX_TICK_RESTORED.html"))
      .toBe("d4f7f2d3e4c8e36dfc0c6edd51a028f28a04afbc2afa434a319009cb2f122bc6");
    expect(hash("docs/reference/entry_decoded_v197.html"))
      .toBe("cdeac0c8574333c7261be2bc410357ecc5407ee0dd5b1b8089630f3914026030");
    expect(hash("docs/reference/universe_decoded_v197.html"))
      .toBe("3cff07b31e8360e5ce793287298d66127c4f278705dc0f8e6abdfbe7e874dc40");
    expect(hash("apps/web/src/bridge/v43StarBrainRuntime.js"))
      .toBe("55fcda001f62073d06002fd48204f8d6740d6528d6e9c73225aa5c96ee0b0b83");
  });

  it("physically removes obsolete visual patch and legacy star runtimes", () => {
    const entry = source("docs/reference/entry_decoded_v197.html");
    const universe = source("docs/reference/universe_decoded_v197.html");

    expect(entry).toContain('id="nur-v61-neural-rewiring-front"');
    expect(entry).toContain('id="nur-v61-neural-rewiring-runtime"');
    expect(entry).not.toMatch(/nur-v(?:3-product|33-master|63-centered|68-unified|196-entry)/);
    expect(universe).toContain('id="nur-v180-canonical-cleaned"');
    expect(universe).toContain('id="nur-v181-runtime"');
    expect(universe).not.toMatch(/nur-v(?:183-master|184-v90|186-exact|196-universe|201-master)/);
  });

  it("uses a zero-visual shell rather than a React presentation root", () => {
    const host = source("apps/web/public/v197/NUR_V197_CHECKBOX_TICK_RESTORED.html");
    const entry = source("apps/web/src/main.ts");
    const viteConfig = source("apps/web/vite.config.ts");

    expect(host).toContain('id="nur-entry-stage"');
    expect(host).toContain('id="nur-universe-stage"');
    expect(host).not.toContain('id="root"');
    expect(host).not.toContain("global.css");
    expect(entry).toContain("bootstrapV197Bridge");
    expect(entry).not.toContain("ReactDOM");
    expect(entry).not.toContain("react-dom");
    expect(viteConfig).toContain("nur-v197-direct-host");
    expect(viteConfig).toContain('src="/assets/v197-bridge.js"');
  });

  it("keeps Phase 1 mutations text-only", () => {
    const mutations = source("apps/web/src/bridge/v197Mutations.ts");
    expect(mutations).not.toMatch(/appendChild|insertAdjacentHTML|innerHTML|classList|\.style\b/);
  });
});
