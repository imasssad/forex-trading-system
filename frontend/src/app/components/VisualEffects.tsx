'use client';

import { useEffect } from 'react';

export function VisualEffects() {
  useEffect(() => {
    // Add visual effects after hydration to avoid SSR mismatch
    document.body.classList.add('noise', 'scanlines');
  }, []);

  return null;
}