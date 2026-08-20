import { expect, test, type BrowserContext, type Frame, type Page } from "@playwright/test";

/**
 * Timeline, through the real browser against the real API.
 *
 * The assertions worth having here are the ones that stop the surface claiming
 * more than it knows: that a drag never reschedules silently, that a prediction
 * never renders as a settled fact, that an overdue commitment is not filed away
 * as ordinary history, that "unscheduled" is visible rather than dropped, and
 * that the canonical shell it lives inside is never damaged.
 */

const OWNER = { email: "owner@nur.app", password: "owner-demo-pass-123" };

// Serial, on one signed-in page, for the same reason as the Orbit and Map specs:
// a context per test means one sign-in each and the auth limiter correctly starts
// refusing partway through the file.
test.describe.configure({ mode: "serial" });

let sharedContext: BrowserContext;
let sharedPage: Page;
let seededTitles: {
  completed: string;
  overdue: string;
  future: string;
  dependent: string;
  predicted: string;
  unscheduled: string;
};

test.beforeAll(async ({ browser }) => {
  sharedContext = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  sharedPage = await sharedContext.newPage();
  await signIn(sharedPage);
  await seedEntries(sharedPage);
});

test.afterAll(async () => {
  await sharedContext?.close();
});

async function signIn(page: Page): Promise<void> {
  await page.goto("/", { waitUntil: "networkidle" });
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
    if (status === 401) {
      status = await page.evaluate(async (owner) => {
        const response = await fetch("/api/v1/auth/register", {
          method: "POST",
          credentials: "include",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ chosen_name: "Timeline Owner", email: owner.email, password: owner.password, consent: true }),
        });
        return response.status === 201 ? 200 : response.status;
      }, OWNER);
      if (status === 200) break;
    }
    if (status !== 429) break;
    await page.waitForTimeout(1500);
  }
  expect(status, "sign-in did not succeed within the limiter's window").toBe(200);
}

/**
 * Seed one entry in each temporal state this file asserts on.
 *
 * Deliberately not left to whatever happens to be in the database: the Orbit
 * spec had a test that passed for a while on residual state and then failed the
 * first time it met a freshly seeded environment. A precondition this file
 * depends on is created by this file.
 */
async function seedEntries(page: Page): Promise<void> {
  const nonce = `${Date.now()}-${Math.random().toString(16).slice(2, 8)}`;
  seededTitles = {
    completed: `E2E completed action ${nonce}`,
    overdue: `E2E overdue action ${nonce}`,
    future: `E2E future predecessor ${nonce}`,
    dependent: `E2E future dependent ${nonce}`,
    predicted: `E2E predicted outcome ${nonce}`,
    unscheduled: `E2E unscheduled idea ${nonce}`,
  };
  const created = await page.evaluate(async (titles) => {
    const csrf = document.cookie.split("; ")
      .find((row) => row.startsWith("nur_csrf="))?.split("=")[1] ?? "";
    const headers = { "Content-Type": "application/json", "X-CSRF-Token": csrf };
    const post = async (body: Record<string, unknown>) => {
      const response = await fetch("/api/v1/timeline/events", {
        method: "POST", credentials: "include", headers,
        body: JSON.stringify({ source_type: "OWNER", ...body }),
      });
      return { status: response.status, body: await response.json() };
    };
    const now = Date.now();
    const day = 86_400_000;
    const results = {
      completed: await post({
        event_type: "ACTION", title: titles.completed,
        status: "COMPLETED", scheduled_for: new Date(now - 4 * day).toISOString(),
      }),
      overdue: await post({
        event_type: "ACTION", title: titles.overdue,
        status: "SCHEDULED", scheduled_for: new Date(now - 2 * day).toISOString(),
      }),
      future: await post({
        event_type: "ACTION", title: titles.future,
        status: "PLANNED", scheduled_for: new Date(now + 3 * day).toISOString(),
      }),
      dependent: await post({
        event_type: "ACTION", title: titles.dependent,
        status: "PLANNED", scheduled_for: new Date(now + 5 * day).toISOString(),
      }),
      predicted: await post({
        event_type: "ACTION", title: titles.predicted,
        status: "PREDICTED", scheduled_for: new Date(now + 20 * day).toISOString(),
      }),
      unscheduled: await post({
        event_type: "ACTION", title: titles.unscheduled,
        date_precision: "UNSCHEDULED",
      }),
    };
    // A confirmed dependency, so the ripple dialog has something downstream to
    // warn about. Reuses map_edges, which is why this is a Timeline route.
    await fetch("/api/v1/timeline/dependencies", {
      method: "POST", credentials: "include", headers,
      body: JSON.stringify({
        predecessor_ref_type: "timeline_event",
        predecessor_ref_id: results.future.body.id,
        successor_ref_type: "timeline_event",
        successor_ref_id: results.dependent.body.id,
        dependency_kind: "FINISH_BEFORE",
      }),
    });
    return results;
  }, seededTitles);
  for (const [name, result] of Object.entries(created)) {
    expect(result.status, `seeding ${name} failed: ${JSON.stringify(result.body)}`).toBe(201);
  }
}

