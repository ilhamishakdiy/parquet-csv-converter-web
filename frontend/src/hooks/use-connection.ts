"use client";

import { useCallback, useEffect, useState } from "react";
import { api, captureTokenFromHash } from "@/lib/api";
import type { Health } from "@/lib/types";

export type ConnectionState = {
  status: "checking" | "offline" | "unpaired" | "ready";
  health: Health | null;
  refresh: () => void;
};

/** Polls GET /health: fast while disconnected, slow once connected. */
export function useConnection(): ConnectionState {
  const [status, setStatus] = useState<ConnectionState["status"]>("checking");
  const [health, setHealth] = useState<Health | null>(null);
  const [nonce, setNonce] = useState(0);

  useEffect(() => {
    captureTokenFromHash();
    let stop = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const check = async () => {
      let next: ConnectionState["status"] = "offline";
      let h: Health | null = null;
      try {
        h = await api.health();
        next = h.paired ? "ready" : "unpaired";
      } catch {
        h = null;
      }
      if (stop) return;
      setHealth(h);
      setStatus(next);
      timer = setTimeout(check, next === "ready" ? 10_000 : 3_000);
    };
    void check();
    return () => {
      stop = true;
      clearTimeout(timer);
    };
  }, [nonce]);

  const refresh = useCallback(() => setNonce((n) => n + 1), []);
  return { status, health, refresh };
}
