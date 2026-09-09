import { useEffect, useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { apiGet } from "../../api";
import PaperList from "../../components/PaperList";

const SUBJECT_ICONS = {
  mathematics: "📐",
  physics: "⚛️",
  chemistry: "🧪",
  biology: "🌿",
  accounting: "📊",
  economics: "🥧",
  history: "🏛️",
  geography: "🌍",
  english: "📖",
  computer_science: "💻",
};

export default function Home() {
  const [subjects, setSubjects] = useState([]);
  const [latest, setLatest] = useState([]);
  const [filters, setFilters] = useState({ subject: "", level: "", year: "", exam_board: "" });
  const [facets, setFacets] = useState({ subjects: [], levels: [], years: [], exam_boards: [] });
  const [q, setQ] = useState("");
  const navigate = useNavigate();

  useEffect(() => {
    apiGet("/subjects").then(setSubjects).catch(() => {});
    apiGet("/papers/latest?limit=6").then(setLatest).catch(() => {});
    apiGet("/facets").then(setFacets).catch(() => {});
  }, []);

  const runSearch = (e) => {
    e?.preventDefault();
    const params = new URLSearchParams();
    if (q) params.set("q", q);
    Object.entries(filters).forEach(([k, v]) => v && params.set(k, v));
    navigate(`/papers?${params.toString()}`);
  };

  return (
    <div className="home">
      <section className="hero">
        <div className="hero-copy">
          <h1>
            Find the right paper.
            <br />
            <span className="hero-accent">Ace</span> your exam.
          </h1>
          <p className="muted">
            Search our collection of past exam papers across subjects, years and exam boards.
            Simple. Fast. Reliable.
          </p>
        </div>
        <div className="hero-art" aria-hidden="true">
          <svg width="140" height="140" viewBox="0 0 140 140" fill="none">
            <rect x="20" y="30" width="70" height="90" rx="6" fill="var(--surface-container-lowest)" stroke="var(--outline-variant)" />
            <rect x="35" y="45" width="40" height="6" rx="3" fill="var(--primary-container)" />
            <rect x="35" y="58" width="40" height="6" rx="3" fill="var(--outline-variant)" />
            <rect x="35" y="71" width="25" height="6" rx="3" fill="var(--outline-variant)" />
            <circle cx="105" cy="95" r="26" fill="var(--tertiary-container)" opacity="0.25" />
          </svg>
        </div>
      </section>

      <form className="search-card" onSubmit={runSearch}>
        <div className="search-card-input">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none"><circle cx="11" cy="11" r="7" stroke="currentColor" strokeWidth="1.8" /><path d="m20 20-3.2-3.2" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" /></svg>
          <input
            type="text"
            placeholder="Search by subject or keyword…"
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
        </div>
        <div className="search-card-filters">
          <select value={filters.subject} onChange={(e) => setFilters((f) => ({ ...f, subject: e.target.value }))}>
            <option value="">Select subject</option>
            {facets.subjects.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
          <select value={filters.level} onChange={(e) => setFilters((f) => ({ ...f, level: e.target.value }))}>
            <option value="">Select level</option>
            {facets.levels.map((l) => <option key={l} value={l}>{l}</option>)}
          </select>
          <select value={filters.year} onChange={(e) => setFilters((f) => ({ ...f, year: e.target.value }))}>
            <option value="">Select year</option>
            {facets.years.map((y) => <option key={y} value={y}>{y}</option>)}
          </select>
          <select value={filters.exam_board} onChange={(e) => setFilters((f) => ({ ...f, exam_board: e.target.value }))}>
            <option value="">Exam board</option>
            {facets.exam_boards.map((b) => <option key={b} value={b}>{b}</option>)}
          </select>
          <button type="submit" className="btn btn-primary">
            Search
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none"><path d="M5 12h14m0 0-5-5m5 5-5 5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" /></svg>
          </button>
        </div>
      </form>

      <section className="section">
        <div className="section-head">
          <h2>Browse by Subject</h2>
          <Link to="/subjects" className="link">View all subjects →</Link>
        </div>
        <div className="subject-grid">
          {subjects.slice(0, 6).map((s) => (
            <Link to={`/papers?subject=${encodeURIComponent(s.subject)}`} key={s.subject} className="subject-card">
              <span className="subject-icon">{SUBJECT_ICONS[s.subject] || "📄"}</span>
              <span className="subject-name">{s.subject}</span>
              <span className="muted subject-count">{s.count} paper{s.count === 1 ? "" : "s"}</span>
            </Link>
          ))}
          {subjects.length === 0 && (
            <p className="muted">No subjects cataloged yet — import some papers from the admin side.</p>
          )}
        </div>
      </section>

      <section className="section">
        <div className="section-head">
          <h2>Recently Added</h2>
          <Link to="/papers?sort=latest" className="link">View all →</Link>
        </div>
        <PaperList papers={latest} emptyMessage="Nothing's been cataloged yet." />
      </section>
    </div>
  );
}
