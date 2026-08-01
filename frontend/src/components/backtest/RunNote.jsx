import { useState, useEffect } from "react";
import PropTypes from "prop-types";
import api from "../../api/client";

/*
 * A saveable human note on one backtest run.
 *
 * The run's numbers are immutable evidence; this is the one editable, human
 * layer on top — why the run was worth doing, what to make of the result. The
 * save is audited on the backend, so even a note leaves a trail.
 */
export default function RunNote({ runId, initialNote, onSaved }) {
  const [note, setNote] = useState(initialNote || "");
  const [saving, setSaving] = useState(false);
  const [status, setStatus] = useState(null);

  // A different run mounts a fresh instance via `key`, but guard anyway.
  useEffect(() => { setNote(initialNote || ""); }, [initialNote, runId]);

  const dirty = note !== (initialNote || "");

  const save = async () => {
    setSaving(true);
    setStatus(null);
    try {
      const res = await api.post(`/backtest-runs/${runId}/note`, { note });
      setStatus({ ok: true, text: "Saved" });
      onSaved?.(res.data.notes ?? null);
    } catch (err) {
      setStatus({ ok: false, text: err.response?.data?.error || "Could not save the note." });
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="run-note">
      <p className="label">Your note</p>
      <textarea
        className="field run-note-input"
        rows={3}
        maxLength={2000}
        placeholder="Why you ran this, and what to make of the result…"
        value={note}
        onChange={(e) => setNote(e.target.value)}
      />
      <div className="run-note-actions">
        <button className="btn btn-primary btn-sm" onClick={save} disabled={saving || !dirty}>
          {saving ? "Saving…" : "Save note"}
        </button>
        {dirty && !saving && <span className="run-note-hint">Unsaved changes</span>}
        {status && (
          <span className={status.ok ? "trade-ok" : "trade-err"}>{status.text}</span>
        )}
      </div>
    </div>
  );
}

RunNote.propTypes = {
  runId: PropTypes.string.isRequired,
  initialNote: PropTypes.string,
  onSaved: PropTypes.func,
};
