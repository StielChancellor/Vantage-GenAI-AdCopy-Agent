import { useState } from 'react';
import { Copy, Check } from 'lucide-react';
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

export default function CampaignTableView({ calendar }) {
  const [copied, setCopied] = useState(false);

  const copyAsCSV = () => {
    const header = 'Date\tDay\tTime\tChannel\tHeadline\tBody\tSubject\tCTA';
    const rows = calendar.map((e) =>
      `${e.date}\t${e.day}\t${e.time_range}\t${CHANNEL_LABELS[e.channel] || e.channel}\t${e.headline || ''}\t${(e.body || '').replace(/\n/g, ' ')}\t${e.subject || ''}\t${e.cta || ''}`
    );
    navigator.clipboard.writeText([header, ...rows].join('\n')).then(() => {
      setCopied(true);
      toast.success('Table copied to clipboard');
      setTimeout(() => setCopied(false), 2000);
    });
  };

  if (!calendar || calendar.length === 0) {
    return <div className="empty-state"><p>No calendar entries.</p></div>;
  }

  return (
    <div className="campaign-table-view">
      <div className="campaign-table-actions">
        <button className="btn btn-sm btn-outline" onClick={copyAsCSV}>
          {copied ? <Check size={14} /> : <Copy size={14} />}
          {copied ? 'Copied!' : 'Copy Table'}
        </button>
      </div>

      <div className="campaign-table-wrapper">
        <table className="campaign-table">
          <thead>
            <tr>
              <th>Date</th>
              <th>Day</th>
              <th>Time</th>
              <th>Channel</th>
              <th>Headline</th>
              <th>Body</th>
              <th>Subject</th>
              <th>CTA</th>
            </tr>
          </thead>
          <tbody>
            {calendar.map((entry, i) => (
              <tr key={i}>
                <td className="table-date">{entry.date}</td>
                <td>{entry.day}</td>
                <td className="table-time">{entry.time_range}</td>
                <td>
                  <span
                    className="channel-badge"
                    style={{ backgroundColor: CHANNEL_COLORS[entry.channel] || '#666' }}
                  >
                    {CHANNEL_LABELS[entry.channel] || entry.channel}
                  </span>
                </td>
                <td className="table-headline">{entry.headline || '-'}</td>
                <td className="table-body">{entry.body ? (entry.body.length > 80 ? entry.body.slice(0, 80) + '...' : entry.body) : '-'}</td>
                <td className="table-subject">{entry.subject || '-'}</td>
                <td className="table-cta">{entry.cta || '-'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
