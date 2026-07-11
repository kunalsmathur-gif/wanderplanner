# Manual Browser Testing Guide for WanderPlanner

## Prerequisites
- ✅ Backend running on http://localhost:8000
- ✅ Frontend running on http://localhost:3000
- Browser with DevTools (Chrome/Firefox/Edge recommended)

---

## Testing Setup

### 1. Open Browser DevTools
1. Open http://localhost:3000 in your browser
2. Press `F12` or `Cmd+Option+I` (Mac) / `Ctrl+Shift+I` (Windows/Linux)
3. Go to **Console** tab - watch for errors
4. Go to **Network** tab - monitor API calls
5. Keep DevTools open throughout testing

### 2. Screen Recording Setup (macOS)
```bash
# Start screen recording with audio
# Press Cmd+Shift+5, select recording area, click "Record"

# Or use QuickTime Player:
# File → New Screen Recording
```

### 2. Screen Recording Setup (Windows)
```bash
# Press Windows+G to open Xbox Game Bar
# Click "Capture" → "Start Recording"

# Or use OBS Studio (free):
# https://obsproject.com/download
```

---

## Test Scenarios

### ✅ Test 1: Fixed Destination Flow

**Steps:**
1. Click "Start Planning with Anya 🗣️" button
2. Click chip: "Yes, I have one 📍"
3. Type: "Paris, France" and press Enter
4. Click chip: "Next month" (or type "next month")
5. Type budget: "150000" and press Enter
6. Click chip: "Hotels 🏨"
7. Click chip: "Moderate ⚖️" (or type "moderate")
8. Click chip: "Culture & History 🏛️" and "Food & Cuisine 🍜"
9. Watch itinerary generate

**Expected Results:**
- ✅ Each response triggers next question smoothly
- ✅ No console errors
- ✅ Listening Orb breathing animation smooth
- ✅ Progress bar updates with each answer
- ✅ Itinerary appears with 3-column layout
- ✅ Travel tips load with thumbnails
- ✅ Map shows Paris location

**Look for:**
- ❌ Hydration errors in console
- ❌ Failed API calls in Network tab
- ❌ Broken layout or overlapping elements
- ❌ Chips not clickable after typing

---

### ✅ Test 2: Suggest Mode (Fuzzy Matching)

