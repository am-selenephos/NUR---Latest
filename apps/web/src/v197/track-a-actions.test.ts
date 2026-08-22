import { describe, expect, it, vi } from "vitest";

import { V197ApiError, type V197BridgeSnapshot } from "../bridge/v197ApiClient";
import {
  bindV197Actions,
  bindV197EntryAuth,
  talkSemanticsForAction,
  type V197ActionApi,
  type V197TalkTransport,
} from "../bridge/v197Bindings";

function snapshot(): V197BridgeSnapshot {
  return {
    session: {
      id: "owner",
      email: "owner@nur.app",
      profile: { chosen_name: "Owner", locale: "ur", writing_preference: "roman" },
      orbit: { id: "personal", title: "Personal Orbit", kind: "PERSONAL_BRIDGE", status: "ACTIVE" },
    },
    ownerState: null,
    map: { provenance_label: "owner_ledger", counts: [], nodes: [{ id: "system-1", title: "Ambition", kind: "PROJECT", orbit_id: "system-1", active: true, counts: {} }] },
    orbits: null,
    timeline: null,
    insights: null,
    preferences: { locale: "ur", writing_preference: "roman", active_orbit_id: "system-1", default_boundary: "PRIVATE_ORBIT" },
    talkThread: [],
    journal: [],
    plans: [],
    glow: { balance: 0, lifetime_points: 0, recent_transactions: [], streaks: [] },
    researchBriefs: [],
  };
}

function api(): Record<string, ReturnType<typeof vi.fn>> {
  return {
    event: vi.fn(),
    talk: vi.fn(),
    createJournal: vi.fn(),
    createPlan: vi.fn(),
    patchPlanStep: vi.fn(),
    createOutcome: vi.fn(),
    rewardGlow: vi.fn(),
    patchPreferences: vi.fn(),
    createResearchBrief: vi.fn(),
    createOrbit: vi.fn(),
    acceptInsight: vi.fn(),
    rejectInsight: vi.fn(),
    correctInsight: vi.fn(),
    convertInsightToPlan: vi.fn(),
    addInsightToTimeline: vi.fn(),
    get: vi.fn(),
  };
}

function talkTransport(fake: Record<string, ReturnType<typeof vi.fn>>): V197TalkTransport {
  return {
    active: false,
    async talk(payload, hooks) {
      hooks?.onEvent?.({ id: 1, event: "talk.accepted", data: { request_id: payload.request_id } });
      hooks?.onDelta?.("Live response");
      const invoke = fake.talk as unknown as (
        value: typeof payload,
      ) => ReturnType<V197TalkTransport["talk"]>;
      return invoke(payload);
    },
    cancel: vi.fn().mockResolvedValue(true),
  };
}

async function settle(): Promise<void> {
  await new Promise(resolve => window.setTimeout(resolve, 0));
  await new Promise(resolve => window.setTimeout(resolve, 0));
}

