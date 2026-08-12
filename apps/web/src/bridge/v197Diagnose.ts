/**
 * On-screen galaxy diagnostic, opt-in via `?nur-diagnose=1`.
 *
 * The star field renders on every browser configuration reachable from this
 * machine — default flags, forced GPU, disabled GPU, device scale factors from
 * 1 to 2.5, viewports from 360x640 to 4K, with and without a service worker —
 * and does not render on the founder's screen. Five hypotheses were tested and
 * all five were wrong, so the next step cannot be another guess made here. It
 * has to be data from the machine where it actually fails.
 *
 * This panel reads the live canvas and prints what it finds, with a copy button,
 * so one screenshot or paste settles which of the remaining cases it is:
 *
 *   litPixels 0            the runtime is not painting there; the loop is the
 *                          problem, not CSS
 *   litPixels > 0, unseen  it paints and something hides it; read `coveredBy`,
 *                          `opacity`, `zIndex`, `filter`
 *   backing != css x dpr   a sizing bug under that display's scaling
 *   canvas missing         the stage never mounted
 *
 * Nothing renders unless the parameter is present, so this cannot affect a
 * normal load.
 */

const PARAM = "nur-diagnose";
const PANEL_ID = "nur-diagnostic-panel";

type Probe = Record<string, unknown>;

function probeGalaxy(doc: Document): Probe {
  const view = doc.defaultView;
  const canvas = doc.querySelector<HTMLCanvasElement>("#space3d");
  if (!canvas || !view) return { stage: doc === document ? "host" : "frame", canvas: "MISSING" };

  const rect = canvas.getBoundingClientRect();
  const style = view.getComputedStyle(canvas);

  let litPixels: number | string = 0;
  let maxLuminance = 0;
  try {
    const context = canvas.getContext("2d", { willReadFrequently: true });
    if (!context) {
      litPixels = "NO 2D CONTEXT";
    } else {
      const w = Math.min(canvas.width, 900);
      const h = Math.min(canvas.height, 600);
      const data = context.getImageData(0, 0, w, h).data;
      let lit = 0;
      for (let i = 0; i < data.length; i += 4) {
        const luminance = 0.2126 * data[i] + 0.7152 * data[i + 1] + 0.0722 * data[i + 2];
        if (luminance > 10) lit += 1;
        if (luminance > maxLuminance) maxLuminance = luminance;
      }
      litPixels = lit;
    }
  } catch (error) {
    litPixels = `READBACK FAILED: ${String(error).slice(0, 60)}`;
  }

  // What is actually on top of the canvas at a point the field should occupy?
  let coveredBy = "n/a";
  try {
    const hit = doc.elementFromPoint(view.innerWidth / 2, view.innerHeight / 3);
    coveredBy = hit ? `${hit.tagName}.${String(hit.className).split(" ")[0]}` : "nothing";
  } catch { /* cross-document hit test can throw */ }

  const galaxy = (view as unknown as { __nurGalaxy?: Record<string, () => unknown> }).__nurGalaxy
    ?? (view as unknown as { nurGalaxy?: Record<string, () => unknown> }).nurGalaxy;
  const diagnostics = typeof galaxy?.getParticleDiagnostics === "function"
    ? galaxy.getParticleDiagnostics() as Record<string, unknown>
    : null;

  return {
    devicePixelRatio: view.devicePixelRatio,
    browserZoom: +(view.outerWidth / view.innerWidth).toFixed(2),
    viewport: [view.innerWidth, view.innerHeight],
    backingStore: [canvas.width, canvas.height],
    cssBox: [Math.round(rect.width), Math.round(rect.height)],
    canvasAt: [Math.round(rect.x), Math.round(rect.y)],
    backingOverCss: rect.width ? +(canvas.width / rect.width).toFixed(3) : null,
    litPixels,
    maxLuminance: Math.round(maxLuminance),
    opacity: style.opacity,
    display: style.display,
    visibility: style.visibility,
    zIndex: style.zIndex,
    position: style.position,
    transform: style.transform === "none" ? "none" : style.transform.slice(0, 40),
    filter: style.filter === "none" ? "none" : style.filter.slice(0, 40),
    mixBlendMode: style.mixBlendMode,
    coveredBy,
    particles: diagnostics?.total ?? null,
    byKind: diagnostics?.byKind ?? null,
    shouldRender: diagnostics?.shouldRender ?? null,
    frameScheduled: diagnostics?.frameScheduled ?? null,
  };
}

