"use client";

export default function GlobalError({
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <html>
      <body>
        <main
          className="flex min-h-screen flex-col items-center justify-center gap-3 px-6 text-center"
          style={{
            background: "var(--color-background-primary)",
            color: "var(--color-text-primary)",
          }}
        >
          <h1 className="text-[24px] font-semibold">Something went wrong</h1>
          <p className="max-w-[420px] text-[14px]" style={{ color: "var(--color-text-secondary)" }}>
            The chat workspace hit an unexpected error. Your uploaded sources and saved chats are kept on the server.
          </p>
          <button
            type="button"
            onClick={reset}
            className="rounded-[8px] px-3 py-2 text-[13px]"
            style={{
              background: "var(--color-text-primary)",
              color: "var(--color-background-primary)",
            }}
          >
            Try again
          </button>
        </main>
      </body>
    </html>
  );
}
