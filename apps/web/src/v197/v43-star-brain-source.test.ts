import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

const runtimePath = resolve(process.cwd(), "src/bridge/v197CelestialRuntime.ts");
const bridgePath = resolve(process.cwd(), "src/bridge/v197StarBrain.ts");
const runtime = readFileSync(runtimePath, "utf8");
const bridge = readFileSync(bridgePath, "utf8");

describe("V43 anatomical Three.js celestial runtime", () => {
  it("keeps the complete anatomy and guarantees seven visible spectrum bands", () => {
    expect(runtime).toContain('import * as THREE from "three";');
    expect(runtime).toContain('"red",');
    expect(runtime).toContain('"orange",');
    expect(runtime).toContain('"yellow",');
    expect(runtime).toContain('"green",');
    expect(runtime).toContain('"blue",');
    expect(runtime).toContain('"indigo",');
    expect(runtime).toContain('"violet",');
    expect(runtime).toContain('tissue: PointSeed["tissue"]');
    expect(runtime).toContain('"cortex"');
    expect(runtime).toContain('"cerebellum"');
    expect(runtime).toContain('"brainstem"');
    expect(runtime).toContain("const cortexCount = mobile ? 900 : 1320;");
    expect(runtime).toContain("const brainstemCount = mobile ? 120 : 180;");
    expect(runtime).toContain("const dustCount = mobile ? 430 : 760;");
    expect(runtime).toContain("band: index % V197_SPECTRUM_NAMES.length");
    expect(runtime).toContain('brainHost.dataset.nurSpectrumBandCount = String(V197_SPECTRUM_NAMES.length);');
    expect(runtime).toContain('galaxyCanvas.dataset.nurSpectrumBandCount = String(V197_SPECTRUM_NAMES.length);');
  });

  it("uses real perspective, stellar shaders and one coordinated frame owner", () => {
    expect(runtime).toContain("new THREE.WebGLRenderer");
    expect(runtime).toContain("new THREE.PerspectiveCamera");
    expect(runtime).toContain("new THREE.ShaderMaterial");
    expect(runtime).toContain("gl_PointSize");
    expect(runtime).toContain("requestFrame(controller)");
    expect(runtime).toContain("oneRafOwner: true");
    expect(runtime).toContain('brainHost.dataset.nurRenderProfile = "one-raf-two-canonical-canvases-v1";');
    expect(runtime).not.toContain("requestAnimationFrame(frame)");
  });

  it("publishes real interaction, diagnostics and deterministic disposal", () => {
    expect(runtime).toContain('bind(frameWindow, "pointerdown"');
    expect(runtime).toContain("galaxyAngularVelocityYaw");
    expect(runtime).toContain("galaxyAngularVelocityPitch");
    expect(runtime).toContain("galaxyParallaxX");
    expect(runtime).toContain('bind(brainCanvas, "pointerdown"');
    expect(runtime).toContain('bind(brainCanvas, "pointermove"');
    expect(runtime).toContain("brainAngularVelocityYaw");
    expect(runtime).toContain("brainAngularVelocityPitch");
    expect(runtime).toContain('bind(brainCanvas, "wheel"');
    expect(runtime).toContain('bind(brainCanvas, "dblclick"');
    expect(runtime).toContain("getParticleDiagnostics");
    expect(runtime).toContain("getDiagnostics");
    expect(runtime).toContain("function disposeController");
    expect(runtime).toContain("controller.renderer.dispose();");
    expect(runtime).toContain('brainHost.dataset.nurInteractionProfile = "independent-3d-drag-inertia-v1";');
    expect(runtime).toContain('galaxyCanvas.dataset.nurInteractionProfile = "spatial-drag-inertia-parallax-v1";');
    expect(bridge).toContain("export function disposeV197StarBrain");
    expect(bridge).toContain("disposeV197CelestialRuntime(document)");
  });

  it("mounts without the deleted warm-only source injection", () => {
    expect(bridge).toContain('from "./v197CelestialRuntime";');
    expect(bridge).toContain("ensureV197CelestialRuntime(document, brainHost)");
    expect(bridge).toContain('brainHost.dataset.nurDispersal = "radial-circle";');
    expect(bridge).not.toContain("v43StarBrainRuntime.js?raw");
    expect(bridge).not.toContain("script.textContent");
  });
});