describe("Track A V197 write bindings", () => {
  it("awards Journal Glow only after the journal row is persisted", async () => {
    const document = window.document.implementation.createHTMLDocument("Journal");
    document.body.innerHTML = '<textarea id="journal-input">A persisted line.</textarea><button id="journal-save">Save</button>';
    const calls: string[] = [];
    const fake = api();
    fake.createJournal.mockImplementation(async () => {
      calls.push("journal");
      return { id: "journal-1", body: "A persisted line.", orbit_id: "system-1", event_id: "event-1", created_at: "2026-07-11T10:00:00Z" };
    });
    fake.rewardGlow.mockImplementation(async () => {
      calls.push("glow");
      return { awarded_points: 4, balance: 4, lifetime_points: 4, idempotent_replay: false, streak: null };
    });
    const refresh = vi.fn().mockResolvedValue(snapshot());

    bindV197Actions(document, fake as unknown as V197ActionApi, snapshot(), refresh, () => undefined, talkTransport(fake));
    document.querySelector<HTMLButtonElement>("#journal-save")?.click();
    await settle();

    expect(calls).toEqual(["journal", "glow"]);
    expect(fake.rewardGlow).toHaveBeenCalledWith(expect.objectContaining({
      source_id: "journal-1",
      event_type: "journal_saved",
      idempotency_key: "journal:journal-1:saved",
    }));
    expect(refresh).toHaveBeenCalledOnce();
  });

  it("passes persisted locale and Roman Urdu preference into Talk", async () => {
    const document = window.document.implementation.createHTMLDocument("Talk");
    document.body.innerHTML = '<input id="talk-input" value="Seedha jawab do"><button data-send="talk">Send</button><div id="talk-stream"></div>';
    const fake = api();
    fake.talk.mockResolvedValue({
      turn_event_id: "turn-1",
      response_event_id: "response-1",
      model_run_id: "run-1",
      provider: "disabled",
      provider_available: false,
      provider_reason: "AI not connected",
      output: { direct_response: "AI not connected", observed: [], inferred: [], hypotheses: [], uncertainty: [], next_move: "Connect AI", memory_candidates: [], source_refs: [] },
      verification: { verdict: "ALLOW" },
    });
    fake.rewardGlow.mockResolvedValue({ awarded_points: 2, balance: 2, lifetime_points: 2, idempotent_replay: false, streak: null });
    const refresh = vi.fn().mockResolvedValue(snapshot());

    bindV197Actions(document, fake as unknown as V197ActionApi, snapshot(), refresh, () => undefined, talkTransport(fake));
    document.querySelector<HTMLButtonElement>('[data-send="talk"]')?.click();
    await settle();

    expect(fake.talk).toHaveBeenCalledWith(expect.objectContaining({
      message: "Seedha jawab do",
      locale: "ur",
      writing_preference: "roman",
      orbit_id: "system-1",
      mode: "talk",
      capability_id: null,
      memory_mode: "EPHEMERAL",
    }));
    expect(fake.rewardGlow).toHaveBeenCalledWith(expect.objectContaining({ source_id: "turn-1", event_type: "talk_meaningful" }));
  });

  it.each([
    ["reflect", "capability:contextual_answer", "REVIEW"],
    ["plan", "capability:plan_from_conversation", "EPHEMERAL"],
    ["challenge", "capability:contextual_answer", "EPHEMERAL"],
    ["explore", "capability:contextual_answer", "EPHEMERAL"],
    ["summarize", "capability:contextual_answer", "EPHEMERAL"],
  ] as const)("maps the explicit %s action to its capability and memory semantics", (mode, capabilityId, memoryMode) => {
    expect(talkSemanticsForAction(mode)).toEqual({
      mode,
      capability_id: capabilityId,
      memory_mode: memoryMode,
    });
  });

  it("keeps an explicit capability refusal visible without inventing an assistant answer", async () => {
    const document = window.document.implementation.createHTMLDocument("Talk refusal");
    document.body.innerHTML = `
      <div class="universe-prompt-row"><button data-action="reflect">Reflect</button></div>
      <input id="talk-input" value="Reflect this honestly">
      <button data-send="talk">Send</button>
      <div id="talk-stream"></div>
    `;
    const fake = api();
    fake.talk.mockRejectedValue(new V197ApiError("This capability is outside the owner's current grant.", 403, "capability_denied"));

    bindV197Actions(
      document,
      fake as unknown as V197ActionApi,
      snapshot(),
      vi.fn().mockResolvedValue(snapshot()),
      () => undefined,
      talkTransport(fake),
    );
    document.querySelector<HTMLButtonElement>('[data-action="reflect"]')?.click();
    document.querySelector<HTMLButtonElement>('[data-send="talk"]')?.click();
    await settle();

    expect(fake.talk).toHaveBeenCalledWith(expect.objectContaining({
      capability_id: "capability:contextual_answer",
      memory_mode: "REVIEW",
    }));
    const refusal = document.querySelector<HTMLElement>('[data-nur-talk-error="true"]');
    expect(refusal?.textContent).toContain("outside the owner's current grant");
    expect(refusal?.textContent).toContain("nothing was invented");
    expect(document.querySelectorAll(".talk-message.nur")).toHaveLength(1);
  });

  it("hydrates a persisted Talk turn even when Glow is anti-spam gated", async () => {
    const document = window.document.implementation.createHTMLDocument("Talk capped Glow");
    document.body.innerHTML = '<input id="talk-input" value="Second real turn"><button data-send="talk">Send</button><div id="talk-stream"></div>';
    const fake = api();
    fake.talk.mockResolvedValue({
      turn_event_id: "turn-2",
      response_event_id: "response-2",
      model_run_id: "run-2",
      provider: "disabled",
      provider_available: false,
      provider_reason: "AI not connected",
      output: { direct_response: "AI not connected", observed: [], inferred: [], hypotheses: [], uncertainty: [], next_move: "Connect AI", memory_candidates: [], source_refs: [] },
      verification: { verdict: "ALLOW" },
    });
    fake.rewardGlow.mockRejectedValue(new V197ApiError("Glow action is inside its anti-spam window.", 409));
    const refresh = vi.fn().mockResolvedValue(snapshot());

    bindV197Actions(document, fake as unknown as V197ActionApi, snapshot(), refresh, () => undefined, talkTransport(fake));
    document.querySelector<HTMLButtonElement>('[data-send="talk"]')?.click();
    await settle();

    expect(fake.talk).toHaveBeenCalledOnce();
    expect(refresh).toHaveBeenCalledOnce();
    expect(document.querySelector<HTMLInputElement>("#talk-input")?.value).toBe("");
  });

  it("persists dedicated Insight review actions through their backend routes", async () => {
    const document = window.document.implementation.createHTMLDocument("Insight review");
    document.body.innerHTML = `
      <section id="nur-v197-insight-controls" data-insight-id="insight-1">
        <input id="nur-v197-insight-correction" value="The pattern only applies under deadline pressure.">
        <button data-action="insight-accept">Accept</button>
        <button data-action="insight-correct">Correct</button>
        <button data-action="insight-plan">Make a Plan</button>
        <button data-action="insight-timeline">Add to Timeline</button>
      </section>
    `;
    const fake = api();
    fake.acceptInsight.mockResolvedValue({ status: "ACCEPTED" });
    fake.correctInsight.mockResolvedValue({ status: "CORRECTED" });
    fake.convertInsightToPlan.mockResolvedValue({ plan_id: "plan-1" });
    fake.addInsightToTimeline.mockResolvedValue({ timeline_event_id: "timeline-1" });
    const refresh = vi.fn().mockResolvedValue(snapshot());
    bindV197Actions(document, fake as unknown as V197ActionApi, snapshot(), refresh);

    for (const action of ["insight-accept", "insight-correct", "insight-plan", "insight-timeline"]) {
      document.querySelector<HTMLButtonElement>(`[data-action="${action}"]`)?.click();
      await settle();
    }

    expect(fake.acceptInsight).toHaveBeenCalledWith("insight-1");
    expect(fake.correctInsight).toHaveBeenCalledWith(
      "insight-1",
      "The pattern only applies under deadline pressure.",
    );
    expect(fake.convertInsightToPlan).toHaveBeenCalledWith("insight-1");
    expect(fake.addInsightToTimeline).toHaveBeenCalledWith("insight-1");
    expect(refresh).toHaveBeenCalledTimes(4);
  });

  it("restores the active route after hydration before an action completes", async () => {
    const document = window.document.implementation.createHTMLDocument("System mutation");
    document.body.innerHTML = `
      <button data-action="add-system">Add system</button>
    `;
    const order: string[] = [];
    const fake = api();
    fake.createOrbit.mockImplementation(async () => {
      order.push("persist");
      return { id: "orbit-new", title: "A new owner System" };
    });
    const refresh = vi.fn().mockImplementation(async () => {
      order.push("snapshot");
      return snapshot();
    });
    const afterHydrate = vi.fn().mockImplementation(async () => {
      order.push("route");
    });

    bindV197Actions(
      document,
      fake as unknown as V197ActionApi,
      snapshot(),
      refresh,
      () => undefined,
      talkTransport(fake),
      afterHydrate,
    );
    document.querySelector<HTMLButtonElement>('[data-action="add-system"]')?.click();
    const dialog = document.querySelector<HTMLDialogElement>("#nur-v197-system-create");
    expect(dialog?.hasAttribute("open")).toBe(true);
    const input = document.querySelector<HTMLInputElement>("#nur-v197-system-title");
    if (input) input.value = "A new owner System";
    document.querySelector<HTMLButtonElement>('[data-action="system-create-submit"]')?.click();
    await settle();

    expect(order).toEqual(["persist", "snapshot", "route"]);
    expect(afterHydrate).toHaveBeenCalledOnce();
  });
});

