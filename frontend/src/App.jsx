import { useEffect, useState } from 'react';
import FileUpload from './components/FileUpload';
import ChatInput from './components/ChatInput';
import ResultsTable from './components/ResultsTable';
import AuthDialog from './components/AuthDialog';
import HistoryPanel from './components/HistoryPanel';
import { getDataset, getPastAnswer, logout, onUserChange, queryDataset, restoreSession } from './api';

function App() {
  const [user, setUser] = useState(null);
  const [showAuth, setShowAuth] = useState(false);
  const [dataset, setDataset] = useState(null);
  const [queryData, setQueryData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [historyVersion, setHistoryVersion] = useState(0);

  useEffect(() => {
    const off = onUserChange(setUser);
    restoreSession();
    return off;
  }, []);

  const signOut = async () => {
    await logout();
    // signed-in files are private; don't leave one on screen
    setDataset(null);
    setQueryData(null);
  };

  const show = (data, message = '') => {
    setQueryData(data);
    setNotice(message);
    setError('');
  };

  const handleQuery = async (question) => {
    if (!question || !dataset) return;
    setLoading(true);
    setError('');
    setNotice('');
    try {
      show(await queryDataset(dataset.dataset_id, question));
    } catch (err) {
      setQueryData(null);
      setError(err.message);
    } finally {
      setLoading(false);
      setHistoryVersion((v) => v + 1);
    }
  };

  const openDataset = async (datasetId) => {
    try {
      setDataset(await getDataset(datasetId));
      show(null);
    } catch (err) {
      setError(err.message);
    }
  };

  const openAnswer = async (item) => {
    try {
      const answer = await getPastAnswer(item.query_id);
      if (answer.dataset_available && answer.dataset_id !== dataset?.dataset_id) {
        setDataset(await getDataset(answer.dataset_id));
      }
      show(answer, answer.dataset_available
        ? `From your history, ${new Date(answer.created_at).toLocaleString()}. Rows re-read from the file.`
        : 'From your history. The file has expired, so only the SQL and the insight are left.');
    } catch (err) {
      setError(err.message);
    }
  };

  return (
    <div className="min-h-screen bg-slate-50 p-8 max-w-7xl mx-auto">
      <header className="flex items-start justify-between mb-8">
        <div>
          <h1 className="text-3xl font-bold text-slate-900">InsightIQ</h1>
          <p className="text-slate-500">Conversational Data Analysis</p>
        </div>
        <div className="text-sm text-slate-600 flex items-center gap-3">
          {user ? (
            <>
              <span className="hidden sm:inline">{user.email}</span>
              <button onClick={signOut} className="px-3 py-1.5 rounded-lg border border-slate-300 hover:bg-white">Sign out</button>
            </>
          ) : (
            <button onClick={() => setShowAuth(true)} className="px-3 py-1.5 rounded-lg border border-slate-300 hover:bg-white">
              Sign in
            </button>
          )}
        </div>
      </header>

      <div className={user ? 'grid gap-8 lg:grid-cols-[1fr_18rem]' : 'max-w-5xl mx-auto'}>
        <main className="space-y-8 min-w-0">
          <FileUpload
            dataset={dataset}
            onUploadSuccess={(data) => {
              setDataset(data);
              show(null);
              setHistoryVersion((v) => v + 1);
            }}
          />

          <ChatInput onQuerySubmit={handleQuery} isLoading={loading} disabled={!dataset} />

          {!user && (
            <p className="text-xs text-slate-400">
              Using InsightIQ as a guest: uploads are removed after a day.{' '}
              <button onClick={() => setShowAuth(true)} className="text-blue-600 hover:underline">Sign in</button>
              {' '}to keep your files private and your questions saved.
            </p>
          )}

          {error && (
            <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg text-sm">
              {error}
            </div>
          )}
          {notice && <p className="text-xs text-slate-500">{notice}</p>}

          <ResultsTable key={queryData?.query_id} queryData={queryData} />
        </main>

        {user && (
          <HistoryPanel
            key={user.id}
            version={historyVersion}
            activeDatasetId={dataset?.dataset_id}
            onOpenDataset={openDataset}
            onOpenAnswer={openAnswer}
            onDatasetDeleted={(id) => {
              if (dataset?.dataset_id === id) {
                setDataset(null);
                setQueryData(null);
              }
            }}
          />
        )}
      </div>

      {showAuth && <AuthDialog onClose={() => setShowAuth(false)} />}
    </div>
  );
}
export default App;
