# Refinement-Fidelity Eval Report

Mode: **live** · positive cases: 16 · honesty (negative) cases: 4

## Headline

- **Refinement fidelity score: 0.99** (0.4·pin-recall + 0.4·itinerary-inclusion + 0.2·stability)
- Verified-POI pin recall: 0.98
- Hard-constraint compliance (pinned & appears exactly once): 1.00
- Pin stability across an unrelated re-refinement: 1.00
- Pin precision (on-interest): 0.95
- Honesty on impossible asks: 100%

## Per-case results

| Case | Destination | Interest | Pin recall | Inclusion | Stability | Fidelity |
|---|---|---|---|---|---|---|
| RF-001 | London | Harry Potter | 0.67 | 1.00 | 1.00 | 0.87 |
| RF-002 | Edinburgh | Harry Potter | 1.00 | 1.00 | 1.00 | 1.00 |
| RF-003 | Tokyo | anime | 1.00 | 1.00 | 1.00 | 1.00 |
| RF-004 | Kyoto | zen gardens | 1.00 | 1.00 | 1.00 | 1.00 |
| RF-005 | Paris | Impressionist art | 1.00 | 1.00 | 1.00 | 1.00 |
| RF-006 | Rome | ancient Roman history | 1.00 | 1.00 | 1.00 | 1.00 |
| RF-007 | Barcelona | Gaudi architecture | 1.00 | 1.00 | 1.00 | 1.00 |
| RF-008 | Liverpool | The Beatles | 1.00 | 1.00 | 1.00 | 1.00 |
| RF-009 | Los Angeles | movie studios | 1.00 | 1.00 | 1.00 | 1.00 |
| RF-010 | Singapore | hawker food | 1.00 | 1.00 | 1.00 | 1.00 |
| RF-011 | Delhi | Mughal history | 1.00 | 1.00 | 1.00 | 1.00 |
| RF-012 | Mumbai | Bollywood | 1.00 | 1.00 | 1.00 | 1.00 |
| RF-013 | Jaipur | royal Rajput heritage | 1.00 | 1.00 | 1.00 | 1.00 |
| RF-014 | Goa | Portuguese heritage | 1.00 | 1.00 | 1.00 | 1.00 |
| RF-015 | Amritsar | Sikh heritage | 1.00 | 1.00 | 1.00 | 1.00 |
| RF-016 | Bengaluru | historic palaces and gardens | 1.00 | 1.00 | 1.00 | 1.00 |

### Honesty cases (nothing real to pin — did we invent?)

| Case | Destination | Interest | Honest |
|---|---|---|---|
| RF-017 | Goa | Harry Potter | ✅ |
| RF-018 | Jaipur | Formula 1 | ✅ |
| RF-019 | Amritsar | Studio Ghibli | ✅ |
| RF-020 | Kyoto | scuba diving | ✅ |
