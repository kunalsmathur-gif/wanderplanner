import {
  Document,
  Page,
  Text,
  View,
  Link,
  Image,
  StyleSheet,
  Font,
} from '@react-pdf/renderer'
import type { ReactNode } from 'react'
import type { ItineraryDay, TripConfig, ExpenseBreakdown } from '@/types'

Font.register({
  family: 'Helvetica',
  fonts: [],
})

// ── Craft-style palette: each "card" cycles through a soft pastel tone with
// a matching darker accent for headings/dividers — mirrors the colorful
// scrapbook-journal look of the reference itinerary. ──────────────────────
const PALETTE = [
  { bg: '#FCE7F3', accent: '#9D174D' }, // pink
  { bg: '#FFEDD5', accent: '#9A3412' }, // peach
  { bg: '#DCFCE7', accent: '#166534' }, // mint
  { bg: '#DBEAFE', accent: '#1E40AF' }, // sky
  { bg: '#EDE9FE', accent: '#5B21B6' }, // lavender
  { bg: '#FEF9C3', accent: '#854D0E' }, // butter
  { bg: '#CCFBF1', accent: '#115E59' }, // teal
]

const colors = {
  dark: '#0F172A',
  mid: '#475569',
  light: '#94A3B8',
  border: '#E2E8F0',
  green: '#166534',
  amber: '#9A3412',
  page: '#F1F5F9',
}

const styles = StyleSheet.create({
  page: { fontFamily: 'Helvetica', fontSize: 10, color: colors.dark, backgroundColor: colors.page, paddingHorizontal: 28, paddingVertical: 32 },
  // Cover header
  brand: { fontSize: 20, fontFamily: 'Helvetica-Bold', color: colors.dark },
  headerSub: { fontSize: 9, color: colors.mid, marginTop: 2 },
  coverTitle: { fontSize: 16, fontFamily: 'Helvetica-Bold', color: colors.dark, marginTop: 18, marginBottom: 6 },
  coverSubtitle: { fontSize: 10, color: colors.mid, lineHeight: 1.5, marginBottom: 14 },

  // Generic colorful "card" — one per day / section
  card: { borderRadius: 14, padding: 16, marginBottom: 12 },
  cardBreadcrumb: { fontSize: 8, marginBottom: 2 },
  cardTitle: { fontSize: 14, fontFamily: 'Helvetica-Bold', marginBottom: 8 },
  cardDivider: { borderBottomWidth: 1, marginBottom: 8, opacity: 0.4 },

  // Hero photo (Pexels) + attribution shown above a day card's title
  heroImage: { width: '100%', height: 130, borderRadius: 10, marginBottom: 8, objectFit: 'cover' },
  heroAttribution: { fontSize: 6, color: colors.mid, marginBottom: 8, textAlign: 'right' },

  // Bullet item
  bulletRow: { flexDirection: 'row', marginBottom: 6, paddingRight: 4 },
  bulletDot: { width: 10, fontSize: 9, color: colors.dark },
  bulletBody: { flex: 1 },
  bulletLabel: { fontSize: 9, fontFamily: 'Helvetica-Bold', color: colors.dark },
  bulletTime: { fontSize: 8, fontFamily: 'Helvetica-Bold' },
  bulletText: { fontSize: 9, color: colors.dark, lineHeight: 1.45 },

  tagRow: { flexDirection: 'row', flexWrap: 'wrap', marginTop: 2, marginBottom: 4, gap: 4, marginLeft: 10 },
  tag: { fontSize: 7, color: colors.mid, backgroundColor: 'rgba(255,255,255,0.65)', paddingHorizontal: 5, paddingVertical: 2, borderRadius: 8 },

  // Booking link "preview" chip — mimics the Airbnb-style link card in the reference
  linkPreview: { flexDirection: 'row', alignItems: 'center', backgroundColor: 'rgba(255,255,255,0.7)', borderRadius: 8, paddingVertical: 6, paddingHorizontal: 8, marginTop: 2, marginBottom: 6, marginLeft: 10, gap: 6 },
  linkPreviewIcon: { fontSize: 11 },
  linkPreviewText: { fontSize: 8, fontFamily: 'Helvetica-Bold' },

  warnBox: { backgroundColor: 'rgba(255,255,255,0.6)', borderRadius: 8, padding: 8, marginTop: 2, marginLeft: 10 },
  warnText: { fontSize: 8, color: colors.amber },

  // Expense table
  expRow: { flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 4, borderBottomWidth: 1, borderBottomColor: 'rgba(255,255,255,0.7)' },
  expLabel: { fontSize: 9, color: colors.dark },
  expValue: { fontSize: 9, fontFamily: 'Helvetica-Bold', color: colors.dark },
  expTotal: { flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 6, marginTop: 4, borderTopWidth: 2 },
  expTotalLabel: { fontSize: 10, fontFamily: 'Helvetica-Bold' },
  expTotalValue: { fontSize: 10, fontFamily: 'Helvetica-Bold' },
  expToggleRow: { flexDirection: 'row', gap: 8, marginBottom: 8, flexWrap: 'wrap' },
  expBadge: { fontSize: 8, color: colors.dark, backgroundColor: 'rgba(255,255,255,0.7)', paddingHorizontal: 6, paddingVertical: 2, borderRadius: 6 },

  checkItem: { flexDirection: 'row', marginBottom: 5, fontSize: 9 },
  checkBox: { width: 10, height: 10, borderWidth: 1, borderColor: colors.dark, borderRadius: 2, marginRight: 6, marginTop: 1 },

  noteText: { fontSize: 9, color: colors.dark, lineHeight: 1.55 },

  footer: { position: 'absolute', bottom: 16, left: 28, right: 28, flexDirection: 'row', justifyContent: 'space-between', fontSize: 8, color: colors.light },
})

