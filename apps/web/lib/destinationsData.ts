// Static SEO landing-page content for `/destinations/[slug]`.
// Kept separate from FEATURED_TRIPS (LandingHero.tsx) — that list drives the
// homepage inspiration gallery and wizard preloads; this one drives indexable,
// keyword-targeted long-form content. Deliberately small and hand-curated —
// add entries here (and to DESTINATION_SLUGS) as new guides are written.

export interface DestinationDay {
  title: string
  items: string[]
}

export interface DestinationFaq {
  q: string
  a: string
}

export interface Destination {
  slug: string
  // Search terms fed into the wizard preload / useWikiImage — kept singular
  // and literal (a real city/region), even for the multi-country Europe guide.
  city: string
  country: string
  label: string
  emoji: string
  tagline: string
  recommendedDays: number
  budgetINR: string
  metaTitle: string
  metaDescription: string
  keywords: string[]
  imageQuery?: string
  overview: string[]
  highlights: string[]
  bestTimeToVisit: string
  budgetBreakdown: { category: string; amount: string }[]
  sampleItinerary: DestinationDay[]
  faqs: DestinationFaq[]
}

export const destinations: Destination[] = [
  {
    slug: 'bali',
    city: 'Bali',
    country: 'Indonesia',
    label: 'Bali, Indonesia',
    emoji: '🏖️',
    tagline: 'Beaches, rice terraces, and temples in equal measure',
    recommendedDays: 7,
    budgetINR: '₹70,000–₹90,000',
    metaTitle: 'Bali Trip Planner — 7-Day AI Itinerary & Budget Guide',
    metaDescription:
      'Free AI Bali trip planner. Get a personalised 7-day Bali itinerary covering Ubud, Seminyak, Uluwatu, and the Nusa islands — with budget, best time to visit, and local tips.',
    keywords: ['Bali trip planner', 'Bali itinerary', 'Bali travel guide', '7 days in Bali', 'Bali budget trip'],
    imageQuery: 'Uluwatu Temple Bali',
    overview: [
      "Bali packs an unusual range of experiences into a small island — surf beaches in the south, rice terraces and waterfalls in the centre, and quieter volcanic landscapes up north. Most first-time visitors split their week between Ubud (culture, jungle, rice fields), Seminyak or Canggu (beach clubs, cafés, sunsets), and Uluwatu (cliffs, temples, world-class surf).",
      "It's also one of the better value long-haul destinations for Indian travellers — direct flights from major metros, visa-on-arrival, and daily costs that stay reasonable even at mid-range hotels.",
    ],
    highlights: [
      'Sunrise trek up Mount Batur',
      'Tegallalang rice terraces near Ubud',
      'Uluwatu Temple at sunset with a Kecak fire dance',
      'Snorkelling or diving around Nusa Penida',
      'Beach clubs in Canggu and Seminyak',
    ],
    bestTimeToVisit:
      'April–October (dry season) for the most reliable weather. July–August is peak tourist season and pricier; April, May, June, and September offer similar weather with fewer crowds.',
    budgetBreakdown: [
      { category: 'Flights (India round-trip)', amount: '₹25,000–₹40,000' },
      { category: 'Stay (7 nights, mid-range)', amount: '₹15,000–₹25,000' },
      { category: 'Food & drink', amount: '₹10,000–₹15,000' },
      { category: 'Activities & transport', amount: '₹10,000–₹15,000' },
    ],
    sampleItinerary: [
      { title: 'Arrive, settle into Seminyak', items: ['Check in, sunset at Seminyak Beach', 'Dinner at a beachfront café'] },
      { title: 'Ubud culture & rice terraces', items: ['Tegallalang rice terraces', 'Ubud Palace & Monkey Forest', 'Evening Legong dance show'] },
      { title: 'Waterfalls & jungle swing', items: ['Tegenungan or Tibumana waterfall', 'Jungle swing photo stop', 'Balinese cooking class'] },
      { title: 'Mount Batur sunrise trek', items: ['Pre-dawn hike to Batur summit', 'Hot springs afterward', 'Rest of day free / spa'] },
      { title: 'Move to Uluwatu', items: ['Uluwatu Temple at sunset', 'Kecak fire dance performance', 'Cliffside dinner'] },
      { title: 'Nusa Penida day trip', items: ['Kelingking Beach viewpoint', 'Snorkelling at Crystal Bay', 'Broken Beach & Angel\'s Billabong'] },
      { title: 'Beach day & departure', items: ['Morning surf lesson or beach club', 'Last-minute shopping in Canggu', 'Departure'] },
    ],
    faqs: [
      { q: 'How many days do you need in Bali?', a: '7 days is comfortable for Ubud, the south coast, and one island day trip. 10+ days lets you add Nusa Lembongan/Ceningan or the north coast.' },
      { q: 'Do Indians need a visa for Bali?', a: 'Indonesia offers visa-on-arrival for Indian passport holders, valid for 30 days and extendable once.' },
      { q: 'Is Bali good for a budget trip?', a: 'Yes — outside of flights, daily costs (food, local transport, guesthouses) are low compared to most beach destinations.' },
    ],
  },
  {
    slug: 'rajasthan',
    city: 'Rajasthan',
    country: 'India',
    label: 'Rajasthan, India',
    emoji: '🏰',
    tagline: 'Forts, palaces, and desert landscapes across royal India',
    recommendedDays: 10,
    budgetINR: '₹45,000–₹65,000',
    metaTitle: 'Rajasthan Travel Guide — 10-Day AI Itinerary & Budget',
    metaDescription:
      'Free AI Rajasthan trip planner. Get a personalised 10-day itinerary covering Jaipur, Udaipur, Jodhpur, and Jaisalmer — with budget, best time to visit, and fort/palace tips.',
    keywords: ['Rajasthan travel guide', 'Rajasthan trip planner', 'Rajasthan itinerary', '10 days in Rajasthan', 'Jaipur Udaipur Jodhpur trip'],
    imageQuery: 'Amber Fort Jaipur',
    overview: [
      "Rajasthan is India's most classic heritage circuit — a loop through Jaipur's forts, Udaipur's lakes, Jodhpur's blue city, and Jaisalmer's desert dunes, all connected by well-worn tourist rail and road routes. It rewards a slower pace: each city has a genuinely distinct character, from Udaipur's romantic lakeside palaces to Jaisalmer's living desert fort.",
      "It also works well as either a first big India trip or a focused heritage-and-photography trip for repeat visitors, since the driving distances between cities (4–6 hours) make a loop itinerary practical without much backtracking.",
    ],
    highlights: [
      'Amber Fort and City Palace, Jaipur',
      'Boat ride on Lake Pichola, Udaipur',
      'Mehrangarh Fort towering over the Blue City, Jodhpur',
      'Camel safari and dunes at Sam, Jaisalmer',
      'Living inside Jaisalmer Fort\'s old town',
    ],
    bestTimeToVisit:
      'October–March. Daytime temperatures are pleasant and desert nights are cool but manageable; April–June gets extremely hot (40°C+), especially in Jaisalmer.',
    budgetBreakdown: [
      { category: 'Intercity travel (train/car)', amount: '₹8,000–₹12,000' },
      { category: 'Stay (10 nights, mid-range heritage hotels)', amount: '₹20,000–₹30,000' },
      { category: 'Food', amount: '₹8,000–₹10,000' },
      { category: 'Monument entry & activities', amount: '₹6,000–₹10,000' },
    ],
    sampleItinerary: [
      { title: 'Arrive Jaipur', items: ['City Palace & Jantar Mantar', 'Evening at Bapu Bazaar'] },
      { title: 'Jaipur forts', items: ['Amber Fort at sunrise', 'Nahargarh Fort at sunset for the city view'] },
      { title: 'Travel to Udaipur', items: ['Drive/train to Udaipur', 'Evening boat ride on Lake Pichola'] },
      { title: 'Udaipur palaces', items: ['City Palace complex', 'Saheliyon ki Bari gardens', 'Rooftop dinner overlooking the lake'] },
      { title: 'Travel to Jodhpur', items: ['Drive to Jodhpur', 'Sunset at Mehrangarh Fort ramparts'] },
      { title: 'Jodhpur, the Blue City', items: ['Mehrangarh Fort museum', 'Walk the blue lanes near the clock tower', 'Umaid Bhawan Palace'] },
      { title: 'Travel to Jaisalmer', items: ['Long drive/train to Jaisalmer', 'Evening at Jaisalmer Fort\'s ramparts'] },
      { title: 'Jaisalmer town', items: ['Patwon ki Haveli', 'Gadisar Lake', 'Sunset camel ride at Sam dunes'] },
      { title: 'Desert camp', items: ['Overnight desert camp', 'Folk music & dinner under the stars'] },
      { title: 'Return / departure', items: ['Morning at leisure', 'Fly out from Jodhpur or Jaipur'] },
    ],
    faqs: [
      { q: 'What is the ideal number of days for Rajasthan?', a: '10 days covers the core Jaipur–Udaipur–Jodhpur–Jaisalmer loop comfortably. 5–7 days works if you drop Jaisalmer, which adds long drives.' },
      { q: 'Is Rajasthan good for a family trip?', a: "Yes — forts and palaces appeal across ages, and most cities have easy day-trip pacing rather than long treks." },
      { q: 'Best way to travel between Rajasthan cities?', a: 'Private car/driver is the most flexible for the full loop; trains connect Jaipur, Jodhpur, and Udaipur well if you\'re on a tighter budget.' },
    ],
  },
  {
    slug: 'dubai',
    city: 'Dubai',
    country: 'UAE',
    label: 'Dubai, UAE',
    emoji: '🌃',
    tagline: 'Skyscrapers, desert safaris, and a short flight from India',
    recommendedDays: 4,
    budgetINR: '₹1,40,000–₹1,80,000',
    metaTitle: 'Dubai Trip Planner — 4-Day AI Itinerary & Budget Guide',
    metaDescription:
      'Free AI Dubai trip planner. Get a personalised 4-day Dubai itinerary covering Burj Khalifa, desert safari, Old Dubai, and the Marina — with budget and visa tips.',
    keywords: ['Dubai trip planner', 'Dubai itinerary', '4 days in Dubai', 'Dubai travel guide', 'Dubai budget trip'],
    imageQuery: 'Burj Khalifa Dubai skyline',
    overview: [
      "Dubai suits a short, high-density trip — most of the marquee experiences (Burj Khalifa, desert safari, Dubai Mall, the Marina) sit within a 30-minute drive of each other, and the metro covers a surprising amount of it directly. It's also one of the most convenient international trips for Indian travellers: a 3-hour flight, visa-on-arrival for most passport holders with a valid US/UK/Schengen visa or eligible visa categories, and no time-zone adjustment worth mentioning.",
      "It works equally well as a long weekend city break or as a 2–3 night stopover extension on a longer Europe or East Africa trip.",
    ],
    highlights: [
      "Burj Khalifa 'At the Top' observation deck",
      'Desert safari with dune bashing and a BBQ dinner',
      'Old Dubai — Al Fahidi district and the Gold/Spice Souks by abra boat',
      'Dubai Marina and JBR beach promenade',
      'Dubai Mall & the Dubai Fountain show',
    ],
    bestTimeToVisit:
      'November–March, when daytime temperatures are comfortable for outdoor sightseeing and desert safaris. May–September is extremely hot (40°C+) and best avoided for anything outdoors.',
    budgetBreakdown: [
      { category: 'Flights (India round-trip)', amount: '₹20,000–₹35,000' },
      { category: 'Stay (4 nights)', amount: '₹25,000–₹45,000' },
      { category: 'Food', amount: '₹15,000–₹20,000' },
      { category: 'Activities (Burj Khalifa, safari, etc.)', amount: '₹20,000–₹30,000' },
    ],
    sampleItinerary: [
      { title: 'Arrive, Downtown Dubai', items: ['Check in near Downtown', 'Burj Khalifa at sunset', 'Dubai Fountain show'] },
      { title: 'Old Dubai & souks', items: ['Al Fahidi historic district', 'Abra boat across Dubai Creek', 'Gold & Spice Souks'] },
      { title: 'Desert safari', items: ['Afternoon dune bashing', 'Camel ride & sandboarding', 'BBQ dinner with entertainment'] },
      { title: 'Marina & departure', items: ['Dubai Marina walk / boat', 'Dubai Mall & departure'] },
    ],
    faqs: [
      { q: 'Do Indians need a visa for Dubai?', a: "Indian passport holders can get visa-on-arrival if they hold a valid US visa, UK visa, or Schengen visa; otherwise a UAE visa must be arranged in advance." },
      { q: 'Is 4 days enough for Dubai?', a: "Yes for the main highlights. Add 1–2 days for Abu Dhabi (Sheikh Zayed Mosque, Louvre Abu Dhabi) if you want to combine both cities." },
      { q: 'Is Dubai expensive?', a: "It can be, but costs scale with choices — budget hotels, metro instead of taxis, and food courts instead of fine dining keep it reasonable." },
    ],
  },
  {
    slug: 'europe',
    city: 'Paris',
    country: 'France',
    label: 'Europe',
    emoji: '🗼',
    tagline: 'A classic multi-country loop through Western Europe',
    recommendedDays: 12,
    budgetINR: '₹2,20,000–₹3,00,000',
    metaTitle: 'Europe Trip Itinerary — 12-Day AI Multi-Country Planner',
    metaDescription:
      'Free AI Europe trip planner. Get a personalised 12-day itinerary across Paris, Amsterdam, and Rome — with Schengen visa, rail pass, and budget tips.',
    keywords: ['Europe trip itinerary', 'Europe travel planner', '12 days in Europe', 'first time Europe trip', 'Europe budget itinerary'],
    imageQuery: 'Eiffel Tower Paris',
    overview: [
      "A first Europe trip usually means choosing between going deep on one country or covering a classic multi-city loop — Paris, Amsterdam, and Rome remain the most popular combination for a first-timer, connected by cheap short-haul flights or high-speed rail, and each offering a distinctly different city character.",
      "Because most Western European countries share the Schengen visa, one visa application covers the whole loop, which is what makes multi-country itineraries this efficient in the first place.",
    ],
    highlights: [
      'Eiffel Tower and the Louvre, Paris',
      'Canal cruise and Anne Frank House, Amsterdam',
      'Colosseum and Vatican City, Rome',
      'Day trip to Versailles from Paris',
      'Evening at a canal-side café in Amsterdam',
    ],
    bestTimeToVisit:
      'April–June and September–October offer mild weather and smaller crowds than peak summer (July–August), which is also the most expensive travel window.',
    budgetBreakdown: [
      { category: 'Flights (India round-trip)', amount: '₹55,000–₹80,000' },
      { category: 'Stay (12 nights, mid-range)', amount: '₹60,000–₹90,000' },
      { category: 'Intercity trains/flights within Europe', amount: '₹15,000–₹25,000' },
      { category: 'Food & activities', amount: '₹50,000–₹70,000' },
    ],
    sampleItinerary: [
      { title: 'Arrive Paris', items: ['Check in, evening walk along the Seine', 'Eiffel Tower at night'] },
      { title: 'Paris landmarks', items: ['The Louvre', 'Notre-Dame area', 'Montmartre & Sacré-Cœur'] },
      { title: 'Versailles day trip', items: ['Palace of Versailles & gardens', 'Evening back in Paris'] },
      { title: 'Travel to Amsterdam', items: ['High-speed train to Amsterdam', 'Evening canal walk'] },
      { title: 'Amsterdam', items: ['Anne Frank House', 'Canal cruise', 'Van Gogh Museum'] },
      { title: 'Amsterdam day trip', items: ['Zaanse Schans windmills or Keukenhof (seasonal)', 'Evening free'] },
      { title: 'Travel to Rome', items: ['Flight to Rome', 'Evening at Trastevere'] },
      { title: 'Rome ancient sites', items: ['Colosseum & Roman Forum', 'Palatine Hill'] },
      { title: 'Vatican City', items: ['Vatican Museums & Sistine Chapel', 'St. Peter\'s Basilica'] },
      { title: 'Rome free day', items: ['Trevi Fountain, Pantheon, Spanish Steps', 'Evening gelato crawl'] },
      { title: 'Buffer / day trip', items: ['Optional Naples/Pompeii day trip', 'Or rest day in Rome'] },
      { title: 'Departure', items: ['Morning free', 'Fly out from Rome'] },
    ],
    faqs: [
      { q: 'How many days do you need for a first Europe trip?', a: "10–14 days lets you cover 3 cities without feeling rushed. Fewer days works better focused on one or two cities instead." },
      { q: 'Do Indians need a visa for Europe?', a: "Most Western European countries are in the Schengen Area, which Indian passport holders need a single Schengen visa for, valid across all member countries." },
      { q: 'Is it cheaper to fly or take the train between European cities?', a: 'Both are usually similar in price on this route; trains save airport transfer time, budget flights can be cheaper if booked early.' },
    ],
  },
]

export const destinationBySlug = new Map(destinations.map((d) => [d.slug, d]))
