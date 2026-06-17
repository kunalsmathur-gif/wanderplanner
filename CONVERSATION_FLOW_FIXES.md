# Conversation Flow Bug Fixes

## Bug #4: Multi-Destination Flow Issues

### Problem Identified:
**Lines 514-530 in ConversationalWizard.tsx:**

```typescript
if (currentField === 'destination_mode') {
  if (value.startsWith('Yes')) {
    updateConfig({ destination_mode: 'fixed', ... })  // ✓ Correct
  } else if (value.startsWith('Exploring')) {
    updateConfig({ destination_mode: 'country', ... }) // ❌ WRONG!
  } else {
    updateConfig({ destination_mode: 'exploring', ... }) // This becomes "Suggest me!"
  }
}
```

**The mapping is backwards!**
- Chip: "Suggest me! ✨" → Should map to `'exploring'` (AI suggests destinations)
- Chip: "Exploring a country 🗺️" → Should map to `'country'` (User picks country, then cities)

### Current (Broken) Behavior:
1. User clicks "Exploring a country 🗺️"
2. System sets `destination_mode: 'country'` ✓
3. User types "France"
4. System shows French cities ✓
5. User selects "Paris"
6. **BUG**: System moves to dates, NO option to add more cities

### Root Cause:
Line 570-590: After selecting ONE city in 'country' mode, it immediately calls `pushNextField('dates')` with no way to add multiple destinations.

### Fix Required:
1. **Fix the mapping** (lines 520-522):
   ```typescript
   } else if (value.startsWith('Exploring')) {
     updateConfig({ destination_mode: 'country', ... }) 
   }
   ```
   Should be:
   ```typescript
   } else if (value.startsWith('Suggest')) {
     updateConfig({ destination_mode: 'exploring', ... })
   } else if (value.startsWith('Exploring')) {
     updateConfig({ destination_mode: 'country', ... })
   }
   ```

2. **Add multi-city support** (after line 587):
   After selecting a city, ask: "Would you like to add another city? (Yes / No, continue)"
   - If Yes: Stay in 'city-select' stage, show more cities or allow typing
   - If No: Move to dates

---

## Bug #5: Missing Duration Question in Suggest Flow

### Problem Identified:
**Lines 593-617:** When `destination_mode: 'exploring'`, the flow is:
1. User describes preferences ("beaches and relaxation")
2. System recommends cities
3. User selects city
4. **System jumps to dates** (line 615, 638)
5. **MISSING**: Never asks "How many days?"

### Root Cause:
The duration/days question is embedded in the 'dates' field, but in exploring mode, system should ask duration BEFORE recommending destinations (to give better recommendations).

### Expected Flow (Exploring Mode):
1. "Surprise me / Exploring" selected
2. Ask: "How many days do you have?" → Store duration
3. Ask: "What are you looking for?" → Get themes/preferences
4. **Use duration + themes to recommend cities**
5. User selects city
6. Move to start date question

### Fix Required:
1. Add new field: `'duration'` (separate from 'dates')
2. In exploring mode, ask duration BEFORE destination
3. Pass duration to `recommendCities()` API for better suggestions
4. Field order for exploring mode:
   - purpose → origin → destination_mode → **duration** → themes → destination → dates (start date only)

---

## Implementation Plan

### Phase 1: Fix Destination Mode Mapping (Bug #4a)
File: `ConversationalWizard.tsx` lines 514-530

```typescript
if (currentField === 'destination_mode') {
  resetDestinationSelectionState()

  if (value.startsWith('Yes')) {
    // Fixed destination
    updateConfig({ destination_mode: 'fixed', destination_country: null })
    setDestination(null)
  } else if (value.startsWith('Suggest')) {
    // AI suggests based on preferences
    updateConfig({ destination_mode: 'exploring', destination_country: null })
    setDestination(null)
  } else if (value.startsWith('Exploring')) {
    // User picks country, then cities (can be multiple)
    updateConfig({ destination_mode: 'country', destination_country: null })
    setDestination(null)
  }

  pushNextField('destination')
  return
}
```

### Phase 2: Add Multi-City Selection (Bug #4b)
File: `ConversationalWizard.tsx` lines 570-591

After a city is selected in 'country' mode:
```typescript
if (mode === 'country' && destinationSubStage === 'city-select') {
  // ... existing city selection logic ...
  
  // NEW: Ask if they want to add another city
  addMessage(botMessage(
    'Would you like to add another city to your trip?',
    { chips: ['Yes, add another city ➕', 'No, continue to dates ✓'] }
  ))
  setDestinationSubStage('multi-city-confirm')
  return
}

// NEW: Handle multi-city confirmation
if (mode === 'country' && destinationSubStage === 'multi-city-confirm') {
  if (value.startsWith('Yes')) {
    setDestinationSubStage('city-select')
    addMessage(botMessage(
      'Great! Which other city would you like to visit?',
      { chips: suggestedCities.filter(c => c.name !== currentDestination.city).map(recommendedCityChip) }
    ))
    return
  } else {
    pushNextField('dates')
    return
  }
}
```

### Phase 3: Add Duration Field for Exploring Mode (Bug #5)
File: `ConversationalWizard.tsx`

1. Add DURATION_CHIPS after line 56:
```typescript
const DURATION_CHIPS = ['3 days', '5 days', '7 days', '10 days', '14 days', 'Flexible']
```

2. Add 'duration' to WizardField type (in store)

3. Add duration prompt in `promptForField()` (after line 189):
```typescript
case 'duration':
  return botMessage('How many days do you have for this trip?', { chips: DURATION_CHIPS })
```

4. Change field progression for exploring mode (after line 528):
```typescript
} else {
  // Exploring mode: ask duration first
  updateConfig({ destination_mode: 'exploring', destination_country: null })
  setDestination(null)
  pushNextField('duration')  // NEW: Ask duration before destination
  return
}
```

5. Handle duration answer (add after line 640):
```typescript
if (currentField === 'duration') {
  const days = parseInt(value.match(/\d+/)?.[0] ?? '7', 10)
  updateConfig({ dates: { ...config.dates, duration: days } })
  addLabel('duration', `${days} days`)
  pushNextField('destination')
  return
}
```

---

## Testing Checklist

### Test Bug #4 Fix:
- [ ] Select "Exploring a country 🗺️"
- [ ] Enter "France"
- [ ] See French city recommendations
- [ ] Select "Paris"
- [ ] **Should see**: "Would you like to add another city?"
- [ ] Click "Yes, add another city"
- [ ] **Should see**: More city options (Lyon, Nice, etc.)
- [ ] Select "Lyon"
- [ ] **Should see**: "Would you like to add another city?" again
- [ ] Click "No, continue"
- [ ] **Should proceed to**: Dates question

### Test Bug #5 Fix:
- [ ] Select "Suggest me! ✨"
- [ ] **Should see**: "How many days do you have for this trip?"
- [ ] Select "7 days"
- [ ] **Should see**: "What are you looking for?"
- [ ] Enter themes ("beaches, food, culture")
- [ ] **Should see**: City recommendations based on 7 days + themes
- [ ] Select a city
- [ ] **Should proceed to**: Start date question (not duration again)

---

**Status:** Analysis complete, fixes documented, ready to implement.
**Next:** Implement Phase 1 (destination mode mapping fix).
