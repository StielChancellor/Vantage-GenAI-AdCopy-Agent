import { useState, useEffect, useRef } from 'react';
import {
  startTraining, getTrainingProgress, answerTraining, getTrainingSessions,
  deleteTrainingSession, exportTrainingSessions, uploadCreativePack,
} from '../services/api';
import toast from 'react-hot-toast';
import {
  Upload, CheckCircle, XCircle, MessageSquare, Trash2,
  Download, FileText, Type, FileSpreadsheet, Star, Image as ImageIcon,
} from 'lucide-react';
import IntelligentPropertyPicker from './IntelligentPropertyPicker';

const SECTION_TYPES = [
  { value: 'google_ads_export', label: 'Google Ads Export (Editor CSV)', icon: '🔍' },
  { value: 'moengage_push', label: 'MoEngage Push Export', icon: '🔔' },
  { value: 'ad_performance', label: 'Ad Performance (generic)', icon: '📊' },
  { value: 'brand_usp', label: 'Brand & USP', icon: '🏨' },
  { value: 'crm_performance', label: 'CRM Performance', icon: '📱' },
  { value: 'creative_assets', label: 'Creative Assets (Zip + Manifest)', icon: '🖼️' },
];

const TRAINING_MODES = [
  { value: 'csv_only', label: 'CSV Upload', icon: FileSpreadsheet, desc: 'Upload performance data CSV' },
  { value: 'text_only', label: 'Text Input', icon: Type, desc: 'Enter strategy notes & context' },
  { value: 'csv_and_text', label: 'CSV + Text', icon: FileText, desc: 'Combine data with strategy' },
];

