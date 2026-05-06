const DEFAULT_CHIPS = [
  "Show top 10 by revenue",
  "Group by month",
  "Compare year over year",
  "Show as table",
  "Summarize key insights",
];

export function FollowUpChips({ onSelect }: { onSelect: (s: string) => void }) {
  return (
    <div className="flex gap-2 flex-wrap mt-3 mb-1 pl-1">
      {DEFAULT_CHIPS.map((chip) => (
        <button
          key={chip}
          onClick={() => onSelect(chip)}
          className="text-[11.5px] px-3 py-1.5 rounded-full transition-all"
          style={{
            border: "0.5px solid var(--color-border-secondary)",
            background: "var(--color-background-secondary)",
            color: "var(--color-text-secondary)",
          }}
          onMouseEnter={(e) => {
            e.currentTarget.style.background = "var(--color-background-tertiary)";
            e.currentTarget.style.borderColor = "var(--color-border-primary)";
            e.currentTarget.style.color = "var(--color-text-primary)";
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.background = "var(--color-background-secondary)";
            e.currentTarget.style.borderColor = "var(--color-border-secondary)";
            e.currentTarget.style.color = "var(--color-text-secondary)";
          }}
        >
          {chip}
        </button>
      ))}
    </div>
  );
}
