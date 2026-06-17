# End-to-End Testing Report - WanderPlan v2.1

**Test Date:** 2026-06-17 19:03 IST  
**Tester:** Copilot CLI  
**Build:** feat/frontend-scaffold (commit 5b4eefd)

---

## 🎯 Test Scope

1. **Server Health Checks**
2. **Console Errors & Warnings**
3. **Conversation Flow Testing**
4. **Fuzzy Input Matching**
5. **UI/UX Hygiene**
6. **Edge Cases & Error Handling**

---

## ✅ 1. Server Health Checks

### Backend API (Port 8000)
- [ ] Health endpoint responding
- [ ] Travel tips endpoint
- [ ] Recommend cities endpoint
- [ ] Reddit highlights endpoint

### Frontend (Port 3000)
- [ ] Next.js dev server running
- [ ] Homepage loads without errors
- [ ] Static assets loading
- [ ] Fonts loading correctly

---

## 🔍 2. Console Errors & Warnings

### Critical Issues to Check
- [ ] Hydration mismatches
- [ ] Nested button warnings
- [ ] React key warnings
- [ ] API 500 errors
- [ ] Network failures
- [ ] Unhandled promise rejections

### Warnings to Investigate
- [ ] Deprecated API usage
- [ ] Missing dependencies in useEffect
- [ ] Performance warnings
- [ ] Accessibility warnings

---

## 💬 3. Conversation Flow Testing

### Flow A: Fixed Destination Mode
1. [ ] Click "Start Planning with Anya 🗣️"
2. [ ] Click "Yes, I have one 📍" chip
3. [ ] Type destination (e.g., "Paris")
4. [ ] Verify destination selected
5. [ ] Answer dates question (chip or text)
6. [ ] Answer budget question
7. [ ] Answer accommodation
8. [ ] Answer pace
9. [ ] Answer themes
10. [ ] Verify itinerary generation

### Flow B: Suggest Mode
1. [ ] Click "Start Planning with Anya 🗣️"
2. [ ] Click "Suggest me! ✨" chip
3. [ ] Enter duration (e.g., "7 days")
4. [ ] Enter preferences (e.g., "beaches and cafes")
5. [ ] Verify city suggestions appear
6. [ ] Select a city from suggestions
7. [ ] Complete remaining questions
8. [ ] Verify itinerary generation

### Flow C: Explore by Country
1. [ ] Click "Start Planning with Anya 🗣️"
2. [ ] Click "I'm exploring 🌍" chip
3. [ ] Enter country (e.g., "Thailand")
4. [ ] Verify city suggestions appear
5. [ ] Select a city
6. [ ] Complete flow

### Flow D: Multi-City Selection
1. [ ] Start with "I'm exploring 🌍"
2. [ ] Enter country
3. [ ] Select first city
4. [ ] Click "Add another city ➕"
5. [ ] Select second city
6. [ ] Click "Sounds good 👍"
7. [ ] Verify multi-city handling

---

## 🧪 4. Fuzzy Input Matching Tests

### Destination Mode (Text vs Chips)
- [ ] Type "i want suggestions" → should trigger suggest mode
- [ ] Type "recommend something" → should trigger suggest mode
- [ ] Type "help me choose" → should trigger suggest mode
- [ ] Type "thailand" → should trigger country explore mode
- [ ] Type "yes" → should trigger fixed destination mode
- [ ] Type "gibberish xyz" → should show clarification prompt

### Dates Field
- [ ] Type "flexible" → should set flexible: true
- [ ] Type "not sure" → should set flexible: true
- [ ] Type "this month" → should set thisMonth
- [ ] Type "next month" → should set nextMonth
- [ ] Type "3 months" → should set inThreeMonths
- [ ] Type "summer vacation" → should accept as text

### Pace Field
- [ ] Type "slow" → should set relaxed
- [ ] Type "chill" → should set relaxed
- [ ] Type "busy" → should set packed
- [ ] Type "intense" → should set packed
- [ ] Type "moderate" → should default to moderate

---

## 🎨 5. UI/UX Hygiene Checks

### Layout & Spacing
- [ ] Three-column layout (25% | 50% | 25%)
- [ ] Proper spacing between elements
- [ ] No overlapping UI elements
- [ ] Scrolling works in each column
- [ ] No content cutoff

### Typography
- [ ] Fraunces for headings
- [ ] Inter for body text
- [ ] JetBrains Mono for data
- [ ] Font sizes legible
- [ ] Line heights comfortable

### Color Consistency
- [ ] Passport Navy (#1A3A52) used correctly
- [ ] Horizon Amber (#E88D3A) for accents
- [ ] Map Ivory (#F7F4EF) for backgrounds
- [ ] No random color deviations

### Interactive Elements
- [ ] Chips clickable and responsive
- [ ] Buttons have hover states
- [ ] Input fields have focus states
- [ ] Voice button (Listening Orb) animates
- [ ] Loading states visible

### Listening Orb (Voice Button)
- [ ] Visible in wizard
- [ ] FloatingAnyaButton appears on itinerary page
- [ ] Circular (not oval) shape
- [ ] Breathing animation smooth
- [ ] No nested button errors

---

## ⚠️ 6. Edge Cases & Error Handling

### API Failures
- [ ] Gemini 503 error → falls back to mock
- [ ] Travel tips empty → shows fallback tips
- [ ] YouTube API fails → gracefully hides thumbnails
- [ ] Network timeout → shows error message

### Invalid Inputs
- [ ] Empty destination → prompts again
- [ ] Invalid dates → handles gracefully
- [ ] Budget 0 or negative → validation
- [ ] Special characters in inputs

### State Management
- [ ] Back button doesn't break flow
- [ ] Refresh maintains state (if applicable)
- [ ] Multiple wizards don't conflict
- [ ] Store updates properly

---

## 🐛 Known Issues to Verify Fixed

1. ✅ Nested button hydration error
2. ✅ Travel tips API fallback
3. ✅ YouTube thumbnails loading
4. ✅ Persistent Listening Orb on itinerary page
5. ✅ Multi-city selection flow
6. ✅ Duration question in suggest mode
7. ✅ Chip vs text input deadlock
8. ✅ Gemini 503 error handling

---

## 📋 Test Results

### Critical Issues Found
<!-- To be filled during testing -->

### Medium Priority Issues
<!-- To be filled during testing -->

### Low Priority / Polish
<!-- To be filled during testing -->

---

## 📝 Notes

<!-- Additional observations during testing -->
