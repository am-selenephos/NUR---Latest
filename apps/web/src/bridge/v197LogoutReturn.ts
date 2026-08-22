const LOGOUT_ENTRY_KEY = "nur:v197:logout-entry";

type SessionMarkerStorage = Pick<Storage, "getItem" | "setItem" | "removeItem">;

export function markImmediateLogoutReturn(storage: SessionMarkerStorage = window.sessionStorage): void {
  storage.setItem(LOGOUT_ENTRY_KEY, "1");
}

export function consumeImmediateLogoutReturn(storage: SessionMarkerStorage = window.sessionStorage): boolean {
  const marked = storage.getItem(LOGOUT_ENTRY_KEY) === "1";
  storage.removeItem(LOGOUT_ENTRY_KEY);
  return marked;
}
