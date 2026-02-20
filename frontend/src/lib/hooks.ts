'use client';

import { useState, useEffect } from 'react';

export function useOpenTrades() {
  const [trades, setTrades] = useState([]);
  const [loading, setLoading] = useState(true);

  const refresh = async () => {
    try {
      const response = await fetch('/api/trades/open');
      if (response.ok) {
        const data = await response.json();
        setTrades(data.trades || []);
      }
    } catch (error) {
      console.error('Error fetching open trades:', error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    refresh();
    const interval = setInterval(refresh, 5000); //Refresh every 5 seconds
    return () => clearInterval(interval);
  }, []);

  return { trades, loading, refresh };
}
