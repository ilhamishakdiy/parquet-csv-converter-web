"use client";

import { useEffect } from "react";
import { captureTokenFromHash } from "@/lib/api";

/** Saves the pairing token from #token=... on whichever page Start.bat opened. */
export function TokenCapture() {
  useEffect(() => {
    captureTokenFromHash();
  }, []);
  return null;
}
