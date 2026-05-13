/**
 * Dashboard data cache — in-memory SWR-style cache with localStorage persistence.
 *
 * Provides stale-while-revalidate semantics:
 * - Returns cached data instantly if available and fresh (< TTL)
 * - Background-refreshes stale data while serving cache
 * - Falls back to localStorage for cross-session persistence
 *
 * Guards against infinite refresh loops:
 * - Minimum 30s cooldown between fetches for the same key
 * - In-flight request deduplication
 * - Stale flag auto-clears on fetch failure (no permanent "Updating..." state)
 * - Singleton fetch guard prevents concurrent fetches
 *
 * Usage:
 *   import { useCachedFetch } from '../lib/cache';
 *   const { data, loading, stale, error, refetch } = useCachedFetch('me-dashboard', fetchFn, []);
 */
import { useState, useEffect, useCallback, useRef } from 'react';

// ── In-memory cache store ────────────────────────────────
const _store = new Map();   // key → { data, fetchedAt }
const DEFAULT_TTL = 120_000; // 2 minutes (was 60s — too aggressive)

// ── In-flight dedup ──────────────────────────────────────
const _inflight = new Map(); // key → Promise

// ── Fetch cooldown tracker ───────────────────────────────
// Prevents re-fetching the same key within MIN_FETCH_INTERVAL
const _lastFetchAt = new Map(); // key → timestamp
const MIN_FETCH_INTERVAL = 30_000; // 30 seconds minimum between fetches

// ── Cache version — bump to invalidate all localStorage entries ──
const CACHE_VERSION = 'v9';
const LS_PREFIX = 'atrack_cache_';
const LS_VERSION_KEY = 'atrack_cache_version';

// Wipe all cached entries if the version changed (e.g. after a metric formula fix)
try {
  if (localStorage.getItem(LS_VERSION_KEY) !== CACHE_VERSION) {
    // Clear localStorage entries
    Object.keys(localStorage)
      .filter((k) => k.startsWith(LS_PREFIX))
      .forEach((k) => localStorage.removeItem(k));
    localStorage.setItem(LS_VERSION_KEY, CACHE_VERSION);
    // Also clear in-memory store so HMR/hot-reload doesn't serve stale data
    _store.clear();
  }
} catch {
  // localStorage unavailable — still clear memory
  _store.clear();
}

function lsGet(key) {
  try {
    const raw = localStorage.getItem(LS_PREFIX + key);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    return parsed?.data != null ? parsed : null;
  } catch {
    return null;
  }
}

function lsSet(key, data) {
  try {
    localStorage.setItem(LS_PREFIX + key, JSON.stringify({ data, fetchedAt: Date.now() }));
  } catch {
    // localStorage full or unavailable
  }
}

/**
 * Get cached entry if it exists.
 * Checks memory first, then localStorage fallback.
 * @returns {{ data: any, stale: boolean } | null}
 */
export function getCached(key, ttl = DEFAULT_TTL) {
  // Memory cache first
  const entry = _store.get(key);
  if (entry) {
    const age = Date.now() - entry.fetchedAt;
    return { data: entry.data, stale: age > ttl };
  }
  // localStorage fallback
  const ls = lsGet(key);
  if (ls) {
    // Hydrate memory cache from localStorage
    _store.set(key, ls);
    const age = Date.now() - ls.fetchedAt;
    return { data: ls.data, stale: age > ttl };
  }
  return null;
}

/**
 * Store data in both memory and localStorage.
 */
export function setCache(key, data) {
  const now = Date.now();
  const entry = { data, fetchedAt: now };
  _store.set(key, entry);
  _lastFetchAt.set(key, now);
  lsSet(key, data);
}

/**
 * Invalidate a specific cache key.
 */
export function invalidateCache(key) {
  _store.delete(key);
  try { localStorage.removeItem(LS_PREFIX + key); } catch {}
}

/**
 * Invalidate all cache entries.
 */
export function invalidateAll() {
  _store.clear();
  try {
    const keys = Object.keys(localStorage).filter(k => k.startsWith(LS_PREFIX));
    keys.forEach(k => localStorage.removeItem(k));
  } catch {}
}

/**
 * Check if a fetch is allowed (cooldown elapsed).
 */
function canFetch(key) {
  const last = _lastFetchAt.get(key);
  if (!last) return true;
  return (Date.now() - last) >= MIN_FETCH_INTERVAL;
}

