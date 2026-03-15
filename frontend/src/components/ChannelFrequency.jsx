const DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
const INTERVALS = [1, 2, 3, 4];
const DURATIONS = [2, 3, 4, 6, 8, 10, 12];

const CHANNEL_COLORS = {
  whatsapp: '#25d366',
  email: '#4a90d9',
  app_push: '#9b59b6',
};

const CHANNEL_LABELS = {
  whatsapp: 'WhatsApp',
  email: 'Email',
  app_push: 'App Push',
};

export default function ChannelFrequency({ channels, value, onChange }) {
  const getChannelConfig = (ch) => {
    return value[ch] || { days: ['Mon'], every_n_weeks: 1, duration_weeks: 4, custom_pattern: '' };
  };

  const updateChannel = (ch, fields) => {
    onChange({
      ...value,
      [ch]: { ...getChannelConfig(ch), ...fields },
    });
  };

  const toggleDay = (ch, day) => {
    const config = getChannelConfig(ch);
    const days = config.days || [];
    const updated = days.includes(day)
      ? days.filter((d) => d !== day)
      : [...days, day];
    // Keep at least one day
    if (updated.length === 0) return;
    updateChannel(ch, { days: updated });
  };

  if (!channels || channels.length === 0) {
    return <p style={{ color: 'var(--text-muted)', fontSize: '0.85rem' }}>Select channels first.</p>;
  }

  return (
    <div className="channel-frequency">
      {channels.map((ch) => {
        const config = getChannelConfig(ch);
        const color = CHANNEL_COLORS[ch] || 'var(--gold)';

        return (
          <div key={ch} className="channel-freq-card" style={{ borderLeft: `3px solid ${color}` }}>
            <h4 style={{ color }}>{CHANNEL_LABELS[ch] || ch}</h4>

            {/* Day Picker */}
            <div className="form-group">
              <label>Send Days</label>
              <div className="day-picker">
                {DAYS.map((day) => (
                  <button
                    key={day}
                    type="button"
                    className={`day-btn ${(config.days || []).includes(day) ? 'active' : ''}`}
                    onClick={() => toggleDay(ch, day)}
                    style={{ '--accent': color }}
                  >
                    {day}
                  </button>
                ))}
              </div>
            </div>

            {/* Interval */}
            <div className="form-row" style={{ gap: '1rem' }}>
              <div className="form-group" style={{ flex: 1 }}>
                <label>Every N Weeks</label>
                <select
                  value={config.every_n_weeks || 1}
                  onChange={(e) => updateChannel(ch, { every_n_weeks: parseInt(e.target.value) })}
                >
                  {INTERVALS.map((n) => (
                    <option key={n} value={n}>Every {n} week{n > 1 ? 's' : ''}</option>
                  ))}
                </select>
              </div>

              <div className="form-group" style={{ flex: 1 }}>
                <label>Duration</label>
                <select
                  value={config.duration_weeks || 4}
                  onChange={(e) => updateChannel(ch, { duration_weeks: parseInt(e.target.value) })}
                >
                  {DURATIONS.map((n) => (
                    <option key={n} value={n}>{n} weeks</option>
                  ))}
                </select>
              </div>
            </div>

            {/* Custom Override */}
            <div className="form-group">
              <label>Custom Override <span style={{ fontSize: '0.7rem', fontWeight: 400 }}>(optional — overrides above settings)</span></label>
              <input
                value={config.custom_pattern || ''}
                onChange={(e) => updateChannel(ch, { custom_pattern: e.target.value })}
                placeholder="e.g., Send only on Diwali week, skip first week of month"
              />
            </div>
          </div>
        );
      })}
    </div>
  );
}
