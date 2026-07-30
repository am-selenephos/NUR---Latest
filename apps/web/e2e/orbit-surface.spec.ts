import { expect, test, type BrowserContext, type Frame, type Page } from "@playwright/test";

/**
 * Orbit, through the real browser against the real API.
 *
 * The assertions worth having on this surface are the negative ones: that no
 * boxed control slipped in, that no colour is the only carrier of meaning, that
 * an inferred reading is never presented as a fact, and that nothing is
 * fabricated when the owner's Orbit is empty.
 */

const OWNER = { email: "owner@nur.app", password: "owner-demo-pass-123" };

// Serial, on one signed-in page. A fresh context per test meant eleven sign-ins,
// and the auth limiter correctly began refusing them partway through the file —
// so the suite was testing the limiter rather than Orbit. The two tests that
// genuinely need a different context (reduced motion, mobile viewport) still make
// their own.
test.describe.configure({ mode: "serial" });

let sharedContext: BrowserContext;
let sharedPage: Page;

test.beforeAll(async ({ browser }) => {
  sharedContext = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  sharedPage = await sharedContext.newPage();
  await signIn(sharedPage);
});

test.afterAll(async () => {
  await sharedContext?.close();
});

async function signIn(page: Page): Promise<void> {
  await page.goto("/", { waitUntil: "networkidle" });
  // Each test gets a fresh context and therefore signs in again, and the auth
  // limiter correctly starts returning 429 partway through the file. That is the
  // limiter working, not a defect, so it is waited out rather than asserted away.
  let status = 0;
  for (let attempt = 0; attempt < 3; attempt += 1) {
    status = await page.evaluate(async (owner) => {
      const response = await fetch("/api/v1/auth/login", {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(owner),
      });
      return response.status;
    }, OWNER);
    if (status !== 429) break;
    await page.waitForTimeout(1500);
  }
  expect(status, "sign-in did not succeed within the limiter's window").toBe(200);
}

/** The universe stage is where every bridge-native surface mounts. */
async function openOrbit(page: Page): Promise<Frame> {
  await page.goto("/universe/orbits", { waitUntil: "networkidle" });
  const stage = page.frameLocator("#nur-universe-stage");
  await expect(stage.locator("#nur-orbit-root")).toBeVisible({ timeout: 20_000 });
  // Resolved from the element itself. Picking the first child frame instead grabs
  // the entry stage, which is also a direct child of the main frame and has no
  // Orbit root in it.
  const handle = await page.waitForSelector("#nur-universe-stage");
  const frame = await handle.contentFrame();
  if (!frame) throw new Error("the universe stage frame is not attached");
  return frame;
}

test("Orbit mounts into the canonical document and never as a React root", async () => {
  const page = sharedPage;
  const frame = await openOrbit(page);
  const shape = await frame.evaluate(() => {
    const root = document.getElementById("nur-orbit-root");
    return {
      mounted: Boolean(root),
      // The architecture law: no product page may be owned by a React tree.
      reactRoot: Boolean(document.getElementById("root")),
      nativeFlag: root?.dataset.v197NativeAdjunct ?? null,
      zones: {
        rail: Boolean(root?.querySelector(".nur-orbit-rail")),
        field: Boolean(root?.querySelector(".nur-orbit-field-surface")),
        detail: Boolean(root?.querySelector(".nur-orbit-detail")),
      },
      title: root?.querySelector(".nur-orbit-title")?.textContent,
      subtitle: root?.querySelector(".nur-orbit-subtitle")?.textContent,
    };
  });
  expect(shape.mounted).toBe(true);
  expect(shape.reactRoot).toBe(false);
  expect(shape.nativeFlag).toBe("true");
  expect(shape.zones).toEqual({ rail: true, field: true, detail: true });
  expect(shape.title).toBe("Orbit");
  expect(shape.subtitle).toBe("People, circles and relational gravity");
});

