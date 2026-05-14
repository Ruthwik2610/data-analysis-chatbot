import React from "react";
import type { TravelOffer } from "@/lib/types";
import { Clock, AlertTriangle, CheckCircle2 } from "lucide-react";

const formatTime = (iso: string) => {
  if (!iso) return "";
  return new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
};

const formatDuration = (mins: number) => {
  const h = Math.floor(mins / 60);
  const m = mins % 60;
  return `${h}h ${m}m`;
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

type RouteRowProps = {
  departure_at: string;
  origin: string;
  arrival_at: string;
  destination: string;
  duration_minutes: number;
  stops: number;
};

function RouteRow({ departure_at, origin, arrival_at, destination, duration_minutes, stops }: RouteRowProps) {
  return (
    <div className="flex items-center justify-between mb-5">
      <div className="flex flex-col items-start">
        <span className="text-[20px] font-bold text-[var(--color-text-primary)]">{formatTime(departure_at)}</span>
        <span className="text-[13px] font-medium" style={{ color: "var(--color-text-secondary)" }}>{origin}</span>
      </div>

      <div className="flex flex-col items-center flex-1 px-4">
        <span className="text-[10px] font-bold tracking-widest uppercase mb-1" style={{ color: "var(--color-text-tertiary)" }}>
          {formatDuration(duration_minutes)}
        </span>
        <div className="w-full relative flex items-center justify-center h-[2px] bg-white/10 rounded-full">
           <div className="absolute w-[6px] h-[6px] rounded-full border-[1.5px] border-[var(--color-text-primary)] bg-transparent left-0" />
           <div className="absolute w-[6px] h-[6px] rounded-full border-[1.5px] border-[var(--color-text-primary)] bg-transparent right-0" />
        </div>
        <span className="text-[11px] font-medium mt-1" style={{ color: "var(--color-text-secondary)" }}>
          {stops === 0 ? "Direct" : `${stops} Stop${stops > 1 ? "s" : ""}`}
        </span>
      </div>

      <div className="flex flex-col items-end">
        <span className="text-[20px] font-bold text-[var(--color-text-primary)]">{formatTime(arrival_at)}</span>
        <span className="text-[13px] font-medium" style={{ color: "var(--color-text-secondary)" }}>{destination}</span>
      </div>
    </div>
  );
}

type TravelOfferCardProps = {
  offer: TravelOffer;
  selected?: boolean;
  onSelect?: () => void;
  selectLabel?: string;
};

export function TravelOfferCard({ offer, selected = false, onSelect, selectLabel }: TravelOfferCardProps) {
  const hasReturn = !!offer.return_slice;

  return (
    <div className="flex flex-col p-5 rounded-[20px] glass shadow-lg border border-white/5 transition-transform hover:-translate-y-1 hover:shadow-xl w-full min-w-[300px]">
      {/* Top row: Airline & Badge */}
      <div className="flex justify-between items-start mb-4">
        <div className="flex flex-col">
          <span className="font-bold text-[16px] text-[var(--color-text-primary)]">{offer.airline}</span>
          <span className="text-[11px] font-medium tracking-wide uppercase opacity-70" style={{ color: "var(--color-text-tertiary)" }}>
            {offer.cabin_class.replace("_", " ")}
          </span>
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

      {/* Middle row: Route & Times */}
      {hasReturn && (
        <span className="text-[11px] font-medium tracking-wide uppercase opacity-70 mb-1" style={{ color: "var(--color-text-tertiary)" }}>
          Outbound
        </span>
      )}
      <RouteRow
        departure_at={offer.departure_at}
        origin={offer.origin}
        arrival_at={offer.arrival_at}
        destination={offer.destination}
        duration_minutes={offer.duration_minutes}
        stops={offer.stops}
      />
      {offer.return_slice && (
        <>
          <span className="text-[11px] font-medium tracking-wide uppercase opacity-70 mb-1" style={{ color: "var(--color-text-tertiary)" }}>
            Return
          </span>
          <RouteRow
            departure_at={offer.return_slice.departure_at}
            origin={offer.return_slice.origin}
            arrival_at={offer.return_slice.arrival_at}
            destination={offer.return_slice.destination}
            duration_minutes={offer.return_slice.duration_minutes}
            stops={offer.return_slice.stops}
          />
        </>
      )}

      {/* Bottom row: Price & Selection */}
      <div className="flex items-end justify-between mt-auto pt-4 border-t border-white/5">
        <div className="flex flex-col">
          <span className="text-[10px] font-bold tracking-widest uppercase opacity-60" style={{ color: "var(--color-text-tertiary)" }}>
            Total ({offer.currency})
          </span>
          <span className="text-[24px] font-black tracking-tight" style={{ color: "var(--color-text-primary)" }}>
            {formatCurrency(offer.price_usd, offer.currency)}
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
      
      {/* Expiry Footer */}
      {offer.expires_at && (
        <div className="mt-3 flex items-center justify-center gap-1.5 text-[10px] uppercase tracking-widest font-bold opacity-50" style={{ color: "var(--color-text-secondary)" }}>
          <Clock size={12} />
          Expires {new Date(offer.expires_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
        </div>
      )}
    </div>
  );
}
