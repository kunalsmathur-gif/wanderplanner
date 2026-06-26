'use client'

import { useState } from 'react'
import { Plus, Trash2, Plane, BedDouble, Ticket, Bus, ChevronDown, ChevronUp } from 'lucide-react'
import { useBookingStore } from '@/store/bookingStore'
import type { BookingType, Booking } from '@/store/bookingStore'

const TYPE_ICONS: Record<BookingType, React.ReactNode> = {
  Flight:    <Plane size={13} />,
  Hotel:     <BedDouble size={13} />,
  Activity:  <Ticket size={13} />,
  Transport: <Bus size={13} />,
}

const TYPE_COLORS: Record<BookingType, string> = {
  Flight:    'text-sky-600 bg-sky-50 dark:bg-sky-900/30 dark:text-sky-400',
  Hotel:     'text-violet-600 bg-violet-50 dark:bg-violet-900/30 dark:text-violet-400',
  Activity:  'text-emerald-600 bg-emerald-50 dark:bg-emerald-900/30 dark:text-emerald-400',
  Transport: 'text-amber-600 bg-amber-50 dark:bg-amber-900/30 dark:text-amber-400',
}

const EMPTY_FORM = {
  type: 'Flight' as BookingType,
  name: '',
  confirmation: '',
  date: '',
  amount: 0,
  notes: '',
}

export function BookingHub() {
  const { bookings, addBooking, removeBooking } = useBookingStore()
  const [expanded, setExpanded] = useState(true)
  const [adding, setAdding] = useState(false)
  const [form, setForm] = useState({ ...EMPTY_FORM })

  function handleAdd() {
    if (!form.name.trim()) return
    addBooking(form)
    setForm({ ...EMPTY_FORM })
    setAdding(false)
  }

  const totalSpend = bookings.reduce((s, b) => s + (b.amount || 0), 0)

  return (
    <section className="border-t border-[var(--_border)]">
      {/* Collapsible header */}
      <button
        type="button"
        onClick={() => setExpanded((x) => !x)}
        className="flex w-full items-center justify-between px-4 py-3 hover:bg-[var(--_card-elevated)] transition-colors"
        aria-expanded={expanded}
      >
        <div className="flex items-center gap-2">
          <Ticket size={14} className="text-[var(--_primary)]" />
          <span className="text-xs font-bold uppercase tracking-widest text-[var(--_fg)]">
            My Bookings
          </span>
          {bookings.length > 0 && (
            <span className="rounded-full bg-[var(--_primary)]/15 px-1.5 py-0.5 text-[10px] font-semibold text-[var(--_primary)]">
              {bookings.length}
            </span>
          )}
        </div>
        {expanded ? <ChevronUp size={14} className="text-[var(--_muted-fg)]" /> : <ChevronDown size={14} className="text-[var(--_muted-fg)]" />}
      </button>

      {expanded && (
        <div className="px-4 pb-4">
          {/* Summary row */}
          {bookings.length > 0 && totalSpend > 0 && (
            <p className="mb-2 text-[10px] text-[var(--_muted-fg)]">
              Total tracked: <span className="font-semibold text-[var(--_fg)]">₹{totalSpend.toLocaleString('en-IN')}</span>
            </p>
          )}

          {/* Booking list */}
          <div className="space-y-2">
            {bookings.length === 0 && !adding && (
              <p className="py-2 text-center text-xs text-[var(--_muted-fg)]">
                No bookings yet — add flights, hotels, or activities.
              </p>
            )}
            {bookings.map((b) => (
              <BookingRow key={b.id} booking={b} onDelete={() => removeBooking(b.id)} />
            ))}
          </div>

          {/* Add form */}
          {adding ? (
            <div className="mt-3 space-y-2 rounded-xl border border-[var(--_border)] bg-[var(--_card-elevated)] p-3">
              {/* Type selector */}
              <div className="flex gap-1">
                {(['Flight', 'Hotel', 'Activity', 'Transport'] as BookingType[]).map((t) => (
                  <button
                    key={t}
                    type="button"
                    onClick={() => setForm((f) => ({ ...f, type: t }))}
                    className={[
                      'flex items-center gap-1 rounded-lg px-2 py-1 text-[10px] font-semibold transition-all',
                      form.type === t
                        ? 'bg-[var(--_primary)] text-white'
                        : 'bg-[var(--_card)] text-[var(--_muted-fg)] border border-[var(--_border)]',
                    ].join(' ')}
                  >
                    {TYPE_ICONS[t]} {t}
                  </button>
                ))}
              </div>

              <input
                className="input w-full rounded-lg border border-[var(--_border)] bg-[var(--_bg)] px-3 py-1.5 text-xs text-[var(--_fg)] placeholder:text-[var(--_muted-fg)] focus:border-[var(--_primary)] focus:outline-none"
                placeholder="Name (e.g. IndiGo 6E-123, Taj Hotel)"
                value={form.name}
                onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
              />
              <div className="flex gap-2">
                <input
                  className="input flex-1 rounded-lg border border-[var(--_border)] bg-[var(--_bg)] px-3 py-1.5 text-xs text-[var(--_fg)] placeholder:text-[var(--_muted-fg)] focus:border-[var(--_primary)] focus:outline-none"
                  placeholder="Confirmation #"
                  value={form.confirmation}
                  onChange={(e) => setForm((f) => ({ ...f, confirmation: e.target.value }))}
                />
                <input
                  type="date"
                  className="input flex-1 rounded-lg border border-[var(--_border)] bg-[var(--_bg)] px-3 py-1.5 text-xs text-[var(--_fg)] focus:border-[var(--_primary)] focus:outline-none"
                  value={form.date}
                  onChange={(e) => setForm((f) => ({ ...f, date: e.target.value }))}
                />
              </div>
              <input
                type="number"
                className="input w-full rounded-lg border border-[var(--_border)] bg-[var(--_bg)] px-3 py-1.5 text-xs text-[var(--_fg)] placeholder:text-[var(--_muted-fg)] focus:border-[var(--_primary)] focus:outline-none"
                placeholder="Amount (₹, optional)"
                value={form.amount || ''}
                onChange={(e) => setForm((f) => ({ ...f, amount: Number(e.target.value) }))}
              />
              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={handleAdd}
                  disabled={!form.name.trim()}
                  className="flex-1 rounded-lg bg-[var(--_primary)] py-1.5 text-xs font-semibold text-white transition-opacity hover:opacity-90 disabled:opacity-50"
                >
                  Save
                </button>
                <button
                  type="button"
                  onClick={() => { setAdding(false); setForm({ ...EMPTY_FORM }) }}
                  className="flex-1 rounded-lg border border-[var(--_border)] py-1.5 text-xs font-semibold text-[var(--_fg)] hover:bg-[var(--_card)]"
                >
                  Cancel
                </button>
              </div>
            </div>
          ) : (
            <button
              type="button"
              onClick={() => setAdding(true)}
              className="mt-2 flex w-full items-center justify-center gap-1.5 rounded-xl border border-dashed border-[var(--_border)] py-2 text-xs font-medium text-[var(--_muted-fg)] transition-colors hover:border-[var(--_primary)] hover:text-[var(--_primary)]"
            >
              <Plus size={13} /> Add booking
            </button>
          )}
        </div>
      )}
    </section>
  )
}

