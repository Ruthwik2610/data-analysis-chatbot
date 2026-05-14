import React, { useMemo, useState } from "react";
import type { TravelOffer, TravelIntent, HotelOffer } from "@/lib/types";
import { api } from "@/lib/api";
import { TravelOfferCard } from "./TravelOfferCard";
import { HotelOfferCard } from "./HotelOfferCard";
import { RefreshCw, Plane, Filter, Hotel, ArrowLeft, ArrowRight, Download } from "lucide-react";

interface TravelResultPanelProps {
  offers: TravelOffer[];
  hotels: HotelOffer[];
  intent: TravelIntent;
  chatId?: string | null;
  onRefresh?: () => void;
}

type SortOption = "price" | "score" | "duration";
type HotelSortOption = "score" | "price" | "rating";
type Step = "flight" | "hotel" | "itinerary";

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

export function TravelResultPanel({ offers, hotels, intent, chatId, onRefresh }: TravelResultPanelProps) {
  const [sortBy, setSortBy] = useState<SortOption>("score");
  const [hotelSortBy, setHotelSortBy] = useState<HotelSortOption>("score");
  const [step, setStep] = useState<Step>(offers.length > 0 ? "flight" : "hotel");
  const [selectedFlightId, setSelectedFlightId] = useState<string | null>(null);
  const [selectedHotelId, setSelectedHotelId] = useState<string | null>(null);
  const [hotelSkipped, setHotelSkipped] = useState(false);
  const [downloadError, setDownloadError] = useState<string | null>(null);
  const [downloading, setDownloading] = useState(false);

  const hasFlights = offers.length > 0;
  const hasHotels = hotels.length > 0;

  const sortedOffers = useMemo(() => [...offers].sort((a, b) => {
    if (sortBy === "price") return a.price_usd - b.price_usd;
    if (sortBy === "duration") return a.duration_minutes - b.duration_minutes;
    return b.score - a.score;
  }), [offers, sortBy]);

  const sortedHotels = useMemo(() => [...hotels].sort((a, b) => {
    if (hotelSortBy === "price") return a.total_price - b.total_price;
    if (hotelSortBy === "rating") {
      const norm = (v: number | null | undefined) => (typeof v === "number" && Number.isFinite(v) ? v : -Infinity);
      return norm(b.star_rating) - norm(a.star_rating);
    }
    return b.score - a.score;
  }), [hotels, hotelSortBy]);

  if (!hasFlights && !hasHotels) return null;

  const selectedFlight = offers.find((offer) => offer.offer_id === selectedFlightId) || null;
  const selectedHotel = hotels.find((hotel) => hotel.hotel_id === selectedHotelId) || null;
  const hasMixedCurrencies = !!selectedFlight && !!selectedHotel && selectedFlight.currency !== selectedHotel.currency;
  const totalLabel = hasMixedCurrencies ? "Mixed currencies" : "Total";
  const totalValue = hasMixedCurrencies
    ? `${formatCurrency(selectedFlight.price_usd, selectedFlight.currency)} + ${formatCurrency(selectedHotel.total_price, selectedHotel.currency)}`
    : formatCurrency(
        (selectedFlight?.price_usd || 0) + (selectedHotel?.total_price || 0),
        selectedFlight?.currency || selectedHotel?.currency || "USD",
      );
  const canPersist = !!selectedFlight;

  const goNextFromFlight = () => setStep(hasHotels ? "hotel" : "itinerary");
  const goNextFromHotel = () => setStep("itinerary");
  const goBackFromHotel = () => setStep(hasFlights ? "flight" : "itinerary");
  const goBackFromItinerary = () => setStep(hasHotels ? "hotel" : "flight");

  const downloadItinerary = async () => {
    if (!selectedFlight) return;
    setDownloadError(null);
    setDownloading(true);
    try {
      const saved = await api.saveTravelJourney({
        chat_id: chatId ?? null,
        intent,
        offer: selectedFlight,
        hotel_offer: selectedHotel,
        status: "downloaded",
      });
      const blob = new Blob([JSON.stringify(saved, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `itinerary_${saved.id}.json`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch {
      setDownloadError("Could not download itinerary.");
    } finally {
      setDownloading(false);
    }
  };

  return (
    <div className="flex flex-col mt-4 w-full animate-in fade-in slide-in-from-bottom-4 duration-500 max-w-[800px]">
      <div className="flex flex-wrap items-center gap-3 mb-4 p-3 rounded-[16px] glass" style={{ border: "1px solid var(--color-border-secondary)" }}>
        {step === "flight" && hasFlights && (
          <SortControls
            options={["score", "price", "duration"]}
            value={sortBy}
            onChange={(value) => setSortBy(value as SortOption)}
          />
        )}
        {step === "hotel" && hasHotels && (
          <SortControls
            options={["score", "price", "rating"]}
            value={hotelSortBy}
            onChange={(value) => setHotelSortBy(value as HotelSortOption)}
          />
        )}
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

      {step === "flight" && (
        <>
          <SectionHeader
            icon={<Plane size={20} strokeWidth={2.5} />}
            title={`${intent.origin} → ${intent.destination}`}
            subtitle={`${intent.departure_date} • ${intent.passengers} pax • ${intent.traveler_tier} tier`}
          />
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {sortedOffers.map((offer, index) => (
              <div key={offer.offer_id} className="relative">
                {sortBy === "score" && index === 0 && <BestMatchBadge />}
                <TravelOfferCard
                  offer={offer}
                  selected={selectedFlightId === offer.offer_id}
                  selectLabel={`Select ${offer.airline} flight ${offer.origin} to ${offer.destination}`}
                  onSelect={() => setSelectedFlightId(offer.offer_id)}
                />
              </div>
            ))}
          </div>
          <WorkflowFooter>
            <button type="button" onClick={goNextFromFlight} disabled={!selectedFlight} className={actionButtonClass} style={primaryButtonStyle(!selectedFlight)}>
              Next
              <ArrowRight size={14} />
            </button>
          </WorkflowFooter>
        </>
      )}

      {step === "hotel" && (
        <>
          <SectionHeader
            icon={<Hotel size={20} strokeWidth={2.5} />}
            title={`Hotels in ${intent.destination}`}
            subtitle={`${intent.check_in_date ?? "TBD"} → ${intent.check_out_date ?? "TBD"} • ${intent.rooms} room${intent.rooms !== 1 ? "s" : ""} • ${intent.guests} guest${intent.guests !== 1 ? "s" : ""}`}
          />
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {sortedHotels.map((hotel, index) => (
              <div key={hotel.hotel_id || `hotel-${index}`} className="relative">
                {hotelSortBy === "score" && index === 0 && <BestMatchBadge />}
                <HotelOfferCard
                  offer={hotel}
                  selected={selectedHotelId === hotel.hotel_id}
                  selectLabel={`Select ${hotel.name}`}
                  onSelect={() => {
                    setSelectedHotelId(hotel.hotel_id);
                    setHotelSkipped(false);
                  }}
                />
              </div>
            ))}
          </div>
          <WorkflowFooter>
            {hasFlights && (
              <button type="button" onClick={goBackFromHotel} className={actionButtonClass} style={secondaryButtonStyle}>
                <ArrowLeft size={14} />
                Back
              </button>
            )}
            <button
              type="button"
              onClick={() => {
                setSelectedHotelId(null);
                setHotelSkipped(true);
                setStep("itinerary");
              }}
              className={actionButtonClass}
              style={secondaryButtonStyle}
            >
              Skip hotel
            </button>
            <button type="button" onClick={goNextFromHotel} disabled={!selectedHotel && !hotelSkipped} className={actionButtonClass} style={primaryButtonStyle(!selectedHotel && !hotelSkipped)}>
              Next
              <ArrowRight size={14} />
            </button>
          </WorkflowFooter>
        </>
      )}

      {step === "itinerary" && (
        <div className="flex flex-col gap-4 rounded-[16px] glass p-4" style={{ border: "1px solid var(--color-border-secondary)" }}>
          <div>
            <h3 className="text-[16px] font-bold" style={{ color: "var(--color-text-primary)" }}>Itinerary</h3>
            <p className="text-[12px] mt-1" style={{ color: "var(--color-text-secondary)" }}>
              {selectedFlight ? `${selectedFlight.airline} ${selectedFlight.origin} to ${selectedFlight.destination}` : "Flight required to save itinerary"}
            </p>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <SummaryTile label="Flight" value={selectedFlight ? formatCurrency(selectedFlight.price_usd, selectedFlight.currency) : "Not selected"} />
            <SummaryTile label="Hotel" value={selectedHotel ? formatCurrency(selectedHotel.total_price, selectedHotel.currency) : "Hotel skipped"} />
            <SummaryTile label={totalLabel} value={totalValue} />
          </div>
          <div className="flex flex-wrap gap-2">
            <button type="button" onClick={goBackFromItinerary} className={actionButtonClass} style={secondaryButtonStyle}>
              <ArrowLeft size={14} />
              Back
            </button>
            {selectedFlight && (
              <a href={selectedFlight.booking_redirect_url} target="_blank" rel="noopener noreferrer" className={actionButtonClass} style={secondaryButtonStyle}>
                Book flight
              </a>
            )}
            {selectedHotel && (
              <a href={selectedHotel.redirect_url} target="_blank" rel="noopener noreferrer" className={actionButtonClass} style={secondaryButtonStyle}>
                Book hotel
              </a>
            )}
            <button type="button" onClick={downloadItinerary} disabled={!canPersist || downloading} className={actionButtonClass} style={primaryButtonStyle(!canPersist || downloading)}>
              <Download size={14} />
              {downloading ? "Downloading" : "Download itinerary"}
            </button>
          </div>
          {downloadError && <p className="text-[12px]" style={{ color: "var(--color-text-warning)" }}>{downloadError}</p>}
        </div>
      )}
    </div>
  );
}

function SortControls({ options, value, onChange }: { options: string[]; value: string; onChange: (value: string) => void }) {
  return (
    <div className="flex items-center gap-1 glass rounded-lg p-1" style={{ border: "1px solid var(--color-border-secondary)" }}>
      <Filter size={14} className="ml-1.5 mr-1" style={{ color: "var(--color-text-tertiary)" }} />
      {options.map((opt) => (
        <button
          key={opt}
          onClick={() => onChange(opt)}
          aria-pressed={value === opt}
          className="px-2.5 py-1 text-[11px] font-bold uppercase tracking-wider rounded-md transition-all"
          style={{
            background: value === opt ? "var(--color-background-info)" : "transparent",
            color: value === opt ? "var(--color-text-info)" : "var(--color-text-secondary)",
          }}
        >
          {opt}
        </button>
      ))}
    </div>
  );
}

function SectionHeader({ icon, title, subtitle }: { icon: React.ReactNode; title: string; subtitle: string }) {
  return (
    <div className="flex flex-wrap items-center gap-4 mb-4 p-4 rounded-[16px] glass" style={{ border: "1px solid var(--color-border-secondary)" }}>
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 rounded-full flex items-center justify-center" style={{ background: "var(--color-background-info)", color: "var(--color-text-info)" }}>
          {icon}
        </div>
        <div className="flex flex-col">
          <span className="text-[14px] font-bold" style={{ color: "var(--color-text-primary)" }}>{title}</span>
          <span className="text-[11px] font-medium opacity-70" style={{ color: "var(--color-text-secondary)" }}>{subtitle}</span>
        </div>
      </div>
    </div>
  );
}

function BestMatchBadge() {
  return (
    <div className="absolute -top-2.5 right-4 z-10 px-2 py-0.5 rounded-full bg-amber-500 text-[10px] font-black text-amber-950 uppercase tracking-widest shadow-lg border border-amber-400">
      Best Match
    </div>
  );
}

function WorkflowFooter({ children }: { children: React.ReactNode }) {
  return <div className="flex flex-wrap justify-end gap-2 mt-4">{children}</div>;
}

function SummaryTile({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-[12px] p-3" style={{ background: "var(--color-background-elevated)", border: "1px solid var(--color-border-secondary)" }}>
      <div className="text-[10px] font-bold uppercase tracking-widest" style={{ color: "var(--color-text-tertiary)" }}>{label}</div>
      <div className="text-[14px] font-bold mt-1" style={{ color: "var(--color-text-primary)" }}>{value}</div>
    </div>
  );
}

const secondaryButtonStyle = {
  color: "var(--color-text-primary)",
  background: "var(--color-background-elevated)",
  border: "1px solid var(--color-border-secondary)",
};

const actionButtonClass = "inline-flex items-center justify-center gap-1.5 rounded-[10px] px-3 py-2 text-[12px] font-bold transition-colors active:scale-95";

const primaryButtonStyle = (disabled: boolean) => ({
  color: disabled ? "var(--color-text-tertiary)" : "var(--color-background-primary)",
  background: disabled ? "var(--color-background-elevated)" : "var(--color-text-info)",
  border: "1px solid var(--color-border-secondary)",
  opacity: disabled ? 0.6 : 1,
});
