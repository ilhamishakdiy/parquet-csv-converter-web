"use client";

import { Eye, Loader2, RefreshCw } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { displayValue, formatNumber } from "@/lib/format";
import type { Plan } from "@/lib/types";
import { StepCard } from "./step-card";
import { ErrorAlert, WarningsList } from "./warnings-list";

/** FR-07: exact filenames, part counts, rows per part, largest group and warnings. */
export function PreviewStep({
  disabled,
  canPreview,
  invalidReason,
  onPreview,
  previewing,
  error,
  plan,
  stale,
}: {
  disabled: boolean;
  canPreview: boolean;
  invalidReason: string | null;
  onPreview: () => void;
  previewing: boolean;
  error: string | null;
  plan: Plan | null;
  stale: boolean;
}) {
  return (
    <StepCard
      step={3}
      title="Preview the files"
      description="Check the exact filenames and row counts before anything is written."
      disabled={disabled}
      action={
        <Button onClick={onPreview} disabled={!canPreview || previewing} variant={plan && !stale ? "outline" : "default"}>
          {previewing ? <Loader2 className="animate-spin" /> : plan ? <RefreshCw /> : <Eye />}
          {plan ? "Refresh preview" : "Preview"}
        </Button>
      }
    >
      {invalidReason && <p className="text-sm text-muted-foreground">{invalidReason}</p>}
      {previewing && (
        <p className="text-sm text-muted-foreground">
          Counting rows per filter value and group. Large files can take a minute.
        </p>
      )}
      <ErrorAlert message={error} />
      {plan && (
        <div className={stale ? "space-y-4 opacity-50" : "space-y-4"}>
          {stale && (
            <p className="text-sm font-medium text-amber-700 dark:text-amber-300">
              The settings changed since this preview. Refresh the preview before converting.
            </p>
          )}
          <dl className="grid grid-cols-2 gap-3 rounded-lg border bg-muted/40 p-3 text-sm sm:grid-cols-4">
            <Stat label="CSV files" value={formatNumber(plan.part_count)} />
            <Stat label="Total rows" value={formatNumber(plan.total_rows)} />
            {plan.filter_column && <Stat label={`Values of ${plan.filter_column}`} value={formatNumber(plan.filter_count)} />}
            {plan.mode === "group" && <Stat label="Groups" value={formatNumber(plan.group_count)} />}
            {plan.mode !== "single" && <Stat label="Row limit" value={formatNumber(plan.row_limit)} />}
          </dl>
          {plan.largest_group && (
            <p className="text-sm">
              Largest group:{" "}
              <span className="font-mono text-xs">
                {plan.filter_column && `${plan.filter_column}=${displayValue(plan.largest_group.filter_value)}, `}
                {Object.entries(plan.largest_group.values)
                  .map(([k, v]) => `${k}=${displayValue(v)}`)
                  .join(", ")}
              </span>{" "}
              with <strong className="tabular-nums">{formatNumber(plan.largest_group.rows)}</strong> rows.
            </p>
          )}
          <WarningsList warnings={plan.warnings} />
          <ScrollArea className="h-72 rounded-lg border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>File name</TableHead>
                  {plan.filter_column && <TableHead>{plan.filter_column}</TableHead>}
                  {plan.mode === "group" && <TableHead className="text-right">Groups</TableHead>}
                  <TableHead className="text-right">Rows</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {plan.files.map((f) => (
                  <TableRow key={f.part_id}>
                    <TableCell className="font-mono text-xs">
                      {f.file_name}
                      {f.oversized && (
                        <Badge variant="destructive" className="ml-2">
                          oversized
                        </Badge>
                      )}
                    </TableCell>
                    {plan.filter_column && (
                      <TableCell className="text-xs">{displayValue(f.filter_value, f.filter_is_null)}</TableCell>
                    )}
                    {plan.mode === "group" && <TableCell className="text-right tabular-nums">{formatNumber(f.groups)}</TableCell>}
                    <TableCell className="text-right tabular-nums">{formatNumber(f.rows)}</TableCell>
                  </TableRow>
                ))}
                <TableRow>
                  <TableCell className="font-mono text-xs text-muted-foreground">{plan.catalog_file}</TableCell>
                  <TableCell colSpan={3} className="text-xs text-muted-foreground">
                    Lookup index: {plan.catalog_headers.join(", ")}
                  </TableCell>
                </TableRow>
              </TableBody>
            </Table>
          </ScrollArea>
          {plan.files_truncated && (
            <p className="text-xs text-muted-foreground">
              Showing the first {formatNumber(plan.files.length)} of {formatNumber(plan.part_count)} files.
            </p>
          )}
        </div>
      )}
    </StepCard>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0">
      <dt className="truncate text-xs text-muted-foreground">{label}</dt>
      <dd className="font-medium tabular-nums">{value}</dd>
    </div>
  );
}
