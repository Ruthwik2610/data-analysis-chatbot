import 'dotenv/config';
import express from 'express';
import cors from 'cors';
import { Server } from '@modelcontextprotocol/sdk/server/index.js';
import { SSEServerTransport } from '@modelcontextprotocol/sdk/server/sse.js';
import { ListToolsRequestSchema, CallToolRequestSchema } from '@modelcontextprotocol/sdk/types.js';
import { Duffel } from '@duffel/api';

// ── Config ──────────────────────────────────────────────────────────────────
const PORT = parseInt(process.env.PORT || '8083', 10);
const HOST = process.env.HOST || '0.0.0.0';
const DUFFEL_TOKEN = process.env.DUFFEL_API_TOKEN || '';
// The installed @duffel/api SDK defaults to apiVersion 'v1', which Duffel
// has deprecated ("Unsupported version" 400). Pin to v2 explicitly. Override
// with DUFFEL_API_VERSION if needed.
const DUFFEL_API_VERSION = process.env.DUFFEL_API_VERSION || 'v2';

if (!DUFFEL_TOKEN) {
  console.warn('[Duffel Bridge] WARNING: DUFFEL_API_TOKEN is not set. API calls will fail.');
}

// ── Duffel Client ────────────────────────────────────────────────────────────
function createDuffelClient() {
  return new Duffel({ token: DUFFEL_TOKEN, apiVersion: DUFFEL_API_VERSION });
}

// ── Tool Definitions ─────────────────────────────────────────────────────────
const TOOLS = [
  {
    name: 'list_airports',
    description: 'Search airports by city name or keyword. Returns IATA codes, city, and country. Use this first to resolve city names to IATA codes before searching flights.',
    inputSchema: {
      type: 'object',
      properties: {
        keyword: {
          type: 'string',
          description: 'City name, airport name, or partial keyword to search (e.g. "London", "Heathrow", "JFK")',
        },
      },
      required: ['keyword'],
    },
  },
  {
    name: 'search_flights',
    description: 'Search for available flights between two airports. Returns up to 10 offers sorted by price (cheapest first). Always use IATA codes for origin and destination.',
    inputSchema: {
      type: 'object',
      properties: {
        origin: { type: 'string', description: 'Origin IATA airport code (e.g. LHR, JFK, BOM)' },
        destination: { type: 'string', description: 'Destination IATA airport code (e.g. JFK, LHR, SYD)' },
        departure_date: { type: 'string', description: 'Departure date in YYYY-MM-DD format' },
        return_date: { type: 'string', description: 'Return date in YYYY-MM-DD format for round trips (omit for one-way)' },
        passengers: { type: 'number', description: 'Number of adult passengers (default: 1)', default: 1 },
        cabin_class: {
          type: 'string',
          description: 'Cabin class preference',
          enum: ['economy', 'premium_economy', 'business', 'first'],
          default: 'economy',
        },
        max_price_usd: { type: 'number', description: 'Maximum total price in USD (optional filter)' },
      },
      required: ['origin', 'destination', 'departure_date'],
    },
  },
  {
    name: 'get_offer_details',
    description: 'Retrieve full, refreshed details for a specific Duffel offer ID. Always call this before showing a final price to the user — offer prices can change.',
    inputSchema: {
      type: 'object',
      properties: {
        offer_id: { type: 'string', description: 'The Duffel offer ID (e.g. off_0000A...) from a previous search_flights call' },
      },
      required: ['offer_id'],
    },
  },
  {
    name: 'get_cheapest_offer',
    description: 'Search flights and return only the single cheapest offer. Ideal for quick policy-budget checks. Returns one offer or an error if none found within the max price.',
    inputSchema: {
      type: 'object',
      properties: {
        origin: { type: 'string', description: 'Origin IATA airport code' },
        destination: { type: 'string', description: 'Destination IATA airport code' },
        departure_date: { type: 'string', description: 'Departure date in YYYY-MM-DD format' },
        return_date: { type: 'string', description: 'Return date (optional, for round trips)' },
        passengers: { type: 'number', description: 'Number of adult passengers', default: 1 },
        cabin_class: { type: 'string', description: 'Cabin class', default: 'economy' },
        max_price_usd: { type: 'number', description: 'Maximum total price in USD (required for budget checking)' },
      },
      required: ['origin', 'destination', 'departure_date'],
    },
  },
];

// ── Helper: build booking redirect URL ─────────────────────────────────────
function buildRedirectUrl(origin, destination, departure_date, passengers = 1, cabin_class = 'economy', return_date = null) {
  const params = new URLSearchParams({
    origin,
    destination,
    departure_date,
    passengers: String(passengers),
    cabin_class,
  });
  if (return_date) params.set('return_date', return_date);
  return `https://app.duffel.com/search?${params.toString()}`;
}

