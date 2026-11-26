"use client";

import { useState } from "react";
import { Ban, CheckCircle2, Copy, FileSpreadsheet, FolderOpen, Loader2, RotateCcw, XCircle } from "lucide-react";
import { ApiError, api } from "@/lib/api";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { displayValue, formatDuration, formatNumber } from "@/lib/format";
import { roundEta, type Eta } from "@/lib/eta";
import type { JobResult, JobStatus } from "@/lib/types";
import { ErrorAlert, WarningsList } from "./warnings-list";

const STAGES: Record<string, string> = {
  starting: "Starting",
  checking_source: "Checking the source file",
  exporting: "Writing CSV parts",
  validating: "Verifying row counts",
  writing_catalog: "Writing _catalog.csv",
  publishing: "Publishing files",
};

/** FR-08: stage, completed parts, elapsed time, progress, errors and cancellation. */
export function JobProgress({
  status,
  eta,
  onCancel,
  cancelling,
  onReset,
}: {
  status: JobStatus;
  eta: Eta | null;
  onCancel: () => void;
  cancelling: boolean;
  onReset: () => void;
}) {
  const running = status.state === "running";
  const pct = Math.round(status.progress * 100);
  return (
    <Card className={running ? "ring-2 ring-primary/30" : status.state === "failed" ? "border-destructive/50" : undefined}>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          {running && <Loader2 className="size-5 animate-spin" />}
          {status.state === "failed" && <XCircle className="size-5 text-destructive" />}
          {status.state === "cancelled" && <Ban className="size-5 text-muted-foreground" />}
          {running ? "Converting…" : status.state === "failed" ? "Conversion failed" : status.state === "cancelled" ? "Conversion cancelled" : "Finishing…"}
        </CardTitle>
        <CardDescription>
          {running
            ? "You can keep this page open. Closing the converter window stops the conversion."
            : "No files or catalogue were published."}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="space-y-2">
          <div className="flex justify-between text-sm">
            <span>{STAGES[status.stage] ?? status.stage}</span>
            <span className="tabular-nums text-muted-foreground">{pct}%</span>
          </div>
          <Progress value={pct} className="h-2" />
        </div>
        <dl className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-3">
          <div>
            <dt className="text-xs text-muted-foreground">Elapsed</dt>
            <dd className="tabular-nums">{formatDuration(status.elapsed_seconds)}</dd>
          </div>
          <div>
            <dt className="text-xs text-muted-foreground">Parts verified</dt>
            <dd className="tabular-nums">
              {formatNumber(status.parts_completed)}
              {status.parts_total != null && ` / ${formatNumber(status.parts_total)}`}
            </dd>
          </div>
          {running && (
            <div>
              <dt className="text-xs text-muted-foreground">Time remaining (estimate)</dt>
              <dd className="tabular-nums">
                {eta === null ? (
                  <span className="text-muted-foreground">Calculating…</span>
                ) : (
                  <>
                    About {formatDuration(roundEta(eta.seconds))}
                    <span className="block text-xs text-muted-foreground">
                      Expected to finish around{" "}
                      {new Date(eta.finishAt).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                    </span>
                  </>
                )}
              </dd>
            </div>
          )}
        </dl>
        {status.error && status.state === "failed" && (
          <Alert variant="destructive">
            <XCircle />
            <AlertTitle>What went wrong</AlertTitle>
            <AlertDescription>{status.error.message}</AlertDescription>
          </Alert>
        )}
        {running ? (
          <Button variant="destructive" onClick={onCancel} disabled={cancelling}>
            {cancelling ? <Loader2 className="animate-spin" /> : <Ban />} Cancel conversion
          </Button>
        ) : (
          <Button variant="outline" onClick={onReset}>
            <RotateCcw /> Back to settings
          </Button>
        )}
      </CardContent>
    </Card>
  );
}

/** FR-09 / FR-10: actual outputs, rows, duration, integrity checks, oversized parts and catalog path. */
export function JobResults({ result, filterColumn, onReset }: { result: JobResult; filterColumn: string | null; onReset: () => void }) {
  return (
    <Card className="border-emerald-300">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <CheckCircle2 className="size-5 text-emerald-600" /> Conversion complete
        </CardTitle>
        <CardDescription>
          {formatNumber(result.file_count)} CSV file(s) and _catalog.csv were verified and published in{" "}
          {formatDuration(result.duration_seconds)}.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <OpenButtons jobId={result.job_id} />
        <dl className="grid gap-3 rounded-lg border bg-muted/40 p-3 text-sm sm:grid-cols-2">
          <PathRow label="Destination folder" value={result.destination} />
          <PathRow label="Catalogue" value={result.catalog_path} />
          <div>
            <dt className="text-xs text-muted-foreground">Rows exported / source rows</dt>
            <dd className="tabular-nums">
              {formatNumber(result.total_rows)} / {formatNumber(result.source_rows)}
            </dd>
          </div>
          <div>
            <dt className="text-xs text-muted-foreground">Catalogue entries</dt>
            <dd className="tabular-nums">{formatNumber(result.catalog_rows)}</dd>
          </div>
        </dl>

        <div className="space-y-1">
          <h3 className="text-sm font-medium">Integrity checks</h3>
          <ul className="space-y-1 text-sm">
            {result.validation.checks.map((c) => (
              <li key={c.name} className="flex items-start gap-2">
                {c.passed ? <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-emerald-600" /> : <XCircle className="mt-0.5 size-4 shrink-0 text-destructive" />}
                {c.detail}
              </li>
            ))}
          </ul>
        </div>

        {result.oversized_files.length > 0 && (
          <p className="text-sm">
            <Badge variant="destructive">Oversized</Badge> {result.oversized_files.join(", ")}
          </p>
        )}
        <WarningsList warnings={result.warnings.filter((w) => w.severity !== "info")} />

        <ScrollArea className="h-72 rounded-lg border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>File</TableHead>
                {filterColumn && <TableHead>{filterColumn}</TableHead>}
                <TableHead className="text-right">Rows</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {result.files.map((f) => (
                <TableRow key={f.path}>
                  <TableCell className="font-mono text-xs" title={f.path}>
                    {f.file_name}
                    {f.oversized && (
                      <Badge variant="destructive" className="ml-2">
                        oversized
                      </Badge>
                    )}
                  </TableCell>
                  {filterColumn && <TableCell className="text-xs">{displayValue(f.filter_value, f.filter_is_null)}</TableCell>}
                  <TableCell className="text-right tabular-nums">{formatNumber(f.rows)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </ScrollArea>
        <p className="text-xs text-muted-foreground">
          CSV format: UTF-8, comma separated, one header row, standard quoting. Empty (NULL) values are written as an
          empty field; empty text is written as <span className="font-mono">&quot;&quot;</span>. Excel may change values
          such as leading zeros or long numbers when opening CSV files directly. Use Data → From Text/CSV to keep them as
          text.
        </p>
        <Button variant="outline" onClick={onReset}>
          <RotateCcw /> Convert another file
        </Button>
      </CardContent>
    </Card>
  );
}

function OpenButtons({ jobId }: { jobId: string }) {
  const [busy, setBusy] = useState<"folder" | "catalog" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const open = async (target: "folder" | "catalog") => {
    setBusy(target);
    setError(null);
    try {
      await api.openOutput(jobId, target);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err));
    } finally {
      setBusy(null);
    }
  };
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap gap-2">
        <Button onClick={() => open("folder")} disabled={busy !== null}>
          {busy === "folder" ? <Loader2 className="animate-spin" /> : <FolderOpen />} Open destination folder
        </Button>
        <Button variant="outline" onClick={() => open("catalog")} disabled={busy !== null}>
          {busy === "catalog" ? <Loader2 className="animate-spin" /> : <FileSpreadsheet />} Open _catalog.csv
        </Button>
      </div>
      <ErrorAlert message={error} />
    </div>
  );
}

function PathRow({ label, value }: { label: string; value: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <div className="min-w-0">
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="flex items-center gap-1">
        <span className="truncate font-mono text-xs" title={value}>
          {value}
        </span>
        <Button
          size="icon-xs"
          variant="ghost"
          aria-label={`Copy ${label}`}
          onClick={() => {
            void navigator.clipboard?.writeText(value).then(() => {
              setCopied(true);
              setTimeout(() => setCopied(false), 1500);
            });
          }}
        >
          {copied ? <CheckCircle2 className="text-emerald-600" /> : <Copy />}
        </Button>
      </dd>
    </div>
  );
}