export default function TrainingWizard() {
  // Training config
  const [sectionType, setSectionType] = useState('ad_performance');
  const [trainingMode, setTrainingMode] = useState('csv_only');
  const [textInput, setTextInput] = useState('');
  const [remarks, setRemarks] = useState('');
  const [uploading, setUploading] = useState(false);

  // CSV column handling
  const [csvFile, setCsvFile] = useState(null);
  const [csvColumns, setCsvColumns] = useState([]);
  const [kpiColumns, setKpiColumns] = useState([]);
  const [heroColumns, setHeroColumns] = useState([]);
  const fileInputRef = useRef(null);

  // Creative-asset (zip) upload state
  const [zipFile, setZipFile] = useState(null);
  const [creativeBrandSel, setCreativeBrandSel] = useState(null);
  const zipInputRef = useRef(null);
  const isCreativeAssets = sectionType === 'creative_assets';

  // Training session state
  const [session, setSession] = useState(null);
  const [answers, setAnswers] = useState({});
  const [submitting, setSubmitting] = useState(false);
  const [showSaveMode, setShowSaveMode] = useState(false);

  // Live progress (v2.1 ingestion runs)
  const [progress, setProgress] = useState(null); // {percent, phase, message, status}
  const progressPollRef = useRef(null);

  // History
  const [sessions, setSessions] = useState([]);

  useEffect(() => {
    loadSessions();
  }, []);

  const loadSessions = async () => {
    try {
      const res = await getTrainingSessions();
      setSessions(res.data || []);
    } catch {}
  };

  // Parse CSV headers client-side
  const handleFileSelect = (e) => {
    const file = e.target.files[0];
    if (!file) return;
    if (!file.name.endsWith('.csv')) {
      toast.error('Only CSV files are supported');
      return;
    }
    setCsvFile(file);

    // Read first line to extract column names
    const reader = new FileReader();
    reader.onload = (evt) => {
      const text = evt.target.result;
      const firstLine = text.split('\n')[0];
      const cols = firstLine.split(',').map((c) => c.trim().replace(/^"|"$/g, ''));
      setCsvColumns(cols);
      setKpiColumns([]);
      setHeroColumns([]);
    };
    reader.readAsText(file.slice(0, 4096)); // Read just the first 4KB
  };

  const toggleKpi = (col) => {
    setKpiColumns((prev) =>
      prev.includes(col) ? prev.filter((c) => c !== col) : [...prev, col]
    );
  };

  const addHeroColumn = () => {
    setHeroColumns((prev) => [...prev, { column: '', description: '' }]);
  };

  const updateHeroColumn = (idx, field, value) => {
    setHeroColumns((prev) => {
      const updated = [...prev];
      updated[idx] = { ...updated[idx], [field]: value };
      return updated;
    });
  };

  const removeHeroColumn = (idx) => {
    setHeroColumns((prev) => prev.filter((_, i) => i !== idx));
  };

  const stopProgressPolling = () => {
    if (progressPollRef.current) {
      clearInterval(progressPollRef.current);
      progressPollRef.current = null;
    }
  };

  const startProgressPolling = (runId) => {
    stopProgressPolling();
    progressPollRef.current = setInterval(async () => {
      try {
        const r = await getTrainingProgress(runId);
        if (r?.data) {
          setProgress(r.data);
          if (r.data.status === 'completed' || r.data.status === 'failed') {
            stopProgressPolling();
          }
        }
      } catch {
        // Silent — keep polling; transient errors are fine
      }
    }, 800);
  };

  const handleUpload = async () => {
    // Creative-asset (zip) path — different inputs from the CSV/text flow.
    if (isCreativeAssets) {
      if (!zipFile) {
        toast.error('Please select a .zip file');
        return;
      }
      const brandId = (creativeBrandSel?.brand_ids || [])[0] || creativeBrandSel?.brand_id || '';
      if (!brandId) {
        toast.error('Pick a single brand — creative assets are scoped per brand.');
        return;
      }
      const runId = (typeof crypto !== 'undefined' && crypto.randomUUID)
        ? crypto.randomUUID()
        : `${Date.now()}-${Math.random().toString(36).slice(2)}`;
      setUploading(true);
      setProgress({ percent: 0, phase: 'starting', message: 'Uploading zip…', status: 'running' });
      startProgressPolling(runId);
      try {
        const res = await uploadCreativePack(zipFile, brandId, runId);
        stopProgressPolling();
        setProgress({ percent: 100, phase: 'completed', message: 'Captioning complete', status: 'completed' });
        const data = res.data || {};
        toast.success(
          `Ingested ${data.written ?? 0} / ${data.rows_in_manifest ?? 0} assets · cost ₹${(data.cost_inr ?? 0).toFixed(4)}`,
          { duration: 8000 }
        );
        setZipFile(null);
        if (zipInputRef.current) zipInputRef.current.value = '';
        loadSessions();
      } catch (err) {
        stopProgressPolling();
        setProgress({ percent: 0, phase: 'failed', message: err.response?.data?.detail || 'Upload failed', status: 'failed' });
        toast.error(err.response?.data?.detail || 'Upload failed');
      } finally {
        setUploading(false);
      }
      return;
    }

    if (trainingMode !== 'text_only' && !csvFile) {
      toast.error('Please select a CSV file');
      return;
    }
    if (trainingMode !== 'csv_only' && !textInput.trim()) {
      toast.error('Please enter text input');
      return;
    }

    // Client-supplied run_id lets us start polling progress before the
    // synchronous /upload response arrives.
    const runId = (typeof crypto !== 'undefined' && crypto.randomUUID)
      ? crypto.randomUUID()
      : `${Date.now()}-${Math.random().toString(36).slice(2)}`;

    setUploading(true);
    setProgress({ percent: 0, phase: 'starting', message: 'Uploading file...', status: 'running' });

    // For v2.1 ingestion section types, poll progress live
    const isV21 = sectionType === 'google_ads_export' || sectionType === 'moengage_push';
    if (isV21) startProgressPolling(runId);

    try {
      const res = await startTraining(
        trainingMode !== 'text_only' ? csvFile : null,
        sectionType,
        trainingMode,
        textInput,
        kpiColumns,
        heroColumns.filter((h) => h.column),
        runId,
        remarks,
      );
      stopProgressPolling();
      setProgress({ percent: 100, phase: 'completed', message: 'Training complete', status: 'completed' });
      setSession(res.data);

      // Initialize answers
      const initAnswers = {};
      (res.data.questions || []).forEach((q) => {
        initAnswers[q.question_id] = q.default || '';
      });
      setAnswers(initAnswers);

      // v2.1 deterministic ingestion — no Q&A flow, just stats
      const dp = res.data.directive_preview || {};
      if (res.data.status === 'approved' && dp.format) {
        const embedded = dp.embedded ?? 0;
        const skipped = dp.skipped_low_volume ?? 0;
        const quality = (dp.quality_score ?? 0).toFixed(2);
        toast.success(
          `Trained on ${dp.source_rows} CSV rows → ${dp.normalized_records} records, ` +
          `${embedded} embedded (${skipped} below impression floor). Quality: ${quality}`,
          { duration: 8000 }
        );
        loadSessions();
      } else {
        toast.success('Data analyzed — review AI questions below');
      }
    } catch (err) {
      stopProgressPolling();
      setProgress({ percent: 0, phase: 'failed', message: err.response?.data?.detail || 'Upload failed', status: 'failed' });
      toast.error(err.response?.data?.detail || 'Upload failed');
    } finally {
      setUploading(false);
    }
  };

  // Cleanup the poll on unmount
  useEffect(() => () => stopProgressPolling(), []);

  const handleSubmitAnswers = async (approve = false, saveMode = null) => {
    setSubmitting(true);
    try {
      const answerList = Object.entries(answers).map(([qid, answer]) => ({
        question_id: parseInt(qid),
        answer,
      }));

      const payload = {
        session_id: session.session_id,
        answers: answerList,
        approve,
      };
      if (saveMode) payload.save_mode = saveMode;

      const res = await answerTraining(payload);
      setSession(res.data);
      setShowSaveMode(false);

      if (res.data.status === 'approved') {
        toast.success('Training directive approved and saved!');
        loadSessions();
        loadDirectives();
      } else if (res.data.status === 'ready_for_approval') {
        toast.success('Directive refined — ready for approval');
      } else if (res.data.questions?.length > 0) {
        const initAnswers = {};
        res.data.questions.forEach((q) => {
          initAnswers[q.question_id] = q.default || '';
        });
        setAnswers(initAnswers);
        toast('Follow-up questions generated');
      }
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to submit answers');
    } finally {
      setSubmitting(false);
    }
  };

  const handleDeleteSession = async (sessionId) => {
    if (!window.confirm(
      'Delete this training session?\n\nThis removes the session record and the BigQuery rows it produced. ' +
      'Embedding cache entries are kept (they will be reused or overwritten by future training runs).'
    )) return;
    try {
      const res = await deleteTrainingSession(sessionId);
      const bq = res.data?.bq_rows ?? 0;
      toast.success(`Session deleted${bq > 0 ? ` — ${bq.toLocaleString()} BQ rows removed` : ''}`);
      loadSessions();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to delete session');
    }
  };

  const handleExportSessions = async () => {
    try {
      const res = await exportTrainingSessions();
      const blob = new Blob([res.data], { type: 'text/csv' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `training_sessions_${new Date().toISOString().slice(0, 10)}.csv`;
      a.click();
      URL.revokeObjectURL(url);
      toast.success('Sessions exported!');
    } catch {
      toast.error('Export failed');
    }
  };

  const resetForm = () => {
    setSession(null);
    setCsvFile(null);
    setCsvColumns([]);
    setKpiColumns([]);
    setHeroColumns([]);
    setTextInput('');
    setRemarks('');
    setAnswers({});
    setShowSaveMode(false);
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  const needsCSV = !isCreativeAssets && trainingMode !== 'text_only';
  const needsText = !isCreativeAssets && trainingMode !== 'csv_only';
  const showCsvOptions = needsCSV && csvColumns.length > 0;

  return (
    <div className="admin-panel">
      {/* Upload Section */}
      <div className="training-upload">
        <h3>AI Training — Upload & Analyze</h3>
        <p style={{ fontSize: '0.85rem', marginBottom: '1rem' }}>
          Upload data and/or provide text context. Gemini will analyze inputs,
          generate insights, and ask clarifying questions before saving.
        </p>

        {/* Section Type */}
        <div className="form-group">
          <label>Section Type</label>
          <div className="section-type-tabs">
            {SECTION_TYPES.map((s) => (
              <button
                key={s.value}
                className={`section-type-tab ${sectionType === s.value ? 'active' : ''}`}
                onClick={() => setSectionType(s.value)}
              >
                <span>{s.icon}</span> {s.label}
              </button>
            ))}
          </div>
        </div>

        {/* Training Mode (hidden for creative_assets — that path is zip-only) */}
        {!isCreativeAssets && (
          <div className="form-group">
            <label>Training Mode</label>
            <div className="training-mode-grid">
              {TRAINING_MODES.map((m) => {
                const Icon = m.icon;
                return (
                  <button
                    key={m.value}
                    className={`training-mode-card ${trainingMode === m.value ? 'active' : ''}`}
                    onClick={() => setTrainingMode(m.value)}
                  >
                    <Icon size={20} />
                    <span className="training-mode-label">{m.label}</span>
                    <span className="training-mode-desc">{m.desc}</span>
                  </button>
                );
              })}
            </div>
          </div>
        )}

        {/* Creative-asset (zip) — brand picker + zip input */}
        {isCreativeAssets && (
          <>
            <div className="form-group">
              <label>Brand *</label>
              <IntelligentPropertyPicker
                value={creativeBrandSel}
                onChange={setCreativeBrandSel}
                scopeSummary={null}
                placeholder="Pick the brand this pack belongs to…"
              />
              <p style={{ fontSize: 12, color: 'var(--text-muted, #6b7280)', marginTop: 4 }}>
                One brand per pack. Mixed-brand zips must be uploaded separately so ideation retrieval stays scoped correctly.
              </p>
            </div>
            <div className="form-group">
              <label>Pack Zip *</label>
              <input
                ref={zipInputRef}
                type="file"
                accept=".zip"
                onChange={(e) => setZipFile(e.target.files?.[0] || null)}
                disabled={uploading}
              />
              <p style={{ fontSize: 12, color: 'var(--text-muted, #6b7280)', marginTop: 4 }}>
                Zip layout: images at the root + <code>ad_copies.xlsx</code> with columns{' '}
                <code>image_filename, headline, body</code> (optional: <code>cta, platform, persona, hero_offer, campaign_name, season, theme</code>).
                Each image is captioned by Gemini Vision and the cost is recorded under Training Sessions.
              </p>
            </div>
          </>
        )}

        {/* CSV Upload (legacy CSV/text paths only) */}
        {!isCreativeAssets && needsCSV && (
          <div className="form-group">
            <label>CSV File</label>
            <input
              ref={fileInputRef}
              type="file"
              accept=".csv"
              onChange={handleFileSelect}
              disabled={uploading}
            />
          </div>
        )}

        {/* CSV Column Options */}
        {showCsvOptions && (
          <>
            {/* KPI Columns */}
            <div className="form-group">
              <label>KPI Columns <span style={{ fontSize: '0.7rem', fontWeight: 400 }}>(optional — select key metrics to focus analysis)</span></label>
              <div className="kpi-selector">
                {csvColumns.map((col) => (
                  <button
                    key={col}
                    className={`kpi-chip ${kpiColumns.includes(col) ? 'active' : ''}`}
                    onClick={() => toggleKpi(col)}
                  >
                    {col}
                  </button>
                ))}
              </div>
            </div>

            {/* Hero Columns */}
            <div className="form-group">
              <label>
                <Star size={14} style={{ verticalAlign: 'middle' }} /> Hero Columns
                <span style={{ fontSize: '0.7rem', fontWeight: 400 }}> (optional — mark columns for special attention)</span>
              </label>
              {heroColumns.map((h, idx) => (
                <div key={idx} className="hero-column-row">
                  <select
                    value={h.column}
                    onChange={(e) => updateHeroColumn(idx, 'column', e.target.value)}
                  >
                    <option value="">Select column...</option>
                    {csvColumns.map((col) => (
                      <option key={col} value={col}>{col}</option>
                    ))}
                  </select>
                  <input
                    value={h.description}
                    onChange={(e) => updateHeroColumn(idx, 'description', e.target.value)}
                    placeholder="Description (e.g., primary revenue metric)"
                  />
                  <button className="btn-icon danger" onClick={() => removeHeroColumn(idx)}>
                    <XCircle size={16} />
                  </button>
                </div>
              ))}
              <button className="btn btn-sm btn-outline" onClick={addHeroColumn} style={{ marginTop: '0.5rem' }}>
                + Add Hero Column
              </button>
            </div>
          </>
        )}

        {/* Text Input */}
        {needsText && (
          <div className="form-group">
            <label>Strategy Notes & Context</label>
            <textarea
              className="training-text-input"
              value={textInput}
              onChange={(e) => setTextInput(e.target.value)}
              placeholder="Enter brand guidelines, strategy notes, campaign context, or any instructions for the AI to consider during analysis..."
              rows={6}
            />
          </div>
        )}

        {/* Remarks */}
        <div className="form-group">
          <label>
            Remarks <span style={{ fontSize: '0.7rem', fontWeight: 400 }}>(optional — note about this training run)</span>
          </label>
          <textarea
            className="training-text-input"
            value={remarks}
            onChange={(e) => setRemarks(e.target.value)}
            placeholder="e.g., Q4 Diwali campaign data, Sept-Nov 2025. Includes only Demand Gen and Search ads."
            rows={2}
            maxLength={1000}
            style={{ minHeight: 'auto' }}
          />
        </div>

        {/* Submit Button */}
        <button
          className="btn btn-primary"
          onClick={handleUpload}
          disabled={uploading}
          style={{ marginTop: '0.5rem' }}
        >
          {uploading ? (
            <><div className="loading-spinner" style={{ width: 16, height: 16 }} /> Training Model...</>
          ) : (
            <><Upload size={16} /> Start Model Training</>
          )}
        </button>

        {/* Live progress bar (v2.1 ingestion) */}
        {progress && (
          <div
            style={{
              marginTop: '1rem',
              padding: '0.75rem 1rem',
              border: '1px solid var(--border, #e5e7eb)',
              borderRadius: 8,
              background: progress.status === 'failed' ? '#fef2f2' : progress.status === 'completed' ? '#f0fdf4' : '#f9fafb',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6, fontSize: '0.85rem' }}>
              <span style={{ fontWeight: 500 }}>
                {progress.status === 'failed' ? '❌ Failed'
                  : progress.status === 'completed' ? '✅ Complete'
                  : `⏳ ${progress.phase || 'Processing'}`}
              </span>
              <span style={{ color: '#6b7280' }}>{progress.percent || 0}%</span>
            </div>
            <div style={{ height: 8, background: '#e5e7eb', borderRadius: 4, overflow: 'hidden' }}>
              <div
                style={{
                  width: `${Math.min(100, progress.percent || 0)}%`,
                  height: '100%',
                  background: progress.status === 'failed'
                    ? '#ef4444'
                    : progress.status === 'completed'
                    ? '#10b981'
                    : 'linear-gradient(90deg, #d4a017, #f59e0b)',
                  transition: 'width 0.4s ease',
                }}
              />
            </div>
            <div style={{ fontSize: '0.75rem', color: '#6b7280', marginTop: 6 }}>
              {progress.message || ''}
              {progress.total ? ` (${progress.processed || 0} / ${progress.total})` : ''}
            </div>
          </div>
        )}
      </div>

      {/* Q&A Section */}
      {session && session.status !== 'approved' && session.status !== 'error' && (
        <div className="training-qa">
          <h3>
            <MessageSquare size={18} /> AI Questions
            <span className="badge badge-info" style={{ marginLeft: '0.5rem' }}>{session.status}</span>
          </h3>

          {session.questions?.length > 0 ? (
            <div className="training-questions">
              {session.questions.map((q) => (
                <div key={q.question_id} className="training-question-card">
                  <label className="training-question-text">{q.question}</label>
                  {q.options?.length > 0 ? (
                    <select
                      value={answers[q.question_id] || ''}
                      onChange={(e) => setAnswers({ ...answers, [q.question_id]: e.target.value })}
                    >
                      <option value="">Select...</option>
                      {q.options.map((opt, i) => (
                        <option key={i} value={opt}>{opt}</option>
                      ))}
                    </select>
                  ) : (
                    <input
                      value={answers[q.question_id] || ''}
                      onChange={(e) => setAnswers({ ...answers, [q.question_id]: e.target.value })}
                      placeholder="Your answer..."
                    />
                  )}
                </div>
              ))}

              <div className="training-actions">
                <button className="btn btn-outline" onClick={() => handleSubmitAnswers(false)} disabled={submitting}>
                  {submitting ? 'Submitting...' : 'Submit Answers'}
                </button>
                <button className="btn btn-primary" onClick={() => setShowSaveMode(true)} disabled={submitting}>
                  <CheckCircle size={16} /> Approve & Save
                </button>
              </div>
            </div>
          ) : session.status === 'ready_for_approval' ? (
            <div className="training-actions">
              <p>Directive is ready for final approval.</p>
              <button className="btn btn-primary" onClick={() => setShowSaveMode(true)} disabled={submitting}>
                <CheckCircle size={16} /> Approve & Save Directive
              </button>
            </div>
          ) : null}

          {/* Save Mode Dialog */}
          {showSaveMode && (
            <div className="save-mode-dialog">
              <h4>How should this directive be saved?</h4>
              <div className="save-mode-options">
                <button
                  className="save-mode-option"
                  onClick={() => handleSubmitAnswers(true, 'replace')}
                  disabled={submitting}
                >
                  <strong>Replace</strong>
                  <span>Remove all previous {SECTION_TYPES.find((s) => s.value === sectionType)?.label} directives and save this one</span>
                </button>
                <button
                  className="save-mode-option"
                  onClick={() => handleSubmitAnswers(true, 'append')}
                  disabled={submitting}
                >
                  <strong>Append</strong>
                  <span>Keep existing directives and add this one alongside them</span>
                </button>
              </div>
              <button className="btn btn-sm btn-outline" onClick={() => setShowSaveMode(false)} style={{ marginTop: '0.5rem' }}>
                Cancel
              </button>
            </div>
          )}

          {/* Directive Preview */}
          {session.directive_preview && !session.directive_preview.error && (
            <div className="training-preview">
              <h4>Directive Preview</h4>
              <pre className="training-preview-json">
                {JSON.stringify(session.directive_preview, null, 2)}
              </pre>
            </div>
          )}
        </div>
      )}

      {/* Approved Confirmation */}
      {session?.status === 'approved' && (
        <div className="training-success">
          <CheckCircle size={24} />
          <p>Training directive approved and saved successfully!</p>
          <button className="btn btn-outline" onClick={resetForm}>
            Start New Training
          </button>
        </div>
      )}

      {/* Error */}
      {session?.status === 'error' && (
        <div className="training-error">
          <XCircle size={24} />
          <p>Training failed: {session.directive_preview?.error || 'Unknown error'}</p>
          <button className="btn btn-outline" onClick={resetForm}>
            Try Again
          </button>
        </div>
      )}

      {/* Bottom Panel — Sessions only */}
      <div className="training-panels">
        {true && (
          <div className="training-history">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem' }}>
              <h4 style={{ margin: 0 }}>Training Sessions</h4>
              <button className="btn btn-sm btn-outline export-btn" onClick={handleExportSessions}>
                <Download size={14} /> Export CSV
              </button>
            </div>
            {sessions.length === 0 ? (
              <p style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>No training sessions yet.</p>
            ) : (
              <div style={{ overflowX: 'auto' }}>
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Section</th>
                      <th>Mode</th>
                      <th>Status</th>
                      <th>Save</th>
                      <th>Tokens</th>
                      <th>Cost (₹)</th>
                      <th>Time</th>
                      <th>Date</th>
                      <th>Remarks</th>
                      <th style={{ width: 60 }}></th>
                    </tr>
                  </thead>
                  <tbody>
                    {sessions.map((s) => (
                      <tr key={s.session_id}>
                        <td>{SECTION_TYPES.find((t) => t.value === s.section_type)?.label || s.section_type || s.csv_type || '-'}</td>
                        <td>{TRAINING_MODES.find((m) => m.value === s.training_mode)?.label || s.training_mode || '-'}</td>
                        <td>
                          <span className={`badge badge-${s.status === 'approved' ? 'admin' : s.status === 'error' ? 'danger' : 'user'}`}>
                            {s.status}
                          </span>
                        </td>
                        <td>{s.save_mode || '-'}</td>
                        <td>{((s.input_tokens || 0) + (s.output_tokens || 0)).toLocaleString()}</td>
                        <td style={{ color: 'var(--gold)' }}>
                          {s.cost_inr != null ? `₹${Number(s.cost_inr).toFixed(4)}` : '-'}
                        </td>
                        <td>{s.time_seconds ? `${s.time_seconds}s` : '-'}</td>
                        <td>{s.created_at ? new Date(s.created_at).toLocaleDateString() : '-'}</td>
                        <td
                          style={{ maxWidth: 220, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', fontSize: '0.8rem', color: '#6b7280' }}
                          title={s.remarks || ''}
                        >
                          {s.remarks || '—'}
                        </td>
                        <td>
                          <button
                            className="btn-icon danger"
                            onClick={() => handleDeleteSession(s.session_id)}
                            title="Delete session"
                            style={{ padding: 4 }}
                          >
                            <Trash2 size={14} />
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}

      </div>
    </div>
  );
}