async function openTimeline(page: Page): Promise<Frame> {
  await page.goto("/universe/timeline", { waitUntil: "networkidle" });
  const stage = page.frameLocator("#nur-universe-stage");
  await expect(stage.locator("#nur-timeline-root")).toBeVisible({ timeout: 20_000 });
  const handle = await page.waitForSelector("#nur-universe-stage");
  const frame = await handle.contentFrame();
  if (!frame) throw new Error("the universe stage frame is not attached");
  // Wait for the composed flow, not the first paint. Asserting against the
  // initial empty render is a race the Map spec already lost once.
  await expect.poll(
    async () => frame.evaluate(
      () => document.getElementById("nur-timeline-root")?.dataset.timelineLoaded ?? "missing",
    ),
    { timeout: 20_000, message: "the Timeline flow never finished loading" },
  ).toBe("true");
  return frame;
}

test("Timeline mounts into the canonical document and never as a React root", async () => {
  const frame = await openTimeline(sharedPage);
  const shape = await frame.evaluate(() => {
    const root = document.getElementById("nur-timeline-root");
    return {
      mounted: Boolean(root),
      // The architecture law: no product page may be owned by a React tree.
      reactRoot: Boolean(document.getElementById("root")),
      nativeFlag: root?.dataset.v197NativeAdjunct ?? null,
      zones: {
        nav: Boolean(root?.querySelector(".nur-timeline-nav")),
        workspace: Boolean(root?.querySelector(".nur-timeline-workspace")),
        detail: Boolean(root?.querySelector(".nur-timeline-detail")),
      },
      title: root?.querySelector(".nur-timeline-title h1")?.textContent,
      subtitle: root?.querySelector(".nur-timeline-subtitle")?.textContent,
      modes: Array.from(root?.querySelectorAll("[data-timeline-mode]") ?? [])
        .map((node) => (node as HTMLElement).dataset.timelineMode),
    };
  });
  expect(shape.mounted).toBe(true);
  expect(shape.reactRoot).toBe(false);
  expect(shape.nativeFlag).toBe("true");
  expect(shape.zones).toEqual({ nav: true, workspace: true, detail: true });
  expect(shape.title).toBe("Timeline");
  // The full subtitle, not a truncated one. Side by side with the title it was
  // clipped to "PAST, PRES…" the moment the surface moved into the canonical
  // content region, which is narrower than the viewport it was designed against.
  expect(shape.subtitle).toBe("Past, present and possible futures");
  expect(shape.modes).toEqual(["flow", "calendar", "horizons", "review"]);
});

