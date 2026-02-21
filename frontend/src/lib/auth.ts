/**
 * Auth helpers — JWT stored in localStorage.
 * Token is issued by POST /api/auth/login and expires after 24h.
 */

const TOKEN_KEY = 'ats_token';

export function getToken(): string | null {
  if (typeof window === 'undefined') return null;
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token);
}

export function removeToken(): void {
  localStorage.removeItem(TOKEN_KEY);
}

/** Decode the JWT payload (no signature verification — trusted from server). */
export function getTokenPayload(): { sub: string; exp: number } | null {
  const token = getToken();
  if (!token) return null;
  try {
    const parts = token.split('.');
    if (parts.length !== 3) return null;
    const payload = JSON.parse(atob(parts[1]));
    return payload as { sub: string; exp: number };
  } catch {
    return null;
  }
}

/** True if a non-expired token exists in localStorage. */
export function isAuthenticated(): boolean {
  const payload = getTokenPayload();
  if (!payload) return false;
  // exp is seconds since epoch; Date.now() is milliseconds
  return payload.exp * 1000 > Date.now();
}
