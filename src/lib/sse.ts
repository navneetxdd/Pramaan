import { getApiBase } from "./apiBase";

export type JobStreamEvent = {
  status?: string;
  progress?: number;
  message?: string;
  result?: Record<string, unknown>;
  error?: string;
  heartbeat?: boolean;
};

type SubscribeOptions = {
  onEvent: (event: JobStreamEvent) => void;
  onError?: (error: Error) => void;
  onOpen?: () => void;
};

export function subscribeJobEvents(
  jobId: string,
  { onEvent, onError, onOpen }: SubscribeOptions,
): () => void {
  let closed = false;
  let es: EventSource | null = null;
  let retryMs = 800;

  function connect() {
    if (closed) return;
    es?.close();
    es = new EventSource(`${getApiBase()}/api/v1/jobs/${jobId}/events`);

    es.onopen = () => {
      retryMs = 800;
      onOpen?.();
    };

    es.onmessage = (msg) => {
      try {
        const payload = JSON.parse(msg.data) as JobStreamEvent;
        onEvent(payload);
        if (
          payload.status &&
          ["completed", "failed", "cancelled", "interrupted"].includes(
            payload.status,
          )
        ) {
          cleanup();
        }
      } catch {
        onError?.(new Error("Invalid job event payload"));
      }
    };

    es.onerror = () => {
      es?.close();
      es = null;
      if (closed) return;
      window.setTimeout(connect, retryMs);
      retryMs = Math.min(retryMs * 1.5, 5000);
    };
  }

  function cleanup() {
    closed = true;
    es?.close();
    es = null;
  }

  connect();
  return cleanup;
}

export function waitForJobCompletion(
  jobId: string,
  timeoutMs = 120_000,
): Promise<JobStreamEvent> {
  return new Promise((resolve, reject) => {
    const timer = window.setTimeout(() => {
      unsubscribe();
      reject(new Error("Job timed out"));
    }, timeoutMs);

    const unsubscribe = subscribeJobEvents(jobId, {
      onEvent: (event) => {
        if (event.status === "completed") {
          window.clearTimeout(timer);
          unsubscribe();
          resolve(event);
        }
        if (
          event.status === "failed" ||
          event.status === "cancelled" ||
          event.status === "interrupted"
        ) {
          window.clearTimeout(timer);
          unsubscribe();
          reject(new Error(event.error || "Job failed"));
        }
      },
      onError: (err) => {
        window.clearTimeout(timer);
        unsubscribe();
        reject(err);
      },
    });
  });
}
