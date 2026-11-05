import { useCallback, useEffect, useState } from 'react';
import { deleteDataset, getHistory, listDatasets } from '../api';

const when = (iso) => new Date(iso).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' });

// Your files and past questions. `version` bumps after each new question so the list reloads.
const HistoryPanel = ({ version, activeDatasetId, onOpenDataset, onOpenAnswer, onDatasetDeleted }) => {
  const [items, setItems] = useState([]);
  const [nextBefore, setNextBefore] = useState(null);
  const [datasets, setDatasets] = useState([]);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    setError('');
    try {
      const [page, files] = await Promise.all([getHistory(), listDatasets()]);
      setItems(page.items);
      setNextBefore(page.next_before);
      setDatasets(files);
    } catch (err) {
      setError(err.message);
    }
  }, []);

  // fetching on mount and after each question; the state is set once the request returns
  // eslint-disable-next-line react-hooks/set-state-in-effect
  useEffect(() => { load(); }, [load, version]);

  const more = async () => {
    try {
      const page = await getHistory({ before: nextBefore });
      setItems((prev) => [...prev, ...page.items]);
      setNextBefore(page.next_before);
    } catch (err) {
      setError(err.message);
    }
  };

  const remove = async (d) => {
    if (!window.confirm(`Delete ${d.filename}? Its data is removed; your questions stay in history.`)) return;
    try {
      await deleteDataset(d.dataset_id);
      onDatasetDeleted(d.dataset_id);
      load();
    } catch (err) {
      setError(err.message);
    }
  };

  return (
    <aside className="space-y-6 text-sm">
      {error && <p className="text-red-600">{error}</p>}

      <section>
        <h3 className="text-xs font-bold uppercase tracking-widest text-slate-400 mb-2">Your files</h3>
        {datasets.length === 0 && <p className="text-slate-400">Files you upload while signed in show up here.</p>}
        <ul className="space-y-1">
          {datasets.map((d) => (
            <li key={d.dataset_id} className="flex items-center gap-2">
              <button
                onClick={() => onOpenDataset(d.dataset_id)}
                disabled={d.status !== 'ready'}
                className={`flex-1 text-left truncate hover:text-blue-700 disabled:text-slate-400 ${d.dataset_id === activeDatasetId ? 'font-semibold text-blue-700' : 'text-slate-700'}`}
                title={`${d.rows.toLocaleString()} rows · uploaded ${when(d.created_at)}`}
              >
                {d.filename}
              </button>
              <button onClick={() => remove(d)} className="text-slate-300 hover:text-red-600" aria-label={`Delete ${d.filename}`}>✕</button>
            </li>
          ))}
        </ul>
      </section>

      <section>
        <h3 className="text-xs font-bold uppercase tracking-widest text-slate-400 mb-2">History</h3>
        {items.length === 0 && <p className="text-slate-400">Questions you ask will be saved here.</p>}
        <ul className="space-y-2">
          {items.map((q) => (
            <li key={q.query_id}>
              <button
                onClick={() => onOpenAnswer(q)}
                disabled={q.status !== 'ok'}
                className="w-full text-left rounded-lg px-2 py-1.5 hover:bg-white disabled:hover:bg-transparent"
              >
                <span className={`block truncate ${q.status === 'ok' ? 'text-slate-800' : 'text-slate-400 line-through'}`}>
                  {q.question}
                </span>
                <span className="block text-xs text-slate-400 truncate">
                  {q.filename ?? 'file expired'} · {when(q.created_at)}
                  {q.feedback === true && ' · 👍'}{q.feedback === false && ' · 👎'}
                </span>
              </button>
            </li>
          ))}
        </ul>
        {nextBefore && (
          <button onClick={more} className="mt-2 text-blue-600 hover:underline">Show older</button>
        )}
      </section>
    </aside>
  );
};

export default HistoryPanel;