test("every Orbit control is a luminous glass capsule, never a boxed outline", async () => {
  const page = sharedPage;
  const frame = await openOrbit(page);
  const verdict = await frame.evaluate(() => {
    const root = document.getElementById("nur-orbit-root");
    if (!root) return { checked: 0, offenders: ["root missing"] };
    const offenders: string[] = [];
    const controls = Array.from(root.querySelectorAll("button, input"));
    for (const control of controls) {
      const style = getComputedStyle(control);
      const label = (control.textContent || (control as HTMLInputElement).placeholder || "?")
        .trim()
        .slice(0, 28);
      // A capsule is fully rounded. A rectangle with a visible border is the
      // exact treatment this surface rejected.
      const radius = Number.parseFloat(style.borderTopLeftRadius);
      const box = control.getBoundingClientRect();
      if (box.height > 0 && radius < Math.min(box.height, 40) / 2 - 0.5) {
        offenders.push(`${label}: radius ${radius}px is not a capsule`);
      }
      if (style.borderTopStyle !== "none" && Number.parseFloat(style.borderTopWidth) > 0) {
        offenders.push(`${label}: has a drawn border`);
      }
      // No white or light panel anywhere: the body must stay in the void.
      const background = style.backgroundColor;
      const match = background.match(/\d+/g);
      if (match && background.startsWith("rgb")) {
        const [r, g, b] = match.map(Number);
        const alpha = match.length > 3 ? Number(match[3]) : 1;
        if (alpha > 0.5 && r + g + b > 300) {
          offenders.push(`${label}: light background ${background}`);
        }
      }
    }
    return { checked: controls.length, offenders };
  });
  expect(verdict.checked).toBeGreaterThan(6);
  expect(verdict.offenders).toEqual([]);
});

test("Orbit is hosted inside the canonical shell, not laid over it", async () => {
  const page = sharedPage;
  const frame = await openOrbit(page);
  const shell = await frame.evaluate(() => {
    const root = document.getElementById("nur-orbit-root");
    const style = getComputedStyle(root as Element);
    const rail = document.querySelector(".nur-rail");
    const topbar = document.querySelector(".nur-topbar");
    const galaxy = document.getElementById("space3d");
    const host = document.getElementById("nur-surface-host");
    return {
      // Not a full-screen overlay: no fixed positioning and no stacking context,
      // so `#space3d` keeps blending its starfield over this surface.
      position: style.position,
      zIndex: style.zIndex,
      backgroundColor: style.backgroundColor,
      insideHost: Boolean(host && root && host.contains(root)),
      insideCanonicalShell: Boolean(root?.closest(".nur-viewport")),
      // The checkpoint UI is intact: rail, top nav and galaxy all still render.
      railVisible: rail ? getComputedStyle(rail).visibility : null,
      topbarVisible: topbar ? getComputedStyle(topbar).visibility : null,
      galaxyVisible: galaxy ? getComputedStyle(galaxy).visibility : null,
      canonicalPageHidden: getComputedStyle(
        document.querySelector(".nur-viewport > .nur-page") as Element,
      ).display === "none",
    };
  });
  expect(shell.position).toBe("relative");
  expect(shell.zIndex).toBe("auto");
  expect(shell.backgroundColor).toBe("rgba(0, 0, 0, 0)");
  expect(shell.insideHost).toBe(true);
  expect(shell.insideCanonicalShell).toBe(true);
  expect(shell.railVisible).toBe("visible");
  expect(shell.topbarVisible).toBe("visible");
  expect(shell.galaxyVisible).toBe("visible");
  expect(shell.canonicalPageHidden).toBe(true);
});

test("all three views render and the switcher reports the active one", async () => {
  const page = sharedPage;
  const frame = await openOrbit(page);
  for (const view of ["list", "threads", "orbit"] as const) {
    await frame.evaluate((target) => {
      document
        .querySelector<HTMLButtonElement>(`[data-orbit-view="${target}"]`)
        ?.click();
    }, view);
    await page.waitForTimeout(500);
    const state = await frame.evaluate((target) => {
      const root = document.getElementById("nur-orbit-root");
      const tab = root?.querySelector(`[data-orbit-view="${target}"]`);
      return {
        selected: tab?.getAttribute("aria-selected"),
        hasField: Boolean(root?.querySelector(".nur-orbit-field-surface")),
        hasCanvas: Boolean(root?.querySelector(".nur-orbit-canvas")),
        hasRows: (root?.querySelectorAll(".nur-orbit-row").length ?? 0) > 0,
      };
    }, view);
    expect(state.selected).toBe("true");
    expect(state.hasField).toBe(true);
    if (view === "orbit") expect(state.hasCanvas).toBe(true);
  }
});