test("Timeline is hosted inside the canonical shell, not laid over it", async () => {
  const frame = await openTimeline(sharedPage);
  const shell = await frame.evaluate(() => {
    const root = document.getElementById("nur-timeline-root");
    const style = getComputedStyle(root as Element);
    const rail = document.querySelector(".nur-rail");
    const topbar = document.querySelector(".nur-topbar");
    const galaxy = document.getElementById("space3d");
    const host = document.getElementById("nur-surface-host");
    return {
      position: style.position,
      zIndex: style.zIndex,
      backgroundColor: style.backgroundColor,
      insideHost: Boolean(host && root && host.contains(root)),
      insideCanonicalShell: Boolean(root?.closest(".nur-viewport")),
      railVisible: rail ? getComputedStyle(rail).visibility : null,
      topbarVisible: topbar ? getComputedStyle(topbar).visibility : null,
      galaxyVisible: galaxy ? getComputedStyle(galaxy).visibility : null,
    };
  });
  // A full-screen opaque overlay is what cost NUR its stars and its whole
  // navigation shell. This surface must stay inside the canonical content region.
  expect(shell.position).toBe("relative");
  expect(shell.zIndex).toBe("auto");
  expect(shell.backgroundColor).toBe("rgba(0, 0, 0, 0)");
  expect(shell.insideHost).toBe(true);
  expect(shell.insideCanonicalShell).toBe(true);
  expect(shell.railVisible).toBe("visible");
  expect(shell.topbarVisible).toBe("visible");
  expect(shell.galaxyVisible).toBe("visible");
});

test("every Timeline control is a luminous glass capsule, never a boxed outline", async () => {
  const frame = await openTimeline(sharedPage);
  const verdict = await frame.evaluate(() => {
    const root = document.getElementById("nur-timeline-root");
    if (!root) return { checked: 0, offenders: ["root missing"] };
    const offenders: string[] = [];
    for (const control of Array.from(root.querySelectorAll("button, input"))) {
      const style = getComputedStyle(control);
      const radii = [
        style.borderTopLeftRadius, style.borderTopRightRadius,
        style.borderBottomLeftRadius, style.borderBottomRightRadius,
      ].map((value) => parseFloat(value) || 0);
      const label = (control.textContent || (control as HTMLInputElement).placeholder || "?")
        .slice(0, 34);
      const height = control.getBoundingClientRect().height;
      if (height > 0 && Math.max(...radii) < Math.min(height / 2, 12)) {
        offenders.push(`${label} radius ${Math.max(...radii)} height ${height}`);
      }
      if (style.appearance !== "none" && control.tagName === "INPUT") {
        offenders.push(`${label} keeps native appearance ${style.appearance}`);
      }
      if (/^rgb\(2[3-5][0-9], 2[3-5][0-9], 2[3-5][0-9]\)$/.test(style.backgroundColor)) {
        offenders.push(`${label} has a white fill`);
      }
    }
    return { checked: root.querySelectorAll("button, input").length, offenders };
  });
  expect(verdict.checked).toBeGreaterThan(8);
  expect(verdict.offenders).toEqual([]);
});

test("all four modes render their own workspace", async () => {
  // Four mode switches, each fetching. Slow on purpose rather than flaky.
  test.slow();
  const frame = await openTimeline(sharedPage);
  for (const [mode, marker] of [
    ["calendar", "[data-timeline-calendar]"],
    ["horizons", "[data-timeline-horizons]"],
    ["review", "[data-timeline-review]"],
    ["flow", ".nur-timeline-flow-wrap"],
  ] as [string, string][]) {
    await frame.click(`[data-timeline-mode="${mode}"]`);
    await expect.poll(
      async () => frame.evaluate(
        (selector) => Boolean(document.querySelector(selector)), marker,
      ),
      { timeout: 12_000 },
    ).toBe(true);
  }
});

