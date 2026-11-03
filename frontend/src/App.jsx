import { useState } from 'react';
import FileUpload from './components/FileUpload';
import ChatInput from './components/ChatInput';
import ResultsTable from './components/ResultsTable';
import { queryDataset } from './api';

function App() {
  const [dataset, setDataset] = useState(null);
  const [queryData, setQueryData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleQuery = async (question) => {
    if (!question || !dataset) return;
    setLoading(true);
    setError('');
    try {
      const data = await queryDataset(dataset.dataset_id, question);
      setQueryData(data);
    } catch (err) {
      setQueryData(null);
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-50 p-8 space-y-8 max-w-5xl mx-auto">
      <header>
        <h1 className="text-3xl font-bold text-slate-900">InsightIQ</h1>
        <p className="text-slate-500">Conversational Data Analysis</p>
      </header>

      <FileUpload
        onUploadSuccess={(data) => {
          setDataset(data);
          setQueryData(null);
          setError('');
        }}
      />

      <ChatInput onQuerySubmit={handleQuery} isLoading={loading} disabled={!dataset} />

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg text-sm">
          {error}
        </div>
      )}

      <ResultsTable queryData={queryData} />
    </div>
  );
}
export default App;
