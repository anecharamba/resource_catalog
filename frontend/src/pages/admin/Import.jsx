import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { apiGet, apiPost, apiUpload, WS_BASE } from "../../api";
import { useAuth } from "../../context/AuthContext";
import FilePicker from "../../components/FilePicker";

const STATUS_LABEL = {
  queued: "Queued",
  extracting: "Extracting / OCR",
  done: "Cataloged",
  needs_review: "Needs review",
  duplicate: "Duplicate — skipped",
  failed: "Failed",
  cancelled: "Cancelled",
};

export default function Import() {
  const { token } = useAuth();
  const [params, setParams] = useSearchParams();
  const [files, setFiles] = useState([]);
  const [useTier2, setUseTier2] = useState(true);
  const [batchId, setBatchId] = useState(params.get("batch") ? Number(params.get("batch")) : null);
  const [batch, setBatch] = useState(null);
  const [jobs, setJobs] = useState([]);
  const [error, setError] = useState(null);
  const [cancelling, setCancelling] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const wsRef = useRef(null);

  const startImport = async (e) => {
    e.preventDefault();
    if (files.length === 0) {
      setError("Add at least one file first.");
      return;
    }
    setError(null);
    setUploading(true);
    setUploadProgress(0);
    try {
      const res = await apiUpload(
        "/admin/import/upload",
        files,
        { use_tier2: useTier2 },
        token,
        setUploadProgress
      );
      setBatchId(res.batch_id);
      setParams({ batch: String(res.batch_id) });
      setFiles([]);
    } catch (e) {
      setError(e.message);
    } finally {
      setUploading(false);
    }
  };

  // Load current batch snapshot whenever batchId changes
  const [batchLoading, setBatchLoading] = useState(false);

  useEffect(() => {
    if (!batchId) return;
    setBatchLoading(true);
    apiGet(`/admin/batches/${batchId}`, token)
      .then((data) => {
        setBatch(data.batch);
        setJobs(data.jobs);
        setError(null);
      })
      .catch((e) => setError(e.message))
      .finally(() => setBatchLoading(false));
  }, [batchId, token]);

  // Live updates over WebSocket
  useEffect(() => {
    if (!batchId || !token) return;
    const ws = new WebSocket(`${WS_BASE}/admin/batches/${batchId}/live?token=${token}`);
    wsRef.current = ws;

    ws.onmessage = (event) => {
      const msg = JSON.parse(event.data);
      if (msg.type === "file_progress" || msg.type === "file_done") {
        setJobs((prev) =>
          prev.map((j) => (j.id === msg.job_id ? { ...j, status: msg.status, catalog_id: msg.catalog_id, error: msg.error } : j))
        );
      }
      if (msg.type === "batch_done") {
        setBatch((prev) => (prev ? { ...prev, status: "done" } : prev));
        apiGet(`/admin/batches/${batchId}`, token).then((data) => setBatch(data.batch)).catch(() => {});
      }
      if (msg.type === "batch_cancelled") {
        setBatch((prev) => (prev ? { ...prev, status: "cancelled" } : prev));
        setCancelling(false);
      }
    };

    return () => ws.close();
  }, [batchId, token]);

  const doneCount = jobs.filter((j) => ["done", "needs_review", "duplicate", "failed", "cancelled"].includes(j.status)).length;
  const pct = jobs.length ? Math.round((doneCount / jobs.length) * 100) : 0;
  const isRunning = batch?.status === "running";

  const cancelBatch = async () => {
    if (!confirm("Stop this import? Files already being processed will finish, but nothing further will be cataloged.")) return;
    setCancelling(true);
    try {
      await apiPost(`/admin/batches/${batchId}/cancel`, {}, token);
    } catch (e) {
      setError(e.message);
      setCancelling(false);
    }
  };

  return (
    <div>
      <h1 className="page-title">Bulk import</h1>

      {!batchId && (
        <form className="import-form" onSubmit={startImport}>
          <FilePicker files={files} onFilesChange={setFiles} />

          <label className="checkbox-field">
            <input type="checkbox" checked={useTier2} onChange={(e) => setUseTier2(e.target.checked)} />
            <span>Use LLM fallback for uncertain metadata (Tier 2)</span>
          </label>

          {error && <p className="form-error">{error}</p>}

          {uploading && (
            <div className="progress-track">
              <div className="progress-fill" style={{ width: `${Math.round(uploadProgress * 100)}%` }} />
            </div>
          )}

          <button className="btn btn-primary" type="submit" disabled={uploading || files.length === 0}>
            {uploading ? `Uploading… ${Math.round(uploadProgress * 100)}%` : `Start import${files.length ? ` (${files.length} file${files.length === 1 ? "" : "s"})` : ""}`}
          </button>
        </form>
      )}

      {batchId && batchLoading && <p className="muted">Loading batch…</p>}

      {batchId && !batchLoading && !batch && (
        <div className="empty-state">
          <p className="empty-headline">Couldn't load this import</p>
          <p className="muted">{error || "Something went wrong fetching this batch."}</p>
          <button className="btn btn-secondary" onClick={() => { setBatchId(null); setBatch(null); setJobs([]); setParams({}); }}>
            Start a new import
          </button>
        </div>
      )}

      {batchId && batch && (
        <div className="import-monitor">
          <div className="import-monitor-head">
            <div>
              <p className="muted">{jobs.length} file{jobs.length === 1 ? "" : "s"} in this batch</p>
              <span className={`status-pill status-${batch.status}`}>{batch.status}</span>
            </div>
            <div className="import-monitor-actions">
              {isRunning && (
                <button className="btn btn-danger btn-sm" onClick={cancelBatch} disabled={cancelling}>
                  {cancelling ? "Stopping…" : "Cancel import"}
                </button>
              )}
              <button
                className="btn btn-secondary btn-sm"
                onClick={() => { setBatchId(null); setBatch(null); setJobs([]); setParams({}); }}
              >
                Start a new import
              </button>
            </div>
          </div>

          <div className="progress-track">
            <div className="progress-fill" style={{ width: `${pct}%` }} />
          </div>
          <p className="muted">{doneCount} / {jobs.length} files processed</p>

          <div className="job-list">
            {jobs.map((j) => (
              <div className="job-row" key={j.id}>
                <span className="job-filename">{j.filename}</span>
                <span className={`status-pill status-${j.status}`}>{STATUS_LABEL[j.status] || j.status}</span>
                {j.error && <span className="muted job-error">{j.error}</span>}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
