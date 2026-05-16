import { lookupIataCityName } from './makcorps-hotels.js';

const BOOKING_BASE_URL = 'https://booking-com.p.rapidapi.com/v1/hotels';
const RAPIDAPI_HOST = 'booking-com.p.rapidapi.com';

function money(value) {
  const num = Number.parseFloat(String(value ?? '').replace(/[^0-9.]/g, ''));
  return Number.isFinite(num) ? Number.parseFloat(num.toFixed(2)) : null;
}

function nightsBetween(checkInDate, checkOutDate) {
  const checkIn = new Date(checkInDate);
  const checkOut = new Date(checkOutDate);
  const nights = Math.floor((checkOut - checkIn) / (1000 * 60 * 60 * 24));
  return Number.isFinite(nights) ? Math.max(1, nights) : 1;
}

export function buildBookingLocationsUrl(city, locale = 'en-gb') {
  const params = new URLSearchParams({
    name: String(city || '').trim().toLowerCase(),
    locale,
  });
  return `${BOOKING_BASE_URL}/locations?${params.toString()}`;
}

export function buildBookingSearchUrl({
  dest_id,
  dest_type,
  check_in_date,
  check_out_date,
  guests = 1,
  rooms = 1,
  currency = 'USD',
  locale = 'en-gb',
}) {
  const params = new URLSearchParams({
    checkout_date: check_out_date,
    order_by: 'popularity',
    filter_by_currency: currency,
    room_number: String(rooms),
    dest_id: String(dest_id),
    dest_type: String(dest_type),
    adults_number: String(guests),
    checkin_date: check_in_date,
    units: 'metric',
    locale,
    page_number: '0',
    include_adjacency: 'true',
  });
  return `${BOOKING_BASE_URL}/search?${params.toString()}`;
}

export function buildBookingHotelUrl(url, args = {}) {
  if (!url) return '';
  const out = new URL(url);
  out.searchParams.set('checkin', args.check_in_date || '');
  out.searchParams.set('checkout', args.check_out_date || '');
  out.searchParams.set('group_adults', String(args.guests || 1));
  out.searchParams.set('no_rooms', String(args.rooms || 1));
  return out.toString();
}

export function pickBookingDestination(locations) {
  if (!Array.isArray(locations)) return null;
  return locations.find(item => item.dest_type === 'city') || locations[0] || null;
}

function totalFromHotel(hotel) {
  const price = hotel?.composite_price_breakdown || {};
  return money(
    price.all_inclusive_amount?.value
      ?? price.all_inclusive_amount_hotel_currency?.value
      ?? price.gross_amount?.value
      ?? hotel.min_total_price
      ?? hotel.price,
  );
}

function currencyFromHotel(hotel) {
  const price = hotel?.composite_price_breakdown || {};
  return (
    price.all_inclusive_amount?.currency
    || price.all_inclusive_amount_hotel_currency?.currency
    || price.gross_amount?.currency
    || hotel.currency_code
    || 'USD'
  );
}

export function normalizeBookingHotelResults(results, args = {}) {
  if (!Array.isArray(results)) return [];
  const nights = nightsBetween(args.check_in_date, args.check_out_date);
  const offers = [];

  for (const hotel of results) {
    const hotelId = hotel.hotel_id || hotel.id;
    const name = hotel.hotel_name || hotel.hotel_name_trans || hotel.name;
    const total = totalFromHotel(hotel);
    if (!hotelId || !name || total == null) continue;

    const currency = currencyFromHotel(hotel);
    if (args.max_price_usd != null && currency === 'USD' && total > args.max_price_usd) continue;

    offers.push({
      hotel_id: `booking_${hotelId}`,
      name,
      address: hotel.address || hotel.address_trans || hotel.city || '',
      star_rating: hotel.class ?? null,
      review_score: hotel.review_score ?? null,
      photo_url: hotel.main_photo_url || hotel.max_photo_url || '',
      price_per_night: money(total / nights),
      total_price: total,
      currency,
      check_in_date: args.check_in_date,
      check_out_date: args.check_out_date,
      rooms: args.rooms || 1,
      guests: args.guests || 1,
      redirect_url: buildBookingHotelUrl(hotel.url || hotel.hotel_url, args),
      provider: 'booking_com_rapidapi',
    });
  }

  offers.sort((a, b) => a.total_price - b.total_price);
  return offers.slice(0, 10);
}

async function fetchJson(fetchImpl, url, headers) {
  const response = await fetchImpl(url, { headers });
  const text = await response.text();
  let payload;
  try {
    payload = JSON.parse(text);
  } catch {
    return { ok: false, status: response.status, payload: null, nonJson: true };
  }
  return { ok: response.ok, status: response.status, payload };
}

export async function searchBookingHotels(args, options = {}) {
  const apiKey = options.apiKey || process.env.RAPIDAPI_BOOKING_KEY || '';
  if (!apiKey) return { error: 'RAPIDAPI_BOOKING_KEY is not configured' };

  const headers = {
    'x-rapidapi-key': apiKey,
    'x-rapidapi-host': RAPIDAPI_HOST,
  };
  const fetchImpl = options.fetchImpl || fetch;
  const locale = options.locale || process.env.BOOKING_LOCALE || 'en-gb';
  const currency = options.currency || process.env.BOOKING_CURRENCY || 'USD';
  const city = lookupIataCityName(args.destination_iata);

  const locations = await fetchJson(fetchImpl, buildBookingLocationsUrl(city, locale), headers);
  if (!locations.ok || !Array.isArray(locations.payload)) {
    return {
      error: locations.payload?.message || `Booking.com location search failed with HTTP ${locations.status}`,
      code: locations.status,
    };
  }

  const destination = pickBookingDestination(locations.payload);
  if (!destination?.dest_id || !destination?.dest_type) {
    return { error: `No Booking.com hotel destination found for ${city}` };
  }

  const search = await fetchJson(fetchImpl, buildBookingSearchUrl({
    dest_id: destination.dest_id,
    dest_type: destination.dest_type,
    check_in_date: args.check_in_date,
    check_out_date: args.check_out_date,
    guests: args.guests || 1,
    rooms: args.rooms || 1,
    currency,
    locale,
  }), headers);
  if (!search.ok || !search.payload) {
    return {
      error: search.payload?.message || `Booking.com hotel search failed with HTTP ${search.status}`,
      code: search.status,
    };
  }

  const offers = normalizeBookingHotelResults(search.payload.result || [], args);
  return offers.length > 0 ? offers : { error: `No priced Booking.com hotels found for ${city}` };
}