describe("Track A V197 authentication transition", () => {
  it("shows the native star wait chamber for the exact login promise window", async () => {
    const document = window.document.implementation.createHTMLDocument("NUR sign in");
    document.body.innerHTML = `
      <div id="iSpark" class="i-spark spark"><span class="spark-core">star</span></div>
      <p id="f4-status"></p>
      <form id="f4-signin-form">
        <input id="f4-signin-email" type="email" value="owner@nur.app" required>
        <input id="f4-signin-password" type="password" value="private-password" required>
        <button type="submit">Sign in</button>
      </form>
    `;
    let resolveLogin!: () => void;
    const login = vi.fn(() => new Promise<void>(resolve => { resolveLogin = resolve; }));
    const onAuthenticated = vi.fn().mockResolvedValue(undefined);

    bindV197EntryAuth(document, {
      register: vi.fn(),
      login,
    } as never, onAuthenticated);
    document.querySelector<HTMLFormElement>("#f4-signin-form")?.requestSubmit();

    const wait = document.querySelector<HTMLElement>("#nur-v197-auth-wait");
    expect(wait?.hidden).toBe(false);
    expect(wait?.textContent).toContain("NUR is opening your Orbit");
    expect(wait?.querySelectorAll(".nur-star-seal")).toHaveLength(1);
    expect(wait?.querySelector(".nur-star-seal--startup > .i-spark.spark")).not.toBeNull();
    expect(wait?.querySelector(".spark-core")).not.toBeNull();
    expect(wait?.querySelectorAll(".ray")).toHaveLength(0);
    expect(document.querySelector("#f4-signin-form")?.getAttribute("aria-busy")).toBe("true");

    resolveLogin();
    await settle();
    expect(onAuthenticated).toHaveBeenCalledOnce();
    expect(wait?.hidden).toBe(true);
    expect(document.querySelector("#f4-signin-form")?.hasAttribute("aria-busy")).toBe(false);
  });

  function signupDocument(): Document {
    const document = window.document.implementation.createHTMLDocument("NUR sign up");
    document.body.innerHTML = `
      <div id="iSpark" class="i-spark spark"><span class="spark-core">star</span></div>
      <p id="f4-status"></p>
      <form id="f4-signup-form">
        <input id="f4-name" value="Star" required>
        <input id="f4-email" type="email" value="star@nurapp.dev" required>
        <input id="f4-password" type="password" value="orbit-pass-9" required>
        <input id="f4-consent-check" type="checkbox" checked>
        <button type="submit">Begin</button>
      </form>
      <button data-switch="signin" type="button">Sign in</button>
      <form id="f4-signin-form">
        <input id="f4-signin-email" type="email">
        <input id="f4-signin-password" type="password">
        <button type="submit">Enter</button>
      </form>
    `;
    return document;
  }

  it("failed duplicate signup never fakes auth and prepares the real Sign in form", async () => {
    const document = signupDocument();
    const register = vi.fn().mockRejectedValue(
      new V197ApiError("Could not create an Orbit with those details.", 400),
    );
    const onAuthenticated = vi.fn();
    bindV197EntryAuth(document, { register, login: vi.fn() } as never, onAuthenticated);
    document.querySelector<HTMLFormElement>("#f4-signup-form")?.requestSubmit();
    await settle();

    expect(register).toHaveBeenCalledOnce();
    expect(onAuthenticated).not.toHaveBeenCalled();
    const status = document.querySelector("#f4-status");
    expect(status?.textContent).toContain("already has an Orbit");
    expect(document.querySelector<HTMLInputElement>("#f4-signin-email")?.value).toBe("star@nurapp.dev");
    expect(document.querySelector<HTMLInputElement>("#f4-signin-password")?.value).toBe("orbit-pass-9");
    expect(status?.classList.contains("nur-v197-auth-error")).toBe(true);
    expect(document.querySelector<HTMLElement>("#nur-v197-auth-wait")?.hidden).toBe(true);
  });

  it("a 429 shows the clear retry line and never fakes auth state", async () => {
    const document = signupDocument();
    const register = vi.fn().mockRejectedValue(
      new V197ApiError("Too many attempts. Please wait and try again.", 429),
    );
    const onAuthenticated = vi.fn();
    bindV197EntryAuth(document, { register, login: vi.fn() } as never, onAuthenticated);
    document.querySelector<HTMLFormElement>("#f4-signup-form")?.requestSubmit();
    await settle();

    expect(onAuthenticated).not.toHaveBeenCalled();
    const status = document.querySelector("#f4-status");
    expect(status?.textContent).toContain("Too many attempts");
    expect(status?.textContent).toContain("Wait a few minutes, then try once.");
  });
});