const PACKING_LIST = [
  'Valid passport / ID', 'Travel insurance documents', 'Printed visa (if required)',
  'Local currency / travel card', 'Phone charger & adapters', 'Portable power bank',
  'Medications & prescriptions', 'Sunscreen & toiletries', 'Comfortable walking shoes',
  'Light rain jacket', 'Reusable water bottle', 'Copies of bookings & emergency contacts',
]

interface Props {
  days: ItineraryDay[]
  config: TripConfig
  expenseBreakdown?: ExpenseBreakdown | null
}

function Card({
  tone, breadcrumb, title, photo, children,
}: {
  tone: { bg: string; accent: string }
  breadcrumb?: string
  title: string
  photo?: { url: string; photographer: string; photographer_url: string } | null
  children: ReactNode
}) {
  return (
    <View style={{ ...styles.card, backgroundColor: tone.bg }} wrap={false}>
      {photo?.url ? (
        <>
          <Image src={photo.url} style={styles.heroImage} />
          {photo.photographer ? (
            <Text style={styles.heroAttribution}>Photo by {photo.photographer} on Pexels</Text>
          ) : null}
        </>
      ) : null}
      {breadcrumb ? (
        <Text style={{ ...styles.cardBreadcrumb, color: tone.accent }}>{breadcrumb}</Text>
      ) : null}
      <Text style={{ ...styles.cardTitle, color: tone.accent }}>{title}</Text>
      <View style={{ ...styles.cardDivider, borderBottomColor: tone.accent }} />
      {children}
    </View>
  )
}

