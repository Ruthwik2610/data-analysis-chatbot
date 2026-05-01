import type { Metadata } from "next";
import { WebVitalsReporter } from "./WebVitalsReporter";
import "./globals.css";

export const metadata: Metadata = {
  title: "Data Chat",
  description: "Chat with your CSV / Excel / PDF / DuckDB / API data",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        {children}
        <WebVitalsReporter />
      </body>
    </html>
  );
}
