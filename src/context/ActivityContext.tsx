import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

export type ActivityMode = "idle" | "working" | "success" | "error";

type ActivityContextValue = {
  mode: ActivityMode;
  message: string | null;
  setWorking: (message?: string) => void;
  setSuccess: (message?: string) => void;
  setError: (message?: string) => void;
  setIdle: () => void;
};

const ActivityContext = createContext<ActivityContextValue | null>(null);

export function ActivityProvider({ children }: { children: ReactNode }) {
  const [mode, setMode] = useState<ActivityMode>("idle");
  const [message, setMessage] = useState<string | null>(null);

  const setIdle = useCallback(() => {
    setMode("idle");
    setMessage(null);
  }, []);

  const setWorking = useCallback((msg?: string) => {
    setMode("working");
    setMessage(msg ?? null);
  }, []);

  const setSuccess = useCallback((msg?: string) => {
    setMode("success");
    setMessage(msg ?? null);
  }, []);

  const setError = useCallback((msg?: string) => {
    setMode("error");
    setMessage(msg ?? null);
  }, []);

  useEffect(() => {
    if (mode !== "success" && mode !== "error") return;
    const timer = window.setTimeout(() => setIdle(), mode === "success" ? 2400 : 3200);
    return () => window.clearTimeout(timer);
  }, [mode, setIdle]);

  const value = useMemo(
    () => ({ mode, message, setWorking, setSuccess, setError, setIdle }),
    [mode, message, setWorking, setSuccess, setError, setIdle],
  );

  return <ActivityContext.Provider value={value}>{children}</ActivityContext.Provider>;
}

export function useActivity() {
  const ctx = useContext(ActivityContext);
  if (!ctx) throw new Error("useActivity must be used within ActivityProvider");
  return ctx;
}
