import type { ResultCell } from "../api/types";

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
