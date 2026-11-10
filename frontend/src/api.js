const BASE = import.meta.env.VITE_API_BASE || "";

export class ApiError extends Error {
  constructor(message, status, detail) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

function messageFromPayload(payload, fallback) {
  if (!payload) return fallback;
  if (typeof payload === "string") return payload;
  if (typeof payload.detail === "string") return payload.detail;
  if (Array.isArray(payload.detail)) {
    return payload.detail.map((item) => item.msg || JSON.stringify(item)).join("; ");
  }
  return fallback;
}

async function request(path, { method = "GET", body, headers = {} } = {}) {
  const response = await fetch(`${BASE}${path}`, {
    method,
    headers: body && !(body instanceof FormData) ? { "Content-Type": "application/json", ...headers } : headers,
    body: body ? (body instanceof FormData ? body : JSON.stringify(body)) : undefined,
  });
  if (response.status === 204) return null;
  const text = await response.text();
  let payload = null;
  try {
    payload = text ? JSON.parse(text) : null;
  } catch {
    payload = text;
  }
  if (!response.ok) {
    throw new ApiError(
      messageFromPayload(payload, `Request failed (${response.status})`),
      response.status,
      payload,
    );
  }
  return payload;
}

function upload(path, file, onProgress) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    const form = new FormData();
    form.append("file", file);
    xhr.open("POST", `${BASE}${path}`);
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable && onProgress) {
        onProgress(Math.round((event.loaded / event.total) * 100));
      }
    };
    xhr.onload = () => {
      let payload = null;
      try {
        payload = xhr.responseText ? JSON.parse(xhr.responseText) : null;
      } catch {
        payload = xhr.responseText;
      }
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(payload);
      } else {
        reject(new ApiError(messageFromPayload(payload, `Upload failed (${xhr.status})`), xhr.status, payload));
      }
    };
    xhr.onerror = () => reject(new ApiError("Network error while uploading the file.", 0, null));
    xhr.send(form);
  });
}

export const api = {
  raw: request,
  health: () => request("/api/health"),

  datasets: () => request("/api/datasets"),
  dataset: (id) => request(`/api/datasets/${id}`),
  datasetPreview: (id, limit = 50) => request(`/api/datasets/${id}/preview?limit=${limit}`),
  uploadDataset: (file, onProgress) => upload("/api/datasets/upload", file, onProgress),
  setTarget: (id, target_column) =>
    request(`/api/datasets/${id}/target`, { method: "PATCH", body: { target_column } }),
  deleteDataset: (id) => request(`/api/datasets/${id}`, { method: "DELETE" }),
  kaggleStatus: () => request("/api/kaggle/status"),
  importKaggle: (slug) => request("/api/kaggle/import", { method: "POST", body: { slug } }),

  preprocessingRuns: (datasetId) =>
    request(`/api/preprocess/runs${datasetId ? `?dataset_id=${datasetId}` : ""}`),
  preprocessingRun: (id) => request(`/api/preprocess/runs/${id}`),
  startPreprocessing: (config) => request("/api/preprocess/runs", { method: "POST", body: config }),
  families: (runId) => request(`/api/preprocess/runs/${runId}/families`),

  models: () => request("/api/models"),
  experiments: (kind) => request(`/api/experiments${kind ? `?kind=${kind}` : ""}`),
  experiment: (id) => request(`/api/experiments/${id}`),
  deleteExperiment: (id) => request(`/api/experiments/${id}`, { method: "DELETE" }),
  train: (payload) => request("/api/experiments", { method: "POST", body: payload }),
  startUnknown: (payload) => request("/api/unknown/experiments", { method: "POST", body: payload }),
  predict: (id, file) => upload(`/api/experiments/${id}/predict`, file),

  job: (id) => request(`/api/jobs/${id}`),

  containmentStatus: () => request("/api/containment/status"),
  simulateContainment: (payload) =>
    request("/api/containment/simulate", { method: "POST", body: payload }),
  verifyEvent: (id) => request(`/api/containment/events/${id}/verify`, { method: "POST" }),
  releaseEvent: (id) => request(`/api/containment/events/${id}/release`, { method: "POST" }),

  resources: () => request("/api/resources"),
  setEdgeBudget: (budget) => request("/api/resources/edge-budget", { method: "PATCH", body: budget }),
  benchmark: (payload) => request("/api/resources/benchmark", { method: "POST", body: payload }),

  commandCenter: () => request("/api/command-center"),
  analyticsOverview: () => request("/api/analytics/overview"),
  compare: (ids) => request(`/api/analytics/compare${ids?.length ? `?ids=${ids.join(",")}` : ""}`),
  analyticsExperiment: (id) => request(`/api/analytics/experiments/${id}`),
  threats: (experimentId, threshold) => {
    const params = new URLSearchParams();
    if (experimentId) params.set("experiment_id", experimentId);
    if (threshold !== undefined) params.set("threshold", String(threshold));
    return request(`/api/threats?${params.toString()}`);
  },

  reports: () => request("/api/reports"),
  createReport: (experimentId) => request("/api/reports", { method: "POST", body: { experiment_id: experimentId } }),
  documentation: () => request("/api/documentation"),

  exportUrl: (experimentId, format = "csv") => `${BASE}/api/analytics/export?experiment_id=${experimentId}&format=${format}`,
  reportDownloadUrl: (reportId) => `${BASE}/api/reports/${reportId}/download`,
};

export function jobSocketUrl(jobId) {
  if (!jobId) return null;
  if (import.meta.env.VITE_API_BASE) {
    return `${import.meta.env.VITE_API_BASE.replace(/^http/, "ws")}/ws/jobs/${jobId}`;
  }
  const protocol = window.location.protocol === "https:" ? "wss" : "ws";
  return `${protocol}://${window.location.host}/ws/jobs/${jobId}`;
}

export const API_BASE = BASE;
