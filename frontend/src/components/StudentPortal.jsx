import React, { useState } from 'react';

const API_BASE = import.meta.env.VITE_API_BASE_URL || '';

function StudentPortal() {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleSearch = async (e) => {
    if (e) e.preventDefault();
    const cleanQ = query.trim();
    if (!cleanQ) {
      setError('Please enter your email or name to search.');
      return;
    }
    if (cleanQ.length < 3) {
      setError('Please enter at least 3 characters.');
      return;
    }

    setError('');
    setLoading(true);
    setResults(null);

    try {
      const resp = await fetch(`${API_BASE}/api/certificates/search?query=${encodeURIComponent(cleanQ)}`);
      if (!resp.ok) {
        const errData = await resp.json().catch(() => ({}));
        throw new Error(errData.detail || 'Failed to search certificates.');
      }
      const data = await resp.json();
      setResults(data);
    } catch (err) {
      setError(err.message || 'Error communicating with server.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-8 animate-fadeIn">
      {/* Header */}
      <div className="text-center space-y-2">
        <h2 className="text-2xl md:text-3xl font-extrabold text-gray-800 tracking-tight">
          Student Certificate Portal
        </h2>
        <p className="text-sm text-gray-500 max-w-xl mx-auto">
          Search and download your official ISTE event certificate directly using your registered email address, name, or Certificate ID.
        </p>
      </div>

      {/* Search Input Bar */}
      <form onSubmit={handleSearch} className="max-w-2xl mx-auto flex flex-col sm:flex-row gap-3">
        <div className="relative flex-grow">
          <input
            type="text"
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              if (error) setError('');
            }}
            placeholder="Enter your email (e.g. student@mbcet.ac.in) or name..."
            className="w-full px-5 py-3.5 clay-input rounded-xl text-gray-700 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-indigo-400 text-sm font-medium"
          />
          {query && (
            <button
              type="button"
              onClick={() => { setQuery(''); setResults(null); }}
              className="absolute right-3.5 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600 text-sm font-bold"
            >
              ✕
            </button>
          )}
        </div>
        <button
          type="submit"
          disabled={loading}
          className="clay-btn-primary px-8 py-3.5 font-bold text-sm uppercase tracking-wider disabled:opacity-60 whitespace-nowrap"
        >
          {loading ? 'Searching...' : 'Search'}
        </button>
      </form>

      {/* Error alert */}
      {error && (
        <div className="max-w-2xl mx-auto p-4 bg-red-50 border border-red-200 text-red-700 rounded-xl text-xs font-semibold text-center">
          {error}
        </div>
      )}

      {/* Results Section */}
      {results !== null && (
        <div className="max-w-3xl mx-auto space-y-4">
          <div className="flex justify-between items-center px-1">
            <span className="text-xs font-bold uppercase tracking-wider text-gray-500">
              Found {results.length} Certificate{results.length === 1 ? '' : 's'}
            </span>
          </div>

          {results.length === 0 ? (
            <div className="p-8 bg-gray-50/80 border border-gray-200 rounded-2xl text-center space-y-2">
              <div className="text-3xl">🔍</div>
              <h4 className="text-sm font-bold text-gray-700">No Certificates Found</h4>
              <p className="text-xs text-gray-500 max-w-md mx-auto">
                No certificate record was found matching "<span className="font-semibold text-gray-700">{query}</span>". 
                Please make sure you typed the exact email address used during event registration.
              </p>
            </div>
          ) : (
            <div className="grid gap-4">
              {results.map((cert) => (
                <div
                  key={cert.cert_id}
                  className="p-5 bg-white border border-gray-100 rounded-2xl shadow-sm hover:shadow-md transition-all flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4"
                >
                  <div className="space-y-1">
                    <div className="flex items-center gap-2">
                      <span className="px-2.5 py-0.5 rounded-full bg-indigo-50 text-indigo-700 text-[11px] font-bold uppercase tracking-wide">
                        {cert.cert_type}
                      </span>
                      {cert.tier && (
                        <span className="px-2 py-0.5 rounded-full bg-gray-100 text-gray-600 text-[10px] font-semibold">
                          {cert.tier}
                        </span>
                      )}
                    </div>
                    <h3 className="text-base font-bold text-gray-800">{cert.name}</h3>
                    <p className="text-xs text-gray-500 font-medium">
                      Event: <span className="text-gray-700 font-semibold">{cert.event}</span> • Date: <span className="text-gray-700">{cert.date || 'Official'}</span>
                    </p>
                    <p className="text-[11px] font-mono text-gray-400">
                      ID: {cert.cert_id}
                    </p>
                  </div>

                  <a
                    href={`${API_BASE}${cert.download_url}`}
                    target="_blank"
                    rel="noreferrer"
                    download
                    className="clay-btn bg-emerald-600 text-white hover:bg-emerald-700 px-5 py-2.5 rounded-xl font-bold text-xs uppercase tracking-wider flex items-center gap-2 whitespace-nowrap shadow-sm"
                  >
                    <span>Download PDF</span>
                    <span>↓</span>
                  </a>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default StudentPortal;
