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

export interface DestinationHeroImage {
  url: string
  photographer: string
  photographerUrl: string
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
  // Curated once from Pexels (1600x900, landscape-cropped) — replaces a live
  // Wikipedia thumbnail fetch that was often oddly cropped/low-res when
  // stretched across the full-width hero banner. See DestinationHeroImage.tsx.
  heroImage: DestinationHeroImage
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
    heroImage: {
      url: 'https://images.pexels.com/photos/36593818/pexels-photo-36593818.jpeg?auto=compress&cs=tinysrgb&w=1600&h=900&fit=crop',
      photographer: 'Tom Fisk',
      photographerUrl: 'https://www.pexels.com/@tomfisk',
    },
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
    heroImage: {
      url: 'https://images.pexels.com/photos/19446861/pexels-photo-19446861.jpeg?auto=compress&cs=tinysrgb&w=1600&h=900&fit=crop',
      photographer: 'Abhinav Sharma',
      photographerUrl: 'https://www.pexels.com/@abhi31',
    },
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
    heroImage: {
      url: 'https://images.pexels.com/photos/5577693/pexels-photo-5577693.jpeg?auto=compress&cs=tinysrgb&w=1600&h=900&fit=crop',
      photographer: 'Maria Charizani',
      photographerUrl: 'https://www.pexels.com/@maria-charizani-3542905',
    },
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
    heroImage: {
      url: 'https://images.pexels.com/photos/16496484/pexels-photo-16496484.jpeg?auto=compress&cs=tinysrgb&w=1600&h=900&fit=crop',
      photographer: 'Mehmet Turgut  Kirkgoz',
      photographerUrl: 'https://www.pexels.com/@tkirkgoz',
    },
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
  {
    slug: 'paris',
    city: 'Paris',
    country: 'France',
    label: 'Paris, France',
    emoji: '🗼',
    tagline: 'Romance, world-class art, and café culture on the Seine',
    recommendedDays: 5,
    budgetINR: '₹1,60,000–₹2,00,000',
    metaTitle: 'Paris Trip Planner — 5-Day AI Itinerary & Budget Guide',
    metaDescription:
      'Free AI Paris trip planner. Get a personalised 5-day Paris itinerary covering the Eiffel Tower, the Louvre, Montmartre, and a Versailles day trip — with budget and visa tips.',
    keywords: ['Paris trip planner', 'Paris itinerary', '5 days in Paris', 'Paris travel guide', 'Paris budget trip'],
    imageQuery: 'Eiffel Tower Paris',
    heroImage: {
      url: 'https://images.pexels.com/photos/16496484/pexels-photo-16496484.jpeg?auto=compress&cs=tinysrgb&w=1600&h=900&fit=crop',
      photographer: 'Mehmet Turgut  Kirkgoz',
      photographerUrl: 'https://www.pexels.com/@tkirkgoz',
    },
    overview: [
      "Paris rewards unhurried mornings and a willingness to walk — the Louvre, Notre-Dame, the Latin Quarter, and the Seine's riverbanks are all within a compact, walkable core, with Montmartre's hilltop streets and Sacré-Cœur just a short metro ride away.",
      "Five days is enough to cover the major landmarks at a comfortable pace, with a day left over for either a Versailles side trip or a slower neighbourhood-by-neighbourhood wander through areas like Le Marais and Saint-Germain-des-Prés.",
    ],
    highlights: [
      'Eiffel Tower — daytime view and sunset light-up',
      'The Louvre and the Musée d\'Orsay',
      'Montmartre and Sacré-Cœur',
      'Seine river cruise at dusk',
      'Palace of Versailles day trip',
    ],
    bestTimeToVisit:
      'April–June and September–October for mild weather and thinner crowds than peak summer (July–August), which is also when hotel prices peak.',
    budgetBreakdown: [
      { category: 'Flights (India round-trip)', amount: '₹45,000–₹65,000' },
      { category: 'Stay (5 nights, mid-range)', amount: '₹35,000–₹50,000' },
      { category: 'Food', amount: '₹25,000–₹35,000' },
      { category: 'Museums, Versailles, activities', amount: '₹20,000–₹30,000' },
    ],
    sampleItinerary: [
      { title: 'Arrive, Eiffel Tower', items: ['Check in, evening walk along the Seine', 'Eiffel Tower at night'] },
      { title: 'The Louvre & Île de la Cité', items: ['The Louvre (book ahead)', 'Notre-Dame area', 'Latin Quarter for dinner'] },
      { title: 'Montmartre', items: ['Sacré-Cœur & artists\' square', 'Musée d\'Orsay', 'Seine dinner cruise'] },
      { title: 'Versailles day trip', items: ['Palace of Versailles & gardens', 'Evening back in Le Marais'] },
      { title: 'Saint-Germain & departure', items: ['Café morning in Saint-Germain-des-Prés', 'Last-minute shopping', 'Departure'] },
    ],
    faqs: [
      { q: 'How many days do you need in Paris?', a: '4–5 days covers the major landmarks and a day trip comfortably; add extra days for a slower, neighbourhood-focused pace.' },
      { q: 'Do Indians need a visa for Paris?', a: 'Yes — France is in the Schengen Area, so Indian passport holders need a Schengen visa valid for France.' },
      { q: 'Is Paris expensive?', a: 'It can be, but museum passes, metro day tickets, and bakery lunches keep costs well below fine-dining-every-meal budgets.' },
    ],
  },
  {
    slug: 'kyoto',
    city: 'Kyoto',
    country: 'Japan',
    label: 'Kyoto, Japan',
    emoji: '⛩️',
    tagline: 'Temples, gardens, and old-Japan calm away from Tokyo\'s pace',
    recommendedDays: 7,
    budgetINR: '₹1,80,000–₹2,20,000',
    metaTitle: 'Kyoto Trip Planner — 7-Day AI Itinerary & Budget Guide',
    metaDescription:
      'Free AI Kyoto trip planner. Get a personalised 7-day Kyoto itinerary covering Fushimi Inari, Arashiyama, Gion, and day trips to Nara and Osaka — with budget and season tips.',
    keywords: ['Kyoto trip planner', 'Kyoto itinerary', '7 days in Kyoto', 'Kyoto travel guide', 'Japan itinerary'],
    heroImage: {
      url: 'https://images.pexels.com/photos/35076911/pexels-photo-35076911.jpeg?auto=compress&cs=tinysrgb&w=1600&h=900&fit=crop',
      photographer: 'Dmitry Romanoff',
      photographerUrl: 'https://www.pexels.com/@dmitry-romanoff-1151933996',
    },
    overview: [
      "Kyoto was Japan's imperial capital for over a thousand years, and it shows — over a thousand temples and shrines, entire preserved geisha districts, and gardens built for exactly this kind of unhurried walking. It's slower and more traditional than Tokyo, which is precisely why most itineraries pair the two.",
      "A week is enough to cover Kyoto properly (the city itself rewards 4–5 days) plus day trips to Nara's deer park and Osaka's food scene, both under an hour away by train.",
    ],
    highlights: [
      'Fushimi Inari Shrine\'s thousand torii gates',
      'Arashiyama Bamboo Grove',
      'Kinkaku-ji (the Golden Pavilion)',
      'Gion district in the evening',
      'Day trip to Nara\'s deer park',
    ],
    bestTimeToVisit:
      'Late March–early April for cherry blossoms, or November for autumn foliage — both are peak season and book out early. June–August is hot and humid; December–February is cold but far less crowded.',
    budgetBreakdown: [
      { category: 'Flights (India round-trip)', amount: '₹45,000–₹65,000' },
      { category: 'Stay (7 nights, mid-range)', amount: '₹45,000–₹65,000' },
      { category: 'JR Pass / local trains', amount: '₹15,000–₹20,000' },
      { category: 'Food & temple entry fees', amount: '₹35,000–₹45,000' },
    ],
    sampleItinerary: [
      { title: 'Arrive Kyoto', items: ['Check in, evening in Gion'] },
      { title: 'Eastern Kyoto', items: ['Kiyomizu-dera Temple', 'Higashiyama district walk', 'Gion evening again for geisha-spotting'] },
      { title: 'Golden Pavilion & Zen gardens', items: ['Kinkaku-ji', 'Ryoan-ji rock garden', 'Nijo Castle'] },
      { title: 'Arashiyama', items: ['Bamboo Grove at sunrise (fewer crowds)', 'Tenryu-ji Temple', 'Monkey Park hike'] },
      { title: 'Fushimi Inari', items: ['Full torii-gate hike', 'Nearby sake district, Fushimi'] },
      { title: 'Nara day trip', items: ['Nara Park deer', 'Todai-ji Temple\'s giant Buddha'] },
      { title: 'Osaka day trip / departure', items: ['Dotonbori street food', 'Osaka Castle', 'Return to Kyoto or fly out'] },
    ],
    faqs: [
      { q: 'How many days do you need in Kyoto?', a: '4–5 days for Kyoto itself; a week lets you add Nara and Osaka as day trips.' },
      { q: 'Do Indians need a visa for Japan?', a: 'Yes, a standard Japan tourist visa; processing is usually straightforward with a clear itinerary and hotel bookings.' },
      { q: 'Is a JR Pass worth it for a Kyoto-based trip?', a: 'A regional Kansai pass is usually better value than the national JR Pass if you\'re staying within the Kyoto–Osaka–Nara triangle.' },
    ],
  },
  {
    slug: 'kenya-safari',
    city: 'Nairobi',
    country: 'Kenya',
    label: 'Kenya Safari',
    emoji: '🦁',
    tagline: 'The Masai Mara\'s big cats and, in season, the wildebeest migration',
    recommendedDays: 8,
    budgetINR: '₹3,20,000–₹3,80,000',
    metaTitle: 'Kenya Safari Itinerary — 8-Day AI Trip Planner & Budget',
    metaDescription:
      'Free AI Kenya safari planner. Get a personalised 8-day itinerary covering the Masai Mara, Amboseli, and Lake Nakuru — with migration season timing and budget breakdown.',
    keywords: ['Kenya safari itinerary', 'Masai Mara trip planner', 'Kenya safari budget', 'Africa safari itinerary', 'wildlife safari trip'],
    imageQuery: 'Masai Mara wildlife safari',
    heroImage: {
      url: 'https://images.pexels.com/photos/10822350/pexels-photo-10822350.jpeg?auto=compress&cs=tinysrgb&w=1600&h=900&fit=crop',
      photographer: 'Richard Wilson',
      photographerUrl: 'https://www.pexels.com/@richard-wilson-1717169',
    },
    overview: [
      "A Kenya safari is built around a handful of parks, each with a different draw: the Masai Mara for big cats and, from roughly July to October, the wildebeest migration crossing the Mara River; Amboseli for elephant herds set against Kilimanjaro; and Lake Nakuru for rhinos and flamingos in a smaller, easier-to-cover park.",
      "Most trips combine 2–3 parks with internal flights or a long game-drive transfer between them, plus a day or two around Nairobi at either end.",
    ],
    highlights: [
      'Big cat sightings in the Masai Mara',
      'Wildebeest migration river crossings (July–October)',
      'Elephant herds against Kilimanjaro in Amboseli',
      'Rhino and flamingo spotting at Lake Nakuru',
      'Sundowner game drives',
    ],
    bestTimeToVisit:
      'July–October for the wildebeest migration in the Mara; January–February is also good for general game viewing with fewer crowds and lower prices. Avoid the long rains (March–May).',
    budgetBreakdown: [
      { category: 'Flights (India round-trip)', amount: '₹55,000–₹75,000' },
      { category: 'Safari lodges/camps (7 nights, full board)', amount: '₹1,50,000–₹1,90,000' },
      { category: 'Internal flights/transfers between parks', amount: '₹35,000–₹50,000' },
      { category: 'Park fees & guided game drives', amount: '₹40,000–₹50,000' },
    ],
    sampleItinerary: [
      { title: 'Arrive Nairobi', items: ['Overnight near the airport', 'Optional Giraffe Centre or Elephant Orphanage visit'] },
      { title: 'Fly to Masai Mara', items: ['Afternoon game drive on arrival'] },
      { title: 'Masai Mara full day', items: ['Sunrise game drive', 'Afternoon drive toward the Mara River'] },
      { title: 'Masai Mara migration/big cats', items: ['River crossing viewing (seasonal)', 'Sundowner drive'] },
      { title: 'Transfer to Amboseli', items: ['Road/flight transfer', 'Evening game drive with Kilimanjaro views'] },
      { title: 'Amboseli full day', items: ['Elephant herd tracking', 'Observation Hill'] },
      { title: 'Lake Nakuru', items: ['Transfer to Nakuru', 'Rhino sanctuary & flamingo shores'] },
      { title: 'Return Nairobi / departure', items: ['Morning drive back', 'Departure'] },
    ],
    faqs: [
      { q: 'When is the wildebeest migration in Kenya?', a: 'River crossings into the Masai Mara typically happen July–October, though exact timing shifts year to year with rainfall.' },
      { q: 'Do Indians need a visa for Kenya?', a: 'Yes, an eTA (electronic travel authorisation) is required in advance — it\'s a straightforward online application.' },
      { q: 'Is a Kenya safari safe for families?', a: "Yes — most lodges and camps are well set up for families, though check minimum age policies for game drives at specific camps." },
    ],
  },
  {
    slug: 'himachal-pradesh',
    city: 'Manali',
    country: 'India',
    label: 'Himachal Pradesh',
    emoji: '🏔️',
    tagline: 'Himalayan valleys, treks, and hill-station towns',
    recommendedDays: 6,
    budgetINR: '₹40,000–₹50,000',
    metaTitle: 'Himachal Pradesh Trip Planner — 6-Day AI Itinerary & Budget',
    metaDescription:
      'Free AI Himachal Pradesh trip planner. Get a personalised 6-day itinerary covering Manali, Kasol, and Spiti Valley or Shimla — with budget and best season tips.',
    keywords: ['Himachal Pradesh trip planner', 'Manali itinerary', 'Himachal travel guide', 'Kasol trip', '6 days in Himachal'],
    heroImage: {
      url: 'https://images.pexels.com/photos/16104060/pexels-photo-16104060.jpeg?auto=compress&cs=tinysrgb&w=1600&h=900&fit=crop',
      photographer: 'Piyush Sharma',
      photographerUrl: 'https://www.pexels.com/@piyush-sharma-503040734',
    },
    overview: [
      "Himachal Pradesh covers a lot of ground character-wise — Manali's adventure-sports base camp feel, Kasol's backpacker cafés along the Parvati river, Shimla's colonial hill-station streets, and, further out, Spiti Valley's stark high-altitude desert landscape.",
      "Most first-time trips centre on Manali and Kasol (close together, easy loop) or Shimla and Kufri for a gentler, more accessible hill-station trip — Spiti requires more days and is best added on a second visit.",
    ],
    highlights: [
      'Solang Valley and Rohtang Pass views',
      'Old Manali cafés and the Hidimba Temple',
      'Parvati Valley walk from Kasol to Tosh',
      'Mall Road and Jakhoo Temple, Shimla',
      'Riverside camping near Kasol',
    ],
    bestTimeToVisit:
      'March–June for pleasant weather and blooming valleys; December–February for snow around Manali (roads can close). Avoid July–August monsoon landslide risk on mountain roads.',
    budgetBreakdown: [
      { category: 'Travel (flight/train + local transport)', amount: '₹10,000–₹15,000' },
      { category: 'Stay (6 nights)', amount: '₹12,000–₹18,000' },
      { category: 'Food', amount: '₹8,000–₹10,000' },
      { category: 'Activities (adventure sports, permits)', amount: '₹8,000–₹12,000' },
    ],
    sampleItinerary: [
      { title: 'Arrive Manali', items: ['Old Manali café hop', 'Hidimba Temple'] },
      { title: 'Solang Valley', items: ['Paragliding or zorbing (season-dependent)', 'Rohtang Pass views (if open)'] },
      { title: 'Travel to Kasol', items: ['Drive along the Parvati river', 'Evening riverside café'] },
      { title: 'Kasol & Tosh', items: ['Day hike to Tosh village', 'Kheerganga trek option'] },
      { title: 'Manikaran & return', items: ['Manikaran Sahib hot springs', 'Travel back toward Manali'] },
      { title: 'Departure', items: ['Morning at leisure', 'Departure'] },
    ],
    faqs: [
      { q: 'How many days do you need for Manali and Kasol?', a: '5–6 days covers both comfortably including the travel between them.' },
      { q: 'Is Himachal good for a budget trip?', a: 'Yes — guesthouses, dhaba food, and shared cabs keep daily costs low outside of adventure-sport activities.' },
      { q: 'Best time to see snow in Manali?', a: 'December–February for reliable snow, though some higher passes may close.' },
    ],
  },
  {
    slug: 'maldives',
    city: 'Maldives',
    country: 'Maldives',
    label: 'Maldives',
    emoji: '🌊',
    tagline: 'Overwater villas, house reefs, and turquoise lagoons',
    recommendedDays: 5,
    budgetINR: '₹2,80,000–₹3,40,000',
    metaTitle: 'Maldives Trip Planner — 5-Day AI Itinerary & Budget Guide',
    metaDescription:
      'Free AI Maldives trip planner. Get a personalised 5-day Maldives itinerary covering resort selection, snorkelling, and overwater villa stays — with budget and season tips.',
    keywords: ['Maldives trip planner', 'Maldives itinerary', 'Maldives honeymoon', 'Maldives budget trip', 'overwater villa'],
    imageQuery: 'Maldives tourism travel',
    heroImage: {
      url: 'https://images.pexels.com/photos/1287455/pexels-photo-1287455.jpeg?auto=compress&cs=tinysrgb&w=1600&h=900&fit=crop',
      photographer: 'Asad Photo Maldives',
      photographerUrl: 'https://www.pexels.com/@asadphoto',
    },
    overview: [
      "The Maldives is a one-resort-island trip more often than a multi-stop itinerary — most visitors pick a single atoll resort (or two, split across a stay) and build the days around the house reef, water sports, and spa time rather than day-tripping between sights.",
      "Budget swings enormously by resort tier: a guesthouse on a local island (like Maafushi) with day-trip snorkelling costs a fraction of an overwater-villa resort — both are valid ways to do the Maldives depending on the trip you want.",
    ],
    highlights: [
      'Snorkelling the house reef straight off your villa',
      'Sandbank or sunset dolphin cruise',
      'Overwater villa breakfast',
      'Night fishing excursion',
      'Local-island day trip (budget option via Maafushi)',
    ],
    bestTimeToVisit:
      'November–April (dry season) for the calmest seas and best visibility; May–October is the monsoon season with more rain but lower resort prices.',
    budgetBreakdown: [
      { category: 'Flights (India round-trip)', amount: '₹25,000–₹40,000' },
      { category: 'Resort stay (4 nights, overwater villa)', amount: '₹1,80,000–₹2,30,000' },
      { category: 'Seaplane/speedboat transfers', amount: '₹25,000–₹40,000' },
      { category: 'Excursions & spa', amount: '₹20,000–₹30,000' },
    ],
    sampleItinerary: [
      { title: 'Arrive, transfer to resort', items: ['Seaplane/speedboat transfer', 'Evening at leisure, sunset at the house reef'] },
      { title: 'Snorkelling & water sports', items: ['Morning house-reef snorkel', 'Kayaking or paddleboarding'] },
      { title: 'Excursion day', items: ['Sandbank picnic or dolphin cruise', 'Evening spa'] },
      { title: 'Free day / diving', items: ['Optional scuba dive for certified divers', 'Relax at the villa'] },
      { title: 'Departure', items: ['Morning at the beach', 'Transfer back for flight'] },
    ],
    faqs: [
      { q: 'How many days do you need in the Maldives?', a: '4–5 days is typical for a resort stay; shorter trips feel rushed given transfer time.' },
      { q: 'Do Indians need a visa for the Maldives?', a: 'No — Indian passport holders get a free 30-day visa-on-arrival.' },
      { q: 'Can the Maldives be done on a budget?', a: 'Yes, via guesthouses on local islands like Maafushi with day-trip excursions instead of an overwater resort.' },
    ],
  },
  {
    slug: 'singapore',
    city: 'Singapore',
    country: 'Singapore',
    label: 'Singapore',
    emoji: '🌆',
    tagline: 'Hawker food, a walkable skyline, and easy family logistics',
    recommendedDays: 4,
    budgetINR: '₹90,000–₹1,20,000',
    metaTitle: 'Singapore Trip Planner — 4-Day AI Itinerary & Budget Guide',
    metaDescription:
      'Free AI Singapore trip planner. Get a personalised 4-day Singapore itinerary covering Gardens by the Bay, Sentosa, and hawker centres — with budget and visa tips.',
    keywords: ['Singapore trip planner', 'Singapore itinerary', '4 days in Singapore', 'Singapore travel guide', 'Singapore family trip'],
    heroImage: {
      url: 'https://images.pexels.com/photos/18662417/pexels-photo-18662417.jpeg?auto=compress&cs=tinysrgb&w=1600&h=900&fit=crop',
      photographer: 'Mark Baldovino',
      photographerUrl: 'https://www.pexels.com/@odlab2',
    },
    overview: [
      "Singapore is one of the most logistically easy international trips available from India — a clean, English-speaking, well-connected city where the metro reaches almost everything, hawker centres make food both cheap and excellent, and a short flight means minimal jet lag.",
      "Four days covers the core sights (Marina Bay, Sentosa, a couple of neighbourhoods) comfortably, and it works equally well as a standalone trip or a stopover extension.",
    ],
    highlights: [
      'Gardens by the Bay and the Supertree Grove light show',
      'Marina Bay Sands SkyPark',
      'Sentosa Island (Universal Studios or the beaches)',
      'Hawker centre food crawl (Maxwell, Lau Pa Sat)',
      'Chinatown and Little India neighbourhood walks',
    ],
    bestTimeToVisit:
      'Year-round destination given its equatorial climate — February–April has slightly less rain, but Singapore works as a trip in any month.',
    budgetBreakdown: [
      { category: 'Flights (India round-trip)', amount: '₹18,000–₹28,000' },
      { category: 'Stay (4 nights)', amount: '₹20,000–₹35,000' },
      { category: 'Food', amount: '₹12,000–₹18,000' },
      { category: 'Sentosa/attractions', amount: '₹15,000–₹25,000' },
    ],
    sampleItinerary: [
      { title: 'Arrive, Marina Bay', items: ['Check in, Gardens by the Bay evening light show', 'Marina Bay Sands SkyPark'] },
      { title: 'Sentosa Island', items: ['Universal Studios or beach day', 'Evening Wings of Time show'] },
      { title: 'Neighbourhoods & food', items: ['Chinatown & Buddha Tooth Relic Temple', 'Little India', 'Hawker centre dinner'] },
      { title: 'Free day / departure', items: ['Orchard Road shopping or Singapore Zoo', 'Departure'] },
    ],
    faqs: [
      { q: 'Is 4 days enough for Singapore?', a: 'Yes — it covers Marina Bay, Sentosa, and a couple of neighbourhoods comfortably.' },
      { q: 'Do Indians need a visa for Singapore?', a: 'Yes, an e-visa is required and is usually processed quickly online.' },
      { q: 'Is Singapore good for a family trip?', a: 'Very — clean, safe, easy transport, and attractions like Universal Studios and the zoo are built for families.' },
    ],
  },
  {
    slug: 'andaman-islands',
    city: 'Port Blair',
    country: 'India',
    label: 'Andaman Islands',
    emoji: '🏝️',
    tagline: 'Beaches, coral reefs, and India\'s clearest water',
    recommendedDays: 6,
    budgetINR: '₹65,000–₹80,000',
    metaTitle: 'Andaman Islands Trip Planner — 6-Day AI Itinerary & Budget',
    metaDescription:
      'Free AI Andaman Islands trip planner. Get a personalised 6-day itinerary covering Port Blair, Havelock, and Neil Island — with scuba diving, budget, and season tips.',
    keywords: ['Andaman Islands trip planner', 'Andaman itinerary', 'Havelock Island trip', 'Andaman budget trip', 'scuba diving Andaman'],
    imageQuery: 'Radhanagar Beach Andaman',
    heroImage: {
      url: 'https://images.pexels.com/photos/37949152/pexels-photo-37949152.jpeg?auto=compress&cs=tinysrgb&w=1600&h=900&fit=crop',
      photographer: 'Nabil Naidu',
      photographerUrl: 'https://www.pexels.com/@nabilnaidu',
    },
    overview: [
      "The Andaman Islands are India's best beach-and-reef destination, built around a few island hops by ferry — Port Blair for history and logistics, Havelock (Swaraj Dweep) for Radhanagar Beach and scuba diving, and Neil (Shaheed Dweep) for a quieter, smaller-scale version of the same.",
      "It's a genuinely different kind of India trip: clear water, coral reefs, and a slower island pace, with none of the usual heritage-circuit sightseeing pressure.",
    ],
    highlights: [
      'Radhanagar Beach, Havelock',
      'Scuba diving or snorkelling at Elephant Beach',
      'Cellular Jail light-and-sound show, Port Blair',
      'Bharatpur and Laxmanpur beaches, Neil Island',
      'Ferry-hopping between islands',
    ],
    bestTimeToVisit:
      'November–May for calm seas and good diving visibility. Avoid June–September (monsoon, rough ferry crossings).',
    budgetBreakdown: [
      { category: 'Flights (India round-trip to Port Blair)', amount: '₹15,000–₹25,000' },
      { category: 'Stay (6 nights)', amount: '₹18,000–₹25,000' },
      { category: 'Inter-island ferries', amount: '₹5,000–₹8,000' },
      { category: 'Diving/snorkelling & food', amount: '₹15,000–₹22,000' },
    ],
    sampleItinerary: [
      { title: 'Arrive Port Blair', items: ['Cellular Jail visit', 'Evening light-and-sound show'] },
      { title: 'Ferry to Havelock', items: ['Ferry transfer', 'Evening at Radhanagar Beach for sunset'] },
      { title: 'Havelock diving/beach', items: ['Scuba diving or snorkelling at Elephant Beach', 'Beach time at Radhanagar'] },
      { title: 'Ferry to Neil Island', items: ['Ferry transfer', 'Bharatpur Beach'] },
      { title: 'Neil Island', items: ['Laxmanpur Beach sunset', 'Natural rock bridge at low tide'] },
      { title: 'Return Port Blair / departure', items: ['Ferry back to Port Blair', 'Departure'] },
    ],
    faqs: [
      { q: 'How many days do you need for the Andamans?', a: '5–6 days covers Port Blair, Havelock, and Neil Island at a relaxed pace.' },
      { q: 'Do you need a permit to visit the Andamans?', a: 'Indian citizens don\'t need a special permit for Port Blair, Havelock, or Neil; some restricted tribal areas elsewhere do require one.' },
      { q: 'Is scuba diving in the Andamans good for beginners?', a: 'Yes — most dive schools on Havelock offer beginner (discover scuba) dives with no certification required.' },
    ],
  },
  {
    slug: 'new-york',
    city: 'New York City',
    country: 'USA',
    label: 'New York, USA',
    emoji: '🗽',
    tagline: 'Iconic skyline, world-class museums, and non-stop energy',
    recommendedDays: 7,
    budgetINR: '₹2,60,000–₹3,10,000',
    metaTitle: 'New York Trip Planner — 7-Day AI Itinerary & Budget Guide',
    metaDescription:
      'Free AI New York trip planner. Get a personalised 7-day NYC itinerary covering Manhattan, Central Park, the Statue of Liberty, and Brooklyn — with budget and visa tips.',
    keywords: ['New York trip planner', 'NYC itinerary', '7 days in New York', 'New York travel guide', 'New York budget trip'],
    heroImage: {
      url: 'https://images.pexels.com/photos/8569166/pexels-photo-8569166.jpeg?auto=compress&cs=tinysrgb&w=1600&h=900&fit=crop',
      photographer: 'Ivana Rodriguez',
      photographerUrl: 'https://www.pexels.com/@ivana-rodriguez-53736',
    },
    overview: [
      "New York rewards a borough-by-borough approach more than a single checklist — Manhattan's landmarks (Times Square, Central Park, the Empire State Building) anchor most itineraries, but a full week lets you add the Statue of Liberty, world-class museums, and a proper Brooklyn day without feeling rushed.",
      "The subway makes the whole city genuinely walkable-by-transit, so most days can mix 2–3 neighbourhoods without needing a car or ride-share.",
    ],
    highlights: [
      'Statue of Liberty & Ellis Island ferry',
      'Empire State Building or Top of the Rock views',
      'Central Park and the Metropolitan Museum of Art',
      'Times Square and a Broadway show',
      'Brooklyn Bridge walk and DUMBO',
    ],
    bestTimeToVisit:
      'April–June and September–November for mild weather; December is magical for holiday lights but very cold and crowded. Avoid peak summer humidity if possible.',
    budgetBreakdown: [
      { category: 'Flights (India round-trip)', amount: '₹70,000–₹1,00,000' },
      { category: 'Stay (7 nights)', amount: '₹80,000–₹1,10,000' },
      { category: 'Food', amount: '₹40,000–₹55,000' },
      { category: 'Attractions & a Broadway show', amount: '₹40,000–₹55,000' },
    ],
    sampleItinerary: [
      { title: 'Arrive, Times Square', items: ['Check in, evening in Times Square'] },
      { title: 'Downtown & Liberty', items: ['Statue of Liberty & Ellis Island ferry', 'One World Observatory'] },
      { title: 'Midtown', items: ['Empire State Building', 'Fifth Avenue shopping'] },
      { title: 'Central Park & museums', items: ['Central Park morning walk', 'Metropolitan Museum of Art'] },
      { title: 'Brooklyn', items: ['Brooklyn Bridge walk', 'DUMBO waterfront', 'Williamsburg in the evening'] },
      { title: 'Broadway & food', items: ['Chelsea Market', 'Evening Broadway show'] },
      { title: 'Free day / departure', items: ['Optional day trip or extra neighbourhood', 'Departure'] },
    ],
    faqs: [
      { q: 'How many days do you need in New York?', a: '5–7 days covers Manhattan\'s highlights plus a Brooklyn day without rushing.' },
      { q: 'Do Indians need a visa for the USA?', a: 'Yes, a US B1/B2 tourist visa is required and involves an in-person interview.' },
      { q: 'Is the subway easy to use for tourists?', a: 'Yes — a 7-day unlimited MetroCard/OMNY pass covers nearly all sightseeing without needing taxis.' },
    ],
  },
  {
    slug: 'bangkok',
    city: 'Bangkok',
    country: 'Thailand',
    label: 'Bangkok, Thailand',
    emoji: '🌸',
    tagline: 'Street food, ornate temples, and an easy short-haul trip',
    recommendedDays: 5,
    budgetINR: '₹50,000–₹65,000',
    metaTitle: 'Bangkok Trip Planner — 5-Day AI Itinerary & Budget Guide',
    metaDescription:
      'Free AI Bangkok trip planner. Get a personalised 5-day Bangkok itinerary covering the Grand Palace, Wat Pho, floating markets, and street food — with budget and visa tips.',
    keywords: ['Bangkok trip planner', 'Bangkok itinerary', '5 days in Bangkok', 'Bangkok travel guide', 'Bangkok budget trip'],
    imageQuery: 'Wat Pho Bangkok temple',
    heroImage: {
      url: 'https://images.pexels.com/photos/30540817/pexels-photo-30540817.jpeg?auto=compress&cs=tinysrgb&w=1600&h=900&fit=crop',
      photographer: 'Zaonar Saizainalin',
      photographerUrl: 'https://www.pexels.com/@zaonar-saizainalin-547935324',
    },
    overview: [
      "Bangkok works as both a standalone trip and the natural gateway to the rest of Thailand — a dense, chaotic, genuinely exciting city where ornate temples sit blocks away from rooftop bars and some of the best street food in the world.",
      "Five days covers the temple circuit, a floating market day trip, and enough time to just wander Chinatown or Chatuchak Market without feeling like you're racing a checklist.",
    ],
    highlights: [
      'The Grand Palace and Wat Phra Kaew',
      'Wat Pho\'s Reclining Buddha',
      'Damnoen Saduak floating market',
      'Chatuchak Weekend Market',
      'Street food crawl in Chinatown (Yaowarat)',
    ],
    bestTimeToVisit:
      'November–February (cool, dry season) is most comfortable. March–May is very hot; June–October is the rainy season with sudden but usually short downpours.',
    budgetBreakdown: [
      { category: 'Flights (India round-trip)', amount: '₹15,000–₹22,000' },
      { category: 'Stay (5 nights)', amount: '₹15,000–₹22,000' },
      { category: 'Food', amount: '₹10,000–₹14,000' },
      { category: 'Activities & transport', amount: '₹10,000–₹15,000' },
    ],
    sampleItinerary: [
      { title: 'Arrive, Old City', items: ['Check in, evening at Khao San Road'] },
      { title: 'Grand Palace & temples', items: ['The Grand Palace', 'Wat Pho', 'Wat Arun at sunset'] },
      { title: 'Floating market', items: ['Damnoen Saduak day trip', 'Evening street food in Chinatown'] },
      { title: 'Markets & modern Bangkok', items: ['Chatuchak Weekend Market (Sat/Sun)', 'Rooftop bar in the evening'] },
      { title: 'Free day / departure', items: ['Massage & spa or Jim Thompson House', 'Departure'] },
    ],
    faqs: [
      { q: 'How many days do you need in Bangkok?', a: '3–4 days covers the main sights; 5 days lets you add the floating market without rushing.' },
      { q: 'Do Indians need a visa for Thailand?', a: 'Indian passport holders can get a visa-on-arrival or apply for an e-visa in advance.' },
      { q: 'Is Bangkok good for a budget trip?', a: 'Yes — street food, public transport (BTS/MRT), and budget guesthouses make it one of the cheaper short-haul international trips.' },
    ],
  },
]

export const destinationBySlug = new Map(destinations.map((d) => [d.slug, d]))
