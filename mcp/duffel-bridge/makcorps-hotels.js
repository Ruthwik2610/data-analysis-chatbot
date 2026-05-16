const MAKCORPS_BASE_URL = 'https://api.makcorps.com';

const IATA_CITY_NAMES = {
  ATL: 'atlanta',
  BOM: 'mumbai',
  DEL: 'delhi',
  DXB: 'dubai',
  HYD: 'hyderabad',
  JFK: 'new york',
  LAX: 'los angeles',
  LHR: 'london',
  ORD: 'chicago',
  RUH: 'riyadh',
  SFO: 'san francisco',
};

export function lookupIataCityName(iata) {
  const code = String(iata || '').trim().toUpperCase();
  return IATA_CITY_NAMES[code] || code.toLowerCase();
}

export function buildMakcorpsFreeUrl(city) {
  return `${MAKCORPS_BASE_URL}/free/${encodeURIComponent(String(city || '').trim().toLowerCase())}`;
}

export function buildMakcorpsMappingUrl({ destination_city, apiKey }) {
  const params = new URLSearchParams({
    api_key: apiKey,
    name: `hotel ${String(destination_city || '').trim().toLowerCase()}`,
  });
  return `${MAKCORPS_BASE_URL}/mapping?${params.toString()}`;
}

export function buildMakcorpsHotelUrl({
  hotelId,
  check_in_date,
  check_out_date,
  rooms = 1,
  guests = 1,
  apiKey,
}) {
  const params = new URLSearchParams({
    hotelid: String(hotelId),
    adults: String(guests),
    rooms: String(rooms),
    checkin: check_in_date,
    checkout: check_out_date,
    api_key: apiKey,
  });
  return `${MAKCORPS_BASE_URL}/hotel?${params.toString()}`;
}

function nightsBetween(checkInDate, checkOutDate) {
  const checkIn = new Date(checkInDate);
  const checkOut = new Date(checkOutDate);
  const nights = Math.floor((checkOut - checkIn) / (1000 * 60 * 60 * 24));
  return Number.isFinite(nights) ? Math.max(1, nights) : 1;
}

function parsePrice(value) {
  const amount = parseFloat(String(value ?? '').replace(/[^0-9.]/g, ''));
  return Number.isFinite(amount) ? amount : null;
}

function formatMoney(value) {
  return parseFloat(value.toFixed(2));
}

function cheapestVendorPrice(vendors = []) {
  let cheapest = null;
  for (const vendor of vendors) {
    for (let index = 1; index <= 20; index += 1) {
      const price = parsePrice(vendor[`price${index}`]);
      if (price == null) continue;
      const tax = parsePrice(vendor[`tax${index}`]) || 0;
      const total = price + tax;
      const vendorName = vendor[`vendor${index}`] || 'Makcorps';
      if (!cheapest || total < cheapest.total) {
        cheapest = { total, vendor: vendorName };
      }
    }
  }
  return cheapest;
}

function iterMakcorpsHotelRows(payload) {
  if (!Array.isArray(payload)) return [];
  return payload
    .filter(row => Array.isArray(row) && row.length >= 2)
    .map(([hotel, vendors]) => ({
      hotel: hotel || {},
      vendors: Array.isArray(vendors) ? vendors : [],
    }));
}

export function normalizeMakcorpsFreeResponse(payload, args = {}) {
  const {
    destination_iata,
    destination_city = lookupIataCityName(destination_iata),
    check_in_date,
    check_out_date,
    rooms = 1,
    guests = 1,
    max_price_usd,
  } = args;
  const nights = nightsBetween(check_in_date, check_out_date);
  const offers = [];

  for (const { hotel, vendors } of iterMakcorpsHotelRows(payload)) {
    const hotelId = String(hotel.hotelId || hotel.hotel_id || hotel.id || '').trim();
    const name = String(hotel.hotelName || hotel.name || '').trim();
    if (!hotelId || !name) continue;

    const cheapest = cheapestVendorPrice(vendors);
    if (!cheapest) continue;
    if (max_price_usd != null && cheapest.total > max_price_usd) continue;

    const query = new URLSearchParams({
      q: `${name} ${destination_city || destination_iata || ''}`.trim(),
      checkin: check_in_date || '',
      checkout: check_out_date || '',
      adults: String(guests),
    });

    offers.push({
      hotel_id: `makcorps_${hotelId}`,
      name,
      address: destination_city || destination_iata || '',
      star_rating: null,
      review_score: null,
      photo_url: '',
      price_per_night: formatMoney(cheapest.total / nights),
      total_price: formatMoney(cheapest.total),
      currency: 'USD',
      check_in_date,
      check_out_date,
      rooms,
      guests,
      redirect_url: `https://www.google.com/travel/hotels?${query.toString()}`,
      provider: 'makcorps',
      vendor: cheapest.vendor,
    });
  }

  offers.sort((a, b) => a.total_price - b.total_price);
  return offers.slice(0, 10);
}

export function normalizeMakcorpsMappingResponse(payload) {
  if (!Array.isArray(payload)) return [];
  const seen = new Set();
  const hotels = [];

  for (const item of payload) {
    if (item?.type !== 'HOTEL') continue;
    const hotelId = String(item.document_id || '').trim();
    if (!hotelId || seen.has(hotelId)) continue;
    seen.add(hotelId);

    const details = item.details || {};
    const name = String(details.name || item.name || '').split(',')[0].trim();
    if (!name) continue;
    const address = [
      details.address,
      details.parent_name,
      details.grandparent_name,
    ].filter(Boolean).join(', ');

    hotels.push({
      hotel_id: hotelId,
      name,
      address,
      source_url: item.url || '',
    });
  }

  return hotels;
}