**Steps:**
1. Refresh page, click "Start Planning with Anya 🗣️"
2. **Type (don't click chip):** "suggest me something"
   - ✅ Should trigger suggest mode
3. Type duration: "7 days" and press Enter
4. Type preferences: "beaches and cafes" and press Enter
5. Wait for city suggestions
6. Click a city chip (e.g., "Phuket, Thailand")
7. Complete remaining questions

**Expected Results:**
- ✅ Fuzzy text "suggest me something" triggers suggest mode
- ✅ Duration question appears
- ✅ City recommendations appear (5 chips)
- ✅ Itinerary generates for selected city

**Fuzzy Matching Tests:**
Try these text inputs instead of clicking chips:

| Field | Try Typing | Expected |
|-------|-----------|----------|
| Destination mode | "recommend something" | Suggest mode |
| Destination mode | "help me choose" | Suggest mode |
| Destination mode | "i want to explore thailand" | Country mode |
| Destination mode | "gibberish xyz" | Clarification prompt |
| Dates | "flexible dates" | Flexible: true |
| Dates | "not sure" | Flexible: true |
| Dates | "this month" | This month chip |
| Pace | "slow and relaxed" | Relaxed pace |
| Pace | "busy schedule" | Packed pace |

**Look for:**
- ❌ Text ignored, no response
- ❌ Chips become unclickable after typing
- ❌ Dead-end states (no way to proceed)

---

### ✅ Test 3: Explore by Country Mode

**Steps:**
1. Refresh page, click "Start Planning with Anya 🗣️"
2. Click chip: "I'm exploring 🌍"
3. Type: "Thailand" and press Enter
4. Wait for city suggestions
5. Click first city (e.g., "Bangkok, Thailand")
6. Click "Add another city ➕"
7. Click second city (e.g., "Phuket, Thailand")
8. Click "Sounds good 👍"
9. Complete remaining questions

**Expected Results:**
- ✅ Multi-city selection flow works
- ✅ Can add multiple cities (2-3)
- ✅ "Sounds good 👍" confirms selection
- ✅ Itinerary handles multiple destinations

**Look for:**
- ❌ Can't select second city
- ❌ "Sounds good" button doesn't proceed
- ❌ Itinerary only shows one city

---

### ✅ Test 4: Voice Feature

**Steps:**
1. Click Listening Orb (circular breathing button)
2. Allow microphone access if prompted
3. Say: "I want to visit Paris"
4. Check if speech recognized
5. Continue conversation with voice OR text

**Expected Results:**
- ✅ Microphone permission prompt appears
- ✅ Orb shows recording state (red/pulsing)
- ✅ Speech transcribed to text
- ✅ Can switch between voice and text freely

**Look for:**
- ❌ Microphone not accessible
- ❌ Speech not transcribed
- ❌ Orb animation broken

---

### ✅ Test 5: Persistent Orb (Itinerary Page)

**Steps:**
1. Complete any flow to reach itinerary page
2. Look for floating circular button (bottom-right)
3. Click the floating Listening Orb
4. Verify wizard reopens

**Expected Results:**
- ✅ FloatingAnyaButton visible on itinerary page
- ✅ Circular shape (not oval)
- ✅ Breathing animation smooth
- ✅ Clicking reopens wizard
- ✅ No nested button errors in console

**Look for:**
- ❌ Button missing on itinerary page
- ❌ Oval shape instead of circular
- ❌ Nested button console errors

---

### ✅ Test 6: Error Handling

**Test API Failures:**
1. Stop backend server: `kill <PID>`
2. Try starting new conversation
3. Check error messages

**Expected Results:**
- ✅ Graceful error message shown
- ✅ No crash or blank screen
- ✅ User can retry

**Test Invalid Inputs:**
1. Type special characters: `@#$%^&*()`
2. Type very long text (1000+ characters)
3. Leave input empty and submit

**Expected Results:**
- ✅ Validates input gracefully
- ✅ Re-prompts for valid input
- ✅ No console errors

---

### ✅ Test 7: UI/UX Polish

**Check These:**
- [ ] Three-column layout (25% | 50% | 25%)
- [ ] Listening Orb is perfectly circular
- [ ] Progress bar animates smoothly
- [ ] Chips have hover states
- [ ] Text input has focus state
- [ ] Travel tips have YouTube thumbnails
- [ ] Map loads and shows correct location
- [ ] Typography: Fraunces for headings, Inter for body
- [ ] Colors: Passport Navy, Horizon Amber, Map Ivory
- [ ] No text cutoff or overlapping elements
- [ ] Scrolling works in each column independently

---

### ✅ Test 8: Edge Cases

1. **Refresh During Conversation:**
   - Start conversation, refresh mid-flow
   - Expected: State lost (acceptable) or preserved (ideal)

2. **Multiple Wizards:**
   - Open wizard, close it, open again
   - Expected: Clean state, no duplicate messages

3. **Empty Responses:**
   - API returns no cities
   - Expected: Fallback message shown

4. **Very Long Text:**
   - Type 500+ character response
   - Expected: Handled gracefully

---

## Checklist for Recording

When doing screen recording, demonstrate:
- ✅ All three conversation modes (fixed, suggest, explore)
- ✅ Fuzzy text input matching
- ✅ Multi-city selection
- ✅ Voice feature (if microphone available)
- ✅ Persistent orb on itinerary page
- ✅ Travel tips with thumbnails
- ✅ Error recovery
- ✅ Complete end-to-end flow (start to itinerary)

---

## Console Errors to Watch For

**Critical (Must Fix):**
- ❌ Hydration errors: "Text content does not match..."
- ❌ Uncaught exceptions
- ❌ Failed API calls (500 errors)
- ❌ "Cannot read property of undefined"

**Warnings (Should Fix):**
- ⚠️ Missing keys in lists
- ⚠️ Deprecated API usage
- ⚠️ Performance warnings

**Acceptable:**
- ✅ 404 for optional resources (fonts, icons)
- ✅ CORS preflight requests
- ✅ React DevTools messages

---

## Network Tab Monitoring

**Watch these API calls:**
1. `/api/travel-tips?destination=...`
   - Status: 200
   - Response time: < 1s
   
2. `/api/recommend-cities`
   - Status: 200
   - Response time: 1-3s (Gemini) or ~50ms (mock)
   
3. `/api/itinerary`
   - Status: 200
   - Response time: 2-5s
   
4. `/api/youtube-thumbnail`
   - Status: 200
   - Multiple calls for each tip

**Red Flags:**
- ❌ Status 500 (server error)
- ❌ Status 422 (validation error)
- ❌ Timeout (> 30s)
- ❌ Failed requests (red in Network tab)

---

## Reporting Issues

If you find bugs, note:
1. **Steps to reproduce** (exact clicks/typing)
2. **Expected behavior** (what should happen)
3. **Actual behavior** (what actually happened)
4. **Console errors** (copy/paste from DevTools)
5. **Network failures** (screenshot Network tab)
6. **Screenshot/video** (visual proof)

---

## Quick Recording Script

```bash
# macOS: Start recording
# 1. Press Cmd+Shift+5
# 2. Select screen area
# 3. Click "Record"
# 4. Stop with menu bar icon

# Test flow (2-3 minutes):
# 1. Open http://localhost:3000
# 2. Show DevTools console (no errors)
# 3. Start conversation - click "Start Planning"
# 4. Demonstrate fuzzy matching - type "suggest me"
# 5. Complete suggest flow with duration
# 6. Select a city
# 7. Answer remaining questions (chips AND text)
# 8. Show generated itinerary
# 9. Click floating orb to reopen wizard
# 10. Show console - no errors

# Save recording to: ./recordings/wanderplanner-e2e-test.mov
```

---

## Success Criteria

✅ **PASS if:**
- No critical console errors
- All conversation flows complete
- Fuzzy text matching works
- Persistent orb appears on itinerary
- Itinerary generates successfully
- Travel tips load with thumbnails
- UI is polished and responsive

❌ **FAIL if:**
- Hydration errors in console
- Conversation gets stuck
- Chips don't work after typing
- Missing persistent orb
- 500 API errors
- Broken layout

---

## Tools Recommendation

If you want automated testing later:
- **Playwright** - Fast, reliable browser automation
- **Cypress** - Great DevEx, visual testing
- **Selenium** - Cross-browser support

Install Playwright:
```bash
npm install -D @playwright/test
npx playwright install
```

Create `tests/e2e.spec.ts`:
```typescript
import { test, expect } from '@playwright/test';

test('conversation flow', async ({ page }) => {
  await page.goto('http://localhost:3000');
  await page.click('text=Start Planning with Anya');
  await page.click('text=Yes, I have one');
  // ... more steps
});
```

---

**Happy Testing! 🧪**
