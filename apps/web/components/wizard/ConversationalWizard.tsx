'use client'

import { useEffect, useMemo, useRef, useState } from 'react'
import { chatRefine, geocode, recommendCities, streamItinerary } from '@/lib/api'
import { formatCurrency } from '@/lib/format'
import { useAppStore } from '@/store/appStore'
import { useItineraryStore } from '@/store/itineraryStore'
import { useTripConfigStore } from '@/store/tripConfigStore'
import { useWizardChatStore, type WizardField, type WizardMessage } from '@/store/wizardChatStore'
import type { Pace, RecommendedCity, TripConfig } from '@/types'
import { ListeningOrb } from '@/components/voice/ListeningOrb'
import {
  AlertCircle,
  Bed,
  Calendar,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Globe,
  Heart,
  Loader2,
  MapPin,
  Mic,
  MicOff,
  Plane,
  Target,
  type LucideIcon,
  Users,
  Wallet,
  X,
  Zap,
} from 'lucide-react'

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
  'Leisure',
  'Adventure',
  'Honeymoon',
  'Family Vacation',
  'Business + Leisure',
  'Solo Backpacking',
  'Group Holiday',
]

const DESTINATION_MODE_CHIPS = ['Yes, I have one', 'Suggest me!', 'Exploring a country']
const DURATION_CHIPS = ['3 days', '5 days', '7 days', '10 days', '14 days', 'Flexible']
const DATE_CHIPS = ['This month', 'Next month', 'In 3 months', 'Custom dates', 'Flexible']
const BUDGET_CHIPS = ['50,000', '1,00,000', '2,50,000', '5,00,000', '10,00,000+']
const PACE_CHIPS = [
  'Relaxed (fewer activities, more leisure)',
  'Moderate (balanced mix)',
  'Packed (maximum experiences)',
]
const THEME_CHIPS = [
  'Culture',
  'Food',
  'Adventure',
  'Nature',
  'Shopping',
  'Photography',
  'Nightlife',
  'Sports',
  'Skip →',
]
const ACCOMMODATION_CHIPS = [
  'Hotel',
  'Airbnb / Villa',
  'Hostel',
  'Resort',
  'Service Apartment',
  'No preference',
]
const SUMMARY_KEYS = ['purpose', 'origin', 'destination', 'duration', 'dates', 'group', 'budget', 'accommodation', 'pace', 'themes'] as const

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
  return formatCurrency(amount, 'INR')
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

// Deterministic gradient per city name (fallback while image loads)
const DEST_GRADIENTS = [
  'linear-gradient(135deg,#0EA5E9 0%,#0C4A6E 100%)',
  'linear-gradient(135deg,#EA580C 0%,#9A3412 100%)',
  'linear-gradient(135deg,#059669 0%,#065F46 100%)',
  'linear-gradient(135deg,#7C3AED 0%,#4C1D95 100%)',
  'linear-gradient(135deg,#D4AF37 0%,#A8820A 100%)',
  'linear-gradient(135deg,#DB2777 0%,#831843 100%)',
]
function destGradient(name: string) {
  let h = 0; for (let i = 0; i < name.length; i++) h = (h * 31 + name.charCodeAt(i)) >>> 0
  return DEST_GRADIENTS[h % DEST_GRADIENTS.length]
}

import { useWikiImage } from '@/hooks/useWikiImage'

function DestinationCard({ city, disabled, onSelect }: {
  city: RecommendedCity
  disabled: boolean
  onSelect: (chip: string) => void
}) {
  const label   = recommendedCityChip(city)
  const imgUrl  = useWikiImage(city.name, city.country)
  const gradient = destGradient(city.name)

  return (
    <button
      disabled={disabled}
      onClick={() => onSelect(label)}
      className="group relative overflow-hidden rounded-2xl border border-[var(--color-border)] bg-[var(--color-card)] text-left shadow-sm transition-all duration-200 hover:-translate-y-0.5 hover:border-[var(--color-primary)] hover:shadow-md disabled:opacity-50"
    >
      {/* Hero image / gradient */}
      <div className="relative h-28 w-full overflow-hidden" style={{ background: gradient }}>
        {imgUrl && (
          <img
            src={imgUrl}
            alt={city.name}
            className="absolute inset-0 h-full w-full object-cover transition-transform duration-500 group-hover:scale-105"
            loading="lazy"
          />
        )}
        {/* scrim for text readability */}
        <div className="absolute inset-0 bg-gradient-to-t from-black/50 via-transparent to-transparent" />
        {/* City initial — shown only while image is loading */}
        {!imgUrl && (
          <div className="flex h-full items-center justify-center">
            <span className="select-none text-4xl font-black text-white/30">{city.name.charAt(0)}</span>
          </div>
        )}
      </div>

      {/* Card body */}
      <div className="p-3">
        <p className="text-sm font-semibold leading-tight text-[var(--color-foreground)]">{city.name}</p>
        <p className="mt-0.5 text-xs text-[var(--color-foreground-muted)]">{city.country}</p>
        {city.reason && (
          <p className="mt-1.5 line-clamp-2 text-xs leading-relaxed text-[var(--color-foreground-muted)]">
            {city.reason}
          </p>
        )}
        <span className="mt-2 inline-flex items-center gap-1 text-xs font-medium text-[var(--color-primary)] opacity-0 transition-opacity group-hover:opacity-100">
          Plan this trip →
        </span>
      </div>
    </button>
  )
}

function DestinationCardGrid({ cities, disabled, onSelect }: {
  cities: RecommendedCity[]
  disabled: boolean
  onSelect: (chip: string) => void
}) {
  if (!cities.length) return null
  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
      {cities.map((city) => (
        <DestinationCard
          key={recommendedCityChip(city)}
          city={city}
          disabled={disabled}
          onSelect={onSelect}
        />
      ))}
    </div>
  )
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

