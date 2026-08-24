import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = { title: 'Signal | Digital signage for schools', description: 'A calmer, safer way to manage every school display.' };

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
