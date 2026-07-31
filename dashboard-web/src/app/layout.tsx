import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Email Campaign Dashboard",
  description: "Cold email campaign performance dashboard",
};

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