// ── Helper: parse duration string (ISO 8601 PT2H30M) to minutes ─────────────
function parseDurationMinutes(duration) {
  if (!duration) return 0;
  const match = duration.match(/PT(?:(\d+)H)?(?:(\d+)M)?/);
  if (!match) return 0;
  return (parseInt(match[1] || '0') * 60) + parseInt(match[2] || '0');
}

// ── Helper: shape a raw Duffel offer into our standard offer object ──────────
function shapeOffer(offer, searchParams = {}) {
  const slice = offer.slices?.[0];
  const segs = slice?.segments || [];
  const firstSeg = segs[0] || {};
  const lastSeg = segs[segs.length - 1] || {};

  return {
    offer_id: offer.id,
    airline: offer.owner?.name || 'Unknown Airline',
    airline_iata: offer.owner?.iata_code || '',
    origin: firstSeg.origin?.iata_code || searchParams.origin || '',
    destination: lastSeg.destination?.iata_code || searchParams.destination || '',
    departure_at: firstSeg.departing_at || '',
    arrival_at: lastSeg.arriving_at || '',
    duration_minutes: parseDurationMinutes(slice?.duration),
    stops: Math.max(0, segs.length - 1),
    cabin_class: firstSeg.passengers?.[0]?.cabin_class_marketing_name
      || firstSeg.passengers?.[0]?.cabin_class
      || searchParams.cabin_class
      || 'economy',
    price_usd: parseFloat(offer.total_amount || '0'),
    currency: offer.total_currency || 'USD',
    expires_at: offer.expires_at || null,
    booking_redirect_url: buildRedirectUrl(
      firstSeg.origin?.iata_code || searchParams.origin || '',
      lastSeg.destination?.iata_code || searchParams.destination || '',
      searchParams.departure_date || '',
      searchParams.passengers || 1,
      searchParams.cabin_class || 'economy',
      searchParams.return_date || null,
    ),
  };
}

// ── Tool Handlers ────────────────────────────────────────────────────────────
async function handleListAirports({ keyword }) {
  if (!keyword || typeof keyword !== 'string' || !keyword.trim()) {
    return JSON.stringify({ error: 'keyword is required' });
  }
  try {
    const duffel = createDuffelClient();
    // Duffel's Places "suggestions" API is the text-search endpoint.
    // duffel.airports.list does not accept a query parameter.
    const response = await duffel.suggestions.list({ query: keyword.trim() });
    const places = response.data || [];
    const out = [];
    for (const p of places) {
      if (out.length >= 10) break;
      if (p.type === 'airport') {
        out.push({
          iata_code: p.iata_code,
          name: p.name,
          city_name: p.city_name || p.city?.name || '',
          country_name: p.iata_country_code || p.city?.iata_country_code || '',
        });
      } else if (p.type === 'city') {
        // Expand the city into its constituent airports so the LLM gets IATA codes
        // it can pass to search_flights.
        for (const a of (p.airports || [])) {
          if (out.length >= 10) break;
          out.push({
            iata_code: a.iata_code,
            name: a.name,
            city_name: p.name || a.city_name || '',
            country_name: p.iata_country_code || '',
          });
        }
      }
    }
    return JSON.stringify(out, null, 2);
  } catch (err) {
    return JSON.stringify({ error: `Airport search failed: ${err.message}` });
  }
}

async function handleSearchFlights(args) {
  const {
    origin,
    destination,
    departure_date,
    return_date,
    passengers = 1,
    cabin_class = 'economy',
    max_price_usd,
  } = args;

  try {
    const duffel = createDuffelClient();

    const slices = [{ origin, destination, departure_date }];
    if (return_date) {
      slices.push({ origin: destination, destination: origin, departure_date: return_date });
    }

    const offerRequest = await duffel.offerRequests.create({
      slices,
      passengers: Array.from({ length: passengers }, () => ({ type: 'adult' })),
      cabin_class,
      return_offers: true,
    });

    let offers = offerRequest.data?.offers || [];

    // Apply max price filter
    if (max_price_usd) {
      offers = offers.filter(o => parseFloat(o.total_amount || '0') <= max_price_usd);
    }

    // Sort by price ascending
    offers.sort((a, b) => parseFloat(a.total_amount || '0') - parseFloat(b.total_amount || '0'));

    // Take top 10
    const topOffers = offers.slice(0, 10).map(o => shapeOffer(o, args));

    return JSON.stringify(topOffers, null, 2);
  } catch (err) {
    // Duffel's SDK throws a DuffelError whose .message is empty; the real
    // detail lives on .errors / .meta. Surface those so the LLM and the
    // server logs see something actionable.
    const detail =
      err?.errors?.[0]?.message ||
      err?.errors?.[0]?.title ||
      err?.message ||
      err?.toString?.() ||
      'unknown error';
    const code = err?.errors?.[0]?.code || err?.meta?.status || '';
    console.error('[Duffel Bridge] search_flights failed:', code, detail);
    const redirectUrl = buildRedirectUrl(origin, destination, departure_date, passengers, cabin_class, return_date);
    return JSON.stringify({
      error: `Flight search failed: ${detail}`,
      code,
      redirect_url: redirectUrl,
    });
  }
}

