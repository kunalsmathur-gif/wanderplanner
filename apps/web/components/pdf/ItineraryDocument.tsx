import {
  Document,
  Page,
  Text,
  View,
  Link,
  StyleSheet,
  Font,
} from '@react-pdf/renderer'
import type { ItineraryDay, TripConfig } from '@/types'

Font.register({
  family: 'Helvetica',
  fonts: [],
})

const colors = {
  brand: '#1E40AF',
  dark: '#0F172A',
  mid: '#475569',
  light: '#94A3B8',
  bg: '#F8FAFC',
  border: '#E2E8F0',
  green: '#16A34A',
  amber: '#D97706',
}

const styles = StyleSheet.create({
  page: { fontFamily: 'Helvetica', fontSize: 10, color: colors.dark, paddingHorizontal: 40, paddingVertical: 40 },
  // Header
  header: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20, paddingBottom: 12, borderBottomWidth: 2, borderBottomColor: colors.brand },
  brand: { fontSize: 18, fontFamily: 'Helvetica-Bold', color: colors.brand },
  headerSub: { fontSize: 9, color: colors.mid, marginTop: 2 },
  // Section
  sectionTitle: { fontSize: 11, fontFamily: 'Helvetica-Bold', color: colors.brand, marginTop: 16, marginBottom: 6, paddingBottom: 3, borderBottomWidth: 1, borderBottomColor: colors.border },
  // Day block
  dayHeader: { flexDirection: 'row', alignItems: 'center', marginTop: 12, marginBottom: 4 },
  dayBadge: { backgroundColor: colors.brand, color: '#fff', fontSize: 8, fontFamily: 'Helvetica-Bold', paddingHorizontal: 6, paddingVertical: 2, borderRadius: 4, marginRight: 8 },
  dayTheme: { fontSize: 10, fontFamily: 'Helvetica-Bold', color: colors.dark },
  dayDate: { fontSize: 8, color: colors.mid, marginLeft: 6 },
  // Activity
  activity: { marginLeft: 8, marginBottom: 6, paddingLeft: 8, borderLeftWidth: 2, borderLeftColor: colors.border },
  activityTime: { fontSize: 8, color: colors.mid, marginBottom: 1 },
  activityTitle: { fontSize: 9, fontFamily: 'Helvetica-Bold', color: colors.dark },
  activityDesc: { fontSize: 8, color: colors.mid, marginTop: 1, lineHeight: 1.4 },
  activityLink: { fontSize: 8, color: colors.brand, marginTop: 2 },
  tagRow: { flexDirection: 'row', flexWrap: 'wrap', marginTop: 2, gap: 3 },
  tag: { fontSize: 7, color: colors.mid, backgroundColor: colors.bg, paddingHorizontal: 4, paddingVertical: 1, borderRadius: 3 },
  // Checklist
  checkItem: { flexDirection: 'row', marginBottom: 4, fontSize: 9 },
  checkBox: { width: 12, height: 12, borderWidth: 1, borderColor: colors.border, borderRadius: 2, marginRight: 6, marginTop: 1 },
  // Notes
  noteBox: { backgroundColor: colors.bg, borderWidth: 1, borderColor: colors.border, borderRadius: 4, padding: 10, marginTop: 6 },
  noteText: { fontSize: 9, color: colors.mid, lineHeight: 1.5 },
  footer: { position: 'absolute', bottom: 24, left: 40, right: 40, flexDirection: 'row', justifyContent: 'space-between', fontSize: 8, color: colors.light },
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
}

export function ItineraryDocument({ days, config }: Props) {
  const title = config.destination?.city
    ? `${config.destination.city} Itinerary`
    : 'Your WanderPlan Itinerary'

  const dateRange = config.dates.start && config.dates.end
    ? `${config.dates.start} → ${config.dates.end}`
    : 'Flexible dates'

  return (
    <Document title={title} author="WanderPlan" creator="WanderPlan">
      <Page size="A4" style={styles.page}>
        {/* Header */}
        <View style={styles.header}>
          <View>
            <Text style={styles.brand}>WanderPlan</Text>
            <Text style={styles.headerSub}>AI-Powered Travel Itinerary</Text>
          </View>
          <View>
            <Text style={{ fontSize: 11, fontFamily: 'Helvetica-Bold', textAlign: 'right' }}>{title}</Text>
            <Text style={{ fontSize: 9, color: colors.mid, textAlign: 'right', marginTop: 2 }}>{dateRange}</Text>
          </View>
        </View>

        {/* Day-by-day schedule */}
        <Text style={styles.sectionTitle}>📅 Day-by-Day Schedule</Text>

        {days.map((day) => (
          <View key={day.day_number} wrap={false}>
            <View style={styles.dayHeader}>
              <Text style={styles.dayBadge}>Day {day.day_number}</Text>
              <Text style={styles.dayTheme}>{day.theme}</Text>
              {day.date ? <Text style={styles.dayDate}>· {day.date}</Text> : null}
            </View>

            {day.items.map((item) => (
              <View key={item.id} style={styles.activity}>
                <Text style={styles.activityTime}>{item.time_start} → {item.time_end}</Text>
                <Text style={styles.activityTitle}>{item.title}</Text>
                {item.description ? <Text style={styles.activityDesc}>{item.description}</Text> : null}
                {item.tags.length > 0 && (
                  <View style={styles.tagRow}>
                    {item.tags.map((t) => <Text key={t} style={styles.tag}>{t}</Text>)}
                  </View>
                )}
                {item.booking_url ? (
                  <Link src={item.booking_url} style={styles.activityLink}>
                    Book →
                  </Link>
                ) : null}
              </View>
            ))}

            {day.transit_warnings?.map((w, i) => (
              <View key={i} style={{ ...styles.noteBox, borderColor: colors.amber, marginBottom: 4 }}>
                <Text style={{ ...styles.noteText, color: colors.amber }}>⚠ {w.message}</Text>
              </View>
            ))}
          </View>
        ))}

        {/* Visa & Safety notes */}
        <Text style={styles.sectionTitle}>🛂 Visa & Safety</Text>
        <View style={styles.noteBox}>
          <Text style={styles.noteText}>
            Always verify visa requirements via the official embassy website for your nationality
            before departure. Entry rules can change. Carry physical copies of all travel documents.{'\n\n'}
            Register with your country's travel advisory service for destination-specific safety updates.
            Keep emergency contacts (local police, embassy, travel insurance hotline) saved offline.
          </Text>
        </View>

        {/* Packing checklist */}
        <Text style={styles.sectionTitle}>🧳 Packing Checklist</Text>
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6 }}>
          {PACKING_LIST.map((item) => (
            <View key={item} style={{ ...styles.checkItem, width: '48%' }}>
              <View style={styles.checkBox} />
              <Text>{item}</Text>
            </View>
          ))}
        </View>

        {/* Footer */}
        <View style={styles.footer} fixed>
          <Text>Generated by WanderPlan · wanderplan.app</Text>
          <Text render={({ pageNumber, totalPages }) => `${pageNumber} / ${totalPages}`} />
        </View>
      </Page>
    </Document>
  )
}
