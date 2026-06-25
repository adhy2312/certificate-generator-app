import React, { useState } from 'react';

export default function SingleGeneration() {
  const [formData, setFormData] = useState({ name: '', email: '', event: '', tier: 'Participant', date: '', cert_type: 'CERT_Template', prize: '1st Prize', send_email: true });
  const [status, setStatus] = useState({ type: '', message: '' });
  const [isLoading, setIsLoading] = useState(false);

  const handleSubmit = async (e, sendEmailOverride) => {
    e.preventDefault();
    setIsLoading(true);
    // Update local state to reflect the loading text correctly
    setFormData(prev => ({ ...prev, send_email: sendEmailOverride }));
    
    const payload = { ...formData, send_email: sendEmailOverride };
    if (payload.cert_type === 'Certificate of Merit') {
      payload.cert_type = `Certificate of Merit - ${payload.prize}`;
    }
    const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';
    setStatus({ type: '', message: '' });

    try {
      let response;
      if (sendEmailOverride) {
        response = await fetch(`${API_BASE}/api/jobs/single`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        });
        const data = await response.json();
        if (response.ok && data.success) {
          setStatus({ type: 'success', message: `Certificate dispatched to ${payload.email}!` });
          setFormData({ name: '', email: '', event: '', tier: 'Participant', date: '', cert_type: 'CERT_Template', prize: '1st Prize', send_email: true });
        } else {
          setStatus({ type: 'error', message: data.detail || 'Failed to process request.' });
        }
      } else {
        response = await fetch(`${API_BASE}/api/jobs/single`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        });
        
        if (response.ok) {
          const blob = await response.blob();
          const url = window.URL.createObjectURL(blob);
          const a = document.createElement('a');
          a.href = url;
          a.download = `${payload.name}_certificate.pdf`;
          document.body.appendChild(a);
          a.click();
          a.remove();
          window.URL.revokeObjectURL(url);
          setStatus({ type: 'success', message: `Certificate downloaded successfully!` });
        } else {
          const data = await response.json();
          setStatus({ type: 'error', message: data.detail || 'Failed to download certificate.' });
        }
      }
    } catch (err) {
      setStatus({ type: 'error', message: 'Network error. Please try again.' });
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="max-w-2xl mx-auto">
      <div className="mb-10 text-center">
        <h2 className="text-3xl font-extrabold text-gray-800 tracking-tight">Single Dispatch</h2>
        <p className="text-gray-500 font-medium mt-2">Generate and email an individual certificate instantly.</p>
      </div>

      {status.message && (
        <div className={`mb-8 p-5 rounded-2xl clay-panel text-center font-bold text-sm ${status.type === 'success' ? 'text-indigo-600' : 'text-red-500'}`}>
          {status.message}
        </div>
      )}

      <form onSubmit={handleSubmit} className="space-y-8">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
          <div>
            <label className="block text-xs font-bold text-gray-500 uppercase tracking-wider mb-3 ml-2">Full Name</label>
            <input
              type="text"
              required
              className="clay-input w-full px-5 py-3 text-gray-800 font-medium"
              value={formData.name}
              onChange={(e) => setFormData({ ...formData, name: e.target.value })}
            />
          </div>
          <div>
            <label className="block text-xs font-bold text-gray-500 uppercase tracking-wider mb-3 ml-2">Email Address</label>
            <input
              type="email"
              required
              className="clay-input w-full px-5 py-3 text-gray-800 font-medium"
              value={formData.email}
              onChange={(e) => setFormData({ ...formData, email: e.target.value })}
            />
          </div>
        </div>
        
        <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
          <div>
            <label className="block text-xs font-bold text-gray-500 uppercase tracking-wider mb-3 ml-2">Event Name</label>
            <input
              type="text"
              required
              className="clay-input w-full px-5 py-3 text-gray-800 font-medium"
              value={formData.event}
              onChange={(e) => setFormData({ ...formData, event: e.target.value })}
            />
          </div>
          <div>
            <label className="block text-xs font-bold text-gray-500 uppercase tracking-wider mb-3 ml-2">Certificate Date</label>
            <input
              type="text"
              placeholder="e.g. October 15, 2026 (Optional)"
              className="clay-input w-full px-5 py-3 text-gray-800 font-medium placeholder-gray-400"
              value={formData.date}
              onChange={(e) => setFormData({ ...formData, date: e.target.value })}
            />
          </div>
        </div>

        <div className="max-w-md mx-auto">
          <label className="block text-xs font-bold text-gray-500 uppercase tracking-wider mb-3 ml-2 text-center">Role / Tier</label>
          <select
            className="clay-input w-full px-5 py-3 text-gray-800 font-medium cursor-pointer text-center"
            value={formData.tier}
            onChange={(e) => setFormData({ ...formData, tier: e.target.value })}
          >
            <option>Participant</option>
            <option>Winner</option>
            <option>Resource Person</option>
          </select>
        </div>

        <div className="max-w-md mx-auto relative group">
          <label className="block text-xs font-bold text-gray-500 uppercase tracking-wider mb-3 ml-2 text-center transition-colors group-hover:text-indigo-500">Certificate Type</label>
          <div className="relative">
            <div className="absolute -inset-0.5 bg-gradient-to-r from-indigo-500 via-purple-500 to-pink-500 rounded-xl blur opacity-30 group-hover:opacity-70 transition duration-500"></div>
            <div className="relative bg-white rounded-xl flex items-center">
              <select
                className="w-full bg-transparent text-gray-800 font-bold text-center appearance-none px-5 py-4 outline-none cursor-pointer rounded-xl z-10"
                value={formData.cert_type}
                onChange={(e) => setFormData({ ...formData, cert_type: e.target.value })}
              >
                <option value="CERT_Template">Certificate of Participation</option>
                <option value="Certificate of Merit">Certificate of Merit</option>
                <option value="Certificate of Appreciation">Certificate of Appreciation</option>
                <option value="Certificate of Volunteering">Certificate of Volunteering</option>
                <option value="Certificate of Recognition">Certificate of Recognition</option>
              </select>
              <div className="absolute inset-y-0 right-0 flex items-center pr-5 pointer-events-none text-indigo-500 group-hover:text-pink-500 transition-colors">
                <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 9l-7 7-7-7"></path></svg>
              </div>
            </div>
          </div>
        </div>

        {formData.cert_type === 'Certificate of Merit' && (
          <div className="max-w-md mx-auto relative group">
            <label className="block text-xs font-bold text-gray-500 uppercase tracking-wider mb-3 ml-2 text-center transition-colors group-hover:text-indigo-500">Prize Category</label>
            <div className="relative">
              <div className="absolute -inset-0.5 bg-gradient-to-r from-indigo-500 via-purple-500 to-pink-500 rounded-xl blur opacity-30 group-hover:opacity-70 transition duration-500"></div>
              <div className="relative bg-white rounded-xl flex items-center">
                <select
                  className="w-full bg-transparent text-gray-800 font-bold text-center appearance-none px-5 py-4 outline-none cursor-pointer rounded-xl z-10"
                  value={formData.prize}
                  onChange={(e) => setFormData({ ...formData, prize: e.target.value })}
                >
                  <option value="1st Prize">1st Prize</option>
                  <option value="2nd Prize">2nd Prize</option>
                  <option value="3rd Prize">3rd Prize</option>
                </select>
                <div className="absolute inset-y-0 right-0 flex items-center pr-5 pointer-events-none text-indigo-500 group-hover:text-pink-500 transition-colors">
                  <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 9l-7 7-7-7"></path></svg>
                </div>
              </div>
            </div>
          </div>
        )}

        <div className="pt-8 flex flex-col sm:flex-row justify-center gap-4">
          <button
            type="button"
            onClick={(e) => handleSubmit(e, true)}
            disabled={isLoading}
            className="clay-btn-primary px-8 py-4 font-bold text-sm uppercase tracking-widest disabled:opacity-50"
          >
            {isLoading && formData.send_email ? 'Processing...' : 'Generate & Email'}
          </button>
          
          <button
            type="button"
            onClick={(e) => handleSubmit(e, false)}
            disabled={isLoading}
            className="clay-btn px-8 py-4 font-bold text-sm uppercase tracking-widest disabled:opacity-50"
          >
            {isLoading && !formData.send_email ? 'Generating...' : 'Download PDF Only'}
          </button>
        </div>
      </form>
    </div>
  );
}
