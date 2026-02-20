import './globals.css';

export const metadata = {
  title: 'ATS Trading System',
  description: 'Automated Trading System Dashboard',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
