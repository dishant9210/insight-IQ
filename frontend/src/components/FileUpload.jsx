import React, { useState } from 'react';

const FileUpload = ({ onUploadSuccess }) => {
  const [file, setFile] = useState(null);
  const [loading, setLoading] = useState(false);

  const handleUpload = async () => {
    if (!file) return;
    setLoading(true);

    const formData = new FormData();
    formData.append('file', file);
    console.log(formData);

    try {
      // Note: Ensure your FastAPI is running on port 8000
      const response = await fetch('http://127.0.0.1:8000/api/upload', {
        method: 'POST',
        body: formData,
      });

      if (response.ok) {
        const data = await response.json();
        
        console.log(data);
        onUploadSuccess(data); // This tells the parent app we are ready
      }
    } catch (err) {
      console.error("Upload failed", err);
      alert("Error uploading file. Is the backend running?");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="p-8 border-2 border-dashed border-slate-300 rounded-xl bg-white text-center">
      <input 
        type="file" 
        accept=".csv , .json, .xlsx, .parquet" 
        onChange={(e) => setFile(e.target.files[0])}
        className="mb-4 block w-full text-sm text-slate-500 file:mr-4 file:py-2 file:px-4 file:rounded-full file:border-0 file:text-sm file:font-semibold file:bg-blue-50 file:text-blue-700 hover:file:bg-blue-100"
      />
      <button 
        onClick={handleUpload}
        disabled={loading || !file}
        className="bg-blue-600 text-white px-6 py-2 rounded-lg font-medium hover:bg-blue-700 disabled:bg-slate-400 transition-colors"
      >
        {loading ? "Processing..." : "Analyze CSV"}
      </button>
    </div>
  );
};

export default FileUpload;