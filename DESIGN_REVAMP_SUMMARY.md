# WanderPlan Design Revamp — Implementation Summary

## Overview
This document summarizes the comprehensive design overhaul of WanderPlan, transforming it from a generic SaaS interface to a distinctive travel platform with a visual identity rooted in physical travel artifacts (vintage luggage tags, weathered maps, passport stamps).

---

## ✨ Key Changes Implemented

### 1. **Color Palette** — From Generic to Travel-Inspired

**Before:**
- `#1E40AF` - Generic Tailwind blue (SaaS default)
- `#047857` - Emerald green
- `#D97706` - Amber gold

**After:**
- `#1A3A52` - **Passport Navy** (deep, trustworthy)
- `#E88D3A` - **Horizon Amber** (sunset glow, warmth)
- `#F7F4EF` - **Map Ivory** (aged paper texture)
- `#2C3338` - **Ink Charcoal** (grounded body text)
- `#A8BFDB` - **Sky Periwinkle** (light accents)
- `#B85C3F` - **Earth Clay** (CTAs, urgency)

**Rationale:** Colors now evoke physical travel materials (leather-bound journals, vintage luggage tags, aged maps) rather than corporate dashboards.

---

### 2. **Typography** — Three Distinctive Faces

**Before:**
- Geist (neutral sans-serif) for everything

