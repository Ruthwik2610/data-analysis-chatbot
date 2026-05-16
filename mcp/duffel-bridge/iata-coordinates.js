const IATA_COORDINATES = {
  ATL: { latitude: 33.6407, longitude: -84.4277 },
  BOM: { latitude: 19.0896, longitude: 72.8656 },
  DEL: { latitude: 28.5562, longitude: 77.1 },
  DXB: { latitude: 25.2532, longitude: 55.3657 },
  HYD: { latitude: 17.2403, longitude: 78.4294 },
  JFK: { latitude: 40.6413, longitude: -73.7781 },
  LAX: { latitude: 33.9416, longitude: -118.4085 },
  LHR: { latitude: 51.47, longitude: -0.4543 },
  ORD: { latitude: 41.9742, longitude: -87.9073 },
  RUH: { latitude: 24.9576, longitude: 46.6988 },
  SFO: { latitude: 37.6213, longitude: -122.379 },
};

export function lookupIataCoordinates(iata) {
  const code = String(iata || '').trim().toUpperCase();
  return IATA_COORDINATES[code] || null;
}
