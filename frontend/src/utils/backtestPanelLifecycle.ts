interface PendingPanelFlush {
  promise: Promise<void>;
  flush: () => Promise<void> | void;
}

const pendingFlushes = new Map<string, PendingPanelFlush>();

/** Keep a panel's next drawing hydration behind its outgoing save. */
export function registerPendingPanelFlush(
  scopeKey: string,
  flush: () => Promise<void> | void
): Promise<void> {
  const previous = pendingFlushes.get(scopeKey);
  const next = previous
    ? previous.promise.then(() => flush())
    : Promise.resolve().then(() => flush());
  const entry: PendingPanelFlush = { promise: next, flush };
  pendingFlushes.set(scopeKey, entry);
  void next.then(() => {
    if (pendingFlushes.get(scopeKey) === entry) pendingFlushes.delete(scopeKey);
  }, () => {
    // Keep failed flushes addressable so a remounted panel can retry them.
  });
  return next;
}

export async function waitForPendingPanelFlush(scopeKey: string): Promise<void> {
  await pendingFlushes.get(scopeKey)?.promise;
}

/** Discard a rejected outgoing draft only after an explicit user choice. */
export function discardPendingPanelFlush(scopeKey: string): void {
  pendingFlushes.delete(scopeKey);
}

export function retryPendingPanelFlush(scopeKey: string): Promise<void> {
  const entry = pendingFlushes.get(scopeKey);
  if (!entry) return Promise.resolve();
  const retry = entry.promise.then(
    () => undefined,
    () => entry.flush()
  );
  const nextEntry: PendingPanelFlush = { ...entry, promise: retry };
  pendingFlushes.set(scopeKey, nextEntry);
  void retry.then(() => {
    if (pendingFlushes.get(scopeKey) === nextEntry) pendingFlushes.delete(scopeKey);
  }, () => {
    // Keep the draft flush available until it succeeds or the page is left.
  });
  return retry;
}

/** Replace one mounted chart's subscriptions without stale cleanup removing its successor. */
export function registerPanelSubscription(
  subscriptions: Map<string, () => void>,
  panelId: string,
  unsubscribe: () => void
): () => void {
  subscriptions.get(panelId)?.();
  let active = true;
  const detach = () => {
    if (!active) return;
    active = false;
    unsubscribe();
    if (subscriptions.get(panelId) === detach) subscriptions.delete(panelId);
  };
  subscriptions.set(panelId, detach);
  return detach;
}
