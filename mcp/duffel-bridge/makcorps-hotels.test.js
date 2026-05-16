import test from 'node:test';
import assert from 'node:assert/strict';

import {
  buildMakcorpsFreeUrl,
  buildMakcorpsHotelUrl,
  buildMakcorpsMappingUrl,
  lookupIataCityName,
  normalizeMakcorpsFreeResponse,
  normalizeMakcorpsHotelPrice,
  normalizeMakcorpsMappingResponse,
  searchMakcorpsHotels,
} from './makcorps-hotels.js';

test('maps common airport codes to city names for Makcorps city search', () => {
  assert.equal(lookupIataCityName('JFK'), 'new york');
  assert.equal(lookupIataCityName('lhr'), 'london');
  assert.equal(lookupIataCityName('RUH'), 'riyadh');
  assert.equal(lookupIataCityName('ZZZ'), 'zzz');
});

test('builds Makcorps free endpoint URL from city name', () => {
  assert.equal(buildMakcorpsFreeUrl('New York'), 'https://api.makcorps.com/free/new%20york');
});

test('builds Makcorps mapping and hotel price URLs', () => {
  assert.equal(
    buildMakcorpsMappingUrl({ destination_city: 'New York', apiKey: 'test-key' }),
    'https://api.makcorps.com/mapping?api_key=test-key&name=hotel+new+york',
  );
  assert.equal(
    buildMakcorpsHotelUrl({
      hotelId: '19438533',
      check_in_date: '2026-06-01',
      check_out_date: '2026-06-03',
      rooms: 2,
      guests: 3,
      apiKey: 'test-key',
    }),
    'https://api.makcorps.com/hotel?hotelid=19438533&adults=3&rooms=2&checkin=2026-06-01&checkout=2026-06-03&api_key=test-key',
  );
});

test('normalizes Makcorps free hotel response into travel hotel offers', () => {
  const offers = normalizeMakcorpsFreeResponse(
    [
      [
        { hotelName: 'ITC Grand Central', hotelId: '503409' },
        [
          { price1: '180', tax1: '27', vendor1: 'Booking.com' },
          { price2: '153', tax2: '0', vendor2: 'Priceline' },
        ],
      ],
      [
        { hotelName: 'Bloom Hotel', hotelId: '23526565' },
        [
          { price1: '78', tax1: '8', vendor1: 'Booking.com' },
        ],
      ],
    ],
    {
      destination_iata: 'BOM',
      destination_city: 'mumbai',
      check_in_date: '2026-05-30',
      check_out_date: '2026-06-02',
      rooms: 1,
      guests: 2,
      max_price_usd: 500,
    },
  );

  assert.equal(offers.length, 2);
  assert.equal(offers[0].hotel_id, 'makcorps_23526565');
  assert.equal(offers[0].name, 'Bloom Hotel');
  assert.equal(offers[0].price_per_night, 28.67);
  assert.equal(offers[0].total_price, 86);
  assert.equal(offers[0].currency, 'USD');
  assert.equal(offers[0].rooms, 1);
  assert.equal(offers[0].guests, 2);
  assert.match(offers[0].redirect_url, /google\.com\/travel\/hotels/);
  assert.equal(offers[1].hotel_id, 'makcorps_503409');
  assert.equal(offers[1].total_price, 153);
});

test('normalizes Makcorps mapping hotel records', () => {
  const hotels = normalizeMakcorpsMappingResponse([
    {
      type: 'HOTEL',
      document_id: '19438533',
      name: 'Nobu Hotel London Portman Square, London, England',
      details: {
        name: 'Nobu Hotel London Portman Square',
        address: '22 Portman Square',
        parent_name: 'London',
        grandparent_name: 'England',
      },
    },
    { type: 'GEO', document_id: '186338', name: 'London, England' },
  ]);

  assert.equal(hotels.length, 1);
  assert.equal(hotels[0].hotel_id, '19438533');
  assert.equal(hotels[0].name, 'Nobu Hotel London Portman Square');
  assert.equal(hotels[0].address, '22 Portman Square, London, England');
});

test('normalizes Makcorps hotel price comparison response', () => {
  const price = normalizeMakcorpsHotelPrice({
    comparison: [[
      { vendor1: 'Hotels.com', price1: '$524', Totalprice1: '$1,258', tax1: '104' },
      { vendor2: 'Agoda.com', price2: '$462', Totalprice2: '$1,110', tax2: '92' },
      { vendor3: 'Vio.com', price3: null, Totalprice3: null, tax3: null },
    ]],
  }, 2);

  assert.deepEqual(price, {
    vendor: 'Agoda.com',
    total_price: 1110,
    price_per_night: 555,
  });
});

test('searches Makcorps by mapping hotel IDs then pricing each hotel', async () => {
  const seenUrls = [];
  const result = await searchMakcorpsHotels(
    {
      destination_iata: 'LHR',
      check_in_date: '2026-06-01',
      check_out_date: '2026-06-03',
      rooms: 1,
      guests: 1,
    },
    {
      apiKey: 'test-key',
      fetchImpl: async (url) => {
        seenUrls.push(url);
        if (url.includes('/mapping?')) {
          return new Response(JSON.stringify([
            {
              type: 'HOTEL',
              document_id: '19438533',
              name: 'Nobu Hotel London Portman Square, London, England',
              details: { name: 'Nobu Hotel London Portman Square', address: '22 Portman Square', parent_name: 'London' },
            },
            {
              type: 'HOTEL',
              document_id: '193070',
              name: "The Bailey's Hotel London Kensington, London, England",
              details: { name: "The Bailey's Hotel London Kensington", address: '140 Gloucester Road', parent_name: 'London' },
            },
          ]), { status: 200, headers: { 'Content-Type': 'application/json' } });
        }
        const body = url.includes('19438533')
          ? { comparison: [[{ vendor1: 'Agoda.com', price1: '$462', Totalprice1: '$1,110', tax1: '92' }]] }
          : { comparison: [[{ vendor1: 'Expedia.com', price1: '$220', Totalprice1: '$528', tax1: '44' }]] };
        return new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } });
      },
    },
  );

  assert.equal(seenUrls.length, 3);
  assert.equal(result.length, 2);
  assert.equal(result[0].hotel_id, 'makcorps_193070');
  assert.equal(result[0].total_price, 528);
  assert.equal(result[1].hotel_id, 'makcorps_19438533');
  assert.equal(result[1].total_price, 1110);
});
