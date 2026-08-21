import {
  CORE_COPY,
  LOCALE_META,
  resolveLocale,
  type SupportedLocale,
} from "../lib/i18n";

export type WritingPreference = "default" | "roman" | "script";

export const V197_LOCALE_META = LOCALE_META.map(row => ({ ...row }));

type SlotCopy = {
  today: string;
  talk: string;
  journal: string;
  plan: string;
  systems: string;
  universe: string;
  map: string;
  orbits: string;
  timeline: string;
  insights: string;
  research: string;
  community: string;
  send: string;
};

const EN: SlotCopy = {
  today: "Today",
  talk: "Talk",
  journal: "Journal",
  plan: "Plan",
  systems: "Systems",
  universe: "Universe",
  map: "Map",
  orbits: "Orbits",
  timeline: "Timeline",
  insights: "Insights",
  research: "Research",
  community: "Community",
  send: "Send",
};

const SLOT_COPY: Partial<Record<SupportedLocale, SlotCopy>> = {
  en: EN,
  ur: {
    today: "Aaj",
    talk: "Baat",
    journal: "Journal",
    plan: "Plan",
    systems: "Systems",
    universe: "Kainaat",
    map: "Naqsha",
    orbits: "Orbits",
    timeline: "Waqt ki lakeer",
    insights: "Samajh",
    research: "Tehqeeq",
    community: "Community",
    send: "Bhej",
  },
  ko: {
    today: "오늘",
    talk: "대화",
    journal: "저널",
    plan: "계획",
    systems: "시스템",
    universe: "우주",
    map: "지도",
    orbits: "궤도",
    timeline: "타임라인",
    insights: "인사이트",
    research: "리서치",
    community: "커뮤니티",
    send: "보내기",
  },
  hi: { ...EN, today: "आज", talk: "बात", journal: "जर्नल", plan: "योजना", systems: "सिस्टम" },
  ar: { ...EN, today: "اليوم", talk: "تحدث", journal: "اليوميات", plan: "الخطة", systems: "الأنظمة" },
  fa: { ...EN, today: "امروز", talk: "گفتگو", journal: "یادداشت", plan: "برنامه", systems: "سامانه ها" },
  es: { ...EN, today: "Hoy", talk: "Hablar", journal: "Diario", plan: "Plan", systems: "Sistemas" },
  fr: { ...EN, today: "Aujourd'hui", talk: "Parler", journal: "Journal", plan: "Plan", systems: "Systemes" },
  "zh-Hans": { ...EN, today: "今天", talk: "对话", journal: "日志", plan: "计划", systems: "系统" },
};

function setText(document: Document, selector: string, value: string): void {
  document.querySelectorAll<HTMLElement>(selector).forEach(node => {
    node.textContent = value;
  });
}

function setPlaceholder(document: Document, selector: string, value: string): void {
  document.querySelectorAll<HTMLInputElement | HTMLTextAreaElement>(selector).forEach(node => {
    node.placeholder = value;
  });
}

function setDirectLabel(document: Document, selector: string, value: string): void {
  document.querySelectorAll<HTMLElement>(selector).forEach(control => {
    const labels = [...control.children].filter(
      child => child.tagName === "SPAN" && !child.classList.contains("nur-exact-mini-host"),
    );
    const label = labels[labels.length - 1];
    if (label) label.textContent = value;
  });
}

export function directionForPreference(locale: string, writingPreference: WritingPreference): "ltr" | "rtl" {
  const resolved = resolveLocale(locale);
  if (resolved === "ur" && writingPreference === "roman") return "ltr";
  return resolved === "ur" || resolved === "ar" || resolved === "fa" ? "rtl" : "ltr";
}

/**
 * Mutates only established V197 copy slots and document language metadata.
 * It does not alter classes, geometry, the master star, or the NUR wordmark.
 */
