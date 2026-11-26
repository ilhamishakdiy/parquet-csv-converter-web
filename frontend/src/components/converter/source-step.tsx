"use client";

import { useState } from "react";
import { File as FileIcon, FileSearch, FolderOpen, Loader2 } from "lucide-react";
import { BrowseButton } from "./browse-button";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { formatBytes, formatNumber } from "@/lib/format";
import type { SourceInfo } from "@/lib/types";
import { StepCard } from "./step-card";
import { ErrorAlert } from "./warnings-list";

/** FR-02 / FR-03: local source path and metadata-only inspection. */
export function SourceStep({
  disabled,
  path,
  onPathChange,
  onInspect,
  onBrowsed,
  onBrowseError,
  inspecting,
  error,
  source,
  stale,
  approvedRoots,
}: {
  disabled: boolean;
  path: string;
  onPathChange: (v: string) => void;
  onInspect: () => void;
  onBrowsed: (path: string) => void;
  onBrowseError: (message: string | null) => void;
  inspecting: boolean;
  error: string | null;
  source: SourceInfo | null;
  stale: boolean;
  approvedRoots?: string[];
}) {
  const [choice, setChoice] = useState<{ file: string; folder: string; count: number } | null>(null);
  return (
    <StepCard
      step={1}
      title="Choose the Parquet source"
      description="Paste the full path of a .parquet file, or of a folder of .parquet shards (e.g. a BigQuery export). Nothing is uploaded."
      disabled={disabled}
    >
      <form
        className="flex flex-col gap-2 sm:flex-row sm:items-end"
        onSubmit={(e) => {
          e.preventDefault();
          onInspect();
        }}
      >
        <div className="flex-1 space-y-1.5">
          <Label htmlFor="source-path">Source file or folder</Label>
          <Input
            id="source-path"
            placeholder="e.g. C:\Users\you\Documents\sales_nov2026.parquet  or  C:\Users\you\Documents\bq_export"
            value={path}
            onChange={(e) => onPathChange(e.target.value)}
            spellCheck={false}
            autoComplete="off"
            className="font-mono text-sm"
          />
        </div>
        <Button type="submit" disabled={!path.trim() || inspecting}>
          {inspecting ? <Loader2 className="animate-spin" /> : <FileSearch />}
          Inspect
        </Button>
      </form>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <BrowseButton
          kind="file"
          initialPath={path}
          onPicked={(p, r) => {
            if (r.folder && r.folder_parquet_count > 1) {
              setChoice({ file: p, folder: r.folder, count: r.folder_parquet_count });
            } else {
              setChoice(null);
              onBrowsed(p);
            }
          }}
          onError={onBrowseError}
          icon={<FolderOpen />}
          disabled={inspecting}
        >
          Browse…
        </BrowseButton>
        <span className="text-xs text-muted-foreground">
          Pick a file. For a sharded export, pick any one shard. Or{" "}
          <BrowseButton
            kind="folder"
            variant="link"
            initialPath={path}
            onPicked={(p) => {
              setChoice(null);
              onBrowsed(p);
            }}
            onError={onBrowseError}
            disabled={inspecting}
          >
            pick a folder instead
          </BrowseButton>
          . If the Explorer window doesn&apos;t appear, check the taskbar.
        </span>
      </div>
      {choice && (
        <div className="space-y-2 rounded-lg border border-primary/30 bg-muted/40 p-3 text-sm">
          <p>
            <span className="font-mono text-xs">{choice.folder}</span> contains{" "}
            <strong>{formatNumber(choice.count)}</strong> Parquet files. Convert them all together, or only the file
            you picked?
          </p>
          <div className="flex flex-wrap gap-2">
            <Button
              onClick={() => {
                setChoice(null);
                onBrowsed(choice.folder);
              }}
            >
              <FolderOpen /> Use all {formatNumber(choice.count)} files (whole folder)
            </Button>
            <Button
              variant="outline"
              onClick={() => {
                setChoice(null);
                onBrowsed(choice.file);
              }}
            >
              <FileIcon /> Use only {choice.file.split("\\").pop()}
            </Button>
          </div>
        </div>
      )}
      {approvedRoots && approvedRoots.length > 0 && (
        <p className="text-xs text-muted-foreground">
          Approved folders: <span className="font-mono">{approvedRoots.join("; ")}</span>
        </p>
      )}
      <ErrorAlert message={error} />
      {source && (
        <div className={stale ? "opacity-50" : undefined}>
          {stale && (
            <p className="mb-2 text-sm text-amber-700 dark:text-amber-300">
              The path changed. Inspect again to use the new file.
            </p>
          )}
          <dl className="grid grid-cols-2 gap-3 rounded-lg border bg-muted/40 p-3 text-sm sm:grid-cols-5">
            <Stat label={source.is_folder ? "Folder" : "File"} value={source.file_name} mono />
            <Stat label="Parquet files" value={formatNumber(source.file_count)} />
            <Stat label="Size" value={formatBytes(source.size_bytes)} />
            <Stat label="Rows" value={formatNumber(source.row_count)} />
            <Stat label="Columns" value={formatNumber(source.columns.length)} />
          </dl>
          {source.is_folder && (
            <details className="mt-2 text-xs text-muted-foreground">
              <summary className="cursor-pointer">
                {formatNumber(source.file_count)} shard(s) read together as one dataset
              </summary>
              <ul className="mt-1 max-h-32 overflow-auto font-mono">
                {source.sample_files.map((f) => (
                  <li key={f}>{f}</li>
                ))}
                {source.file_count > source.sample_files.length && (
                  <li>…and {formatNumber(source.file_count - source.sample_files.length)} more</li>
                )}
              </ul>
            </details>
          )}
          <ScrollArea className="mt-3 h-56 rounded-lg border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Column</TableHead>
                  <TableHead>Type</TableHead>
                  <TableHead className="text-right">Usable for filter / grouping</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {source.columns.map((c) => (
                  <TableRow key={c.name}>
                    <TableCell className="font-mono text-xs">{c.name}</TableCell>
                    <TableCell className="font-mono text-xs text-muted-foreground">{c.type}</TableCell>
                    <TableCell className="text-right">
                      {c.scalar ? <Badge variant="secondary">Yes</Badge> : <Badge variant="outline">No (nested)</Badge>}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </ScrollArea>
        </div>
      )}
    </StepCard>
  );
}

function Stat({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="min-w-0">
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className={mono ? "truncate font-mono text-xs leading-5" : "font-medium tabular-nums"} title={value}>
        {value}
      </dd>
    </div>
  );
}
