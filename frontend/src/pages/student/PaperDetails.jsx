import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { apiGet, API_BASE } from "../../api";

export default function PaperDetails() {
  const { id } = useParams();
  const [paper, setPaper] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    apiGet(`/papers/${id}`).then(setPaper).catch((e) => setError(e.message));
  }, [id]);

  if (error) return <p className="muted">Couldn't load this paper. {error}</p>;
  if (!paper) return <p className="muted">Loading…</p>;

  const rows = [
    ["Subject", paper.subject],
    ["Level", paper.level],
    ["Year", paper.year || "Not confirmed"],
    ["Session", paper.session || "Not confirmed"],
    ["Exam board", paper.exam_board],
    ["Paper number", paper.paper_number ? `Paper ${paper.paper_number}` : "—"],
    ["Type", paper.doc_type],
    ["Syllabus era", paper.syllabus_era || "Unconfirmed"],
  ];

  return (
    <div className="paper-details">
      <Link to="/papers" className="link back-link">← Back to results</Link>
      <div className="paper-details-card">
        <div className="paper-details-icon" aria-hidden="true">
          <svg width="32" height="32" viewBox="0 0 24 24" fill="none"><path d="M6 3h9l4 4v14H6a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1Z" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" /><path d="M14 3v5h5" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" /></svg>
        </div>
        <h1>{paper.filename}</h1>

        <dl className="meta-grid">
          {rows.map(([label, value]) => (
            <div key={label}>
              <dt>{label}</dt>
              <dd>{value || "—"}</dd>
            </div>
          ))}
        </dl>

        <div className="paper-actions">
          <a className="btn btn-primary" href={`${API_BASE}/papers/${paper.id}/download`}>
            Download
          </a>
          <a className="btn btn-secondary" href={`${API_BASE}/papers/${paper.id}/download`} target="_blank" rel="noreferrer">
            View in new tab
          </a>
        </div>
      </div>
    </div>
  );
}
