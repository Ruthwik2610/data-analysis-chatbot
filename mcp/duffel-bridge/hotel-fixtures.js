export function isStaysAccessDisabledMessage(text) {
  return /feature is not enabled|contact sales to get access/i.test(String(text || ''));
}

export function buildTestHotelOffers({
  destination_iata,
  check_in_date,
  check_out_date,
  rooms = 1,
  guests = 1,
  max_price_usd,
}) {
  const checkIn = new Date(check_in_date);
  const checkOut = new Date(check_out_date);
  const nights = Math.max(1, Math.floor((checkOut - checkIn) / (1000 * 60 * 60 * 24)));
  const destination = String(destination_iata || 'CITY').toUpperCase();
  const offers = [
    {
      hotel_id: `test_${destination.toLowerCase()}_business_hotel`,
      name: `${destination} Business Hotel`,
      address: `${destination} central business district`,
      star_rating: 4,
      review_score: 8.7,
      photo_url: '',
      price_per_night: 180,
    },
    {
      hotel_id: `test_${destination.toLowerCase()}_airport_suites`,
      name: `${destination} Airport Suites`,
      address: `${destination} airport area`,
      star_rating: 4,
      review_score: 8.4,
      photo_url: '',
      price_per_night: 195,
    },
    {
      hotel_id: `test_${destination.toLowerCase()}_executive_stay`,
      name: `${destination} Executive Stay`,
      address: `${destination} downtown`,
      star_rating: 5,
      review_score: 9.1,
      photo_url: '',
      price_per_night: 225,
    },
  ].map((offer) => ({
    ...offer,
    total_price: Number((offer.price_per_night * nights).toFixed(2)),
    currency: 'USD',
    check_in_date,
    check_out_date,
    rooms,
    guests,
    redirect_url: `https://app.duffel.com/stays?check_in_date=${encodeURIComponent(check_in_date)}&check_out_date=${encodeURIComponent(check_out_date)}&destination=${encodeURIComponent(destination)}&accommodation_id=${encodeURIComponent(offer.hotel_id)}`,
  }));

  return offers.filter((offer) => max_price_usd == null || offer.total_price <= max_price_usd);
}
