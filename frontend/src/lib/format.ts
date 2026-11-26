const nf = new Intl.NumberFormat("en-US");

export const formatNumber = (n: number) => nf.format(n);

export function formatBytes(bytes: number): string {
  const units = ["B", "KB", "MB", "GB", "TB"];
  let value = bytes;
  let i = 0;
  while (value >= 1024 && i < units.length - 1) {
    value /= 1024;
    i++;
  }
  return `${value.toFixed(i === 0 ? 0 : 1)} ${units[i]}`;
}

export function formatDuration(seconds: number): string {
  const s = Math.max(0, Math.round(seconds));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const rest = s % 60;
  if (h) return `${h}h ${m}m ${rest}s`;
  if (m) return `${m}m ${rest}s`;
  return `${rest}s`;
}

export function displayValue(value: string | null, isNull = value === null): string {
  if (isNull) return "(NULL)";
  if (value === "") return "(empty)";
  return value as string;
}
