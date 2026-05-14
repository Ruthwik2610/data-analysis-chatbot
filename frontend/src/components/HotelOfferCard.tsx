import React from "react";
import type { HotelOffer } from "@/lib/types";
import { AlertTriangle, CheckCircle2, MapPin, Bed, Star } from "lucide-react";

const formatDate = (iso: string) => {
  if (!iso) return "";
  // Append T00:00 so YYYY-MM-DD parses as local midnight, not UTC midnight —
  // otherwise west-of-UTC users see the previous day for a check-in/check-out date.
  return new Date(iso + "T00:00").toLocaleDateString([], { month: "short", day: "numeric" });
};

const formatNights = (checkIn: string, checkOut: string): number => {
  if (!checkIn || !checkOut) return 0;
  // Parse as local midnight (see formatDate comment). Both endpoints parsed the
  // same way, so the diff is unaffected — but keep it consistent.
  const ms = new Date(checkOut + "T00:00").getTime() - new Date(checkIn + "T00:00").getTime();
  return Math.max(1, Math.round(ms / (1000 * 60 * 60 * 24)));
};

const formatCurrency = (amount: number, currency: string) => {
  try {
    return new Intl.NumberFormat(undefined, {
      style: "currency",
      currency: currency || "USD",
      maximumFractionDigits: 0,
    }).format(amount);
  } catch {
    return `${currency || "USD"} ${Math.round(amount).toLocaleString()}`;
  }
};

function StarRow({ count }: { count: number }) {
  const filled = Math.max(0, Math.min(5, Math.round(count)));
  return (
    <div className="flex items-center gap-0.5 mt-0.5">
      {Array.from({ length: 5 }).map((_, i) => (
        <Star
          key={i}
          size={12}
          strokeWidth={1.5}
          className={i < filled ? "text-amber-400 fill-amber-400" : "text-white/20 fill-transparent"}
        />
      ))}
    </div>
  );
}

type HotelOfferCardProps = {
  offer: HotelOffer;
  selected?: boolean;
  onSelect?: () => void;
  selectLabel?: string;
};

export function HotelOfferCard({ offer, selected = false, onSelect, selectLabel }: HotelOfferCardProps) {
  const nights = formatNights(offer.check_in_date, offer.check_out_date);

  return (
    <div className="flex flex-col p-5 rounded-[20px] glass shadow-lg border border-white/5 transition-transform hover:-translate-y-1 hover:shadow-xl w-full min-w-[300px]">
      {/* Top row: Hotel name & Compliance badge */}
      <div className="flex justify-between items-start mb-4">
        <div className="flex flex-col">
          <span className="font-bold text-[16px] text-[var(--color-text-primary)]">{offer.name}</span>
          {offer.star_rating !== null && <StarRow count={offer.star_rating} />}
        </div>
        {offer.policy_compliant ? (
          <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 text-[11px] font-bold tracking-wide">
            <CheckCircle2 size={13} strokeWidth={2.5} />
            COMPLIANT
          </div>
        ) : (
          <div
            className="flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-bold tracking-wide group relative cursor-help"
            style={{
              background: "rgba(239, 68, 68, 0.1)",
              color: "var(--color-text-warning, #ef4444)",
              border: "1px solid rgba(239, 68, 68, 0.2)"
            }}
          >
            <AlertTriangle size={13} strokeWidth={2.5} />
            OUT OF POLICY
            {/* Tooltip */}
            <div className="absolute bottom-full mb-2 right-0 hidden group-hover:block w-[200px] p-2 text-[11px] glass rounded-lg shadow-xl text-left whitespace-normal z-10 leading-[1.5]">
              {offer.policy_violation_reason || "Violation reason unavailable."}
            </div>
          </div>
        )}
      </div>

      {/* Address row */}
      <div className="flex items-center gap-1 mb-3">
        <MapPin size={13} style={{ color: "var(--color-text-secondary)", flexShrink: 0 }} />
        <span
          className="text-[13px] font-medium opacity-80 truncate"
          style={{ color: "var(--color-text-secondary)" }}
        >
          {offer.address}
        </span>
      </div>

      {/* Photo */}
      {offer.photo_url ? (
        <img
          src={offer.photo_url}
          alt={offer.name}
          className="w-full h-32 object-cover rounded-[12px] mt-3 mb-3"
          loading="lazy"
        />
      ) : null}

      {/* Stay info row */}
      <div className="flex items-center justify-between mb-5">
        <div className="flex flex-col items-start">
          <span className="text-[20px] font-bold text-[var(--color-text-primary)]">{formatDate(offer.check_in_date)}</span>
          <span className="text-[13px] font-medium" style={{ color: "var(--color-text-secondary)" }}>Check-in</span>
        </div>

        <div className="flex flex-col items-center flex-1 px-4">
          <span className="text-[10px] font-bold tracking-widest uppercase mb-1" style={{ color: "var(--color-text-tertiary)" }}>
            {nights} night{nights !== 1 ? "s" : ""}
          </span>
          <div className="w-full relative flex items-center justify-center h-[2px] bg-white/10 rounded-full">
            <div className="absolute w-[6px] h-[6px] rounded-full border-[1.5px] border-[var(--color-text-primary)] bg-transparent left-0" />
            <Bed size={14} className="text-white/40" />
            <div className="absolute w-[6px] h-[6px] rounded-full border-[1.5px] border-[var(--color-text-primary)] bg-transparent right-0" />
          </div>
          <span className="text-[11px] font-medium mt-1" style={{ color: "var(--color-text-secondary)" }}>
            {offer.rooms} rm · {offer.guests} guest{offer.guests !== 1 ? "s" : ""}
          </span>
        </div>

        <div className="flex flex-col items-end">
          <span className="text-[20px] font-bold text-[var(--color-text-primary)]">{formatDate(offer.check_out_date)}</span>
          <span className="text-[13px] font-medium" style={{ color: "var(--color-text-secondary)" }}>Check-out</span>
        </div>
      </div>

      {/* Price footer */}
      <div className="flex items-end justify-between mt-auto pt-4 border-t border-white/5">
        <div className="flex flex-col">
          <span className="text-[10px] font-bold tracking-widest uppercase opacity-60" style={{ color: "var(--color-text-tertiary)" }}>
            Total ({offer.currency})
          </span>
          <span className="text-[24px] font-black tracking-tight" style={{ color: "var(--color-text-primary)" }}>
            {formatCurrency(offer.total_price, offer.currency)}
          </span>
          <span className="text-[12px] font-medium opacity-70" style={{ color: "var(--color-text-secondary)" }}>
            {formatCurrency(offer.price_per_night, offer.currency)}/night
          </span>
        </div>

        {onSelect && (
          <button
            type="button"
            onClick={onSelect}
            aria-label={selectLabel}
            aria-pressed={selected}
            className="flex items-center gap-1.5 px-4 py-2 rounded-[12px] font-bold text-[13px] transition-colors shadow-md active:scale-95"
            style={{
              background: selected ? "var(--color-text-info)" : "var(--color-background-elevated)",
              color: selected ? "var(--color-background-primary)" : "var(--color-text-primary)",
              border: "1px solid var(--color-border-secondary)",
            }}
          >
            {selected ? "Selected" : "Select"}
          </button>
        )}
      </div>
    </div>
  );
}
