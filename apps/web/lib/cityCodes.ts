// Static city → IATA city/metro code map for booking deep-links.
// Deliberately small and deterministic: covers major Indian origins plus the
// international destinations we see in real usage. When a city is missing,
// callers must fall back to a non-prefilled search page — never guess a code.

const CITY_TO_IATA: Record<string, string> = {
  // India
  'delhi': 'DEL',
  'new delhi': 'DEL',
  'mumbai': 'BOM',
  'bengaluru': 'BLR',
  'bangalore': 'BLR',
  'chennai': 'MAA',
  'kolkata': 'CCU',
  'hyderabad': 'HYD',
  'pune': 'PNQ',
  'ahmedabad': 'AMD',
  'jaipur': 'JAI',
  'goa': 'GOI',
  'kochi': 'COK',
  'cochin': 'COK',
  'lucknow': 'LKO',
  'chandigarh': 'IXC',
  'guwahati': 'GAU',
  'varanasi': 'VNS',
  'amritsar': 'ATQ',
  'indore': 'IDR',
  'bhubaneswar': 'BBI',
  'nagpur': 'NAG',
  'coimbatore': 'CJB',
  'thiruvananthapuram': 'TRV',
  'trivandrum': 'TRV',
  'srinagar': 'SXR',
  'leh': 'IXL',
  'dehradun': 'DED',
  'udaipur': 'UDR',
  'patna': 'PAT',
  // International
  'tokyo': 'TYO',
  'osaka': 'OSA',
  'kyoto': 'OSA', // no airport; Osaka is the standard gateway
  'singapore': 'SIN',
  'bangkok': 'BKK',
  'dubai': 'DXB',
  'abu dhabi': 'AUH',
  'london': 'LON',
  'paris': 'PAR',
  'new york': 'NYC',
  'rome': 'ROM',
  'milan': 'MIL',
  'amsterdam': 'AMS',
  'barcelona': 'BCN',
  'madrid': 'MAD',
  'istanbul': 'IST',
  'kathmandu': 'KTM',
  'colombo': 'CMB',
  'male': 'MLE',
  'denpasar': 'DPS',
  'bali': 'DPS',
  'kuala lumpur': 'KUL',
  'hong kong': 'HKG',
  'seoul': 'SEL',
  'sydney': 'SYD',
  'melbourne': 'MEL',
  'los angeles': 'LAX',
  'san francisco': 'SFO',
  'toronto': 'YTO',
  'vancouver': 'YVR',
  'zurich': 'ZRH',
  'vienna': 'VIE',
  'prague': 'PRG',
  'lisbon': 'LIS',
  'athens': 'ATH',
  'cairo': 'CAI',
  'nairobi': 'NBO',
  'johannesburg': 'JNB',
  'mauritius': 'MRU',
  'phuket': 'HKT',
  'hanoi': 'HAN',
  'ho chi minh city': 'SGN',
  'da nang': 'DAD',
  'tbilisi': 'TBS',
  'almaty': 'ALA',
  'tashkent': 'TAS',
}

// Indian city codes — used to decide MakeMyTrip's intl flag.
const INDIAN_CODES = new Set([
  'DEL', 'BOM', 'BLR', 'MAA', 'CCU', 'HYD', 'PNQ', 'AMD', 'JAI', 'GOI',
  'COK', 'LKO', 'IXC', 'GAU', 'VNS', 'ATQ', 'IDR', 'BBI', 'NAG', 'CJB',
  'TRV', 'SXR', 'IXL', 'DED', 'UDR', 'PAT',
])

/** Resolve a city name to an IATA city code, or null when unknown. */
export function cityToIata(city: string): string | null {
  return CITY_TO_IATA[city.trim().toLowerCase()] ?? null
}

export function isIndianCode(code: string): boolean {
  return INDIAN_CODES.has(code.toUpperCase())
}
