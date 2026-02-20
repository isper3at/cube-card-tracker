// Backend API base URL.
// Set API_URL in frontend/.env to point at a different host/port.
// Defaults to the same host the page is served from (works when backend proxies the frontend,
// or when the dev script handles the proxy).
const API_URL = process.env.API_URL ?? 'http://localhost:5000';

/**
 * JSON fetch wrapper. Throws a plain Error with the server's message on non-2xx responses.
 */
export async function apiFetch<T>(path: string, options: RequestInit = {}): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options,
  });

  if (res.status === 204) {
    return undefined as T;
  }

  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.error ?? `HTTP ${res.status}`);
  }

  return res.json();
}

/**
 * Multipart file upload. Don't set Content-Type manually — the browser adds
 * the boundary string automatically when you pass a FormData body.
 */
export async function apiUpload<T>(path: string, formData: FormData): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    method: 'POST',
    body: formData,
  });

  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.error ?? `HTTP ${res.status}`);
  }

  return res.json();
}

// Export so checkin.ts can build image src URLs directly
export { API_URL };

