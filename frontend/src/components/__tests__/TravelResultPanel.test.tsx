import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { TravelResultPanel } from "../TravelResultPanel";
import type { HotelOffer, TravelIntent, TravelOffer } from "@/lib/types";
import autoTable from "jspdf-autotable";

vi.mock("jspdf", () => {
  return {
    default: vi.fn().mockImplementation(function () {
      return {
      setFont: vi.fn(),
      setFontSize: vi.fn(),
      text: vi.fn(),
      save: vi.fn(),
      lastAutoTable: { finalY: 100 }
      };
    })
  };
});
vi.mock("jspdf-autotable", () => {
  return {
    default: vi.fn()
  };
});

const intent: TravelIntent = {
  origin: "SFO",
  destination: "JFK",
  departure_date: "2026-06-01",
  return_date: "2026-06-05",
  passengers: 1,
  cabin_class: "economy",
  traveler_tier: "standard",
  budget_limit_usd: 1200,
  check_in_date: "2026-06-01",
  check_out_date: "2026-06-05",
  rooms: 1,
  guests: 1,
  wants_flights: true,
  wants_hotels: true,
};

const offers: TravelOffer[] = [
  {
    offer_id: "flight_1",
    airline: "United",
    airline_iata: "UA",
    origin: "SFO",
    destination: "JFK",
    departure_at: "2026-06-01T08:00:00Z",
    arrival_at: "2026-06-01T16:30:00Z",
    duration_minutes: 330,
    stops: 0,
    cabin_class: "economy",
    price_usd: 410,
    currency: "USD",
    policy_compliant: true,
    policy_violation_reason: null,
    booking_redirect_url: "https://book.example.com/flight_1",
    expires_at: null,
    return_slice: {
      origin: "JFK",
      destination: "SFO",
      departure_at: "2026-06-05T15:00:00Z",
      arrival_at: "2026-06-05T19:00:00Z",
      duration_minutes: 360,
      stops: 0,
      airline: "United",
      airline_iata: "UA",
    },
    score: 95,
  },
  {
    offer_id: "flight_2",
    airline: "Delta",
    airline_iata: "DL",
    origin: "SFO",
    destination: "JFK",
    departure_at: "2026-06-01T10:00:00Z",
    arrival_at: "2026-06-01T18:30:00Z",
    duration_minutes: 330,
    stops: 0,
    cabin_class: "economy",
    price_usd: 430,
    currency: "USD",
    policy_compliant: true,
    policy_violation_reason: null,
    booking_redirect_url: "https://book.example.com/flight_2",
    expires_at: null,
    return_slice: {
      origin: "JFK",
      destination: "SFO",
      departure_at: "2026-06-05T16:00:00Z",
      arrival_at: "2026-06-05T20:00:00Z",
      duration_minutes: 360,
      stops: 0,
      airline: "Delta",
      airline_iata: "DL",
    },
    score: 85,
  },
];

const hotels: HotelOffer[] = [
  {
    hotel_id: "hotel_1",
    name: "Hudson Hotel",
    address: "123 Manhattan Ave",
    star_rating: 4,
    review_score: 8.8,
    photo_url: "",
    price_per_night: 180,
    total_price: 720,
    currency: "USD",
    check_in_date: "2026-06-01",
    check_out_date: "2026-06-05",
    rooms: 1,
    guests: 1,
    redirect_url: "https://book.example.com/hotel_1",
    policy_compliant: true,
    policy_violation_reason: null,
    score: 92,
  },
];