export function ItineraryDocument({ days, config, expenseBreakdown }: Props) {
  const title = config.destination?.city
    ? `${config.destination.city} Itinerary`
    : 'Your WanderPlan Itinerary'

  const dateRange = config.dates.start && config.dates.end
    ? `${config.dates.start} - ${config.dates.end}`
    : 'Flexible dates'

  const tripBreadcrumb = `TRIP: ${title}`

  return (
    <Document title={title} author="WanderPlan" creator="WanderPlan">
      <Page size="A4" style={styles.page}>
        {/* Cover */}
        <Text style={styles.brand}>WanderPlan</Text>
        <Text style={styles.headerSub}>AI-Powered Travel Itinerary</Text>
        <Text style={styles.coverTitle}>{title}</Text>
        <Text style={styles.coverSubtitle}>
          {dateRange} · A {days.length}-day trip built around{' '}
          {config.themes.length > 0 ? config.themes.join(', ') : config.purpose || 'your travel style'}.
        </Text>

        {/* Trip Essentials */}
        <Card tone={PALETTE[4]} title="Trip Essentials">
          <View style={styles.bulletRow}>
            <Text style={styles.bulletDot}>•</Text>
            <Text style={styles.bulletText}><Text style={styles.bulletLabel}>Visa: </Text>Check entry requirements for your nationality and keep approvals/ETAs handy.</Text>
          </View>
          <View style={styles.bulletRow}>
            <Text style={styles.bulletDot}>•</Text>
            <Text style={styles.bulletText}><Text style={styles.bulletLabel}>Currency: </Text>Carry a mix of local currency and a travel card; note the destination FX rate.</Text>
          </View>
          <View style={styles.bulletRow}>
            <Text style={styles.bulletDot}>•</Text>
            <Text style={styles.bulletText}><Text style={styles.bulletLabel}>Safety: </Text>Secure travel insurance and save embassy / emergency contacts offline.</Text>
          </View>
        </Card>

        {/* Day-by-day cards */}
        {days.map((day, idx) => {
          const tone = PALETTE[idx % PALETTE.length]
          return (
            <Card
              key={day.day_number}
              tone={tone}
              breadcrumb={tripBreadcrumb}
              title={`Day ${day.day_number}: ${day.theme}${day.date ? `  ·  ${day.date}` : ''}`}
              photo={day.image_url ? {
                url: day.image_url,
                photographer: day.image_photographer ?? '',
                photographer_url: day.image_photographer_url ?? '',
              } : null}
            >
              {day.items.map((item) => (
                <View key={item.id} style={{ marginBottom: 4 }}>
                  <View style={styles.bulletRow}>
                    <Text style={styles.bulletDot}>•</Text>
                    <Text style={styles.bulletText}>
                      <Text style={{ ...styles.bulletTime, color: tone.accent }}>
                        {item.time_start}–{item.time_end} · {item.title}
                      </Text>
                      {item.description ? `: ${item.description}` : ''}
                    </Text>
                  </View>
                  {item.tags.length > 0 && (
                    <View style={styles.tagRow}>
                      {item.tags.map((t) => <Text key={t} style={styles.tag}>{t}</Text>)}
                    </View>
                  )}
                  {item.booking_url ? (
                    <Link src={item.booking_url} style={{ textDecoration: 'none' }}>
                      <View style={styles.linkPreview}>
                        <Text style={styles.linkPreviewIcon}>-</Text>
                        <Text style={{ ...styles.linkPreviewText, color: tone.accent }}>Book / view details</Text>
                      </View>
                    </Link>
                  ) : null}
                </View>
              ))}

              {day.transit_warnings?.map((w, i) => (
                <View key={i} style={styles.warnBox}>
                  <Text style={styles.warnText}>! {w.message}</Text>
                </View>
              ))}
            </Card>
          )
        })}

        {/* Visa & Safety */}
        <Card tone={PALETTE[1]} title="Visa & Safety">
          <Text style={styles.noteText}>
            Always verify visa requirements via the official embassy website for your nationality
            before departure. Entry rules can change. Carry physical copies of all travel documents.{'\n\n'}
            Register with your country&apos;s travel advisory service for destination-specific safety
            updates. Keep emergency contacts (local police, embassy, travel insurance hotline) saved offline.
          </Text>
        </Card>

        {/* Expense Breakup */}
        {expenseBreakdown && expenseBreakdown.total_inr > 0 && (
          <Card tone={PALETTE[2]} title="Cost Breakdown">
            <View style={styles.expToggleRow}>
              <Text style={styles.expBadge}>Group of {expenseBreakdown.num_people}</Text>
              <Text style={styles.expBadge}>Per person ÷ {expenseBreakdown.num_people}</Text>
              {expenseBreakdown.destination_currency_code && (
                <Text style={styles.expBadge}>
                  Total ~{expenseBreakdown.destination_currency_code}{' '}
                  {expenseBreakdown.total_destination_currency.toLocaleString()}
                </Text>
              )}
            </View>

            {[
              { label: 'Flights (round-trip)', val: expenseBreakdown.flights_inr },
              { label: '   Visa & Entry fees', val: expenseBreakdown.visa_inr },
              { label: '   Accommodation', val: expenseBreakdown.accommodation_inr },
              { label: '   Activities & Passes', val: expenseBreakdown.activities_inr },
              { label: '   Food & Dining', val: expenseBreakdown.food_inr },
              { label: '   Local Transport', val: expenseBreakdown.local_transport_inr },
              { label: '   Shopping & Souvenirs', val: expenseBreakdown.shopping_inr },
              { label: '   Emergency Buffer (10%)', val: expenseBreakdown.emergency_buffer_inr },
            ].filter((r) => r.val > 0).map((row) => (
              <View key={row.label} style={styles.expRow}>
                <Text style={styles.expLabel}>{row.label}</Text>
                <View style={{ flexDirection: 'row', gap: 16 }}>
                  <Text style={{ ...styles.expValue, color: colors.mid, minWidth: 70, textAlign: 'right' }}>
                    {`/person  Rs.${Math.round(row.val / expenseBreakdown.num_people).toLocaleString()}`}
                  </Text>
                  <Text style={{ ...styles.expValue, minWidth: 70, textAlign: 'right' }}>
                    {`Rs.${row.val.toLocaleString()}`}
                  </Text>
                </View>
              </View>
            ))}

            <View style={{ ...styles.expTotal, borderTopColor: PALETTE[2].accent }}>
              <Text style={{ ...styles.expTotalLabel, color: PALETTE[2].accent }}>TOTAL ESTIMATE</Text>
              <View style={{ flexDirection: 'row', gap: 16 }}>
                <Text style={{ ...styles.expTotalValue, color: colors.mid, minWidth: 70, textAlign: 'right' }}>
                  {`/person  Rs.${Math.round(expenseBreakdown.total_inr / expenseBreakdown.num_people).toLocaleString()}`}
                </Text>
                <Text style={{ ...styles.expTotalValue, color: PALETTE[2].accent, minWidth: 70, textAlign: 'right' }}>
                  {`Rs.${expenseBreakdown.total_inr.toLocaleString()}`}
                </Text>
              </View>
            </View>

            {config.budget.amount > 0 && (
              <Text style={{
                ...styles.noteText,
                marginTop: 6,
                color: expenseBreakdown.total_inr > config.budget.amount ? colors.amber : colors.green,
              }}>
                {expenseBreakdown.total_inr > config.budget.amount
                  ? `Budget may be tight — estimate exceeds your Rs.${config.budget.amount.toLocaleString()} budget by Rs.${(expenseBreakdown.total_inr - config.budget.amount).toLocaleString()}.`
                  : `Within budget — Rs.${(config.budget.amount - expenseBreakdown.total_inr).toLocaleString()} remaining after estimated expenses.`}
                {'\n'}All figures are approximate and based on average market rates.
              </Text>
            )}
          </Card>
        )}

        {/* Packing checklist */}
        <Card tone={PALETTE[5]} title="Packing Checklist">
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6 }}>
            {PACKING_LIST.map((item) => (
              <View key={item} style={{ ...styles.checkItem, width: '48%' }}>
                <View style={styles.checkBox} />
                <Text>{item}</Text>
              </View>
            ))}
          </View>
        </Card>

        {/* Footer */}
        <View style={styles.footer} fixed>
          <Text>Generated by WanderPlan · wanderplan.app</Text>
          <Text render={({ pageNumber, totalPages }) => `${pageNumber} / ${totalPages}`} />
        </View>
      </Page>
    </Document>
  )
}
