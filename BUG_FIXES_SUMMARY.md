# WanderPlan Bug Fixes Summary

## Status: 1/5 Fixed, 4 Pending Investigation

---

## ✅ Fixed Bugs

### 1. **Listening Orb Disappears on Itinerary Page** ✓
**Issue:** Chat bubble/orb disappears after itinerary is generated. Should always be visible as an entry point to Anya.

**Fix Applied:**
- Created `FloatingAnyaButton.tsx` component
- Added persistent floating Anya button in bottom-right corner
- Button shows circular ListeningOrb with "Anya" label
- Appears on itinerary page when wizard is closed
- Click opens conversational wizard

**Files Modified:**
- `apps/web/components/common/FloatingAnyaButton.tsx` (NEW)
- `apps/web/app/page.tsx`

**Status:** ✅ FIXED - Ready for testing

---

## 🔍 Bugs Requiring Further Investigation

### 2. **Travel Tips Links Not Working**
**Issue:** Article/tips links are outdated and no longer hosted by those platforms.

**Investigation Findings:**
- Travel tips API (`/api/travel-tips`) returns empty results
- Two sources: Reddit API + Gemini-generated tips
- Reddit API may be blocking/rate-limiting requests
- Gemini tips generation may be failing silently

**Potential Solutions:**
1. Add better error logging to see which source fails
2. Implement fallback mock data for demos
3. Cache successful responses longer
4. Switch to alternative Reddit API endpoints
5. Consider using Reddit RSS feeds instead

**Status:** 🔍 NEEDS INVESTIGATION

---

### 3. **YouTube Thumbnails Not Loading**
**Issue:** YouTube thumbnails not appearing in travel tips section.

**Investigation Findings:**
- YouTube thumbnail API (`/api/youtube-thumbnail`) exists and works
- Returns correct video IDs and thumbnail URLs
- Issue: Thumbnails are NOT being displayed in the UI
- `Column3Sidebar.tsx` shows travel tips but without thumbnails

**Root Cause:** The YouTube thumbnail functionality was built but never integrated into the travel tips display component.

**Potential Solutions:**
1. Add thumbnail images to travel tip cards in `Column3Sidebar.tsx`
2. Fetch thumbnail for each tip using the `/api/youtube-thumbnail` endpoint
3. Show placeholder/fallback if thumbnail fails to load

**Status:** 🔍 NEEDS IMPLEMENTATION

---

### 4. **Multi-Destination Not Supported in Recommendations**
**Issue:** When user wants recommendations, system does not allow adding multiple locations. Even when user says they have a fixed location in mind and enters a country, it is not asking which cities.

**Investigation Findings:**
- Need to review conversational flow in `ConversationalWizard.tsx`
- Check `destination_mode` handling: 'fixed', 'country', 'exploring'
- Verify `recommendCities` API is being called correctly
- Check if `city_selection` field is properly handled

**Expected Flow:**
1. User selects "I want recommendations"
2. System asks "Which country?"
3. User enters country (e.g., "France")
4. System calls `/api/recommend-cities` with country
5. System shows city options (Paris, Lyon, Nice, etc.)
6. User can select multiple cities
7. System generates itinerary covering multiple cities

**Status:** 🔍 NEEDS CODE REVIEW

---

### 5. **Suggest Flow Missing Duration Question**
**Issue:** When asking to suggest destinations, Anya does not ask how many days the user wants to spend.

**Investigation Findings:**
- Need to review field progression logic
- Check if 'duration' field is being asked in 'exploring' mode
- Verify DATE_CHIPS includes duration options

**Expected Flow:**
1. User selects "Surprise me / I'm exploring"
2. System asks about themes/preferences
3. **System should ask: "How long is your trip?"**
4. User provides duration (3 days, 7 days, etc.)
5. System generates recommendations based on duration + themes

**Status:** 🔍 NEEDS CODE REVIEW

---

## 🧪 Testing Recommendations

### For Fixed Bugs:
1. ✅ Clear browser cache and reload http://localhost:3000
2. ✅ Generate an itinerary
3. ✅ Verify floating Anya button appears in bottom-right
4. ✅ Click button to reopen wizard
5. ✅ Verify button disappears when wizard is open

### For Pending Bugs:
**Travel Tips (#2):**
- Check API logs for errors: `/api/travel-tips?destination=Paris`
- Test Reddit endpoint directly
- Verify Gemini API key is valid

**YouTube Thumbnails (#3):**
- Open browser console
- Check if `/api/youtube-thumbnail` is being called
- Verify images are in DOM but failing to load
- Check for CORS issues

**Multi-Destination (#4):**
- Start conversation with "I want recommendations"
- Select "I have a specific country in mind"
- Enter "France"
- Verify system asks which cities
- Try selecting multiple cities

**Suggest Duration (#5):**
- Start conversation with "Surprise me"
- Complete theme selection
- Check if duration question appears before location question

---

## 📋 Next Steps

1. **Priority 1:** Test fixed floating Anya button
2. **Priority 2:** Add debug logging to travel tips API
3. **Priority 3:** Integrate YouTube thumbnails into tip cards
4. **Priority 4:** Review and fix destination recommendation flow
5. **Priority 5:** Add duration question to suggest flow

---

## 🎯 Files to Review for Pending Bugs

**Conversation Flow (#4, #5):**
- `apps/web/components/wizard/ConversationalWizard.tsx`
- Lines 172-210: `promptForField()` function
- Lines 300-600: `handleAnswer()` logic
- Check field progression order

**Travel Tips (#2, #3):**
- `apps/api/routers/travel_tips.py`
- `apps/web/components/itinerary/Column3Sidebar.tsx`
- `apps/web/app/api/youtube-thumbnail/route.ts`

---

**Last Updated:** June 17, 2026  
**Next Action:** Test floating Anya button, then investigate conversation flow bugs.