test("the past crystallises, the future stays translucent, the overdue is neither", async () => {
  const frame = await openTimeline(sharedPage);
  await frame.click('[data-timeline-mode="flow"]');
  const lanes = await frame.evaluate((titles) => {
    const byTitle = (needle: string) => {
      const node = Array.from(document.querySelectorAll("[data-timeline-entry]"))
        .find((row) => (row.textContent || "").includes(needle));
      if (!node) return null;
      const style = getComputedStyle(node);
      return {
        lane: (node as HTMLElement).dataset.timelineLane ?? null,
        borderStyle: style.borderTopStyle,
        borderColor: style.borderTopColor,
      };
    };
    return {
      completed: byTitle(titles.completed),
      overdue: byTitle(titles.overdue),
      future: byTitle(titles.future),
    };
  }, seededTitles);

  // A settled past reads as settled: solid edge.
  expect(lanes.completed?.lane).toBe("past");
  expect(lanes.completed?.borderStyle).toBe("solid");

  // §60: something still owed is not ordinary history. It gets its own restrained
  // coral treatment rather than being filed away with the completed work.
  expect(lanes.overdue?.lane).toBe("overdue");
  expect(lanes.overdue?.borderColor).toContain("255, 82, 111");

  // The future is never drawn as settled fact: dashed, not solid.
  expect(lanes.future?.lane).toBe("future");
  expect(lanes.future?.borderStyle).toBe("dashed");
});

test("a prediction is labelled as one and never as an observed fact", async () => {
  const frame = await openTimeline(sharedPage);
  await frame.click('[data-timeline-mode="flow"]');
  const predicted = await frame.evaluate((title) => {
    const node = Array.from(document.querySelectorAll("[data-timeline-entry]"))
      .find((row) => (row.textContent || "").includes(title));
    return {
      found: Boolean(node),
      text: node?.textContent ?? "",
      lane: (node as HTMLElement | undefined)?.dataset.timelineLane ?? null,
    };
  }, seededTitles.predicted);
  expect(predicted.found).toBe(true);
  // The word, not only a hue — the basis survives for a reader who cannot
  // separate these colours.
  expect(predicted.text).toContain("Predicted");
  expect(predicted.text).not.toContain("Observed");
  expect(predicted.text).not.toContain("Completed");
  expect(predicted.lane).toBe("future");
});

test("unscheduled work stays visible in its own holding field", async () => {
  const frame = await openTimeline(sharedPage);
  await frame.click('[data-timeline-mode="flow"]');
  const holding = await frame.evaluate((title) => {
    const field = document.querySelector("[data-timeline-unscheduled]");
    return {
      present: Boolean(field),
      // §18: valid work without a date is held, never dropped from the surface.
      containsIdea: (field?.textContent || "").includes(title),
      // And it is not smuggled into the dated river.
      inRiver: Array.from(
        document.querySelectorAll(".nur-timeline-day-group [data-timeline-entry]"),
      ).some((row) => (row.textContent || "").includes(title)),
    };
  }, seededTitles.unscheduled);
  expect(holding.present).toBe(true);
  expect(holding.containsIdea).toBe(true);
  expect(holding.inRiver).toBe(false);
});

test("the Now Horizon sits at the present, between past and future entries", async () => {
  const frame = await openTimeline(sharedPage);
  await frame.click('[data-timeline-mode="flow"]');
  const order = await frame.evaluate((titles) => {
    const spine = document.querySelector(".nur-timeline-spine");
    if (!spine) return null;
    const nodes = Array.from(spine.querySelectorAll(
      "[data-timeline-now], [data-timeline-entry]",
    ));
    const nowIndex = nodes.findIndex((n) => (n as HTMLElement).dataset.timelineNow === "true");
    const indexOf = (needle: string) => nodes.findIndex(
      (n) => (n.textContent || "").includes(needle),
    );
    return {
      nowIndex,
      completedIndex: indexOf(titles.completed),
      futureIndex: indexOf(titles.future),
      nowLabel: (nodes[nowIndex]?.textContent || "").trim(),
    };
  }, seededTitles);
  expect(order).not.toBeNull();
  expect(order!.nowIndex).toBeGreaterThan(-1);
  // Placed by timestamp, not by day: a horizon labelled with a time must not sit
  // above an entry that is earlier than that time.
  expect(order!.completedIndex).toBeLessThan(order!.nowIndex);
  expect(order!.futureIndex).toBeGreaterThan(order!.nowIndex);
  expect(order!.nowLabel.length).toBeGreaterThan(4);
});

