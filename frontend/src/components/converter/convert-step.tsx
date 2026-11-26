"use client";

import { FolderOpen, Loader2, Play } from "lucide-react";
import { BrowseButton } from "./browse-button";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import type { CollisionPolicy } from "@/lib/types";
import { StepCard } from "./step-card";
import { ErrorAlert } from "./warnings-list";

/** FR-02: destination and collision policy; conversion only from a fresh, valid preview. */
export function ConvertStep({
  disabled,
  destination,
  onDestinationChange,
  onBrowseError,
  collision,
  onCollisionChange,
  needsAck,
  ack,
  onAckChange,
  canConvert,
  blockedReason,
  starting,
  onConvert,
  error,
}: {
  disabled: boolean;
  destination: string;
  onDestinationChange: (v: string) => void;
  onBrowseError: (message: string | null) => void;
  collision: CollisionPolicy;
  onCollisionChange: (v: CollisionPolicy) => void;
  needsAck: boolean;
  ack: boolean;
  onAckChange: (v: boolean) => void;
  canConvert: boolean;
  blockedReason: string | null;
  starting: boolean;
  onConvert: () => void;
  error: string | null;
}) {
  return (
    <StepCard
      step={4}
      title="Convert"
      description="Files are written to a hidden staging folder first and appear only after every row count is verified."
      disabled={disabled}
    >
      <div className="space-y-1.5">
        <Label htmlFor="dest">Destination folder</Label>
        <div className="flex gap-2">
          <Input
            id="dest"
            placeholder="e.g. C:\Users\you\Documents\exports"
            value={destination}
            onChange={(e) => onDestinationChange(e.target.value)}
            className="font-mono text-sm"
            spellCheck={false}
            autoComplete="off"
          />
          <BrowseButton
            kind="folder"
            initialPath={destination}
            onPicked={(p) => onDestinationChange(p)}
            onError={onBrowseError}
            icon={<FolderOpen />}
          >
            Browse…
          </BrowseButton>
        </div>
        <p className="text-xs text-muted-foreground">Created if it does not exist (its parent folder must exist).</p>
      </div>
      <div className="space-y-2">
        <Label>If files with the same names already exist</Label>
        <RadioGroup value={collision} onValueChange={(v) => onCollisionChange(v as CollisionPolicy)}>
          <Label htmlFor="col-fail" className="flex items-center gap-2 font-normal">
            <RadioGroupItem id="col-fail" value="fail" /> Stop and tell me (existing files are never overwritten)
          </Label>
          <Label htmlFor="col-new" className="flex items-center gap-2 font-normal">
            <RadioGroupItem id="col-new" value="new_folder" /> Create a new dated subfolder for this export
          </Label>
          <Label htmlFor="col-overwrite" className="flex items-center gap-2 font-normal">
            <RadioGroupItem id="col-overwrite" value="overwrite" /> Overwrite existing files with the same names
          </Label>
        </RadioGroup>
        {collision === "overwrite" && (
          <p className="text-xs text-muted-foreground">
            Only files with the same names as the preview (and <span className="font-mono">_catalog.csv</span>) are
            replaced, after every row count is verified. Other files in the folder, such as extra parts from an earlier
            export, are left as they are. Close any of these files that are open in Excel first.
          </p>
        )}
      </div>
      {needsAck && (
        <Label htmlFor="ack" className="flex items-start gap-2 rounded-lg border border-amber-300 bg-amber-50 p-3 font-normal text-amber-900 dark:bg-amber-950/40 dark:text-amber-200">
          <Checkbox id="ack" checked={ack} onCheckedChange={(v) => onAckChange(v === true)} className="mt-0.5" />
          I understand that some files will contain more rows than the row limit, so that no group is split.
        </Label>
      )}
      <ErrorAlert id="convert-error" title="The conversion could not start" message={error} />
      <div className="flex items-center gap-3">
        <Button size="lg" onClick={onConvert} disabled={!canConvert || starting}>
          {starting ? <Loader2 className="animate-spin" /> : <Play />}
          Convert
        </Button>
        {blockedReason && <span className="text-sm text-muted-foreground">{blockedReason}</span>}
      </div>
    </StepCard>
  );
}
