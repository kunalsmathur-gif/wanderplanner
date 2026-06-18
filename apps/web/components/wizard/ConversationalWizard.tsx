'use client'

import { useEffect, useMemo, useRef, useState } from 'react'
import { chatRefine, geocode, recommendCities, streamItinerary } from '@/lib/api'
import { useAppStore } from '@/store/appStore'
import { useItineraryStore } from '@/store/itineraryStore'
import { useTripConfigStore } from '@/store/tripConfigStore'
import { useWizardChatStore, type WizardField, type WizardMessage } from '@/store/wizardChatStore'
import type { Pace, RecommendedCity, TripConfig } from '@/types'
import { ListeningOrb } from '@/components/voice/ListeningOrb'
import { StampChip } from './StampChip'

type DateStage = 'preset' | 'custom-start' | 'custom-end'
type GroupStage = 'adults' | 'kids-count' | 'kids-ages'
type DestinationSubStage = 'input' | 'city-select' | 'suggest-select' | 'multi-city-confirm'

type RecognitionEvent = {
  results: ArrayLike<ArrayLike<{ transcript: string }>>
}

type RecognitionErrorEvent = {
  error?: string
}

type RecognitionInstance = {
  continuous: boolean
  interimResults: boolean
  lang: string
  onresult: ((event: RecognitionEvent) => void) | null
  onerror: ((event: RecognitionErrorEvent) => void) | null
  onend: (() => void) | null
  start: () => void
  stop: () => void
}

type RecognitionConstructor = new () => RecognitionInstance

declare global {
  interface Window {
    SpeechRecognition?: RecognitionConstructor
    webkitSpeechRecognition?: RecognitionConstructor
  }
}

const PURPOSE_CHIPS = [
  'Leisure 🏖️',
  'Adventure 🏔️',
  'Honeymoon 💑',
  'Family Vacation 👨‍👩‍👧',
  'Business + Leisure 💼',
  'Solo Backpacking 🎒',
  'Group Holiday 🎉',
]

const DESTINATION_MODE_CHIPS = ['Yes, I have one 📍', 'Suggest me! ✨', 'Exploring a country 🗺️']
const DURATION_CHIPS = ['3 days', '5 days', '7 days', '10 days', '14 days', 'Flexible']
const DATE_CHIPS = ['This month', 'Next month', 'In 3 months', 'Custom dates 📅', 'Flexible 🔄']
const BUDGET_CHIPS = ['50,000', '1,00,000', '2,50,000', '5,00,000', '10,00,000+']
const PACE_CHIPS = [
  'Relaxed 😌 (fewer activities, more leisure)',
  'Moderate ⚡ (balanced mix)',
  'Packed 🚀 (maximum experiences)',
]
const THEME_CHIPS = [
  '🏛️ Culture',
  '🍜 Food',
  '🧗 Adventure',
  '🌿 Nature',
  '🛍️ Shopping',
  '📸 Photography',
  '🌙 Nightlife',
  '⚽ Sports',
  'Skip →',
]
const ACCOMMODATION_CHIPS = [
  '🏨 Hotel',
  '🏡 Airbnb / Villa',
  '🛏️ Hostel',
  '🏕️ Resort',
  '🏢 Service Apartment',
  'No preference',
]
const SUMMARY_KEYS = ['purpose', 'origin', 'destination', 'dates', 'group', 'budget', 'accommodation', 'pace', 'themes'] as const

function botMessage(content: string, options?: Pick<WizardMessage, 'chips' | 'inputType'>): Omit<WizardMessage, 'id'> {
  return {
    role: 'bot',
    content,
    chips: options?.chips,
    inputType: options?.inputType,
  }
}

function stripEmoji(value: string) {
  return value.replace(/[\u{1F300}-\u{1FAFF}]/gu, '').replace(/\s+/g, ' ').trim()
}

function parseNumber(value: string) {
  const digits = value.replace(/[^\d]/g, '')
  return digits ? Number.parseInt(digits, 10) : Number.NaN
}

function isValidDate(value: string) {
  return /^\d{4}-\d{2}-\d{2}$/.test(value) && !Number.isNaN(Date.parse(value))
}

function formatBudget(amount: number) {
  return `INR ${amount.toLocaleString('en-IN')}`
}

function formatThemeLabel(themes: string[]) {
  return themes.length > 0 ? themes.join(', ') : 'None'
}

function formatDateLabel(dates: TripConfig['dates']) {
  if (dates.flexible) return dates.season ?? 'Flexible'
  if (dates.start && dates.end) return `${dates.start} → ${dates.end}`
  return dates.season ?? '—'
}

function formatGroupLabel(group: TripConfig['group']) {
  const segments = [`${group.adults} adult${group.adults === 1 ? '' : 's'}`]

  if (group.kids.length > 0) segments.push(`${group.kids.length} kid${group.kids.length === 1 ? '' : 's'}`)
  if (group.infants > 0) segments.push(`${group.infants} infant${group.infants === 1 ? '' : 's'}`)
  if (group.seniors > 0) segments.push(`${group.seniors} senior${group.seniors === 1 ? '' : 's'}`)
  if (group.pets > 0) segments.push(`${group.pets} pet${group.pets === 1 ? '' : 's'}`)

  return segments.join(' + ')
}

function recommendedCityChip(city: RecommendedCity) {
  return city.country && !city.name.toLowerCase().includes(city.country.toLowerCase())
    ? `${city.name}, ${city.country}`
    : city.name
}

function normalizeChipValue(value: string) {
  return stripEmoji(value).replace(/\s*,\s*/g, ', ').toLowerCase()
}

function findSuggestedCity(value: string, cities: RecommendedCity[]) {
  const normalizedValue = normalizeChipValue(value)
  return cities.find((city) => {
    const chipLabel = normalizeChipValue(recommendedCityChip(city))
    const cityLabel = normalizeChipValue(city.name)
    const cityWithCountry = normalizeChipValue(`${city.name}, ${city.country}`)
    return normalizedValue === chipLabel || normalizedValue === cityLabel || normalizedValue === cityWithCountry
  })
}

function formatDestinationLabel(config: TripConfig) {
  if (config.destination) {
    return [config.destination.city, config.destination.country].filter(Boolean).join(', ')
  }

  return config.destination_country ?? '—'
}