/**
 * Prefetch data into cache (used for sidebar hover + post-login prefetch).
 * De-duplicates in-flight requests. Respects cooldown.
 * @param {string} key
 * @param {() => Promise<any>} fetchFn
 */
export async function prefetchCache(key, fetchFn) {
  const existing = getCached(key);
  if (existing && !existing.stale) return existing.data;

  // Respect cooldown
  if (!canFetch(key)) return existing?.data ?? null;

  // Deduplicate in-flight requests
  if (_inflight.has(key)) return _inflight.get(key);

  const promise = fetchFn()
    .then(data => {
      setCache(key, data);
      _inflight.delete(key);
      return data;
    })
    .catch(err => {
      _inflight.delete(key);
      throw err;
    });

  _inflight.set(key, promise);
  return promise;
}

/**
 * React hook: stale-while-revalidate data fetching.
 *
 * Guards against infinite loops:
 * - 30s minimum cooldown between fetches per key
 * - In-flight request deduplication
 * - Stale flag auto-clears after failed fetch (no permanent "Updating...")
 * - fetchRef prevents stale closure issues
 *
 * @param {string} key       Unique cache key
 * @param {() => Promise<any>} fetchFn  Async function returning data
 * @param {any[]} deps       Dependencies that trigger refetch
 * @param {{ ttl?: number }} opts  Options
 */
export function useCachedFetch(key, fetchFn, deps = [], opts = {}) {
  const ttl = opts.ttl ?? DEFAULT_TTL;
  const mountedRef = useRef(true);
  const fetchingRef = useRef(false);  // guard against concurrent fetches
  const fetchFnRef = useRef(fetchFn);
  fetchFnRef.current = fetchFn;

  // Initialize from cache (memory or localStorage)
  const cached = getCached(key, ttl);
  const [data, setData] = useState(cached?.data ?? null);
  const [loading, setLoading] = useState(!cached?.data);
  const [stale, setStale] = useState(cached?.stale ?? false);
  const [error, setError] = useState(null);

  const doFetch = useCallback(async (opts = {}) => {
    const { showLoading = false, bypassCooldown = false } = opts;

    // Guard: prevent concurrent fetches
    if (fetchingRef.current) return data;

    // Guard: respect cooldown (unless explicit bypass e.g. manual refresh)
    if (!bypassCooldown && !canFetch(key)) {
      return data;
    }

    if (showLoading) setLoading(true);
    setError(null);
    fetchingRef.current = true;

    // Deduplicate in-flight requests
    if (_inflight.has(key)) {
      try {
        const result = await _inflight.get(key);
        if (mountedRef.current) {
          setData(result);
          setStale(false);
          setLoading(false);
        }
        return result;
      } catch (e) {
        if (mountedRef.current) {
          setError(e);
          setStale(false);  // ← Clear stale on error to stop "Updating..."
          setLoading(false);
        }
        return data; // Return existing data on error
      } finally {
        fetchingRef.current = false;
      }
    }

    const promise = fetchFnRef.current();
    _inflight.set(key, promise);

    try {
      const result = await promise;
      _inflight.delete(key);
      if (mountedRef.current) {
        setData(result);
        setCache(key, result);
        setStale(false);
        setLoading(false);
      }
      return result;
    } catch (e) {
      _inflight.delete(key);
      if (mountedRef.current) {
        setError(e);
        setStale(false);  // ← Clear stale on error to stop "Updating..."
        setLoading(false);
      }
      return data; // Return existing data on error
    } finally {
      fetchingRef.current = false;
    }
  }, [key]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    mountedRef.current = true;
    const cached = getCached(key, ttl);

    if (cached?.data) {
      // Serve cached data immediately — zero wait
      setData(cached.data);
      setLoading(false);

      // Background refresh if stale AND cooldown allows
      if (cached.stale && canFetch(key)) {
        setStale(true);
        doFetch({ showLoading: false }).catch(() => {});
      } else {
        setStale(false);
      }
    } else {
      // No cache — fetch with loading state
      setLoading(true);
      doFetch({ showLoading: true }).catch(() => {});
    }

    return () => { mountedRef.current = false; };
  }, [key]); // eslint-disable-line react-hooks/exhaustive-deps

  const refetch = useCallback(() => {
    invalidateCache(key);
    _lastFetchAt.delete(key); // Clear cooldown for manual refresh
    return doFetch({ showLoading: true, bypassCooldown: true });
  }, [key, doFetch]);

  return { data, loading, stale, error, refetch };
}
