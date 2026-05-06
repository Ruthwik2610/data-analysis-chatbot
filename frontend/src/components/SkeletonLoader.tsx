export function SkeletonLine({ width = "100%", height = 12 }: { width?: string; height?: number }) {
  return (
    <div
      className="skeleton"
      style={{ width, height, marginBottom: 8, borderRadius: 6, flexShrink: 0 }}
    />
  );
}

export function SkeletonChatList() {
  return (
    <div className="px-4 py-2">
      {([100, 78, 90, 65] as number[]).map((w, i) => (
        <SkeletonLine key={i} width={`${w}%`} height={13} />
      ))}
    </div>
  );
}
