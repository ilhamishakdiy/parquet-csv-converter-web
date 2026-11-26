"use client";

import { useState } from "react";
import Link from "next/link";
import { CheckCircle2, Loader2, PlugZap, ShieldAlert } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { setToken } from "@/lib/api";
import type { ConnectionState } from "@/hooks/use-connection";

export function ConnectionBadge({ conn }: { conn: ConnectionState }) {
  if (conn.status === "ready")
    return (
      <Badge variant="secondary" className="gap-1">
        <CheckCircle2 className="size-3 text-emerald-600" /> Converter connected (v{conn.health?.api_version})
      </Badge>
    );
  if (conn.status === "checking")
    return (
      <Badge variant="outline" className="gap-1">
        <Loader2 className="size-3 animate-spin" /> Checking…
      </Badge>
    );
  return (
    <Badge variant="destructive" className="gap-1">
      <PlugZap className="size-3" /> {conn.status === "unpaired" ? "Not paired" : "Not connected"}
    </Badge>
  );
}

/** FR-01: guided setup while the local converter is unreachable or unpaired. */
export function SetupGuide({ conn }: { conn: ConnectionState }) {
  const [code, setCode] = useState("");
  if (conn.status === "ready" || conn.status === "checking") return null;
  const unpaired = conn.status === "unpaired";
  return (
    <Card className="border-destructive/40">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <ShieldAlert className="size-5 text-destructive" />
          {unpaired ? "Reconnect this page to the converter" : "Start the converter on this PC"}
        </CardTitle>
        <CardDescription>
          Your data never leaves this computer. This page only talks to the converter running locally at
          127.0.0.1:8765.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4 text-sm">
        {unpaired ? (
          <p>
            The converter is running, but this page is not paired with it (each launch uses a new security code).
            Double-click <strong>Start.bat</strong> again. It reopens this page already paired.
          </p>
        ) : (
          <ol className="list-decimal space-y-2 pl-5">
            <li>
              Open the converter folder you extracted from the approved ZIP and double-click <strong>Start.bat</strong>.
              The first launch installs what it needs and takes a minute or two.
            </li>
            <li>Keep the black converter window open while you work. Closing it stops the converter.</li>
            <li>
              If the browser asks to allow access to <strong>devices on your local network</strong>, choose{" "}
              <strong>Allow</strong>.
            </li>
            <li>This page reconnects automatically once the converter is running.</li>
          </ol>
        )}
        <details className="rounded-md border p-3">
          <summary className="cursor-pointer font-medium">Paste a pairing code manually</summary>
          <div className="mt-3 flex items-end gap-2">
            <div className="flex-1 space-y-1">
              <Label htmlFor="pair-code">Pairing code (the text after #token= in the address Start.bat opened)</Label>
              <Input id="pair-code" value={code} onChange={(e) => setCode(e.target.value)} autoComplete="off" />
            </div>
            <Button
              disabled={!code.trim()}
              onClick={() => {
                setToken(code);
                setCode("");
                conn.refresh();
              }}
            >
              Pair
            </Button>
          </div>
        </details>
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" onClick={conn.refresh}>
            Check again
          </Button>
          <Button asChild variant="link">
            <Link href="/start/">First time? Read How to start and download the converter</Link>
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
