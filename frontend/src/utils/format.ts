import type { DashboardUnit, ResultCell } from "../api/types";

export function formatCell(value: ResultCell): string {
  if (value === null) return "—";
  if (typeof value === "boolean") return value ? "True" : "False";
  return String(value);
}

export function safeSourcePath(path: string): string {
  const normalized = path.replaceAll("\\", "/");
  const parts = normalized.split("/").filter(Boolean);
  return parts.slice(-2).join("/") || "Source";
}

export function formatMetric(value: number): string {
  return new Intl.NumberFormat(undefined, { maximumFractionDigits: 2 }).format(value);
}

export function formatDashboardValue(
  value: number,
  unit: DashboardUnit,
  compact = true,
): string {
  if (unit === "currency") {
    return new Intl.NumberFormat(undefined, {
      style: "currency",
      currency: "USD",
      notation: compact ? "compact" : "standard",
      maximumFractionDigits: compact ? 2 : 2,
    }).format(value);
  }
  return new Intl.NumberFormat(undefined, {
    notation: compact ? "compact" : "standard",
    maximumFractionDigits: compact ? 1 : 0,
  }).format(value);
}

export function formatComparison(value: number): string {
  const formatted = new Intl.NumberFormat(undefined, {
    signDisplay: "always",
    maximumFractionDigits: 1,
  }).format(value);
  return `${formatted}%`;
}
