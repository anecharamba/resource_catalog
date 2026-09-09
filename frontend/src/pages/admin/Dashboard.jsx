import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { apiGet } from "../../api";
import { useAuth } from "../../context/AuthContext";

export default function Dashboard() {
  const { token } = useAuth();
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = () => {
    setLoading(true);
    setError(null);
    apiGet("/admin/dashboard", token)
      .then(setData)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  };

  useEffect(load, [token]); // eslint-disable-line react-hooks/exhaustive-deps

  if (loading) return <p className="muted">Loading…</p>;

  if (error) {
    return (
      <div className="empty-state">
        <p className="empty-headline">Couldn't load the dashboard</p>
        <p className="muted">{error}</p>
        <button className="btn btn-secondary" onClick={load}>Try again</button>
      </div>
    );
  }

  if (!data) return null;

  return (
    <div>
      <h1 className="page-title">Dashboard</h1>

      <div className="stat-grid">
        <Link to="/admin/catalog" className="stat-card stat-card-link">
          <span className="stat-value">{data.total_catalog_entries}</span>
          <span className="muted">Catalog entries</span>
        </Link>
        <Link to="/admin/review" className="stat-card stat-card-link">
          <span className="stat-value">{data.needs_review}</span>
          <span className="muted">Needs review</span>
        </Link>
        <div className="stat-card">
          <span className="stat-value">{data.by_subject.length}</span>
          <span className="muted">Subjects covered</span>
        </div>
      </div>

      {data.needs_review > 0 && (
        <Link to="/admin/review" className="callout-link">
          {data.needs_review} paper{data.needs_review === 1 ? "" : "s"} waiting in the review queue →
        </Link>
      )}

      <section className="section">
        <h2>Recent imports</h2>
        {data.recent_batches.length === 0 && <p className="muted">No imports yet.</p>}
        <div className="batch-table">
          {data.recent_batches.map((b) => (
            <Link to={`/admin/import?batch=${b.id}`} key={b.id} className="batch-row">
              <span className="batch-folder">
                {b.source_folder.includes("/uploads/")
                  ? `Uploaded batch · ${b.total_files} file${b.total_files === 1 ? "" : "s"}`
                  : b.source_folder}
              </span>
              <span className={`status-pill status-${b.status}`}>{b.status}</span>
              <span className="muted">{b.processed_files}/{b.total_files} processed</span>
              <span className="muted">{b.needs_review_files} needs review</span>
            </Link>
          ))}
        </div>
      </section>

      <section className="section">
        <h2>By subject</h2>
        <div className="subject-bars">
          {data.by_subject.map((s) => (
            <div className="subject-bar-row" key={s.subject}>
              <span>{s.subject}</span>
              <div className="subject-bar-track">
                <div
                  className="subject-bar-fill"
                  style={{ width: `${Math.min(100, (s.n / (data.by_subject[0]?.n || 1)) * 100)}%` }}
                />
              </div>
              <span className="muted">{s.n}</span>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
