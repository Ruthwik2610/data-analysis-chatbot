import test from 'node:test';
import assert from 'node:assert/strict';
import { buildTestHotelOffers, isStaysAccessDisabledMessage } from './hotel-fixtures.js';

test('detects Duffel Stays account access errors', () => {
  assert.equal(
    isStaysAccessDisabledMessage('This feature is not enabled for your account. Please contact sales to get access.'),
    true,
  );
  assert.equal(isStaysAccessDisabledMessage('No hotels found'), false);
});

test('builds selectable test hotel offers under the policy cap', () => {
  const offers = buildTestHotelOffers({
    destination_iata: 'JFK',
    check_in_date: '2026-06-01',
    check_out_date: '2026-06-05',
    rooms: 1,
    guests: 1,
    max_price_usd: 800,
  });

  assert.equal(offers.length, 2);
  assert.equal(offers[0].hotel_id, 'test_jfk_business_hotel');
  assert.equal(offers[0].total_price, 720);
  assert.equal(offers[0].currency, 'USD');
  assert.equal(offers[0].check_in_date, '2026-06-01');
  assert.equal(offers[0].check_out_date, '2026-06-05');
  assert.match(offers[0].redirect_url, /app\.duffel\.com\/stays/);
});
