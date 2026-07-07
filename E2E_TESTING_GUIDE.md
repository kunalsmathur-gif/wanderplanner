# WanderPlanner End-to-End Testing & Screen Recording Guide

## 🎬 Screen Recording Setup (macOS)

### Option 1: Built-in Screen Recording (QuickTime)
1. Press **Cmd + Space**, type "QuickTime Player"
2. Go to **File → New Screen Recording**
3. Click the record button and select the area to record
4. Click **Start Recording**
5. When done, press **Cmd + Control + Esc** to stop

### Option 2: Built-in Screenshot Toolbar (Easier!)
1. Press **Cmd + Shift + 5**
2. Select "Record Entire Screen" or "Record Selected Portion"
3. Click **Record**
4. Stop recording from menu bar or press **Cmd + Control + Esc**
5. Video saves automatically to Desktop

### Option 3: Professional Recording (OBS Studio)
If you need more control:
```bash
brew install --cask obs
```
Then open OBS and configure screen capture source.

---

## ✅ Pre-Test Checklist

### Servers Running:
- [ ] Frontend: http://localhost:3000
- [ ] Backend API: http://localhost:8000
- [ ] Health check: http://localhost:8000/health

### Environment Variables:
- [ ] GEMINI_API_KEY is set
- [ ] QDRANT_URL is configured
- [ ] All required API keys are present

---

## 🧪 End-to-End Test Scenarios

### **Test 1: First-Time User Experience (5-7 minutes)**

#### Objective: Complete flow from landing page to itinerary generation

**Steps:**
1. **Landing Page**
   - [ ] Open http://localhost:3000
   - [ ] Verify hero section loads with new design
   - [ ] Check that "Start Planning" button is visible
   
