const ResultsTable = ({ queryData }) => {
  const result = queryData?.result || [];
  const insight = queryData?.insight || "";
  const sql = queryData?.sql || "";
  const truncated = queryData?.truncated || false;
  const cached = queryData?.cached || false;

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