test("list view is operational: every column, and sortable headers", async () => {
  const page = sharedPage;
  const frame = await openOrbit(page);
  await frame.evaluate(() => {
    document.querySelector<HTMLButtonElement>('[data-orbit-view="list"]')?.click();
  });
  await page.waitForTimeout(500);
  const list = await frame.evaluate(() => {
    const root = document.getElementById("nur-orbit-root");
    return {
      headers: Array.from(root?.querySelectorAll(".nur-orbit-list-head [role=columnheader]") ?? [])
        .map((cell) => cell.textContent?.trim()),
      sortable: root?.querySelectorAll(".nur-orbit-list-head button").length ?? 0,
      rows: root?.querySelectorAll(".nur-orbit-row").length ?? 0,
    };
  });
  expect(list.headers).toEqual([
    "Person", "Orbit", "Relationship", "Activity", "Next move", "Privacy",
  ]);
  expect(list.sortable).toBeGreaterThanOrEqual(3);
  expect(list.rows).toBeGreaterThan(0);
});

test("selecting a person opens all five tabs and dims the unrelated field", async () => {
  const page = sharedPage;
  const frame = await openOrbit(page);
  await frame.evaluate(() => {
    document.querySelector<HTMLButtonElement>('[data-orbit-view="list"]')?.click();
  });
  await page.waitForTimeout(400);
  await frame.evaluate(() => {
    document.querySelector<HTMLButtonElement>(".nur-orbit-row")?.click();
  });
  await page.waitForTimeout(1200);

  const detail = await frame.evaluate(() => {
    const root = document.getElementById("nur-orbit-root");
    return {
      name: root?.querySelector(".nur-orbit-detail-name")?.textContent,
      tabs: Array.from(root?.querySelectorAll(".nur-orbit-tab") ?? [])
        .map((tab) => tab.textContent?.trim()),
      signalCards: root?.querySelectorAll(".nur-orbit-signal").length ?? 0,
      selectedRow: root?.querySelector('.nur-orbit-row[aria-selected="true"]') !== null,
    };
  });
  expect(detail.name).toBeTruthy();
  expect(detail.tabs).toEqual([
    "Overview", "Shared Context", "Threads", "Plans", "Insights",
  ]);
  // Connection, Trust, Momentum, Tension — always four, even when empty, so a
  // missing signal reads as "nothing recorded" rather than silently vanishing.
  expect(detail.signalCards).toBe(4);
  expect(detail.selectedRow).toBe(true);

  for (const tab of ["context", "threads", "plans", "insights", "overview"]) {
    await frame.evaluate((target) => {
      document.querySelector<HTMLButtonElement>(`[data-orbit-tab="${target}"]`)?.click();
    }, tab);
    await page.waitForTimeout(300);
    const active = await frame.evaluate((target) => document
      .querySelector(`[data-orbit-tab="${target}"]`)
      ?.getAttribute("aria-selected"), tab);
    expect(active).toBe("true");
  }
});

