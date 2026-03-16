import { useEffect, useRef, useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth';
import { login } from '../services/api';
import toast from 'react-hot-toast';

// ─── FEATURE DATA ─────────────────────────────────────────────────────────────
const FEATURES = [
  {
    icon: '🎯',
    title: 'AI Ad Copy Generation',
    desc: 'Generate high-converting ad copy in seconds. Upload your brand brief, USPs, and past performance data — Vantage outputs multiple variants optimized per platform.',
    tag: 'Marketer',
  },
  {
    icon: '📅',
    title: 'CRM Marketing Calendar',
    desc: 'Plan, schedule, and track every campaign in a beautiful calendar. From acquisition pushes to retention flows — never miss a critical touchpoint.',
    tag: 'Marketer',
  },
  {
    icon: '🌐',
    title: 'Multi-Platform Orchestration',
    desc: 'One brief, every channel. Output tailored copy for Meta, Google, LinkedIn, TikTok, and more with platform-specific tone and format rules built in.',
    tag: 'Marketer',
  },
  {
    icon: '💬',
    title: 'Smart Brief Copilot',
    desc: 'Chat naturally with your AI marketing partner. Describe your campaign in plain English — the Copilot extracts intent, crafts a structured brief, and generates assets.',
    tag: 'Marketer',
  },
  {
    icon: '🔍',
    title: 'Intent Capture Engine',
    desc: 'Every conversation captures audience intent signals. Build smarter retargeting and lookalike segments from real interaction data without extra data pipelines.',
    tag: 'Marketer',
  },
  {
    icon: '📊',
    title: 'Real-Time Performance Insights',
    desc: 'Track CTR, ROAS, impressions, and conversion rates live. AI surfaces anomalies and recommends optimizations before you notice the drop.',
    tag: 'Marketer',
  },
  {
    icon: '🧠',
    title: 'RAG-Powered Knowledge Engine',
    desc: 'Firestore-backed Retrieval Augmented Generation indexes your historical campaign data, brand guidelines, and competitor insights for contextual, brand-accurate output.',
    tag: 'CIO',
  },
  {
    icon: '🔐',
    title: 'Secure Multi-Tenant Architecture',
    desc: 'Role-based access control with JWT auth. Isolated data namespacing per property. Admin panel with full audit trail, user management, and training controls.',
    tag: 'CIO',
  },
  {
    icon: '📍',
    title: 'Geo-Targeted Campaigns',
    desc: 'Google Maps API integration delivers real-time location intelligence. Combine geo-signals with intent data for hyper-local campaign precision.',
    tag: 'CIO',
  },
  {
    icon: '⚡',
    title: 'Cloud-Native & Scalable',
    desc: 'Deployed on GCP Cloud Run with Firestore as the primary data layer. Zero cold-start latency in production. Auto-scales to handle peak campaign launches.',
    tag: 'CIO',
  },
  {
    icon: '🤖',
    title: 'Anthropic Claude AI Core',
    desc: 'Powered by Claude Sonnet — the state-of-the-art model for long-context reasoning, structured output, and instruction following at production grade.',
    tag: 'CIO',
  },
  {
    icon: '🛠️',
    title: 'Full Admin Control Center',
    desc: 'Manage users, upload training data, review audit logs, configure system-wide settings, and monitor agent activity — all from a unified admin dashboard.',
    tag: 'CIO',
  },
];

// ─── SPACE CANVAS (stars + shooting stars, mouse-reactive twinkling) ──────────
function SpaceCanvas() {
  const canvasRef = useRef(null);
  const mouseRef = useRef({ x: -9999, y: -9999 });

  useEffect(() => {
    const canvas = canvasRef.current;
    const ctx = canvas.getContext('2d');
    let animId;
    const stars = [];
    const shootingStars = [];

    const resize = () => {
      canvas.width = window.innerWidth;
      canvas.height = window.innerHeight;
    };
    resize();
    window.addEventListener('resize', resize);

    const handleMouseMove = (e) => {
      mouseRef.current = { x: e.clientX, y: e.clientY };
    };
    const handleTouchMove = (e) => {
      if (e.touches[0]) {
        mouseRef.current = { x: e.touches[0].clientX, y: e.touches[0].clientY };
      }
    };
    window.addEventListener('mousemove', handleMouseMove);
    window.addEventListener('touchmove', handleTouchMove, { passive: true });

    // Dense starfield — 480 stars with parallax drift
    for (let i = 0; i < 480; i++) {
      const r = Math.random() * 1.8 + 0.2;
      // Bigger/brighter stars drift faster (parallax: they're "closer")
      const driftSpeed = 0.04 + r * 0.06;
      const angle = Math.random() * Math.PI * 2;
      stars.push({
        x: Math.random() * window.innerWidth,
        y: Math.random() * window.innerHeight,
        r,
        vx: Math.cos(angle) * driftSpeed,
        vy: Math.sin(angle) * driftSpeed,
        twinkle: Math.random() * Math.PI * 2,
        baseSpeed: 0.010 + Math.random() * 0.018,
        baseAlpha: 0.28 + Math.random() * 0.72,
        hue: Math.random() > 0.85 ? 'rgba(200,220,255,' : Math.random() > 0.5 ? 'rgba(255,255,255,' : 'rgba(180,200,255,',
      });
    }

    function spawnShootingStar() {
      shootingStars.push({
        x: Math.random() * window.innerWidth * 0.75,
        y: Math.random() * window.innerHeight * 0.4,
        len: 90 + Math.random() * 140,
        spd: 8 + Math.random() * 8,
        alpha: 1,
        angle: Math.PI / 4 + (Math.random() - 0.5) * 0.4,
        width: 1 + Math.random(),
      });
    }

    function draw() {
      ctx.clearRect(0, 0, canvas.width, canvas.height);

      // Deep space gradient background
      const bg = ctx.createLinearGradient(0, 0, 0, canvas.height);
      bg.addColorStop(0, '#02020e');
      bg.addColorStop(0.45, '#060618');
      bg.addColorStop(1, '#030510');
      ctx.fillStyle = bg;
      ctx.fillRect(0, 0, canvas.width, canvas.height);

      // Nebula blobs
      const nebulas = [
        { cx: 0.18, cy: 0.28, r: 340, col: '37,99,235',   a: 0.06  },
        { cx: 0.82, cy: 0.55, r: 280, col: '139,92,246',  a: 0.07  },
        { cx: 0.5,  cy: 0.88, r: 220, col: '236,72,153',  a: 0.038 },
        { cx: 0.65, cy: 0.12, r: 190, col: '6,182,212',   a: 0.032 },
      ];
      nebulas.forEach(n => {
        const grd = ctx.createRadialGradient(
          n.cx * canvas.width, n.cy * canvas.height, 0,
          n.cx * canvas.width, n.cy * canvas.height, n.r
        );
        grd.addColorStop(0, `rgba(${n.col},${n.a})`);
        grd.addColorStop(1, 'transparent');
        ctx.fillStyle = grd;
        ctx.fillRect(0, 0, canvas.width, canvas.height);
      });

      // Stars — mouse proximity boosts twinkle speed and brightness
      const mx = mouseRef.current.x;
      const my = mouseRef.current.y;
      const hoverRadius = 160;

      stars.forEach(s => {
        // Drift — wrap around edges with a small margin
        s.x += s.vx;
        s.y += s.vy;
        const pad = 4;
        if (s.x < -pad) s.x = canvas.width + pad;
        else if (s.x > canvas.width + pad) s.x = -pad;
        if (s.y < -pad) s.y = canvas.height + pad;
        else if (s.y > canvas.height + pad) s.y = -pad;

        // Mouse hover reactivity
        const dx = s.x - mx;
        const dy = s.y - my;
        const dist = Math.sqrt(dx * dx + dy * dy);
        const hoverFactor = dist < hoverRadius ? 1 - dist / hoverRadius : 0;

        // Twinkle speed ramps up near cursor
        s.twinkle += s.baseSpeed + hoverFactor * 0.20;

        // Alpha pulses stronger near cursor
        const pulseRange = 0.40 + hoverFactor * 0.58;
        const a = Math.max(0.04, s.baseAlpha * (0.56 + Math.sin(s.twinkle) * pulseRange));

        // Slight size boost on hover
        const r = s.r + hoverFactor * 1.4;

        ctx.beginPath();
        ctx.arc(s.x, s.y, r, 0, Math.PI * 2);
        ctx.fillStyle = `${s.hue}${a})`;
        ctx.fill();

        // Cross sparkle for bright hovered stars
        if (hoverFactor > 0.5 && a > 0.7) {
          ctx.strokeStyle = `rgba(255,255,255,${hoverFactor * 0.55})`;
          ctx.lineWidth = 0.6;
          ctx.beginPath();
          ctx.moveTo(s.x - r * 2.5, s.y);
          ctx.lineTo(s.x + r * 2.5, s.y);
          ctx.moveTo(s.x, s.y - r * 2.5);
          ctx.lineTo(s.x, s.y + r * 2.5);
          ctx.stroke();
        }
      });

      // Shooting stars
      for (let i = shootingStars.length - 1; i >= 0; i--) {
        const ss = shootingStars[i];
        ss.x += Math.cos(ss.angle) * ss.spd;
        ss.y += Math.sin(ss.angle) * ss.spd;
        ss.alpha -= 0.025;
        if (ss.alpha <= 0) { shootingStars.splice(i, 1); continue; }

        const tail = ctx.createLinearGradient(
          ss.x, ss.y,
          ss.x - Math.cos(ss.angle) * ss.len,
          ss.y - Math.sin(ss.angle) * ss.len
        );
        tail.addColorStop(0, `rgba(255,255,255,${ss.alpha})`);
        tail.addColorStop(0.4, `rgba(180,210,255,${ss.alpha * 0.6})`);
        tail.addColorStop(1, 'transparent');
        ctx.beginPath();
        ctx.moveTo(ss.x, ss.y);
        ctx.lineTo(
          ss.x - Math.cos(ss.angle) * ss.len,
          ss.y - Math.sin(ss.angle) * ss.len
        );
        ctx.strokeStyle = tail;
        ctx.lineWidth = ss.width;
        ctx.stroke();
      }

      animId = requestAnimationFrame(draw);
    }
    draw();

    const shootInterval = setInterval(spawnShootingStar, 3500);

    return () => {
      cancelAnimationFrame(animId);
      clearInterval(shootInterval);
      window.removeEventListener('resize', resize);
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('touchmove', handleTouchMove);
    };
  }, []);

  return (
    <canvas
      ref={canvasRef}
      style={{
        position: 'fixed', top: 0, left: 0, width: '100vw', height: '100vh',
        zIndex: 0, pointerEvents: 'none',
      }}
    />
  );
}

// ─── INLINE LOGIN OVERLAY ─────────────────────────────────────────────────────
function InlineLogin({ onClose }) {
  const { loginUser } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);

  const sparkles = useRef(
    Array.from({ length: 14 }, (_, i) => ({
      id: i,
      left: `${5 + Math.random() * 90}%`,
      top: `${5 + Math.random() * 90}%`,
      delay: `${Math.random() * 2.5}s`,
      dur: `${1.8 + Math.random() * 1.5}s`,
      size: `${5 + Math.random() * 8}px`,
    }))
  ).current;

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      const res = await login(email, password);
      loginUser(res.data.user, res.data.access_token);
      toast.success('Agent initialized!');
      if (res.data.user.role === 'admin') {
        navigate('/admin');
      } else {
        navigate('/adcopy');
      }
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Authentication failed');
      setLoading(false);
    }
  };

  return (
    <div className="lp-overlay-bg" onClick={e => e.target === e.currentTarget && onClose()}>
      <div className="lp-login-card">
        {sparkles.map(s => (
          <div
            key={s.id}
            className="lp-sparkle"
            style={{
              left: s.left, top: s.top,
              animationDelay: s.delay, animationDuration: s.dur,
              width: s.size, height: s.size,
            }}
          />
        ))}
        <button className="lp-login-close" onClick={onClose} aria-label="Close">✕</button>
        <div className="lp-login-icon-wrap">
          <div className="lp-login-icon">⚡</div>
        </div>
        <h2 className="lp-login-title">Welcome to Vantage</h2>
        <p className="lp-login-sub">Sign in to initialize your AI agent</p>
        <form onSubmit={handleSubmit} className="lp-login-form">
          <div className="lp-form-group">
            <label htmlFor="lp-email">Email</label>
            <input
              id="lp-email"
              type="email"
              value={email}
              onChange={e => setEmail(e.target.value)}
              placeholder="you@company.com"
              required
              autoFocus
            />
          </div>
          <div className="lp-form-group">
            <label htmlFor="lp-pass">Password</label>
            <input
              id="lp-pass"
              type="password"
              value={password}
              onChange={e => setPassword(e.target.value)}
              placeholder="••••••••"
              required
            />
          </div>
          <button type="submit" className="lp-login-submit" disabled={loading}>
            {loading ? (
              <span className="lp-login-spinner">
                <span className="lp-spinner-ring" />
                Authenticating...
              </span>
            ) : (
              'Initialize Agent →'
            )}
          </button>
        </form>
      </div>
    </div>
  );
}

