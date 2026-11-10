export function formatNumber(value, digits = 0) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "—";
  return Number(value).toLocaleString(undefined, {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

export function formatMetric(value, digits = 3) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "—";
  return Number(value).toFixed(digits);
}

export function formatPercent(value, digits = 1) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "—";
  return `${(Number(value) * 100).toFixed(digits)}%`;
}

export function formatBytes(bytes) {
  if (!bytes && bytes !== 0) return "—";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let size = Number(bytes);
  let index = 0;
  while (size >= 1024 && index < units.length - 1) {
    size /= 1024;
    index += 1;
  }
  return `${size >= 10 || index === 0 ? size.toFixed(0) : size.toFixed(1)} ${units[index]}`;
}

export function formatDate(value) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function timeAgo(value) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  const seconds = Math.round((Date.now() - date.getTime()) / 1000);
  if (seconds < 45) return "just now";
  if (seconds < 3600) return `${Math.round(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.round(seconds / 3600)}h ago`;
  return formatDate(value);
}

export function titleCase(value) {
  if (!value) return "—";
  return String(value)
    .replaceAll("_", " ")
    .replace(/\b\w/g, (character) => character.toUpperCase());
}

export function truncate(value, length = 26) {
  if (!value) return "—";
  const text = String(value);
  return text.length > length ? `${text.slice(0, length - 1)}…` : text;
}

export function classForStatus(status) {
  const value = String(status || "").toUpperCase();
  if (["ACTIVE", "CONTAINED", "SUCCESS", "COMPLETED", "READY", "OK"].includes(value)) return "green";
  if (["MONITORED", "RUNNING", "QUEUED", "THROTTLED", "REAUTH_REQUIRED", "INCONCLUSIVE"].includes(value)) return "amber";
  if (["QUARANTINED", "FAILED", "FAILURE", "RELEASED"].includes(value)) return "red";
  return "neutral";
}

export function actionTone(action) {
  const value = String(action || "").toUpperCase();
  if (value === "QUARANTINE") return "red";
  if (value === "REAUTHENTICATE") return "amber";
  if (value === "RATE_LIMIT") return "blue";
  return "neutral";
}

export function normalizeStatus(value) {
  return String(value || "").replaceAll("_", " ").toUpperCase();
}