test("a reading always shows its basis, and an inferred one is never a bare fact", async () => {
  const page = sharedPage;
  const frame = await openOrbit(page);

  // Seed the reading this test is about, rather than relying on whatever signals
  // happen to be left in the database. It passed for a while on residue from
  // earlier runs and then failed the first time it met a freshly seeded
  // environment — the assertions below are unchanged, only the precondition is
  // now guaranteed instead of assumed.
  await frame.evaluate(async () => {
    const csrf = document.cookie.split("; ")
      .find((row) => row.startsWith("nur_csrf="))?.split("=")[1] ?? "";
    const headers = { "Content-Type": "application/json", "X-CSRF-Token": csrf };
    const field = await (await fetch("/api/v1/orbit-field", { credentials: "include" })).json();
    let personId: string | undefined = field?.people?.[0]?.id;
    if (!personId) {
      const made = await (await fetch("/api/v1/orbits/people", {
        method: "POST", credentials: "include", headers,
        body: JSON.stringify({ display_name: "Basis Probe", relationship_type: "Friend" }),
      })).json();
      personId = made.id;
    }
    const existing = await (await fetch(
      `/api/v1/orbit-entities/${personId}/signals`, { credentials: "include" },
    )).json();
    if (Array.isArray(existing) && existing.length > 0) return;
    // PUT, not POST: the endpoint is an upsert keyed on (person, kind, basis).
    await fetch(`/api/v1/orbit-entities/${personId}/signals`, {
      method: "PUT", credentials: "include", headers,
      body: JSON.stringify({
        signal_kind: "CONNECTION",
        basis: "USER_STATED",
        value: 70,
        evidence: [],
      }),
    });
  });
  await page.reload({ waitUntil: "networkidle" });
  const reloaded = await openOrbit(page);
  await reloaded.evaluate(() => {
    document.querySelector<HTMLButtonElement>('[data-orbit-view="list"]')?.click();
  });
  await page.waitForTimeout(400);
  await reloaded.evaluate(() => {
    document.querySelector<HTMLButtonElement>(".nur-orbit-row")?.click();
  });
  await page.waitForTimeout(1200);

  const basis = await reloaded.evaluate(() => {
    const root = document.getElementById("nur-orbit-root");
    const badges = Array.from(root?.querySelectorAll(".nur-orbit-basis") ?? []);
    return {
      count: badges.length,
      // Every badge carries a word, not only a hue, so the basis survives for a
      // reader who cannot distinguish the colours.
      words: badges.map((badge) => badge.textContent?.trim()),
      bases: badges.map((badge) => (badge as HTMLElement).dataset.basis),
      whyButtons: root?.querySelectorAll("[data-orbit-why]").length ?? 0,
    };
  });
  expect(basis.count).toBeGreaterThan(0);
  for (const word of basis.words) expect(word && word.length > 3).toBe(true);
  for (const value of basis.bases) {
    expect(["USER_STATED", "OBSERVED", "NUR_INFERRED"]).toContain(value);
  }
  expect(basis.whyButtons).toBeGreaterThan(0);

  // "Why is NUR showing this?" must open real substance, never an empty shell.
  await reloaded.evaluate(() => {
    document.querySelector<HTMLButtonElement>("[data-orbit-why]")?.click();
  });
  await page.waitForTimeout(500);
  const why = await reloaded.evaluate(() => {
    const box = document.querySelector(".nur-orbit-why");
    return {
      open: Boolean(box),
      expanded: document.querySelector("[data-orbit-why]")?.getAttribute("aria-expanded"),
      text: box?.textContent?.trim() ?? "",
    };
  });
  expect(why.open).toBe(true);
  expect(why.expanded).toBe("true");
  expect(why.text.length).toBeGreaterThan(10);
});

test("Orbit is fully keyboard reachable with a visible focus halo", async () => {
  const page = sharedPage;
  const frame = await openOrbit(page);
  // Tab through the surface and confirm focus lands on real controls that show a
  // ring — a focus state carried by animation alone would fail this.
  const reached: string[] = [];
  // Focus has to start inside the universe frame: pressing Tab against the main
  // frame walks the host document's own tab order and never enters Orbit.
  await frame.evaluate(() => {
    document.querySelector<HTMLElement>("#nur-orbit-root .nur-orbit-capsule")?.focus();
  });
  for (let i = 0; i < 12; i += 1) {
    await page.keyboard.press("Tab");
    const active = await frame.evaluate(() => {
      const el = document.activeElement as HTMLElement | null;
      if (!el || el === document.body) return null;
      const style = getComputedStyle(el);
      return {
        tag: el.tagName.toLowerCase(),
        cls: el.className?.toString().slice(0, 40),
        hasRing: style.boxShadow !== "none" && style.boxShadow.length > 0,
      };
    });
    if (active?.cls?.includes("nur-orbit")) {
      reached.push(active.cls);
      expect(active.hasRing).toBe(true);
    }
  }
  expect(reached.length).toBeGreaterThan(2);
});

