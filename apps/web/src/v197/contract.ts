export const V197_SOURCE_SHA256 =
  "c4699091db9f1ebc3a6e2076d483a3d41303d3e261ace0111c9411322f7ea3a5";

export const V197_NAV_ITEMS = [
  { page: "today", path: "/today", glyph: "◍", title: "Today", note: "land" },
  { page: "talk", path: "/talk", glyph: "◌", title: "Talk", note: "ask NUR" },
  { page: "journal", path: "/journal", glyph: "✧", title: "Journal", note: "keep" },
  { page: "plan", path: "/plan", glyph: "→", title: "Plan", note: "move" },
  { page: "systems", path: "/systems", glyph: "✣", title: "Systems", note: "together" },
] as const;

export const V197_TOOL_ITEMS = [] as const;

export const V197_WORLD_TABS = [
  { focus: "universe", path: "/universe", glyph: "✦", label: "Universe" },
  { focus: "map", path: "/universe/map", glyph: "◌", label: "Map" },
  { focus: "orbits", path: "/universe/orbits", glyph: "◎", label: "Orbits" },
  { focus: "timeline", path: "/universe/timeline", glyph: "◫", label: "Timeline" },
  { focus: "insights", path: "/universe/insights", glyph: "⌁", label: "Insights" },
] as const;

export const V197_CONTEXT_PANES = [
  { key: "boundary", label: "Boundary" },
  { key: "continuity", label: "Continuity" },
  { key: "glows", label: "Glows" },
] as const;

export const V197_SYSTEM_NODES = [
  { key: "quiet", glyph: "✦", name: "Quiet Ambition", tag: "Build without noise", lensTag: "Build without noise", x: "30%", y: "21%" },
  { key: "public", glyph: "⌁", name: "Public Resonance", tag: "Be seen. Be clear.", lensTag: "System voice", x: "22%", y: "47%" },
  { key: "wealth", glyph: "✣", name: "Wealth Architecture", tag: "Build freedom on purpose", lensTag: "Freedom by design", x: "31%", y: "78%" },
  { key: "embodied", glyph: "◌", name: "Embodied Edge", tag: "Power in your presence", lensTag: "Power in presence", x: "84%", y: "24%" },
  { key: "relational", glyph: "♡", name: "Relational Gravity", tag: "Meet without shrinking", lensTag: "Meet without shrinking", x: "84%", y: "58%" },
  { key: "social", glyph: "◈", name: "Social Constellation", tag: "Belong. Contribute. Co-create.", lensTag: "Belong. Contribute. Co-create.", x: "75%", y: "79%" },
  { key: "neural", glyph: "✧", name: "Neural Upgrade", tag: "Rewire. Reframe. Become.", lensTag: "Rewire the route", x: "55%", y: "84%" },
] as const;

export const V197_WORLD_COMMANDS = [
  { key: "universe", glyph: "✦", label: "Live universe" },
  { key: "insights", glyph: "✧", label: "Candidate insights" },
] as const;

export const V197_PROMPT_ACTIONS = [] as const;
