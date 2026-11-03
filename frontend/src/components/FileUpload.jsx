import { useState } from 'react';
import { uploadDataset } from '../api';

const FileUpload = ({ onUploadSuccess }) => {
  const [file, setFile] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [uploaded, setUploaded] = useState(null);

  const handleUpload = async () => {
    if (!file) return;
    setLoading(true);
    setError('');

    try {
      const data = await uploadDataset(file);
      setUploaded(data);
      onUploadSuccess(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="p-8 border-2 border-dashed border-slate-300 rounded-xl bg-white text-center space-y-4">
      <input
        type="file"
        accept=".csv,.json,.xlsx,.xls,.parquet"
        onChange={(e) => setFile(e.target.files[0])}
        className="block w-full text-sm text-slate-500 file:mr-4 file:py-2 file:px-4 file:rounded-full file:border-0 file:text-sm file:font-semibold file:bg-blue-50 file:text-blue-700 hover:file:bg-blue-100"
      />
      <button
        onClick={handleUpload}
        disabled={loading || !file}
        className="bg-blue-600 text-white px-6 py-2 rounded-lg font-medium hover:bg-blue-700 disabled:bg-slate-400 transition-colors"
      >
        {loading ? "Processing..." : "Analyze File"}
      </button>

      {error && <p className="text-sm text-red-600">{error}</p>}

      {uploaded && !error && (
        <div className="text-sm text-slate-600 text-left">
          <p>
            <span className="font-medium text-slate-800">{uploaded.filename}</span>
            {' — '}{uploaded.rows.toLocaleString()} rows, {uploaded.columns.length} columns
          </p>
          {uploaded.warnings?.length > 0 && (
            <ul className="mt-1 text-amber-700 list-disc list-inside">
              {uploaded.warnings.map((w, i) => <li key={i}>{w}</li>)}
            </ul>
          )}
        </div>
      )}
    </div>
  );
};

export default FileUpload;
