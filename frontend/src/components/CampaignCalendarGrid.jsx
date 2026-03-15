import { useState, useMemo } from 'react';
import { ChevronLeft, ChevronRight } from 'lucide-react';

const CHANNEL_COLORS = {
  whatsapp: '#25d366',
  email: '#4a90d9',
  app_push: '#9b59b6',
};

const CHANNEL_LABELS = {
  whatsapp: 'WA',
  email: 'EM',
  app_push: 'AP',
};

const MONTH_NAMES = ['January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December'];

const DAY_HEADERS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];

export default function CampaignCalendarGrid({ calendar }) {
  // Determine initial month from first calendar entry
  const firstDate = calendar?.[0]?.date ? new Date(calendar[0].date) : new Date();
  const [currentMonth, setCurrentMonth] = useState(firstDate.getMonth());
  const [currentYear, setCurrentYear] = useState(firstDate.getFullYear());

  // Group entries by date
  const entriesByDate = useMemo(() => {
    const map = {};
    (calendar || []).forEach((entry) => {
      if (!map[entry.date]) map[entry.date] = [];
      map[entry.date].push(entry);
    });
    return map;
  }, [calendar]);

  // Build calendar grid for current month
  const calendarGrid = useMemo(() => {
    const firstDay = new Date(currentYear, currentMonth, 1);
    const lastDay = new Date(currentYear, currentMonth + 1, 0);

    // Monday-based: getDay() returns 0=Sun, we want 0=Mon
    let startDow = firstDay.getDay() - 1;
    if (startDow < 0) startDow = 6;

    const weeks = [];
    let week = new Array(startDow).fill(null);

    for (let d = 1; d <= lastDay.getDate(); d++) {
      const dateStr = `${currentYear}-${String(currentMonth + 1).padStart(2, '0')}-${String(d).padStart(2, '0')}`;
      week.push({ day: d, date: dateStr, entries: entriesByDate[dateStr] || [] });
      if (week.length === 7) {
        weeks.push(week);
        week = [];
      }
    }
    if (week.length > 0) {
      while (week.length < 7) week.push(null);
      weeks.push(week);
    }

    return weeks;
  }, [currentMonth, currentYear, entriesByDate]);

  const prevMonth = () => {
    if (currentMonth === 0) { setCurrentMonth(11); setCurrentYear(currentYear - 1); }
    else setCurrentMonth(currentMonth - 1);
  };

  const nextMonth = () => {
    if (currentMonth === 11) { setCurrentMonth(0); setCurrentYear(currentYear + 1); }
    else setCurrentMonth(currentMonth + 1);
  };

  const today = new Date().toISOString().slice(0, 10);

  return (
    <div className="campaign-calendar-grid">
      <div className="calendar-grid-header">
        <button className="btn-icon" onClick={prevMonth}><ChevronLeft size={18} /></button>
        <h4>{MONTH_NAMES[currentMonth]} {currentYear}</h4>
        <button className="btn-icon" onClick={nextMonth}><ChevronRight size={18} /></button>
      </div>

      <div className="calendar-grid">
        <div className="calendar-grid-row calendar-grid-day-headers">
          {DAY_HEADERS.map((d) => (
            <div key={d} className="calendar-grid-day-header">{d}</div>
          ))}
        </div>

        {calendarGrid.map((week, wi) => (
          <div key={wi} className="calendar-grid-row">
            {week.map((cell, ci) => (
              <div
                key={ci}
                className={`calendar-grid-cell ${cell ? '' : 'empty'} ${cell?.date === today ? 'today' : ''}`}
              >
                {cell && (
                  <>
                    <span className="calendar-grid-date">{cell.day}</span>
                    <div className="calendar-grid-entries">
                      {cell.entries.map((e, ei) => (
                        <div
                          key={ei}
                          className="calendar-grid-entry"
                          style={{ backgroundColor: CHANNEL_COLORS[e.channel] || '#666' }}
                          title={`${e.channel}: ${e.message_preview}`}
                        >
                          <span className="entry-channel">{CHANNEL_LABELS[e.channel] || e.channel}</span>
                          <span className="entry-time">{e.time_range?.split(' - ')[0]}</span>
                        </div>
                      ))}
                    </div>
                  </>
                )}
              </div>
            ))}
          </div>
        ))}
      </div>

      {/* Legend */}
      <div className="calendar-grid-legend">
        {Object.entries(CHANNEL_COLORS).map(([ch, color]) => (
          <span key={ch} className="legend-item">
            <span className="legend-dot" style={{ backgroundColor: color }} />
            {ch === 'whatsapp' ? 'WhatsApp' : ch === 'email' ? 'Email' : 'App Push'}
          </span>
        ))}
      </div>
    </div>
  );
}