async function handleGetOfferDetails({ offer_id }) {
  try {
    const duffel = createDuffelClient();
    const response = await duffel.offers.get(offer_id);
    const offer = response.data;
    return JSON.stringify(shapeOffer(offer), null, 2);
  } catch (err) {
    return JSON.stringify({ error: `Offer details failed: ${err.message}` });
  }
}

async function handleGetCheapestOffer(args) {
  const { max_price_usd } = args;
  try {
    const results = await handleSearchFlights(args);
    const offers = JSON.parse(results);

    if (offers.error) return results;
    if (!Array.isArray(offers) || offers.length === 0) {
      return JSON.stringify({
        error: 'No flights found for this route and date.',
        redirect_url: buildRedirectUrl(args.origin, args.destination, args.departure_date),
      });
    }

    const filtered = max_price_usd
      ? offers.filter(o => o.price_usd <= max_price_usd)
      : offers;

    if (filtered.length === 0) {
      return JSON.stringify({
        error: `No offers found within budget of $${max_price_usd}. Cheapest available: $${offers[0].price_usd}`,
        cheapest_available: offers[0],
        redirect_url: offers[0].booking_redirect_url,
      });
    }

    return JSON.stringify(filtered[0], null, 2);
  } catch (err) {
    return JSON.stringify({ error: `Cheapest offer search failed: ${err.message}` });
  }
}

// ── MCP Server Factory ───────────────────────────────────────────────────────
function buildMCPServer() {
  const server = new Server(
    { name: 'Duffel Flights MCP', version: '1.0.0' },
    { capabilities: { tools: {} } },
  );

  server.setRequestHandler(ListToolsRequestSchema, async () => ({ tools: TOOLS }));

  server.setRequestHandler(CallToolRequestSchema, async (request) => {
    const { name, arguments: args } = request.params;

    let textContent;
    switch (name) {
      case 'list_airports':
        textContent = await handleListAirports(args || {});
        break;
      case 'search_flights':
        textContent = await handleSearchFlights(args || {});
        break;
      case 'get_offer_details':
        textContent = await handleGetOfferDetails(args || {});
        break;
      case 'get_cheapest_offer':
        textContent = await handleGetCheapestOffer(args || {});
        break;
      default:
        textContent = JSON.stringify({ error: `Unknown tool: ${name}` });
    }

    return {
      content: [{ type: 'text', text: textContent }],
    };
  });

  return server;
}

// ── Express App + SSE Transport ──────────────────────────────────────────────
const app = express();
app.use(cors());
app.use(express.json());

const sseTransports = new Map();

app.get('/sse', async (req, res) => {
  console.log('[Duffel Bridge] New SSE connection at /sse');
  const transport = new SSEServerTransport('/message', res);
  sseTransports.set(transport.sessionId, transport);

  // Heartbeat: write an SSE comment line every 15s. Without this, an idle MCP
  // session triggers httpx.ReadTimeout on the Python client (~5-8 min) and the
  // backend marks the connector as errored.
  const heartbeat = setInterval(() => {
    try {
      if (!res.writableEnded) res.write(': ping\n\n');
    } catch (_) {
      clearInterval(heartbeat);
    }
  }, 15000);

  res.on('close', () => {
    clearInterval(heartbeat);
    sseTransports.delete(transport.sessionId);
    console.log(`[Duffel Bridge] SSE session ${transport.sessionId} closed`);
  });

  const server = buildMCPServer();
  await server.connect(transport);
  console.log(`[Duffel Bridge] SSE transport ready (session: ${transport.sessionId})`);
});

app.post('/message', async (req, res) => {
  const sessionId = req.query.sessionId;
  const transport = sseTransports.get(sessionId);
  if (transport) {
    await transport.handlePostMessage(req, res, req.body);
  } else {
    res.status(404).json({ error: 'No active SSE session for this ID' });
  }
});

app.get('/health', (_req, res) => {
  res.json({
    status: 'ok',
    tools: TOOLS.length,
    tool_names: TOOLS.map(t => t.name),
    duffel_connected: !!DUFFEL_TOKEN,
    port: PORT,
  });
});

// ── Start ────────────────────────────────────────────────────────────────────
app.listen(PORT, HOST, () => {
  console.log('─'.repeat(60));
  console.log('  Duffel Flights MCP Bridge');
  console.log('─'.repeat(60));
  console.log(`  SSE endpoint : http://${HOST}:${PORT}/sse`);
  console.log(`  Health check : http://${HOST}:${PORT}/health`);
  console.log(`  Tools        : ${TOOLS.map(t => t.name).join(', ')}`);
  console.log(`  Duffel token : ${DUFFEL_TOKEN ? DUFFEL_TOKEN.slice(0, 20) + '...' : 'NOT SET ⚠️'}`);
  console.log('─'.repeat(60));
});
