export const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";
export const WS_BASE = API_BASE.replace(/^http/, "ws");

// Registered by AuthContext on mount. Lets api.js react to an expired/invalid
// token (401) by forcing a logout + redirect to login, instead of every page
// having to notice and handle that individually — which is what was causing
// pages to hang on "Loading…" forever with no explanation when a token had
// gone stale.
let unauthorizedHandler = null;
export function setUnauthorizedHandler(fn) {
  unauthorizedHandler = fn;
}

class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.status = status;
  }
}

async function handleResponse(res, path) {
  if (res.status === 401) {
    unauthorizedHandler?.();
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new ApiError(body.detail || `Request failed: ${path} (${res.status})`, res.status);
  }
  return res.json();
}

export async function apiGet(path, token) {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  return handleResponse(res, path);
}

export async function apiPost(path, body, token) {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(body),
  });
  return handleResponse(res, path);
}

export async function apiPatch(path, body, token) {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(body),
  });
  return handleResponse(res, path);
}

export async function apiUpload(path, files, extraFields, token, onProgress) {
  const form = new FormData();
  files.forEach((f) => form.append("files", f, f.name));
  Object.entries(extraFields || {}).forEach(([k, v]) => form.append(k, v));

  // Use XHR instead of fetch so we can report upload progress — fetch has no
  // built-in progress event for request bodies.
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${API_BASE}${path}`);
    if (token) xhr.setRequestHeader("Authorization", `Bearer ${token}`);

    xhr.upload.onprogress = (e) => {
      if (onProgress && e.lengthComputable) onProgress(e.loaded / e.total);
    };
    xhr.onload = () => {
      let body;
      try { body = JSON.parse(xhr.responseText); } catch { body = {}; }
      if (xhr.status === 401) unauthorizedHandler?.();
      if (xhr.status >= 200 && xhr.status < 300) resolve(body);
      else reject(new ApiError(body.detail || `Upload failed (${xhr.status})`, xhr.status));
    };
    xhr.onerror = () => reject(new ApiError("Upload failed — network error", 0));
    xhr.send(form);
  });
}

export async function apiDelete(path, token) {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "DELETE",
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  return handleResponse(res, path);
}
