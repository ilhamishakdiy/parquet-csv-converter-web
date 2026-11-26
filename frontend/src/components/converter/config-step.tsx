"use client";

import { ArrowDown, ArrowUp, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import type { Column, Mode, OversizePolicy } from "@/lib/types";
import { StepCard } from "./step-card";

export type ConfigState = {
  prefix: string;
  mode: Mode;
  filterColumn: string | null;
  groupColumns: string[];
  rowLimitText: string;
  oversizePolicy: OversizePolicy;
};

export const DEFAULT_ROW_LIMIT = 800_000;

export const defaultConfig: ConfigState = {
  prefix: "",
  mode: "group",
  filterColumn: null,
  groupColumns: [],
  rowLimitText: String(DEFAULT_ROW_LIMIT),
  oversizePolicy: "strict",
};

export function parseRowLimit(text: string): number | null {
  const clean = text.replace(/[,\s_]/g, "");
  if (!/^\d+$/.test(clean)) return null;
  const n = Number(clean);
  return Number.isSafeInteger(n) && n >= 1 ? n : null;
}

const NONE = "__none__";

const MODES: { value: Mode; title: string; body: string }[] = [
  { value: "single", title: "Single CSV", body: "One file (one per filter value if a filter is chosen). No row limit." },
  { value: "rows", title: "Split by row count", body: "Fixed-size parts. Rows from the same group may end up in different files." },
  { value: "group", title: "Group-aware split", body: "Fixed-size parts that never split a group (e.g. a store)." },
];

/** FR-04 / FR-05 / FR-06: prefix, mode, filter, grouping, row limit and oversize policy. */
export function ConfigStep({
  disabled,
  columns,
  config,
  onChange,
}: {
  disabled: boolean;
  columns: Column[];
  config: ConfigState;
  onChange: (c: ConfigState) => void;
}) {
  const scalar = columns.filter((c) => c.scalar);
  const set = (patch: Partial<ConfigState>) => onChange({ ...config, ...patch });
  const rowLimit = parseRowLimit(config.rowLimitText);
  const available = scalar.filter((c) => !config.groupColumns.includes(c.name) && c.name !== config.filterColumn);

  const move = (i: number, delta: number) => {
    const next = [...config.groupColumns];
    const j = i + delta;
    [next[i], next[j]] = [next[j], next[i]];
    set({ groupColumns: next });
  };

  return (
    <StepCard
      step={2}
      title="Configure the output"
      description="Choose how rows are split into CSV files."
      disabled={disabled}
    >
      <div className="space-y-1.5">
        <Label htmlFor="prefix">Filename prefix</Label>
        <Input
          id="prefix"
          value={config.prefix}
          onChange={(e) => set({ prefix: e.target.value })}
          placeholder="e.g. Malaysia_Sales_Nov2026"
          className="font-mono text-sm"
          autoComplete="off"
        />
        <p className="text-xs text-muted-foreground">
          Files are named <span className="font-mono">{"<prefix>_<filter value>_partXX.csv"}</span>. The filter value
          and part number are added automatically.
        </p>
      </div>

      <div className="space-y-2">
        <Label>Export mode</Label>
        <RadioGroup
          value={config.mode}
          onValueChange={(v) => set({ mode: v as Mode })}
          className="grid gap-2 sm:grid-cols-3"
        >
          {MODES.map((m) => (
            <Label
              key={m.value}
              htmlFor={`mode-${m.value}`}
              className="flex cursor-pointer items-start gap-2 rounded-lg border p-3 font-normal has-[[data-state=checked]]:border-primary has-[[data-state=checked]]:bg-muted/50"
            >
              <RadioGroupItem id={`mode-${m.value}`} value={m.value} className="mt-0.5" />
              <span className="space-y-1">
                <span className="block font-medium">{m.title}</span>
                <span className="block text-xs text-muted-foreground">{m.body}</span>
              </span>
            </Label>
          ))}
        </RadioGroup>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <div className="space-y-1.5">
          <Label>Separate files by (optional filter)</Label>
          <Select
            value={config.filterColumn ?? NONE}
            onValueChange={(v) => {
              const filterColumn = v === NONE ? null : v;
              set({ filterColumn, groupColumns: config.groupColumns.filter((g) => g !== filterColumn) });
            }}
          >
            <SelectTrigger className="w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={NONE}>No filter: all rows together</SelectItem>
              {scalar.map((c) => (
                <SelectItem key={c.name} value={c.name}>
                  {c.name} <span className="text-muted-foreground">({c.type})</span>
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <p className="text-xs text-muted-foreground">
            Every distinct value gets its own files. No rows are excluded.
          </p>
        </div>

        {config.mode !== "single" && (
          <div className="space-y-1.5">
            <Label htmlFor="row-limit">Maximum data rows per file</Label>
            <Input
              id="row-limit"
              inputMode="numeric"
              value={config.rowLimitText}
              onChange={(e) => set({ rowLimitText: e.target.value })}
              aria-invalid={rowLimit === null}
              className="tabular-nums"
            />
            <p className={rowLimit === null ? "text-xs text-destructive" : "text-xs text-muted-foreground"}>
              {rowLimit === null ? "Enter a whole number of at least 1." : "The header row is not counted."}
            </p>
          </div>
        )}
      </div>

      {config.mode === "group" && (
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-1.5">
            <Label>Keep these columns together (grouping)</Label>
            {config.groupColumns.length > 0 && (
              <ol className="space-y-1">
                {config.groupColumns.map((g, i) => (
                  <li key={g} className="flex items-center gap-1 rounded-md border px-2 py-1 text-sm">
                    <span className="w-5 text-xs text-muted-foreground">{i + 1}.</span>
                    <span className="flex-1 truncate font-mono text-xs">{g}</span>
                    <Button size="icon-xs" variant="ghost" disabled={i === 0} onClick={() => move(i, -1)} aria-label={`Move ${g} up`}>
                      <ArrowUp />
                    </Button>
                    <Button
                      size="icon-xs"
                      variant="ghost"
                      disabled={i === config.groupColumns.length - 1}
                      onClick={() => move(i, 1)}
                      aria-label={`Move ${g} down`}
                    >
                      <ArrowDown />
                    </Button>
                    <Button
                      size="icon-xs"
                      variant="ghost"
                      onClick={() => set({ groupColumns: config.groupColumns.filter((x) => x !== g) })}
                      aria-label={`Remove ${g}`}
                    >
                      <X />
                    </Button>
                  </li>
                ))}
              </ol>
            )}
            <Select value="" onValueChange={(v) => set({ groupColumns: [...config.groupColumns, v] })} disabled={!available.length}>
              <SelectTrigger className="w-full">
                <SelectValue placeholder={available.length ? "Add a grouping column…" : "No more columns available"} />
              </SelectTrigger>
              <SelectContent>
                {available.map((c) => (
                  <SelectItem key={c.name} value={c.name}>
                    {c.name} <span className="text-muted-foreground">({c.type})</span>
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <p className="text-xs text-muted-foreground">
              With several columns, a group is the full combination of their values.
            </p>
          </div>

          <div className="space-y-2">
            <Label>If one group is bigger than the row limit</Label>
            <RadioGroup value={config.oversizePolicy} onValueChange={(v) => set({ oversizePolicy: v as OversizePolicy })}>
              <Label htmlFor="pol-strict" className="flex items-start gap-2 font-normal">
                <RadioGroupItem id="pol-strict" value="strict" className="mt-0.5" />
                <span>
                  <span className="block font-medium">Strict (recommended)</span>
                  <span className="block text-xs text-muted-foreground">Stop and tell me. The row limit is never exceeded.</span>
                </span>
              </Label>
              <Label htmlFor="pol-priority" className="flex items-start gap-2 font-normal">
                <RadioGroupItem id="pol-priority" value="group_priority" className="mt-0.5" />
                <span>
                  <span className="block font-medium">Keep the group whole</span>
                  <span className="block text-xs text-muted-foreground">
                    Put it in its own oversized file. You confirm before converting.
                  </span>
                </span>
              </Label>
            </RadioGroup>
          </div>
        </div>
      )}
    </StepCard>
  );
}
