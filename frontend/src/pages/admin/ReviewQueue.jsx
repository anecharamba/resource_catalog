import { useEffect, useState } from "react";
import { apiGet, apiPatch } from "../../api";
import { useAuth } from "../../context/AuthContext";

export default function ReviewQueue() {
  const { token } = useAuth();
  const [items, setItems] = useState([]);
  const [drafts, setDrafts] = useState({});
  const [busyId, setBusyId] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const load = () => {
    setLoading(true);
    setError(null);
    apiGet("/admin/review-queue", token)
      .then(setItems)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  };

  useEffect(load, [token]); // eslint-disable-line react-hooks/exhaustive-deps

  const setDraft = (id, field, value) =>
    setDrafts((d) => ({ ...d, [id]: { ...(d[id] || {}), [field]: value } }));

  const approve = async (item) => {
    setBusyId(item.id);
    const draft = drafts[item.id] || {};
    try {
      await apiPatch(`/admin/catalog/${item.id}`, {
        subject: draft.subject ?? item.subject,
        level: draft.level ?? item.level,
        year: draft.year ? Number(draft.year) : item.year,
        session: draft.session ?? item.session,
        exam_board: draft.exam_board ?? item.exam_board,
        paper_number: draft.paper_number ? Number(draft.paper_number) : item.paper_number,
        approve: true,
      }, token);
      setItems((prev) => prev.filter((i) => i.id !== item.id));
    } finally {
      setBusyId(null);
    }
  };

  if (loading) return <p className="muted">Loading…</p>;

  if (error) {
    return (
      <div className="empty-state">
        <p className="empty-headline">Couldn't load the review queue</p>
        <p className="muted">{error}</p>
        <button className="btn btn-secondary" onClick={load}>Try again</button>
      </div>
    );
  }

  if (items.length === 0) {
    return (
      <div>
        <h1 className="page-title">Review queue</h1>
        <p className="muted">Nothing needs review right now.</p>
      </div>
    );
  }

  return (
    <div>
      <h1 className="page-title">Review queue <span className="muted">({items.length})</span></h1>

      <div className="review-list">
        {items.map((item) => {
          const d = drafts[item.id] || {};
          return (
            <div className="review-card" key={item.id}>
              <div className="review-card-head">
                <span className="paper-title">{item.filename}</span>
                <span className="muted">{item.review_reasons}</span>
              </div>

              {item.text_snippet && (
                <p className="review-snippet">{item.text_snippet.slice(0, 220)}…</p>
              )}

              <div className="review-fields">
                <label className="field">
                  <span>Subject</span>
                  <input defaultValue={item.subject || ""} onChange={(e) => setDraft(item.id, "subject", e.target.value)} />
                </label>
                <label className="field">
                  <span>Level</span>
                  <input defaultValue={item.level || ""} onChange={(e) => setDraft(item.id, "level", e.target.value)} />
                </label>
                <label className="field">
                  <span>Year</span>
                  <input defaultValue={item.year || ""} onChange={(e) => setDraft(item.id, "year", e.target.value)} min="2000" max={new Date().getFullYear()} inputMode="numeric" />
                </label>
                <label className="field">
                  <span>Session</span>
                  <select defaultValue={item.session || ""} onChange={(e) => setDraft(item.id, "session", e.target.value)}>
                    <option value="">Select session</option>
                    <option value="June">June</option>
                    <option value="November">November</option>
                  </select>
                </label>
                <label className="field">
                  <span>Exam board</span>
                  <input defaultValue={item.exam_board || ""} onChange={(e) => setDraft(item.id, "exam_board", e.target.value)} />
                </label>
                <label className="field">
                  <span>Paper #</span>
                  <input defaultValue={item.paper_number || ""} onChange={(e) => setDraft(item.id, "paper_number", e.target.value)} />
                </label>
              </div>

              <div className="review-actions">
                <button className="btn btn-primary" disabled={busyId === item.id} onClick={() => approve(item)}>
                  {busyId === item.id ? "Saving…" : "Save & approve"}
                </button>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
