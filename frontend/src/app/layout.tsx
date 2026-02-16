import type { Metadata } from 'next';
import './globals.css';
import { VisualEffects } from './components/VisualEffects';

export const metadata: Metadata = {
  title: 'Montgomery Trading Platform',
  description: 'Montgomery Automated Forex Trading System',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="dark">
      <body suppressHydrationWarning>
        {children}
        <VisualEffects />
      </body>
    </html>
  );
}
