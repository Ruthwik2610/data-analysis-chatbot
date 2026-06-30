import React, { useMemo, useState } from "react";
import type { TravelOffer, TravelIntent, HotelOffer } from "@/lib/types";
import { api } from "@/lib/api";
import { TravelOfferCard } from "./TravelOfferCard";
import { HotelOfferCard } from "./HotelOfferCard";
import { RefreshCw, Plane, Filter, Hotel, ArrowLeft, ArrowRight, Download } from "lucide-react";
import jsPDF from "jspdf";
import autoTable from "jspdf-autotable";

interface TravelResultPanelProps {
  offers: TravelOffer[];
  hotels: HotelOffer[];
  intent: TravelIntent;
  chatId?: string | null;
  onRefresh?: () => void;
}

type SortOption = "price" | "score" | "duration";
type HotelSortOption = "score" | "price" | "rating";
type Step = "outbound_flight" | "return_flight" | "hotel" | "itinerary";

const RATES_PER_USD: Record<string, number> = {
  USD: 1,
  AED: 3.6725,
  AUD: 1.52,
  CAD: 1.36,
  EUR: 0.92,
  GBP: 0.79,
  INR: 83,
  JPY: 156,
  SAR: 3.75,
  ZAR: 18.5,
};

const DOWNLOAD_CURRENCIES = ["USD", "INR", "AED", "EUR", "GBP", "ZAR"];

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

const convertFromUsd = (amount: number, currency: string) => amount * (RATES_PER_USD[currency] ?? 1);

const getHotelUsdTotal = (hotel: HotelOffer | null) => {
  if (!hotel) return 0;
  if (typeof hotel.total_price_usd === "number" && Number.isFinite(hotel.total_price_usd)) return hotel.total_price_usd;
  if ((hotel.currency || "USD").toUpperCase() === "USD") return hotel.total_price;
  const rate = RATES_PER_USD[(hotel.currency || "").toUpperCase()];
  return rate ? hotel.total_price / rate : 0;
};

const getOutboundKey = (o: TravelOffer) => `${o.airline}-${o.departure_at}-${o.arrival_at}`;