function mergeTripConfig(base: TripConfig, patch: Partial<TripConfig>): TripConfig {
  return {
    ...base,
    ...patch,
    dates: patch.dates ? { ...base.dates, ...patch.dates } : base.dates,
    origin: patch.origin ? { ...base.origin, ...patch.origin } : base.origin,
    destination: patch.destination === undefined ? base.destination : patch.destination,
    group: patch.group ? { ...base.group, ...patch.group } : base.group,
    accommodation: patch.accommodation ? { ...base.accommodation, ...patch.accommodation } : base.accommodation,
    budget: patch.budget ? { ...base.budget, ...patch.budget } : base.budget,
  }
}

function promptForField(field: WizardField, config: TripConfig): Omit<WizardMessage, 'id'> {
  switch (field) {
    case 'purpose':
      return botMessage("What's the occasion for this trip?", { chips: PURPOSE_CHIPS })
    case 'origin':
      return botMessage('Great! Where are you traveling from? (Type your city)', { inputType: 'text' })
    case 'destination_mode':
      return botMessage('Do you have a destination in mind?', { chips: DESTINATION_MODE_CHIPS })
    case 'duration':
      return botMessage('How many days do you have for this trip?', { chips: DURATION_CHIPS })
    case 'destination':
      if (config.destination_mode === 'country') {
        return botMessage('Which country?', { inputType: 'text' })
      }
      if (config.destination_mode === 'exploring') {
        return botMessage("Describe what you're looking for", { inputType: 'text' })
      }
      return botMessage('Where would you like to go?', { inputType: 'text' })
    case 'dates':
      return botMessage('When are you planning to travel?', { chips: DATE_CHIPS })
    case 'group':
      return botMessage('How many adults are traveling?', { inputType: 'number' })
    case 'budget':
      return botMessage("What's your approximate budget in INR?", { chips: BUDGET_CHIPS, inputType: 'number' })
    case 'accommodation':
      return botMessage('What type of accommodation do you prefer?', { chips: ACCOMMODATION_CHIPS })
    case 'pace':
      return botMessage("What's your travel style?", { chips: PACE_CHIPS })
    case 'themes':
      return botMessage('Any travel themes? (choose multiple or skip)', { chips: THEME_CHIPS })
    case 'city_selection':
      return botMessage('Which city would you like to visit?', { inputType: 'text' })
    case 'refinement':
      return botMessage(
        "Almost there! 🙌 Before I generate your itinerary, is there anything else you'd like to add or change?",
        { chips: ['Looks good, proceed ✓'], inputType: 'text' },
      )
    case 'done':
      return botMessage('Everything looks good — review your summary below.')
  }
}

async function resolvePlace(query: string): Promise<{ city: string; country: string; lat: number; lon: number } | null> {
  try {
    const result = await geocode(query)
    const parts = result.display_name.split(',').map((part) => part.trim()).filter(Boolean)

    return {
      city: parts[0] ?? query.trim(),
      country: parts[parts.length - 1] ?? result.country_code.toUpperCase(),
      lat: result.lat,
      lon: result.lon,
    }
  } catch (error) {
    // Geocoding failed - return null to signal failure
    return null
  }
}

function paceFromLabel(value: string): Pace {
  const lowerValue = value.toLowerCase()
  if (value.startsWith('Relaxed') || lowerValue.includes('relaxed') || lowerValue.includes('slow') || lowerValue.includes('easy') || lowerValue.includes('laid back') || lowerValue.includes('chill')) return 'relaxed'
  if (value.startsWith('Packed') || lowerValue.includes('packed') || lowerValue.includes('fast') || lowerValue.includes('busy') || lowerValue.includes('intense') || lowerValue.includes('action')) return 'packed'
  return 'moderate'
}

function themeFromChip(chip: string) {
  return stripEmoji(chip).replace('Skip →', '').trim()
}

