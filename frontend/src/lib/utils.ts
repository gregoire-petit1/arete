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

// Format duration from seconds to human readable
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

// Format distance from meters
export function formatDistance(meters: number | null): string {
  if (meters === null) return "—";
  if (meters >= 1000) {
    return `${(meters / 1000).toFixed(2)} km`;
  }
  return `${meters} m`;
}

// Calculate XP from session (RPE × duration / 10)
export function calculateXP(
  rpe: number | null,
  durationMinutes: number
): number {
  if (rpe === null) return Math.round(durationMinutes);
  return Math.round((rpe * durationMinutes) / 10);
}

// Calculate level from CTL
export function calculateLevel(ctl: number): number {
  return Math.floor(ctl / 5) + 1;
}

// Normalize TSB (-30 to +30) to 0-100 for MP bar
export function normalizeTSB(tsb: number): number {
  return Math.max(0, Math.min(100, (tsb + 30) * (100 / 60)));
}

// Format date for display
export function formatDate(dateStr: string): string {
  const date = new Date(dateStr);
  return date.toLocaleDateString("fr-FR", {
    day: "2-digit",
    month: "short",
  });
}

// Get day of week short
export function getDayOfWeek(dateStr: string): string {
  const date = new Date(dateStr);
  return date.toLocaleDateString("fr-FR", { weekday: "short" }).toUpperCase();
}

// Get relative time (e.g., "2 hours ago")
export function getRelativeTime(dateStr: string): string {
  const date = new Date(dateStr);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMins / 60);
  const diffDays = Math.floor(diffHours / 24);

  if (diffDays > 0) return `${diffDays}d ago`;
  if (diffHours > 0) return `${diffHours}h ago`;
  if (diffMins > 0) return `${diffMins}m ago`;
  return "just now";
}

// Sport icons mapping - using text symbols for system look
export function getSportIcon(sport: string): string {
  const icons: Record<string, string> = {
    running: "▶",
    cycling: "◎",
    swimming: "≋",
    strength: "◆",
    yoga: "◇",
    hiking: "△",
    walking: "○",
    other: "◈",
    default: "●",
  };
  return icons[sport.toLowerCase()] || icons.default;
}

// Session status icons - terminal style
export function getStatusIcon(status: string): string {
  const icons: Record<string, string> = {
    pending: "○",
    completed: "●",
    skipped: "×",
  };
  return icons[status] || "○";
}
