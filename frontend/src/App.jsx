import React, { useState } from 'react';
import Login from './components/Login';
import SingleGeneration from './components/SingleGeneration';
import BulkGeneration from './components/BulkGeneration';

function App() {
  // Persist auth across page refreshes using sessionStorage (cleared when browser tab closes)
  const [isAuthenticated, setIsAuthenticated] = useState(
    () => sessionStorage.getItem('iste_auth') === 'true'
  );
  const [activeTab, setActiveTab] = useState('single');

  const handleLogin = () => {
    sessionStorage.setItem('iste_auth', 'true');
    setIsAuthenticated(true);
  };

  const handleLogout = () => {
    sessionStorage.removeItem('iste_auth');
    setIsAuthenticated(false);
  };

  // Handle QR Code Verification Route natively by redirecting to backend HTML portal
  if (window.location.pathname.startsWith('/verify/')) {
    const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';
    window.location.href = `${API_BASE}${window.location.pathname}`;
    return (
      <div className="min-h-screen flex items-center justify-center bg-[#f4f4f0] font-sans">
        <p className="text-gray-600 font-bold text-lg animate-pulse">Redirecting to Secure Ledger...</p>
      </div>
    );
  }

  if (!isAuthenticated) {
    return <Login onLogin={handleLogin} />;
  }

  return (
    <div className="min-h-screen clay-surface text-gray-700 font-sans selection:bg-indigo-200">
      <header className="pt-8 pb-4">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex flex-col md:flex-row justify-between items-center gap-4">
          <h1 className="text-4xl font-extrabold text-gray-800 tracking-tight drop-shadow-sm">
            ISTE_CERT<span className="text-indigo-600">.HUB</span>
          </h1>
          <button 
            onClick={handleLogout}
            className="clay-btn px-6 py-2 text-sm font-bold uppercase tracking-wider"
          >
            Sign Out
          </button>
        </div>
      </header>

      <main className="max-w-5xl mx-auto px-4 py-8 sm:px-6 lg:px-8">
        <div className="flex justify-center mb-10">
          <nav className="flex space-x-4 p-3 clay-panel rounded-2xl">
            <button
              onClick={() => setActiveTab('single')}
              className={`px-8 py-3 font-bold text-sm uppercase tracking-wider rounded-xl transition-all ${
                activeTab === 'single' ? 'clay-btn active' : 'clay-btn'
              }`}
            >
              Single Generation
            </button>
            <button
              onClick={() => setActiveTab('bulk')}
              className={`px-8 py-3 font-bold text-sm uppercase tracking-wider rounded-xl transition-all ${
                activeTab === 'bulk' ? 'clay-btn active' : 'clay-btn'
              }`}
            >
              Bulk Pipeline
            </button>
          </nav>
        </div>

        <div className="clay-card p-8 md:p-14 transition-all duration-300">
          {activeTab === 'single' ? <SingleGeneration /> : <BulkGeneration />}
        </div>
      </main>
    </div>
  );
}

export default App;
