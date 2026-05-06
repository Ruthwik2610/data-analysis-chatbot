export function StreamingBar({ visible }: { visible: boolean }) {
  if (!visible) return null;
  return (
    <div
      style={{
        position: "absolute",
        top: 0,
        left: 0,
        right: 0,
        height: 2,
        overflow: "hidden",
        zIndex: 50,
        pointerEvents: "none",
      }}
    >
      <div
        style={{
          height: "100%",
          width: "30%",
          background: "linear-gradient(90deg, transparent, #6366f1, #8b5cf6, #a78bfa, transparent)",
          animation: "streamSlide 1.2s ease-in-out infinite",
        }}
      />
    </div>
  );
}