describe("TravelResultPanel workflow", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("shows outbound flight, then return flight, then hotel selection", () => {
    render(<TravelResultPanel offers={offers} hotels={hotels} intent={intent} />);

    // Outbound Step
    expect(screen.getAllByRole("button", { name: "Select outbound flight to JFK" }).length).toBeGreaterThan(0);
    fireEvent.click(screen.getAllByRole("button", { name: "Select outbound flight to JFK" })[0]);
    fireEvent.click(screen.getByRole("button", { name: "Next" }));

    // Return Step
    expect(screen.getByText(/Return/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Select return flight to SFO" })).toBeInTheDocument();
    fireEvent.click(screen.getAllByRole("button", { name: "Select return flight to SFO" })[0]);
    fireEvent.click(screen.getByRole("button", { name: "Next" }));

    // Hotel Step
    expect(screen.getByText("Hotels in JFK")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Skip hotel" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Select Hudson Hotel" })).toHaveTextContent("Select");
  });

  it("only shows valid return flight choices for the selected outbound flight", () => {
    const oneWaySameOutbound = {
      ...offers[0],
      offer_id: "flight_without_return",
      price_usd: 300,
      return_slice: null,
    };
    const roundTripSameOutbound = {
      ...offers[0],
      offer_id: "flight_with_return",
      price_usd: 410,
    };

    render(<TravelResultPanel offers={[oneWaySameOutbound, roundTripSameOutbound]} hotels={hotels} intent={intent} />);

    fireEvent.click(screen.getByRole("button", { name: "Select outbound flight to JFK" }));
    fireEvent.click(screen.getByRole("button", { name: "Next" }));

    expect(screen.queryByText("SFO → JFK (Outbound)")).not.toBeInTheDocument();
    expect(screen.queryByText("$300")).not.toBeInTheDocument();
    expect(screen.getByText("$410")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Select return flight to SFO" }));
    fireEvent.click(screen.getByRole("button", { name: "Next" }));

    expect(screen.getByText("Hotels in JFK")).toBeInTheDocument();
  });

  it("shows the hotel step when hotels were requested but no hotel offers returned", () => {
    render(<TravelResultPanel offers={offers} hotels={[]} intent={intent} />);

    fireEvent.click(screen.getAllByRole("button", { name: "Select outbound flight to JFK" })[0]);
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    fireEvent.click(screen.getAllByRole("button", { name: "Select return flight to SFO" })[0]);
    fireEvent.click(screen.getByRole("button", { name: "Next" }));

    expect(screen.getByText("Hotels in JFK")).toBeInTheDocument();
    expect(screen.getByText("No hotel options returned for this trip.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Continue without hotel" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Continue without hotel" }));
    expect(screen.getByText("Itinerary")).toBeInTheDocument();
  });

  it("shows booking redirects only on the itinerary step", () => {
    render(<TravelResultPanel offers={offers} hotels={hotels} intent={intent} />);

    fireEvent.click(screen.getAllByRole("button", { name: "Select outbound flight to JFK" })[0]);
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    fireEvent.click(screen.getAllByRole("button", { name: "Select return flight to SFO" })[0]);
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    fireEvent.click(screen.getByRole("button", { name: "Select Hudson Hotel" }));
    fireEvent.click(screen.getByRole("button", { name: "Next" }));

    expect(screen.getByText("Itinerary")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Book flight" })).toHaveAttribute("href", offers[0].booking_redirect_url);
    expect(screen.getByRole("link", { name: "Book hotel" })).toHaveAttribute("href", hotels[0].redirect_url);
    expect(screen.getByRole("button", { name: "Download PDF itinerary" })).toBeInTheDocument();
  });

  it("can skip hotel and continue to itinerary", () => {
    render(<TravelResultPanel offers={offers} hotels={hotels} intent={intent} />);

    fireEvent.click(screen.getAllByRole("button", { name: "Select outbound flight to JFK" })[0]);
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    fireEvent.click(screen.getAllByRole("button", { name: "Select return flight to SFO" })[0]);
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    fireEvent.click(screen.getByRole("button", { name: "Skip hotel" }));

    expect(screen.getByText("Itinerary")).toBeInTheDocument();
    expect(screen.getByText("Hotel skipped")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Book hotel" })).not.toBeInTheDocument();
  });

  it("goes directly to itinerary when no hotels are available", () => {
    render(<TravelResultPanel offers={offers} hotels={[]} intent={{ ...intent, wants_hotels: false }} />);

    fireEvent.click(screen.getAllByRole("button", { name: "Select outbound flight to JFK" })[0]);
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    fireEvent.click(screen.getAllByRole("button", { name: "Select return flight to SFO" })[0]);
    fireEvent.click(screen.getByRole("button", { name: "Next" }));

    expect(screen.getByText("Itinerary")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Book flight" })).toHaveAttribute("href", offers[0].booking_redirect_url);
    expect(screen.queryByText("Hotels in JFK")).not.toBeInTheDocument();
  });

  it("lets hotel-only results reach itinerary with hotel booking but disabled download", () => {
    render(<TravelResultPanel offers={[]} hotels={hotels} intent={{ ...intent, wants_flights: false }} />);

    fireEvent.click(screen.getByRole("button", { name: "Select Hudson Hotel" }));
    fireEvent.click(screen.getByRole("button", { name: "Next" }));

    expect(screen.getByText("Itinerary")).toBeInTheDocument();
    expect(screen.getByText("Flight required to save itinerary")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Book flight" })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Book hotel" })).toHaveAttribute("href", hotels[0].redirect_url);
    expect(screen.getByRole("button", { name: "Download PDF itinerary" })).toBeDisabled();
  });

  it("does not save a hotel-only itinerary when download is clicked", () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    render(<TravelResultPanel offers={[]} hotels={hotels} intent={{ ...intent, wants_flights: false }} />);

    fireEvent.click(screen.getByRole("button", { name: "Select Hudson Hotel" }));
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    fireEvent.click(screen.getByRole("button", { name: "Download PDF itinerary" }));

    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("clears stale hotel selection when changing the selected flight path", () => {
    render(<TravelResultPanel offers={offers} hotels={hotels} intent={intent} />);

    fireEvent.click(screen.getAllByRole("button", { name: "Select outbound flight to JFK" })[0]);
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    fireEvent.click(screen.getAllByRole("button", { name: "Select return flight to SFO" })[0]);
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    fireEvent.click(screen.getByRole("button", { name: "Select Hudson Hotel" }));

    fireEvent.click(screen.getByRole("button", { name: "Back" }));
    fireEvent.click(screen.getByRole("button", { name: "Back" }));
    fireEvent.click(screen.getAllByRole("button", { name: "Select outbound flight to JFK" })[1]);
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    fireEvent.click(screen.getAllByRole("button", { name: "Select return flight to SFO" })[0]);
    fireEvent.click(screen.getByRole("button", { name: "Next" }));

    expect(screen.getByRole("button", { name: "Select Hudson Hotel" })).toHaveTextContent(/^Select$/);
    expect(screen.getByRole("button", { name: "Next" })).toBeDisabled();
  });

  it("combines mixed-currency selections through normalized USD totals", () => {
    const euroHotel = { ...hotels[0], currency: "EUR", total_price: 720, total_price_usd: 790 };
    render(<TravelResultPanel offers={offers} hotels={[euroHotel]} intent={intent} />);

    fireEvent.click(screen.getAllByRole("button", { name: "Select outbound flight to JFK" })[0]);
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    fireEvent.click(screen.getAllByRole("button", { name: "Select return flight to SFO" })[0]);
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    fireEvent.click(screen.getByRole("button", { name: "Select Hudson Hotel" }));
    fireEvent.click(screen.getByRole("button", { name: "Next" }));

    expect(screen.getByText("Total")).toBeInTheDocument();
    expect(screen.getAllByText("$1,610").length).toBeGreaterThan(0);
    expect(screen.queryByText("Mixed currencies")).not.toBeInTheDocument();
  });

  it("lets the user switch itinerary download currency", async () => {
    const saved = {
      id: "journey_123",
      status: "downloaded",
      downloaded_at: "2026-05-14T00:00:00Z",
      total_price_usd: 1130,
      currency: "USD",
      flight_offer: offers[0],
      hotel_offer: hotels[0],
      flight_offer_json: offers[0],
      hotel_offer_json: hotels[0],
    };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: true,
      json: async () => saved,
    }));

    render(<TravelResultPanel offers={offers} hotels={hotels} intent={intent} chatId="chat_1" />);

    fireEvent.click(screen.getAllByRole("button", { name: "Select outbound flight to JFK" })[0]);
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    fireEvent.click(screen.getAllByRole("button", { name: "Select return flight to SFO" })[0]);
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    fireEvent.click(screen.getByRole("button", { name: "Select Hudson Hotel" }));
    fireEvent.click(screen.getByRole("button", { name: "Next" }));

    fireEvent.change(screen.getByLabelText("Download currency"), { target: { value: "EUR" } });

    expect(screen.getByText("Download total")).toBeInTheDocument();
    expect(screen.getAllByText("€1,417").length).toBeGreaterThan(0);

    fireEvent.click(screen.getByRole("button", { name: "Download PDF itinerary" }));

    await waitFor(() => expect(autoTable).toHaveBeenCalled());
    const pricingCall = vi.mocked(autoTable).mock.calls.find(([, options]) => {
      const body = (options as any).body as string[][];
      return body?.some((row) => row[0] === "Grand Total");
    });
    expect(pricingCall).toBeTruthy();
    expect((pricingCall?.[1] as any).body).toContainEqual(["Grand Total", "€1,417"]);
  });

  it("includes both selected outbound and return card prices in the itinerary total", () => {
    const americanOffers: TravelOffer[] = [
      {
        ...offers[0],
        offer_id: "american_outbound_low_return",
        airline: "American Airlines",
        airline_iata: "AA",
        price_usd: 314,
        return_slice: {
          ...offers[0].return_slice!,
          airline: "American Airlines",
          airline_iata: "AA",
          departure_at: "2026-06-05T11:00:00Z",
        },
      },
      {
        ...offers[0],
        offer_id: "american_outbound_selected_return",
        airline: "American Airlines",
        airline_iata: "AA",
        price_usd: 334,
        return_slice: {
          ...offers[0].return_slice!,
          airline: "American Airlines",
          airline_iata: "AA",
          departure_at: "2026-06-05T13:00:00Z",
        },
      },
    ];

    render(<TravelResultPanel offers={americanOffers} hotels={[]} intent={{ ...intent, wants_hotels: false }} />);

    fireEvent.click(screen.getByRole("button", { name: "Select outbound flight to JFK" }));
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    fireEvent.click(screen.getAllByRole("button", { name: "Select return flight to SFO" })[1]);
    fireEvent.click(screen.getByRole("button", { name: "Next" }));

    expect(screen.getAllByText("$648").length).toBeGreaterThan(0);
  });

  it("shows a simple error when itinerary download save fails", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: false,
      text: async () => "database token secret stack trace",
    }));

    render(<TravelResultPanel offers={offers} hotels={hotels} intent={intent} chatId="chat_1" />);

    fireEvent.click(screen.getAllByRole("button", { name: "Select outbound flight to JFK" })[0]);
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    fireEvent.click(screen.getAllByRole("button", { name: "Select return flight to SFO" })[0]);
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    fireEvent.click(screen.getByRole("button", { name: "Select Hudson Hotel" }));
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    fireEvent.click(screen.getByRole("button", { name: "Download PDF itinerary" }));

    expect(await screen.findByText("Could not download itinerary.")).toBeInTheDocument();
    expect(screen.queryByText(/token secret|stack trace/i)).not.toBeInTheDocument();
  });

  it("saves before downloading the itinerary PDF", async () => {
    const saved = {
      id: "journey_123",
      status: "downloaded",
      downloaded_at: "2026-05-14T00:00:00Z",
      total_price_usd: 1130,
      currency: "USD",
      flight_offer: offers[0],
      hotel_offer: hotels[0],
      flight_offer_json: offers[0],
      hotel_offer_json: hotels[0],
    };
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => saved,
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<TravelResultPanel offers={offers} hotels={hotels} intent={intent} chatId="chat_1" />);

    fireEvent.click(screen.getAllByRole("button", { name: "Select outbound flight to JFK" })[0]);
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    fireEvent.click(screen.getAllByRole("button", { name: "Select return flight to SFO" })[0]);
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    fireEvent.click(screen.getByRole("button", { name: "Select Hudson Hotel" }));
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    fireEvent.click(screen.getByRole("button", { name: "Download PDF itinerary" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/api/journeys"),
      expect.objectContaining({
        method: "POST",
        body: expect.any(String),
      }),
    ));
    const body = JSON.parse(fetchMock.mock.calls[0][1].body);
    expect(body).toMatchObject({
      chat_id: "chat_1",
      status: "downloaded",
      offer: { offer_id: "flight_1" },
      hotel_offer: { hotel_id: "hotel_1" },
    });
  });
});
