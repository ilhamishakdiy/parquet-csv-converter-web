"use client";

import { useState, type ReactNode } from "react";
import { Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ApiError, api } from "@/lib/api";
import type { BrowseResult } from "@/lib/types";

/** Asks the local converter to open a Windows Explorer dialog and returns the chosen path. */
export function BrowseButton({
  kind,
  initialPath,
  onPicked,
  onError,
  disabled,
  icon,
  variant = "outline",
  children,
}: {
  kind: "file" | "folder";
  initialPath?: string;
  onPicked: (path: string, result: BrowseResult) => void;
  onError: (message: string | null) => void;
  disabled?: boolean;
  icon?: ReactNode;
  variant?: "outline" | "link";
  children: ReactNode;
}) {
  const [waiting, setWaiting] = useState(false);
  return (
    <Button
      type="button"
      variant={variant}
      className={variant === "link" ? "h-auto px-0" : undefined}
      disabled={disabled || waiting}
      title={waiting ? "A Browse window is open. It may be behind the browser." : undefined}
      onClick={async () => {
        setWaiting(true);
        onError(null);
        try {
          const result = await api.browse(kind, initialPath);
          if (result.path) onPicked(result.path, result);
        } catch (err) {
          onError(err instanceof ApiError ? err.message : String(err));
        } finally {
          setWaiting(false);
        }
      }}
    >
      {waiting ? <Loader2 className="animate-spin" /> : icon}
      {children}
    </Button>
  );
}