async function resolvePlace(query: string): Promise<{ city: string; country: string; lat: number; lon: number; isCountry: boolean } | null> {
  try {
    const result = await geocode(query)
    const parts = result.display_name.split(',').map((part) => part.trim()).filter(Boolean)

    return {
      city: parts[0] ?? query.trim(),
      country: parts[parts.length - 1] ?? result.country_code.toUpperCase(),
      lat: result.lat,
      lon: result.lon,
      isCountry: result.is_country,
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
  const wizardPreload = useAppStore((state) => state.wizardPreload)
  const clearWizardPreload = useAppStore((state) => state.clearWizardPreload)

  const tripConfig = useTripConfigStore((state) => state.config)
  const updateConfig = useTripConfigStore((state) => state.updateConfig)
  const updateDates = useTripConfigStore((state) => state.updateDates)
  const updateBudget = useTripConfigStore((state) => state.updateBudget)
  const updateGroup = useTripConfigStore((state) => state.updateGroup)
  const resetConfig = useTripConfigStore((state) => state.resetConfig)
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
  const resetWizardChat = useWizardChatStore((state) => state.reset)

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
  const [stepDirection, setStepDirection] = useState<'forward' | 'back'>('forward')
  const [showEditEntry, setShowEditEntry] = useState(false)
  const [adultCountDraft, setAdultCountDraft] = useState(tripConfig.group.adults || 1)
  const [kidsCountDraft, setKidsCountDraft] = useState(tripConfig.group.kids.length)
  const [kidsAgesDraft, setKidsAgesDraft] = useState(
    tripConfig.group.kids.map(({ age }) => String(age)).join(', '),
  )

  const dialogRef = useRef<HTMLDivElement>(null)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const recognitionRef = useRef<RecognitionInstance | null>(null)
  const streamCleanupRef = useRef<(() => void) | null>(null)
  const speechSynthesisRef = useRef<SpeechSynthesisUtterance | null>(null)
  const [isSpeaking, setIsSpeaking] = useState(false)

  const hasExistingItinerary = days.length > 0

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
      if (wizardPreload) {
        // Pre-fill destination + days from inspiration card
        setDestination({ city: wizardPreload.city, country: wizardPreload.country, lat: 0, lon: 0 })
        updateConfig({ destination_mode: 'fixed', destination_country: null })
        updateDates({ duration_days: wizardPreload.days })
        addLabel('destination', wizardPreload.label)
        addLabel('duration', `${wizardPreload.days} days`)
        clearWizardPreload()
        addMessage(botMessage(
          `Hi! I'm Anya 👋 I see you're interested in **${wizardPreload.label}** for **${wizardPreload.days} days** — great choice!\n\nYou can adjust these details anytime. Let's start with the trip purpose:`,
          { chips: PURPOSE_CHIPS }
        ))
      } else {
        addMessage(botMessage("Hi! I'm Anya, your Wanderplanner travel concierge 👋\n\nI'll help you build a personalised trip plan in just a few steps. Let's start!\n\nWhat's the main purpose of your trip?", { chips: PURPOSE_CHIPS }))
      }
    }
  }, [addMessage, messages.length, phase, setPhase, tripConfig, wizardOpen])

  useEffect(() => {
    if (!wizardOpen) {
      setShowEditEntry(false)
      return
    }

    if (hasExistingItinerary && phase !== 'generating') {
      setShowEditEntry(true)
    }
  }, [wizardOpen])

  useEffect(() => {
    if (currentField !== 'group') return

    const config = useTripConfigStore.getState().config
    setAdultCountDraft(config.group.adults || 1)
    setKidsCountDraft(config.group.kids.length)
    setKidsAgesDraft(config.group.kids.map(({ age }) => String(age)).join(', '))
  }, [currentField])

  useEffect(() => {
    if (phase !== 'chatting') {
      setInput('')
      return
    }

    const config = useTripConfigStore.getState().config

    if (currentField === 'origin') {
      setInput(config.origin.city ?? '')
      return
    }

    if (currentField === 'destination') {
      if (config.destination_mode === 'country') {
        if (destinationSubStage === 'input') {
          setInput(config.destination_country ?? '')
          return
        }

        if (destinationSubStage === 'city-select') {
          setInput(config.destination?.city ?? '')
          return
        }
      }

      setInput(config.destination?.city ?? '')
      return
    }

    if (currentField === 'budget') {
      setInput(config.budget.amount > 0 ? String(config.budget.amount) : '')
      return
    }

    if (currentField === 'dates') {
      if (dateStage === 'custom-start') {
        setInput(config.dates.start ?? '')
        return
      }

      if (dateStage === 'custom-end') {
        setInput(config.dates.end ?? '')
        return
      }
    }

    if (currentField === 'group' && groupStage === 'kids-ages') {
      setInput(config.group.kids.map(({ age }) => String(age)).join(', '))
      return
    }

    setInput('')
  }, [currentField, dateStage, destinationSubStage, groupStage, phase])

  useEffect(() => {
    if (!wizardOpen) return

    const dialog = dialogRef.current
    if (!dialog || typeof window === 'undefined') return

    const previousActiveElement = document.activeElement instanceof HTMLElement ? document.activeElement : null
    const focusableSelector = [
      'button:not([disabled])',
      '[href]',
      'input:not([disabled])',
      'select:not([disabled])',
      'textarea:not([disabled])',
      '[tabindex]:not([tabindex="-1"])',
    ].join(', ')

    const getFocusableElements = () => (
      Array.from(dialog.querySelectorAll<HTMLElement>(focusableSelector))
        .filter((element) => !element.hasAttribute('aria-hidden'))
    )

    const focusFirstElement = () => {
      const [firstElement] = getFocusableElements()
      firstElement?.focus()
    }

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && hasExistingItinerary) {
        event.preventDefault()
        closeWizard()
        return
      }

      if (event.key !== 'Tab') return

      const focusableElements = getFocusableElements()
      if (focusableElements.length === 0) {
        event.preventDefault()
        return
      }

      const firstElement = focusableElements[0]
      const lastElement = focusableElements[focusableElements.length - 1]
      const activeElement = document.activeElement instanceof HTMLElement ? document.activeElement : null

      if (event.shiftKey) {
        if (!activeElement || activeElement === firstElement || !dialog.contains(activeElement)) {
          event.preventDefault()
          lastElement.focus()
        }
        return
      }

      if (!activeElement || activeElement === lastElement || !dialog.contains(activeElement)) {
        event.preventDefault()
        firstElement.focus()
      }
    }

    const focusTimer = window.setTimeout(focusFirstElement, 0)
    document.addEventListener('keydown', handleKeyDown)

    return () => {
      window.clearTimeout(focusTimer)
      document.removeEventListener('keydown', handleKeyDown)
      previousActiveElement?.focus()
    }
  }, [closeWizard, hasExistingItinerary, wizardOpen])

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
        
        pushNextField('dates')
        return
      }

      if (currentField === 'destination') {
        const config = useTripConfigStore.getState().config
        const mode = config.destination_mode

        if (mode === 'fixed') {
          const place = await resolvePlace(value)
          
          if (!place) {
            addMessage(botMessage(
              `I couldn't find "${value}". Please enter a valid city or destination (e.g., "Paris, France", "Tokyo, Japan")`,
              { inputType: 'text' }
            ))
            return
          }

          // If the input resolved to a whole country, switch to multi-city mode
          if (place.isCountry) {
            updateConfig({ destination_mode: 'country', destination_country: place.country })
            setDestination(null)
            setDestinationSubStage('city-select')
            try {
              const { cities } = await recommendCities(place.country, useTripConfigStore.getState().config)
              const nextCities = cities.slice(0, 5)
              setSuggestedCities(nextCities)
              if (nextCities.length > 0) {
                addMessage(botMessage(
                  `${place.country} is a country — I can help you plan a multi-city trip! Here are popular destinations:`,
                  { chips: nextCities.map(recommendedCityChip) }
                ))
              } else {
                addMessage(botMessage(
                  `${place.country} is a country — which city would you like to visit first?`,
                  { inputType: 'text' }
                ))
              }
            } catch {
              addMessage(botMessage(
                `${place.country} is a country — which city would you like to visit first?`,
                { inputType: 'text' }
              ))
            }
            return
          }
          
          setDestination({ city: place.city, country: place.country, lat: place.lat, lon: place.lon })
          updateConfig({ destination_country: null })
          addLabel('destination', value || `${place.city}, ${place.country}`)
          pushNextField('duration')
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
            pushNextField('duration')
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

          pushNextField('duration')
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
        addMessage(botMessage('⚠️ Could not reach WanderPlanner. Please check your internet connection and try again.', { inputType: currentInputType }))
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
    setStepDirection('forward')
    void handleAnswer(chip)
  }

  function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setStepDirection('forward')
    void handleAnswer(input)
  }

  function handleEditLastStep() {
    setStepDirection('back')
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

  function handleGroupContinue() {
    setStepDirection('forward')

    if (groupStage === 'adults') {
      void handleAnswer(String(Math.max(1, adultCountDraft)))
      return
    }

    if (groupStage === 'kids-count') {
      void handleAnswer(String(Math.max(0, kidsCountDraft)))
      return
    }

    void handleAnswer(kidsAgesDraft)
  }

  function handleThemeToggle(chip: string) {
    if (chip === 'Skip →') return

    const theme = themeFromChip(chip)
    setPendingThemeSelections((previous) => (
      previous.includes(theme)
        ? previous.filter((selectedTheme) => selectedTheme !== theme)
        : [...previous, theme]
    ))
  }

  function handleThemesContinue() {
    if (pendingThemeSelections.length === 0) return

    setStepDirection('forward')
    void handleAnswer(pendingThemeSelections.join(', '))
    setPendingThemeSelections([])
  }

  function revisitField(field: WizardField) {
    const config = useTripConfigStore.getState().config

    if (field === 'destination') {
      if (config.destination_mode === 'country') {
        setDestinationSubStage(config.destination_country ? 'city-select' : 'input')
      } else if (config.destination_mode === 'exploring') {
        setDestinationSubStage(suggestedCities.length > 0 ? 'suggest-select' : 'input')
      } else {
        setDestinationSubStage('input')
      }
    }

    if (field === 'dates') {
      setDateStage('preset')
      setPendingStartDate(null)
    }

    if (field === 'group') {
      setGroupStage('adults')
      setPendingKidsCount(0)
    }

    if (field === 'themes') {
      setPendingThemeSelections([...useTripConfigStore.getState().config.themes])
    }

    setCurrentField(field)
    setPhase('chatting')
    addMessage(promptForField(field, config))
  }

  function handleStartNewTrip() {
    setShowEditEntry(false)
    resetConfig()
    resetWizardChat()
    setStepDirection('forward')
    setInput('')
    setPendingThemeSelections([])
    setDateStage('preset')
    setGroupStage('adults')
    setDestinationSubStage('input')
    setSuggestedCities([])
    setPendingStartDate(null)
    setPendingKidsCount(0)
    setAdultCountDraft(1)
    setKidsCountDraft(0)
    setKidsAgesDraft('')
  }

  function handleBack() {
    setStepDirection('back')
    setInput('')

    if (phase === 'summary' || currentField === 'refinement' || currentField === 'done') {
      revisitField('themes')
      return
    }

    if (currentField === 'group') {
      if (groupStage === 'kids-ages') {
        setGroupStage('kids-count')
        return
      }

      if (groupStage === 'kids-count') {
        setGroupStage('adults')
        return
      }
    }

    if (currentField === 'dates') {
      if (dateStage === 'custom-end') {
        setDateStage('custom-start')
        return
      }

      if (dateStage === 'custom-start') {
        setDateStage('preset')
        setPendingStartDate(null)
        return
      }
    }

    if (currentField === 'destination') {
      if (tripConfig.destination_mode === 'country' && destinationSubStage === 'multi-city-confirm') {
        setDestinationSubStage('city-select')
        return
      }

      if (tripConfig.destination_mode === 'country' && destinationSubStage === 'city-select') {
        setDestinationSubStage('input')
        return
      }

      if (tripConfig.destination_mode === 'exploring' && destinationSubStage === 'suggest-select') {
        setDestinationSubStage('input')
        return
      }

      revisitField('destination_mode')
      return
    }

    const previousFieldMap: Partial<Record<WizardField, WizardField>> = {
      origin: 'purpose',
      destination_mode: 'origin',
      duration: 'destination',
      dates: 'duration',
      group: 'dates',
      budget: 'group',
      accommodation: 'budget',
      pace: 'accommodation',
      themes: 'pace',
    }

    const previousField = previousFieldMap[currentField]
    if (previousField) revisitField(previousField)
  }

  const currentStep = useMemo(() => {
    if (phase === 'summary' || phase === 'generating' || phase === 'done' || currentField === 'refinement' || currentField === 'done') {
      return 11
    }

    switch (currentField) {
      case 'purpose':
        return 1
      case 'origin':
        return 2
      case 'destination_mode':
      case 'destination':
        return 3
      case 'duration':
        return 4
      case 'dates':
        return 5
      case 'group':
        return 6
      case 'budget':
        return 7
      case 'accommodation':
        return 8
      case 'pace':
        return 9
      case 'themes':
        return 10
      default:
        return 11
    }
  }, [currentField, phase])

  const stepHeading = getStepHeading(currentField, phase, groupStage, dateStage, destinationSubStage)
  const stepHint = getStepHint(currentField, phase, groupStage, dateStage, destinationSubStage, tripConfig)
  const stepPrompt = phase === 'chatting' ? promptForField(currentField, tripConfig).content.trim() : null
  const contextualMessage = currentPrompt?.content?.trim() && currentPrompt.content.trim() !== stepPrompt
    ? currentPrompt.content.trim()
    : null
  const errorMessage = contextualMessage && isWizardErrorMessage(contextualMessage) ? stripEmoji(contextualMessage) : null
  const helperMessage = errorMessage ? stepHint : (contextualMessage ?? stepHint)

  const summaryLabels = {
    purpose: collectedLabels.purpose ?? tripConfig.purpose ?? '—',
    origin: collectedLabels.origin ?? tripConfig.origin.city ?? '—',
    destination: collectedLabels.destination ?? formatDestinationLabel(tripConfig),
    duration: collectedLabels.duration ?? (tripConfig.dates.duration_days ? `${tripConfig.dates.duration_days} days` : 'Flexible'),
    dates: collectedLabels.dates ?? formatDateLabel(tripConfig.dates),
    group: collectedLabels.group ?? formatGroupLabel(tripConfig.group),
    budget: collectedLabels.budget ?? formatBudget(tripConfig.budget.amount),
    accommodation: collectedLabels.accommodation ?? (tripConfig.accommodation.style.length > 0 ? tripConfig.accommodation.style.join(', ') : 'No preference'),
    pace: collectedLabels.pace ?? (tripConfig.pace.charAt(0).toUpperCase() + tripConfig.pace.slice(1)),
    themes: collectedLabels.themes ?? formatThemeLabel(tripConfig.themes),
  }

  const showNavigation = !showEditEntry
    && phase === 'chatting'
    && currentField !== 'purpose'
    && currentField !== 'destination_mode'
    && currentField !== 'duration'
    && currentField !== 'accommodation'
    && currentField !== 'pace'
    && !(currentField === 'dates' && dateStage === 'preset')
    && !(currentField === 'destination' && (
      destinationSubStage === 'city-select'
      || destinationSubStage === 'suggest-select'
      || destinationSubStage === 'multi-city-confirm'
    ))

  const continueDisabled = (() => {
    if (isProcessing) return true

    if (currentField === 'purpose') return true
    if (currentField === 'origin') return input.trim().length < 3
    if (currentField === 'destination') {
      if (destinationSubStage === 'city-select' || destinationSubStage === 'suggest-select' || destinationSubStage === 'multi-city-confirm') {
        return true
      }

      return input.trim().length < 2
    }

    if (currentField === 'dates') {
      return dateStage === 'preset' ? true : !input.trim()
    }

    if (currentField === 'group') {
      if (groupStage === 'adults') return adultCountDraft < 1
      if (groupStage === 'kids-count') return kidsCountDraft < 0
      return !kidsAgesDraft.trim()
    }

    if (currentField === 'budget') {
      return !input.trim()
    }

    if (currentField === 'themes') {
      return pendingThemeSelections.length === 0
    }

    return !input.trim()
  })()

  const continueLabel = (() => {
    if (currentField === 'group') return groupStage === 'kids-ages' ? 'Continue' : 'Continue'
    if (currentField === 'themes') return `Continue (${pendingThemeSelections.length} selected)`
    return 'Continue'
  })()

  const stepKey = `${phase}-${currentField}-${dateStage}-${groupStage}-${destinationSubStage}`

  return (
    <div
      ref={dialogRef}
      role="dialog"
      aria-modal="true"
      aria-label="Trip Planning Wizard"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm [--color-primary:#0EA5E9] [--color-accent:#EA580C] [--color-background:#F0F9FF] [--color-card:#FFFFFF] [--color-foreground:#0C4A6E] [--color-foreground-muted:#64748B] [--color-border:#BAE6FD] [--color-ring:#0EA5E9] dark:[--color-background:#040D14] dark:[--color-card:#071522] dark:[--color-foreground:#E0F2FE] dark:[--color-primary:#38BDF8] dark:[--color-accent:#FB923C] dark:[--color-border:#0E3A57]"
    >
      <div className="card relative flex max-h-screen w-full flex-col overflow-hidden rounded-none bg-[var(--color-card)] shadow-2xl sm:mx-4 sm:max-h-[90vh] sm:max-w-lg sm:rounded-2xl border-[var(--color-border)]">
        <div className="flex items-start justify-between gap-4 bg-[var(--color-primary)] px-4 py-4 text-white sm:px-8">
          <div className="min-w-0">
            <p className="text-xl font-bold leading-tight [font-family:var(--font-space-grotesk)]">Wanderplanner</p>
            <p className="mt-1 text-sm text-white/80 [font-family:var(--font-dm-sans)]">Anya · Your travel concierge</p>
          </div>

          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={toggleVoiceMode}
              aria-label={voiceModeActive ? 'Deactivate voice mode' : 'Activate voice mode'}
              className="focus-ring rounded-full"
            >
              <ListeningOrb isActive={voiceModeActive} isRecording={isRecording} />
            </button>

            {hasExistingItinerary && (
              <>
                <button
                  type="button"
                  onClick={closeWizard}
                  className="btn btn-ghost min-h-[44px] border-white/20 bg-white/10 px-3 text-white hover:bg-white/20 hover:text-white"
                >
                  Skip to itinerary
                </button>
                <button
                  type="button"
                  onClick={closeWizard}
                  aria-label="Close wizard"
                  className="focus-ring inline-flex min-h-[44px] min-w-[44px] items-center justify-center rounded-xl border border-white/20 bg-white/10 text-white transition-colors hover:bg-white/20"
                >
                  <X className="h-5 w-5" />
                </button>
              </>
            )}
          </div>
        </div>

        {/* Progress bar — sky-blue track fills white as steps complete */}
        <div
          className="relative h-1.5 w-full overflow-hidden bg-[var(--color-primary)]/20"
          role="progressbar"
          aria-valuenow={currentStep}
          aria-valuemin={1}
          aria-valuemax={11}
        >
          <div
            className="h-full rounded-r-full bg-gradient-to-r from-[var(--color-primary)] to-[#38bdf8] shadow-[0_0_8px_var(--color-primary)] transition-all duration-500 ease-out"
            style={{ width: `${(currentStep / 11) * 100}%` }}
          />
        </div>

        <div className="border-b border-[var(--color-border)] px-8 py-3">
          <p className="text-sm text-[var(--color-foreground-muted)] [font-family:var(--font-dm-sans)]">
            Step {currentStep} of 11
          </p>
        </div>

        <div className="relative flex-1 overflow-y-auto bg-[var(--color-background)]">
          <div className="p-8">
            {voiceModeActive && (
              <div className="mb-6 flex items-center gap-3 rounded-xl border border-[var(--color-border)] bg-[var(--color-card)] px-4 py-3 text-sm text-[var(--color-foreground)]">
                <span className="inline-flex h-10 w-10 items-center justify-center rounded-full bg-[var(--color-primary)]/10 text-[var(--color-primary)]">
                  {isRecording ? <Mic className="h-5 w-5" /> : <MicOff className="h-5 w-5" />}
                </span>
                <div>
                  <p className="font-semibold">Listening...</p>
                  <p className="text-[var(--color-foreground-muted)]">Your voice reply will fill the current step.</p>
                </div>
              </div>
            )}

            {phase === 'generating' && (
              <GeneratingView
                message={itineraryProgress.message || 'Gathering the best route, budget and day plans.'}
                step={Math.max(itineraryProgress.step, 0)}
                total={Math.max(itineraryProgress.total, 4)}
              />
            )}

            {phase === 'done' && <DoneView onViewItinerary={closeWizard} />}

            {showEditEntry && (
              <div className="space-y-4 fade-up">
                <h2 className="text-2xl font-bold leading-tight text-[var(--color-foreground)] [font-family:var(--font-space-grotesk)]">
                  What would you like to do?
                </h2>
                <p className="text-sm text-[var(--color-foreground-muted)]">Your itinerary is saved. You can add instructions or start fresh.</p>

                <button
                  type="button"
                  onClick={() => {
                    setShowEditEntry(false)
                    revisitField('refinement')
                  }}
                  className="chip w-full rounded-xl p-4 text-left"
                  style={{ minHeight: '64px', display: 'flex', flexDirection: 'column', alignItems: 'flex-start' }}
                >
                  <span className="font-semibold text-[var(--color-foreground)]">Add custom instructions</span>
                  <span className="mt-0.5 text-xs text-[var(--color-foreground-muted)]">Add requests to the current trip configuration</span>
                </button>

                <button
                  type="button"
                  onClick={handleStartNewTrip}
                  className="chip w-full rounded-xl p-4 text-left"
                  style={{ minHeight: '64px', display: 'flex', flexDirection: 'column', alignItems: 'flex-start' }}
                >
                  <span className="font-semibold text-[var(--color-foreground)]">Plan a new trip</span>
                  <span className="mt-0.5 text-xs text-[var(--color-foreground-muted)]">Start fresh with a new destination and preferences</span>
                </button>

                <button
                  type="button"
                  onClick={closeWizard}
                  className="btn btn-ghost w-full rounded-xl border-[var(--color-border)] text-[var(--color-foreground-muted)]"
                >
                  Cancel — keep viewing itinerary
                </button>
              </div>
            )}

            {!showEditEntry && phase !== 'generating' && phase !== 'done' && (
              <div key={stepKey} className={stepDirection === 'back' ? 'step-enter-back' : 'step-enter'}>
                <h2 className="text-2xl font-bold leading-tight text-[var(--color-foreground)] [font-family:var(--font-space-grotesk)]">
                  {stepHeading}
                </h2>

                {helperMessage && (
                  <p className="mt-1 mb-6 text-sm text-[var(--color-foreground-muted)] [font-family:var(--font-dm-sans)]">
                    {helperMessage}
                  </p>
                )}

                {errorMessage && <ErrorBanner message={errorMessage} />}

                <div className="mt-6 space-y-6">
                  {phase === 'summary' && (
                    <SummaryStepCard
                      labels={summaryLabels}
                      errorMessage={itineraryStatus === 'error' ? itineraryError?.message ?? null : null}
                      hasExistingItinerary={hasExistingItinerary}
                      generateLabel={itineraryStatus === 'error'
                        ? 'Retry Itinerary'
                        : hasExistingItinerary
                          ? 'Regenerate Itinerary'
                          : 'Generate Itinerary'}
                      onEdit={handleEditLastStep}
                      onGenerate={handleGenerate}
                      onViewItinerary={closeWizard}
                    />
                  )}

                  {phase === 'chatting' && currentField === 'purpose' && (
                    <ChipGrid
                      chips={PURPOSE_CHIPS}
                      columns={2}
                      disabled={isProcessing}
                      onSelect={handleChipSelect}
                    />
                  )}

                  {phase === 'chatting' && currentField === 'origin' && (
                    <form onSubmit={handleSubmit} className="space-y-3">
                      <input
                        autoFocus
                        value={input}
                        onChange={(event) => setInput(event.target.value)}
                        type="text"
                        placeholder="Enter your departure city"
                        disabled={isProcessing}
                        className="input min-h-[52px] rounded-xl border-[var(--color-border)] bg-[var(--color-card)] px-4 text-[var(--color-foreground)]"
                      />
                    </form>
                  )}

                  {phase === 'chatting' && currentField === 'destination_mode' && (
                    <ChipGrid
                      chips={DESTINATION_MODE_CHIPS}
                      columns={1}
                      disabled={isProcessing}
                      onSelect={handleChipSelect}
                      icons={{
                        'Yes, I have one': MapPin,
                        'Suggest me!': Plane,
                        'Exploring a country': Globe,
                      }}
                      descriptions={{
                        'Yes, I have one': 'I already know the city or destination.',
                        'Suggest me!': 'Show me places based on my vibe.',
                        'Exploring a country': 'Help me pick cities within a country.',
                      }}
                    />
                  )}

                  {phase === 'chatting' && currentField === 'destination' && (
                    <>
                      {tripConfig.destination_mode === 'fixed' && (
                        <form onSubmit={handleSubmit} className="space-y-3">
                          <input
                            autoFocus
                            value={input}
                            onChange={(event) => setInput(event.target.value)}
                            type="text"
                            placeholder="Search city or destination"
                            disabled={isProcessing}
                            className="input min-h-[52px] rounded-xl border-[var(--color-border)] bg-[var(--color-card)] px-4 text-[var(--color-foreground)]"
                          />
                        </form>
                      )}

                      {tripConfig.destination_mode === 'country' && destinationSubStage === 'input' && (
                        <form onSubmit={handleSubmit} className="space-y-3">
                          <input
                            autoFocus
                            value={input}
                            onChange={(event) => setInput(event.target.value)}
                            type="text"
                            placeholder="Enter a country"
                            disabled={isProcessing}
                            className="input min-h-[52px] rounded-xl border-[var(--color-border)] bg-[var(--color-card)] px-4 text-[var(--color-foreground)]"
                          />
                        </form>
                      )}

                      {tripConfig.destination_mode === 'country' && destinationSubStage === 'city-select' && suggestedCities.length > 0 && (
                        <ChipGrid
                          chips={suggestedCities.map(recommendedCityChip)}
                          columns={1}
                          disabled={isProcessing}
                          onSelect={handleChipSelect}
                        />
                      )}

                      {tripConfig.destination_mode === 'country' && destinationSubStage === 'city-select' && suggestedCities.length === 0 && (
                        <form onSubmit={handleSubmit} className="space-y-3">
                          <input
                            autoFocus
                            value={input}
                            onChange={(event) => setInput(event.target.value)}
                            type="text"
                            placeholder={`Enter a city in ${tripConfig.destination_country ?? 'your chosen country'}`}
                            disabled={isProcessing}
                            className="input min-h-[52px] rounded-xl border-[var(--color-border)] bg-[var(--color-card)] px-4 text-[var(--color-foreground)]"
                          />
                        </form>
                      )}

                      {tripConfig.destination_mode === 'country' && destinationSubStage === 'multi-city-confirm' && (
                        <ChipGrid
                          chips={['Yes, add another city', 'No, continue']}
                          columns={1}
                          disabled={isProcessing}
                          onSelect={handleChipSelect}
                          icons={{
                            'Yes, add another city': Globe,
                            'No, continue': ChevronRight,
                          }}
                        />
                      )}

                      {tripConfig.destination_mode === 'exploring' && destinationSubStage === 'input' && (
                        <form onSubmit={handleSubmit} className="space-y-3">
                          <input
                            autoFocus
                            value={input}
                            onChange={(event) => setInput(event.target.value)}
                            type="text"
                            placeholder="Describe the kind of trip you want"
                            disabled={isProcessing}
                            className="input min-h-[52px] rounded-xl border-[var(--color-border)] bg-[var(--color-card)] px-4 text-[var(--color-foreground)]"
                          />
                        </form>
                      )}

                      {tripConfig.destination_mode === 'exploring' && destinationSubStage === 'suggest-select' && (
                        <DestinationCardGrid
                          cities={suggestedCities}
                          disabled={isProcessing}
                          onSelect={handleChipSelect}
                        />
                      )}
                    </>
                  )}

                  {phase === 'chatting' && currentField === 'duration' && (
                    <ChipGrid
                      chips={DURATION_CHIPS}
                      columns={2}
                      disabled={isProcessing}
                      onSelect={handleChipSelect}
                    />
                  )}

                  {phase === 'chatting' && currentField === 'dates' && dateStage === 'preset' && (
                    <ChipGrid
                      chips={DATE_CHIPS}
                      columns={2}
                      disabled={isProcessing}
                      onSelect={handleChipSelect}
                      icons={{ 'Custom dates': Calendar }}
                    />
                  )}

                  {phase === 'chatting' && currentField === 'dates' && dateStage !== 'preset' && (
                    <form onSubmit={handleSubmit} className="space-y-3">
                      <input
                        autoFocus
                        value={input}
                        onChange={(event) => setInput(event.target.value)}
                        type="date"
                        disabled={isProcessing}
                        className="input min-h-[52px] rounded-xl border-[var(--color-border)] bg-[var(--color-card)] px-4 text-[var(--color-foreground)]"
                      />
                    </form>
                  )}

                  {phase === 'chatting' && currentField === 'group' && (
                    <div className="space-y-4">
                      {groupStage === 'adults' && (
                        <CounterCard
                          label="Adults"
                          hint="Minimum 1 adult"
                          value={adultCountDraft}
                          onDecrease={() => setAdultCountDraft((value) => Math.max(1, value - 1))}
                          onIncrease={() => setAdultCountDraft((value) => value + 1)}
                        />
                      )}

                      {groupStage === 'kids-count' && (
                        <CounterCard
                          label="Kids"
                          hint="Add children travelling with you"
                          value={kidsCountDraft}
                          onDecrease={() => setKidsCountDraft((value) => Math.max(0, value - 1))}
                          onIncrease={() => setKidsCountDraft((value) => value + 1)}
                        />
                      )}

                      {groupStage === 'kids-ages' && (
                        <div className="space-y-3">
                          <label className="block text-sm font-bold text-[var(--color-primary)] [font-family:var(--font-dm-sans)]">
                            Kids ages
                          </label>
                          <input
                            autoFocus
                            value={kidsAgesDraft}
                            onChange={(event) => setKidsAgesDraft(event.target.value)}
                            type="text"
                            placeholder="e.g. 4, 8"
                            disabled={isProcessing}
                            className="min-h-[52px] w-full rounded-xl border border-slate-200 bg-white px-4 text-base font-medium text-slate-900 placeholder-slate-400 outline-none transition-colors focus:border-[var(--color-primary)] focus:ring-2 focus:ring-[var(--color-primary)]/20 disabled:opacity-50 dark:border-slate-600 dark:bg-slate-800 dark:text-white dark:placeholder-slate-500 [font-family:var(--font-dm-sans)]"
                          />
                        </div>
                      )}
                    </div>
                  )}

                  {phase === 'chatting' && currentField === 'budget' && (
                    <div className="space-y-4">
                      <ChipGrid
                        chips={BUDGET_CHIPS.map((chip) => `INR ${chip}`)}
                        columns={2}
                        disabled={isProcessing}
                        onSelect={(chip) => handleChipSelect(chip.replace(/^INR\s+/, ''))}
                      />
                      <form onSubmit={handleSubmit} className="space-y-3">
                        <label className="block text-sm font-medium text-[var(--color-foreground)] [font-family:var(--font-dm-sans)]">
                          Or enter a custom budget
                        </label>
                        <div className="relative">
                          <span className="pointer-events-none absolute inset-y-0 left-4 inline-flex items-center text-sm text-[var(--color-foreground-muted)]">
                            INR
                          </span>
                          <input
                            autoFocus
                            value={input}
                            onChange={(event) => setInput(event.target.value)}
                            type="text"
                            placeholder="150000"
                            disabled={isProcessing}
                            className="input min-h-[52px] rounded-xl border-[var(--color-border)] bg-[var(--color-card)] pr-4 text-[var(--color-foreground)]"
                            style={{ paddingLeft: '3.5rem' }}
                          />
                        </div>
                      </form>
                    </div>
                  )}

                  {phase === 'chatting' && currentField === 'accommodation' && (
                    <ChipGrid
                      chips={ACCOMMODATION_CHIPS}
                      columns={2}
                      disabled={isProcessing}
                      onSelect={handleChipSelect}
                      icons={{
                        Hotel: Bed,
                        'Airbnb / Villa': Bed,
                        Hostel: Bed,
                        Resort: Bed,
                        'Service Apartment': Bed,
                        'No preference': Bed,
                      }}
                    />
                  )}

                  {phase === 'chatting' && currentField === 'pace' && (
                    <ChipGrid
                      chips={PACE_CHIPS}
                      columns={1}
                      disabled={isProcessing}
                      onSelect={handleChipSelect}
                      icons={{
                        'Relaxed (fewer activities, more leisure)': Zap,
                        'Moderate (balanced mix)': Zap,
                        'Packed (maximum experiences)': Zap,
                      }}
                    />
                  )}

                  {phase === 'chatting' && currentField === 'themes' && (
                    <div className="space-y-4">
                      <ChipGrid
                        chips={THEME_CHIPS.filter((chip) => chip !== 'Skip →')}
                        columns={2}
                        disabled={isProcessing}
                        onSelect={handleThemeToggle}
                        selected={pendingThemeSelections}
                      />
                      <button
                        type="button"
                        onClick={() => {
                          setStepDirection('forward')
                          void handleAnswer('Skip →')
                        }}
                        className="btn btn-ghost w-full justify-center rounded-xl border-[var(--color-border)] text-[var(--color-foreground-muted)]"
                      >
                        Skip for now
                      </button>
                    </div>
                  )}

                  {phase === 'chatting' && currentField === 'refinement' && (
                    <div className="space-y-4">
                      <p className="text-sm text-[var(--color-foreground-muted)] [font-family:var(--font-dm-sans)]">
                        Type any special requests — dietary needs, mobility requirements, must-visit places, preferred transport, anything at all. Or skip ahead.
                      </p>
                      <form onSubmit={handleSubmit} className="space-y-3">
                        <textarea
                          autoFocus
                          value={input}
                          onChange={(e) => setInput(e.target.value)}
                          placeholder="e.g. Vegetarian meals only, avoid museums, include a beach day…"
                          rows={4}
                          disabled={isProcessing}
                          className="input min-h-[100px] resize-none rounded-xl border-[var(--color-border)] bg-[var(--color-card)] px-4 py-3 text-[var(--color-foreground)] [font-family:var(--font-dm-sans)]"
                          style={{ width: '100%' }}
                        />
                      </form>
                      <div className="flex gap-2">
                        <button
                          type="button"
                          disabled={isProcessing || !input.trim()}
                          onClick={() => {
                            setStepDirection('forward')
                            void handleAnswer(input)
                          }}
                          className="btn btn-primary flex-1 min-h-[44px] rounded-xl bg-[var(--color-primary)] text-[var(--color-on-primary)]"
                        >
                          {isProcessing ? <Loader2 className="h-4 w-4 animate-spin" /> : 'Send & Proceed'}
                        </button>
                        <button
                          type="button"
                          disabled={isProcessing}
                          onClick={() => {
                            setStepDirection('forward')
                            void handleAnswer('Looks good, proceed ✓')
                          }}
                          className="btn btn-ghost rounded-xl border-[var(--color-border)] px-4 text-[var(--color-foreground-muted)]"
                        >
                          Skip
                        </button>
                      </div>
                    </div>
                  )}
                </div>
              </div>
            )}

            <div ref={messagesEndRef} className="sr-only" />
          </div>
        </div>

        {showNavigation && (
          <div className="flex items-center justify-between border-t border-[var(--color-border)] bg-[var(--color-card)] px-8 py-6">
            <div>
              {currentStep > 1 ? (
                <button
                  type="button"
                  onClick={handleBack}
                  className="btn btn-ghost min-h-[44px] rounded-xl border-[var(--color-border)] px-4 text-[var(--color-foreground-muted)]"
                >
                  <ChevronLeft className="h-4 w-4" />
                  Back
                </button>
              ) : <span />}
            </div>

            <div className="flex items-center gap-3">
              {currentField === 'refinement' ? (
                <span />
              ) : currentField === 'themes' ? (
                <button
                  type="button"
                  onClick={handleThemesContinue}
                  disabled={continueDisabled}
                  className="btn btn-primary min-h-[44px] rounded-xl border-[var(--color-primary)] bg-[var(--color-primary)] px-5 text-white"
                >
                  {continueLabel}
                  <ChevronRight className="h-4 w-4" />
                </button>
              ) : currentField === 'group' ? (
                <button
                  type="button"
                  onClick={handleGroupContinue}
                  disabled={continueDisabled}
                  className="btn btn-primary min-h-[44px] rounded-xl border-[var(--color-primary)] bg-[var(--color-primary)] px-5 text-white"
                >
                  {continueLabel}
                  <ChevronRight className="h-4 w-4" />
                </button>
              ) : (
                <button
                  type="button"
                  onClick={() => {
                    if (currentField === 'origin' || currentField === 'destination' || currentField === 'dates' || currentField === 'budget') {
                      setStepDirection('forward')
                      void handleAnswer(input)
                    }
                  }}
                  disabled={continueDisabled}
                  className="btn btn-primary min-h-[44px] rounded-xl border-[var(--color-primary)] bg-[var(--color-primary)] px-5 text-white"
                >
                  {continueLabel}
                  <ChevronRight className="h-4 w-4" />
                </button>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

function getStepHeading(
  field: WizardField,
  phase: 'chatting' | 'summary' | 'generating' | 'done',
  groupStage: GroupStage,
  dateStage: DateStage,
  destinationSubStage: DestinationSubStage,
) {
  if (phase === 'summary') return 'Review your trip'
  if (phase === 'generating') return 'Creating your itinerary'
  if (phase === 'done') return 'Your itinerary is ready!'

  switch (field) {
    case 'purpose':
      return "What's the occasion?"
    case 'origin':
      return 'Flying from?'
    case 'destination_mode':
    case 'destination':
      if (destinationSubStage === 'multi-city-confirm') return 'Add another stop?'
      return 'Where to?'
    case 'duration':
      return 'How long?'
    case 'dates':
      return dateStage === 'custom-end' ? 'When do you return?' : 'When?'
    case 'group':
      if (groupStage === 'kids-count') return 'Any kids joining?'
      if (groupStage === 'kids-ages') return "What are the kids' ages?"
      return "Who's coming?"
    case 'budget':
      return "What's your budget?"
    case 'accommodation':
      return 'Where will you stay?'
    case 'pace':
      return "What's your pace?"
    case 'themes':
      return 'What interests you?'
    default:
      return 'Review your trip'
  }
}

function getStepHint(
  field: WizardField,
  phase: 'chatting' | 'summary' | 'generating' | 'done',
  groupStage: GroupStage,
  dateStage: DateStage,
  destinationSubStage: DestinationSubStage,
  config: TripConfig,
) {
  if (phase === 'summary') return 'Check everything once before generating your itinerary.'
  if (phase === 'generating') return 'We are turning your answers into a day-by-day plan.'
  if (phase === 'done') return 'Your trip plan is ready to explore.'

  switch (field) {
    case 'purpose':
      return 'Choose the main reason for this trip.'
    case 'origin':
      return 'Type the city you will be departing from.'
    case 'destination_mode':
      return 'Pick how you want to choose your destination.'
    case 'destination':
      if (config.destination_mode === 'country' && destinationSubStage === 'input') return 'Start with a country, then choose one or more cities.'
      if (config.destination_mode === 'country' && destinationSubStage === 'city-select') return 'Pick a city or type your own.'
      if (config.destination_mode === 'exploring' && destinationSubStage === 'input') return 'Describe the vibe, weather, or experiences you want.'
      if (config.destination_mode === 'exploring' && destinationSubStage === 'suggest-select') return 'Choose one of the recommended places.'
      if (destinationSubStage === 'multi-city-confirm') return 'You can add another city before continuing.'
      return 'Enter the destination city you have in mind.'
    case 'duration':
      return 'Choose a trip length that feels right.'
    case 'dates':
      return dateStage === 'preset' ? 'Choose a time window or enter exact dates.' : 'Use the YYYY-MM-DD format.'
    case 'group':
      if (groupStage === 'kids-count') return 'Add the number of children travelling with you.'
      if (groupStage === 'kids-ages') return 'Separate each age with a comma.'
      return 'Tell us who is travelling so we can tailor the itinerary.'
    case 'budget':
      return 'Select a range or enter a custom amount in INR.'
    case 'accommodation':
      return 'Choose the stay style you would enjoy most.'
    case 'pace':
      return 'Pick how relaxed or busy your trip should feel.'
    case 'themes':
      return 'Tap multiple themes, then continue.'
    default:
      return ''
  }
}

function isWizardErrorMessage(message: string) {
  const normalized = stripEmoji(message).toLowerCase()
  return normalized.includes('please')
    || normalized.includes("couldn't")
    || normalized.includes('could not')
    || normalized.includes('sorry')
    || normalized.includes('didn\'t quite understand')
    || normalized.includes('make sure')
}

function ErrorBanner({ message }: { message: string }) {
  return (
    <div className="mt-4 flex items-start gap-3 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-900 dark:bg-red-950/50 dark:text-red-400">
      <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
      <span>{message}</span>
    </div>
  )
}

function ChipGrid({
  chips,
  disabled,
  onSelect,
  selected = [],
  columns = 2,
  icons,
  descriptions,
}: {
  chips: string[]
  disabled: boolean
  onSelect: (chip: string) => void
  selected?: string[]
  columns?: 1 | 2 | 3
  icons?: Partial<Record<string, LucideIcon>>
  descriptions?: Partial<Record<string, string>>
}) {
  return (
    <div className={`grid gap-2.5 ${columns === 1 ? 'grid-cols-1' : columns === 3 ? 'grid-cols-3' : 'grid-cols-2'}`}>
      {chips.map((chip) => {
        const cleanLabel = chip === 'Skip →' ? chip : stripEmoji(chip)
        const isSelected = selected.includes(cleanLabel)
        const Icon = icons?.[chip]

        return (
          <button
            key={chip}
            type="button"
            disabled={disabled}
            onClick={() => onSelect(chip)}
            className={[
              'focus-ring flex min-h-[44px] cursor-pointer items-start gap-3 rounded-xl border bg-[var(--color-card)] px-4 py-3 text-left transition-all duration-150',
              isSelected
                ? 'border-[var(--color-primary)] bg-[color:color-mix(in_srgb,var(--color-primary)_10%,transparent)] text-[var(--color-primary)]'
                : 'border-[var(--color-border)] text-[var(--color-foreground)] hover:border-[var(--color-primary)] hover:bg-sky-50 dark:hover:bg-sky-950/30',
              disabled ? 'cursor-not-allowed opacity-60' : '',
            ].join(' ')}
          >
            {Icon && <Icon className="mt-0.5 h-4 w-4 shrink-0" />}
            <span className="min-w-0">
              <span className="block text-sm font-medium">{cleanLabel}</span>
              {descriptions?.[chip] && (
                <span className="mt-1 block text-xs text-[var(--color-foreground-muted)]">
                  {descriptions[chip]}
                </span>
              )}
            </span>
          </button>
        )
      })}
    </div>
  )
}

function CounterCard({
  label,
  hint,
  value,
  onDecrease,
  onIncrease,
}: {
  label: string
  hint: string
  value: number
  onDecrease: () => void
  onIncrease: () => void
}) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 dark:border-slate-700 dark:bg-slate-800">
      <div className="mb-4">
        <p className="text-sm font-bold text-[var(--color-primary)] [font-family:var(--font-dm-sans)]">{label}</p>
        <p className="mt-0.5 text-sm font-medium text-slate-500 dark:text-slate-400 [font-family:var(--font-dm-sans)]">{hint}</p>
      </div>

      <div className="flex items-center justify-between rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 dark:border-slate-600 dark:bg-slate-700/60">
        <button
          type="button"
          onClick={onDecrease}
          className="focus-ring inline-flex min-h-[44px] min-w-[44px] items-center justify-center rounded-xl border border-slate-300 bg-white text-xl font-bold text-slate-700 transition-colors hover:border-[var(--color-primary)] hover:text-[var(--color-primary)] dark:border-slate-500 dark:bg-slate-600 dark:text-slate-100 dark:hover:border-[var(--color-primary)] dark:hover:text-[var(--color-primary)]"
        >
          −
        </button>
        <span className="text-3xl font-extrabold text-slate-900 dark:text-white [font-family:var(--font-space-grotesk)]">
          {value}
        </span>
        <button
          type="button"
          onClick={onIncrease}
          className="focus-ring inline-flex min-h-[44px] min-w-[44px] items-center justify-center rounded-xl border border-slate-300 bg-white text-xl font-bold text-slate-700 transition-colors hover:border-[var(--color-primary)] hover:text-[var(--color-primary)] dark:border-slate-500 dark:bg-slate-600 dark:text-slate-100 dark:hover:border-[var(--color-primary)] dark:hover:text-[var(--color-primary)]"
        >
          +
        </button>
      </div>
    </div>
  )
}

function SummaryStepCard({
  labels,
  errorMessage,
  hasExistingItinerary,
  generateLabel,
  onEdit,
  onGenerate,
  onViewItinerary,
}: {
  labels: Record<(typeof SUMMARY_KEYS)[number], string>
  errorMessage: string | null
  hasExistingItinerary: boolean
  generateLabel: string
  onEdit: () => void
  onGenerate: () => void
  onViewItinerary: () => void
}) {
  return (
    <div className="space-y-5">
      <div className="card rounded-2xl border-[var(--color-border)] bg-[var(--color-card)] p-5">
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <SummaryRow icon={Target} label="Purpose" value={labels.purpose} />
          <SummaryRow icon={MapPin} label="From" value={labels.origin} />
          <SummaryRow icon={MapPin} label="Destination" value={labels.destination} />
          <SummaryRow icon={Calendar} label="Duration" value={labels.duration} />
          <SummaryRow icon={Calendar} label="Dates" value={labels.dates} />
          <SummaryRow icon={Users} label="Group" value={labels.group} />
          <SummaryRow icon={Wallet} label="Budget" value={labels.budget} />
          <SummaryRow icon={Bed} label="Stay" value={labels.accommodation} />
          <SummaryRow icon={Zap} label="Pace" value={labels.pace} />
          <SummaryRow icon={Heart} label="Themes" value={labels.themes} />
        </div>
      </div>

      {errorMessage && <ErrorBanner message={stripEmoji(errorMessage)} />}

      <button
        type="button"
        onClick={onGenerate}
        className="btn btn-accent h-14 w-full rounded-xl border-[var(--color-accent)] bg-[var(--color-accent)] text-base font-bold text-white"
      >
        {generateLabel}
      </button>

      {hasExistingItinerary && (
        <button
          type="button"
          onClick={onViewItinerary}
          className="btn btn-outline w-full rounded-xl border-[var(--color-primary)] px-4 text-[var(--color-primary)]"
        >
          View Current Itinerary
        </button>
      )}

      <button
        type="button"
        onClick={onEdit}
        className="btn btn-ghost w-full rounded-xl border-[var(--color-border)] text-[var(--color-foreground-muted)]"
      >
        ← Edit details
      </button>
    </div>
  )
}

function SummaryRow({
  icon: Icon,
  label,
  value,
}: {
  icon: LucideIcon
  label: string
  value: string
}) {
  return (
    <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-background)] p-4">
      <div className="flex items-start gap-3">
        <span className="inline-flex h-10 w-10 items-center justify-center rounded-full bg-[var(--color-primary)]/10 text-[var(--color-primary)]">
          <Icon className="h-4 w-4" />
        </span>
        <div className="min-w-0">
          <p className="text-xs uppercase tracking-wide text-[var(--color-foreground-muted)]">{label}</p>
          <p className="mt-1 text-sm font-medium text-[var(--color-foreground)]">{value}</p>
        </div>
      </div>
    </div>
  )
}

function GeneratingView({
  message,
  step,
  total,
}: {
  message: string
  step: number
  total: number
}) {
  const steps = Array.from({ length: total }, (_, index) => index + 1)

  return (
    <div className="flex min-h-[420px] flex-col items-center justify-center text-center">
      <span className="inline-flex h-20 w-20 items-center justify-center rounded-full bg-[var(--color-primary)]/10 text-[var(--color-primary)]">
        <Loader2 className="h-10 w-10 animate-spin" />
      </span>
      <h2 className="mt-6 text-2xl font-bold text-[var(--color-foreground)] [font-family:var(--font-space-grotesk)]">
        Building your itinerary
      </h2>
      <p className="mt-3 max-w-sm text-sm text-[var(--color-foreground-muted)] [font-family:var(--font-dm-sans)]">
        {message}
      </p>
      <div className="mt-6 flex items-center gap-3">
        {steps.map((current) => (
          <span
            key={current}
            className={`h-2.5 w-8 rounded-full ${current <= Math.max(step, 1) ? 'bg-[var(--color-primary)]' : 'bg-[var(--color-border)]'}`}
          />
        ))}
      </div>
    </div>
  )
}

function DoneView({ onViewItinerary }: { onViewItinerary: () => void }) {
  return (
    <div className="flex min-h-[420px] flex-col items-center justify-center text-center">
      <span className="inline-flex h-20 w-20 items-center justify-center rounded-full bg-emerald-500/10 text-emerald-500">
        <CheckCircle2 className="h-10 w-10" />
      </span>
      <h2 className="mt-6 text-2xl font-bold text-[var(--color-foreground)] [font-family:var(--font-space-grotesk)]">
        Your itinerary is ready!
      </h2>
      <p className="mt-3 text-sm text-[var(--color-foreground-muted)] [font-family:var(--font-dm-sans)]">
        Everything is set. Open your itinerary to start exploring.
      </p>
      <button
        type="button"
        onClick={onViewItinerary}
        className="btn btn-accent mt-8 h-14 rounded-xl border-[var(--color-accent)] bg-[var(--color-accent)] px-6 text-base font-bold text-white"
      >
        View Itinerary →
      </button>
    </div>
  )
}
