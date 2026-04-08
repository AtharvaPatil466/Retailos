/**
 * Offline-first sync hook for RetailOS dashboard.
 *
 * - Detects online/offline status
 * - Queues mutations in localStorage when offline
 * - Pushes queued operations to /api/sync/push on reconnect
 * - Pulls server changes via /api/sync/pull periodically
 * - Exposes sync status for UI indicators
 */

import { useState, useEffect, useCallback, useRef } from 'react';

const QUEUE_KEY = 'retailos_sync_queue';
const LAST_SYNC_KEY = 'retailos_last_sync';
const PULL_INTERVAL = 60_000; // Pull every 60s when online

function getQueue() {
  try {
    return JSON.parse(localStorage.getItem(QUEUE_KEY) || '[]');
  } catch {
    return [];
  }
}

function setQueue(queue) {
  localStorage.setItem(QUEUE_KEY, JSON.stringify(queue));
}

function getLastSync() {
  return parseFloat(localStorage.getItem(LAST_SYNC_KEY) || '0');
}

function setLastSync(ts) {
  localStorage.setItem(LAST_SYNC_KEY, String(ts));
}

let idCounter = 0;
function generateOpId() {
  idCounter += 1;
  return `cli-${Date.now()}-${idCounter}-${Math.random().toString(36).slice(2, 8)}`;
}

export default function useOfflineSync({ authToken = '', onPulledChanges = null } = {}) {
  const [isOnline, setIsOnline] = useState(navigator.onLine);
  const [pendingCount, setPendingCount] = useState(() => getQueue().length);
  const [isSyncing, setIsSyncing] = useState(false);
  const [lastSyncTime, setLastSyncTime] = useState(() => getLastSync());
  const [syncError, setSyncError] = useState(null);
  const pullTimerRef = useRef(null);

  // Track online/offline
  useEffect(() => {
    const goOnline = () => setIsOnline(true);
    const goOffline = () => setIsOnline(false);
    window.addEventListener('online', goOnline);
    window.addEventListener('offline', goOffline);
    return () => {
      window.removeEventListener('online', goOnline);
      window.removeEventListener('offline', goOffline);
    };
  }, []);

  const headers = authToken
    ? { 'Content-Type': 'application/json', Authorization: `Bearer ${authToken}` }
    : { 'Content-Type': 'application/json' };

  // Push queued operations to the server
  const pushSync = useCallback(async () => {
    const queue = getQueue();
    if (queue.length === 0) return;

    setIsSyncing(true);
    setSyncError(null);

    try {
      const res = await fetch('/api/sync/push', {
        method: 'POST',
        headers,
        body: JSON.stringify({
          operations: queue,
          device_id: `dashboard-${navigator.userAgent.slice(0, 20)}`,
          last_sync_timestamp: getLastSync(),
        }),
      });

      if (!res.ok) throw new Error(`Push failed: ${res.status}`);

      const data = await res.json();

      // Remove successfully processed operations from the queue
      const processedIds = new Set(
        data.results
          .filter((r) => r.status === 'ok' || r.status === 'already_processed')
          .map((r) => r.op_id)
      );

      const remaining = queue.filter((op) => !processedIds.has(op.op_id));
      setQueue(remaining);
      setPendingCount(remaining.length);

      if (data.server_timestamp) {
        setLastSync(data.server_timestamp);
        setLastSyncTime(data.server_timestamp);
      }
    } catch (err) {
      setSyncError(err.message);
    } finally {
      setIsSyncing(false);
    }
  }, [headers]);

  // Pull server-side changes
  const pullSync = useCallback(async () => {
    if (!isOnline) return;

    try {
      const since = getLastSync();
      const res = await fetch(`/api/sync/pull?since=${since}&limit=500`, { headers });
      if (!res.ok) return;

      const data = await res.json();

      if (data.server_timestamp) {
        setLastSync(data.server_timestamp);
        setLastSyncTime(data.server_timestamp);
      }

      // Notify the app about pulled changes
      if (onPulledChanges && data.changes) {
        const totalChanges =
          (data.counts?.products || 0) +
          (data.counts?.orders || 0) +
          (data.counts?.customers || 0);
        if (totalChanges > 0) {
          onPulledChanges(data.changes);
          window.dispatchEvent(new CustomEvent('retailos:data-changed'));
        }
      }
    } catch {
      // Silent fail for pulls — will retry next interval
    }
  }, [isOnline, headers, onPulledChanges]);

  // When coming back online, push then pull
  useEffect(() => {
    if (isOnline) {
      pushSync().then(() => pullSync());
    }
  }, [isOnline, pushSync, pullSync]);

  // Periodic pull when online
  useEffect(() => {
    if (isOnline) {
      pullTimerRef.current = setInterval(pullSync, PULL_INTERVAL);
    }
    return () => {
      if (pullTimerRef.current) clearInterval(pullTimerRef.current);
    };
  }, [isOnline, pullSync]);

  // Queue a mutation (used when offline OR as an optimistic write)
  const queueOperation = useCallback(
    (opType, entityType, entityId, data) => {
      const op = {
        op_id: generateOpId(),
        op_type: opType,
        entity_type: entityType,
        entity_id: entityId,
        data,
        client_timestamp: Date.now() / 1000,
      };

      const queue = getQueue();
      queue.push(op);
      setQueue(queue);
      setPendingCount(queue.length);

      // If online, push immediately
      if (navigator.onLine) {
        pushSync();
      }

      return op.op_id;
    },
    [pushSync]
  );

  // Force a full sync cycle
  const forceSync = useCallback(async () => {
    await pushSync();
    await pullSync();
  }, [pushSync, pullSync]);

  return {
    isOnline,
    isSyncing,
    pendingCount,
    lastSyncTime,
    syncError,
    queueOperation,
    forceSync,
    pushSync,
    pullSync,
  };
}
