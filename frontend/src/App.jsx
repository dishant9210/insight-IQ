import FileUpload from './components/FileUpload'

function App() {
  return (
    <div className="min-h-screen bg-slate-50 p-8">
      <div className="max-w-2xl mx-auto">
        <h1 className="text-4xl font-bold text-slate-900 mb-2">IngestIQ Pro</h1>
        <p className="text-slate-600 mb-8">Upload a CSV to start asking natural language questions.</p>
        
        <FileUpload onUploadSuccess={(data) => console.log("Backend says:", data)} />
      </div>
    </div>
  )
}

export default App