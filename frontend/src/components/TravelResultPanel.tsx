import React, { useState } from "react";
import type { TravelOffer, TravelIntent, HotelOffer } from "@/lib/types";
import { TravelOfferCard } from "./TravelOfferCard";
import { HotelOfferCard } from "./HotelOfferCard";
import { RefreshCw, Plane, Filter, Hotel } from "lucide-react";

interface TravelResultPanelProps {
  offers: TravelOffer[];
  hotels: HotelOffer[];
  intent: TravelIntent;
  onRefresh?: () => void;
}

type SortOption = "price" | "score" | "duration";
type HotelSortOption = "score" | "price" | "rating";

export function TravelResultPanel({ offers, hotels, intent, onRefresh }: TravelResultPanelProps) {
  const [sortBy, setSortBy] = useState<SortOption>("score");
  const [hotelSortBy, setHotelSortBy] = useState<HotelSortOption>("score");

  const hasFlights = offers.length > 0;
  const hasHotels = hotels.length > 0;

  if (!hasFlights && !hasHotels) return null;

  const sortedOffers = [...offers].sort((a, b) => {
    if (sortBy === "price") return a.price_usd - b.price_usd;
    if (sortBy === "duration") return a.duration_minutes - b.duration_minutes;
    return b.score - a.score;
  });

  const sortedHotels = [...hotels].sort((a, b) => {
    if (hotelSortBy === "price") return a.total_price - b.total_price;
    if (hotelSortBy === "rating") {
      const norm = (v: number | null | undefined) => (typeof v === "number" && Number.isFinite(v) ? v : -Infinity);
      return norm(b.star_rating) - norm(a.star_rating);
    }
    return b.score - a.score;
  });

  return (
    <div className="flex flex-col mt-4 w-full animate-in fade-in slide-in-from-bottom-4 duration-500 max-w-[800px]">

      {/* Shared toolbar — visible whenever there is any result */}
      {(hasFlights || hasHotels) && (
        <div className="flex flex-wrap items-center gap-3 mb-4 p-3 rounded-[16px] glass border-white/5">
          {/* Flight sort — only when flights present */}
          {hasFlights && (
            <div className="flex items-center gap-1 glass rounded-lg p-1 border-white/5">
              <Filter size={14} className="text-white/40 ml-1.5 mr-1" />
              {(["score", "price", "duration"] as SortOption[]).map((opt) => (
                <button
                  key={opt}
                  onClick={() => setSortBy(opt)}
                  aria-pressed={sortBy === opt}
                  className={`px-2.5 py-1 text-[11px] font-bold uppercase tracking-wider rounded-md transition-all ${
                    sortBy === opt
                      ? "bg-blue-500 text-white shadow-sm"
                      : "text-white/50 hover:text-white/80 hover:bg-white/5"
                  }`}
                >
                  {opt}
                </button>
              ))}
            </div>
          )}

          {/* Hotel sort — only when hotels present */}
          {hasHotels && (
            <div className="flex items-center gap-1 glass rounded-lg p-1 border-white/5">
              <Filter size={14} className="text-white/40 ml-1.5 mr-1" />
              {(["score", "price", "rating"] as HotelSortOption[]).map((opt) => (
                <button
                  key={opt}
                  onClick={() => setHotelSortBy(opt)}
                  aria-pressed={hotelSortBy === opt}
                  className={`px-2.5 py-1 text-[11px] font-bold uppercase tracking-wider rounded-md transition-all ${
                    hotelSortBy === opt
                      ? "bg-purple-500 text-white shadow-sm"
                      : "text-white/50 hover:text-white/80 hover:bg-white/5"
                  }`}
                >
                  {opt}
                </button>
              ))}
            </div>
          )}

          {/* Save Best — disabled when no flights (backend schema is flight-only) */}
          <button
            onClick={async () => {
              if (offers.length === 0) return;
              try {
                const token = localStorage.getItem("datachat_token");
                const headers: any = { "Content-Type": "application/json" };
                if (token) headers["Authorization"] = `Bearer ${token}`;
                const res = await fetch(process.env.NEXT_PUBLIC_API_URL + "/api/journeys", {
                  method: "POST",
                  headers,
                  body: JSON.stringify({ intent, offer: sortedOffers[0] })
                });
                if (!res.ok) throw new Error("Failed");
                alert("Journey saved successfully!");
              } catch (err) {
                alert("Failed to save journey");
              }
            }}
            disabled={!hasFlights}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg glass bg-green-500/10 text-green-500 hover:bg-green-500/20 text-[11px] font-bold uppercase tracking-wider transition-colors ${!hasFlights ? "pointer-events-none opacity-50" : ""}`}
            title={!hasFlights ? "Saving only supported for flights right now" : "Save this journey to history"}
          >
            Save Best
          </button>

          <button
            onClick={async () => {
              try {
                const token = localStorage.getItem("datachat_token");
                const headers: any = {};
                if (token) headers["Authorization"] = `Bearer ${token}`;
                const res = await fetch(process.env.NEXT_PUBLIC_API_URL + "/api/journeys/export", { headers });
                if (!res.ok) throw new Error("Failed");
                const blob = await res.blob();
                const url = URL.createObjectURL(blob);
                const a = document.createElement("a");
                a.href = url;
                a.download = "travel_journeys.xlsx";
                document.body.appendChild(a);
                a.click();
                a.remove();
                URL.revokeObjectURL(url);
              } catch (err) {
                alert("Failed to download itinerary");
              }
            }}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg glass bg-indigo-500/10 text-indigo-500 hover:bg-indigo-500/20 text-[11px] font-bold uppercase tracking-wider transition-colors"
            title="Download saved journeys as Excel"
          >
            Export Excel
          </button>

          {onRefresh && (
            <button
              onClick={onRefresh}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg glass hover:bg-white/5 text-[11px] font-bold uppercase tracking-wider transition-colors"
              style={{ color: "var(--color-text-primary)" }}
              title="Re-run search to get live prices"
            >
              <RefreshCw size={14} />
              Refresh
            </button>
          )}
        </div>
      )}

      {/* Flight header — identity only */}
      {hasFlights && (
        <div className="flex flex-wrap items-center gap-4 mb-4 p-4 rounded-[16px] glass bg-blue-500/5 border-blue-500/10">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-full bg-blue-500/10 flex items-center justify-center text-blue-500">
              <Plane size={20} strokeWidth={2.5} />
            </div>
            <div className="flex flex-col">
              <span className="text-[14px] font-bold" style={{ color: "var(--color-text-primary)" }}>
                {intent.origin} → {intent.destination}
              </span>
              <span className="text-[11px] font-medium opacity-70" style={{ color: "var(--color-text-secondary)" }}>
                {intent.departure_date} • {intent.passengers} pax • {intent.traveler_tier} tier
              </span>
            </div>
          </div>
        </div>
      )}

      {/* Flights Grid */}
      {hasFlights && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {sortedOffers.map((offer, index) => (
            <div key={offer.offer_id} className="relative">
              {sortBy === "score" && index === 0 && (
                <div className="absolute -top-2.5 right-4 z-10 px-2 py-0.5 rounded-full bg-amber-500 text-[10px] font-black text-amber-950 uppercase tracking-widest shadow-lg border border-amber-400">
                  Best Match
                </div>
              )}
              <div className={sortBy === "score" && index === 0 ? "ring-2 ring-amber-500/50 rounded-[20px]" : ""}>
                <TravelOfferCard offer={offer} />
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Hotels Section */}
      {hasHotels && (
        <div className="flex flex-col mt-6">
          {/* Hotel header — identity only */}
          <div className="flex flex-wrap items-center gap-4 mb-4 p-4 rounded-[16px] glass bg-purple-500/5 border-purple-500/10">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-full bg-purple-500/10 flex items-center justify-center text-purple-500">
                <Hotel size={20} strokeWidth={2.5} />
              </div>
              <div className="flex flex-col">
                <span className="text-[14px] font-bold" style={{ color: "var(--color-text-primary)" }}>
                  Hotels in {intent.destination}
                </span>
                <span className="text-[11px] font-medium opacity-70" style={{ color: "var(--color-text-secondary)" }}>
                  {intent.check_in_date ?? "TBD"} → {intent.check_out_date ?? "TBD"} • {intent.rooms} room{intent.rooms !== 1 ? "s" : ""} • {intent.guests} guest{intent.guests !== 1 ? "s" : ""}
                </span>
              </div>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {sortedHotels.map((hotel, index) => (
              <div key={hotel.hotel_id || `hotel-${index}`} className="relative">
                {hotelSortBy === "score" && index === 0 && (
                  <div className="absolute -top-2.5 right-4 z-10 px-2 py-0.5 rounded-full bg-amber-500 text-[10px] font-black text-amber-950 uppercase tracking-widest shadow-lg border border-amber-400">
                    Best Match
                  </div>
                )}
                <div className={hotelSortBy === "score" && index === 0 ? "ring-2 ring-amber-500/50 rounded-[20px]" : ""}>
                  <HotelOfferCard offer={hotel} />
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

    </div>
  );
}
