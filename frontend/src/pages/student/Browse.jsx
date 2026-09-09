import { useEffect, useState, useCallback } from "react";
import { useSearchParams } from "react-router-dom";
import { apiGet } from "../../api";
import PaperList from "../../components/PaperList";

export default function Browse() {
  const [params, setParams] = useSearchParams();
  const [facets, setFacets] = useState({ subjects: [], levels: [], years: [], exam_boards: [], sessions: [] });
  const [papers, setPapers] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);

  const sort = params.get("sort"); // "latest" | "popular" | null

  useEffect(() => {
    apiGet("/facets").then(setFacets).catch(() => {});
  }, []);

  const load = useCallback(() => {
    setLoading(true);
    const endpoint =
      sort === "latest" ? "/papers/latest?limit=50" :
      sort === "popular" ? "/papers/popular?limit=50" :
      (() => {
        const q = new URLSearchParams();
        ["q", "subject", "level", "year", "session", "exam_board"].forEach((k) => {
          const v = params.get(k);
          if (v) q.set(k, v);
        });
        return `/search?${q.toString()}`;
      })();

    apiGet(endpoint)
      .then((data) => {
        if (Array.isArray(data)) {
          setPapers(data);
          setTotal(data.length);
        } else {
          setPapers(data.results);
          setTotal(data.total);
        }
      })
      .finally(() => setLoading(false));
  }, [params, sort]);

  useEffect(() => { load(); }, [load]);

  const setFilter = (key, value) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value); else next.delete(key);
    next.delete("sort");
    setParams(next);
  };

  const title = sort === "latest" ? "Recently added" : sort === "popular" ? "Most downloaded" : "Search results";

  return (
    <div className="browse">
      <h1 className="page-title">{title}</h1>

      {!sort && (
        <div className="filter-bar">
          <input
            type="text"
            placeholder="Keyword…"
            defaultValue={params.get("q") || ""}
            onBlur={(e) => setFilter("q", e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && setFilter("q", e.target.value)}
          />
          <select value={params.get("subject") || ""} onChange={(e) => setFilter("subject", e.target.value)}>
            <option value="">All subjects</option>
            {facets.subjects.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
          <select value={params.get("level") || ""} onChange={(e) => setFilter("level", e.target.value)}>
            <option value="">All levels</option>
            {facets.levels.map((l) => <option key={l} value={l}>{l}</option>)}
          </select>
          <select value={params.get("year") || ""} onChange={(e) => setFilter("year", e.target.value)}>
            <option value="">All years</option>
            {facets.years.map((y) => <option key={y} value={y}>{y}</option>)}
          </select>
          <select value={params.get("session") || ""} onChange={(e) => setFilter("session", e.target.value)}>
            <option value="">All sessions</option>
            {facets.sessions.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
          <select value={params.get("exam_board") || ""} onChange={(e) => setFilter("exam_board", e.target.value)}>
            <option value="">All boards</option>
            {facets.exam_boards.map((b) => <option key={b} value={b}>{b}</option>)}
          </select>
        </div>
      )}

      <p className="muted results-count">{loading ? "Searching…" : `${total} paper${total === 1 ? "" : "s"}`}</p>

      <PaperList papers={papers} loading={loading} />
    </div>
  );
}