export function TravelResultPanel({ offers, hotels, intent, chatId, onRefresh }: TravelResultPanelProps) {
  const [sortBy, setSortBy] = useState<SortOption>("score");
  const [hotelSortBy, setHotelSortBy] = useState<HotelSortOption>("score");
  const [step, setStep] = useState<Step>(offers.length > 0 ? "outbound_flight" : "hotel");
  
  const [selectedOutboundKey, setSelectedOutboundKey] = useState<string | null>(null);
  const [selectedOutboundOfferId, setSelectedOutboundOfferId] = useState<string | null>(null);
  const [selectedOfferId, setSelectedOfferId] = useState<string | null>(null);
  const [selectedHotelId, setSelectedHotelId] = useState<string | null>(null);
  const [hotelSkipped, setHotelSkipped] = useState(false);
  const [downloadError, setDownloadError] = useState<string | null>(null);
  const [downloading, setDownloading] = useState(false);
  const [downloadCurrency, setDownloadCurrency] = useState("USD");

  const hasFlights = offers.length > 0;
  const hasHotels = hotels.length > 0;
  const shouldShowHotelStep = intent.wants_hotels || hasHotels;

  // Process Outbound Offers
  const sortedOutboundOffers = useMemo(() => {
    const outboundGroupMap = new Map<string, TravelOffer>();
    for (const offer of offers) {
      const key = getOutboundKey(offer);
      if (!outboundGroupMap.has(key)) {
        outboundGroupMap.set(key, offer);
      } else {
        // Keep the cheapest offer for this outbound flight
        if (offer.price_usd < outboundGroupMap.get(key)!.price_usd) {
          outboundGroupMap.set(key, offer);
        }
      }
    }
    const uniqueOutboundOffers = Array.from(outboundGroupMap.values());
    return [...uniqueOutboundOffers].sort((a, b) => {
      if (sortBy === "price") return a.price_usd - b.price_usd;
      if (sortBy === "duration") return a.duration_minutes - b.duration_minutes;
      return b.score - a.score;
    });
  }, [offers, sortBy]);

  // Process Return Offers based on selected outbound flight
  const sortedReturnOffers = useMemo(() => {
    if (!selectedOutboundKey) return [];
    const matchingReturnOffers = offers.filter(o => getOutboundKey(o) === selectedOutboundKey && !!o.return_slice);
    return [...matchingReturnOffers].sort((a, b) => {
      if (sortBy === "price") return a.price_usd - b.price_usd;
      if (sortBy === "duration") return (a.return_slice?.duration_minutes ?? 0) - (b.return_slice?.duration_minutes ?? 0);
      return b.score - a.score;
    });
  }, [offers, selectedOutboundKey, sortBy]);

  const sortedHotels = useMemo(() => [...hotels].sort((a, b) => {
    if (hotelSortBy === "price") return a.total_price - b.total_price;
    if (hotelSortBy === "rating") {
      const norm = (v: number | null | undefined) => (typeof v === "number" && Number.isFinite(v) ? v : -Infinity);
      return norm(b.star_rating) - norm(a.star_rating);
    }
    return b.score - a.score;
  }), [hotels, hotelSortBy]);

  if (!hasFlights && !hasHotels) return null;

  const selectedFlight = offers.find((offer) => offer.offer_id === selectedOfferId) || null;
  const selectedOutboundFlight = offers.find((offer) => offer.offer_id === selectedOutboundOfferId) || null;
  const selectedHotel = hotels.find((hotel) => hotel.hotel_id === selectedHotelId) || null;
  const hasSelectedReturn = !!selectedFlight?.return_slice;
  const selectedFlightPriceUsd = selectedFlight
    ? selectedFlight.price_usd + (hasSelectedReturn ? (selectedOutboundFlight?.price_usd || 0) : 0)
    : selectedOutboundFlight?.price_usd || 0;
  const selectedHotelTotalUsd = getHotelUsdTotal(selectedHotel);
  const totalUsd = selectedFlightPriceUsd + selectedHotelTotalUsd;
  const totalValue = formatCurrency(totalUsd, "USD");
  const downloadTotalValue = formatCurrency(convertFromUsd(totalUsd, downloadCurrency), downloadCurrency);
  const downloadCurrencyOptions = Array.from(new Set([
    ...DOWNLOAD_CURRENCIES,
    selectedHotel?.currency?.toUpperCase(),
    selectedFlight?.original_currency?.toUpperCase(),
  ].filter(Boolean) as string[])).filter((currency) => RATES_PER_USD[currency]);
  const canPersist = !!selectedFlight;
  const persistedFlight = selectedFlight && selectedOutboundFlight && hasSelectedReturn
    ? {
        ...selectedFlight,
        outbound_offer_id: selectedOutboundFlight.offer_id,
        return_offer_id: selectedFlight.offer_id,
        price_usd: selectedFlightPriceUsd,
        currency: "USD",
      }
    : selectedFlight;

  const goNextFromOutbound = () => {
    const options = offers.filter(o => getOutboundKey(o) === selectedOutboundKey);
    const hasReturnOptions = options.some(o => !!o.return_slice);
    
    if (hasReturnOptions) {
      setStep("return_flight");
    } else {
      // It's a one-way trip
      const cheapest = [...options].sort((a, b) => a.price_usd - b.price_usd)[0];
      if (cheapest) setSelectedOfferId(cheapest.offer_id);
      setStep(shouldShowHotelStep ? "hotel" : "itinerary");
    }
  };

  const goBackFromReturn = () => {
    setSelectedOfferId(null);
    setStep("outbound_flight");
  };

  const goNextFromReturn = () => {
    setStep(shouldShowHotelStep ? "hotel" : "itinerary");
  };

  const goBackFromHotel = () => {
    if (hasFlights) {
      if (selectedFlight && selectedFlight.return_slice) {
        setStep("return_flight");
      } else {
        setStep("outbound_flight");
      }
    } else {
      setStep("itinerary");
    }
  };

  const goNextFromHotel = () => setStep("itinerary");
  const goBackFromItinerary = () => setStep(shouldShowHotelStep ? "hotel" : (hasFlights ? (selectedFlight?.return_slice ? "return_flight" : "outbound_flight") : "outbound_flight"));

  const downloadItinerary = async () => {
    if (!canPersist || !selectedFlight) return;
    setDownloadError(null);
    setDownloading(true);
    try {
      const saved = await api.saveTravelJourney({
        chat_id: chatId ?? null,
        intent,
        offer: persistedFlight || selectedFlight,
        hotel_offer: selectedHotel,
        status: "downloaded",
      });

      // Generate PDF
      const doc = new jsPDF();
      doc.setFont("helvetica", "bold");
      doc.setFontSize(22);
      doc.text("Travel Itinerary", 14, 22);

      doc.setFontSize(11);
      doc.setFont("helvetica", "normal");
      doc.text(`Reference: ${saved.id}`, 14, 30);
      doc.text(`Date Generated: ${new Date().toLocaleDateString()}`, 14, 36);

      let currentY = 46;

      if (selectedFlight) {
        doc.setFontSize(14);
        doc.setFont("helvetica", "bold");
        doc.text("Flight Details", 14, currentY);
        currentY += 6;

        autoTable(doc, {
          startY: currentY,
          head: [["Leg", "Airline", "Route", "Departure", "Arrival", "Duration"]],
          body: [
            [
              "Outbound",
              selectedFlight.airline,
              `${selectedFlight.origin} -> ${selectedFlight.destination}`,
              new Date(selectedFlight.departure_at).toLocaleString(),
              new Date(selectedFlight.arrival_at).toLocaleString(),
              `${Math.floor(selectedFlight.duration_minutes / 60)}h ${selectedFlight.duration_minutes % 60}m`
            ],
            ...(selectedFlight.return_slice ? [[
              "Return",
              selectedFlight.return_slice.airline,
              `${selectedFlight.return_slice.origin} -> ${selectedFlight.return_slice.destination}`,
              new Date(selectedFlight.return_slice.departure_at).toLocaleString(),
              new Date(selectedFlight.return_slice.arrival_at).toLocaleString(),
              `${Math.floor(selectedFlight.return_slice.duration_minutes / 60)}h ${selectedFlight.return_slice.duration_minutes % 60}m`
            ]] : [])
          ],
          theme: 'grid',
          headStyles: { fillColor: [41, 128, 185] },
          margin: { top: 10 }
        });
        currentY = (doc as any).lastAutoTable.finalY + 15;
      }

      if (selectedHotel) {
        doc.setFontSize(14);
        doc.setFont("helvetica", "bold");
        doc.text("Hotel Details", 14, currentY);
        currentY += 6;

        autoTable(doc, {
          startY: currentY,
          head: [["Hotel", "Check In", "Check Out", "Rooms", "Guests", "Rating"]],
          body: [
            [
              selectedHotel.name,
              selectedHotel.check_in_date,
              selectedHotel.check_out_date,
              selectedHotel.rooms.toString(),
              selectedHotel.guests.toString(),
              selectedHotel.star_rating ? `${selectedHotel.star_rating} Stars` : "N/A"
            ]
          ],
          theme: 'grid',
          headStyles: { fillColor: [39, 174, 96] },
          margin: { top: 10 }
        });
        currentY = (doc as any).lastAutoTable.finalY + 15;
      }

      doc.setFontSize(14);
      doc.setFont("helvetica", "bold");
      doc.text("Pricing Summary", 14, currentY);
      currentY += 6;

      autoTable(doc, {
        startY: currentY,
        head: [["Item", "Price"]],
        body: [
          ...(selectedFlight ? [["Flight Total", formatCurrency(convertFromUsd(selectedFlightPriceUsd, downloadCurrency), downloadCurrency)]] : []),
          ...(selectedHotel ? [["Hotel Total", formatCurrency(convertFromUsd(selectedHotelTotalUsd, downloadCurrency), downloadCurrency)]] : []),
          ["Grand Total", downloadTotalValue]
        ],
          theme: 'plain',
          styles: { fontStyle: 'bold' },
          margin: { top: 10 }
      });

      doc.save(`itinerary_${saved.id}.pdf`);
    } catch {
      setDownloadError("Could not download itinerary.");
    } finally {
      setDownloading(false);
    }
  };

  return (
    <div className="flex flex-col mt-4 w-full animate-in fade-in slide-in-from-bottom-4 duration-500 max-w-[800px]">
      <div className="flex flex-wrap items-center gap-3 mb-4 p-3 rounded-[16px] glass" style={{ border: "1px solid var(--color-border-secondary)" }}>
        {(step === "outbound_flight" || step === "return_flight") && hasFlights && (
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

      {step === "outbound_flight" && (
        <>
          <SectionHeader
            icon={<Plane size={20} strokeWidth={2.5} />}
            title={`${intent.origin} → ${intent.destination} (Outbound)`}
            subtitle={`${intent.departure_date} • ${intent.passengers} pax • ${intent.traveler_tier} tier`}
          />
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {sortedOutboundOffers.map((offer, index) => (
              <div key={getOutboundKey(offer)} className="relative">
                {sortBy === "score" && index === 0 && <BestMatchBadge />}
                <TravelOfferCard
                  offer={offer}
                  mode="outbound_only"
                  selected={selectedOutboundKey === getOutboundKey(offer)}
                  selectLabel={`Select outbound flight to ${offer.destination}`}
                  onSelect={() => {
                    setSelectedOutboundKey(getOutboundKey(offer));
                    setSelectedOutboundOfferId(offer.offer_id);
                    setSelectedOfferId(null);
                    setSelectedHotelId(null);
                    setHotelSkipped(false);
                  }}
                />
              </div>
            ))}
          </div>
          <WorkflowFooter>
            <button type="button" onClick={goNextFromOutbound} disabled={!selectedOutboundKey} className={actionButtonClass} style={primaryButtonStyle(!selectedOutboundKey)}>
              Next
              <ArrowRight size={14} />
            </button>
          </WorkflowFooter>
        </>
      )}

      {step === "return_flight" && (
        <>
          <SectionHeader
            icon={<Plane size={20} strokeWidth={2.5} className="rotate-180" />}
            title={`${intent.destination} → ${intent.origin} (Return)`}
            subtitle={`${intent.return_date || intent.departure_date} • ${intent.passengers} pax • ${intent.traveler_tier} tier`}
          />
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {sortedReturnOffers.map((offer, index) => (
              <div key={offer.offer_id} className="relative">
                {sortBy === "score" && index === 0 && <BestMatchBadge />}
                <TravelOfferCard
                  offer={offer}
                  mode="return_only"
                  selected={selectedOfferId === offer.offer_id}
                  selectLabel={`Select return flight to ${offer.origin}`}
                  onSelect={() => {
                    setSelectedOfferId(offer.offer_id);
                    setSelectedHotelId(null);
                    setHotelSkipped(false);
                  }}
                />
              </div>
            ))}
          </div>
          <WorkflowFooter>
            <button type="button" onClick={goBackFromReturn} className={actionButtonClass} style={secondaryButtonStyle}>
              <ArrowLeft size={14} />
              Back
            </button>
            <button type="button" onClick={goNextFromReturn} disabled={!selectedOfferId} className={actionButtonClass} style={primaryButtonStyle(!selectedOfferId)}>
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
          {!hasHotels && (
            <div className="rounded-[12px] p-4" style={{ background: "var(--color-background-elevated)", border: "1px solid var(--color-border-secondary)" }}>
              <p className="text-[13px] font-medium" style={{ color: "var(--color-text-secondary)" }}>
                No hotel options returned for this trip.
              </p>
            </div>
          )}
          <WorkflowFooter>
            {hasFlights && (
              <button type="button" onClick={goBackFromHotel} className={actionButtonClass} style={secondaryButtonStyle}>
                <ArrowLeft size={14} />
                Back
              </button>
            )}
            {hasHotels ? (
              <>
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
              </>
            ) : (
              <button
                type="button"
                onClick={() => {
                  setSelectedHotelId(null);
                  setHotelSkipped(true);
                  setStep("itinerary");
                }}
                className={actionButtonClass}
                style={primaryButtonStyle(false)}
              >
                Continue without hotel
                <ArrowRight size={14} />
              </button>
            )}
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
            <SummaryTile label="Flight" value={selectedFlight ? formatCurrency(selectedFlightPriceUsd, "USD") : "Not selected"} />
            <SummaryTile label="Hotel" value={selectedHotel ? formatCurrency(selectedHotel.total_price, selectedHotel.currency) : "Hotel skipped"} />
            <SummaryTile label="Total" value={totalValue} />
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-[minmax(180px,240px)_1fr] gap-3 items-end">
            <label className="flex flex-col gap-1 text-[11px] font-bold uppercase tracking-wider" style={{ color: "var(--color-text-tertiary)" }}>
              Download currency
              <select
                value={downloadCurrency}
                onChange={(event) => setDownloadCurrency(event.target.value)}
                className="rounded-[10px] px-3 py-2 text-[13px] font-bold outline-none"
                style={{
                  color: "var(--color-text-primary)",
                  background: "var(--color-background-elevated)",
                  border: "1px solid var(--color-border-secondary)",
                }}
              >
                {downloadCurrencyOptions.map((currency) => (
                  <option key={currency} value={currency}>{currency}</option>
                ))}
              </select>
            </label>
            <SummaryTile label="Download total" value={downloadTotalValue} />
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
              {downloading ? "Downloading" : "Download PDF itinerary"}
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
