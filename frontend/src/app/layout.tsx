import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Data Chat",
  description: "Chat with your CSV / Excel / DuckDB / API data",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