export function ConversationalWizard() {
  const wizardOpen = useAppStore((state) => state.wizardOpen)
  const closeWizard = useAppStore((state) => state.closeWizard)

  const tripConfig = useTripConfigStore((state) => state.config)
  const updateConfig = useTripConfigStore((state) => state.updateConfig)
  const updateDates = useTripConfigStore((state) => state.updateDates)
  const updateBudget = useTripConfigStore((state) => state.updateBudget)
  const updateGroup = useTripConfigStore((state) => state.updateGroup)
  const setOrigin = useTripConfigStore((state) => state.setOrigin)
  const setDestination = useTripConfigStore((state) => state.setDestination)

  const days = useItineraryStore((state) => state.days)
  const itineraryStatus = useItineraryStore((state) => state.status)
  const itineraryProgress = useItineraryStore((state) => state.progress)
  const itineraryError = useItineraryStore((state) => state.error)
  const setDays = useItineraryStore((state) => state.setDays)
  const setStatus = useItineraryStore((state) => state.setStatus)
  const setProgress = useItineraryStore((state) => state.setProgress)
  const setError = useItineraryStore((state) => state.setError)

  const messages = useWizardChatStore((state) => state.messages)
  const currentField = useWizardChatStore((state) => state.currentField)
  const phase = useWizardChatStore((state) => state.phase)
  const collectedLabels = useWizardChatStore((state) => state.collectedLabels)
  const addMessage = useWizardChatStore((state) => state.addMessage)
  const setCurrentField = useWizardChatStore((state) => state.setCurrentField)
  const setPhase = useWizardChatStore((state) => state.setPhase)
  const addLabel = useWizardChatStore((state) => state.addLabel)

  const [input, setInput] = useState('')
  const [dateStage, setDateStage] = useState<DateStage>('preset')
  const [groupStage, setGroupStage] = useState<GroupStage>('adults')
  const [destinationSubStage, setDestinationSubStage] = useState<DestinationSubStage>('input')
  const [suggestedCities, setSuggestedCities] = useState<RecommendedCity[]>([])
  const [pendingThemeSelections, setPendingThemeSelections] = useState<string[]>([])
  const [pendingStartDate, setPendingStartDate] = useState<string | null>(null)
  const [pendingKidsCount, setPendingKidsCount] = useState(0)
  const [isProcessing, setIsProcessing] = useState(false)
  const [isRecording, setIsRecording] = useState(false)
  const [voiceModeActive, setVoiceModeActive] = useState(false)

  const messagesEndRef = useRef<HTMLDivElement>(null)
  const recognitionRef = useRef<RecognitionInstance | null>(null)
  const streamCleanupRef = useRef<(() => void) | null>(null)
  const speechSynthesisRef = useRef<SpeechSynthesisUtterance | null>(null)
  const [isSpeaking, setIsSpeaking] = useState(false)

  const hasExistingItinerary = days.length > 0
  const completedCount = SUMMARY_KEYS.filter((key) => collectedLabels[key]).length
  const progressPercent = phase === 'summary' || phase === 'generating' || phase === 'done'
    ? 100
    : Math.round((completedCount / SUMMARY_KEYS.length) * 100)

  const currentPrompt = useMemo(() => {
    const latestBotMessage = [...messages].reverse().find((message) => message.role === 'bot')
    return latestBotMessage ?? null
  }, [messages])

  const currentInputType = useMemo(() => {
    if (phase !== 'chatting') return 'text'
    if (currentField === 'dates' && (dateStage === 'custom-start' || dateStage === 'custom-end')) return 'date'
    if (currentField === 'group' && groupStage !== 'kids-ages') return 'number'
    if (currentField === 'budget') return 'number'
    return currentPrompt?.inputType ?? 'text'
  }, [currentField, currentPrompt?.inputType, dateStage, groupStage, phase])

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
    
    // Auto-speak latest bot message when voice mode is active
    if (voiceModeActive && messages.length > 0) {
      const lastMessage = messages[messages.length - 1]
      if (lastMessage.role === 'bot') {
        speakMessage(lastMessage.content)
      }
    }
  }, [messages, phase, itineraryProgress.message, voiceModeActive])

  useEffect(() => {
    if (!wizardOpen) return
    if (phase === 'done') {
      setPhase('summary')
      addMessage(botMessage('Welcome back! Your trip details are below. You can refine them or regenerate the itinerary.'))
    }
    if (messages.length === 0) {
      addMessage(botMessage("Hi! I'm Anya from WanderPlan 👋\n\nI'm here to help you plan your perfect trip. Let's get started!\n\nWhat's the main purpose of your trip?", { chips: PURPOSE_CHIPS }))
    }
  }, [addMessage, messages.length, phase, setPhase, tripConfig, wizardOpen])

  useEffect(() => () => {
    streamCleanupRef.current?.()
    recognitionRef.current?.stop()
    if (typeof window !== 'undefined' && window.speechSynthesis) {
      window.speechSynthesis.cancel()
    }
  }, [])

  // Preload voices on mount
  useEffect(() => {
    if (typeof window !== 'undefined' && window.speechSynthesis) {
      // Some browsers require calling getVoices() first to trigger voice loading
      window.speechSynthesis.getVoices()
      // Listen for voiceschanged event (for browsers that load voices asynchronously)
      window.speechSynthesis.addEventListener('voiceschanged', () => {
        window.speechSynthesis.getVoices()
      })
    }
  }, [])

  function speakMessage(text: string) {
    if (typeof window === 'undefined' || !window.speechSynthesis) return
    
    // Stop any ongoing speech
    window.speechSynthesis.cancel()
    
    // Strip markdown formatting and emojis for cleaner speech
    const cleanText = text
      .replace(/[*_~`#]/g, '')
      .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
      .replace(/[^\w\s.,!?'-]/g, '')
      .trim()
    
    if (!cleanText) return
    
    const utterance = new SpeechSynthesisUtterance(cleanText)
    utterance.lang = 'en-IN'
    
    // Select a young Indian female voice
    const voices = window.speechSynthesis.getVoices()
    const preferredVoice = voices.find(voice => 
      // Look for Indian English female voices
      (voice.lang.includes('en-IN') || voice.lang.includes('en_IN')) && 
      voice.name.toLowerCase().includes('female')
    ) || voices.find(voice =>
      // Fallback: any English female voice
      voice.lang.startsWith('en') && 
      (voice.name.toLowerCase().includes('female') || voice.name.toLowerCase().includes('woman'))
    ) || voices.find(voice =>
      // Fallback: Google/Microsoft Indian voices (usually female by default)
      voice.lang.includes('en-IN') || voice.name.toLowerCase().includes('india')
    )
    
    if (preferredVoice) {
      utterance.voice = preferredVoice
    }
    
    // Voice characteristics for young female (20-25 yrs)
    utterance.rate = 1.05      // Slightly faster - energetic
    utterance.pitch = 1.15     // Higher pitch for young female voice
    utterance.volume = 1.0
    
    utterance.onstart = () => setIsSpeaking(true)
    utterance.onend = () => setIsSpeaking(false)
    utterance.onerror = () => setIsSpeaking(false)
    
    speechSynthesisRef.current = utterance
    window.speechSynthesis.speak(utterance)
  }

  function stopSpeaking() {
    if (typeof window !== 'undefined' && window.speechSynthesis) {
      window.speechSynthesis.cancel()
      setIsSpeaking(false)
    }
  }

  function resetDestinationSelectionState() {
    setDestinationSubStage('input')
    setSuggestedCities([])
  }

  function syncLabelsForPatch(nextConfig: TripConfig, patch: Partial<TripConfig>) {
    if (patch.purpose !== undefined) addLabel('purpose', nextConfig.purpose)
    if (patch.origin !== undefined) addLabel('origin', nextConfig.origin.city || '—')

    if (
      patch.destination !== undefined
      || patch.destination_country !== undefined
      || patch.destination_mode !== undefined
    ) {
      addLabel('destination', formatDestinationLabel(nextConfig))
    }

    if (patch.dates !== undefined) addLabel('dates', formatDateLabel(nextConfig.dates))
    if (patch.group !== undefined) addLabel('group', formatGroupLabel(nextConfig.group))
    if (patch.budget !== undefined) addLabel('budget', formatBudget(nextConfig.budget.amount))
    if (patch.pace !== undefined) addLabel('pace', nextConfig.pace.charAt(0).toUpperCase() + nextConfig.pace.slice(1))
    if (patch.themes !== undefined) addLabel('themes', formatThemeLabel(nextConfig.themes))
  }

  function applyConfigPatch(patch: Partial<TripConfig>) {
    const currentConfig = useTripConfigStore.getState().config
    const nextConfig = mergeTripConfig(currentConfig, patch)
    updateConfig(nextConfig)
    syncLabelsForPatch(nextConfig, patch)
  }

  function pushNextField(field: Exclude<WizardField, 'done'>) {
    if (field === 'destination') {
      resetDestinationSelectionState()
    }

    if (field === 'dates') {
      resetDestinationSelectionState()
      setDateStage('preset')
      setPendingStartDate(null)
    }

    if (field === 'group') {
      setGroupStage('adults')
      setPendingKidsCount(0)
    }

    if (field === 'themes') {
      setPendingThemeSelections([])
    }

    setCurrentField(field)
    addMessage(promptForField(field, useTripConfigStore.getState().config))
  }

  function moveToRefinement() {
    setPendingThemeSelections([])
    setCurrentField('refinement')
    addMessage(promptForField('refinement', useTripConfigStore.getState().config))
  }

  function moveToSummary() {
    setCurrentField('done')
    setPhase('summary')
    addMessage(promptForField('done', useTripConfigStore.getState().config))
  }

  function postValidationError(message: string) {
    addMessage(botMessage(message, { inputType: currentInputType }))
  }

  async function handleAnswer(rawValue: string) {
    const value = rawValue.trim()
    if (!value || isProcessing || (phase !== 'chatting' && phase !== 'summary')) return

    addMessage({ role: 'user', content: value })
    setInput('')
    setIsProcessing(true)

    try {
      if (phase === 'summary') {
        const wizardMessages = useWizardChatStore.getState().messages.map((message) => ({
          role: message.role === 'bot' ? 'assistant' : 'user',
          content: message.content,
        }))
        const allMessages = [
          ...(wizardMessages[wizardMessages.length - 1]?.role === 'user' && wizardMessages[wizardMessages.length - 1]?.content === value
            ? wizardMessages.slice(0, -1)
            : wizardMessages),
          { role: 'user', content: value },
        ]

        const result = await chatRefine(allMessages, useTripConfigStore.getState().config)
        if (result.config_patch) applyConfigPatch(result.config_patch)
        addMessage(botMessage(result.reply))
        return
      }

      if (currentField === 'purpose') {
        const trimmed = stripEmoji(value).trim()
        
        // Minimum length validation
        if (trimmed.length < 5) {
          addMessage(botMessage(
            `Please provide more detail about your trip purpose. For example: "birthday celebration", "honeymoon", "family reunion", "Diwali festival"`,
            { chips: PURPOSE_CHIPS }
          ))
          return
        }
        
        updateConfig({ purpose: trimmed })
        addLabel('purpose', trimmed)
        pushNextField('origin')
        return
      }

      if (currentField === 'origin') {
        // Validate minimum length (reject very short inputs like "Ad")
        if (value.trim().length < 3) {
          addMessage(botMessage(
            `Please enter at least 3 characters. Try your city name (e.g., "Mumbai", "Delhi", "Bangalore")`,
            { inputType: 'text' }
          ))
          return
        }
        
        const place = await resolvePlace(value)
        
        if (!place) {
          // Geocoding failed - invalid location
          addMessage(botMessage(
            `Hmm, I couldn't find "${value}". Could you try again with a city name? (e.g., "Mumbai", "New Delhi", "Bangalore")`,
            { inputType: 'text' }
          ))
          return
        }
        
        setOrigin({ city: place.city, iata: '', lat: place.lat, lon: place.lon })
        addLabel('origin', place.city)
        pushNextField('destination_mode')
        return
      }

      if (currentField === 'destination_mode') {
        resetDestinationSelectionState()

        const lowerValue = value.toLowerCase()
        
        // Try to match user's text to intended mode
        if (value.startsWith('Yes') || lowerValue.includes('yes') || lowerValue.includes('know') || lowerValue.includes('decided') || lowerValue.includes('have one') || lowerValue.includes('specific')) {
          // Fixed destination - user knows exactly where they want to go
          updateConfig({ destination_mode: 'fixed', destination_country: null })
          setDestination(null)
          pushNextField('destination')
        } else if (value.startsWith('Suggest') || lowerValue.includes('suggest') || lowerValue.includes('recommend') || lowerValue.includes('help') || lowerValue.includes('idea')) {
          // AI suggests destinations based on user preferences - ask for preferences FIRST, then duration
          updateConfig({ destination_mode: 'exploring', destination_country: null })
          setDestination(null)
          pushNextField('destination')  // Go to destination (which asks for preferences in exploring mode)
        } else if (value.startsWith('Exploring') || lowerValue.includes('exploring') || lowerValue.includes('country') || lowerValue.includes('nation') || lowerValue.includes('within')) {
          // User picks country, then selects cities (can be multiple)
          updateConfig({ destination_mode: 'country', destination_country: null })
          setDestination(null)
          pushNextField('destination')
        } else {
          // Unrecognized response - ask for clarification
          addMessage(botMessage(
            "I didn't quite understand. Do you:\n• Have a specific destination in mind?\n• Want me to suggest destinations?\n• Want to explore cities within a country?",
            { chips: DESTINATION_MODE_CHIPS }
          ))
          return
        }

        return
      }

      if (currentField === 'duration') {
        // Extract number of days from the response
        const daysMatch = value.match(/(\d+)/)
        if (daysMatch) {
          const days = parseInt(daysMatch[1], 10)
          updateDates({ duration_days: days })
          addLabel('duration', `${days} days`)
        } else if (value.toLowerCase().includes('flexible')) {
          updateDates({ duration_days: undefined })
          addLabel('duration', 'Flexible')
        }
        
        pushNextField('destination')
        return
      }

      if (currentField === 'destination') {
        const config = useTripConfigStore.getState().config
        const mode = config.destination_mode

        if (mode === 'fixed') {
          const place = await resolvePlace(value)
          
          if (!place) {
            // Geocoding failed - invalid location
            addMessage(botMessage(
              `I couldn't find "${value}". Please enter a valid city or destination (e.g., "Paris, France", "Tokyo, Japan")`,
              { inputType: 'text' }
            ))
            return
          }
          
          setDestination({ city: place.city, country: place.country, lat: place.lat, lon: place.lon })
          updateConfig({ destination_country: null })
          addLabel('destination', value || `${place.city}, ${place.country}`)
          pushNextField('dates')
          return
        }

        if (mode === 'country' && destinationSubStage === 'input') {
          updateConfig({ destination_country: value })
          setDestination(null)
          setDestinationSubStage('city-select')

          try {
            const { cities } = await recommendCities(value, config)
            const nextCities = cities.slice(0, 5)
            setSuggestedCities(nextCities)

            if (nextCities.length > 0) {
              addMessage(botMessage(
                `Here are some popular cities in ${value}! Which one catches your eye?`,
                { chips: nextCities.map(recommendedCityChip) },
              ))
            } else {
              addMessage(botMessage(`Which city in ${value} would you like to visit?`, { inputType: 'text' }))
            }
          } catch {
            addMessage(botMessage(`Which city in ${value} would you like to visit?`, { inputType: 'text' }))
          }

          return
        }

        if (mode === 'country' && destinationSubStage === 'city-select') {
          const matchedCity = findSuggestedCity(value, suggestedCities)

          if (matchedCity) {
            setDestination({
              city: matchedCity.name,
              country: matchedCity.country,
              lat: matchedCity.lat,
              lon: matchedCity.lon,
            })
            updateConfig({ destination_country: matchedCity.country })
            addLabel('destination', recommendedCityChip(matchedCity))
          } else {
            const place = await resolvePlace(config.destination_country ? `${value}, ${config.destination_country}` : value)
            
            if (!place) {
              // Geocoding failed
              addMessage(botMessage(
                `I couldn't find "${value}". Please enter a valid city name from ${config.destination_country || 'your chosen destination'}.`,
                { inputType: 'text' }
              ))
              return
            }
            
            setDestination({ city: place.city, country: place.country, lat: place.lat, lon: place.lon })
            updateConfig({ destination_country: config.destination_country ?? place.country })
            addLabel('destination', value)
          }

          // Ask if user wants to add another city
          setDestinationSubStage('multi-city-confirm')
          addMessage(botMessage(
            'Would you like to add another city to your trip?',
            { chips: ['Yes, add another city ➕', 'No, continue ✓'] }
          ))
          return
        }

        if (mode === 'country' && destinationSubStage === 'multi-city-confirm') {
          if (value.startsWith('Yes')) {
            // User wants to add another city
            setDestinationSubStage('city-select')
            const currentDestination = useTripConfigStore.getState().config.destination
            
            // Show remaining cities or allow typing
            const remainingCities = suggestedCities.filter(c => 
              c.name !== currentDestination?.city
            )
            
            if (remainingCities.length > 0) {
              addMessage(botMessage(
                'Great! Which other city would you like to visit?',
                { chips: remainingCities.map(recommendedCityChip) }
              ))
            } else {
              addMessage(botMessage(
                'Which other city would you like to add?',
                { inputType: 'text' }
              ))
            }
            return
          } else {
            // User is done adding cities, proceed to dates
            pushNextField('dates')
            return
          }
        }

        if (mode === 'exploring' && destinationSubStage === 'input') {
          setDestination(null)
          
          try {
            const { cities } = await recommendCities(value, config)
            const nextCities = cities.slice(0, 5)

            if (nextCities.length > 0) {
              setSuggestedCities(nextCities)
              setDestinationSubStage('suggest-select')
              addLabel('destination', `Preferences: ${value}`)
              addMessage(botMessage(
                "Here are some destinations that match what you're looking for! Which one would you like?",
                { chips: nextCities.map(recommendedCityChip) },
              ))
              return
            }
          } catch (err) {
            console.error('Failed to recommend cities:', err)
          }

          // If no cities returned, ask for a country or region as fallback
          addMessage(botMessage(
            "I couldn't find specific destinations for that. Could you tell me which country or region you're interested in?",
            { inputType: 'text' }
          ))
          // Stay in 'input' substage to get a valid location
          return
        }

        if (mode === 'exploring' && destinationSubStage === 'suggest-select') {
          const matchedCity = findSuggestedCity(value, suggestedCities)

          if (matchedCity) {
            setDestination({
              city: matchedCity.name,
              country: matchedCity.country,
              lat: matchedCity.lat,
              lon: matchedCity.lon,
            })
            updateConfig({ destination_country: matchedCity.country })
            addLabel('destination', recommendedCityChip(matchedCity))
          } else {
            const place = await resolvePlace(value)
            
            if (!place) {
              // Geocoding failed
              addMessage(botMessage(
                `I couldn't find "${value}". Please enter a valid city or destination name.`,
                { inputType: 'text' }
              ))
              return
            }
            
            setDestination({ city: place.city, country: place.country, lat: place.lat, lon: place.lon })
            updateConfig({ destination_country: place.country })
            addLabel('destination', value)
          }

          pushNextField('dates')
          return
        }
      }

      if (currentField === 'dates') {
        if (dateStage === 'preset') {
          const lowerValue = value.toLowerCase()
          
          if (value.startsWith('Custom dates') || lowerValue.includes('custom') || lowerValue.includes('specific') || lowerValue.includes('exact')) {
            setDateStage('custom-start')
            addMessage(botMessage('Start date? (YYYY-MM-DD)', { inputType: 'date' }))
            return
          }

          if (value.startsWith('Flexible') || lowerValue.includes('flexible') || lowerValue.includes('not sure') || lowerValue.includes("don't know") || lowerValue.includes('any time')) {
            updateDates({ start: null, end: null, flexible: true, season: 'Flexible' })
            addLabel('dates', 'Flexible')
          } else if (lowerValue.includes('this month') || lowerValue.includes('soon')) {
            updateDates({ start: null, end: null, flexible: false, season: 'This month' })
            addLabel('dates', 'This month')
          } else if (lowerValue.includes('next month')) {
            updateDates({ start: null, end: null, flexible: false, season: 'Next month' })
            addLabel('dates', 'Next month')
          } else if (lowerValue.includes('3 months') || lowerValue.includes('three months')) {
            updateDates({ start: null, end: null, flexible: false, season: 'In 3 months' })
            addLabel('dates', 'In 3 months')
          } else {
            // Try to use the text as-is (might be a season or timeframe)
            updateDates({ start: null, end: null, flexible: false, season: value })
            addLabel('dates', value)
          }

          pushNextField('group')
          return
        }

        if (!isValidDate(value)) {
          postValidationError('Please enter a valid date in YYYY-MM-DD format.')
          return
        }

        if (dateStage === 'custom-start') {
          setPendingStartDate(value)
          setDateStage('custom-end')
          addMessage(botMessage('End date? (YYYY-MM-DD)', { inputType: 'date' }))
          return
        }

        if (!pendingStartDate || value < pendingStartDate) {
          postValidationError('End date must be on or after the start date.')
          return
        }

        updateDates({ start: pendingStartDate, end: value, flexible: false, season: undefined })
        addLabel('dates', `${pendingStartDate} → ${value}`)
        setPendingStartDate(null)
        setDateStage('preset')
        pushNextField('group')
        return
      }

      if (currentField === 'group') {
        if (groupStage === 'adults') {
          const adults = parseNumber(value)
          if (!Number.isFinite(adults) || adults < 1) {
            postValidationError('Please enter at least 1 adult.')
            return
          }

          updateGroup({ adults })
          setGroupStage('kids-count')
          addMessage(botMessage('Any kids? (number or 0)', { inputType: 'number' }))
          return
        }

        if (groupStage === 'kids-count') {
          const kidsCount = parseNumber(value)
          if (!Number.isFinite(kidsCount) || kidsCount < 0) {
            postValidationError('Please enter the number of kids, or 0.')
            return
          }

          if (kidsCount === 0) {
            updateGroup({ kids: [] })
            addLabel('group', `${useTripConfigStore.getState().config.group.adults} adults`)
            setGroupStage('adults')
            pushNextField('budget')
            return
          }

          setPendingKidsCount(kidsCount)
          setGroupStage('kids-ages')
          addMessage(botMessage(`Please enter ${kidsCount} kid age${kidsCount > 1 ? 's' : ''} separated by commas.`, { inputType: 'text' }))
          return
        }

        const ages = value
          .split(',')
          .map((part) => Number.parseInt(part.trim(), 10))
          .filter((age) => Number.isFinite(age))

        if (ages.length !== pendingKidsCount) {
          postValidationError(`Please enter exactly ${pendingKidsCount} age${pendingKidsCount > 1 ? 's' : ''} separated by commas.`)
          return
        }

        updateGroup({ kids: ages.map((age) => ({ age })) })
        const adults = useTripConfigStore.getState().config.group.adults
        addLabel('group', `${adults} adults + ${ages.length} kid${ages.length > 1 ? 's' : ''}`)
        setPendingKidsCount(0)
        setGroupStage('adults')
        pushNextField('budget')
        return
      }

      if (currentField === 'budget') {
        const amount = parseNumber(value)
        if (!Number.isFinite(amount) || amount <= 0) {
          postValidationError('Please enter a valid budget in INR.')
          return
        }

        updateBudget({ amount, currency: 'INR' })
        addLabel('budget', formatBudget(amount))
        pushNextField('accommodation')
        return
      }

      if (currentField === 'accommodation') {
        const style = value === 'No preference' ? [] : [stripEmoji(value).trim()]
        updateConfig({ accommodation: { ...useTripConfigStore.getState().config.accommodation, style } })
        addLabel('accommodation', value === 'No preference' ? 'No preference' : stripEmoji(value).trim())
        pushNextField('pace')
        return
      }

      if (currentField === 'pace') {
        const pace = paceFromLabel(value)
        updateConfig({ pace })
        addLabel('pace', pace.charAt(0).toUpperCase() + pace.slice(1))
        pushNextField('themes')
        return
      }

      if (currentField === 'themes') {
        if (value === 'Skip →') {
          setPendingThemeSelections([])
          addLabel('themes', formatThemeLabel(useTripConfigStore.getState().config.themes))
          moveToRefinement()
          return
        }

        const selectedThemes = value.includes(',')
          ? value.split(',').map((part) => part.trim()).filter(Boolean).map(themeFromChip)
          : [themeFromChip(value)]

        const nextThemes = Array.from(new Set([...useTripConfigStore.getState().config.themes, ...selectedThemes]))
        updateConfig({ themes: nextThemes })
        addLabel('themes', formatThemeLabel(nextThemes))

        if (value.includes(',')) {
          setPendingThemeSelections([])
          moveToRefinement()
          return
        }

        addMessage(botMessage(`Added ${selectedThemes.join(', ')}. Any other themes or skip?`, { chips: THEME_CHIPS }))
      }

      if (currentField === 'refinement') {
        const normalized = value.toLowerCase().trim()
        if (normalized === 'looks good, proceed ✓' || normalized === 'looks good' || normalized === 'proceed' || normalized === 'ok' || normalized === 'done') {
          moveToSummary()
          return
        }
        // User added a refinement — run it through chatRefine
        const wizardMessages = useWizardChatStore.getState().messages.map((message) => ({
          role: message.role === 'bot' ? 'assistant' : 'user',
          content: message.content,
        }))
        const result = await chatRefine(wizardMessages, useTripConfigStore.getState().config)
        if (result.config_patch) applyConfigPatch(result.config_patch)
        addMessage(botMessage(result.reply))
        addMessage(botMessage('Anything else, or shall we proceed?', { chips: ['Looks good, proceed ✓'], inputType: 'text' }))
      }
    } catch (err) {
      const isNetworkError = err instanceof TypeError || (err as { code?: string })?.code === 'ECONNREFUSED'
        || String(err).includes('Network Error') || String(err).includes('fetch')
      if (isNetworkError) {
        addMessage(botMessage('⚠️ Could not reach the server. Please make sure the backend is running and try again.', { inputType: currentInputType }))
      } else if (currentField === 'origin' || (currentField === 'destination' && useTripConfigStore.getState().config.destination_mode === 'fixed')) {
        addMessage(botMessage("I couldn't find that location, please try again", { inputType: 'text' }))
      } else {
        addMessage(botMessage('Sorry, something went wrong. Please try again.'))
      }
    } finally {
      setIsProcessing(false)
    }
  }

  function handleChipSelect(chip: string) {
    void handleAnswer(chip)
  }

  function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    void handleAnswer(input)
  }

  function handleEditLastStep() {
    setPendingThemeSelections([])
    setPhase('chatting')
    setCurrentField('themes')
    addMessage(promptForField('themes', useTripConfigStore.getState().config))
  }

  function handleGenerate() {
    setPhase('generating')
    setStatus('loading')
    setProgress({ message: 'Starting your itinerary...', step: 0, total: 4 })
    addMessage(botMessage('Perfect! Building your itinerary...'))

    streamCleanupRef.current?.()
    const cleanup = streamItinerary(
      useTripConfigStore.getState().config,
      (message, step, total) => {
        setProgress({ message, step, total })
      },
      (result) => {
        setDays(result.days, result.alignment_score, result.expense_breakdown)
        setPhase('done')
        addMessage(botMessage('🎉 Your itinerary is ready! Click "View Itinerary" below to explore it, or keep refining your trip here.'))
        streamCleanupRef.current = null
      },
      (code, message, retryable) => {
        setError({ code, message, retryable })
        setPhase('summary')
        addMessage(botMessage(message))
        streamCleanupRef.current = null
      },
    )

    streamCleanupRef.current = cleanup
  }

  function toggleVoiceMode() {
    if (typeof window === 'undefined') return

    // If already active, turn off
    if (voiceModeActive) {
      recognitionRef.current?.stop()
      stopSpeaking()
      setVoiceModeActive(false)
      setIsRecording(false)
      return
    }

    // Check if speech recognition is supported
    const Recognition = window.SpeechRecognition ?? window.webkitSpeechRecognition
    if (!Recognition) {
      addMessage(botMessage('Voice mode is not supported in this browser.'))
      return
    }

    // Activate voice mode
    setVoiceModeActive(true)
    
    // Speak the latest bot message
    const lastBotMsg = [...messages].reverse().find(m => m.role === 'bot')
    if (lastBotMsg) {
      speakMessage(lastBotMsg.content)
    }
    
    // Start listening
    const recognition = new Recognition()
    recognition.continuous = false
    recognition.interimResults = false
    recognition.lang = 'en-IN'
    recognition.onresult = (event) => {
      const transcript = event.results[0]?.[0]?.transcript?.trim() ?? ''
      if (transcript) setInput(transcript)
    }
    recognition.onerror = () => {
      setIsRecording(false)
    }
    recognition.onend = () => {
      setIsRecording(false)
      recognitionRef.current = null
      // Auto-restart listening if voice mode is still active
      if (voiceModeActive && !isProcessing) {
        setTimeout(() => {
          if (voiceModeActive) {
            const newRecognition = new Recognition()
            Object.assign(newRecognition, {
              continuous: false,
              interimResults: false,
              lang: 'en-IN',
              onresult: recognition.onresult,
              onerror: recognition.onerror,
              onend: recognition.onend,
            })
            recognitionRef.current = newRecognition
            setIsRecording(true)
            newRecognition.start()
          }
        }, 500)
      }
    }

    recognitionRef.current = recognition
    setIsRecording(true)
    recognition.start()
  }

  return (
    <div className="mx-4 flex h-[85vh] max-h-[600px] w-full max-w-[900px] flex-col overflow-hidden rounded-3xl bg-white shadow-2xl">
      {/* Redesigned Anya Header */}
      <div className="relative overflow-hidden bg-[#1A3A52] px-6 py-5">
        {/* Subtle map texture background */}
        <div 
          className="absolute inset-0 opacity-5" 
          style={{
            backgroundImage: 'url("data:image/svg+xml,%3Csvg width=\'60\' height=\'60\' xmlns=\'http://www.w3.org/2000/svg\'%3E%3Cpath d=\'M0 0h60v60H0z\' fill=\'none\'/%3E%3Cpath d=\'M30 0v60M0 30h60\' stroke=\'%23fff\' stroke-width=\'0.5\'/%3E%3C/svg%3E")'
          }} 
        />
        
        <div className="relative flex items-start justify-between gap-4">
          <div>
            <h1 
              className="font-display text-[28px] font-bold leading-none text-white" 
              style={{ fontVariationSettings: '"WONK" 1, "opsz" 144' }}
            >
              Anya
            </h1>
            <p className="mt-1 font-body text-[13px] font-medium tracking-tight text-[#A8BFDB]">
              Your AI travel companion — tap the orb to chat by voice
            </p>
          </div>
          <div className="flex items-center gap-3">
            <button
              onClick={toggleVoiceMode}
              className="transition-transform hover:scale-105"
              aria-label={voiceModeActive ? 'Deactivate voice mode' : 'Activate voice mode'}
              type="button"
            >
              <ListeningOrb 
                isActive={voiceModeActive}
                isRecording={isRecording}
              />
            </button>
            {hasExistingItinerary && (
              <button
                type="button"
                onClick={closeWizard}
                className="text-sm text-[#A8BFDB] underline-offset-2 hover:underline hover:text-white"
              >
                Skip to itinerary
              </button>
            )}
          </div>
        </div>
      </div>

      <div className="border-b border-slate-200 px-6 py-3">
        <div className="mb-1 flex items-center justify-between text-xs font-medium text-slate-500">
          <span>{completedCount} / {SUMMARY_KEYS.length} details captured</span>
          <span>{progressPercent}%</span>
        </div>
        <div className="h-2 overflow-hidden rounded-full bg-slate-100">
          <div className="h-full rounded-full bg-[#E88D3A] transition-all" style={{ width: `${progressPercent}%` }} />
        </div>
      </div>

      <div className="flex min-h-0 flex-1 flex-col">
        <div className="flex-1 space-y-4 overflow-y-auto px-6 py-5">
          {messages.map((message, index) => {
            const canUseChips = phase === 'chatting' && message.role === 'bot' && index === messages.length - 1
            return (
              <div key={message.id} className="space-y-2">
                <WizardMessageBubble message={message} />
                {message.role === 'bot' && message.chips && message.chips.length > 0 && (
                  <div className="space-y-2">
                    <QuickReplyChips
                      chips={message.chips}
                      disabled={!canUseChips || isProcessing}
                      onSelect={currentField === 'themes' && canUseChips
                        ? (chip) => {
                            if (chip === 'Skip →') {
                              setPendingThemeSelections([])
                              void handleAnswer(chip)
                              return
                            }

                            const theme = themeFromChip(chip)
                            setPendingThemeSelections((previous) => (
                              previous.includes(theme)
                                ? previous.filter((selectedTheme) => selectedTheme !== theme)
                                : [...previous, theme]
                            ))
                          }
                        : handleChipSelect}
                      selected={currentField === 'themes' ? pendingThemeSelections : []}
                    />
                    {currentField === 'themes' && canUseChips && pendingThemeSelections.length > 0 && (
                      <button
                        type="button"
                        onClick={() => {
                          void handleAnswer(pendingThemeSelections.join(', '))
                          setPendingThemeSelections([])
                        }}
                        className="rounded-full bg-[#1E40AF] px-4 py-1.5 text-xs font-semibold text-white hover:bg-blue-800"
                      >
                        Done ✓ ({pendingThemeSelections.length} selected)
                      </button>
                    )}
                  </div>
                )}
              </div>
            )
          })}

          {phase === 'summary' && (
            <TripSummaryCard
              labels={{
                purpose: collectedLabels.purpose ?? '—',
                origin: collectedLabels.origin ?? tripConfig.origin.city ?? '—',
                destination: collectedLabels.destination ?? formatDestinationLabel(tripConfig),
                dates: collectedLabels.dates ?? '—',
                group: collectedLabels.group ?? `${tripConfig.group.adults} adults`,
                budget: collectedLabels.budget ?? formatBudget(tripConfig.budget.amount),
                accommodation: collectedLabels.accommodation ?? (tripConfig.accommodation.style.length > 0 ? tripConfig.accommodation.style.join(', ') : 'No preference'),
                pace: collectedLabels.pace ?? (tripConfig.pace.charAt(0).toUpperCase() + tripConfig.pace.slice(1)),
                themes: collectedLabels.themes ?? formatThemeLabel(tripConfig.themes),
              }}
              isRetry={itineraryStatus === 'error' && !!itineraryError}
              hasExistingItinerary={hasExistingItinerary}
              errorMessage={itineraryStatus === 'error' ? itineraryError?.message ?? null : null}
              onEdit={handleEditLastStep}
              onGenerate={handleGenerate}
              onViewItinerary={closeWizard}
            />
          )}

          {phase === 'generating' && (
            <div className="flex min-h-[240px] flex-col items-center justify-center rounded-2xl border border-slate-200 bg-slate-50 px-6 text-center">
              <div className="h-12 w-12 animate-spin rounded-full border-4 border-[#E88D3A] border-t-transparent" />
              <p className="mt-4 text-base font-semibold text-slate-800">Generating your itinerary…</p>
              <p className="mt-2 text-sm text-slate-500">{itineraryProgress.message || 'Gathering the best route, budget and day plans.'}</p>
              <p className="mt-2 text-xs text-slate-400">Step {Math.max(itineraryProgress.step, 1)} of {itineraryProgress.total}</p>
            </div>
          )}

          {phase === 'done' && (
            <div className="rounded-2xl border border-green-200 bg-green-50 p-5 text-center">
              <p className="text-2xl">🗺️</p>
              <p className="mt-2 text-base font-semibold text-slate-800">Your itinerary is ready!</p>
              <button
                type="button"
                onClick={closeWizard}
                className="mt-4 h-12 w-full rounded-2xl bg-[#B85C3F] text-sm font-semibold text-white transition-colors hover:bg-[#9a4b34]"
              >
                View Itinerary →
              </button>
              <button
                type="button"
                onClick={handleEditLastStep}
                className="mt-2 block w-full text-sm font-medium text-slate-500 transition-colors hover:text-[#1A3A52]"
              >
                ← Edit Trip Details
              </button>
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>

        {(phase === 'chatting' || phase === 'summary') && (
          <form onSubmit={handleSubmit} className="border-t border-slate-200 bg-white px-6 py-4">
            <div className="flex items-end gap-3">
              <div className="relative flex-1">
                <input
                  value={input}
                  onChange={(event) => setInput(event.target.value)}
                  type={currentInputType}
                  placeholder={phase === 'summary'
                    ? 'Refine your trip details...'
                    : currentInputType === 'date'
                      ? 'YYYY-MM-DD'
                      : 'Type your reply...'}
                  disabled={isProcessing}
                  className="h-12 w-full rounded-2xl border border-slate-300 px-4 pr-12 text-sm text-slate-800 outline-none transition-colors focus:border-[#E88D3A] disabled:bg-slate-50"
                />
              </div>
              <button
                type="submit"
                disabled={!input.trim() || isProcessing}
                className="h-12 rounded-2xl bg-[#B85C3F] px-5 text-sm font-semibold text-white transition-colors hover:bg-[#9a4b34] disabled:cursor-not-allowed disabled:bg-slate-200"
              >
                Send
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  )
}

function WizardMessageBubble({ message }: { message: WizardMessage }) {
  const isBot = message.role === 'bot'

  return (
    <div className={`flex ${isBot ? 'justify-start' : 'justify-end'}`}>
      <div
        className={[
          'max-w-[85%] rounded-2xl px-4 py-3 text-sm leading-relaxed shadow-sm',
          isBot ? 'rounded-tl-md bg-slate-100 text-slate-800' : 'rounded-tr-md bg-[#1A3A52] text-white',
        ].join(' ')}
      >
        {message.content}
      </div>
    </div>
  )
}

function QuickReplyChips({
  chips,
  disabled,
  onSelect,
  selected,
}: {
  chips: string[]
  disabled: boolean
  onSelect: (chip: string) => void
  selected: string[]
}) {
  return (
    <div className="flex flex-wrap gap-3 pl-1">
      {chips.map((chip) => {
        const label = chip === 'Skip →' ? chip : stripEmoji(chip)
        const isSelected = chip !== 'Skip →' && selected.includes(label)

        return (
          <StampChip
            key={chip}
            label={chip}
            isSelected={isSelected}
            onClick={() => !disabled && onSelect(chip)}
          />
        )
      })}
    </div>
  )
}

function TripSummaryCard({
  labels,
  isRetry,
  hasExistingItinerary,
  errorMessage,
  onEdit,
  onGenerate,
  onViewItinerary,
}: {
  labels: Record<string, string>
  isRetry: boolean
  hasExistingItinerary: boolean
  errorMessage: string | null
  onEdit: () => void
  onGenerate: () => void
  onViewItinerary: () => void
}) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-slate-50 p-5 shadow-sm">
      <div className="space-y-2 text-sm text-slate-700">
        <SummaryRow icon="🎯" label="Purpose" value={labels.purpose} />
        <SummaryRow icon="📍" label="From" value={labels.origin} />
        <SummaryRow icon="🗺️" label="Destination" value={labels.destination} />
        <SummaryRow icon="📅" label="Dates" value={labels.dates} />
        <SummaryRow icon="👥" label="Group" value={labels.group} />
        <SummaryRow icon="💰" label="Budget" value={labels.budget} />
        <SummaryRow icon="🏨" label="Stay" value={labels.accommodation} />
        <SummaryRow icon="⚡" label="Pace" value={labels.pace} />
        <SummaryRow icon="🎨" label="Themes" value={labels.themes} />
      </div>

      {errorMessage && (
        <div className="mt-4 rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-600">
          ⚠️ {errorMessage}
        </div>
      )}

      <button
        type="button"
        onClick={onGenerate}
        className="mt-5 h-12 w-full rounded-2xl bg-[#1E40AF] text-sm font-semibold text-white transition-colors hover:bg-blue-800"
      >
        {isRetry ? 'Retry Itinerary Generation ✈️' : hasExistingItinerary ? 'Regenerate Itinerary ✈️' : 'Generate Itinerary ✈️'}
      </button>

      {hasExistingItinerary && (
        <button
          type="button"
          onClick={onViewItinerary}
          className="mt-2 h-10 w-full rounded-2xl border border-[#1E40AF] text-sm font-semibold text-[#1E40AF] transition-colors hover:bg-blue-50"
        >
          View Current Itinerary 🗺️
        </button>
      )}

      <button
        type="button"
        onClick={onEdit}
        className="mt-3 text-sm font-medium text-slate-500 transition-colors hover:text-[#1E40AF]"
      >
        ← Edit
      </button>
    </div>
  )
}

function SummaryRow({ icon, label, value }: { icon: string; label: string; value: string }) {
  return (
    <div className="flex items-start gap-2">
      <span className="shrink-0">{icon}</span>
      <p>
        <span className="font-semibold text-slate-800">{label}:</span> {value}
      </p>
    </div>
  )
}
