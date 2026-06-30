import test from 'node:test';
import assert from 'node:assert/strict';

import {
  buildBookingHotelUrl,
  buildBookingLocationsUrl,
  buildBookingSearchUrl,
  normalizeBookingHotelResults,
  pickBookingDestination,
  searchBookingHotels,
} from './booking-hotels.js';

test('builds Booking.com RapidAPI hotel URLs', () => {
  assert.equal(
    buildBookingLocationsUrl('New York'),
    'https://booking-com.p.rapidapi.com/v1/hotels/locations?name=new+york&locale=en-gb',
  );
  assert.equal(
    buildBookingSearchUrl({
      dest_id: '-2601889',
      dest_type: 'city',
      check_in_date: '2026-09-18',
      check_out_date: '2026-09-20',
      guests: 2,
      rooms: 1,
      currency: 'AED',
    }),
    'https://booking-com.p.rapidapi.com/v1/hotels/search?checkout_date=2026-09-20&order_by=popularity&filter_by_currency=AED&room_number=1&dest_id=-2601889&dest_type=city&adults_number=2&checkin_date=2026-09-18&units=metric&locale=en-gb&page_number=0&include_adjacency=true',
  );
});

test('picks the first city destination from Booking locations', () => {
  const destination = pickBookingDestination([
    { dest_type: 'district', dest_id: 'abc', name: 'Central London' },
    { dest_type: 'city', dest_id: '-2601889', name: 'London' },
  ]);

  assert.deepEqual(destination, { dest_type: 'city', dest_id: '-2601889', name: 'London' });
});

test('normalizes Booking.com hotel search results into travel hotel offers', () => {
  const offers = normalizeBookingHotelResults(
    [
      {
        hotel_id: 1682114,
        hotel_name: 'London Backpackers',
        address: '8-10 Queens Parade',
        review_score: 8.1,
        class: 3,
        currency_code: 'GBP',
        min_total_price: 28.8,
        main_photo_url: 'https://example.com/photo.jpg',
        url: 'https://www.booking.com/hotel/gb/london-backpackers.html',
        composite_price_breakdown: {
          gross_amount: { value: 28.8, currency: 'GBP' },
        },
      },
      {
        hotel_id: 2,
        hotel_name: 'Missing Price',
      },
    ],
    {
      check_in_date: '2026-09-18',
      check_out_date: '2026-09-20',
      rooms: 1,
      guests: 2,
    },
  );

  assert.equal(offers.length, 1);
  assert.equal(offers[0].hotel_id, 'booking_1682114');
  assert.equal(offers[0].name, 'London Backpackers');
  assert.equal(offers[0].price_per_night, 14.4);
  assert.equal(offers[0].total_price, 28.8);
  assert.equal(offers[0].currency, 'GBP');
  assert.match(offers[0].redirect_url, /checkin=2026-09-18/);
});

test('searches Booking.com locations then hotels with RapidAPI headers', async () => {
  const calls = [];
  const result = await searchBookingHotels(
    {
      destination_iata: 'LHR',
      check_in_date: '2026-09-18',
      check_out_date: '2026-09-20',
      rooms: 1,
      guests: 1,
    },
    {
      apiKey: 'rapid-key',
      fetchImpl: async (url, options) => {
        calls.push({ url, headers: options.headers });
        if (url.includes('/locations?')) {
          return new Response(JSON.stringify([
            { dest_type: 'city', dest_id: '-2601889', name: 'London' },
          ]), { status: 200, headers: { 'Content-Type': 'application/json' } });
        }
        return new Response(JSON.stringify({
          result: [
            {
              hotel_id: 1682114,
              hotel_name: 'London Backpackers',
              min_total_price: 28.8,
              currency_code: 'GBP',
              url: 'https://www.booking.com/hotel/gb/london-backpackers.html',
            },
          ],
        }), { status: 200, headers: { 'Content-Type': 'application/json' } });
      },
    },
  );

  assert.equal(calls.length, 2);
  assert.equal(calls[0].headers['x-rapidapi-key'], 'rapid-key');
  assert.equal(calls[0].headers['x-rapidapi-host'], 'booking-com.p.rapidapi.com');
  assert.equal(result.length, 1);
  assert.equal(result[0].hotel_id, 'booking_1682114');
});

