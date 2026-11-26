// Mirrors the local API contract (backend/api.py, PRD 05).

export type Health = {
  status: string;
  app: string;
  api_version: string;
  paired: boolean;
  running_job_id?: string | null;
  approved_roots?: string[];
};

/** folder/folder_parquet_count are set when a picked file sits among other .parquet shards. */
export type BrowseResult = { path: string | null; folder: string | null; folder_parquet_count: number };

export type Column ={ name: string; type: string; scalar: boolean };

export type SourceInfo = {
  path: string;
  file_name: string;
  is_folder: boolean;
  file_count: number;
  sample_files: string[];
  size_bytes: number;
  row_count: number;
  row_groups: number;
  uncompressed_bytes: number;
  created_by: string | null;
  columns: Column[];
  fingerprint: string;
};

export type Mode = "single" | "rows" | "group";
export type OversizePolicy = "strict" | "group_priority";
export type CollisionPolicy = "fail" | "new_folder";

export type PlanWarning = {
  severity: "info" | "warning" | "blocking";
  code: string;
  message: string;
};

export type PlannedFile = {
  part_id: number;
  file_name: string;
  filter_value: string | null;
  filter_is_null: boolean;
  part_no: number;
  rows: number;
  groups: number;
  largest_group_rows: number;
  oversized: boolean;
};

export type Plan = {
  preview_id: string;
  fingerprint: string;
  mode: Mode;
  filter_column: string | null;
  group_columns: string[];
  row_limit: number;
  oversize_policy: OversizePolicy;
  output_prefix: string;
  total_rows: number;
  part_count: number;
  filter_count: number;
  group_count: number;
  largest_group: { filter_value: string | null; values: Record<string, string | null>; rows: number } | null;
  files: PlannedFile[];
  files_truncated: boolean;
  catalog_file: string;
  catalog_headers: string[];
  warnings: PlanWarning[];
  can_convert: boolean;
  requires_acknowledgement: boolean;
};

export type PreviewRequest = {
  fingerprint: string;
  mode: Mode;
  filter_column: string | null;
  group_columns: string[];
  row_limit: number;
  oversize_policy: OversizePolicy;
  output_prefix: string;
};

export type JobState = "running" | "succeeded" | "failed" | "cancelled";

export type JobStatus = {
  job_id: string;
  state: JobState;
  stage: string;
  progress: number;
  parts_completed: number;
  parts_total: number | null;
  elapsed_seconds: number;
  error: { code: string; message: string } | null;
};

export type ResultFile = {
  file_name: string;
  path: string;
  filter_value: string | null;
  filter_is_null: boolean;
  part_no: number;
  rows: number;
  groups: number;
  oversized: boolean;
};

export type JobResult = {
  job_id: string;
  destination: string;
  catalog_path: string;
  catalog_rows: number;
  files: ResultFile[];
  file_count: number;
  total_rows: number;
  source_rows: number;
  oversized_files: string[];
  duration_seconds: number;
  warnings: PlanWarning[];
  validation: { status: string; checks: { name: string; passed: boolean; detail: string }[] };
};
