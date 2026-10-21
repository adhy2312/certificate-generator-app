import React, { useState, useEffect, useMemo } from 'react';
import { safeFetchJson, getApiBaseUrl } from '../api';

export default function BulkGeneration() {
  const [inputMethod, setInputMethod] = useState('link');
  const [url, setUrl] = useState('');
  const [file, setFile] = useState(null);
  const [globalEvent, setGlobalEvent] = useState('');
  const [globalDate, setGlobalDate] = useState('');
  const [globalType, setGlobalType] = useState('Certificate of Participation');
  const [sendEmail, setSendEmail] = useState(true);
  
  const [records, setRecords] = useState([]);
  const [searchTerm, setSearchTerm] = useState('');
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useState(25);
  
  const [status, setStatus] = useState({ type: '', message: '' });
  const [isParsing, setIsParsing] = useState(false);
  const [isRetrying, setIsRetrying] = useState(false);
  const [batchId, setBatchId] = useState(null);
  const [jobStatus, setJobStatus] = useState(null);
  const [showFailedList, setShowFailedList] = useState(true);
  const [copiedNotice, setCopiedNotice] = useState(false);

  const handleCopyFailedEmails = () => {
    if (!jobStatus?.failed_students || jobStatus.failed_students.length === 0) return;
    const emailList = jobStatus.failed_students.map(s => s.email).filter(Boolean).join(', ');
    navigator.clipboard.writeText(emailList);
    setCopiedNotice(true);
    setTimeout(() => setCopiedNotice(false), 3000);
  };

  const handleParse = async () => {
    setIsParsing(true);
    setStatus({ type: '', message: '' });
    setBatchId(null);
    setJobStatus(null);
    
    const formData = new FormData();
    if (inputMethod === 'link') {
      if (!url.trim()) {
        setStatus({ type: 'error', message: 'Please provide a Google Sheets link.' });
        setIsParsing(false);
        return;
      }
      formData.append('url', url.trim());
    } else {
      if (!file) {
        setStatus({ type: 'error', message: 'Please upload a CSV or XLSX file.' });
        setIsParsing(false);
        return;
      }
      formData.append('file', file);
    }

    try {
      const data = await safeFetchJson('/api/parse-preview', {
        method: 'POST',
        body: formData,
      });
      
      if (data && data.full_records) {
        setRecords(data.full_records);
        setCurrentPage(1);
        setStatus({ type: 'success', message: `Loaded ${data.full_records.length} records successfully. Ready for batch execution.` });
      } else {
        setStatus({ type: 'error', message: data?.detail || 'Parsing failed.' });
      }
    } catch (err) {
      setStatus({ type: 'error', message: err.message || 'Failed to parse data source.' });
    } finally {
      setIsParsing(false);
    }
  };

  const handleDispatch = async (sendEmailOverride) => {
    if (!globalEvent.trim()) {
      setStatus({ type: 'error', message: 'Please provide a Global Event Name.' });
      return;
    }
    if (records.length === 0) {
      setStatus({ type: 'error', message: 'Please load a valid data source first.' });
      return;
    }
    
    setStatus({ type: '', message: '' });
    setSendEmail(sendEmailOverride);
    
    try {
      const data = await safeFetchJson('/api/jobs/bulk', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          records: records.map(r => ({ Name: r.Name, Email: r.Email, Tier: r.Tier, Type: r.Type })),
          event: globalEvent.trim(),
          date: globalDate.trim(),
          cert_type: globalType,
          send_email: sendEmailOverride
        }),
      });
      if (data && data.batch_id) {
        setBatchId(data.batch_id);
        setStatus({ type: 'success', message: `Batch queued: Processing ${data.total} certificates in background.` });
      } else {
        setStatus({ type: 'error', message: data?.detail || 'Dispatch failed' });
      }
    } catch (err) {
      setStatus({ type: 'error', message: err.message || 'Dispatch request failed.' });
    }
  };

  const handleCancel = async () => {
    const password = prompt('Enter admin password to cancel this job:');
    if (!password) return;
    try {
      const data = await safeFetchJson(`/api/jobs/${batchId}/cancel`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ password }),
      });
      setStatus({ type: 'error', message: data?.message || 'Process terminated mid-way.' });
    } catch (err) {
      setStatus({ type: 'error', message: err.message || 'Failed to cancel job.' });
    }
  };

  const handleRetryFailed = async () => {
    if (!batchId) return;
    setIsRetrying(true);
    setStatus({ type: '', message: '' });
    try {
      const data = await safeFetchJson(`/api/jobs/${batchId}/retry`, {
        method: 'POST',
      });
      if (data && data.success) {
        setStatus({ type: 'success', message: data.message || `Retrying failed certificates...` });
      } else {
        setStatus({ type: 'error', message: data?.message || 'Retry failed.' });
      }
    } catch (err) {
      setStatus({ type: 'error', message: err.message || 'Failed to trigger retry.' });
    } finally {
      setIsRetrying(false);
    }
  };

  // Status Poller with graceful retry
  useEffect(() => {
    let interval;
    if (batchId) {
      interval = setInterval(async () => {
        try {
          const data = await safeFetchJson(`/api/jobs/${batchId}`);
          if (data && typeof data === 'object' && 'total' in data) {
            setJobStatus(data);
            
            if (data.completed) {
              clearInterval(interval);
              const summaryMsg = data.failed > 0
                ? `Pipeline Complete! Successful: ${data.sent + data.generated} / ${data.total}. Failed: ${data.failed}`
                : `Pipeline Complete! All ${data.total} certificates processed successfully!`;
              setStatus({ type: data.failed > 0 ? 'error' : 'success', message: summaryMsg });
            }
          }
        } catch (err) {
          console.warn('Status poller transient error:', err.message || err);
        }
      }, 3500);
    }
    return () => clearInterval(interval);
  }, [batchId]);

  useEffect(() => {
    const handleBeforeUnload = (e) => {
      if (batchId && !jobStatus?.completed) {
        e.preventDefault();
        e.returnValue = '';
      }
    };
    window.addEventListener('beforeunload', handleBeforeUnload);
    return () => window.removeEventListener('beforeunload', handleBeforeUnload);
  }, [batchId, jobStatus]);

  // Client-side pagination & search for high responsiveness with 1,000+ records
  const filteredRecords = useMemo(() => {
    if (!searchTerm.trim()) return records;
    const term = searchTerm.toLowerCase();
    return records.filter(r => 
      (r.Name && r.Name.toLowerCase().includes(term)) ||
      (r.Email && r.Email.toLowerCase().includes(term)) ||
      (r.Tier && r.Tier.toLowerCase().includes(term))
    );
  }, [records, searchTerm]);

  const totalPages = Math.ceil(filteredRecords.length / pageSize) || 1;
  const paginatedRecords = useMemo(() => {
    const start = (currentPage - 1) * pageSize;
    return filteredRecords.slice(start, start + pageSize);
  }, [filteredRecords, currentPage, pageSize]);

  const getProgress = () => {
    if (!jobStatus || !jobStatus.total) return 0;
    const done = (jobStatus.sent || 0) + (jobStatus.generated || 0) + (jobStatus.failed || 0) + (jobStatus.cancelled || 0);
    return Math.min(100, Math.round((done / jobStatus.total) * 100));
  };

  return (
    <div className="max-w-4xl mx-auto">
      <div className="mb-10 text-center">
        <h2 className="text-3xl font-extrabold text-gray-800 tracking-tight">Bulk Pipeline</h2>
        <p className="text-gray-500 font-medium mt-2">Generate, package, and dispatch 1,000+ certificates seamlessly with zero lag.</p>
      </div>

      {status.message && (
        <div className={`mb-8 p-5 rounded-2xl clay-panel text-center font-bold text-sm ${status.type === 'success' ? 'text-indigo-600' : 'text-red-500'}`}>
          {status.message}
        </div>
      )}

      {/* Input Source Panel */}
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
                disabled={batchId !== null && !jobStatus?.completed}
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
                disabled={batchId !== null && !jobStatus?.completed}
              />
            </div>
          )}
        </div>

        <div className="flex justify-center">
          <button
            onClick={handleParse}
            disabled={isParsing || (batchId !== null && !jobStatus?.completed)}
            className="clay-btn-primary px-10 py-3 font-bold text-sm uppercase tracking-widest disabled:opacity-50"
          >
            {isParsing ? 'Validating...' : 'Load Data Source'}
          </button>
        </div>
      </div>

      {records.length > 0 && (
        <div className="animate-fadeIn space-y-10">
          {/* Paginated Data Preview Panel */}
          <div className="clay-panel p-6">
            <div className="flex flex-col sm:flex-row justify-between items-center gap-4 mb-4">
              <div className="flex items-center gap-3 w-full sm:w-auto">
                <span className="text-xs font-bold text-gray-500 uppercase tracking-wider">
                  Records: <span className="text-indigo-600 font-black">{records.length}</span>
                </span>
                <select
                  value={pageSize}
                  onChange={(e) => { setPageSize(Number(e.target.value)); setCurrentPage(1); }}
                  className="clay-input px-3 py-1.5 text-xs font-bold text-gray-700 rounded-lg outline-none cursor-pointer"
                >
                  <option value={25}>25 / page</option>
                  <option value={50}>50 / page</option>
                  <option value={100}>100 / page</option>
                </select>
              </div>

              <div className="w-full sm:w-72">
                <input
                  type="text"
                  placeholder="Filter by name, email..."
                  value={searchTerm}
                  onChange={(e) => { setSearchTerm(e.target.value); setCurrentPage(1); }}
                  className="clay-input w-full px-4 py-2 text-xs font-medium placeholder-gray-400"
                />
              </div>
            </div>

            <div className="max-h-80 overflow-y-auto pr-2 custom-scrollbar border border-gray-100 rounded-xl">
              <table className="w-full text-left border-collapse">
                <thead className="sticky top-0 bg-white shadow-sm z-10">
                  <tr>
                    <th className="p-3 text-xs font-bold text-gray-500 uppercase tracking-wider border-b border-gray-400/20">Name</th>
                    <th className="p-3 text-xs font-bold text-gray-500 uppercase tracking-wider border-b border-gray-400/20">Email</th>
                    <th className="p-3 text-xs font-bold text-gray-500 uppercase tracking-wider border-b border-gray-400/20">Tier</th>
                  </tr>
                </thead>
                <tbody>
                  {paginatedRecords.map((row, idx) => (
                    <tr key={idx} className="hover:bg-gray-50 transition-colors border-b border-gray-100">
                      <td className="p-3 text-sm font-bold text-gray-700">{row.Name}</td>
                      <td className="p-3 text-sm font-medium text-gray-500">{row.Email}</td>
                      <td className="p-3 text-sm font-medium text-gray-500">{row.Tier}</td>
                    </tr>
                  ))}
                  {paginatedRecords.length === 0 && (
                    <tr>
                      <td colSpan={3} className="p-6 text-center text-sm font-medium text-gray-400">
                        No matching records found.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>

            {/* Pagination Controls */}
            {totalPages > 1 && (
              <div className="flex justify-between items-center mt-4 px-2">
                <button
                  onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
                  disabled={currentPage === 1}
                  className="clay-btn px-4 py-1.5 text-xs font-bold uppercase tracking-wider disabled:opacity-40"
                >
                  Previous
                </button>
                <span className="text-xs font-bold text-gray-500">
                  Page {currentPage} of {totalPages}
                </span>
                <button
                  onClick={() => setCurrentPage(p => Math.min(totalPages, p + 1))}
                  disabled={currentPage === totalPages}
                  className="clay-btn px-4 py-1.5 text-xs font-bold uppercase tracking-wider disabled:opacity-40"
                >
                  Next
                </button>
              </div>
            )}
          </div>

          {/* Certificate Parameters & Dispatch Panel */}
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
                  disabled={batchId !== null && !jobStatus?.completed}
                />
              </div>
              <div>
                <label className="block text-xs font-bold text-gray-500 uppercase tracking-wider mb-3 ml-2 text-left">Global Date</label>
                <input
                  type="text"
                  className="clay-input w-full px-5 py-4 text-gray-800 font-bold text-center text-lg tracking-wide placeholder-gray-400"
                  value={globalDate}
                  onChange={(e) => setGlobalDate(e.target.value)}
                  placeholder="Optional (e.g. Oct 21, 2026)"
                  disabled={batchId !== null && !jobStatus?.completed}
                />
              </div>
            </div>

            <div className="max-w-md mx-auto mb-8 relative group">
              <label className="block text-xs font-bold text-gray-500 uppercase tracking-wider mb-3 ml-2 text-center transition-colors group-hover:text-indigo-500">Global Cert Type</label>
              <div className="relative">
                <div className="absolute -inset-0.5 bg-gradient-to-r from-indigo-500 via-purple-500 to-pink-500 rounded-xl blur opacity-30 group-hover:opacity-70 transition duration-500"></div>
                <div className="relative bg-white rounded-xl flex items-center">
                  <select
                    className="w-full bg-transparent text-gray-800 font-bold text-center appearance-none px-5 py-4 outline-none cursor-pointer rounded-xl z-10 disabled:opacity-50"
                    value={globalType}
                    onChange={(e) => setGlobalType(e.target.value)}
                    disabled={batchId !== null && !jobStatus?.completed}
                  >
                    <option value="Certificate of Participation">Certificate of Participation</option>
                    <option value="Certificate of Merit - 1st Prize">Certificate of Merit – 1st Prize</option>
                    <option value="Certificate of Merit - 2nd Prize">Certificate of Merit – 2nd Prize</option>
                    <option value="Certificate of Merit - 3rd Prize">Certificate of Merit – 3rd Prize</option>
                    <option value="Certificate of Appreciation">Certificate of Appreciation</option>
                    <option value="Certificate of Recognition">Certificate of Recognition</option>
                    <option value="Certificate of Volunteering">Certificate of Volunteering</option>
                  </select>
                  <div className="absolute inset-y-0 right-0 flex items-center pr-5 pointer-events-none text-indigo-500 group-hover:text-pink-500 transition-colors">
                    <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 9l-7 7-7-7"></path></svg>
                  </div>
                </div>
              </div>
            </div>

            {!batchId ? (
              <div className="flex flex-col sm:flex-row justify-center gap-4">
                <button
                  onClick={() => handleDispatch(true)}
                  className="clay-btn-primary px-8 py-4 font-bold text-sm uppercase tracking-widest"
                >
                  Generate & Email All ({records.length})
                </button>
                <button
                  onClick={() => handleDispatch(false)}
                  className="clay-btn px-8 py-4 font-bold text-sm uppercase tracking-widest"
                >
                  Download ZIP Only ({records.length})
                </button>
              </div>
            ) : (
              <div className="space-y-4 max-w-lg mx-auto">
                <div className="flex justify-between items-center px-2">
                  <span className="text-sm font-bold text-gray-500 uppercase tracking-wider">
                    {jobStatus?.completed ? 'Completed' : 'Processing Batch...'}
                  </span>
                  <span className="text-2xl font-black text-indigo-600">{getProgress()}%</span>
                </div>

                <div className="w-full clay-input h-6 rounded-full overflow-hidden p-1 relative">
                  <div 
                    className="bg-indigo-500 h-full rounded-full transition-all duration-300 shadow-[inset_0_-2px_4px_rgba(0,0,0,0.2)]" 
                    style={{ width: `${getProgress()}%` }}
                  ></div>
                </div>

                {/* Metrics Breakdown */}
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs font-bold uppercase text-gray-500 mt-3 p-3 bg-gray-50/80 rounded-xl">
                  {jobStatus?.sent > 0 && <div className="text-green-600">Sent: {jobStatus.sent}</div>}
                  {jobStatus?.generated > 0 && <div className="text-indigo-600">Generated: {jobStatus.generated}</div>}
                  <div className="text-gray-500">Pending: {jobStatus?.pending || 0}</div>
                  <div className={jobStatus?.failed > 0 ? "text-red-500" : "text-gray-400"}>Failed: {jobStatus?.failed || 0}</div>
                  {jobStatus?.cancelled > 0 && <div className="text-orange-500">Cancelled: {jobStatus.cancelled}</div>}
                </div>

                {/* Failed Students Heads-Up & Recovery Hub */}
                {jobStatus?.failed > 0 && (
                  <div className="p-5 bg-red-50/90 border-2 border-red-200 rounded-2xl text-left space-y-4 shadow-sm animate-fadeIn">
                    <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-3">
                      <div>
                        <div className="text-sm font-extrabold text-red-700 uppercase tracking-wider flex items-center gap-2">
                          <span>⚠️ Heads-Up:</span>
                          <span>{jobStatus.failed} student(s) did not receive certificates</span>
                        </div>
                        <p className="text-xs text-red-600 mt-0.5">
                          Review the affected students below. You can retry dispatch or export the list.
                        </p>
                      </div>

                      <div className="flex flex-wrap items-center gap-2 w-full sm:w-auto">
                        <button
                          onClick={handleRetryFailed}
                          disabled={isRetrying}
                          className="clay-btn bg-indigo-600 text-white px-3.5 py-1.5 text-xs font-bold uppercase tracking-wider hover:bg-indigo-700 disabled:opacity-50"
                        >
                          {isRetrying ? 'Retrying...' : `Retry Failed (${jobStatus.failed})`}
                        </button>
                        <button
                          onClick={() => {
                            const API_BASE = getApiBaseUrl();
                            window.open(`${API_BASE}/api/jobs/${batchId}/failed/csv`, '_blank');
                          }}
                          className="clay-btn bg-white text-gray-700 border border-gray-300 px-3 py-1.5 text-xs font-bold uppercase tracking-wider hover:bg-gray-50"
                          title="Export list of failed students to CSV"
                        >
                          Export CSV
                        </button>
                        <button
                          onClick={handleCopyFailedEmails}
                          className="clay-btn bg-white text-gray-700 border border-gray-300 px-3 py-1.5 text-xs font-bold uppercase tracking-wider hover:bg-gray-50"
                          title="Copy all failed student email addresses to clipboard"
                        >
                          {copiedNotice ? '✓ Copied!' : 'Copy Emails'}
                        </button>
                        <button
                          onClick={() => setShowFailedList(!showFailedList)}
                          className="text-xs font-bold text-red-600 hover:text-red-800 underline ml-1"
                        >
                          {showFailedList ? 'Hide List' : 'Show List'}
                        </button>
                      </div>
                    </div>

                    {/* Detailed List of Affected Students */}
                    {showFailedList && jobStatus?.failed_students && jobStatus.failed_students.length > 0 && (
                      <div className="mt-3 max-h-60 overflow-y-auto pr-1 custom-scrollbar border border-red-200/60 rounded-xl bg-white shadow-inner">
                        <table className="w-full text-left border-collapse text-xs">
                          <thead className="sticky top-0 bg-red-100/90 backdrop-blur z-10 border-b border-red-200">
                            <tr>
                              <th className="p-2.5 font-bold text-red-900 uppercase">Student Name</th>
                              <th className="p-2.5 font-bold text-red-900 uppercase">Email</th>
                              <th className="p-2.5 font-bold text-red-900 uppercase">Issue Reason</th>
                            </tr>
                          </thead>
                          <tbody>
                            {jobStatus.failed_students.map((st, i) => (
                              <tr key={i} className="border-b border-gray-100 hover:bg-red-50/50">
                                <td className="p-2.5 font-bold text-gray-800 whitespace-nowrap">{st.name}</td>
                                <td className="p-2.5 font-mono text-gray-600 select-all">{st.email}</td>
                                <td className="p-2.5 text-red-600 font-medium break-words">
                                  <span className="inline-block px-2 py-0.5 rounded bg-red-100 text-red-700 text-[11px] font-semibold">
                                    {st.reason}
                                  </span>
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )}
                  </div>
                )}

                <div className="text-xs text-gray-400 font-medium mt-4">
                  Job ID: <span className="font-mono text-gray-600">{batchId}</span>
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
                  <div className="mt-6 flex flex-col sm:flex-row justify-center gap-3 animate-fadeIn">
                    <button 
                      onClick={() => {
                        const API_BASE = getApiBaseUrl();
                        window.open(`${API_BASE}/api/jobs/${batchId}/download`, '_blank');
                      }}
                      className="clay-btn bg-green-500 text-white font-bold py-3.5 px-8 text-sm uppercase tracking-wider shadow-md hover:bg-green-600"
                    >
                      Download All as ZIP
                    </button>
                    <button
                      onClick={() => {
                        setBatchId(null);
                        setJobStatus(null);
                        setStatus({ type: '', message: '' });
                      }}
                      className="clay-btn px-6 py-3.5 text-xs font-bold uppercase tracking-wider text-gray-600"
                    >
                      Start New Batch
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
