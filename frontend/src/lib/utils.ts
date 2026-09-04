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

// Calculate XP from session (RPE × duration / 10)
export function calculateXP(
  rpe: number | null,
  durationMinutes: number
): number {
  if (rpe === null) return Math.round(durationMinutes);
  return Math.round((rpe * durationMinutes) / 10);
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
