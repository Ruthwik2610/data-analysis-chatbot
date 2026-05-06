import { useEffect } from "react";

export function useKeyboardShortcuts({
  onNewChat,
  onStop,
  loading,
}: {
  onNewChat: () => void;
  onStop: () => void;
  loading: boolean;
}) {
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      const mod = e.metaKey || e.ctrlKey;

      // Cmd/Ctrl+K — focus input
      if (mod && e.key === "k") {
        e.preventDefault();
        window.dispatchEvent(new CustomEvent("data-chat:focus-input"));
      }

      // Cmd/Ctrl+N — new chat
      if (mod && e.key === "n") {
        e.preventDefault();
        onNewChat();
      }

      // Escape — stop streaming
      if (e.key === "Escape" && loading) {
        e.preventDefault();
        onStop();
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [onNewChat, onStop, loading]);
}