export function normalizeMakcorpsHotelPrice(payload, nights = 1) {
  const comparisons = Array.isArray(payload?.comparison)
    ? payload.comparison.flat(Number.POSITIVE_INFINITY).filter(item => item && typeof item === 'object')
    : [];

  let cheapest = null;
  for (const vendor of comparisons) {
    for (let index = 1; index <= 30; index += 1) {
      const totalPrice = parsePrice(vendor[`Totalprice${index}`]);
      const nightlyPrice = parsePrice(vendor[`price${index}`]);
      if (totalPrice == null && nightlyPrice == null) continue;
      const tax = parsePrice(vendor[`tax${index}`]) || 0;
      const total = totalPrice ?? ((nightlyPrice * nights) + tax);
      const vendorName = vendor[`vendor${index}`] || 'Makcorps';
      if (!cheapest || total < cheapest.total_price) {
        cheapest = {
          vendor: vendorName,
          total_price: formatMoney(total),
          price_per_night: formatMoney(total / nights),
        };
      }
    }
  }
  return cheapest;
}

async function fetchJson(fetchImpl, url, options = {}) {
  const response = await fetchImpl(url, options);
  const text = await response.text();
  let payload;
  try {
    payload = JSON.parse(text);
  } catch {
    return { ok: false, status: response.status, payload: null, nonJson: true };
  }
  return { ok: response.ok, status: response.status, payload };
}

async function searchMakcorpsHotelPrices(args, options) {
  const apiKey = options.apiKey || process.env.MAKCORPS_API_KEY || '';
  if (!apiKey) {
    return { error: 'MAKCORPS_API_KEY is not configured' };
  }

  const fetchImpl = options.fetchImpl || fetch;
  const destination_city = lookupIataCityName(args.destination_iata);
  const mapping = await fetchJson(fetchImpl, buildMakcorpsMappingUrl({ destination_city, apiKey }));
  if (!mapping.ok || !Array.isArray(mapping.payload)) {
    return {
      error: mapping.payload?.message || `Makcorps hotel mapping failed with HTTP ${mapping.status}`,
      code: mapping.status,
    };
  }

  const lookupLimit = Number.parseInt(options.lookupLimit || process.env.MAKCORPS_HOTEL_LOOKUP_LIMIT || '3', 10);
  const candidates = normalizeMakcorpsMappingResponse(mapping.payload).slice(0, Math.max(1, lookupLimit));
  if (candidates.length === 0) {
    return { error: `No Makcorps hotel IDs found for ${destination_city}` };
  }

  const nights = nightsBetween(args.check_in_date, args.check_out_date);
  const offers = [];
  for (const hotel of candidates) {
    const priceUrl = buildMakcorpsHotelUrl({
      hotelId: hotel.hotel_id,
      check_in_date: args.check_in_date,
      check_out_date: args.check_out_date,
      rooms: args.rooms || 1,
      guests: args.guests || 1,
      apiKey,
    });
    const price = await fetchJson(fetchImpl, priceUrl);
    if (!price.ok || !price.payload) continue;
    const cheapest = normalizeMakcorpsHotelPrice(price.payload, nights);
    if (!cheapest) continue;
    if (args.max_price_usd != null && cheapest.total_price > args.max_price_usd) continue;

    const query = new URLSearchParams({
      q: `${hotel.name} ${destination_city}`.trim(),
      checkin: args.check_in_date || '',
      checkout: args.check_out_date || '',
      adults: String(args.guests || 1),
    });

    offers.push({
      hotel_id: `makcorps_${hotel.hotel_id}`,
      name: hotel.name,
      address: hotel.address || destination_city,
      star_rating: null,
      review_score: null,
      photo_url: '',
      price_per_night: cheapest.price_per_night,
      total_price: cheapest.total_price,
      currency: 'USD',
      check_in_date: args.check_in_date,
      check_out_date: args.check_out_date,
      rooms: args.rooms || 1,
      guests: args.guests || 1,
      redirect_url: hotel.source_url || `https://www.google.com/travel/hotels?${query.toString()}`,
      provider: 'makcorps',
      vendor: cheapest.vendor,
    });
  }

  offers.sort((a, b) => a.total_price - b.total_price);
  return offers.length > 0 ? offers.slice(0, 10) : { error: `No priced Makcorps hotels found for ${destination_city}` };
}

export async function searchMakcorpsHotels(args, options = {}) {
  const apiKey = options.apiKey || process.env.MAKCORPS_API_KEY || '';
  const jwt = options.jwt || process.env.MAKCORPS_JWT || '';
  if (!apiKey && !jwt) {
    return { error: 'MAKCORPS_API_KEY or MAKCORPS_JWT is not configured' };
  }

  const destination_city = lookupIataCityName(args.destination_iata);
  if (apiKey) {
    return searchMakcorpsHotelPrices(args, options);
  }

  const result = await fetchJson(options.fetchImpl || fetch, buildMakcorpsFreeUrl(destination_city), {
    headers: { Authorization: `JWT ${jwt}` },
  });
  if (result.nonJson) {
    return { error: 'Makcorps hotel search returned non-JSON response', code: result.status };
  }
  if (!result.ok) {
    return {
      error: result.payload?.error || result.payload?.message || `Makcorps hotel search failed with HTTP ${result.status}`,
      code: result.status,
    };
  }

  const offers = normalizeMakcorpsFreeResponse(result.payload, { ...args, destination_city });
  if (offers.length === 0) {
    return { error: `No Makcorps hotels found for ${destination_city}` };
  }
  return offers;
}