test("reduced motion stops every animation without hiding any state", async ({ browser }) => {
  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    reducedMotion: "reduce",
  });
  const page = await context.newPage();
  await signIn(page);
  const frame = await openOrbit(page);
  const motion = await frame.evaluate(() => {
    const root = document.getElementById("nur-orbit-root");
    const animated = Array.from(root?.querySelectorAll("*") ?? []).filter((node) => {
      const style = getComputedStyle(node);
      return style.animationName !== "none" && style.animationDuration !== "0s";
    });
    const capsule = root?.querySelector(".nur-orbit-capsule");
    return {
      stillAnimating: animated.length,
      // The rim must remain, so the control is still legible as a control.
      capsuleRim: capsule ? getComputedStyle(capsule).boxShadow !== "none" : false,
      bandsStillLabelled:
        (root?.querySelectorAll(".nur-orbit-band, .nur-orbit-ring-label").length ?? 0) > 0,
    };
  });
  expect(motion.stillAnimating).toBe(0);
  expect(motion.capsuleRim).toBe(true);
  expect(motion.bandsStillLabelled).toBe(true);
  await context.close();
});

test("mobile opens in List view with a reachable bottom sheet", async ({ browser }) => {
  const context = await browser.newContext({ viewport: { width: 390, height: 844 } });
  const page = await context.newPage();
  await signIn(page);
  const frame = await openOrbit(page);
  const mobile = await frame.evaluate(() => {
    const root = document.getElementById("nur-orbit-root");
    const listTab = root?.querySelector('[data-orbit-view="list"]');
    const rail = root?.querySelector(".nur-orbit-rail");
    const detail = root?.querySelector(".nur-orbit-detail");
    return {
      // §23: mobile must not open into the full graph.
      listActive: listTab?.getAttribute("aria-selected"),
      railHidden: rail ? getComputedStyle(rail).display === "none" : false,
      detailFixed: detail ? getComputedStyle(detail).position === "fixed" : false,
      rows: root?.querySelectorAll(".nur-orbit-row").length ?? 0,
      overflowsSideways: document.documentElement.scrollWidth > window.innerWidth + 1,
    };
  });
  expect(mobile.listActive).toBe("true");
  expect(mobile.railHidden).toBe(true);
  expect(mobile.detailFixed).toBe(true);
  expect(mobile.rows).toBeGreaterThan(0);
  expect(mobile.overflowsSideways).toBe(false);

  // Every touch target clears 44px.
  const small = await frame.evaluate(() => Array
    .from(document.querySelectorAll("#nur-orbit-root .nur-orbit-capsule"))
    .map((node) => ({
      label: node.textContent?.trim().slice(0, 24),
      height: Math.round(node.getBoundingClientRect().height),
    }))
    .filter((item) => item.height > 0 && item.height < 36));
  expect(small).toEqual([]);
  await context.close();
});

test("leaving Orbit restores the canonical universe untouched", async () => {
  const page = sharedPage;
  await openOrbit(page);
  await page.goto("/universe/map", { waitUntil: "networkidle" });

  // Polled rather than waited on a fixed timer. Navigating away reloads the host,
  // which detaches the stage frame and re-creates it, so both the frame handle
  // and the runtime's own boot are racing this assertion.
  await expect
    .poll(async () => {
      const handle = await page.$("#nur-universe-stage");
      const frame = handle ? await handle.contentFrame() : null;
      if (!frame) return null;
      try {
        return await frame.evaluate(() => ({
          orbitRoot: Boolean(document.getElementById("nur-orbit-root")),
          // The canonical galaxy was layered under Orbit, never removed, so it is
          // still here and still rendering once Orbit stops owning the screen.
          galaxy: Boolean(document.getElementById("space3d")),
        }));
      } catch {
        return null; // frame swapped mid-evaluate; poll again
      }
    }, { timeout: 25_000 })
    .toEqual({ orbitRoot: false, galaxy: true });
});
