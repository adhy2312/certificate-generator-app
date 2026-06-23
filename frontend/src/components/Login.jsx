import React, { useState } from 'react';

export default function Login({ onLogin }) {
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';
    setError('');
    setIsLoading(true);

    try {
      const response = await fetch(`${API_BASE}/api/verify-password`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ password }),
      });

      if (response.ok) {
        const data = await response.json();
        if (data.success) {
          onLogin();
        }
      } else {
        setError('Access Denied: Incorrect gatekeeper token.');
      }
    } catch (err) {
      setError('Network error. Ensure backend is running.');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center clay-surface p-4">
      <div className="clay-card p-10 md:p-14 w-full max-w-md">
        <div className="text-center mb-10">
          <div className="inline-block p-5 clay-panel rounded-full mb-6">
            <span className="text-5xl">🎓</span>
          </div>
          <h2 className="text-3xl font-extrabold text-gray-800 tracking-tight mb-2">Secure Gateway</h2>
          <p className="text-gray-500 font-medium tracking-wide text-sm uppercase">ISTE_CERT.HUB Platform</p>
        </div>
        
        {error && (
          <div className="mb-8 p-4 clay-panel text-red-600 rounded-xl text-sm font-bold text-center border border-red-200/20">
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-8">
          <div>
            <label className="block text-xs font-bold text-gray-500 uppercase tracking-wider mb-3 ml-2">Access Token</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="clay-input w-full px-6 py-4 text-gray-800 placeholder-gray-400 font-mono tracking-widest text-center"
              placeholder="••••••••"
              required
            />
          </div>
          <button
            type="submit"
            disabled={isLoading}
            className="clay-btn-primary w-full py-4 px-6 font-bold text-lg uppercase tracking-widest disabled:opacity-70 flex justify-center items-center"
          >
            {isLoading ? (
              <span className="animate-pulse">Verifying...</span>
            ) : 'Authenticate'}
          </button>
        </form>
      </div>
    </div>
  );
}