export function applyV197Locale(
  document: Document,
  rawLocale: string | null | undefined,
  writingPreference: WritingPreference = "default",
): void {
  const locale = resolveLocale(rawLocale);
  const copy = SLOT_COPY[locale] ?? EN;
  const direction = directionForPreference(locale, writingPreference);

  document.documentElement.lang = locale;
  document.documentElement.dir = direction;
  document.body.dataset.nurLocale = locale;
  document.body.dataset.nurWritingPreference = writingPreference;

  const pageLabels: Array<[string, string]> = [
    ["today", copy.today],
    ["talk", copy.talk],
    ["journal", copy.journal],
    ["plan", copy.plan],
    ["systems", copy.systems],
  ];
  for (const [page, label] of pageLabels) {
    setText(document, `[data-page="${page}"] .clean-nav-title`, label);
    setDirectLabel(document, `.mobile-tabs [data-page="${page}"]`, label);
  }

  const worldLabels: Array<[string, string]> = [
    ["universe", copy.universe],
    ["map", copy.map],
    ["orbits", copy.orbits],
    ["timeline", copy.timeline],
    ["insights", copy.insights],
  ];
  for (const [world, label] of worldLabels) {
    setDirectLabel(document, `[data-world-tab="${world}"]`, label);
  }

  setText(document, '[data-world-focus="research"] .clean-tool-button b', copy.research);
  setText(document, '[data-world-focus="community"] .clean-tool-button b', copy.community);
  setText(document, '[data-send="talk"] > span', copy.send);
  setText(document, '[data-send="today"] > span', copy.send);
  setPlaceholder(document, "#talk-input", CORE_COPY[locale].askPlaceholder);
  setPlaceholder(document, "#today-input", CORE_COPY[locale].askPlaceholder);
  setText(document, ".v172-boundary-current b", CORE_COPY[locale].privateBoundary);
}