2. **Open Conversational Wizard**
   - [ ] Click "Start Planning"
   - [ ] Verify Anya's header appears with:
     - Fraunces font for "Anya"
     - Map texture background (Passport Navy #1A3A52)
     - Circular ListeningOrb in top-right
   - [ ] Check progress bar (0% initially)
   
3. **Conversational Flow - Text Input**
   - [ ] Read Anya's greeting: "Hi! I'm Anya from WanderPlanner..."
   - [ ] Answer each question via text:
     - **Purpose:** Click stamp chip (e.g., "Leisure 🏖️")
     - **Destination:** Type "Paris, France"
     - **Start Date:** Type date or click chip (e.g., "Next Month")
     - **Duration:** Click "7 Days"
     - **Budget:** Select chip (e.g., "₹1,00,000 - ₹2,50,000")
     - **Group:** Select "2 Adults"
     - **Accommodation:** Click "4-Star Hotel"
     - **Pace:** Select "Relaxed"
     - **Themes:** Select 2-3 themes (e.g., "Art & Culture", "Food & Wine")
   - [ ] Verify stamp chips have:
     - Dashed borders
     - Slight rotation
     - Horizon Amber (#E88D3A) when selected
   - [ ] Check progress bar increases with each answer
   
4. **Summary Screen**
   - [ ] Verify all captured details are shown
   - [ ] Check "Generate Itinerary" button (Earth Clay #B85C3F)
   - [ ] Click "Generate Itinerary"
   
5. **Generation Phase**
   - [ ] Verify loading spinner (Horizon Amber color)
   - [ ] Check progress messages appear
   - [ ] Wait for completion (30-60 seconds)
   
6. **Itinerary View**
   - [ ] Verify wizard closes automatically
   - [ ] Check three-column layout:
     - Left sidebar (25%): Trip snapshot with metrics
     - Center (50%): Day-by-day timeline on Map Ivory background
     - Right sidebar (25%): Map + Travel Tips
   - [ ] Verify new color scheme throughout
   - [ ] Check day cards render properly
   - [ ] Scroll through full itinerary

---

### **Test 2: Voice Assistant (Anya) - 3-4 minutes**

#### Objective: Test voice input/output with new Listening Orb

**Steps:**
1. **Activate Voice Mode**
   - [ ] Open conversational wizard
   - [ ] Click the circular **ListeningOrb** in header
   - [ ] Verify orb animates:
     - Breathing gets faster
     - Pulse rings appear
     - Gradient glows (Amber → Periwinkle)
   
2. **Voice Input**
   - [ ] Speak your answer (e.g., "I want a leisure trip")
   - [ ] Verify browser requests microphone permission
   - [ ] Check red recording dot appears
   - [ ] See your speech transcribed to text input
   
3. **Voice Output**
   - [ ] Listen to Anya speak the question
   - [ ] Verify female Indian accent voice
   - [ ] Check voice is natural and clear
   
4. **Deactivate Voice Mode**
   - [ ] Click ListeningOrb again
   - [ ] Verify pulse rings disappear
   - [ ] Orb returns to slow breathing animation

---

### **Test 3: Edit & Regenerate - 3-4 minutes**

#### Objective: Modify trip parameters and regenerate

**Steps:**
1. **From Itinerary View**
   - [ ] Click "Edit Trip" button in left sidebar
   - [ ] Wizard reopens in summary mode
   
2. **Modify Parameters**
   - [ ] Change duration (e.g., 7 days → 5 days)
   - [ ] Update budget range
   - [ ] Add/remove themes
   
3. **Regenerate**
   - [ ] Click "Regenerate Itinerary"
   - [ ] Verify new itinerary reflects changes
   - [ ] Compare with previous version

---

### **Test 4: Compare Itineraries - 2-3 minutes**

#### Objective: View side-by-side comparison

**Steps:**
1. **Trigger Comparison**
   - [ ] Click "Compare" button in left sidebar
   - [ ] Verify comparison panel opens
   
2. **Review Comparison**
   - [ ] Check side-by-side layout
   - [ ] Verify differences are highlighted
   - [ ] Test scrolling both panels
   
3. **Close Comparison**
   - [ ] Click "Close" or "Back to Itinerary"
   - [ ] Return to normal itinerary view

---

### **Test 5: PDF Export - 2 minutes**

#### Objective: Download itinerary as PDF

**Steps:**
1. **Generate PDF**
   - [ ] Click "Download PDF" in left sidebar
   - [ ] Wait for PDF generation
   - [ ] Verify download starts
   
2. **Review PDF**
   - [ ] Open downloaded PDF
   - [ ] Check formatting and content
   - [ ] Verify all days are included

---

### **Test 6: Mobile Warning - 1 minute**

#### Objective: Test mobile responsiveness warning

**Steps:**
1. **Resize Browser**
   - [ ] Make browser window narrow (< 1024px)
   - [ ] Verify mobile warning banner appears
   - [ ] Check message is clear
   
2. **Restore Desktop View**
   - [ ] Expand browser window
   - [ ] Verify warning disappears

---

## 🎨 Design Review Checklist

While testing, verify these new design elements:

### Colors:
- [ ] Passport Navy (#1A3A52) - Headers, user messages
- [ ] Horizon Amber (#E88D3A) - Progress bar, accents, orb gradient
- [ ] Map Ivory (#F7F4EF) - Center itinerary background
- [ ] Earth Clay (#B85C3F) - Primary CTA buttons
- [ ] Sky Periwinkle (#A8BFDB) - Subtitles, orb gradient

### Typography:
- [ ] Fraunces - "Anya" in header (with wonky axis)
- [ ] Inter - Body text (tightened tracking)
- [ ] JetBrains Mono - Timestamps, budget figures

### Components:
- [ ] ListeningOrb - Circular, breathing animation
- [ ] StampChips - Dashed borders, rotation, texture
- [ ] Layout - 25%-50%-25% with inset shadows

---


## 🔁 Full-Stack Regression Checklist

Run this before every release that touches auth, itinerary generation, analytics, or the new Postgres-backed account flows. Use the detailed cases in `docs/eval-set.md` as the source of truth; this checklist is only the release gate.

| Area | Mode | Release checklist | Traceability |
|---|---|---|---|
| Authentication & session lifecycle | Automated API smoke + manual Google SSO smoke | [ ] Verify signup, duplicate-email handling, password validation, login, Google SSO success/failure, refresh rotation, logout, and `/auth/me` unauthenticated behavior | `AUTH-001` → `AUTH-012` |
| Password reset | Automated API + manual email-link smoke | [ ] Verify forgot-password non-enumeration, valid reset, reused/expired/malformed token rejection, and reset-password strength checks | `PWRESET-001` → `PWRESET-006` |
| Consent capture & legal disclosure | Manual browser + spot-check in DB/admin tooling | [ ] Verify signup consent checkbox enforcement, `/terms` + `/privacy` links, consent timestamp persistence, and copy consistency with the legal pages | `CONSENT-001` → `CONSENT-004` |
| Itinerary auth gate & resume-after-auth | Manual browser + targeted API smoke | [ ] Verify logged-out generate redirects to signup, pending trip config survives full-page Google OAuth, auth success auto-resumes generation, and direct unauthenticated generation calls return 401 | `GATE-001` → `GATE-004` |
| Self-service account deletion | Manual browser + API verification | [ ] Verify `/account` requires `DELETE`, account deletion clears the session, and refresh-token rows are removed/anonymized as documented | `PURGE-001`, `PURGE-002` |
| Admin dashboard & admin delete flows | Manual browser + admin API smoke | [ ] Verify `/admin` 401/403 gating, summary cards, 7d/30d chart, cost cards, single-user delete, self-delete block, and bulk purge confirmation flow | `ADMIN-001` → `ADMIN-006`, `PURGE-003` → `PURGE-006` |
| Cost / usage analytics | Automated integration smoke + manual admin spot-check | [ ] Verify aggregated `gemini_usage` events, uncached-only Pexels counting, and YouTube thumbnail client beacons | `COST-021` → `COST-024` |

**Minimum manual release sweep:** Google SSO happy path, forgot-password email flow, logged-out itinerary → signup → auto-resume, `/account` self-delete confirmation, `/admin` bulk purge confirmation (against seeded non-production data only).

---

## 🐛 Issues to Watch For

### Common Issues:
- [ ] Voice recognition not working (browser compatibility)
- [ ] Slow API responses (Gemini rate limits)
- [ ] Missing environment variables
- [ ] Layout breaking on certain screen sizes
- [ ] Font not loading (check network tab)

### Performance Metrics:
- [ ] Wizard opens in < 500ms
- [ ] Itinerary generation < 60 seconds
- [ ] Page transitions smooth (no jank)
- [ ] Voice latency < 2 seconds

---

## 📊 Test Data Suggestions

### Quick Test Trips:
1. **Paris Weekend** - 3 days, ₹1L-2L, Leisure, Art & Culture
2. **Bali Adventure** - 7 days, ₹2L-5L, Adventure, Beach + Nature
3. **Dubai Business+Leisure** - 5 days, ₹3L-5L, Luxury + Shopping
4. **Goa Family Trip** - 4 days, ₹50K-1L, Family, Beach + Food

---

## 🎬 Screen Recording Tips

### Before Recording:
1. Close unnecessary tabs/windows
2. Set browser to full screen (Cmd + Ctrl + F)
3. Clear browser console
4. Have test data ready
5. Disable notifications (Do Not Disturb mode)

### During Recording:
1. Speak clearly describing what you're doing
2. Move cursor slowly and deliberately
3. Pause 2-3 seconds on each screen
4. Highlight key interactions (clicks, form fills)
5. Show success/error states

### After Recording:
1. Review the video
2. Note timestamp of any bugs
3. Export in standard format (MP4)
4. Store in `wanderplanner/recordings/` folder

---

## 📝 Bug Report Template

If you find issues, document them:

```markdown
## Bug: [Short Description]

**Severity:** Critical / High / Medium / Low

**Steps to Reproduce:**
1. 
2. 
3. 

**Expected:** 
**Actual:** 

**Screenshot/Video:** 
**Timestamp in Recording:** 

**Browser:** 
**Environment:** 
```

---

## ✅ Final Checklist

After testing:
- [ ] All 6 test scenarios completed
- [ ] Screen recording saved
- [ ] Bugs documented (if any)
- [ ] Design elements verified
- [ ] Performance acceptable
- [ ] Ready for stakeholder demo

---

**Estimated Total Test Time:** 20-25 minutes  
**Recording File Size:** ~200-500 MB (depending on quality)

**Ready to start? Run:**
```bash
open http://localhost:3000
# Then press Cmd + Shift + 5 to start recording!
```
