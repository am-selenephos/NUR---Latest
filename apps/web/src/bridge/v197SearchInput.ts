/**
 * Search input support for the bridge-native Map, Orbit and Timeline surfaces.
 *
 * Each surface's paint function replaces its complete DOM tree. The measured
 * performance baseline records the resulting listener growth and main-thread
 * work, so search commits are intentionally settled before they trigger that
 * rebuild. Pending work is keyed by document and surface so route teardown can
 * cancel it instead of retaining a detached surface.
 */

export const V197_SEARCH_DEBOUNCE_MS = 140;

interface PendingSearchCommit {
  handle: ReturnType<typeof setTimeout>;
}

const pendingByDocument = new WeakMap<Document, Map<string, PendingSearchCommit>>();

function pendingFor(doc: Document): Map<string, PendingSearchCommit> {
  let pending = pendingByDocument.get(doc);
  if (!pending) {
    pending = new Map();
    pendingByDocument.set(doc, pending);
  }
  return pending;
}

export function cancelV197SearchCommit(doc: Document, surface: string): void {
  const pending = pendingByDocument.get(doc);
  const current = pending?.get(surface);
  if (!current) return;
  clearTimeout(current.handle);
  pending?.delete(surface);
  if (pending?.size === 0) pendingByDocument.delete(doc);
}

export function cancelAllV197SearchCommits(doc: Document): void {
  const pending = pendingByDocument.get(doc);
  if (!pending) return;
  for (const current of pending.values()) clearTimeout(current.handle);
  pendingByDocument.delete(doc);
}

export function scheduleV197SearchCommit(
  doc: Document,
  surface: string,
  value: string,
  commit: (nextValue: string) => void,
  waitMs = V197_SEARCH_DEBOUNCE_MS,
): void {
  cancelV197SearchCommit(doc, surface);
  const pending = pendingFor(doc);
  const handle = setTimeout(() => {
    pending.delete(surface);
    if (pending.size === 0) pendingByDocument.delete(doc);
    commit(value);
  }, waitMs);
  pending.set(surface, { handle });
}

interface SearchFocusSnapshot {
  selectionStart: number | null;
  selectionEnd: number | null;
}

export function captureV197SearchFocus(
  doc: Document,
  selector: string,
): SearchFocusSnapshot | null {
  const active = doc.activeElement;
  if (!active || active.tagName !== "INPUT" || !active.matches(selector)) return null;
  const input = active as HTMLInputElement;
  return {
    selectionStart: input.selectionStart,
    selectionEnd: input.selectionEnd,
  };
}

export function restoreV197SearchFocus(
  root: ParentNode,
  selector: string,
  snapshot: SearchFocusSnapshot | null,
): void {
  if (!snapshot) return;
  const input = root.querySelector<HTMLInputElement>(selector);
  if (!input) return;
  input.focus({ preventScroll: true });
  if (snapshot.selectionStart !== null && snapshot.selectionEnd !== null) {
    input.setSelectionRange(snapshot.selectionStart, snapshot.selectionEnd);
  }
}
