import { useEffect, useRef, useState } from "react";
import { fetchJobStatus } from "../api/client";
import type { JobStatus } from "../types/recipe";

const TERMINAL: JobStatus[] = ["done", "failed"];
const POLL_INTERVAL_MS = 2000;

interface JobStreamState {
  status: JobStatus | null;
  message: string | null;
  error: string | null;
}

export function useJobStream(jobId: string | null): JobStreamState {
  const [state, setState] = useState<JobStreamState>({ status: null, message: null, error: null });
  const pollTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (!jobId) return;
    setState({ status: null, message: null, error: null });

    let cancelled = false;
    const stopPolling = () => {
      if (pollTimerRef.current) {
        clearInterval(pollTimerRef.current);
        pollTimerRef.current = null;
      }
    };

    const startPolling = () => {
      stopPolling();
      pollTimerRef.current = setInterval(async () => {
        try {
          const job = await fetchJobStatus(jobId);
          if (cancelled) return;
          setState({ status: job.status, message: job.stage_message, error: job.error });
          if (TERMINAL.includes(job.status)) stopPolling();
        } catch {
          // transient network hiccup while polling — keep retrying
        }
      }, POLL_INTERVAL_MS);
    };

    // EventSource first; if the browser can't establish/maintain it (e.g.
    // the connection drops when the phone locks), fall back to polling so
    // progress is never permanently lost.
    const source = new EventSource(`/api/jobs/${jobId}/events`);

    source.addEventListener("progress", (evt) => {
      if (cancelled) return;
      const data = JSON.parse((evt as MessageEvent).data);
      setState({ status: data.stage, message: data.message, error: data.status === "failed" ? data.message : null });
      if (TERMINAL.includes(data.stage)) {
        source.close();
        stopPolling();
      }
    });

    source.onerror = () => {
      source.close();
      if (!cancelled) startPolling();
    };

    return () => {
      cancelled = true;
      source.close();
      stopPolling();
    };
  }, [jobId]);

  return state;
}
