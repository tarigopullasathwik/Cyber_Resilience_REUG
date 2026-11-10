import { useCallback, useEffect, useRef, useState } from "react";
import { api, jobSocketUrl } from "./api";

export function useFetch(path, { poll = 0, enabled = true } = {}) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(Boolean(path && enabled));
  const mounted = useRef(true);
  const firstLoad = useRef(true);

  const refresh = useCallback(async () => {
    if (!path || !enabled) return;
    try {
      if (firstLoad.current) setLoading(true);
      const payload = await api.raw(path);
      if (!mounted.current) return;
      setData(payload);
      setError(null);
    } catch (exc) {
      if (!mounted.current) return;
      setError(exc);
    } finally {
      if (!mounted.current) return;
      setLoading(false);
      firstLoad.current = false;
    }
  }, [path, enabled]);

  useEffect(() => {
    mounted.current = true;
    firstLoad.current = true;
    if (!path || !enabled) {
      setLoading(false);
      return undefined;
    }
    refresh();
    if (!poll) return () => { mounted.current = false; };
    const timer = setInterval(refresh, poll);
    return () => {
      mounted.current = false;
      clearInterval(timer);
    };
  }, [path, poll, enabled, refresh]);

  return { data, error, loading, refresh, setData };
}

export function useJob(jobId, onDone) {
  const [job, setJob] = useState(null);
  const doneRef = useRef(false);
  const callbackRef = useRef(onDone);
  callbackRef.current = onDone;

  useEffect(() => {
    doneRef.current = false;
    if (!jobId) {
      setJob(null);
      return undefined;
    }
    let socket = null;
    let timer = null;
    let cancelled = false;

    const finish = (next) => {
      if (cancelled) return;
      setJob(next);
      if (["completed", "failed"].includes(next.status) && !doneRef.current) {
        doneRef.current = true;
        callbackRef.current?.(next);
      }
    };

    const startPolling = () => {
      if (timer) return;
      timer = setInterval(async () => {
        try {
          const next = await api.job(jobId);
          finish(next);
          if (["completed", "failed"].includes(next.status)) clearInterval(timer);
        } catch {
          /* transient network error; keep polling */
        }
      }, 900);
    };

    try {
      socket = new WebSocket(jobSocketUrl(jobId));
      socket.onmessage = (event) => {
        try {
          const next = JSON.parse(event.data);
          if (next.error && !next.status) return;
          finish(next);
          if (["completed", "failed"].includes(next.status)) socket.close();
        } catch {
          /* fall back to polling below */
        }
      };
      socket.onerror = startPolling;
      socket.onclose = () => {
        if (!doneRef.current) startPolling();
      };
    } catch {
      startPolling();
    }

    return () => {
      cancelled = true;
      if (socket) socket.close();
      if (timer) clearInterval(timer);
    };
  }, [jobId]);

  return job;
}

export function useDebouncedValue(value, delay = 300) {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(timer);
  }, [value, delay]);
  return debounced;
}