function collect(): Probe {
  const report: Probe = {
    generatedAt: new Date().toISOString(),
    href: location.href,
    userAgent: navigator.userAgent,
    hardwareConcurrency: navigator.hardwareConcurrency,
    reducedMotion: matchMedia("(prefers-reduced-motion: reduce)").matches,
    serviceWorkerControlled: Boolean(navigator.serviceWorker?.controller),
    runtimeProfile: document.documentElement.dataset.nurRuntimeProfile ?? null,
    runtimeProfileError: document.documentElement.dataset.nurRuntimeProfileError ?? null,
  };

  for (const id of ["nur-entry-stage", "nur-universe-stage"]) {
    const frame = document.querySelector<HTMLIFrameElement>(`#${id}`);
    if (!frame) { report[id] = "STAGE NOT PRESENT"; continue; }
    const rect = frame.getBoundingClientRect();
    const style = getComputedStyle(frame);
    let inner: Probe | string;
    try {
      const doc = frame.contentDocument;
      inner = doc ? probeGalaxy(doc) : "NO CONTENT DOCUMENT";
    } catch (error) {
      inner = `FRAME UNREADABLE: ${String(error).slice(0, 60)}`;
    }
    report[id] = {
      stageBox: [Math.round(rect.width), Math.round(rect.height)],
      stageClass: frame.className,
      stageOpacity: style.opacity,
      stageDisplay: style.display,
      stageVisibility: style.visibility,
      ariaHidden: frame.getAttribute("aria-hidden"),
      galaxy: inner,
    };
  }
  return report;
}

export function installV197Diagnostics(): void {
  if (!new URLSearchParams(location.search).has(PARAM)) return;
  if (document.getElementById(PANEL_ID)) return;

  document.title = `NUR DIAG RM:${matchMedia("(prefers-reduced-motion: reduce)").matches ? "1" : "0"}`;
  const panel = document.createElement("div");
  panel.id = PANEL_ID;
  panel.setAttribute("role", "region");
  panel.setAttribute("aria-label", "NUR galaxy diagnostics");
  panel.style.cssText = [
    "position:fixed", "inset:auto 12px 12px auto", "width:min(560px,92vw)",
    "max-height:76vh", "overflow:auto", "z-index:2147483647",
    "background:rgba(6,6,9,.96)", "color:#ffe9c0",
    "font:12px/1.45 ui-monospace,SFMono-Regular,Menlo,monospace",
    "border:1px solid rgba(255,214,138,.34)", "border-radius:12px",
    "padding:12px 14px", "box-shadow:0 18px 50px rgba(0,0,0,.7)",
    "white-space:pre-wrap", "word-break:break-word",
  ].join(";");

  const render = () => {
    const report = collect();
    const universe = report["nur-universe-stage"] as {
      galaxy?: { litPixels?: unknown; shouldRender?: unknown; frameScheduled?: unknown };
    } | undefined;
    const galaxy = universe?.galaxy;
    document.title = [
      `NUR P:${String(report.runtimeProfile ?? "?")}`,
      `E:${String(report.runtimeProfileError ?? "-")}`,
      `RM:${report.reducedMotion ? "1" : "0"}`,
      `L:${String(galaxy?.litPixels ?? "?")}`,
      `R:${String(galaxy?.shouldRender ?? "?")}`,
      `F:${String(galaxy?.frameScheduled ?? "?")}`,
    ].join(" ");
    const text = JSON.stringify(report, null, 2);
    panel.textContent = "";
    const bar = document.createElement("div");
    bar.style.cssText = "display:flex;gap:8px;margin-bottom:8px";
    const copy = document.createElement("button");
    copy.textContent = "Copy report";
    const again = document.createElement("button");
    again.textContent = "Re-read";
    for (const button of [copy, again]) {
      button.style.cssText = "font:inherit;color:#0c0a06;background:#f6d98e;border:0;"
        + "border-radius:999px;padding:5px 12px;cursor:pointer";
    }
    copy.addEventListener("click", () => {
      void navigator.clipboard.writeText(text)
        .then(() => { copy.textContent = "Copied"; })
        .catch(() => { copy.textContent = "Select and copy manually"; });
    });
    again.addEventListener("click", render);
    bar.append(copy, again);
    const body = document.createElement("pre");
    body.style.cssText = "margin:0;white-space:pre-wrap";
    body.textContent = text;
    panel.append(bar, body);
  };

  // Let the stages mount and the galaxy seed before the first read.
  const start = () => window.setTimeout(render, 6000);
  if (document.readyState === "complete") start();
  else window.addEventListener("load", start, { once: true });
}
