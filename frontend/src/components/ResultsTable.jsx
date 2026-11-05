import { useState } from 'react';
import { sendFeedback } from '../api';

const ResultsTable = ({ queryData }) => {
  const [vote, setVote] = useState(null);
  const [voteError, setVoteError] = useState('');
  const result = queryData?.result || [];
  const insight = queryData?.insight || "";
  const sql = queryData?.sql || "";
  const truncated = queryData?.truncated || false;
  const cached = queryData?.cached || false;
  const examplesUsed = queryData?.examples_used || 0;
  const queryId = queryData?.query_id;

  const rate = async (helpful) => {
    setVoteError('');
    try {
      await sendFeedback(queryId, helpful);
      setVote(helpful);
    } catch (err) {
      setVoteError(err.message);
    }
  };

  if (!queryData) return null;

  const headers = result.length ? Object.keys(result[0]) : [];

  return (
    <div className="space-y-6 animate-in fade-in duration-500">

      {/* LLM Insight Section */}
      {insight && (
        <div className="bg-white p-6 rounded-xl border border-blue-100 shadow-sm border-l-4 border-l-blue-500">
          <div className="flex items-center justify-between mb-2">
            <h4 className="text-xs font-bold uppercase tracking-widest text-blue-500">AI Insight</h4>
            {cached && (
              <span
                className="text-[10px] font-semibold uppercase tracking-wider text-emerald-700 bg-emerald-50 border border-emerald-200 rounded-full px-2 py-0.5"
                title="Answered from cache: this question was asked before, so no new model call was made"
              >
                Cached
              </span>
            )}
          </div>
          <p className="text-slate-700 leading-relaxed italic">"{insight}"</p>
        </div>
      )}

      {/* Main Data Table */}
      {result.length > 0 && (
        <div className="bg-white rounded-xl shadow-sm border border-slate-200 overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="bg-slate-50 border-b border-slate-200">
                  {headers.map((header) => (
                    <th key={header} className="px-6 py-3 text-xs font-bold text-slate-500 uppercase tracking-wider">
                      {header}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {result.map((row, rowIndex) => (
                  <tr key={rowIndex} className="hover:bg-slate-50/50 transition-colors">
                    {headers.map((header) => (
                      <td key={header} className="px-6 py-4 text-sm text-slate-600 whitespace-nowrap">
                        {row[header] === null || row[header] === undefined ? "—" : String(row[header])}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {truncated && (
            <p className="px-6 py-2 text-xs text-slate-500 bg-slate-50 border-t border-slate-200">
              Showing the first {result.length.toLocaleString()} rows.
            </p>
          )}
        </div>
      )}

      {/* Feedback: thumbs down drops the cached answer and keeps this SQL out of future prompts */}
      {queryId && (
        <div className="flex flex-wrap items-center gap-3 text-xs text-slate-500">
          {vote === null ? (
            <>
              <span>Was this answer right?</span>
              <button onClick={() => rate(true)} className="px-2 py-1 rounded border border-slate-200 hover:bg-emerald-50" aria-label="Yes, helpful">👍</button>
              <button onClick={() => rate(false)} className="px-2 py-1 rounded border border-slate-200 hover:bg-red-50" aria-label="No, wrong">👎</button>
            </>
          ) : (
            <span>{vote ? 'Thanks, this will guide similar questions.' : "Thanks. Ask again and it won't reuse this answer."}</span>
          )}
          {voteError && <span className="text-red-600">{voteError}</span>}
          {examplesUsed > 0 && (
            <span className="ml-auto" title="Similar questions answered before on data with the same columns were shown to the model">
              Guided by {examplesUsed} past answer{examplesUsed > 1 ? 's' : ''}
            </span>
          )}
        </div>
      )}

      {/* SQL Transparency Section */}
      {sql && (
        <details className="group border border-slate-200 rounded-lg bg-slate-50 px-4 py-2">
          <summary className="text-xs text-slate-500 cursor-pointer font-medium list-none flex items-center gap-2">
            <span className="group-open:rotate-90 transition-transform">▶</span>
            Show Generated SQL
          </summary>
          <div className="mt-2 p-3 bg-slate-900 rounded text-pink-400 font-mono text-[11px] overflow-x-auto">
            {sql}
          </div>
        </details>
      )}
    </div>
  );
};

export default ResultsTable;
