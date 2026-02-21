'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { isAuthenticated } from '../lib/auth';
import Sidebar from '../components/Sidebar';
import StatusBar from '../components/StatusBar';
import AccountPanel from '../components/panels/AccountPanel';
import OpenTradesPanel from '../components/panels/OpenTradesPanel';
import TradeHistoryPanel from '../components/panels/TradeHistoryPanel';
import PerformancePanel from '../components/panels/PerformancePanel';
import NewsPanel from '../components/panels/NewsPanel';
import ActivityPanel from '../components/panels/ActivityPanel';
import SettingsPanel from '../components/panels/SettingsPanel';
import BacktestPanel from '../components/panels/BacktestPanel';
import SignalsPanel from '../components/panels/SignalsPanel';

export type ActiveView =
  | 'overview'
  | 'trades'
  | 'performance'
  | 'signals'
  | 'backtest'
  | 'news'
  | 'settings'
  | 'logs';

export default function Dashboard() {
  const router = useRouter();
  const [activeView, setActiveView] = useState<ActiveView>('overview');
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [authed, setAuthed] = useState(false);

  // Auth guard — redirect to login if no valid token.
  // Must use state (not inline isAuthenticated()) because localStorage is
  // unavailable during SSR, causing a blank render without this pattern.
  useEffect(() => {
    if (isAuthenticated()) {
      setAuthed(true);
    } else {
      router.replace('/login');
    }
  }, [router]);

  // Show dark loading screen while auth check completes (avoids blank flash)
  if (!authed) {
    return (
      <div className="flex h-screen items-center justify-center bg-[#0B0E11]">
        <div className="flex flex-col items-center gap-3">
          <svg className="animate-spin h-8 w-8 text-[rgb(0,212,170)]" fill="none" viewBox="0 0 24 24">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
          </svg>
          <span className="text-sm text-[#5C6A7F]">Loading…</span>
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-screen overflow-hidden">
      {/* Mobile Sidebar Overlay */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 bg-black/50 z-40 lg:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* Sidebar */}
      <Sidebar
        activeView={activeView}
        onNavigate={(view) => {
          setActiveView(view);
          setSidebarOpen(false); // Close sidebar on mobile after navigation
        }}
        isOpen={sidebarOpen}
        onToggle={() => setSidebarOpen(!sidebarOpen)}
      />

      {/* Main Content */}
      <div className="flex-1 flex flex-col min-w-0 lg:ml-0">
        {/* Top Status Bar */}
        <StatusBar onMenuClick={() => setSidebarOpen(true)} />

        {/* Content Area */}
        <main className="flex-1 overflow-auto p-2 sm:p-4">
          {activeView === 'overview' && <OverviewLayout />}
          {activeView === 'trades' && <TradesLayout />}
          {activeView === 'performance' && <PerformanceLayout />}
          {activeView === 'signals' && <SignalsLayout />}
          {activeView === 'backtest' && <BacktestLayout />}
          {activeView === 'news' && <NewsLayout />}
          {activeView === 'settings' && <SettingsLayout />}
          {activeView === 'logs' && <LogsLayout />}
        </main>
      </div>
    </div>
  );
}

function OverviewLayout() {
  return (
    <div className="grid grid-cols-12 gap-3 animate-fade-in">
      {/* Account summary - full width */}
      <div className="col-span-12">
        <AccountPanel />
      </div>

      {/* Open trades - left 7 cols */}
      <div className="col-span-12 lg:col-span-7">
        <OpenTradesPanel />
      </div>

      {/* News & Activity - right 5 cols */}
      <div className="col-span-12 lg:col-span-5 flex flex-col gap-3">
        <NewsPanel compact />
        <ActivityPanel compact />
      </div>

      {/* Recent trade history */}
      <div className="col-span-12">
        <TradeHistoryPanel compact />
      </div>
    </div>
  );
}

function TradesLayout() {
  return (
    <div className="flex flex-col gap-3 animate-fade-in">
      <OpenTradesPanel />
      <TradeHistoryPanel />
    </div>
  );
}

function PerformanceLayout() {
  return (
    <div className="animate-fade-in">
      <PerformancePanel />
    </div>
  );
}

function NewsLayout() {
  return (
    <div className="animate-fade-in">
      <NewsPanel />
    </div>
  );
}

function SettingsLayout() {
  return (
    <div className="animate-fade-in">
      <SettingsPanel />
    </div>
  );
}

function SignalsLayout() {
  return (
    <div className="animate-fade-in">
      <SignalsPanel />
    </div>
  );
}

function BacktestLayout() {
  return (
    <div className="animate-fade-in">
      <BacktestPanel />
    </div>
  );
}

function LogsLayout() {
  return (
    <div className="animate-fade-in">
      <ActivityPanel />
    </div>
  );
}