export function ensureV197LanguageControls(
  document: Document,
  rawLocale: string | null | undefined,
  writingPreference: WritingPreference,
  save: (locale: SupportedLocale, writingPreference: WritingPreference) => Promise<void>,
  aiProvider = "disabled",
): void {
  const currentLocale = resolveLocale(rawLocale);
  const providerLabel = aiProvider === "openai"
    ? "OPENAI_CONFIGURED · server-side only"
    : "DISABLED · AI not connected";
  let topbarButton = document.querySelector<HTMLButtonElement>("#nur-v197-language-open");
  if (!topbarButton) {
    topbarButton = document.createElement("button");
    topbarButton.id = "nur-v197-language-open";
    topbarButton.type = "button";
    topbarButton.className = "nur-scope nur-v197-language-open";
    topbarButton.setAttribute("aria-label", "Choose NUR language");
    topbarButton.addEventListener("click", () => {
      document.querySelector<HTMLElement>("#scope-open")?.click();
      window.setTimeout(() => document.querySelector<HTMLSelectElement>("#nur-v197-locale")?.focus(), 0);
    });
    const scopeButton = document.querySelector("#scope-open");
    scopeButton?.parentElement?.insertBefore(topbarButton, scopeButton);
  }
  const currentMeta = V197_LOCALE_META.find(row => row.locale === currentLocale);
  topbarButton.textContent = currentMeta?.label ?? currentLocale;
  topbarButton.title = "Choose NUR language";

  const existingLocale = document.querySelector<HTMLSelectElement>("#nur-v197-locale");
  const existingWriting = document.querySelector<HTMLSelectElement>("#nur-v197-writing-preference");
  if (existingLocale && existingWriting) {
    existingLocale.value = currentLocale;
    existingWriting.value = writingPreference;
    setText(document, "#nur-v197-provider-status strong", providerLabel);
    return;
  }

  const chamber = document.querySelector<HTMLElement>("#scope-modal .scope-modal");
  if (!chamber) return;
  const section = document.createElement("section");
  section.id = "nur-v197-language-settings";
  section.className = "scope-options";
  section.setAttribute("aria-labelledby", "nur-v197-language-title");

  const title = document.createElement("h3");
  title.id = "nur-v197-language-title";
  title.textContent = "Language and writing";
  const note = document.createElement("p");
  note.textContent = "Saved privately. NUR uses this language for interface copy and Talk.";

  const providerStatus = document.createElement("div");
  providerStatus.id = "nur-v197-provider-status";
  providerStatus.className = "nur-v197-provider-status";
  const providerTitle = document.createElement("span");
  providerTitle.textContent = "AI provider status";
  const providerValue = document.createElement("strong");
  providerValue.textContent = providerLabel;
  const providerNote = document.createElement("small");
  providerNote.textContent = aiProvider === "openai"
    ? "Talk calls OpenAI through the NUR backend. No key is sent to this browser."
    : "Run the local OpenAI setup, then start NUR in openai mode.";
  providerStatus.append(providerTitle, providerValue, providerNote);

  const localeLabel = document.createElement("label");
  localeLabel.setAttribute("for", "nur-v197-locale");
  localeLabel.textContent = "Language";
  const localeSelect = document.createElement("select");
  localeSelect.id = "nur-v197-locale";
  localeSelect.className = "scope-option nur-v197-select";
  localeSelect.setAttribute("aria-label", "NUR language");
  V197_LOCALE_META.forEach(row => {
    const option = document.createElement("option");
    option.value = row.locale;
    option.textContent = `${row.label} · ${row.status === "polished_beta" ? "beta reviewed" : "draft"}`;
    localeSelect.append(option);
  });
  localeSelect.value = currentLocale;
  const localeShell = document.createElement("div");
  localeShell.className = "nur-v197-select-shell";
  localeShell.append(localeSelect);

  const writingLabel = document.createElement("label");
  writingLabel.setAttribute("for", "nur-v197-writing-preference");
  writingLabel.textContent = "Writing preference";
  const writingSelect = document.createElement("select");
  writingSelect.id = "nur-v197-writing-preference";
  writingSelect.className = "scope-option nur-v197-select";
  writingSelect.setAttribute("aria-label", "NUR writing preference");
  (["default", "roman", "script"] as const).forEach(value => {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = value === "roman" ? "Roman / transliterated" : value === "script" ? "Native script" : "Locale default";
    writingSelect.append(option);
  });
  writingSelect.value = writingPreference;
  const writingShell = document.createElement("div");
  writingShell.className = "nur-v197-select-shell";
  writingShell.append(writingSelect);

  const saveButton = document.createElement("button");
  saveButton.id = "nur-v197-language-save";
  saveButton.type = "button";
  saveButton.className = "scope-option";
  saveButton.textContent = "Save language";
  const status = document.createElement("p");
  status.id = "nur-v197-language-status";
  status.setAttribute("aria-live", "polite");

  saveButton.addEventListener("click", async () => {
    const locale = resolveLocale(localeSelect.value);
    const preference = writingSelect.value as WritingPreference;
    saveButton.disabled = true;
    saveButton.setAttribute("aria-busy", "true");
    status.textContent = "Saving privately…";
    try {
      await save(locale, preference);
      applyV197Locale(document, locale, preference);
      const label = V197_LOCALE_META.find(row => row.locale === locale)?.label ?? locale;
      if (topbarButton) topbarButton.textContent = label;
      status.textContent = `Saved: ${V197_LOCALE_META.find(row => row.locale === locale)?.label ?? locale}.`;
    } catch (error) {
      status.textContent = error instanceof Error ? error.message : "Language could not be saved.";
    } finally {
      saveButton.disabled = false;
      saveButton.removeAttribute("aria-busy");
    }
  });

  section.append(
    title,
    note,
    providerStatus,
    localeLabel,
    localeShell,
    writingLabel,
    writingShell,
    saveButton,
    status,
  );
  chamber.append(section);
}
