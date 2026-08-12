import { createHash } from "node:crypto";
import { readFileSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

import { JSDOM, VirtualConsole } from "jsdom";

const webRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const repositoryRoot = path.resolve(webRoot, "../..");
const hostPath = path.join(webRoot, "public/v197/NUR_V197_CHECKBOX_TICK_RESTORED.html");
const referencePaths = {
  entry: path.join(repositoryRoot, "docs/reference/entry_decoded_v197.html"),
  universe: path.join(repositoryRoot, "docs/reference/universe_decoded_v197.html"),
};

const keep = {
  entry: {
    styles: new Set(["nur-app-shell-styles", "nur-v61-neural-rewiring-front"]),
    scripts: new Set(["nur-v61-neural-rewiring-runtime", "nur-v67-popup-close-hardening"]),
  },
  universe: {
    styles: new Set(["nur-v180-canonical-cleaned"]),
    scripts: new Set(["nur-v181-runtime"]),
  },
};

const retiredUniverseSelectors = [
  'section.clean-rail-section[aria-label="Universe tools"]',
  'section.clean-rail-section[aria-label="Universe tools"] + .clean-rule',
  '.universe-top-tools > .universe-search',
  '.universe-top-tools > #deep-research-button',
  '.universe-command-row [data-world-focus="consult"]',
  '.universe-command-row [data-world-focus="research"]',
  '.universe-command-row [data-world-focus="community"]',
  '.universe-state-strip',
  '.universe-lower-grid',
  '.universe-composer-shell',
];

function extract(host, name) {
  const match = host.match(new RegExp(`const ${name} = "([A-Za-z0-9+/=]+)";`));
  if (!match) throw new Error(`Unable to locate ${name}.`);
  return match[1];
}

function replaceConstant(host, name, value) {
  const pattern = new RegExp(`const ${name} = "[A-Za-z0-9+/=]+";`);
  if (!pattern.test(host)) throw new Error(`Unable to replace ${name}.`);
  return host.replace(pattern, `const ${name} = "${value}";`);
}

function prune(source, kind) {
  const virtualConsole = new VirtualConsole();
  const dom = new JSDOM(source, { includeNodeLocations: true, virtualConsole });
  const document = dom.window.document;
  const removed = [];

  for (const node of document.querySelectorAll("style, script")) {
    const tag = node.tagName.toLowerCase();
    const id = node.id;
    const allowed = id
      ? keep[kind][tag === "style" ? "styles" : "scripts"].has(id)
      : true;
    if (allowed) continue;
    const location = dom.nodeLocation(node);
    if (!location) throw new Error(`Missing source location for ${kind}:${tag}#${id}.`);
    removed.push({ start: location.startOffset, end: location.endOffset, label: `${tag}#${id}` });
  }

  if (kind === "universe") {
    for (const selector of retiredUniverseSelectors) {
      for (const node of document.querySelectorAll(selector)) {
        const location = dom.nodeLocation(node);
        if (!location) throw new Error(`Missing source location for retired Universe surface ${selector}.`);
        removed.push({ start: location.startOffset, end: location.endOffset, label: `retired:${selector}` });
      }
    }
  }

  let next = source;
  for (const range of removed.sort((a, b) => b.start - a.start)) {
    next = next.slice(0, range.start) + next.slice(range.end);
  }

  next = next.replace(/#020103/gi, "#000000");

  const validation = new JSDOM(next, { virtualConsole }).window.document;
  for (const id of keep[kind].styles) {
    if (!validation.getElementById(id)) throw new Error(`Required ${kind} style #${id} was removed.`);
  }
  for (const id of keep[kind].scripts) {
    if (!validation.getElementById(id)) throw new Error(`Required ${kind} script #${id} was removed.`);
  }
  const remaining = [...validation.querySelectorAll("style, script")];
  const expected = kind === "entry" ? 6 : 3;
  if (remaining.length !== expected) {
    throw new Error(`${kind} retained ${remaining.length} style/script nodes; expected ${expected}.`);
  }
  if (kind === "universe") {
    for (const selector of retiredUniverseSelectors) {
      if (validation.querySelector(selector)) {
        throw new Error(`Retired Universe surface survived rebuild: ${selector}.`);
      }
    }
    const commands = [...validation.querySelectorAll(".universe-command-row [data-world-focus]")]
      .map(node => node.getAttribute("data-world-focus"));
    if (commands.join(",") !== "universe,insights") {
      throw new Error(`Unexpected Universe commands after rebuild: ${commands.join(",")}.`);
    }
    if (validation.querySelector("#universe-search, #deep-research-button")) {
      throw new Error("Retired web-research controls survived the canonical rebuild.");
    }
  }

  return { source: next, removed: removed.map(item => item.label) };
}

function digest(source) {
  return createHash("sha256").update(source).digest("hex");
}

let host = readFileSync(hostPath, "utf8");
const entry = prune(Buffer.from(extract(host, "ENTRY_SOURCE_B64"), "base64").toString("utf8"), "entry");
const universe = prune(Buffer.from(extract(host, "UNIVERSE_SOURCE_B64"), "base64").toString("utf8"), "universe");

writeFileSync(referencePaths.entry, entry.source);
writeFileSync(referencePaths.universe, universe.source);

host = replaceConstant(host, "ENTRY_SOURCE_B64", Buffer.from(entry.source).toString("base64"));
host = replaceConstant(host, "UNIVERSE_SOURCE_B64", Buffer.from(universe.source).toString("base64"));

const manifestMatch = host.match(/const MANIFEST = Object\.freeze\((\{.*?\})\);/);
if (!manifestMatch) throw new Error("Unable to locate the canonical manifest.");
const manifest = JSON.parse(manifestMatch[1]);
manifest.bundle = "NUR_V197_CLEAN_CONSOLIDATED_ENTRY_TO_UNIVERSE";
manifest.entry.sha256 = digest(entry.source);
manifest.entry.bytes = Buffer.byteLength(entry.source);
manifest.universe.sha256 = digest(universe.source);
manifest.universe.bytes = Buffer.byteLength(universe.source);
manifest.integration.preserved_source_bytes = false;
manifest.integration.cleanup = "obsolete patches and retired consultation, research, community, expert surfaces removed; canonical core retained";
host = host.replace(manifestMatch[0], `const MANIFEST = Object.freeze(${JSON.stringify(manifest)});`);
host = host.replace(/#020103/gi, "#000000");
writeFileSync(hostPath, host);

console.log(JSON.stringify({
  entry: {
    bytes: manifest.entry.bytes,
    sha256: manifest.entry.sha256,
    removed: entry.removed.length,
  },
  universe: {
    bytes: manifest.universe.bytes,
    sha256: manifest.universe.sha256,
    removed: universe.removed.length,
  },
}, null, 2));
