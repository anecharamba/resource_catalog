import { useEffect, useState, useMemo } from "react";
import { apiGet, apiPatch } from "../../api";
import { useAuth } from "../../context/AuthContext";

const EDITABLE_FIELDS = ["subject", "level", "year", "session", "exam_board", "paper_number", "doc_type"];

function isIncomplete(row) {
  return !row.subject || !row.level || !row.year || !row.session || !row.exam_board || !row.paper_number;
}

export default function Catalog() {
  const { token } = useAuth();
  const [q, setQ] = useState("");
  const [results, setResults] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState("all"); // "all" | "incomplete" | "needs_review"
  const [editingId, setEditingId] = useState(null);
  const [drafts, setDrafts] = useState({});
  const [savingId, setSavingId] = useState(null);
  const [error, setError] = useState(null);

  const search = () => {
    setLoading(true);
    const params = new URLSearchParams();
    if (q) params.set("q", q);
    params.set("exclude_needs_review", "false"); // catalog view shows everything, flagged or not
    params.set("limit", "200");
    apiGet(`/search?${params.toString()}`)
      .then((data) => {
        setResults(data.results);
        setTotal(data.total);
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  };

  useEffect(() => { search(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const visibleResults = useMemo(() => {
    if (filter === "incomplete") return results.filter(isIncomplete);
    if (filter === "needs_review") return results.filter((r) => r.needs_review);
    return results;
  }, [results, filter]);

  const incompleteCount = useMemo(() => results.filter(isIncomplete).length, [results]);
  const needsReviewCount = useMemo(() => results.filter((r) => r.needs_review).length, [results]);

  const startEdit = (row) => {
    setEditingId(row.id);
    setDrafts((d) => ({
      ...d,
      [row.id]: {
        subject: row.subject || "",
        level: row.level || "",
        year: row.year || "",
        session: row.session || "",
        exam_board: row.exam_board || "",
        paper_number: row.paper_number || "",
        doc_type: row.doc_type || "",
      },
    }));
  };

  const cancelEdit = () => setEditingId(null);

  const setDraftField = (id, field, value) =>
    setDrafts((d) => ({ ...d, [id]: { ...d[id], [field]: value } }));

  const saveEdit = async (row) => {
    const draft = drafts[row.id];
    setSavingId(row.id);
    setError(null);
    try {
      const updated = await apiPatch(`/admin/catalog/${row.id}`, {
        subject: draft.subject || null,
        level: draft.level || null,
        year: draft.year ? Number(draft.year) : null,
        session: draft.session || null,
        exam_board: draft.exam_board || null,
        paper_number: draft.paper_number ? Number(draft.paper_number) : null,
        doc_type: draft.doc_type || null,
        approve: true,
      }, token);
      setResults((prev) => prev.map((r) => (r.id === row.id ? { ...r, ...updated } : r)));
      setEditingId(null);
    } catch (e) {
      setError(e.message);
    } finally {
      setSavingId(null);
    }
  };

  return (
    <div>
      <h1 className="page-title">Catalog</h1>

      <div className="filter-bar">
        <input
          type="text"
          placeholder="Search filename or content…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && search()}
        />
        <button className="btn btn-secondary" onClick={search}>Search</button>
      </div>

      <div className="catalog-filter-tabs">
        <button
          className={`filter-tab${filter === "all" ? " active" : ""}`}
          onClick={() => setFilter("all")}
        >
          All <span className="filter-tab-count">{results.length}</span>
        </button>
        <button
          className={`filter-tab${filter === "incomplete" ? " active" : ""}`}
          onClick={() => setFilter("incomplete")}
        >
          Missing details <span className="filter-tab-count">{incompleteCount}</span>
        </button>
        <button
          className={`filter-tab${filter === "needs_review" ? " active" : ""}`}
          onClick={() => setFilter("needs_review")}
        >
          Needs review <span className="filter-tab-count">{needsReviewCount}</span>
        </button>
      </div>

      {error && <p className="form-error">{error}</p>}
      <p className="muted results-count">
        {loading ? "Loading…" : `${visibleResults.length} of ${total} record${total === 1 ? "" : "s"}`}
      </p>

      <div className="catalog-list">
        {visibleResults.map((r) => {
          const editing = editingId === r.id;
          const draft = drafts[r.id] || {};
          const incomplete = isIncomplete(r);

          return (
            <div className={`catalog-row${incomplete ? " incomplete" : ""}${editing ? " editing" : ""}`} key={r.id}>
              <div className="catalog-row-main">
                <span className="paper-title">{r.filename}</span>
                <div className="catalog-row-badges">
                  {incomplete && <span className="badge badge-warning">Missing details</span>}
                  {r.needs_review && <span className="status-pill status-needs_review">Needs review</span>}
                </div>
              </div>

              {!editing ? (
                <>
                  <div className="catalog-row-fields">
                    <div><span className="muted">Subject</span><span>{r.subject || "—"}</span></div>
                    <div><span className="muted">Level</span><span>{r.level || "—"}</span></div>
                    <div><span className="muted">Year</span><span>{r.year || "—"}</span></div>
                    <div><span className="muted">Session</span><span>{r.session || "—"}</span></div>
                    <div><span className="muted">Board</span><span>{r.exam_board || "—"}</span></div>
                    <div><span className="muted">Paper #</span><span>{r.paper_number || "—"}</span></div>
                    <div><span className="muted">Type</span><span>{r.doc_type || "—"}</span></div>
                  </div>
                  <button className="btn btn-secondary btn-sm" onClick={() => startEdit(r)}>Edit</button>
                </>
              ) : (
                <>
                  <div className="catalog-row-edit-fields">
                    <label className="field">
                      <span>Subject</span>
                      <input value={draft.subject} onChange={(e) => setDraftField(r.id, "subject", e.target.value)} />
                    </label>
                    <label className="field">
                      <span>Level</span>
                      <input value={draft.level} onChange={(e) => setDraftField(r.id, "level", e.target.value)} />
                    </label>
                    <label className="field">
                      <span>Year</span>
                      <input value={draft.year} onChange={(e) => setDraftField(r.id, "year", e.target.value)} min="2000" max={new Date().getFullYear()} inputMode="numeric" />
                    </label>
                    <label className="field">
                      <span>Session</span>
                      <select value={draft.session} onChange={(e) => setDraftField(r.id, "session", e.target.value)}>
                        <option value="">Select session</option>
                        <option value="June">June</option>
                        <option value="November">November</option>
                      </select>
                    </label>
                    <label className="field">
                      <span>Exam board</span>
                      <input value={draft.exam_board} onChange={(e) => setDraftField(r.id, "exam_board", e.target.value)} />
                    </label>
                    <label className="field">
                      <span>Paper #</span>
                      <input value={draft.paper_number} onChange={(e) => setDraftField(r.id, "paper_number", e.target.value)} inputMode="numeric" />
                    </label>
                    <label className="field">
                      <span>Type</span>
                      <input value={draft.doc_type} onChange={(e) => setDraftField(r.id, "doc_type", e.target.value)} />
                    </label>
                  </div>
                  <div className="catalog-row-edit-actions">
                    <button className="link-btn" onClick={cancelEdit} disabled={savingId === r.id}>Cancel</button>
                    <button className="btn btn-primary btn-sm" onClick={() => saveEdit(r)} disabled={savingId === r.id}>
                      {savingId === r.id ? "Saving…" : "Save"}
                    </button>
                  </div>
                </>
              )}
            </div>
          );
        })}

        {!loading && visibleResults.length === 0 && (
          <div className="empty-state">
            <p className="empty-headline">Nothing here</p>
            <p className="muted">
              {filter === "incomplete" ? "No papers are missing details right now." :
               filter === "needs_review" ? "Nothing is waiting for review." :
               "No papers match your search."}
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
