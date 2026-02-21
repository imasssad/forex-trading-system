'use client';

import { useState, useEffect, FormEvent } from 'react';
import { useRouter } from 'next/navigation';
import { setToken, isAuthenticated } from '../../lib/auth';

export default function LoginPage() {
  const router = useRouter();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  // If already logged in, skip the login page
  useEffect(() => {
    if (isAuthenticated()) {
      router.push('/');
    }
  }, [router]);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      const res = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password }),
      });

      if (res.ok) {
        const data = await res.json();
        setToken(data.access_token);
        router.push('/');
      } else {
        setError('Invalid username or password');
      }
    } catch {
      setError('Could not reach the server. Please try again.');
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-[#0B0E11] px-4">
      <div className="w-full max-w-sm">

        {/* Logo / Title */}
        <div className="text-center mb-8">
          <h1 className="text-3xl font-bold text-gray-100 font-display tracking-tight">
            ATS Trading
          </h1>
          <p className="mt-2 text-sm text-[#5C6A7F]">
            Sign in to your dashboard
          </p>
        </div>

        {/* Card */}
        <div className="bg-[#12161C] border border-[#1E2530] rounded-2xl p-8 shadow-2xl">
          <form onSubmit={handleSubmit} className="space-y-5">

            {/* Username */}
            <div>
              <label htmlFor="username" className="block text-xs font-medium text-[#5C6A7F] uppercase tracking-wider mb-2">
                Username
              </label>
              <input
                id="username"
                type="text"
                autoComplete="username"
                required
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                className="w-full px-4 py-3 bg-[#0B0E11] border border-[#1E2530] rounded-lg text-gray-100 text-sm
                           placeholder-[#3A4553] focus:outline-none focus:border-[rgb(0,212,170)]
                           focus:ring-1 focus:ring-[rgb(0,212,170)] transition-colors"
                placeholder="admin"
              />
            </div>

            {/* Password */}
            <div>
              <label htmlFor="password" className="block text-xs font-medium text-[#5C6A7F] uppercase tracking-wider mb-2">
                Password
              </label>
              <input
                id="password"
                type="password"
                autoComplete="current-password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full px-4 py-3 bg-[#0B0E11] border border-[#1E2530] rounded-lg text-gray-100 text-sm
                           placeholder-[#3A4553] focus:outline-none focus:border-[rgb(0,212,170)]
                           focus:ring-1 focus:ring-[rgb(0,212,170)] transition-colors"
                placeholder="••••••••"
              />
            </div>

            {/* Error */}
            {error && (
              <div className="flex items-center gap-2 px-4 py-3 bg-[rgba(255,71,87,0.13)] border border-[rgba(255,71,87,0.3)] rounded-lg">
                <span className="text-[rgb(255,71,87)] text-sm">{error}</span>
              </div>
            )}

            {/* Submit */}
            <button
              type="submit"
              disabled={loading}
              className="w-full py-3 px-4 bg-[rgb(0,212,170)] hover:bg-[rgba(0,212,170,0.85)]
                         disabled:opacity-50 disabled:cursor-not-allowed
                         text-[#0B0E11] font-semibold text-sm rounded-lg
                         transition-colors duration-150 focus:outline-none
                         focus:ring-2 focus:ring-[rgb(0,212,170)] focus:ring-offset-2 focus:ring-offset-[#12161C]"
            >
              {loading ? (
                <span className="flex items-center justify-center gap-2">
                  <svg className="animate-spin h-4 w-4" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor"
                      d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                  </svg>
                  Signing in…
                </span>
              ) : (
                'Sign In'
              )}
            </button>
          </form>
        </div>

        <p className="mt-6 text-center text-xs text-[#3A4553]">
          ATS Trading System · Secured with JWT
        </p>
      </div>
    </div>
  );
}
