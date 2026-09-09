import { Link } from "react-router-dom";

const SUBJECT_COLORS = {
  mathematics: "tag-purple",
  physics: "tag-blue",
  chemistry: "tag-orange",
  biology: "tag-green",
  history: "tag-red",
  accounting: "tag-indigo",
  economics: "tag-teal",
};

function subjectClass(subject) {
  return SUBJECT_COLORS[subject] || "tag-neutral";
}

export default function PaperList({ papers, loading, emptyMessage }) {
  if (loading) {
    return <p className="muted">Loading papers…</p>;
  }

  if (!papers || papers.length === 0) {
    return (
      <div className="empty-state">
        <p className="empty-headline">No papers found</p>
        <p className="muted">{emptyMessage || "Try a different search or filter."}</p>
      </div>
    );
  }

  return (
    <div className="paper-table">
      <div className="paper-table-head">
        <span>Paper</span>
        <span>Subject</span>
        <span>Level</span>
        <span>Year</span>
        <span>Session</span>
        <span>Board</span>
        <span>Paper</span>
        <span></span>
      </div>
      {papers.map((p) => (
        <div className="paper-row" key={p.id}>
          <Link to={`/papers/${p.id}`} className="paper-row-name">
            <span className="paper-icon" aria-hidden="true">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none"><path d="M6 3h9l4 4v14H6a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1Z" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" /><path d="M14 3v5h5" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" /></svg>
            </span>
            <span>
              <span className="paper-title">{p.filename}</span>
            </span>
          </Link>
          <span className={`tag ${subjectClass(p.subject)}`}>{p.subject || "—"}</span>
          <span className="muted">{p.level || "—"}</span>
          <span className="muted">{p.year || "TBD"}</span>
          <span className="muted">{p.session || "—"}</span>
          <span className="muted">{p.exam_board || "—"}</span>
          <span className="muted">{p.paper_number ? `P${p.paper_number}` : "—"}</span>
          <a
            className="icon-btn"
            href={`${import.meta.env.VITE_API_BASE || "http://localhost:8000"}/papers/${p.id}/download`}
            title="Download"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none"><path d="M12 3v12m0 0-4-4m4 4 4-4M5 19h14" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" /></svg>
          </a>
        </div>
      ))}
    </div>
  );
}