**After:**
- **Display:** Fraunces (variable serif with "wonky" axis for Anya's personality)
- **Body:** Inter (tightened letter-spacing `-0.01em` for confidence)
- **Mono:** JetBrains Mono (timestamps, budget figures, data)

**Rationale:** Typography now carries personality and hierarchy through texture (bold vs. light) rather than just size. The trio feels intentional and specific to travel planning.

---

### 3. **The Listening Orb** — Signature Element

**Before:**
- 🎙️ emoji with generic pulsing animation

**After:**
- Custom SVG component with:
  - Breathing oval animation (organic, not circular)
  - Gradient: Horizon Amber → Sky Periwinkle
  - Pulse rings when active (sound waves aesthetic)
  - Microphone icon overlay
  - Recording indicator dot

**Location:** `apps/web/components/voice/ListeningOrb.tsx`

**Rationale:** This is the ONE thing people will screenshot and say "that's WanderPlan." It's not a button — it's a living presence.

---

### 4. **Anya's Header** — From Generic to Memorable

**Before:**
```tsx
<p className="text-lg font-semibold">✈ Anya - Your AI Travel Assistant</p>
```

**After:**
- Fraunces typography with "wonky" axis (`fontVariationSettings: '"WONK" 1'`)
- Subtle map texture background (grid pattern at 5% opacity)
- Copy: "Your AI travel companion — tap the orb to chat by voice"
- Passport Navy (#1A3A52) background
- Sky Periwinkle (#A8BFDB) for subtitle

**Rationale:** Anya now feels like a character with handwriting, not a bot label. The map texture signals travel without being decorative.

---

### 5. **Stamp Chips** — From Generic Pills to Travel Stamps

**Before:**
- Rounded pills with borders (`border-radius: full`)
- Standard hover effects

**After:**
- Rectangular with dashed borders (stamp aesthetic)
- Slight rotation (-2° to +2°) for tactile feel
- Striped texture overlay (repeating linear gradient)
- JetBrains Mono font (vintage typewriter)
- Selected state: Horizon Amber background

**Location:** `apps/web/components/wizard/StampChip.tsx`

**Rationale:** Chips now feel like artifacts from travel (passport stamps, luggage tags) rather than UI components.

---

### 6. **Polaroid Cards** — Ready for Itinerary Implementation

**Created component** (not yet integrated into timeline):
- Polaroid photo aesthetic with caption area
- Handwritten-style title (Fraunces)
- Monospace timestamps
- Slight rotation for scrapbook feel
- Gradient photo placeholder

**Location:** `apps/web/components/itinerary/PolaroidCard.tsx`

**Next step:** Replace current list items in ItineraryTimeline with PolaroidCard components.

---

### 7. **Layout Colors** — From BI Dashboard to Travel Journal

**Before:**
- `bg-slate-50` on sidebars
- `border-slate-200` dividers
- Stark white background

**After:**
- `bg-[#F7F4EF]` (Map Ivory) for center itinerary area
- `bg-white` on sidebars with inset shadows (`shadow-[inset_-1px_0_0_rgba(26,58,82,0.1)]`)
- 25%-50%-25% asymmetric layout (more breathing room)

**Rationale:** Now feels like a journal with aged paper, not a spreadsheet.

---

## 📊 Updated Components

### Modified Files:
1. **`apps/web/app/globals.css`**
   - New color tokens (Passport Navy, Horizon Amber, Map Ivory, etc.)
   - Typography scale with Fraunces, Inter, JetBrains Mono
   - Tighter letter-spacing for body text

2. **`apps/web/app/layout.tsx`**
   - Added Fraunces, Inter, JetBrains_Mono font imports
   - Updated viewport themeColor to Passport Navy

3. **`apps/web/components/wizard/ConversationalWizard.tsx`**
   - Replaced header with Fraunces typography + map texture
   - Integrated ListeningOrb (replaced emoji button)
   - Updated all button colors (Passport Navy → Earth Clay for CTAs)
   - Replaced QuickReplyChips with StampChips
   - Updated message bubble colors (user messages now Passport Navy)

4. **`apps/web/components/layout/ThreeColumnLayout.tsx`**
   - Changed background from white to Map Ivory
   - Updated sidebar widths (20% → 25%)
   - Added inset shadows (depth without hard borders)

### New Components:
1. **`ListeningOrb.tsx`** — Signature voice interaction element
2. **`StampChip.tsx`** — Vintage travel stamp aesthetic for quick replies
3. **`PolaroidCard.tsx`** — Ready for itinerary timeline integration

---

## 🎯 What Makes This Distinctive?

1. **No default AI patterns:**
   - Not warm cream + serif (AI default #1)
   - Not black + acid green (AI default #2)
   - Not broadsheet hairlines (AI default #3)

2. **Rooted in travel's physical materials:**
   - Passport Navy (leather)
   - Map Ivory (aged paper)
   - Stamp Chips (luggage tags)
   - Polaroid Cards (travel memories)

3. **The Listening Orb:**
   - The ONE signature element people will recognize
   - Breathing animation = organic, alive
   - Not just functional — memorable

---

## 🚀 Next Steps (Not Yet Implemented)

1. **Integrate Polaroid Cards:**
   - Replace current activity list items in `ItineraryTimeline.tsx`
   - Use gradient colors based on activity category
   - Add hover effects (rotate to 0°, lift on hover)

2. **Update Button Components:**
   - Audit remaining blue (#1E40AF) references
   - Replace with Earth Clay (#B85C3F) for primary actions
   - Passport Navy for secondary actions

3. **Weather Widget Styling:**
   - Apply Map Ivory backgrounds
   - Use monospace for temperatures
   - Stamp-style borders

4. **Travel Tips Cards:**
   - Convert to stamp aesthetic
   - Add slight rotation
   - Reddit integration stays, but visual treatment updates

---

## 📐 Design Tokens Reference

```css
/* Primary Colors */
--color-passport-navy:   #1A3A52;  /* Brand, headers */
--color-horizon-amber:   #E88D3A;  /* Accents, progress */
--color-map-ivory:       #F7F4EF;  /* Backgrounds */
--color-ink-charcoal:    #2C3338;  /* Body text */
--color-sky-periwinkle:  #A8BFDB;  /* Subtle accents */
--color-earth-clay:      #B85C3F;  /* CTAs */

/* Typography */
--font-display: var(--font-fraunces);  /* Fraunces */
--font-body:    var(--font-inter);     /* Inter */
--font-mono:    var(--font-jetbrains); /* JetBrains Mono */

/* Spacing */
--radius-card: 4px;   /* Reduced from 8px */
--radius-stamp: 2px;  /* For stamp chips */

/* Shadows */
--shadow-card: 0 2px 8px rgb(26 58 82 / 0.1);
--shadow-polaroid: 0 4px 12px rgb(26 58 82 / 0.15);
```

---

## ✅ Build Status

**Build successful:** ✓  
All TypeScript compilation passed.  
No runtime errors detected.

---

## 🎨 Design Philosophy Applied

This revamp followed the custom design-revamp skill principles:

1. **Ground in subject:** Travel materials (passports, luggage tags, maps)
2. **Avoid AI defaults:** Unique color palette and typography
3. **Signature element:** The Listening Orb
4. **Restraint:** Bold in one place (the Orb), quiet elsewhere
5. **Two-pass workflow:** Brainstorm → critique → build

---

**Last Updated:** June 17, 2026  
**Status:** Phase 1 Complete — Core design system implemented, ready for iterative refinement.
