import { NextRequest, NextResponse } from 'next/server';

/** Pages that don't require authentication */
const PUBLIC_PATHS = ['/login', '/signup'];

export function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl;

  // Always allow public auth pages and Next.js internals
  if (PUBLIC_PATHS.some((p) => pathname.startsWith(p))) {
    return NextResponse.next();
  }

  // Check for the auth cookie set by the login page
  const token = request.cookies.get('ats_auth')?.value;

  if (!token) {
    return NextResponse.redirect(new URL('/login', request.url));
  }

  // Validate JWT expiry (decode without signature — backend already verified it)
  try {
    const payload = JSON.parse(atob(token.split('.')[1]));
    if (payload.exp * 1000 < Date.now()) {
      // Token expired — clear cookie and redirect
      const response = NextResponse.redirect(new URL('/login', request.url));
      response.cookies.delete('ats_auth');
      return response;
    }
  } catch {
    return NextResponse.redirect(new URL('/login', request.url));
  }

  return NextResponse.next();
}

export const config = {
  // Run on all routes except static assets and API proxy routes
  matcher: ['/((?!_next/static|_next/image|favicon.ico|api/).*)'],
};
