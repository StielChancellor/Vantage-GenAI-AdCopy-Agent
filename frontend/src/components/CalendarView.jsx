import { useState } from 'react';
import { Download, LayoutGrid, Table } from 'lucide-react';
import CampaignCalendarGrid from './CampaignCalendarGrid';
import CampaignTableView from './CampaignTableView';

export default function CalendarView({ calendar, onExportCSV }) {
  const [viewMode, setViewMode] = useState('grid'); // 'grid' | 'table'

  if (!calendar || calendar.length === 0) {
    return <div className="empty-state"><p>No calendar entries to display.</p></div>;
  }

  return (
    <div className="calendar-view">
      <div className="calendar-header">
        <h3>Campaign Calendar</h3>
        <div className="calendar-actions">
          <div className="view-toggle">
            <button className={`view-toggle-btn ${viewMode === 'grid' ? 'active' : ''}`} onClick={() => setViewMode('grid')}>
              <LayoutGrid size={14} /> Grid
            </button>
            <button className={`view-toggle-btn ${viewMode === 'table' ? 'active' : ''}`} onClick={() => setViewMode('table')}>
              <Table size={14} /> Table
            </button>
          </div>
          {onExportCSV && (
            <button className="btn btn-sm btn-primary" onClick={onExportCSV}>
              <Download size={14} /> Export CSV
            </button>
          )}
        </div>
      </div>

      {viewMode === 'grid' ? (
        <CampaignCalendarGrid calendar={calendar} />
      ) : (
        <CampaignTableView calendar={calendar} />
      )}
    </div>
  );
}
