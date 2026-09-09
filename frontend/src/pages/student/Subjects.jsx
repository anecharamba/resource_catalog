import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { apiGet } from "../../api";

export default function Subjects() {
  const [subjects, setSubjects] = useState([]);

  useEffect(() => {
    apiGet("/subjects").then(setSubjects).catch(() => {});
  }, []);

  return (
    <div className="browse">
      <h1 className="page-title">All subjects</h1>
      <div className="subject-grid subject-grid-wide">
        {subjects.map((s) => (
          <Link to={`/papers?subject=${encodeURIComponent(s.subject)}`} key={s.subject} className="subject-card">
            <span className="subject-name">{s.subject}</span>
            <span className="muted subject-count">{s.count} paper{s.count === 1 ? "" : "s"}</span>
          </Link>
        ))}
        {subjects.length === 0 && <p className="muted">No subjects cataloged yet.</p>}
      </div>
    </div>
  );
}
