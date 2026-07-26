export const V197_EVENTS = {
  ready: "NUR:READY",
  phaseOneReadOnlyBlocked: "NUR:PHASE1:READ_ONLY_BLOCKED",
  phaseOneEntryBlocked: "NUR:PHASE1:ENTRY_BLOCKED",
  entryBegin: "NUR:ENTRY:BEGIN",
  authSignup: "NUR:AUTH:SIGNUP",
  authSignin: "NUR:AUTH:SIGNIN",
  sessionHydrate: "NUR:SESSION:HYDRATE",
  todayCheckinSubmit: "NUR:TODAY:CHECKIN_SUBMIT",
  talkSend: "NUR:TALK:SEND",
  talkStreamChunk: "NUR:TALK:STREAM_CHUNK",
  talkStreamDone: "NUR:TALK:STREAM_DONE",
  talkSaveToJournal: "NUR:TALK:SAVE_TO_JOURNAL",
  talkMakePlan: "NUR:TALK:MAKE_PLAN",
  talkMarkGlow: "NUR:TALK:MARK_GLOW",
  journalSave: "NUR:JOURNAL:SAVE",
  planStepToggle: "NUR:PLAN:STEP_TOGGLE",
  planMakeEasier: "NUR:PLAN:MAKE_EASIER",
  systemsLoad: "NUR:SYSTEMS:LOAD",
  systemsSelect: "NUR:SYSTEMS:SELECT",
  systemsAdd: "NUR:SYSTEMS:ADD",
  worldMap: "NUR:WORLD_TAB:MAP",
  worldOrbits: "NUR:WORLD_TAB:ORBITS",
  worldTimeline: "NUR:WORLD_TAB:TIMELINE",
  worldInsights: "NUR:WORLD_TAB:INSIGHTS",
  researchQuery: "NUR:RESEARCH:QUERY",
  researchRun: "NUR:RESEARCH:RUN",
  communityThreadCreate: "NUR:COMMUNITY:THREAD_CREATE",
  communityReplyCreate: "NUR:COMMUNITY:REPLY_CREATE",
  consultationStageSelect: "NUR:CONSULTATION:STAGE_SELECT",
  consultationContribute: "NUR:CONSULTATION:CONTRIBUTE",
  scopeSelect: "NUR:SCOPE:SELECT",
  capsuleCreate: "NUR:CAPSULE:CREATE",
  glowCreate: "NUR:GLOW:CREATE",
  composerAction: "NUR:COMPOSER:ACTION",
} as const;

export type V197BridgeEventName = (typeof V197_EVENTS)[keyof typeof V197_EVENTS];

export type V197NativeRoute =
  | "/"
  | "/auth"
  | "/onboarding"
  | "/today"
  | "/talk"
  | `/talk/${string}`
  | "/journal"
  | `/journal/${string}`
  | "/plan"
  | `/plan/${string}`
  | "/systems"
  | `/systems/${string}`
  | "/universe"
  | "/universe/life"
  | "/universe/map"
  | "/universe/orbits"
  | "/universe/timeline"
  | "/universe/insights"
  | "/universe/research"
  | "/universe/community"
  | "/universe/web-signals"
  | "/settings"
  | "/universe/omega"
  | "/universe/omega/review"
  | "/consultations"
  | `/consultations/${string}`
  | "/community"
  | `/community/${string}`
  | "/projects"
  | `/projects/${string}`
  | "/glow"
  | "/notifications"
  | `/universe/omega/why-changed/${string}`
  | `/capsule/${string}`;


const pageRoutes: Record<string, V197NativeRoute> = {
  today: "/today",
  talk: "/talk",
  journal: "/journal",
  plan: "/plan",
  systems: "/systems",
};

const worldRoutes: Record<string, V197NativeRoute> = {
  universe: "/systems",
  map: "/universe/map",
  orbits: "/universe/orbits",
  timeline: "/universe/timeline",
  insights: "/universe/insights",
  research: "/universe/research",
  community: "/universe/community",
  web: "/universe/web-signals",
};

export function routeForPage(page: string): V197NativeRoute | null {
  return pageRoutes[page] ?? null;
}

export function routeForWorldFocus(focus: string): V197NativeRoute | null {
  return worldRoutes[focus] ?? null;
}

export function emitBridgeEvent(name: V197BridgeEventName, detail: Record<string, unknown> = {}): void {
  window.dispatchEvent(new CustomEvent(name, { detail }));
}
