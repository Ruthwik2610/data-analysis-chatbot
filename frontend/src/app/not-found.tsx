import Link from "next/link";

export default function NotFound() {
  return (
    <main
      className="flex min-h-screen flex-col items-center justify-center gap-3 px-6 text-center"
      style={{
        background: "var(--color-background-primary)",
        color: "var(--color-text-primary)",
      }}
    >
      <h1 className="text-[24px] font-semibold">Page not found</h1>
      <p className="max-w-[420px] text-[14px]" style={{ color: "var(--color-text-secondary)" }}>
        This route is not part of the Data Chat workspace.
      </p>
      <Link
        href="/"
        className="rounded-[8px] px-3 py-2 text-[13px]"
        style={{
          background: "var(--color-text-primary)",
          color: "var(--color-background-primary)",
        }}
      >
        Back to chat
      </Link>
    </main>
  );
}
