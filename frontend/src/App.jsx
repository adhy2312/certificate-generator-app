import React, { useState } from 'react';
import Login from './components/Login';
import SingleGeneration from './components/SingleGeneration';
import BulkGeneration from './components/BulkGeneration';
import StudentPortal from './components/StudentPortal';

function App() {
  // Persist auth across page refreshes using sessionStorage (cleared when browser tab closes)
  const [isAuthenticated, setIsAuthenticated] = useState(
    () => sessionStorage.getItem('iste_auth') === 'true'
  );
  const [publicView, setPublicView] = useState('student'); // 'student' | 'admin'
  const [adminTab, setAdminTab] = useState('bulk'); // 'single' | 'bulk' | 'student'

  const handleLogin = () => {
    sessionStorage.setItem('iste_auth', 'true');
    setIsAuthenticated(true);
  };

  const handleLogout = () => {
    sessionStorage.removeItem('iste_auth');
    setIsAuthenticated(false);
    setPublicView('student');
  };

  // -------------------------------------------------------------
  // Public View (Unauthenticated Visitors: Students & Organizers)
  // -------------------------------------------------------------
  if (!isAuthenticated) {
    return (
      <div className="min-h-screen flex flex-col clay-surface text-gray-700 font-sans selection:bg-indigo-200">
        <header className="pt-8 pb-4">
          <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex flex-col sm:flex-row justify-between items-center gap-4">
            <h1 className="text-3xl md:text-4xl font-extrabold text-gray-800 tracking-tight drop-shadow-sm cursor-pointer" onClick={() => setPublicView('student')}>
              ISTE_CERT<span className="text-indigo-600">.HUB</span>
            </h1>

            {/* Toggle between Student Portal and Admin Login */}
            <nav className="flex space-x-2 p-1.5 clay-panel rounded-xl">
              <button
                onClick={() => setPublicView('student')}
                className={`px-5 py-2 font-bold text-xs uppercase tracking-wider rounded-lg transition-all ${
                  publicView === 'student' ? 'clay-btn active' : 'clay-btn'
                }`}
              >
                🎓 Student Portal
              </button>
              <button
                onClick={() => setPublicView('admin')}
                className={`px-5 py-2 font-bold text-xs uppercase tracking-wider rounded-lg transition-all ${
                  publicView === 'admin' ? 'clay-btn active' : 'clay-btn'
                }`}
              >
                🔒 Admin Login
              </button>
            </nav>
          </div>
        </header>

        <main className="max-w-5xl mx-auto px-4 py-8 sm:px-6 lg:px-8 flex-grow w-full">
          {publicView === 'student' ? (
            <div className="clay-card p-8 md:p-14 transition-all duration-300">
              <StudentPortal />
            </div>
          ) : (
            <div className="max-w-md mx-auto">
              <Login onLogin={handleLogin} />
            </div>
          )}
        </main>

        <footer className="w-full text-center py-6 mt-auto">
          <p className="text-xs text-gray-500 font-medium tracking-wide opacity-80">© {new Date().getFullYear()} Developed by Adhy • ISTE Student Chapter</p>
        </footer>
      </div>
    );
  }

  // -------------------------------------------------------------
  // Authenticated Admin Dashboard
  // -------------------------------------------------------------
  return (
    <div className="min-h-screen flex flex-col clay-surface text-gray-700 font-sans selection:bg-indigo-200">
      <header className="pt-8 pb-4">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex flex-col md:flex-row justify-between items-center gap-4">
          <h1 className="text-4xl font-extrabold text-gray-800 tracking-tight drop-shadow-sm">
            ISTE_CERT<span className="text-indigo-600">.HUB</span>
          </h1>
          <div className="flex items-center gap-3">
            <span className="text-xs font-bold uppercase text-emerald-600 bg-emerald-50 px-3 py-1 rounded-full border border-emerald-200">
              ● Admin Active
            </span>
            <button 
              onClick={handleLogout}
              className="clay-btn px-6 py-2 text-sm font-bold uppercase tracking-wider"
            >
              Sign Out
            </button>
          </div>
        </div>
      </header>

      <main className="max-w-5xl mx-auto px-4 py-8 sm:px-6 lg:px-8 flex-grow w-full">
        <div className="flex justify-center mb-10">
          <nav className="flex flex-wrap justify-center gap-2 sm:gap-4 p-2 sm:p-3 clay-panel rounded-2xl">
            <button
              onClick={() => setAdminTab('bulk')}
              className={`px-6 sm:px-8 py-3 font-bold text-xs sm:text-sm uppercase tracking-wider rounded-xl transition-all ${
                adminTab === 'bulk' ? 'clay-btn active' : 'clay-btn'
              }`}
            >
              Bulk Pipeline
            </button>
            <button
              onClick={() => setAdminTab('single')}
              className={`px-6 sm:px-8 py-3 font-bold text-xs sm:text-sm uppercase tracking-wider rounded-xl transition-all ${
                adminTab === 'single' ? 'clay-btn active' : 'clay-btn'
              }`}
            >
              Single Generation
            </button>
            <button
              onClick={() => setAdminTab('student')}
              className={`px-6 sm:px-8 py-3 font-bold text-xs sm:text-sm uppercase tracking-wider rounded-xl transition-all ${
                adminTab === 'student' ? 'clay-btn active' : 'clay-btn'
              }`}
            >
              🎓 Student Portal
            </button>
          </nav>
        </div>

        <div className="clay-card p-8 md:p-14 transition-all duration-300">
          {adminTab === 'single' && <SingleGeneration />}
          {adminTab === 'bulk' && <BulkGeneration />}
          {adminTab === 'student' && <StudentPortal />}
        </div>
      </main>

      <footer className="w-full text-center py-6 mt-auto">
        <p className="text-xs text-gray-500 font-medium tracking-wide opacity-80">© {new Date().getFullYear()} Developed by Adhy • ISTE Student Chapter</p>
      </footer>
    </div>
  );
}

export default App;
