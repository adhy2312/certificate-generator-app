import React, { useState, useEffect } from 'react';

export default function BulkGeneration() {
  const [inputMethod, setInputMethod] = useState('link');
  const [url, setUrl] = useState('');
  const [file, setFile] = useState(null);
  const [globalEvent, setGlobalEvent] = useState('');
  const [globalDate, setGlobalDate] = useState('');
  const [globalType, setGlobalType] = useState('Certificate of Participation');
  const [sendEmail, setSendEmail] = useState(true);
  
  const [records, setRecords] = useState([]);
  const [preview, setPreview] = useState([]);
  
  const [status, setStatus] = useState({ type: '', message: '' });
  const [isParsing, setIsParsing] = useState(false);
  
  const [batchId, setBatchId] = useState(null);
  const [jobStatus, setJobStatus] = useState(null);

  const handleParse = async () => {
    setIsParsing(true);
    setStatus({ type: '', message: '' });
    
    const formData = new FormData();
    if (inputMethod === 'link') {
      if (!url) {
        setStatus({ type: 'error', message: 'Please provide a Google Sheets link.' });
        setIsParsing(false);
        return;
      }
      formData.append('url', url);
    } else {
      if (!file) {
        setStatus({ type: 'error', message: 'Please upload a file.' });
        setIsParsing(false);
        return;
      }
      formData.append('file', file);
    }

    try {
      const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';
      const response = await fetch(`${API_BASE}/api/parse-preview`, {
        method: 'POST',
        body: formData,
      });
      const data = await response.json();
      
      if (response.ok) {
        setPreview(data.records);
        setRecords(data.full_records);
        setStatus({ type: 'success', message: `Loaded ${data.full_records.length} records successfully.` });
      } else {
        setStatus({ type: 'error', message: data.detail || 'Parsing failed.' });
      }
    } catch (err) {
      setStatus({ type: 'error', message: 'Network error.' });
    } finally {
      setIsParsing(false);
    }
  };

  const handleDispatch = async (sendEmailOverride) => {
    if (!globalEvent) {
      setStatus({ type: 'error', message: 'Please provide a Global Event Name.' });
      return;
    }
    
    setStatus({ type: '', message: '' });
    setSendEmail(sendEmailOverride);
    
    try {
      const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';
      const response = await fetch(`${API_BASE}/api/jobs/bulk`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          records: records.map(r => ({ Name: r.Name, Email: r.Email, Tier: r.Tier, Type: r.Type })),
          event: globalEvent,
          date: globalDate,
          cert_type: globalType,
          send_email: sendEmailOverride
        }),
      });
      const data = await response.json();
      if (response.ok) {
        setBatchId(data.batch_id);
      } else {
        setStatus({ type: 'error', message: data.detail || 'Dispatch failed' });
      }
    } catch (err) {
      setStatus({ type: 'error', message: 'Network error.' });
    }
  };

  const handleCancel = async () => {
    try {
      const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';
      await fetch(`${API_BASE}/api/jobs/${batchId}/cancel`, { method: 'POST' });
      setStatus({ type: 'error', message: 'Process terminated mid-way.' });
    } catch (err) {
      console.error('Failed to cancel', err);
    }
  };

  useEffect(() => {
    let interval;
    if (batchId) {
      interval = setInterval(async () => {
        try {
          const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';
          const res = await fetch(`${API_BASE}/api/jobs/${batchId}`);
          const data = await res.json();
          setJobStatus(data);
          
          if (data.completed) {
            clearInterval(interval);
            setStatus({ type: 'success', message: `Pipeline Complete! Dispatched ${data.sent} / ${data.total} certificates. Failed: ${data.failed}` });
          }
        } catch (err) {
          console.error(err);
        }
      }, 2000);
    }
    return () => clearInterval(interval);
  }, [batchId]);

  const getProgress = () => {
    if (!jobStatus) return 0;
    return Math.round(((jobStatus.sent + jobStatus.failed) / jobStatus.total) * 100);
  };

  return (
    <div className="max-w-4xl mx-auto">
      <div className="mb-10 text-center">
        <h2 className="text-3xl font-extrabold text-gray-800 tracking-tight">Bulk Pipeline</h2>
        <p className="text-gray-500 font-medium mt-2">Process and distribute hundreds of certificates seamlessly in the background.</p>
      </div>

      {status.message && (
        <div className={`mb-8 p-5 rounded-2xl clay-panel text-center font-bold text-sm ${status.type === 'success' ? 'text-indigo-600' : 'text-red-500'}`}>
          {status.message}
        </div>
      )}

      <div className="clay-panel p-8 mb-10">
        <div className="flex justify-center space-x-6 mb-8">
          <button 
            onClick={() => setInputMethod('link')}
            className={`px-6 py-3 font-bold text-sm uppercase tracking-wider rounded-xl transition-all ${inputMethod === 'link' ? 'clay-btn active' : 'clay-btn'}`}
          >
            Sheets Link
          </button>
          <button 
            onClick={() => setInputMethod('file')}
            className={`px-6 py-3 font-bold text-sm uppercase tracking-wider rounded-xl transition-all ${inputMethod === 'file' ? 'clay-btn active' : 'clay-btn'}`}
          >
            Local File
          </button>
        </div>

        <div className="mb-8">
          {inputMethod === 'link' ? (
            <div>
              <label className="block text-xs font-bold text-gray-500 uppercase tracking-wider mb-3 ml-2">Google Sheets URL</label>
              <input
                type="text"
                placeholder="https://docs.google.com/spreadsheets/d/..."
                className="clay-input w-full px-5 py-3 text-gray-800 font-medium"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
              />
            </div>
          ) : (
            <div>
              <label className="block text-xs font-bold text-gray-500 uppercase tracking-wider mb-3 ml-2">Upload File (.CSV / .XLSX)</label>
              <input
                type="file"
                accept=".csv, .xlsx"
                className="clay-input w-full px-5 py-3 text-gray-800 font-medium file:mr-4 file:py-2 file:px-4 file:rounded-xl file:border-0 file:text-sm file:font-semibold file:bg-indigo-50 file:text-indigo-700 hover:file:bg-indigo-100"
                onChange={(e) => setFile(e.target.files[0])}
              />
            </div>
          )}
        </div>

        <div className="flex justify-center">
          <button
            onClick={handleParse}
            disabled={isParsing || batchId}
            className="clay-btn-primary px-10 py-3 font-bold text-sm uppercase tracking-widest disabled:opacity-50"
          >
            {isParsing ? 'Validating...' : 'Load Data Source'}
          </button>
        </div>
      </div>

      {records.length > 0 && (
        <div className="animate-fadeIn space-y-10">
          <div className="clay-panel overflow-hidden p-4">
            <div className="max-h-96 overflow-y-auto pr-2 custom-scrollbar">
              <table className="w-full text-left border-collapse">
                <thead className="sticky top-0 bg-white shadow-sm z-10">
                  <tr>
                    <th className="p-4 text-xs font-bold text-gray-500 uppercase tracking-wider border-b border-gray-400/20">Name</th>
                    <th className="p-4 text-xs font-bold text-gray-500 uppercase tracking-wider border-b border-gray-400/20">Email</th>
                    <th className="p-4 text-xs font-bold text-gray-500 uppercase tracking-wider border-b border-gray-400/20">Tier</th>
                  </tr>
                </thead>
                <tbody>
                  {records.map((row, idx) => (
                    <tr key={idx} className="hover:bg-gray-50 transition-colors">
                      <td className="p-4 text-sm font-bold text-gray-700">{row.Name}</td>
                      <td className="p-4 text-sm font-medium text-gray-500">{row.Email}</td>
                      <td className="p-4 text-sm font-medium text-gray-500">{row.Tier}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <div className="clay-panel p-8 text-center">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-8 mb-8 max-w-2xl mx-auto">
              <div>
                <label className="block text-xs font-bold text-gray-500 uppercase tracking-wider mb-3 ml-2 text-left">Global Event Name</label>
                <input
                  type="text"
                  className="clay-input w-full px-5 py-4 text-gray-800 font-bold text-center text-lg tracking-wide"
                  value={globalEvent}
                  onChange={(e) => setGlobalEvent(e.target.value)}
                  placeholder="TechXplore 2026"
                  disabled={batchId !== null}
                />
              </div>
              <div>
                <label className="block text-xs font-bold text-gray-500 uppercase tracking-wider mb-3 ml-2 text-left">Global Date</label>
                <input
                  type="text"
                  className="clay-input w-full px-5 py-4 text-gray-800 font-bold text-center text-lg tracking-wide placeholder-gray-400"
                  value={globalDate}
                  onChange={(e) => setGlobalDate(e.target.value)}
                  placeholder="Optional (e.g. Oct 15)"
                  disabled={batchId !== null}
                />
              </div>
            </div>

            <div className="max-w-md mx-auto mb-8">
              <label className="block text-xs font-bold text-gray-500 uppercase tracking-wider mb-3 ml-2 text-center">Global Cert Type</label>
              <input
                type="text"
                className="clay-input w-full px-5 py-3 text-gray-800 font-medium text-center"
                value={globalType}
                onChange={(e) => setGlobalType(e.target.value)}
                disabled={batchId !== null}
              />
            </div>

            {!batchId ? (
              <div className="flex flex-col sm:flex-row justify-center gap-4">
                <button
                  onClick={() => handleDispatch(true)}
                  className="clay-btn-primary px-8 py-4 font-bold text-sm uppercase tracking-widest"
                >
                  Generate & Email All
                </button>
                <button
                  onClick={() => handleDispatch(false)}
                  className="clay-btn px-8 py-4 font-bold text-sm uppercase tracking-widest"
                >
                  Download ZIP Only
                </button>
              </div>
            ) : (
              <div className="space-y-4 max-w-md mx-auto">
                <div className="flex justify-between items-center px-2">
                  <span className="text-sm font-bold text-gray-500 uppercase tracking-wider">Progress</span>
                  <span className="text-xl font-black text-indigo-600">{getProgress()}%</span>
                </div>
                <div className="w-full clay-input h-6 rounded-full overflow-hidden p-1 relative">
                  <div className="bg-indigo-500 h-full rounded-full transition-all duration-300 shadow-[inset_0_-2px_4px_rgba(0,0,0,0.2)]" style={{ width: `${getProgress()}%` }}></div>
                </div>
                <div className="flex justify-between text-xs font-bold uppercase text-gray-500 mt-2 px-2">
                  <span>Sent: {jobStatus?.sent || 0}</span>
                  <span>Pending: {jobStatus?.pending || records.length}</span>
                  <span className="text-red-400">Failed: {jobStatus?.failed || 0}</span>
                  {jobStatus?.cancelled > 0 && <span className="text-orange-400">Cancelled: {jobStatus.cancelled}</span>}
                </div>
                <div className="text-sm text-gray-500 font-medium mt-4 text-center">
                  Job ID: <span className="font-mono text-xs">{batchId}</span>
                </div>
                
                {!jobStatus?.completed && (
                  <div className="mt-4 flex justify-center">
                    <button 
                      onClick={handleCancel}
                      className="px-6 py-2 text-xs font-bold text-red-500 border-2 border-red-200 hover:bg-red-50 rounded-lg transition-colors uppercase tracking-widest"
                    >
                      Terminate Process
                    </button>
                  </div>
                )}

                {jobStatus?.completed && (
                  <div className="mt-6 flex justify-center animate-fadeIn">
                    <button 
                      onClick={() => {
                        const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';
                        window.open(`${API_BASE}/api/jobs/${batchId}/download`, '_blank');
                      }}
                      className="clay-btn bg-green-500 text-white font-bold py-3 px-8 text-sm uppercase tracking-wider"
                    >
                      Download All as ZIP
                    </button>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
