import { clsx, type ClassValue } from "clsx";

export function cn(...inputs: ClassValue[]) {
  return clsx(inputs);
}

// Zone color mapping
export function getZoneColor(
  zone?: string
): "green" | "orange" | "red" | "cyan" {
  switch (zone) {
    case "optimal":
    case "fresh":
    case "high":
      return "green";
    case "high_risk":
    case "grey":
    case "moderate":
      return "orange";
    case "danger":
    case "fatigued":
    case "exhausted":
    case "low":
      return "red";
    default:
      return "cyan";
  }
}

// Format duration from seconds to human readable ("1h 5m", "12m 30s")
export function formatDuration(seconds: number): string {
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const secs = seconds % 60;

  if (hours > 0) {
    return `${hours}h ${minutes}m`;
  }
  if (minutes > 0) {
    return `${minutes}m ${secs}s`;
  }
  return `${secs}s`;
}

// Compact duration for dense lists ("1h05", "45min", "—")
export function formatDurationCompact(seconds: number | null | undefined): string {
  if (!seconds) return "—";
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  return h > 0 ? `${h}h${m.toString().padStart(2, "0")}` : `${m}min`;
}

// Pace in seconds per km → "m:ss"
export function formatPace(secondsPerKm: number): string {
  const mins = Math.floor(secondsPerKm / 60);
  const secs = Math.round(secondsPerKm % 60);
  return `${mins}:${secs.toString().padStart(2, "0")}`;
}

/** 'API Error 422: {"detail":"Enregistrement vide"}' -> 'Enregistrement vide' */
export function readableError(error: unknown): string {
  const raw = error instanceof Error ? error.message : String(error);
  const match = raw.match(/\{.*\}/s);
  if (match) {
    try {
      const body = JSON.parse(match[0]) as { detail?: string };
      if (body.detail) return body.detail;
    } catch {
      // fall through to the raw message
    }
  }
  return raw;
}
