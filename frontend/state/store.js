const state = { sessionId: null, activePlanId: null, uiState: "initializing" };
const listeners = new Set();

export const getState = () => ({ ...state });

export function setState(patch) {
  Object.assign(state, patch);
  const snap = getState();
  for (const fn of listeners) fn(snap);
}

export function subscribe(fn) {
  listeners.add(fn);
  fn(getState());
  return () => listeners.delete(fn);
}
