'use client';

import { useState, useEffect } from 'react';

interface AccountData {
  balance: number;
  nav: number;
  unrealized_pl: number;
  margin_used: number;
  margin_available: number;
  open_trade_count: number;
}

export default function AccountPanel() {
  const [account, setAccount] = useState<AccountData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchAccount = async () => {
      try {
        const response = await fetch('/api/account');
        if (response.ok) {
          const data = await response.json();
          setAccount(data);
        }
      } catch (error) {
        console.error('Error fetching account:', error);
      } finally {
        setLoading(false);
      }
    };

    fetchAccount();
    const interval = setInterval(fetchAccount, 10000); // Refresh every 10 seconds
    return () => clearInterval(interval);
  }, []);

  if (loading || !account) {
    return (
      <div className="card">
        <div className="px-4 py-3 border-b border-panel-border">
          <span className="text-xs font-display font-semibold text-gray-200 uppercase tracking-wider">
            Account Summary
          </span>
        </div>
        <div className="p-8 text-center text-muted text-xs">
          Loading account data...
        </div>
      </div>
    );
  }

  const isProfitable = account.unrealized_pl >= 0;

  return (
    <div className="card">
      <div className="px-4 py-3 border-b border-panel-border">
        <span className="text-xs font-display font-semibold text-gray-200 uppercase tracking-wider">
          Account Summary
        </span>
      </div>
      <div className="p-4">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div>
            <div className="text-xs text-subtle mb-1">Balance</div>
            <div className="text-lg font-bold text-gray-100">
              ${account.balance.toFixed(2)}
            </div>
          </div>
          <div>
            <div className="text-xs text-subtle mb-1">Equity (NAV)</div>
            <div className="text-lg font-bold text-gray-100">
              ${account.nav.toFixed(2)}
            </div>
          </div>
          <div>
            <div className="text-xs text-subtle mb-1">Unrealized P/L</div>
            <div className={`text-lg font-bold ${isProfitable ? 'text-bull' : 'text-bear'}`}>
              {isProfitable ? '+' : ''}${account.unrealized_pl.toFixed(2)}
            </div>
          </div>
          <div>
            <div className="text-xs text-subtle mb-1">Open Trades</div>
            <div className="text-lg font-bold text-gray-100">
              {account.open_trade_count}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
