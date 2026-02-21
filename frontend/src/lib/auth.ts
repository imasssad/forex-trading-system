/**
 * Auth helpers — JWT stored as a browser cookie.
 * Cookie is readable by Next.js middleware (server-side) so ALL pages
 * are protected without any client-side localStorage hacks.
 */

const TOKEN_KEY = 'ats_auth';
const MAX_AGE = 60 * 60 * 24; // 24 hours in seconds

export function getToken(): string | null {
  if (typeof window === 'undefined') return null;
  const match = document.cookie.match(new RegExp(`(?:^|; )${TOKEN_KEY}=([^;]*)`));
  return match ? decodeURIComponent(match[1]) : null;
}

export function setToken(token: string): void {
  document.cookie = `${TOKEN_KEY}=${encodeURIComponent(token)}; path=/; max-age=${MAX_AGE}; SameSite=Strict`;
}

export function removeToken(): void {
  document.cookie = `${TOKEN_KEY}=; path=/; max-age=0`;
}

/** Decode the JWT payload (no signature verification — trusted from server). */
export function getTokenPayload(): { sub: string; exp: number } | null {
  const token = getToken();
  if (!token) return null;
  try {
    const parts = token.split('.');
    if (parts.length !== 3) return null;
    return JSON.parse(atob(parts[1])) as { sub: string; exp: number };
  } catch {
    return null;
  }
}

/** True if a non-expired token cookie exists. */
export function isAuthenticated(): boolean {
  const payload = getTokenPayload();
  if (!payload) return false;
  return payload.exp * 1000 > Date.now();
}
