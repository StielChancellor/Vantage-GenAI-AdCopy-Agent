import { useState, useEffect } from 'react';
import { startTraining, answerTraining, getTrainingSessions, deleteTrainingDirective } from '../services/api';
import toast from 'react-hot-toast';
import { Upload, CheckCircle, XCircle, MessageSquare, Trash2 } from 'lucide-react';

export default function TrainingWizard() {
  const [csvType, setCsvType] = useState('historical_ads');
  const [hotelName, setHotelName] = useState('');
  const [uploading, setUploading] = useState(false);

  // Training session state
  const [session, setSession] = useState(null);
  const [answers, setAnswers] = useState({});
  const [submitting, setSubmitting] = useState(false);

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

  const handleUpload = async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    if (!file.name.endsWith('.csv')) {
      toast.error('Only CSV files are supported');
      return;
    }

    setUploading(true);
    try {
      const res = await startTraining(file, csvType, hotelName);
      setSession(res.data);
      // Initialize answers
      const initAnswers = {};
      (res.data.questions || []).forEach((q) => {
        initAnswers[q.question_id] = q.default || '';
      });
      setAnswers(initAnswers);
      toast.success('CSV analyzed — review AI questions below');
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Upload failed');
    } finally {
      setUploading(false);
      e.target.value = ''; // Reset file input
    }
  };

  const handleSubmitAnswers = async (approve = false) => {
    setSubmitting(true);
    try {
      const answerList = Object.entries(answers).map(([qid, answer]) => ({
        question_id: parseInt(qid),
        answer,
      }));

      const res = await answerTraining({
        session_id: session.session_id,
        answers: answerList,
        approve,
      });

      setSession(res.data);

      if (res.data.status === 'approved') {
        toast.success('Training directive approved and saved!');
        loadSessions();
      } else if (res.data.status === 'ready_for_approval') {
        toast.success('Directive refined — ready for approval');
      } else if (res.data.questions?.length > 0) {
        // New follow-up questions
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

  const handleDeleteDirective = async (hotelName, type) => {
    if (!window.confirm(`Delete ${type} directive for ${hotelName}?`)) return;
    try {
      await deleteTrainingDirective(hotelName, type);
      toast.success('Directive deleted');
      loadSessions();
    } catch {
      toast.error('Failed to delete directive');
    }
  };

  return (
    <div className="admin-panel">
      {/* Upload Section */}
      <div className="training-upload">
        <h3>AI Training — Upload & Analyze</h3>
        <p style={{ fontSize: '0.85rem', marginBottom: '1rem' }}>
          Upload a CSV file. Gemini will auto-analyze the data, generate insights,
          and ask clarifying questions before saving the training directive.
        </p>

        <div className="training-upload-form">
          <div className="form-group">
            <label>CSV Type</label>
            <select value={csvType} onChange={(e) => setCsvType(e.target.value)}>
              <option value="historical_ads">Historical Ad Performance</option>
              <option value="brand_usp">Brand & USP Data</option>
            </select>
          </div>

          <div className="form-group">
            <label>Hotel Name <span style={{ fontSize: '0.7rem', fontWeight: 400 }}>(optional — auto-detected from CSV)</span></label>
            <input value={hotelName} onChange={(e) => setHotelName(e.target.value)} placeholder="e.g., The Grand Hyatt" />
          </div>

          <div className="form-group">
            <label>CSV File</label>
            <input type="file" accept=".csv" onChange={handleUpload} disabled={uploading} />
          </div>

          {uploading && <div className="training-status"><div className="loading-spinner" /> Analyzing CSV with AI...</div>}
        </div>
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
                <button className="btn btn-primary" onClick={() => handleSubmitAnswers(true)} disabled={submitting}>
                  <CheckCircle size={16} /> Approve & Save
                </button>
              </div>
            </div>
          ) : session.status === 'ready_for_approval' ? (
            <div className="training-actions">
              <p>Directive is ready for final approval.</p>
              <button className="btn btn-primary" onClick={() => handleSubmitAnswers(true)} disabled={submitting}>
                <CheckCircle size={16} /> Approve & Save Directive
              </button>
            </div>
          ) : null}

          {/* Directive Preview */}
          {session.directive_preview && (
            <div className="training-preview">
              <h4>Directive Preview</h4>
              <pre className="training-preview-json">
                {JSON.stringify(session.directive_preview, null, 2)}
              </pre>
            </div>
          )}
        </div>
      )}

      {/* Approved confirmation */}
      {session?.status === 'approved' && (
        <div className="training-success">
          <CheckCircle size={24} />
          <p>Training directive approved and saved successfully!</p>
          <button className="btn btn-outline" onClick={() => setSession(null)}>
            Start New Training
          </button>
        </div>
      )}

      {/* Error */}
      {session?.status === 'error' && (
        <div className="training-error">
          <XCircle size={24} />
          <p>Training failed: {session.directive_preview?.error || 'Unknown error'}</p>
          <button className="btn btn-outline" onClick={() => setSession(null)}>
            Try Again
          </button>
        </div>
      )}

      {/* Training History */}
      <div className="training-history">
        <h3>Training Sessions</h3>
        {sessions.length === 0 ? (
          <p style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>No training sessions yet.</p>
        ) : (
          <table className="data-table">
            <thead>
              <tr><th>Hotel</th><th>Type</th><th>Status</th><th>Date</th><th></th></tr>
            </thead>
            <tbody>
              {sessions.map((s) => (
                <tr key={s.session_id}>
                  <td>{s.hotel_name}</td>
                  <td>{s.csv_type === 'historical_ads' ? 'Historical Ads' : 'Brand USP'}</td>
                  <td>
                    <span className={`badge badge-${s.status === 'approved' ? 'admin' : 'user'}`}>
                      {s.status}
                    </span>
                  </td>
                  <td>{s.created_at ? new Date(s.created_at).toLocaleDateString() : '-'}</td>
                  <td>
                    {s.status === 'approved' && (
                      <button className="btn-icon danger" onClick={() => handleDeleteDirective(s.hotel_name, s.csv_type)}>
                        <Trash2 size={14} />
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