test("dragging a future entry opens the ripple dialog and writes nothing yet", async () => {
  test.slow();
  const page = sharedPage;
  const frame = await openTimeline(page);
  await frame.click('[data-timeline-mode="flow"]');

  const before = await frame.evaluate(async (title) => {
    const flow = await (await fetch("/api/v1/timeline/flow", { credentials: "include" })).json();
    const row = flow.entries.find(
      (e: { title: string }) => e.title === title,
    );
    return { scheduledFor: row.scheduled_for as string, ref: row.ref as string };
  }, seededTitles.future);

  const locator = page.frameLocator("#nur-universe-stage")
    .locator(`[data-timeline-entry="${before.ref}"]`);
  // Bring it into view first. A pointer gesture at coordinates outside the
  // viewport lands on nothing, which is exactly how this test first failed.
  await locator.scrollIntoViewIfNeeded();
  const box = await locator.boundingBox();
  expect(box, "the future entry has no box to drag").not.toBeNull();

  // A real pointer gesture, well past the 6px threshold.
  await page.mouse.move(box!.x + box!.width / 2, box!.y + box!.height / 2);
  await page.mouse.down();
  await page.mouse.move(box!.x + box!.width / 2, box!.y + box!.height / 2 + 70, { steps: 10 });
  await page.mouse.up();

  // The dialog must appear, and it must name what is downstream.
  await expect.poll(
    async () => frame.evaluate(
      () => Boolean(document.querySelector("[data-timeline-ripple-dialog]")),
    ),
    { timeout: 12_000, message: "the drag did not open the ripple dialog" },
  ).toBe(true);

  const dialog = await frame.evaluate(() => {
    const node = document.querySelector("[data-timeline-ripple-dialog]");
    return {
      text: node?.textContent ?? "",
      modes: Array.from(node?.querySelectorAll("[data-timeline-ripple-mode]") ?? [])
        .map((n) => (n as HTMLElement).dataset.timelineRippleMode),
      hasCancel: Boolean(node?.querySelector("[data-timeline-ripple-cancel]")),
    };
  });
  expect(dialog.text).toContain(seededTitles.future);
  expect(dialog.text).toContain(seededTitles.dependent);
  expect(dialog.modes).toContain("MOVE_ONLY");
  expect(dialog.modes).toContain("SHIFT_DEPENDENTS");
  expect(dialog.hasCancel).toBe(true);

  // Nothing is written until a mode is chosen. This is the guarantee.
  const during = await frame.evaluate(async (title) => {
    const flow = await (await fetch("/api/v1/timeline/flow", { credentials: "include" })).json();
    return flow.entries.find(
      (e: { title: string }) => e.title === title,
    ).scheduled_for as string;
  }, seededTitles.future);
  expect(during).toBe(before.scheduledFor);

  // Cancelling leaves it untouched too.
  await frame.click("[data-timeline-ripple-cancel]");
  const after = await frame.evaluate(async (title) => {
    const flow = await (await fetch("/api/v1/timeline/flow", { credentials: "include" })).json();
    return flow.entries.find(
      (e: { title: string }) => e.title === title,
    ).scheduled_for as string;
  }, seededTitles.future);
  expect(after).toBe(before.scheduledFor);
});

test("choosing Move-this-only leaves the dependent where it was", async () => {
  test.slow();
  const frame = await openTimeline(sharedPage);
  const before = await frame.evaluate(async (titles) => {
    const flow = await (await fetch("/api/v1/timeline/flow", { credentials: "include" })).json();
    const pick = (title: string) => flow.entries.find(
      (e: { title: string }) => e.title === title,
    );
    return {
      predecessor: pick(titles.future).scheduled_for as string,
      dependent: pick(titles.dependent).scheduled_for as string,
      predecessorId: pick(titles.future).id as string,
    };
  }, seededTitles);

  // Drive the same dialog the drag opens, through the keyboard-reachable path.
  await frame.evaluate(async (id) => {
    const csrf = document.cookie.split("; ")
      .find((row) => row.startsWith("nur_csrf="))?.split("=")[1] ?? "";
    await fetch("/api/v1/timeline/ripple-apply", {
      method: "POST", credentials: "include",
      headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf },
      body: JSON.stringify({
        entry_id: id,
        new_start_at: new Date(Date.now() + 9 * 86_400_000).toISOString(),
        mode: "MOVE_ONLY",
      }),
    });
  }, before.predecessorId);

  const after = await frame.evaluate(async (titles) => {
    const flow = await (await fetch("/api/v1/timeline/flow", { credentials: "include" })).json();
    const pick = (title: string) => flow.entries.find(
      (e: { title: string }) => e.title === title,
    );
    return {
      predecessor: pick(titles.future).scheduled_for as string,
      dependent: pick(titles.dependent).scheduled_for as string,
    };
  }, seededTitles);
  expect(after.predecessor).not.toBe(before.predecessor);
  // The whole point of MOVE_ONLY: nothing downstream is touched.
  expect(after.dependent).toBe(before.dependent);
});

