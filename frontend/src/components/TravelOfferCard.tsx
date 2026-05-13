import React from "react";
import type { TravelOffer } from "@/lib/types";
import { ArrowRight, Clock, AlertTriangle, CheckCircle2 } from "lucide-react";

export function TravelOfferCard({ offer }: { offer: TravelOffer }) {
  // Format dates: ISO to time (e.g. "14:30")
  const formatTime = (isoString: string) => {
    if (!isoString) return "";
    return new Date(isoString).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  };

  const formatDuration = (mins: number) => {
    const h = Math.floor(mins / 60);
    const m = mins % 60;
    return `${h}h ${m}m`;
  };

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
      <div className="flex items-center justify-between mb-5">
        <div className="flex flex-col items-start">
          <span className="text-[20px] font-bold text-[var(--color-text-primary)]">{formatTime(offer.departure_at)}</span>
          <span className="text-[13px] font-medium" style={{ color: "var(--color-text-secondary)" }}>{offer.origin}</span>
        </div>
        
        <div className="flex flex-col items-center flex-1 px-4">
          <span className="text-[10px] font-bold tracking-widest uppercase mb-1" style={{ color: "var(--color-text-tertiary)" }}>
            {formatDuration(offer.duration_minutes)}
          </span>
          <div className="w-full relative flex items-center justify-center h-[2px] bg-white/10 rounded-full">
             <div className="absolute w-[6px] h-[6px] rounded-full border-[1.5px] border-[var(--color-text-primary)] bg-transparent left-0" />
             <div className="absolute w-[6px] h-[6px] rounded-full border-[1.5px] border-[var(--color-text-primary)] bg-transparent right-0" />
          </div>
          <span className="text-[11px] font-medium mt-1" style={{ color: "var(--color-text-secondary)" }}>
            {offer.stops === 0 ? "Direct" : `${offer.stops} Stop${offer.stops > 1 ? "s" : ""}`}
          </span>
        </div>

        <div className="flex flex-col items-end">
          <span className="text-[20px] font-bold text-[var(--color-text-primary)]">{formatTime(offer.arrival_at)}</span>
          <span className="text-[13px] font-medium" style={{ color: "var(--color-text-secondary)" }}>{offer.destination}</span>
        </div>
      </div>

      {/* Bottom row: Price & Book */}
      <div className="flex items-end justify-between mt-auto pt-4 border-t border-white/5">
        <div className="flex flex-col">
          <span className="text-[10px] font-bold tracking-widest uppercase opacity-60" style={{ color: "var(--color-text-tertiary)" }}>
            Total ({offer.currency})
          </span>
          <span className="text-[24px] font-black tracking-tight" style={{ color: "var(--color-text-primary)" }}>
            ${offer.price_usd.toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 0 })}
          </span>
        </div>
        
        <a 
          href={offer.booking_redirect_url} 
          target="_blank" 
          rel="noopener noreferrer"
          className="flex items-center gap-1.5 px-4 py-2 rounded-[12px] bg-blue-600 hover:bg-blue-500 text-white font-bold text-[13px] transition-colors shadow-md active:scale-95"
        >
          View & Book
          <ArrowRight size={14} strokeWidth={2.5} />
        </a>
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