function BookingRow({ booking: b, onDelete }: { booking: Booking; onDelete: () => void }) {
  return (
    <div className="group flex items-start gap-2 rounded-xl border border-[var(--_border)] bg-[var(--_card)] p-2.5">
      <span className={['mt-0.5 flex shrink-0 items-center gap-0.5 rounded-md px-1.5 py-0.5 text-[10px] font-semibold', TYPE_COLORS[b.type]].join(' ')}>
        {TYPE_ICONS[b.type]}
      </span>
      <div className="min-w-0 flex-1">
        <p className="truncate text-xs font-semibold text-[var(--_fg)]">{b.name}</p>
        <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5 mt-0.5">
          {b.confirmation && (
            <span className="text-[10px] text-[var(--_muted-fg)]">#{b.confirmation}</span>
          )}
          {b.date && (
            <span className="text-[10px] text-[var(--_muted-fg)]">{b.date}</span>
          )}
          {b.amount > 0 && (
            <span className="text-[10px] font-semibold text-[var(--_primary)]">
              ₹{b.amount.toLocaleString('en-IN')}
            </span>
          )}
        </div>
      </div>
      <button
        type="button"
        onClick={onDelete}
        className="shrink-0 text-[var(--_muted-fg)] opacity-0 transition-opacity group-hover:opacity-100 hover:text-red-500"
        aria-label="Remove booking"
      >
        <Trash2 size={13} />
      </button>
    </div>
  )
}