// ─── LANDING PAGE ─────────────────────────────────────────────────────────────
export default function LandingPage() {
  const navigate = useNavigate();
  const { user } = useAuth();

  const [showLogin, setShowLogin] = useState(false);
  const [btnText, setBtnText] = useState('Initialize Agent');
  const [btnDisabled, setBtnDisabled] = useState(false);
  const [activeNav, setActiveNav] = useState('home');
  const [pulseRings, setPulseRings] = useState([]);
  const [trailParticles, setTrailParticles] = useState([]);
  const [filterTag, setFilterTag] = useState('All');

  // Robot refs
  const assemblyRef   = useRef(null);
  const headRef       = useRef(null);
  const torsoRef      = useRef(null);
  const eyeContainerRef = useRef(null);
  const armLeftRef    = useRef(null);
  const armRightRef   = useRef(null);
  const coreLightRef  = useRef(null);
  const floorShadowRef = useRef(null);
  const shockwaveRef  = useRef(null);
  const isTakingOffRef = useRef(false);
  const robotAnimRafRef = useRef(null);
  const pulseIntervalRef = useRef(null);
  const ringIdRef     = useRef(0);
  const particleIdRef = useRef(0);

  // Redirect if already logged in
  useEffect(() => {
    if (user) navigate('/adcopy');
  }, [user, navigate]);

  // ── CSS injection ──────────────────────────────────────────────────────────
  useEffect(() => {
    const style = document.createElement('style');
    style.id = 'lp-robot-styles';
    style.textContent = `
      /* ── ROOT ────────────────────────────────────────── */
      .lp-root {
        position: relative;
        min-height: 100vh;
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
        color: #e2e8f0;
        overflow-x: hidden;
        scrollbar-width: thin;
        scrollbar-color: rgba(37,99,235,0.3) transparent;
      }
      .lp-root::-webkit-scrollbar { width: 4px; }
      .lp-root::-webkit-scrollbar-thumb { background: rgba(37,99,235,0.35); border-radius: 3px; }

      /* ── SPOTLIGHT ───────────────────────────────────── */
      .lp-spotlight-fx {
        position: fixed; top: 0; left: 0;
        width: 100vw; height: 100vh;
        background: radial-gradient(600px circle at var(--lp-mx,50%) var(--lp-my,50%), rgba(6,182,212,0.045), transparent 40%);
        z-index: 1; pointer-events: none;
      }

      /* ── NAV ─────────────────────────────────────────── */
      .lp-nav {
        position: fixed; top: 0; left: 0; right: 0; z-index: 100;
        display: flex; align-items: center; justify-content: space-between;
        padding: 18px 48px;
        background: rgba(2,2,14,0.72);
        backdrop-filter: blur(14px);
        border-bottom: 1px solid rgba(255,255,255,0.05);
        animation: lpSlideDown 0.9s ease-out forwards;
      }
      @keyframes lpSlideDown { from { opacity:0; transform:translateY(-18px); } to { opacity:1; transform:none; } }

      .lp-logo {
        display: flex; align-items: center; gap: 10px;
        font-size: 1.4rem; font-weight: 800; letter-spacing: -0.5px; color: #f1f5f9;
        text-decoration: none; cursor: pointer;
      }
      .lp-logo-mark {
        width: 26px; height: 26px; border-radius: 7px; flex-shrink: 0;
        background: linear-gradient(135deg, #06b6d4, #8b5cf6);
        box-shadow: 0 0 18px rgba(6,182,212,0.45);
      }

      .lp-nav-links {
        display: flex; gap: 30px; align-items: center;
      }
      .lp-nav-link {
        background: none; border: none; cursor: pointer;
        color: rgba(226,232,240,0.55); font-size: 0.88rem; font-weight: 600;
        transition: color 0.2s; padding: 0; font-family: inherit;
      }
      .lp-nav-link:hover, .lp-nav-link.active { color: #06b6d4; }

      /* ── HERO SECTION ────────────────────────────────── */
      .lp-hero-section {
        position: relative; z-index: 2;
        min-height: 100vh;
        display: flex; align-items: center; justify-content: center;
        padding: 100px 48px 48px;
      }
      .lp-hero-container {
        display: flex; align-items: center; justify-content: space-between;
        width: 100%; max-width: 1280px; gap: 60px;
      }
      .lp-hero-content {
        flex: 1; max-width: 580px;
        display: flex; flex-direction: column; align-items: flex-start;
        animation: lpFadeUp 1s ease-out 0.2s both;
      }
      @keyframes lpFadeUp { from { opacity:0; transform:translateY(22px); } to { opacity:1; transform:none; } }

      .lp-badge {
        display: inline-flex; align-items: center; gap: 8px;
        padding: 6px 16px;
        background: rgba(139,92,246,0.12); border: 1px solid rgba(139,92,246,0.28);
        border-radius: 999px; color: #a78bfa;
        font-size: 0.82rem; font-weight: 600; margin-bottom: 28px;
        animation: lpFadeUp 1s ease-out 0.3s both;
      }
      .lp-badge-dot {
        width: 6px; height: 6px; border-radius: 50%;
        background: #a78bfa; box-shadow: 0 0 8px rgba(167,139,250,0.7);
        flex-shrink: 0; animation: lpDotPulse 2s infinite;
      }
      @keyframes lpDotPulse { 0%,100%{opacity:1;} 50%{opacity:0.4;} }

      .lp-hero-title {
        font-size: clamp(2.8rem, 5vw, 5.2rem);
        font-weight: 800; line-height: 1.05;
        letter-spacing: -2px; margin-bottom: 22px; color: #f8fafc;
        animation: lpFadeUp 1s ease-out 0.45s both;
      }
      .lp-title-gradient {
        background: linear-gradient(135deg, #06b6d4 0%, #8b5cf6 50%, #ec4899 100%);
        -webkit-background-clip: text; -webkit-text-fill-color: transparent;
        background-clip: text;
      }
      .lp-hero-sub {
        font-size: clamp(1rem, 1.8vw, 1.15rem);
        color: rgba(148,163,184,0.88); max-width: 530px;
        line-height: 1.65; margin-bottom: 40px; font-weight: 400;
        animation: lpFadeUp 1s ease-out 0.6s both;
      }
      .lp-cta-wrap { animation: lpFadeUp 1s ease-out 0.75s both; }

      /* ── GRADIENT CTA BUTTON ─────────────────────────── */
      .lp-gradient-btn {
        position: relative; isolation: isolate;
        background: transparent; border-radius: 9999px;
        padding: 16px 44px; border: none; cursor: pointer;
        font-family: inherit; font-size: 1.05rem; font-weight: 700;
        color: #fff; display: inline-flex; align-items: center; gap: 10px;
        box-shadow: 0 8px 24px rgba(0,0,0,0.2);
        transition: transform 0.2s, box-shadow 0.2s, opacity 0.2s;
        -webkit-tap-highlight-color: transparent;
      }
      .lp-gradient-btn::before {
        content: ''; position: absolute; inset: -2px; border-radius: 9999px;
        background: linear-gradient(90deg, #06b6d4, #8b5cf6, #ec4899, #06b6d4);
        background-size: 200% 100%;
        animation: lpGlowBorder 3s linear infinite; z-index: -2;
      }
      .lp-gradient-btn::after {
        content: ''; position: absolute; inset: 1px;
        background: #060a18; border-radius: 9999px; z-index: -1;
      }
      @keyframes lpGlowBorder { 0%{background-position:0% 50%;} 100%{background-position:200% 50%;} }
      .lp-gradient-btn:hover:not(:disabled) { transform: translateY(-2px) scale(1.02); box-shadow: 0 14px 32px rgba(139,92,246,0.35); }
      .lp-gradient-btn:active:not(:disabled) { transform: scale(0.98); }
      .lp-gradient-btn:disabled { opacity: 0.65; cursor: not-allowed; }

      /* ── HERO VISUAL ─────────────────────────────────── */
      .lp-hero-visual {
        flex: 1; position: relative;
        display: flex; justify-content: center; align-items: center;
        height: 580px; perspective: 1200px;
        animation: lpFadeUp 1s ease-out 0.5s both;
      }

      /* Halos */
      .lp-halo {
        position: absolute; border-radius: 50%;
        top: 50%; left: 50%; transform: translate(-50%, -50%);
        pointer-events: none;
      }
      .lp-halo-1 {
        width: 540px; height: 540px;
        border: 1px dashed rgba(6,182,212,0.32);
        animation: lpSpinRight 42s linear infinite;
      }
      .lp-halo-2 {
        width: 470px; height: 470px;
        border: 2px solid rgba(139,92,246,0.07);
        border-top: 2px solid rgba(139,92,246,0.55);
        animation: lpSpinLeft 25s linear infinite;
        box-shadow: 0 0 35px rgba(139,92,246,0.07);
      }
      @keyframes lpSpinRight { 100%{ transform:translate(-50%,-50%) rotate(360deg); } }
      @keyframes lpSpinLeft  { 100%{ transform:translate(-50%,-50%) rotate(-360deg); } }

      .lp-robot-scaler { display:flex; justify-content:center; align-items:center; width:100%; height:100%; }

      /* ── ROBOT ASSEMBLY ──────────────────────────────── */
      .lp-robot-assembly {
        position: relative; width: 300px; height: 400px;
        animation: lpRobotFloat 4s ease-in-out infinite; isolation: isolate;
      }
      @keyframes lpRobotFloat { 0%,100%{transform:translateY(0);} 50%{transform:translateY(-20px);} }

      /* Shiny polished metal — visible against dark space */
      .lp-glossy {
        background: linear-gradient(
          145deg,
          #7a9bb5 0%,    /* bright steel-blue top-left specular */
          #4a6d8a 10%,
          #2c4a62 25%,
          #1a2f42 45%,
          #0e1d2e 65%,
          #060f1a 100%
        );
        box-shadow:
          /* Strong top-left specular highlight */
          inset 8px 16px 32px rgba(255,255,255,0.38),
          /* Soft secondary fill */
          inset 2px 4px 10px rgba(150,200,255,0.12),
          /* Deep shadow bottom-right */
          inset -8px -10px 28px rgba(0,0,0,0.97),
          /* Cyan rim light — separates robot from dark bg */
          0 0 0 1.5px rgba(6,182,212,0.55),
          0 0 18px rgba(6,182,212,0.28),
          0 0 45px rgba(6,182,212,0.12),
          /* Purple accent rim on back */
          0 0 60px rgba(139,92,246,0.08),
          /* Depth shadow */
          0 24px 50px rgba(0,0,0,0.7);
        border: 1px solid rgba(150,210,240,0.22);
      }

      /* Glowing platform beneath robot */
      .lp-robot-assembly::after {
        content: '';
        position: absolute;
        bottom: -30px; left: 50%;
        transform: translateX(-50%);
        width: 180px; height: 24px;
        background: radial-gradient(ellipse at center, rgba(6,182,212,0.35) 0%, rgba(139,92,246,0.12) 50%, transparent 75%);
        filter: blur(8px);
        border-radius: 50%;
        z-index: -2;
        pointer-events: none;
      }

      .lp-robot-head {
        width: 240px; height: 180px; border-radius: 120px 120px 90px 90px;
        position: absolute; top: 20px; left: 50%; margin-left: -120px;
        display: flex; justify-content: center; align-items: center; z-index: 3;
        transition: transform 0.05s linear;
      }
      /* Large primary specular — upper-left gleam */
      .lp-robot-head::before {
        content: ''; position: absolute; top: 4%; left: 8%; width: 55%; height: 32%;
        background: radial-gradient(ellipse at 35% 35%, rgba(255,255,255,0.62) 0%, rgba(200,235,255,0.28) 40%, transparent 72%);
        border-radius: 50%; transform: rotate(-18deg); pointer-events: none; z-index: 5;
      }
      /* Secondary smaller gleam bottom-right */
      .lp-robot-head::after {
        content: ''; position: absolute; bottom: 12%; right: 12%; width: 22%; height: 14%;
        background: radial-gradient(ellipse at center, rgba(255,255,255,0.28) 0%, transparent 70%);
        border-radius: 50%; pointer-events: none; z-index: 5;
      }

      /* Teal-tinted glassy visor */
      .lp-robot-visor {
        width: 190px; height: 90px;
        background: linear-gradient(160deg, #001018 0%, #000a14 60%, #000608 100%);
        border-radius: 45px;
        box-shadow:
          inset 0 8px 24px rgba(0,0,0,1),
          inset 0 0 20px rgba(6,182,212,0.3),
          inset 0 0 40px rgba(6,182,212,0.1),
          0 0 12px rgba(6,182,212,0.25),
          0 3px 6px rgba(255,255,255,0.1);
        position: relative; display: flex; justify-content: center; align-items: center; gap: 20px; overflow: hidden;
        border: 1px solid rgba(6,182,212,0.2);
      }
      .lp-robot-visor::after {
        content: ''; position: absolute; top: 2px; left: 5%; width: 90%; height: 42px;
        background: linear-gradient(to bottom, rgba(180,240,255,0.18), rgba(100,200,255,0.06), transparent);
        border-radius: 40px 40px 0 0; pointer-events: none;
      }

      .lp-eye-container { display:flex; gap:25px; position:relative; z-index:2; transition:transform 0.05s linear; }
      .lp-robot-eye {
        width: 26px; height: 36px; border-radius: 20px; background: #e8f8ff;
        box-shadow:
          0 0 8px #fff,
          0 0 18px #06b6d4,
          0 0 35px #06b6d4,
          0 0 65px rgba(6,182,212,0.6),
          inset 0 0 8px rgba(6,182,212,0.4);
        animation: lpEyeBlink 4s infinite;
        transition: height 0.2s, background 0.2s, box-shadow 0.2s;
      }
      @keyframes lpEyeBlink { 0%,90%,100%{transform:scaleY(1);} 95%{transform:scaleY(0.08);} }

      /* Neck — brighter to be visible */
      .lp-robot-neck {
        width: 60px; height: 30px;
        background: linear-gradient(to bottom, #2a4a62, #162536);
        border-radius: 10px;
        position: absolute; top: 180px; left: 50%; margin-left: -30px; z-index: 2;
        box-shadow: inset 0 4px 8px rgba(0,0,0,0.7), 0 0 0 1px rgba(6,182,212,0.3);
      }
      .lp-robot-neck::after {
        content: ''; position: absolute; top: 50%; left: 50%; transform: translate(-50%,-50%);
        width: 80%; height: 4px; background: #06b6d4;
        box-shadow: 0 0 12px #06b6d4, 0 0 24px rgba(6,182,212,0.5); border-radius: 2px;
      }

      .lp-robot-torso {
        width: 160px; height: 140px; border-radius: 40px 40px 80px 80px;
        position: absolute; top: 200px; left: 50%; margin-left: -80px; z-index: 1;
        display: flex; justify-content: center; transition: transform 0.05s linear;
      }
      .lp-robot-core {
        width: 44px; height: 44px; background: #000; border-radius: 50%; margin-top: 28px;
        box-shadow: inset 0 4px 10px rgba(0,0,0,0.9), 0 0 0 2px rgba(139,92,246,0.5), 0 0 16px rgba(139,92,246,0.4);
        display: flex; justify-content: center; align-items: center;
      }
      .lp-robot-core-light {
        width: 18px; height: 18px; background: #a855f7; border-radius: 50%;
        box-shadow: 0 0 12px #a855f7, 0 0 28px #8b5cf6, 0 0 50px rgba(139,92,246,0.7);
        animation: lpPulseCore 2s infinite alternate; transition: all 0.3s ease;
      }
      @keyframes lpPulseCore { from{transform:scale(0.88);opacity:0.7;box-shadow:0 0 10px #a855f7,0 0 22px #8b5cf6;} to{transform:scale(1.12);opacity:1;box-shadow:0 0 18px #a855f7,0 0 40px #8b5cf6,0 0 70px rgba(139,92,246,0.5);} }

      .lp-robot-arm {
        position: absolute; width: 45px; height: 110px; border-radius: 25px; top: 215px; z-index: 4;
        transition: top 0.05s linear, margin-left 0.05s linear;
      }
      .lp-arm-left  { left:50%; margin-left:-130px; animation:lpFloatArmL 4s ease-in-out infinite; }
      .lp-arm-right { left:50%; margin-left:85px;   animation:lpFloatArmR 4s ease-in-out infinite reverse; }
      @keyframes lpFloatArmL { 0%,100%{transform:translateY(0) rotate(10deg);} 50%{transform:translateY(-10px) rotate(15deg);} }
      @keyframes lpFloatArmR { 0%,100%{transform:translateY(0) rotate(-10deg);} 50%{transform:translateY(-10px) rotate(-15deg);} }

      .lp-thruster {
        position: absolute; bottom: 5px; left: 50%; transform: translateX(-50%);
        display: flex; flex-direction: column; align-items: center;
        opacity: 0; z-index: -1; transition: opacity 0.2s;
      }
      .lp-flame-core {
        width: 12px; height: 0; background: #fff; border-radius: 100px;
        box-shadow: 0 0 20px #fff, 0 0 40px #06b6d4;
        transition: height 0.3s cubic-bezier(0.4,0,0.2,1); z-index: 2;
      }
      .lp-flame-plume {
        position: absolute; top: 0; width: 30px; height: 0;
        background: linear-gradient(to bottom, rgba(6,182,212,1) 0%, rgba(139,92,246,0.8) 50%, transparent 100%);
        border-radius: 100px; filter: blur(8px);
        transition: height 0.3s cubic-bezier(0.4,0,0.2,1); z-index: 1;
      }
      .lp-torso-thruster { bottom: 15px; }
      .lp-torso-thruster .lp-flame-core  { width: 25px; }
      .lp-torso-thruster .lp-flame-plume { width: 70px; filter: blur(12px); }

      /* Takeoff states */
      @keyframes lpMechShake {
        0%,100%{transform:translate(0,0) rotate(0);}
        20%{transform:translate(-3px,2px) rotate(-1deg);}
        40%{transform:translate(3px,-2px) rotate(1deg);}
        60%{transform:translate(-3px,-2px);}
        80%{transform:translate(3px,2px) rotate(-1deg);}
      }
      .lp-shaking { animation:lpMechShake 0.06s infinite !important; }
      .lp-warming-up .lp-thruster           { opacity:0.6; }
      .lp-warming-up .lp-flame-core         { height:20px; }
      .lp-warming-up .lp-flame-plume        { height:50px; }
      .lp-warming-up .lp-torso-thruster .lp-flame-core  { height:30px; }
      .lp-warming-up .lp-torso-thruster .lp-flame-plume { height:80px; }
      .lp-ignited .lp-thruster    { opacity:1; }
      .lp-ignited .lp-flame-core  { height:120px; animation:lpVFlicker 0.05s infinite alternate; }
      .lp-ignited .lp-flame-plume { height:180px; animation:lpVFlicker 0.07s infinite alternate-reverse; }
      .lp-ignited .lp-torso-thruster .lp-flame-core  { height:250px; }
      .lp-ignited .lp-torso-thruster .lp-flame-plume { height:400px; }
      @keyframes lpVFlicker { 0%{transform:scaleY(0.9) scaleX(0.95);opacity:0.8;} 100%{transform:scaleY(1.1) scaleX(1.05);opacity:1;} }
      /* Natural physics takeoff — squash → compress → liftoff → exponential acceleration */
      @keyframes lpNaturalTakeoff {
        /* Idle */
        0%   { transform: translateY(0px) scaleX(1)    scaleY(1); }
        /* Thrusters build — robot compresses down (weight + thrust) */
        6%   { transform: translateY(6px)  scaleX(1.04) scaleY(0.95); }
        13%  { transform: translateY(14px) scaleX(1.07) scaleY(0.90); }
        /* Fighting gravity — slight bounce before commit */
        22%  { transform: translateY(10px) scaleX(1.05) scaleY(0.93); }
        /* Breaks free — first lunge upward */
        32%  { transform: translateY(-18px) scaleX(0.96) scaleY(1.06); }
        /* Brief hover — thrusters at full, about to accelerate */
        40%  { transform: translateY(-30px) scaleX(0.97) scaleY(1.04);
               animation-timing-function: cubic-bezier(0.42, 0, 0.98, 0.52); }
        /* Exponential climb — gets faster every frame */
        58%  { transform: translateY(-200px) scaleX(0.98) scaleY(1.02); }
        72%  { transform: translateY(-600px) scaleX(0.99) scaleY(1.01); }
        85%  { transform: translateY(-1300px) scaleX(1) scaleY(1); }
        100% { transform: translateY(-2800px) scaleX(1) scaleY(1); }
      }
      .lp-flying { animation: lpNaturalTakeoff 2.2s forwards !important; }

      .lp-floor-shadow {
        position: absolute; bottom: -80px; width: 200px; height: 20px;
        background: rgba(0,0,0,0.18); border-radius: 50%; filter: blur(10px);
        animation: lpShadowBreathe 4s ease-in-out infinite; transition: opacity 0.3s;
      }
      @keyframes lpShadowBreathe { 0%,100%{transform:scale(1);opacity:0.18;} 50%{transform:scale(0.8);opacity:0.06;} }

      .lp-shockwave {
        position: absolute; bottom: -60px; left: 50%;
        width: 0; height: 0; border-radius: 50%;
        border: 4px solid #06b6d4; opacity: 0;
        transform: translate(-50%,-50%) rotateX(75deg); pointer-events: none; z-index: 0;
      }
      .lp-shockwave-go { animation:lpBlastRing 0.85s cubic-bezier(0.1,0.8,0.3,1) forwards; }
      @keyframes lpBlastRing {
        0%{width:50px;height:50px;opacity:1;border-width:20px;box-shadow:0 0 50px #06b6d4;}
        100%{width:800px;height:800px;opacity:0;border-width:0;}
      }

      /* ── PULSE RINGS ─────────────────────────────────── */
      .lp-pulse-ring {
        position: fixed; z-index: 3; pointer-events: none; border-radius: 50%;
        border: 1.5px solid rgba(139,92,246,0.55); transform: translate(-50%,-50%);
        animation: lpRingExpand 1.8s ease-out forwards;
      }
      @keyframes lpRingExpand { 0%{width:20px;height:20px;opacity:0.85;} 100%{width:200px;height:200px;opacity:0;} }

      /* ── TRAIL PARTICLES ─────────────────────────────── */
      .lp-trail-particle {
        position: fixed; z-index: 3; pointer-events: none; border-radius: 50%;
        animation: lpTrailFade var(--dur,1.2s) ease-out forwards;
      }
      @keyframes lpTrailFade {
        0%{opacity:0.9;transform:translate(var(--tx,0),var(--ty,0));}
        100%{opacity:0;transform:translate(var(--tx,0),calc(var(--ty,0) + 60px));}
      }

      /* ── SECTIONS ────────────────────────────────────── */
      .lp-section { position:relative; z-index:2; padding:100px 48px; }
      .lp-section-inner { max-width:1180px; margin:0 auto; }
      .lp-section-header { text-align:center; margin-bottom:56px; }
      .lp-section-label {
        display:inline-block; font-size:0.76rem; font-weight:700;
        letter-spacing:2px; text-transform:uppercase; color:#06b6d4; margin-bottom:14px;
      }
      .lp-section-title {
        font-size:clamp(1.9rem, 3.5vw, 3rem); font-weight:800; letter-spacing:-1px;
        color:#f1f5f9; margin-bottom:14px;
      }
      .lp-section-sub { font-size:1.05rem; color:rgba(148,163,184,0.82); max-width:580px; margin:0 auto; line-height:1.6; }

      /* ── FEATURE CARDS ───────────────────────────────── */
      .lp-tag-filters { display:flex; justify-content:center; gap:10px; margin-bottom:44px; flex-wrap:wrap; }
      .lp-tag-btn {
        padding:6px 18px; border-radius:999px; font-size:0.8rem; font-weight:600;
        border:1px solid rgba(255,255,255,0.1); background:transparent;
        color:rgba(148,163,184,0.8); cursor:pointer; transition:all 0.2s; font-family:inherit;
        -webkit-tap-highlight-color:transparent;
      }
      .lp-tag-btn.active      { background:rgba(6,182,212,0.12); border-color:rgba(6,182,212,0.4); color:#06b6d4; }
      .lp-tag-btn.active-cio  { background:rgba(139,92,246,0.12); border-color:rgba(139,92,246,0.4); color:#a78bfa; }
      .lp-tag-btn:hover       { background:rgba(6,182,212,0.08); border-color:rgba(6,182,212,0.3); color:#06b6d4; }

      .lp-features-grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(300px,1fr)); gap:18px; }
      .lp-feature-card {
        background:rgba(10,15,30,0.65); border:1px solid rgba(255,255,255,0.07);
        border-radius:14px; padding:26px; position:relative; overflow:hidden;
        transition:border-color 0.25s, transform 0.25s, box-shadow 0.25s;
      }
      .lp-feature-card::before {
        content:''; position:absolute; inset:0;
        background:linear-gradient(135deg, rgba(6,182,212,0.04) 0%, transparent 60%);
        opacity:0; transition:opacity 0.3s;
      }
      .lp-feature-card:hover { border-color:rgba(6,182,212,0.28); transform:translateY(-3px); box-shadow:0 12px 40px rgba(6,182,212,0.09); }
      .lp-feature-card:hover::before { opacity:1; }
      .lp-feature-icon { font-size:1.75rem; margin-bottom:12px; display:block; }
      .lp-feature-tag {
        position:absolute; top:14px; right:14px; font-size:0.65rem; font-weight:700;
        letter-spacing:1px; text-transform:uppercase; padding:3px 8px; border-radius:4px;
      }
      .lp-feature-tag-marketer { background:rgba(6,182,212,0.12); color:#06b6d4; border:1px solid rgba(6,182,212,0.22); }
      .lp-feature-tag-cio      { background:rgba(139,92,246,0.12); color:#a78bfa; border:1px solid rgba(139,92,246,0.22); }
      .lp-feature-title { font-size:1rem; font-weight:700; color:#f1f5f9; margin-bottom:9px; }
      .lp-feature-desc  { font-size:0.875rem; color:rgba(148,163,184,0.78); line-height:1.6; }

      /* ── DOCS ────────────────────────────────────────── */
      .lp-docs-placeholder {
        text-align:center; padding:60px 20px;
        border:1px dashed rgba(255,255,255,0.08); border-radius:16px;
        background:rgba(10,15,30,0.4);
      }
      .lp-docs-icon  { font-size:3rem; margin-bottom:18px; opacity:0.55; }
      .lp-docs-title { font-size:1.35rem; font-weight:700; color:#f1f5f9; margin-bottom:9px; }
      .lp-docs-sub   { font-size:0.95rem; color:rgba(148,163,184,0.65); }

      /* ── FOOTER CTA ──────────────────────────────────── */
      .lp-footer-cta { position:relative; z-index:2; padding:80px 48px 56px; text-align:center; border-top:1px solid rgba(255,255,255,0.05); }
      .lp-footer-cta-title { font-size:clamp(1.7rem,3vw,2.5rem); font-weight:800; letter-spacing:-1px; color:#f1f5f9; margin-bottom:12px; }
      .lp-footer-cta-sub   { font-size:1rem; color:rgba(148,163,184,0.72); margin-bottom:34px; }
      .lp-footer-bottom    { margin-top:44px; font-size:0.78rem; color:rgba(100,116,139,0.55); }

      /* ── LOGIN OVERLAY ───────────────────────────────── */
      .lp-overlay-bg {
        position:fixed; inset:0; z-index:200;
        background:rgba(0,0,0,0.72); backdrop-filter:blur(8px);
        display:flex; align-items:center; justify-content:center;
        animation:lpFadeIn 0.3s ease-out; padding:16px;
      }
      @keyframes lpFadeIn { from{opacity:0;} to{opacity:1;} }
      .lp-login-card {
        position:relative; background:rgba(8,12,26,0.96);
        border:1px solid rgba(6,182,212,0.22); border-radius:20px;
        padding:44px 40px 40px; width:100%; max-width:420px;
        box-shadow:0 0 80px rgba(6,182,212,0.1), 0 20px 60px rgba(0,0,0,0.6);
        animation:lpCardIn 0.35s cubic-bezier(0.34,1.56,0.64,1) both; overflow:hidden;
      }
      @keyframes lpCardIn { from{opacity:0;transform:scale(0.88) translateY(20px);} to{opacity:1;transform:none;} }
      .lp-login-close {
        position:absolute; top:14px; right:16px;
        background:rgba(255,255,255,0.06); border:none; border-radius:6px;
        color:rgba(148,163,184,0.6); cursor:pointer; font-size:0.95rem;
        width:28px; height:28px; display:flex; align-items:center; justify-content:center;
        transition:all 0.2s; font-family:inherit;
      }
      .lp-login-close:hover { background:rgba(255,255,255,0.12); color:#e2e8f0; }
      .lp-sparkle {
        position:absolute; pointer-events:none; border-radius:50%;
        background:radial-gradient(circle, rgba(6,182,212,0.9), rgba(139,92,246,0.6), transparent 70%);
        animation:lpSparkleAnim var(--dur,2s) ease-in-out infinite;
      }
      @keyframes lpSparkleAnim { 0%,100%{opacity:0;transform:scale(0);} 50%{opacity:0.7;transform:scale(1);} }
      .lp-login-icon-wrap { text-align:center; margin-bottom:12px; }
      .lp-login-icon {
        width:52px; height:52px; border-radius:14px; margin:0 auto;
        background:linear-gradient(135deg, rgba(6,182,212,0.2), rgba(139,92,246,0.2));
        border:1px solid rgba(6,182,212,0.3);
        display:flex; align-items:center; justify-content:center; font-size:1.5rem;
        box-shadow:0 0 30px rgba(6,182,212,0.18);
      }
      .lp-login-title { font-size:1.5rem; font-weight:800; color:#f1f5f9; text-align:center; margin-bottom:6px; }
      .lp-login-sub   { font-size:0.88rem; color:rgba(148,163,184,0.68); text-align:center; margin-bottom:28px; }
      .lp-login-form  { display:flex; flex-direction:column; gap:15px; position:relative; z-index:1; }
      .lp-form-group  { display:flex; flex-direction:column; gap:7px; }
      .lp-form-group label { font-size:0.8rem; font-weight:600; color:rgba(148,163,184,0.82); letter-spacing:0.3px; }
      .lp-form-group input {
        background:rgba(255,255,255,0.05); border:1px solid rgba(255,255,255,0.1);
        border-radius:9px; padding:10px 14px; color:#f1f5f9;
        font-size:0.92rem; font-family:inherit; outline:none;
        transition:border-color 0.2s, box-shadow 0.2s;
      }
      .lp-form-group input:focus { border-color:rgba(6,182,212,0.5); box-shadow:0 0 0 3px rgba(6,182,212,0.1); }
      .lp-form-group input::placeholder { color:rgba(100,116,139,0.55); }
      .lp-login-submit {
        margin-top:6px; padding:12px; border:none; border-radius:10px;
        background:linear-gradient(135deg, #06b6d4, #8b5cf6);
        color:#fff; font-size:0.95rem; font-weight:700; font-family:inherit;
        cursor:pointer; transition:opacity 0.2s, transform 0.2s;
        box-shadow:0 4px 20px rgba(6,182,212,0.28);
      }
      .lp-login-submit:hover:not(:disabled) { opacity:0.9; transform:translateY(-1px); }
      .lp-login-submit:disabled { opacity:0.55; cursor:not-allowed; }
      .lp-login-spinner { display:flex; align-items:center; justify-content:center; gap:10px; }
      .lp-spinner-ring {
        width:14px; height:14px; border:2px solid rgba(255,255,255,0.3);
        border-top-color:#fff; border-radius:50%; flex-shrink:0;
        animation:lpSpin 0.7s linear infinite;
      }
      @keyframes lpSpin { 100%{transform:rotate(360deg);} }

      /* ── RESPONSIVE ──────────────────────────────────── */
      @media (max-width: 1024px) {
        .lp-hero-container { flex-direction:column-reverse; gap:32px; }
        .lp-hero-content   { align-items:center; text-align:center; max-width:100%; }
        .lp-hero-sub       { text-align:center; }
        .lp-hero-visual    { height:420px; width:100%; }
        .lp-robot-scaler   { transform:scale(0.8); }
        .lp-hero-section   { padding-top:88px; padding-bottom:32px; min-height:auto; }
        .lp-halo-1         { width:380px; height:380px; }
        .lp-halo-2         { width:330px; height:330px; }
      }
      @media (max-width: 768px) {
        .lp-nav            { padding:14px 20px; }
        .lp-nav-links      { display:none; }
        .lp-hero-section   { padding:76px 20px 24px; }
        .lp-section        { padding:64px 20px; }
        .lp-footer-cta     { padding:60px 20px 44px; }
        .lp-robot-scaler   { transform:scale(0.62); }
        .lp-hero-visual    { height:320px; }
        .lp-halo-1         { width:300px; height:300px; }
        .lp-halo-2         { width:260px; height:260px; }
        .lp-features-grid  { grid-template-columns:1fr; }
        .lp-login-card     { padding:36px 20px 30px; }
        .lp-gradient-btn   { padding:14px 32px; font-size:0.95rem; }
      }
      @media (max-width: 480px) {
        .lp-hero-title     { letter-spacing:-1px; }
        .lp-robot-scaler   { transform:scale(0.52); }
        .lp-hero-visual    { height:270px; }
      }
    `;
    document.head.appendChild(style);
    return () => { document.getElementById('lp-robot-styles')?.remove(); };
  }, []);

  // ── Mouse tracking → spotlight + robot rigging ────────────────────────────
  useEffect(() => {
    let targetX = window.innerWidth / 2;
    let targetY = window.innerHeight / 2;
    let currX = targetX;
    let currY = targetY;

    const handleMouseMove = (e) => {
      if (!isTakingOffRef.current) { targetX = e.clientX; targetY = e.clientY; }
    };
    const handleTouchMove = (e) => {
      if (!isTakingOffRef.current && e.touches[0]) {
        targetX = e.touches[0].clientX; targetY = e.touches[0].clientY;
      }
    };
    window.addEventListener('mousemove', handleMouseMove);
    window.addEventListener('touchmove', handleTouchMove, { passive: true });

    function raf() {
      currX += (targetX - currX) * 0.1;
      currY += (targetY - currY) * 0.1;

      document.documentElement.style.setProperty('--lp-mx', `${currX}px`);
      document.documentElement.style.setProperty('--lp-my', `${currY}px`);

      if (!isTakingOffRef.current) {
        const nx = (currX / Math.max(1, window.innerWidth))  * 2 - 1;
        const ny = (currY / Math.max(1, window.innerHeight)) * 2 - 1;

        if (headRef.current)        headRef.current.style.transform        = `rotateX(${ny * -25}deg) rotateY(${nx * 35}deg)`;
        if (torsoRef.current)       torsoRef.current.style.transform       = `rotateX(${ny * -10}deg) rotateY(${nx * 15}deg)`;
        if (eyeContainerRef.current) eyeContainerRef.current.style.transform = `translate(${nx * 40}px, ${ny * 15}px)`;
        if (armLeftRef.current) {
          armLeftRef.current.style.marginLeft = `calc(-130px + ${nx * -20}px)`;
          armLeftRef.current.style.top        = `calc(215px + ${ny * -10}px)`;
        }
        if (armRightRef.current) {
          armRightRef.current.style.marginLeft = `calc(85px + ${nx * 20}px)`;
          armRightRef.current.style.top        = `calc(215px + ${ny * -10}px)`;
        }
      }
      robotAnimRafRef.current = requestAnimationFrame(raf);
    }
    robotAnimRafRef.current = requestAnimationFrame(raf);

    return () => {
      cancelAnimationFrame(robotAnimRafRef.current);
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('touchmove', handleTouchMove);
    };
  }, []);

  // ── Pulse rings from core ──────────────────────────────────────────────────
  useEffect(() => {
    pulseIntervalRef.current = setInterval(() => {
      if (isTakingOffRef.current || !coreLightRef.current) return;
      const rect = coreLightRef.current.getBoundingClientRect();
      const cx = rect.left + rect.width / 2;
      const cy = rect.top + rect.height / 2;
      const id = ringIdRef.current++;
      setPulseRings(prev => [...prev.slice(-6), { id, cx, cy }]);
      setTimeout(() => setPulseRings(prev => prev.filter(r => r.id !== id)), 1900);
    }, 2400);
    return () => clearInterval(pulseIntervalRef.current);
  }, []);

  // ── Takeoff ────────────────────────────────────────────────────────────────
  const triggerTakeoff = useCallback(() => {
    if (isTakingOffRef.current) return;
    isTakingOffRef.current = true;
    setBtnDisabled(true);
    setBtnText('Initializing...');

    const assembly = assemblyRef.current;
    const eyes = assembly?.querySelectorAll('.lp-robot-eye');
    const coreLight = coreLightRef.current;

    eyes?.forEach(eye => {
      eye.style.height = '10px';
      eye.style.background = '#fff';
      eye.style.boxShadow = '0 0 30px #fff, 0 0 80px #06b6d4, 0 0 150px #06b6d4';
    });
    if (coreLight) {
      coreLight.style.animation = 'none';
      coreLight.style.transform = 'scale(1.9)';
      coreLight.style.background = '#fff';
      coreLight.style.boxShadow = '0 0 30px #fff, 0 0 60px #06b6d4, 0 0 100px #8b5cf6';
    }

    // Phase 1: 300ms — eyes glow, core charges (already happening above)
    // Phase 2: 300ms → 900ms — shake + warm up engines (600ms of shaking feels right)
    setTimeout(() => {
      assembly?.classList.add('lp-shaking', 'lp-warming-up');
    }, 300);

    // Phase 3: 900ms — ignite + launch (2.2s flight animation)
    setTimeout(() => {
      assembly?.classList.remove('lp-shaking', 'lp-warming-up');
      assembly?.classList.add('lp-ignited', 'lp-flying');
      if (floorShadowRef.current) floorShadowRef.current.style.opacity = '0';

      // Shockwave fires when robot breaks free (~40% into animation = ~880ms after launch)
      setTimeout(() => {
        if (shockwaveRef.current) shockwaveRef.current.classList.add('lp-shockwave-go');
      }, 880);

      // Trail particles — spawn over first 1.5s of flight
      if (assembly) {
        const rect = assembly.getBoundingClientRect();
        const cx = rect.left + rect.width / 2;
        const cy = rect.top + rect.height / 2;
        for (let i = 0; i < 55; i++) {
          setTimeout(() => {
            const pid = particleIdRef.current++;
            const px  = cx + (Math.random() - 0.5) * 70;
            const py  = cy + i * -6 + (Math.random() - 0.5) * 40;
            const size = 2 + Math.random() * 8;
            const isBlue = Math.random() > 0.4;
            const dur  = 0.8 + Math.random() * 1.0;
            const tx   = (Math.random() - 0.5) * 100;
            const ty   = -20 - Math.random() * 60;
            setTrailParticles(prev => [...prev.slice(-60), { id: pid, px, py, size, isBlue, dur, tx, ty }]);
            setTimeout(() => setTrailParticles(prev => prev.filter(p => p.id !== pid)), dur * 1000 + 300);
          }, i * 28);
        }
      }

      // Login appears after robot is fully gone (2.2s flight + small buffer)
      setTimeout(() => {
        setBtnText('Agent Active');
        setTimeout(() => { setShowLogin(true); resetRobot(); }, 500);
      }, 2400);
    }, 900);
  }, []);

  const resetRobot = useCallback(() => {
    const assembly = assemblyRef.current;
    assembly?.classList.remove('lp-flying', 'lp-ignited');
    if (assembly) assembly.style.animation = '';
    shockwaveRef.current?.classList.remove('lp-shockwave-go');
    if (floorShadowRef.current) floorShadowRef.current.style.opacity = '';
    assembly?.querySelectorAll('.lp-robot-eye').forEach(e => {
      e.style.height = ''; e.style.background = ''; e.style.boxShadow = '';
    });
    if (coreLightRef.current) {
      coreLightRef.current.style.animation = '';
      coreLightRef.current.style.transform = '';
      coreLightRef.current.style.background = '';
      coreLightRef.current.style.boxShadow = '';
    }
    isTakingOffRef.current = false;
    setBtnText('Initialize Agent');
    setBtnDisabled(false);
  }, []);

  const scrollToSection = (id) => {
    setActiveNav(id);
    document.getElementById(id)?.scrollIntoView({ behavior: 'smooth' });
  };

  const filteredFeatures = filterTag === 'All' ? FEATURES : FEATURES.filter(f => f.tag === filterTag);

  return (
    <div className="lp-root">
      {/* Space background */}
      <SpaceCanvas />

      {/* Spotlight */}
      <div className="lp-spotlight-fx" />

      {/* Pulse rings */}
      {pulseRings.map(r => (
        <div key={r.id} className="lp-pulse-ring" style={{ left: r.cx, top: r.cy }} />
      ))}

      {/* Trail particles */}
      {trailParticles.map(p => (
        <div
          key={p.id}
          className="lp-trail-particle"
          style={{
            left: p.px, top: p.py, width: p.size, height: p.size,
            background: p.isBlue ? 'rgba(6,182,212,0.9)' : 'rgba(139,92,246,0.9)',
            boxShadow: p.isBlue ? `0 0 ${p.size * 2}px rgba(6,182,212,0.5)` : `0 0 ${p.size * 2}px rgba(139,92,246,0.5)`,
            '--dur': `${p.dur}s`, '--tx': `${p.tx}px`, '--ty': `${p.ty}px`,
          }}
        />
      ))}

      {/* Login overlay */}
      {showLogin && <InlineLogin onClose={() => setShowLogin(false)} />}

      {/* ── NAV ── */}
      <nav className="lp-nav">
        <div className="lp-logo" onClick={() => scrollToSection('home')}>
          <div className="lp-logo-mark" />
          Vantage
        </div>
        <div className="lp-nav-links">
          {['home', 'about', 'docs'].map(sec => (
            <button
              key={sec}
              className={`lp-nav-link${activeNav === sec ? ' active' : ''}`}
              onClick={() => scrollToSection(sec)}
            >
              {sec === 'docs' ? 'Documentation' : sec.charAt(0).toUpperCase() + sec.slice(1)}
            </button>
          ))}
        </div>
        {/* Right side intentionally empty — no toggle, no sign-in */}
        <div />
      </nav>

      {/* ── HERO ── */}
      <section id="home" className="lp-hero-section">
        <div className="lp-hero-container">

          {/* Content */}
          <div className="lp-hero-content">
            <div className="lp-badge">
              <div className="lp-badge-dot" />
              Omnichannel AI Agent · v2.6
            </div>

            <h1 className="lp-hero-title">
              Omnichannel AI.<br />
              <span className="lp-title-gradient">Engineered to convert.</span>
            </h1>

            <p className="lp-hero-sub">
              Transform historical performance data into high-converting Ad Copy and
              personalized CRM Marketing Calendars — in seconds. Powered by Claude AI
              and real-time Firestore RAG.
            </p>

            <div className="lp-cta-wrap">
              <button className="lp-gradient-btn" onClick={triggerTakeoff} disabled={btnDisabled}>
                <span>{btnText}</span>
              </button>
            </div>
          </div>

          {/* Robot */}
          <div className="lp-hero-visual">
            <div className="lp-halo lp-halo-1" />
            <div className="lp-halo lp-halo-2" />

            <div className="lp-robot-scaler">
              <div className="lp-robot-assembly" ref={assemblyRef}>
                {/* Head */}
                <div className="lp-robot-head lp-glossy" ref={headRef}>
                  <div className="lp-robot-visor">
                    <div className="lp-eye-container" ref={eyeContainerRef}>
                      <div className="lp-robot-eye" />
                      <div className="lp-robot-eye" />
                    </div>
                  </div>
                </div>
                {/* Neck */}
                <div className="lp-robot-neck" />
                {/* Torso */}
                <div className="lp-robot-torso lp-glossy" ref={torsoRef}>
                  <div className="lp-thruster lp-torso-thruster">
                    <div className="lp-flame-plume" />
                    <div className="lp-flame-core" />
                  </div>
                  <div className="lp-robot-core">
                    <div className="lp-robot-core-light" ref={coreLightRef} />
                  </div>
                </div>
                {/* Arms */}
                <div className="lp-robot-arm lp-glossy lp-arm-left" ref={armLeftRef}>
                  <div className="lp-thruster">
                    <div className="lp-flame-plume" />
                    <div className="lp-flame-core" />
                  </div>
                </div>
                <div className="lp-robot-arm lp-glossy lp-arm-right" ref={armRightRef}>
                  <div className="lp-thruster">
                    <div className="lp-flame-plume" />
                    <div className="lp-flame-core" />
                  </div>
                </div>
              </div>
            </div>

            <div className="lp-floor-shadow" ref={floorShadowRef} />
            <div className="lp-shockwave" ref={shockwaveRef} />
          </div>
        </div>
      </section>

      {/* ── ABOUT / FEATURES ── */}
      <section id="about" className="lp-section">
        <div className="lp-section-inner">
          <div className="lp-section-header">
            <div className="lp-section-label">Platform Capabilities</div>
            <h2 className="lp-section-title">Built for Marketers &amp; Engineers</h2>
            <p className="lp-section-sub">
              A complete AI marketing stack — from brief to launch — with the
              enterprise-grade architecture your team can trust.
            </p>
          </div>

          <div className="lp-tag-filters">
            {['All', 'Marketer', 'CIO'].map(tag => (
              <button
                key={tag}
                className={`lp-tag-btn${
                  filterTag === tag ? (tag === 'CIO' ? ' active-cio' : ' active') : ''
                }`}
                onClick={() => setFilterTag(tag)}
              >
                {tag === 'All' ? '🔮 All Features' : tag === 'Marketer' ? '🎯 Marketer View' : '⚙️ CIO View'}
              </button>
            ))}
          </div>

          <div className="lp-features-grid">
            {filteredFeatures.map(f => (
              <div key={f.title} className="lp-feature-card">
                <span className={`lp-feature-tag ${f.tag === 'CIO' ? 'lp-feature-tag-cio' : 'lp-feature-tag-marketer'}`}>
                  {f.tag}
                </span>
                <span className="lp-feature-icon">{f.icon}</span>
                <div className="lp-feature-title">{f.title}</div>
                <div className="lp-feature-desc">{f.desc}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── DOCS ── */}
      <section id="docs" className="lp-section">
        <div className="lp-section-inner">
          <div className="lp-section-header">
            <div className="lp-section-label">Documentation</div>
            <h2 className="lp-section-title">Guides &amp; API Reference</h2>
          </div>
          <div className="lp-docs-placeholder">
            <div className="lp-docs-icon">📚</div>
            <div className="lp-docs-title">Coming Soon</div>
            <div className="lp-docs-sub">
              Comprehensive setup guides, API references, RAG engine docs,
              and CRM integration playbooks are in progress.
            </div>
          </div>
        </div>
      </section>

      {/* ── FOOTER CTA ── */}
      <section className="lp-footer-cta">
        <h2 className="lp-footer-cta-title">
          Ready to <span className="lp-title-gradient">transform</span> your marketing?
        </h2>
        <p className="lp-footer-cta-sub">
          Join teams shipping better campaigns, faster — with Vantage GenAI.
        </p>
        <button className="lp-gradient-btn" onClick={triggerTakeoff} disabled={btnDisabled}>
          <span>Get Started Free</span>
        </button>
        <div className="lp-footer-bottom">
          © 2025 Vantage GenAI · Powered by Anthropic Claude · Built on GCP
        </div>
      </section>
    </div>
  );
}
