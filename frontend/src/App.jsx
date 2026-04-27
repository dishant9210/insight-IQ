import { useState } from 'react';
import FileUpload from './components/FileUpload';
import ChatInput from './components/ChatInput';
import ResultsTable from './components/ResultsTable';

function App() {
  const [queryData, setQueryData] = useState({
    result: [],
    insight: "",
    sql: "",
    chart_type: ""
  });
  const [loading, setLoading] = useState(false);
  const [fileId, setFileId] = useState(null); // Track the current active file

  const handleQuery = async (userText) => {
    setLoading(true);
    try {
      
      if (!userText || !fileId) {
        console.error("Invalid input: userText or fileId is missing");
        return;
      }      
      const response = await fetch('http://localhost:8000/api/query', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
          question: userText,
          dataset_id: fileId // Tells backend which uploaded file to query
        })
      });
      const data = await response.json();
      console.log(data)
     
      setQueryData({
        result : data.result,
        insight : data.insight,
        sql : data.sql,
        chart_type : data.chart_type
      });

      console.log(queryData);
    } catch (err) {
      console.error("Query failed", err);
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

      <FileUpload onUploadSuccess={(data) => setFileId(data.dataset_id)} />
      
      <ChatInput onQuerySubmit={handleQuery} isLoading={loading} />
      
      <ResultsTable queryData={queryData} />
    </div>
  );
}
export default App;