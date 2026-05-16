import test from 'node:test';
import assert from 'node:assert/strict';
import { lookupIataCoordinates } from './iata-coordinates.js';

test('returns coordinates for common IATA airport codes', () => {
  assert.deepEqual(lookupIataCoordinates('JFK'), { latitude: 40.6413, longitude: -73.7781 });
  assert.deepEqual(lookupIataCoordinates(' sfo '), { latitude: 37.6213, longitude: -122.379 });
});

test('returns null for unknown IATA airport codes', () => {
  assert.equal(lookupIataCoordinates('ZZZ'), null);
});