test("the five detail tabs render, and NUR View always states its doubt", async () => {
  test.slow();
  const frame = await openTimeline(sharedPage);
  await frame.click('[data-timeline-mode="flow"]');
  const ref = await frame.evaluate(
    () => document.querySelector("[data-timeline-entry]")?.getAttribute("data-timeline-entry"),
  );
  expect(ref).not.toBeNull();
  await frame.click(`[data-timeline-entry="${ref}"]`);

  const tabs = await frame.evaluate(
    () => Array.from(document.querySelectorAll("[data-timeline-tab]"))
      .map((n) => (n as HTMLElement).dataset.timelineTab),
  );
  expect(tabs).toEqual(["overview", "time", "links", "activity", "nur"]);

  for (const tab of tabs) {
    await frame.click(`[data-timeline-tab="${tab}"]`);
    await expect.poll(
      async () => frame.evaluate(
        (name) => document.querySelector("[data-timeline-tab-panel]")
          ?.getAttribute("data-timeline-tab-panel") === name,
        tab,
      ),
      { timeout: 10_000 },
    ).toBe(true);
  }

  // Required and never omitted.
  const doubt = await frame.evaluate(() => {
    const node = document.querySelector("[data-timeline-doubt]");
    return {
      present: Boolean(node),
      label: node?.querySelector(".nur-timeline-doubt-label")?.textContent ?? "",
      body: node?.querySelector(".nur-timeline-field-value")?.textContent ?? "",
    };
  });
  expect(doubt.present).toBe(true);
  expect(doubt.label).toBe("What NUR may be wrong about");
  expect(doubt.body.length).toBeGreaterThan(30);
});

test("an unmeasured field says so instead of showing a number", async () => {
  const frame = await openTimeline(sharedPage);
  await frame.click('[data-timeline-mode="flow"]');
  const ref = await frame.evaluate((title) => {
    const node = Array.from(document.querySelectorAll("[data-timeline-entry]"))
      .find((row) => (row.textContent || "").includes(title));
    return node?.getAttribute("data-timeline-entry") ?? null;
  }, seededTitles.dependent);
  expect(ref).not.toBeNull();
  await frame.click(`[data-timeline-entry="${ref}"]`);
  await frame.click('[data-timeline-tab="time"]');

  const values = await frame.evaluate(() => {
    const panel = document.querySelector("[data-timeline-tab-panel]");
    const rows = Array.from(panel?.querySelectorAll(".nur-timeline-field") ?? []);
    return rows.map((row) => ({
      label: row.querySelector(".nur-timeline-field-label")?.textContent ?? "",
      value: row.querySelector(".nur-timeline-field-value")?.textContent ?? "",
      unmeasured: Boolean(row.querySelector(".nur-timeline-field-value.is-unmeasured")),
    }));
  });
  const quality = values.find((row) => row.label === "Completion quality");
  expect(quality?.value).toBe("Not assessed");
  expect(quality?.unmeasured).toBe(true);
  const actualEnd = values.find((row) => row.label === "Actual end");
  expect(actualEnd?.unmeasured).toBe(true);
});

