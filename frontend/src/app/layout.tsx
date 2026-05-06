import type { Metadata } from "next";
import { WebVitalsReporter } from "./WebVitalsReporter";
import "./globals.css";

export const metadata: Metadata = {
  title: "Unipro Data Chat",
  description: "Chat with your CSV / Excel / PDF / DuckDB / API data",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <head>
        {/* Synchronously apply saved theme before first paint to prevent flash */}
        <script
          dangerouslySetInnerHTML={{
            __html: `(function(){try{var t=localStorage.getItem('theme');if(t)document.documentElement.setAttribute('data-theme',t);}catch(e){}})()`,
          }}
        />
      </head>
      <body>
        {children}
        <WebVitalsReporter />
      </body>
    </html>
  );
}
