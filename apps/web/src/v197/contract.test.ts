import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import {
  V197_CONTEXT_PANES,
  V197_NAV_ITEMS,
  V197_PROMPT_ACTIONS,
  V197_SOURCE_SHA256,
  V197_SYSTEM_NODES,
  V197_TOOL_ITEMS,
  V197_WORLD_COMMANDS,
  V197_WORLD_TABS,
} from "./contract";

const read = (path: string) => readFileSync(resolve(process.cwd(), path), "utf8");

describe("V197 immutable host contract", () => {
  it("records the canonical V197 source SHA", () => {
    expect(V197_SOURCE_SHA256).toBe("d4f7f2d3e4c8e36dfc0c6edd51a028f28a04afbc2afa434a319009cb2f122bc6");
  });

  it("keeps native V197 control identities in the decoded source", () => {
    const decoded = read("../../docs/reference/universe_decoded_v197.html");
    const parsed = new DOMParser().parseFromString(decoded, "text/html");
    for (const item of V197_NAV_ITEMS) {
      expect(decoded).toContain(`data-page="${item.page}"`);
      expect(decoded).toContain(`<span class="clean-nav-title">${item.title}</span>`);
    }
    expect(V197_TOOL_ITEMS).toHaveLength(0);
    expect(decoded).not.toContain('aria-label="Universe tools"');
    for (const tab of V197_WORLD_TABS) expect(decoded).toContain(`data-world-tab="${tab.focus}"`);
    for (const pane of V197_CONTEXT_PANES) expect(decoded).toContain(`data-context-pane="${pane.key}"`);
    for (const node of V197_SYSTEM_NODES) expect(decoded).toContain(`data-system="${node.name}"`);
    for (const command of V197_WORLD_COMMANDS) expect(decoded).toContain(`data-world-focus="${command.key}"`);
    expect(V197_PROMPT_ACTIONS).toHaveLength(0);
    expect(parsed.querySelector(".universe-composer-shell")).toBeNull();
    expect(parsed.querySelector(".universe-lower-grid")).toBeNull();
    expect(parsed.querySelector("#universe-search, #deep-research-button")).toBeNull();
  });

  it("does not make React the visible V197 renderer", () => {
    const entry = read("src/main.ts");
    const canonical = read("public/v197/NUR_V197_CHECKBOX_TICK_RESTORED.html");
    const viteConfig = read("vite.config.ts");
    const bridge = read("src/bridge/v197Bridge.ts");

    expect(entry).not.toContain("ReactDOM");
    expect(entry).not.toContain("react-dom");
    expect(canonical).toContain('id="nur-entry-stage"');
    expect(canonical).toContain('id="nur-universe-stage"');
    expect(canonical).not.toContain('id="root"');
    expect(canonical).not.toContain("global.css");
    expect(viteConfig).toContain("composedV197Document");
    expect(bridge).toContain("hydrateTrackAV197");
    expect(bridge).not.toContain("ReactDOM");
  });
});