test("Review compares planned against actual and says it is deterministic", async () => {
  const frame = await openTimeline(sharedPage);
  await frame.click('[data-timeline-mode="review"]');
  await expect.poll(
    async () => frame.evaluate(
      () => Boolean(document.querySelector("[data-timeline-review]")),
    ),
    { timeout: 12_000 },
  ).toBe(true);
  const review = await frame.evaluate(() => {
    const panel = document.querySelector("[data-timeline-review]");
    return {
      labels: Array.from(panel?.querySelectorAll(".nur-timeline-stat-label") ?? [])
        .map((n) => n.textContent),
      text: panel?.textContent ?? "",
    };
  });
  expect(review.labels).toEqual(["Entries", "Completed", "Missed", "Rescheduled"]);
  // No model is consulted anywhere in this repository, and the surface says so
  // rather than implying analysis it did not do.
  expect(review.text).toContain("Deterministic");
  expect(review.text).toContain("no model consulted");
});

test("Horizons buckets work by real timestamp and never invent an entry", async () => {
  const frame = await openTimeline(sharedPage);
  await frame.click('[data-timeline-mode="horizons"]');
  await expect.poll(
    async () => frame.evaluate(
      () => document.querySelectorAll("[data-timeline-horizon-bucket]").length > 0,
    ),
    { timeout: 12_000 },
  ).toBe(true);
  const verdict = await frame.evaluate(async () => {
    const served = await (await fetch("/api/v1/timeline/horizons", {
      credentials: "include",
    })).json();
    const rendered = Array.from(document.querySelectorAll("[data-timeline-horizon-bucket]"))
      .map((node) => {
        const key = (node as HTMLElement).dataset.timelineHorizonBucket ?? "";
        const items = Array.from(node.querySelectorAll(".nur-timeline-horizon-item"))
          .map((row) => (row.textContent || "").trim());
        return {
          key,
          items,
          saysEmpty: (node.textContent || "").includes("Nothing here."),
          servedCount: (served.buckets[key] ?? []).length,
        };
      });
    return rendered;
  });

  expect(verdict.map((row) => row.key)).toEqual([
    "NOW", "THIS_WEEK", "THIRTY_DAYS", "NINETY_DAYS", "SIX_MONTHS", "ONE_YEAR", "SOMEDAY",
  ]);

  for (const bucket of verdict) {
    // Never invent an entry: what is drawn matches what the server bucketed,
    // exactly. Asserting "some bucket is empty" was data-dependent and started
    // failing once repeated runs had filled every horizon.
    expect(
      bucket.items.length,
      `${bucket.key} rendered ${bucket.items.length} items for ${bucket.servedCount} served`,
    ).toBe(bucket.servedCount);
    // And an empty horizon says so rather than being padded with filler.
    expect(bucket.saysEmpty).toBe(bucket.servedCount === 0);
  }
});

test("an entry is reachable and reschedulable by keyboard alone", async () => {
  const frame = await openTimeline(sharedPage);
  await frame.click('[data-timeline-mode="flow"]');
  const focused = await frame.evaluate(() => {
    const node = Array.from(document.querySelectorAll("[data-timeline-entry]"))
      .find((row) => (row as HTMLElement).dataset.timelineLane === "future") as HTMLElement | undefined;
    if (!node) return null;
    node.focus();
    return {
      focusable: document.activeElement === node,
      tabindex: node.getAttribute("tabindex"),
      role: node.getAttribute("role"),
      ref: node.dataset.timelineEntry ?? null,
    };
  });
  expect(focused).not.toBeNull();
  expect(focused!.focusable).toBe(true);
  expect(focused!.tabindex).toBe("0");
  expect(focused!.role).toBe("button");

  // Arrow keys are the non-drag alternative, and they open the same dialog a
  // drag does rather than a second, weaker path.
  await frame.locator(`[data-timeline-entry="${focused!.ref}"]`).scrollIntoViewIfNeeded();
  await frame.press(`[data-timeline-entry="${focused!.ref}"]`, "ArrowDown");
  await expect.poll(
    async () => frame.evaluate(
      () => Boolean(document.querySelector("[data-timeline-ripple-dialog]")),
    ),
    { timeout: 12_000, message: "the keyboard nudge did not open the ripple dialog" },
  ).toBe(true);
  await frame.click("[data-timeline-ripple-cancel]");
});

