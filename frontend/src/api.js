/**
 * Centralized API utility for ISTE CertHub frontend.
 * Provides resilient URL discovery, unified request handling,
 * safe JSON/error parsing, and friendly cold-start messaging.
 */

export function getApiBaseUrl() {
  const envUrl = import.meta.env.VITE_API_URL;
  if (envUrl && typeof envUrl === 'string' && envUrl.trim() !== '') {
    return envUrl.trim().replace(/\/+$/, '');
  }

  // Fallback based on runtime hostname
  if (typeof window !== 'undefined') {
    const hostname = window.location.hostname;
    if (hostname === 'localhost' || hostname === '127.0.0.1') {
      return 'http://localhost:8000';
    }
  }

  // Production Render instance fallback
  return 'https://certificate-generator-app-v2.onrender.com';
}

/**
 * Executes a fetch request and safely handles JSON, HTML error bodies,
 * HTTP status errors (401, 429, 502, etc.), and network interruptions.
 */
export async function safeFetchJson(endpoint, options = {}) {
  const baseUrl = getApiBaseUrl();
  const fullUrl = endpoint.startsWith('http') ? endpoint : `${baseUrl}${endpoint.startsWith('/') ? '' : '/'}${endpoint}`;

  let response;
  try {
    response = await fetch(fullUrl, options);
  } catch (netErr) {
    const isLocal = typeof window !== 'undefined' && (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1');
    if (isLocal) {
      throw new Error(`Cannot connect to local backend (${baseUrl}). Please ensure uvicorn is running on port 8000.`);
    } else {
      throw new Error('Connection failed. The backend server on Render free tier may be waking up from sleep (takes 30-50s). Please wait a moment and try again.');
    }
  }

  // Parse body safely (could be JSON, text, or empty)
  let data = null;
  const contentType = response.headers.get('content-type') || '';
  if (contentType.includes('application/json')) {
    try {
      data = await response.json();
    } catch {
      data = null;
    }
  } else {
    try {
      const text = await response.text();
      try {
        data = JSON.parse(text);
      } catch {
        data = text ? { detail: text } : null;
      }
    } catch {
      data = null;
    }
  }

  if (!response.ok) {
    let errorMsg = data?.detail || data?.message;
    if (!errorMsg) {
      if (response.status === 401) {
        errorMsg = 'Access Denied: Incorrect gatekeeper token.';
      } else if (response.status === 429) {
        errorMsg = 'Too many attempts. Please wait 5 minutes before retrying.';
      } else if (response.status === 502 || response.status === 503 || response.status === 504) {
        errorMsg = 'Backend server is currently starting up (cold start). Please retry in 30 seconds.';
      } else {
        errorMsg = `Server error (${response.status}: ${response.statusText || 'Unexpected response'})`;
      }
    }
    const err = new Error(errorMsg);
    err.status = response.status;
    err.data = data;
    throw err;
  }

  return data;
}
