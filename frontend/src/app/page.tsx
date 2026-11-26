"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Lock } from "lucide-react";
import { ConfigStep, defaultConfig, parseRowLimit, type ConfigState } from "@/components/converter/config-step";
import { ConnectionBadge, SetupGuide } from "@/components/converter/connection-panel";
import { ConvertStep } from "@/components/converter/convert-step";
import { JobProgress, JobResults } from "@/components/converter/job-panel";
import { PreviewStep } from "@/components/converter/preview-step";
import { SourceStep } from "@/components/converter/source-step";
import { useConnection } from "@/hooks/use-connection";
import { ApiError, api } from "@/lib/api";
import { estimateRemaining, type Eta, type ProgressSample } from "@/lib/eta";
import type { CollisionPolicy, JobResult, JobStatus, Plan, PreviewRequest, SourceInfo } from "@/lib/types";

const POLL_MS = 750;

function stem(fileName: string): string {
  return fileName.replace(/\.parquet$/i, "").replace(/[<>:"/\\|?*]/g, "_");
}

function buildRequest(source: SourceInfo, c: ConfigState): PreviewRequest | null {
  const rowLimit = c.mode === "single" ? 0 : parseRowLimit(c.rowLimitText);
  if (rowLimit === null) return null;
  return {
    fingerprint: source.fingerprint,
    mode: c.mode,
    filter_column: c.filterColumn,
    group_columns: c.mode === "group" ? c.groupColumns : [],
    row_limit: c.mode === "single" ? 800_000 : rowLimit,
    oversize_policy: c.mode === "group" ? c.oversizePolicy : "strict",
    output_prefix: c.prefix.trim(),
  };
}

export default function Home() {
  const conn = useConnection();
  const ready = conn.status === "ready";

  const [sourcePath, setSourcePath] = useState("");
  const [inspectedPath, setInspectedPath] = useState<string | null>(null);
  const [source, setSource] = useState<SourceInfo | null>(null);
  const [inspecting, setInspecting] = useState(false);
  const [inspectError, setInspectError] = useState<string | null>(null);

  const [config, setConfig] = useState<ConfigState>(defaultConfig);

  const [plan, setPlan] = useState<Plan | null>(null);
  const [planKey, setPlanKey] = useState<string | null>(null);
  const [previewing, setPreviewing] = useState(false);
  const [previewError, setPreviewError] = useState<string | null>(null);

  const [destination, setDestination] = useState("");
  const [collision, setCollision] = useState<CollisionPolicy>("fail");
  const [ack, setAck] = useState(false);
  const [starting, setStarting] = useState(false);
  const [convertError, setConvertError] = useState<string | null>(null);

  const [jobId, setJobId] = useState<string | null>(null);
  const [jobStatus, setJobStatus] = useState<JobStatus | null>(null);
  const [result, setResult] = useState<JobResult | null>(null);
  const [cancelling, setCancelling] = useState(false);
  const [eta, setEta] = useState<Eta | null>(null);

  const handleError = useCallback(
    (err: unknown, set: (m: string) => void) => {
      if (err instanceof ApiError) {
        if (err.code === "invalid_token" || err.code === "backend_unreachable") conn.refresh();
        set(err.message);
      } else set(String(err));
    },
    [conn],
  );

  const sourceStale = source !== null && sourcePath.trim() !== inspectedPath;
  const request = useMemo(() => (source ? buildRequest(source, config) : null), [source, config]);
  const configKey = request ? JSON.stringify(request) : null;
  const planStale = plan !== null && (planKey !== configKey || sourceStale);

  const invalidReason = !source
    ? "Inspect a source file first."
    : sourceStale
      ? "Inspect the changed source path first."
      : !config.prefix.trim()
        ? "Enter a filename prefix."
        : request === null
          ? "Enter a valid row limit."
          : config.mode === "group" && config.groupColumns.length === 0
            ? "Add at least one grouping column."
            : null;

  const needsAck = !!plan && !planStale && plan.requires_acknowledgement;
  const blockedReason = !plan
    ? "Preview the files first."
    : planStale
      ? "Refresh the preview first."
      : !plan.can_convert
        ? "Fix the blocking problem shown in the preview."
        : !destination.trim()
          ? "Enter a destination folder."
          : needsAck && !ack
            ? "Confirm the oversized files above."
            : null;

  const jobActive = jobId !== null;
  const jobRunning = jobStatus?.state === "running" || (jobActive && !jobStatus);

  // Reattach to a conversion that is already running (e.g. after a page reload).
  useEffect(() => {
    const running = conn.health?.running_job_id;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- sync with server-side job state
    if (running && !jobId) setJobId(running);
  }, [conn.health?.running_job_id, jobId]);

  // Poll the job until it reaches a terminal state.
  useEffect(() => {
    if (!jobId) return;
    let stop = false;
    let timer: ReturnType<typeof setTimeout>;
    const samples: ProgressSample[] = [];
    const tick = async () => {
      try {
        const st = await api.jobStatus(jobId);
        if (stop) return;
        setJobStatus(st);
        samples.push({ t: st.elapsed_seconds, p: st.progress });
        const remaining = st.state === "running" ? estimateRemaining(samples) : null;
        setEta(remaining === null ? null : { seconds: remaining, finishAt: Date.now() + remaining * 1000 });
        if (st.state === "succeeded") {
          setResult(await api.jobResult(jobId));
          return;
        }
        if (st.state !== "running") return;
      } catch (err) {
        if (err instanceof ApiError && err.status === 404) {
          setJobId(null);
          return;
        }
      }
      if (!stop) timer = setTimeout(tick, POLL_MS);
    };
    void tick();
    return () => {
      stop = true;
      clearTimeout(timer);
    };
  }, [jobId]);

  const inspect = async (picked?: string) => {
    const path = (picked ?? sourcePath).trim();
    if (picked !== undefined) setSourcePath(picked);
    setInspecting(true);
    setInspectError(null);
    try {
      const info = await api.inspect(path);
      if (!source || source.fingerprint !== info.fingerprint) {
        // FR-03: a new or changed source clears column selections and the preview.
        setConfig((c) => ({ ...c, filterColumn: null, groupColumns: [], prefix: c.prefix || stem(info.file_name) }));
        setPlan(null);
        setPlanKey(null);
      }
      setSource(info);
      setInspectedPath(path);
    } catch (err) {
      setSource(null);
      setPlan(null);
      handleError(err, setInspectError);
    } finally {
      setInspecting(false);
    }
  };

  const preview = async () => {
    if (!request) return;
    setPreviewing(true);
    setPreviewError(null);
    try {
      const p = await api.preview(request);
      setPlan(p);
      setPlanKey(JSON.stringify(request));
      setAck(false);
    } catch (err) {
      setPlan(null);
      handleError(err, setPreviewError);
    } finally {
      setPreviewing(false);
    }
  };

  const convert = async () => {
    if (!plan || blockedReason) return;
    setStarting(true);
    setConvertError(null);
    try {
      const job = await api.createJob({
        preview_id: plan.preview_id,
        destination_dir: destination.trim(),
        collision_policy: collision,
        acknowledge_oversize: ack,
      });
      setJobStatus(null);
      setResult(null);
      setEta(null);
      setJobId(job.job_id);
      // The progress card is at the top of the page.
      window.scrollTo({ top: 0, behavior: "smooth" });
    } catch (err) {
      handleError(err, setConvertError);
      requestAnimationFrame(() =>
        document.getElementById("convert-error")?.scrollIntoView({ behavior: "smooth", block: "center" }),
      );
    } finally {
      setStarting(false);
    }
  };

  const cancel = async () => {
    if (!jobId) return;
    setCancelling(true);
    try {
      setJobStatus(await api.cancelJob(jobId));
    } catch (err) {
      handleError(err, setConvertError);
    } finally {
      setCancelling(false);
    }
  };

  const resetJob = () => {
    setJobId(null);
    setJobStatus(null);
    setResult(null);
    if (result) {
      // Outputs now exist in the destination; require a fresh preview for the next run.
      setPlan(null);
      setPlanKey(null);
    }
  };

  const locked = !ready || jobActive;

  return (
    <div className="min-h-full bg-muted/30">
      <header className="border-b bg-background">
        <div className="mx-auto flex max-w-5xl flex-wrap items-center justify-between gap-3 px-4 py-4">
          <div>
            <h1 className="text-lg font-semibold tracking-tight">Parquet to CSV Converter</h1>
            <p className="flex items-center gap-1 text-xs text-muted-foreground">
              <Lock className="size-3" /> All processing happens on this PC. Nothing is uploaded.
            </p>
          </div>
          <ConnectionBadge conn={conn} />
        </div>
      </header>

      <main className="mx-auto max-w-5xl space-y-4 px-4 py-6">
        <SetupGuide conn={conn} />

        {jobActive && jobStatus?.state === "succeeded" && result ? (
          <JobResults result={result} filterColumn={plan?.filter_column ?? null} onReset={resetJob} />
        ) : jobActive && !jobStatus ? (
          <JobProgress
            status={{ job_id: jobId ?? "", state: "running", stage: "starting", progress: 0, parts_completed: 0, parts_total: null, elapsed_seconds: 0, error: null }}
            eta={null}
            onCancel={cancel}
            cancelling={cancelling}
            onReset={resetJob}
          />
        ) : jobActive && jobStatus ? (
          <JobProgress status={jobStatus} eta={eta} onCancel={cancel} cancelling={cancelling} onReset={resetJob} />
        ) : null}

        <SourceStep
          disabled={locked}
          path={sourcePath}
          onPathChange={setSourcePath}
          onInspect={() => inspect()}
          onBrowsed={(p) => inspect(p)}
          onBrowseError={setInspectError}
          inspecting={inspecting}
          error={inspectError}
          source={source}
          stale={sourceStale}
          approvedRoots={conn.health?.approved_roots}
        />
        <ConfigStep disabled={locked || !source || sourceStale} columns={source?.columns ?? []} config={config} onChange={setConfig} />
        <PreviewStep
          disabled={locked || !source}
          canPreview={!invalidReason}
          invalidReason={invalidReason}
          onPreview={preview}
          previewing={previewing}
          error={previewError}
          plan={plan}
          stale={planStale}
        />
        <ConvertStep
          disabled={locked || !plan}
          destination={destination}
          onDestinationChange={setDestination}
          onBrowseError={setConvertError}
          collision={collision}
          onCollisionChange={setCollision}
          needsAck={needsAck}
          ack={ack}
          onAckChange={setAck}
          canConvert={!blockedReason && !jobRunning}
          blockedReason={blockedReason}
          starting={starting}
          onConvert={convert}
          error={convertError}
        />
      </main>
    </div>
  );
}
