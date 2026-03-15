import { useState, useMemo } from 'react';
import { ChevronLeft, ChevronRight, Calendar, List } from 'lucide-react';

const MONTH_NAMES = ['January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December'];
const DAY_HEADERS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];

export default function EventCalendar({ events, selectedEvents, onToggleEvent }) {
  const [viewMode, setViewMode] = useState('timeline'); // 'grid' | 'timeline'

  // Determine initial month from events
  const firstEvent = events?.[0];
  const firstDate = firstEvent?.date ? new Date(firstEvent.date) : new Date();
  const [currentMonth, setCurrentMonth] = useState(firstDate.getMonth());
  const [currentYear, setCurrentYear] = useState(firstDate.getFullYear());

  // Group events by date
  const eventsByDate = useMemo(() => {
    const map = {};
    (events || []).forEach((e) => {
      const dateKey = e.date?.slice(0, 10);
      if (dateKey) {
        if (!map[dateKey]) map[dateKey] = [];
        map[dateKey].push(e);
      }
    });
    return map;
  }, [events]);

  const isSelected = (event) =>
    selectedEvents?.find((e) => e.title === event.title && e.date === event.date);

  // Calendar grid
  const calendarGrid = useMemo(() => {
    const firstDay = new Date(currentYear, currentMonth, 1);
    const lastDay = new Date(currentYear, currentMonth + 1, 0);
    let startDow = firstDay.getDay() - 1;
    if (startDow < 0) startDow = 6;

    const weeks = [];
    let week = new Array(startDow).fill(null);
    for (let d = 1; d <= lastDay.getDate(); d++) {
      const dateStr = `${currentYear}-${String(currentMonth + 1).padStart(2, '0')}-${String(d).padStart(2, '0')}`;
      week.push({ day: d, date: dateStr, events: eventsByDate[dateStr] || [] });
      if (week.length === 7) { weeks.push(week); week = []; }
    }
    if (week.length > 0) {
      while (week.length < 7) week.push(null);
      weeks.push(week);
    }
    return weeks;
  }, [currentMonth, currentYear, eventsByDate]);

  const prevMonth = () => {
    if (currentMonth === 0) { setCurrentMonth(11); setCurrentYear(currentYear - 1); }
    else setCurrentMonth(currentMonth - 1);
  };

  const nextMonth = () => {
    if (currentMonth === 11) { setCurrentMonth(0); setCurrentYear(currentYear + 1); }
    else setCurrentMonth(currentMonth + 1);
  };

  if (!events || events.length === 0) return null;

  return (
    <div className="event-calendar">
      {/* View Toggle */}
      <div className="view-toggle" style={{ marginBottom: '0.75rem' }}>
        <button className={`view-toggle-btn ${viewMode === 'timeline' ? 'active' : ''}`} onClick={() => setViewMode('timeline')}>
          <List size={14} /> Timeline
        </button>
        <button className={`view-toggle-btn ${viewMode === 'grid' ? 'active' : ''}`} onClick={() => setViewMode('grid')}>
          <Calendar size={14} /> Calendar
        </button>
      </div>

      {/* Timeline View */}
      {viewMode === 'timeline' && (
        <div className="event-results">
          {events.map((event, i) => {
            const selected = isSelected(event);
            return (
              <div key={i} className={`event-card ${selected ? 'selected' : ''}`} onClick={() => onToggleEvent(event)}>
                <div className="event-card-header">
                  <input type="checkbox" checked={!!selected} readOnly />
                  <strong>{event.title}</strong>
                  <span className="event-date">{event.date}</span>
                </div>
                <p className="event-desc">{event.description}</p>
                <div className="event-meta">
                  <span className="event-market">{event.market}</span>
                  <span className="event-source">{event.source}</span>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Calendar Grid View */}
      {viewMode === 'grid' && (
        <>
          <div className="calendar-grid-header">
            <button className="btn-icon" onClick={prevMonth}><ChevronLeft size={18} /></button>
            <h4>{MONTH_NAMES[currentMonth]} {currentYear}</h4>
            <button className="btn-icon" onClick={nextMonth}><ChevronRight size={18} /></button>
          </div>

          <div className="calendar-grid event-grid">
            <div className="calendar-grid-row calendar-grid-day-headers">
              {DAY_HEADERS.map((d) => (
                <div key={d} className="calendar-grid-day-header">{d}</div>
              ))}
            </div>

            {calendarGrid.map((week, wi) => (
              <div key={wi} className="calendar-grid-row">
                {week.map((cell, ci) => (
                  <div key={ci} className={`calendar-grid-cell ${cell ? '' : 'empty'}`}>
                    {cell && (
                      <>
                        <span className="calendar-grid-date">{cell.day}</span>
                        <div className="calendar-grid-entries">
                          {cell.events.map((e, ei) => (
                            <div
                              key={ei}
                              className={`calendar-grid-entry event-entry ${isSelected(e) ? 'selected' : ''}`}
                              onClick={() => onToggleEvent(e)}
                              title={e.title}
                            >
                              {e.title.slice(0, 15)}{e.title.length > 15 ? '...' : ''}
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
        </>
      )}
    </div>
  );
}
