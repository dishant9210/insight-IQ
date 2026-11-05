import { useState } from 'react';
import { saveDictionary } from '../api';

// Optional notes per column ("amount: revenue in INR, after discount") that the
// model sees next to the schema.
const ColumnNotes = ({ dataset }) => {
  const [notes, setNotes] = useState(dataset.dictionary || {});
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState('');

  const setNote = (table, column, value) => {
    setNotes((prev) => ({ ...prev, [table]: { ...prev[table], [column]: value } }));
    setMessage('');
  };

  const save = async () => {
    setSaving(true);
    try {
      const data = await saveDictionary(dataset.dataset_id, notes);
      setNotes(data.dictionary || {});
      setMessage('Saved. New questions will use these notes.');
    } catch (err) {
      setMessage(err.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <details className="group text-left border border-slate-200 rounded-lg px-4 py-2 bg-slate-50">
      <summary className="text-xs text-slate-500 cursor-pointer font-medium list-none flex items-center gap-2">
        <span className="group-open:rotate-90 transition-transform">▶</span>
        Describe your columns (optional, improves answers)
      </summary>
      <div className="mt-3 space-y-4">
        {dataset.tables.map((t) => (
          <div key={t.name}>
            {dataset.tables.length > 1 && <p className="text-xs font-semibold text-slate-600 mb-1">{t.name}</p>}
            <div className="grid grid-cols-1 sm:grid-cols-[minmax(0,10rem)_1fr] gap-x-3 gap-y-1 items-center">
              {t.columns.map((c) => (
                <label key={c} className="contents">
                  <code className="text-xs text-blue-700 truncate">{c}</code>
                  <input
                    type="text"
                    maxLength={300}
                    value={notes[t.name]?.[c] || ''}
                    onChange={(e) => setNote(t.name, c, e.target.value)}
                    placeholder="e.g. revenue in INR, after discount"
                    className="w-full text-sm border border-slate-200 rounded px-2 py-1 bg-white"
                  />
                </label>
              ))}
            </div>
          </div>
        ))}
        <div className="flex items-center gap-3">
          <button
            onClick={save}
            disabled={saving}
            className="text-sm bg-slate-800 text-white px-4 py-1.5 rounded-lg hover:bg-slate-900 disabled:bg-slate-400"
          >
            {saving ? 'Saving...' : 'Save notes'}
          </button>
          {message && <span className="text-xs text-slate-500">{message}</span>}
        </div>
      </div>
    </details>
  );
};

export default ColumnNotes;
