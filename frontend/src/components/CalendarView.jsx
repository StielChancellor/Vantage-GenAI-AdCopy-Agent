import { useState } from 'react';
import { Copy, Download, Check } from 'lucide-react';
import toast from 'react-hot-toast';

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

export default function CalendarView({ calendar, onExportCSV }) {
  const [copied, setCopied] = useState(false);

  const copyToClipboard = () => {
    const header = 'Day\tDate\tTime Range\tChannel\tMessage Preview';
    const rows = calendar.map(
      (e) => `${e.day}\t${e.date}\t${e.time_range}\t${CHANNEL_LABELS[e.channel] || e.channel}\t${e.message_preview}`
    );
    const text = [header, ...rows].join('\n');
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true);
      toast.success('Calendar copied to clipboard');
      setTimeout(() => setCopied(false), 2000);
    });
  };

  if (!calendar || calendar.length === 0) {
    return <div className="empty-state"><p>No calendar entries to display.</p></div>;
  }

  return (
    <div className="calendar-view">
      <div className="calendar-header">
        <h3>Campaign Calendar</h3>
        <div className="calendar-actions">
          <button className="btn btn-sm btn-outline" onClick={copyToClipboard}>
            {copied ? <Check size={14} /> : <Copy size={14} />}
            {copied ? 'Copied!' : 'Copy All'}
          </button>
          {onExportCSV && (
            <button className="btn btn-sm btn-primary" onClick={onExportCSV}>
              <Download size={14} /> Export CSV
            </button>
          )}
        </div>
      </div>

      <div className="calendar-table-wrapper">
        <table className="calendar-table">
          <thead>
            <tr>
              <th>Day</th>
              <th>Date</th>
              <th>Time Range</th>
              <th>Channel</th>
              <th>Message Preview</th>
            </tr>
          </thead>
          <tbody>
            {calendar.map((entry, i) => (
              <tr key={i}>
                <td className="calendar-day">{entry.day}</td>
                <td className="calendar-date">{entry.date}</td>
                <td className="calendar-time">{entry.time_range}</td>
                <td>
                  <span
                    className="channel-badge"
                    style={{ backgroundColor: CHANNEL_COLORS[entry.channel] || '#666' }}
                  >
                    {CHANNEL_LABELS[entry.channel] || entry.channel}
                  </span>
                </td>
                <td className="calendar-preview">{entry.message_preview}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
