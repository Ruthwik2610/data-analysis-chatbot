import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Admin | Data Analysis Chatbot",
  description: "Insights and usage statistics",
};

export default function AdminLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="min-h-screen bg-primary">
      {children}
    </div>
  );
}
