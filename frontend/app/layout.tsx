import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "SAR Command Center",
  description: "Search and Rescue AI Assistant",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="h-full">{children}</body>
    </html>
  );
}