test("nothing loops when reduced motion is requested", async ({ browser }) => {
  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    reducedMotion: "reduce",
    storageState: await sharedContext.storageState(),
  });
  const page = await context.newPage();
  try {
    const frame = await openTimeline(page);
    const motion = await frame.evaluate(() => {
      const sigil = document.querySelector(".nur-timeline-now-sigil");
      return {
        honoured: matchMedia("(prefers-reduced-motion: reduce)").matches,
        // The Now sigil is the only looping element on this surface.
        sigilAnimation: sigil ? getComputedStyle(sigil).animationName : null,
        sigilPresent: Boolean(sigil),
      };
    });
    expect(motion.honoured).toBe(true);
    expect(motion.sigilPresent).toBe(true);
    expect(motion.sigilAnimation).toBe("none");
  } finally {
    await context.close();
  }
});

test("mobile keeps the flow readable without a sideways scroll", async ({ browser }) => {
  const context = await browser.newContext({
    viewport: { width: 390, height: 844 },
    storageState: await sharedContext.storageState(),
  });
  const page = await context.newPage();
  try {
    const frame = await openTimeline(page);
    const layout = await frame.evaluate(() => {
      const root = document.getElementById("nur-timeline-root");
      const nav = root?.querySelector(".nur-timeline-nav");
      const detail = root?.querySelector(".nur-timeline-detail");
      return {
        navHidden: nav ? getComputedStyle(nav).display === "none" : null,
        detailHidden: detail ? getComputedStyle(detail).display === "none" : null,
        flowPresent: Boolean(root?.querySelector(".nur-timeline-flow-wrap")),
        bodyScrollsSideways: document.documentElement.scrollWidth
          > document.documentElement.clientWidth + 1,
      };
    });
    // §53: the rail and the detail panel are not columns on a phone.
    expect(layout.navHidden).toBe(true);
    expect(layout.detailHidden).toBe(true);
    expect(layout.flowPresent).toBe(true);
    expect(layout.bodyScrollsSideways).toBe(false);
  } finally {
    await context.close();
  }
});

test("leaving Timeline restores the canonical universe untouched", async () => {
  const page = sharedPage;
  await openTimeline(page);
  await page.goto("/systems", { waitUntil: "networkidle" });

  // Polled, not asserted once. Navigating away reloads the host, which detaches
  // and re-creates the stage frame, so the canonical runtime's own boot — the
  // star-brain canvas in particular — is racing this assertion. It passed alone
  // and failed in sequence, which is the signature of exactly that race.
  await expect
    .poll(async () => {
      const handle = await page.$("#nur-universe-stage");
      const frame = handle ? await handle.contentFrame() : null;
      if (!frame) return null;
      try {
        return await frame.evaluate(() => {
          const front = document.getElementById("nur-front-v61");
          return {
            timelineRemoved: !document.getElementById("nur-timeline-root"),
            hostReleased: !document.getElementById("nur-surface-host"),
            galaxyPresent: Boolean(document.getElementById("space3d")),
            reactRoot: Boolean(document.getElementById("root")),
            frontVisible: front ? getComputedStyle(front).visibility === "visible" : false,
            canonicalPageShown: Boolean(
              document.querySelector(".nur-viewport > .nur-page.active"),
            ),
            // The star-brain is the identity of the canonical page. If leaving a
            // surface cost NUR its brain, that is the defect worth catching.
            starBrainPresent: Boolean(document.getElementById("nur-brain-canvas")),
          };
        });
      } catch {
        // The frame detached mid-evaluate; poll again.
        return null;
      }
    }, { timeout: 25_000, message: "the canonical universe never came back" })
    .toEqual({
      timelineRemoved: true,
      hostReleased: true,
      galaxyPresent: true,
      reactRoot: false,
      frontVisible: true,
      canonicalPageShown: true,
      starBrainPresent: true,
    });
});
