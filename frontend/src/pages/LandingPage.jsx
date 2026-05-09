import { useEffect, useRef, useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth';
import { login } from '../services/api';
import toast from 'react-hot-toast';
import { APP_VERSION } from '../version';


// ─── SPACE CANVAS (stars + shooting stars, mouse-reactive twinkling) ──────────
function SpaceCanvas({ isDark = true }) {
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
        hue: isDark
          ? (Math.random() > 0.85 ? 'rgba(200,220,255,' : Math.random() > 0.5 ? 'rgba(255,255,255,' : 'rgba(180,200,255,')
          : (Math.random() > 0.85 ? 'rgba(15,23,42,' : Math.random() > 0.5 ? 'rgba(30,41,59,' : 'rgba(51,65,85,'),
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

      // Background gradient — dark space or light sky
      const bg = ctx.createLinearGradient(0, 0, 0, canvas.height);
      if (isDark) {
        bg.addColorStop(0, '#02020e');
        bg.addColorStop(0.45, '#060618');
        bg.addColorStop(1, '#030510');
      } else {
        bg.addColorStop(0, '#ffffff');
        bg.addColorStop(0.45, '#f8fafc');
        bg.addColorStop(1, '#f1f5f9');
      }
      ctx.fillStyle = bg;
      ctx.fillRect(0, 0, canvas.width, canvas.height);

      // Nebula blobs
      const nebulas = isDark ? [
        { cx: 0.18, cy: 0.28, r: 340, col: '37,99,235',   a: 0.06  },
        { cx: 0.82, cy: 0.55, r: 280, col: '139,92,246',  a: 0.07  },
        { cx: 0.5,  cy: 0.88, r: 220, col: '236,72,153',  a: 0.038 },
        { cx: 0.65, cy: 0.12, r: 190, col: '6,182,212',   a: 0.032 },
      ] : [
        { cx: 0.18, cy: 0.28, r: 340, col: '59,130,246',  a: 0.04  },
        { cx: 0.82, cy: 0.55, r: 280, col: '139,92,246',  a: 0.035 },
        { cx: 0.5,  cy: 0.88, r: 220, col: '236,72,153',  a: 0.025 },
        { cx: 0.65, cy: 0.12, r: 190, col: '6,182,212',   a: 0.02  },
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
          ctx.strokeStyle = isDark ? `rgba(255,255,255,${hoverFactor * 0.55})` : `rgba(15,23,42,${hoverFactor * 0.4})`;
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
        tail.addColorStop(0, isDark ? `rgba(255,255,255,${ss.alpha})` : `rgba(15,23,42,${ss.alpha * 0.5})`);
        tail.addColorStop(0.4, isDark ? `rgba(180,210,255,${ss.alpha * 0.6})` : `rgba(51,65,85,${ss.alpha * 0.3})`);
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
  }, [isDark]);

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
  const [isDark, setIsDark] = useState(true);
  const [pulseRings, setPulseRings] = useState([]);
  const [trailParticles, setTrailParticles] = useState([]);

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

  // ── IntersectionObserver for scroll-based nav highlighting ─────────────────
  useEffect(() => {
    const sectionIds = ['home', 'about', 'docs'];
    const observerOptions = { root: null, rootMargin: '-40% 0px -40% 0px', threshold: 0 };
    const observer = new IntersectionObserver((entries) => {
      entries.forEach(entry => {
        if (entry.isIntersecting) {
          setActiveNav(entry.target.id);
        }
      });
    }, observerOptions);
    sectionIds.forEach(id => {
      const el = document.getElementById(id);
      if (el) observer.observe(el);
    });
    return () => observer.disconnect();
  }, []);

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
        overflow-y: auto;
        scrollbar-width: thin;
        scrollbar-color: rgba(37,99,235,0.3) transparent;
      }
      .lp-root::-webkit-scrollbar { width: 4px; }
      .lp-root::-webkit-scrollbar-thumb { background: rgba(37,99,235,0.35); border-radius: 3px; }

      /* ── THEME TOGGLE ─────────────────────────────────── */
      .lp-theme-toggle {
        background: rgba(255,255,255,0.08);
        border: 1px solid rgba(255,255,255,0.12);
        border-radius: 9999px;
        width: 40px; height: 40px;
        display: flex; align-items: center; justify-content: center;
        cursor: pointer; font-size: 1.15rem;
        transition: background 0.2s, border-color 0.2s, transform 0.2s;
        padding: 0; flex-shrink: 0;
      }
      .lp-theme-toggle:hover { background: rgba(255,255,255,0.14); transform: scale(1.08); }

      /* ── LIGHT MODE OVERRIDES ─────────────────────────── */
      .lp-light-mode { color: #334155; }
      .lp-light-mode .lp-theme-toggle {
        background: rgba(15,23,42,0.06);
        border-color: rgba(15,23,42,0.12);
      }
      .lp-light-mode .lp-theme-toggle:hover { background: rgba(15,23,42,0.1); }

      /* Nav */
      .lp-light-mode .lp-nav {
        background: rgba(255,255,255,0.85);
        border-bottom: 1px solid rgba(15,23,42,0.08);
      }
      .lp-light-mode .lp-logo { color: #0f172a; }
      .lp-light-mode .lp-nav-link { color: rgba(51,65,85,0.6); }
      .lp-light-mode .lp-nav-link:hover,
      .lp-light-mode .lp-nav-link.active { color: #0891b2; }

      /* Hero text */
      .lp-light-mode .lp-hero-title { color: #0f172a; }
      .lp-light-mode .lp-hero-sub { color: #475569; }
      .lp-light-mode .lp-badge {
        background: rgba(139,92,246,0.08);
        border-color: rgba(139,92,246,0.2);
        color: #7c3aed;
      }
      .lp-light-mode .lp-badge-dot {
        background: #7c3aed;
        box-shadow: 0 0 8px rgba(124,58,237,0.5);
      }

      /* CTA button dark inner in light mode */
      .lp-light-mode .lp-gradient-btn::after { background: #0f172a; }

      /* Spotlight */
      .lp-light-mode .lp-spotlight-fx {
        background: radial-gradient(600px circle at var(--lp-mx,50%) var(--lp-my,50%), rgba(6,182,212,0.03), transparent 40%);
      }

      /* Robot — darker metallic in light mode */
      .lp-light-mode .lp-glossy {
        background: linear-gradient(145deg, #94a3b8 0%, #64748b 10%, #475569 25%, #334155 45%, #1e293b 65%, #0f172a 100%);
        box-shadow:
          inset 8px 16px 32px rgba(255,255,255,0.22),
          inset 2px 4px 10px rgba(150,200,255,0.08),
          inset -8px -10px 28px rgba(0,0,0,0.6),
          0 0 0 1.5px rgba(6,182,212,0.4),
          0 0 18px rgba(6,182,212,0.15),
          0 0 45px rgba(6,182,212,0.08),
          0 0 60px rgba(139,92,246,0.05),
          0 24px 50px rgba(0,0,0,0.25);
        border-color: rgba(100,116,139,0.3);
      }
      .lp-light-mode .lp-robot-visor {
        border-color: rgba(6,182,212,0.3);
      }
      .lp-light-mode .lp-halo-1 { border-color: rgba(6,182,212,0.2); }
      .lp-light-mode .lp-halo-2 {
        border-color: rgba(139,92,246,0.05);
        border-top-color: rgba(139,92,246,0.35);
        box-shadow: 0 0 25px rgba(139,92,246,0.04);
      }

      /* Section text */
      .lp-light-mode .lp-section-title { color: #0f172a; }
      .lp-light-mode .lp-section-sub { color: #475569; }
      .lp-light-mode .lp-about-eyebrow {
        color: #7c3aed;
        background: rgba(139,92,246,0.06);
        border-color: rgba(139,92,246,0.15);
      }

      /* Bento cards */
      .lp-light-mode .lp-bento-card {
        background: rgba(255,255,255,0.85);
        border-color: rgba(15,23,42,0.08);
        backdrop-filter: blur(16px);
      }
      .lp-light-mode .lp-bento-card:hover { border-color: rgba(6,182,212,0.2); box-shadow: 0 16px 40px rgba(6,182,212,0.06); }
      .lp-light-mode .lp-bento-card:nth-child(even):hover { border-color: rgba(139,92,246,0.2); box-shadow: 0 16px 40px rgba(139,92,246,0.06); }
      .lp-light-mode .lp-bento-card h3 { color: #0f172a; }
      .lp-light-mode .lp-bento-card-sub { color: #475569; }
      .lp-light-mode .lp-bento-feature-title { color: #1e293b; }
      .lp-light-mode .lp-bento-feature-desc { color: #64748b; }

      /* Docs section */
      .lp-light-mode .lp-docs-eyebrow {
        color: #0891b2;
        background: rgba(6,182,212,0.06);
        border-color: rgba(6,182,212,0.15);
      }
      .lp-light-mode .lp-arch-flow {
        background: rgba(255,255,255,0.85);
        border-color: rgba(15,23,42,0.08);
      }
      .lp-light-mode .lp-arch-title { color: rgba(51,65,85,0.5); }
      .lp-light-mode .lp-arch-node {
        background: rgba(248,250,252,0.95);
        border-color: rgba(15,23,42,0.1);
        color: #334155;
      }
      .lp-light-mode .lp-arch-node.lp-arch-primary { background: rgba(6,182,212,0.06); border-color: rgba(6,182,212,0.2); color: #0891b2; }
      .lp-light-mode .lp-arch-node.lp-arch-ai { background: rgba(139,92,246,0.06); border-color: rgba(139,92,246,0.2); color: #7c3aed; }
      .lp-light-mode .lp-arch-node.lp-arch-data { background: rgba(6,182,212,0.04); border-color: rgba(6,182,212,0.15); color: #0e7490; }
      .lp-light-mode .lp-arch-line-v { background: rgba(15,23,42,0.08); }
      .lp-light-mode .lp-arch-split::before {
        border-color: rgba(15,23,42,0.08);
      }
      .lp-light-mode .lp-docs-card {
        background: rgba(255,255,255,0.85);
        border-color: rgba(15,23,42,0.08);
      }
      .lp-light-mode .lp-docs-card:hover { border-color: rgba(15,23,42,0.14); box-shadow: 0 16px 40px rgba(0,0,0,0.06); }
      .lp-light-mode .lp-docs-card h3 { color: #0f172a; }
      .lp-light-mode .lp-docs-card-sub { color: #475569; }
      .lp-light-mode .lp-docs-feature-mono { color: #1e293b; }
      .lp-light-mode .lp-docs-feature-desc { color: #64748b; }
      .lp-light-mode .lp-docs-feature-bullet {
        background: rgba(15,23,42,0.04);
        color: rgba(51,65,85,0.5);
      }

      /* Footer */
      .lp-light-mode .lp-footer-cta { border-top-color: rgba(15,23,42,0.06); }
      .lp-light-mode .lp-footer-cta-title { color: #0f172a; }
      .lp-light-mode .lp-footer-cta-sub { color: #475569; }
      .lp-light-mode .lp-footer-bottom { color: rgba(100,116,139,0.6); }

      /* Pulse ring light mode */
      .lp-light-mode .lp-pulse-ring { border-color: rgba(139,92,246,0.3); }

      /* Login overlay light mode */
      .lp-light-mode .lp-login-card {
        background: rgba(255,255,255,0.97);
        border-color: rgba(6,182,212,0.18);
        box-shadow: 0 0 80px rgba(6,182,212,0.06), 0 20px 60px rgba(0,0,0,0.12);
      }
      .lp-light-mode .lp-login-title { color: #0f172a; }
      .lp-light-mode .lp-login-sub { color: #475569; }
      .lp-light-mode .lp-form-group label { color: #475569; }
      .lp-light-mode .lp-form-group input {
        background: rgba(15,23,42,0.04);
        border-color: rgba(15,23,42,0.12);
        color: #0f172a;
      }
      .lp-light-mode .lp-form-group input::placeholder { color: rgba(100,116,139,0.5); }
      .lp-light-mode .lp-login-close {
        background: rgba(15,23,42,0.06);
        color: rgba(51,65,85,0.5);
      }
      .lp-light-mode .lp-login-close:hover { background: rgba(15,23,42,0.1); color: #0f172a; }

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
        padding: 80px 48px 32px;
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
        height: 500px; perspective: 1200px;
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

      /* ── ABOUT EYEBROW ───────────────────────────────── */
      .lp-about-eyebrow {
        display:inline-block; color:#a78bfa; font-size:0.8rem; font-weight:700;
        letter-spacing:1px; text-transform:uppercase; margin-bottom:14px;
        background:rgba(139,92,246,0.1); padding:5px 14px; border-radius:100px;
        border:1px solid rgba(139,92,246,0.2);
      }

      /* ── BENTO GRID (About) ──────────────────────────── */
      .lp-bento-grid { display:grid; grid-template-columns:repeat(2,1fr); gap:20px; }
      .lp-bento-card {
        background:rgba(8,14,32,0.75); border:1px solid rgba(255,255,255,0.07);
        border-radius:20px; padding:36px; backdrop-filter:blur(16px);
        transition:transform 0.3s ease, box-shadow 0.3s ease, border-color 0.3s ease;
        display:flex; flex-direction:column;
      }
      .lp-bento-card:hover { transform:translateY(-4px); border-color:rgba(6,182,212,0.25); box-shadow:0 16px 40px rgba(6,182,212,0.08); }
      .lp-bento-card:nth-child(even):hover { border-color:rgba(139,92,246,0.25); box-shadow:0 16px 40px rgba(139,92,246,0.08); }
      .lp-bento-card-icon {
        width:52px; height:52px; border-radius:14px;
        display:flex; align-items:center; justify-content:center; margin-bottom:20px;
      }
      .lp-bento-icon-create { background:linear-gradient(135deg,rgba(6,182,212,0.15),rgba(6,182,212,0.05)); color:#06b6d4; border:1px solid rgba(6,182,212,0.2); }
      .lp-bento-icon-target { background:linear-gradient(135deg,rgba(139,92,246,0.15),rgba(139,92,246,0.05)); color:#a78bfa; border:1px solid rgba(139,92,246,0.2); }
      .lp-bento-icon-plan   { background:linear-gradient(135deg,rgba(6,182,212,0.12),rgba(8,145,178,0.05)); color:#22d3ee; border:1px solid rgba(6,182,212,0.18); }
      .lp-bento-icon-manage { background:linear-gradient(135deg,rgba(100,116,139,0.15),rgba(71,85,105,0.05)); color:#94a3b8; border:1px solid rgba(100,116,139,0.2); }
      .lp-bento-card h3 { font-size:1.45rem; font-weight:700; letter-spacing:-0.5px; color:#f1f5f9; margin-bottom:8px; }
      .lp-bento-card-sub { font-size:0.925rem; color:rgba(148,163,184,0.7); margin-bottom:28px; line-height:1.5; }
      .lp-bento-feature-list { list-style:none; display:flex; flex-direction:column; gap:14px; margin-top:auto; }
      .lp-bento-feature-item { display:flex; align-items:flex-start; gap:12px; }
      .lp-bento-feature-dot {
        flex-shrink:0; width:22px; height:22px; border-radius:50%;
        background:rgba(6,182,212,0.1); color:#06b6d4;
        display:flex; align-items:center; justify-content:center; margin-top:2px;
      }
      .lp-bento-card:nth-child(even) .lp-bento-feature-dot { background:rgba(139,92,246,0.1); color:#a78bfa; }
      .lp-bento-feature-text { display:flex; flex-direction:column; }
      .lp-bento-feature-title { font-weight:600; color:#e2e8f0; font-size:0.925rem; margin-bottom:3px; }
      .lp-bento-feature-desc  { font-size:0.845rem; color:rgba(148,163,184,0.68); line-height:1.5; }

      /* ── DOCS EYEBROW ─────────────────────────────────── */
      .lp-docs-eyebrow {
        display:inline-flex; align-items:center; gap:8px;
        color:#06b6d4; font-family:ui-monospace,'SFMono-Regular',Consolas,monospace;
        font-size:0.8rem; font-weight:500; letter-spacing:0.5px; margin-bottom:14px;
        background:rgba(6,182,212,0.08); padding:5px 14px; border-radius:100px;
        border:1px solid rgba(6,182,212,0.2);
      }
      .lp-docs-status-dot {
        width:7px; height:7px; background:#10b981; border-radius:50%;
        box-shadow:0 0 8px rgba(16,185,129,0.5); animation:lpStatusPulse 2s infinite;
      }
      @keyframes lpStatusPulse { 0%{box-shadow:0 0 0 0 rgba(16,185,129,0.4);} 70%{box-shadow:0 0 0 8px rgba(16,185,129,0);} 100%{box-shadow:0 0 0 0 rgba(16,185,129,0);} }

      /* ── ARCHITECTURE FLOW ───────────────────────────── */
      .lp-arch-flow {
        background:rgba(8,14,32,0.75); border:1px solid rgba(255,255,255,0.07);
        border-radius:20px; padding:36px 36px 40px; backdrop-filter:blur(16px);
        margin-bottom:20px; overflow-x:auto;
      }
      .lp-arch-title {
        font-size:0.72rem; font-weight:700; letter-spacing:2px; text-transform:uppercase;
        color:rgba(148,163,184,0.42); margin-bottom:32px;
        font-family:ui-monospace,'SFMono-Regular',Consolas,monospace;
      }
      .lp-arch-container { display:flex; flex-direction:column; align-items:center; min-width:480px; }
      .lp-arch-row { display:flex; justify-content:center; gap:20px; width:100%; flex-wrap:wrap; }
      .lp-arch-node {
        background:rgba(10,16,36,0.9); border:1px solid rgba(255,255,255,0.1);
        padding:13px 20px; border-radius:12px; font-weight:600; font-size:0.875rem; color:#cbd5e1;
        display:flex; align-items:center; gap:9px; min-width:195px; justify-content:center;
      }
      .lp-arch-node.lp-arch-primary { background:rgba(6,182,212,0.1); border-color:rgba(6,182,212,0.3); color:#67e8f9; box-shadow:0 0 18px rgba(6,182,212,0.07); }
      .lp-arch-node.lp-arch-ai      { background:rgba(139,92,246,0.1); border-color:rgba(139,92,246,0.3); color:#c4b5fd; }
      .lp-arch-node.lp-arch-data    { background:rgba(6,182,212,0.06); border-color:rgba(6,182,212,0.18); color:#7dd3fc; }
      .lp-arch-line-v { width:2px; height:24px; background:rgba(255,255,255,0.08); margin:0 auto; }
      .lp-arch-split { width:100%; height:24px; position:relative; display:flex; justify-content:center; }
      .lp-arch-split::before {
        content:''; position:absolute; top:0; left:50%; transform:translateX(-50%);
        width:460px; height:24px;
        border-top:2px solid rgba(255,255,255,0.08);
        border-left:2px solid rgba(255,255,255,0.08);
        border-right:2px solid rgba(255,255,255,0.08);
        border-radius:8px 8px 0 0;
      }

      /* ── DOCS GRID ───────────────────────────────────── */
      .lp-docs-grid { display:grid; grid-template-columns:repeat(2,1fr); gap:20px; }
      .lp-docs-card {
        background:rgba(8,14,32,0.75); border:1px solid rgba(255,255,255,0.07);
        border-radius:20px; padding:36px; backdrop-filter:blur(16px);
        transition:transform 0.3s ease, box-shadow 0.3s ease, border-color 0.3s ease;
      }
      .lp-docs-card.lp-span-2 { grid-column:span 2; display:grid; grid-template-columns:1fr 1fr; gap:36px; align-items:start; }
      .lp-docs-card:hover { transform:translateY(-4px); border-color:rgba(255,255,255,0.11); box-shadow:0 16px 40px rgba(0,0,0,0.2); }
      .lp-docs-card-header { display:flex; align-items:center; gap:14px; margin-bottom:18px; }
      .lp-docs-card-icon { width:44px; height:44px; border-radius:11px; display:flex; align-items:center; justify-content:center; }
      .lp-docs-icon-ai      { background:rgba(139,92,246,0.12); color:#c4b5fd; border:1px solid rgba(139,92,246,0.22); }
      .lp-docs-icon-security{ background:rgba(239,68,68,0.1); color:#fca5a5; border:1px solid rgba(239,68,68,0.18); }
      .lp-docs-icon-infra   { background:rgba(16,185,129,0.1); color:#6ee7b7; border:1px solid rgba(16,185,129,0.18); }
      .lp-docs-icon-metrics { background:rgba(245,158,11,0.1); color:#fcd34d; border:1px solid rgba(245,158,11,0.18); }
      .lp-docs-icon-api     { background:rgba(100,116,139,0.1); color:#94a3b8; border:1px solid rgba(100,116,139,0.18); }
      .lp-docs-icon-brain   { background:rgba(236,72,153,0.1); color:#f9a8d4; border:1px solid rgba(236,72,153,0.18); }
      .lp-docs-card h3 { font-size:1.2rem; font-weight:700; letter-spacing:-0.3px; color:#f1f5f9; }
      .lp-docs-card-sub { font-size:0.875rem; color:rgba(148,163,184,0.62); margin-bottom:20px; line-height:1.5; }
      .lp-docs-feature-list { list-style:none; display:flex; flex-direction:column; gap:16px; }
      .lp-docs-feature-item { display:flex; align-items:flex-start; gap:11px; }
      .lp-docs-feature-bullet {
        flex-shrink:0; width:18px; height:18px; border-radius:5px;
        background:rgba(255,255,255,0.04); display:flex; align-items:center; justify-content:center;
        color:rgba(148,163,184,0.55); margin-top:3px;
      }
      .lp-docs-feature-mono { font-family:ui-monospace,'SFMono-Regular',Consolas,monospace; font-size:0.8rem; font-weight:600; color:#e2e8f0; margin-bottom:4px; }
      .lp-docs-feature-desc { font-size:0.855rem; color:rgba(148,163,184,0.67); line-height:1.58; }
      .lp-docs-feature-text { display:flex; flex-direction:column; }

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
        .lp-theme-toggle   { width:36px; height:36px; font-size:1rem; }
        .lp-hero-section   { padding:76px 20px 24px; }
        .lp-section        { padding:48px 16px; }
        .lp-footer-cta     { padding:48px 16px 36px; }
        .lp-robot-scaler   { transform:scale(0.62); }
        .lp-hero-visual    { height:320px; }
        .lp-halo-1         { width:300px; height:300px; }
        .lp-halo-2         { width:260px; height:260px; }
        .lp-login-card     { padding:36px 20px 30px; }
        .lp-gradient-btn   { padding:14px 32px; font-size:0.95rem; }
        .lp-bento-grid     { grid-template-columns:1fr; }
        .lp-bento-card     { padding:26px; }
        .lp-docs-grid      { grid-template-columns:1fr; }
        .lp-docs-card      { padding:26px; }
        .lp-docs-card.lp-span-2 { grid-column:span 1; grid-template-columns:1fr; }
        .lp-arch-flow      { padding:20px; }
        .lp-arch-container { min-width:280px; }
        .lp-arch-split::before { width:240px; }
        .lp-arch-row       { gap:10px; }
        .lp-arch-node      { min-width:150px; font-size:0.8rem; padding:10px 14px; }
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


  return (
    <div className={`lp-root${isDark ? '' : ' lp-light-mode'}`}>
      {/* Space background */}
      <SpaceCanvas isDark={isDark} />

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
        {/* Day/Night toggle */}
        <button
          className="lp-theme-toggle"
          onClick={() => setIsDark(prev => !prev)}
          aria-label={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
          title={isDark ? 'Light mode' : 'Dark mode'}
        >
          {isDark ? (
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/></svg>
          ) : (
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>
          )}
        </button>
      </nav>

      {/* ── HERO ── */}
      <section id="home" className="lp-hero-section">
        <div className="lp-hero-container">

          {/* Content */}
          <div className="lp-hero-content">
            <div className="lp-badge">
              <div className="lp-badge-dot" />
              Omnichannel AI Agent · v{APP_VERSION}
            </div>

            <h1 className="lp-hero-title">
              AI Agent for <span className="lp-title-gradient">Ad Copy &amp; CRM Calendars.</span>
            </h1>

            <p className="lp-hero-sub">
              Generate high-converting ad copies across Google, Meta, YouTube and more.
              Plan full-funnel CRM campaigns with intelligent marketing calendars — all from a single brief.
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

      {/* ── ABOUT ── */}
      <section id="about" className="lp-section">
        <div className="lp-section-inner">
          <div className="lp-section-header">
            <span className="lp-about-eyebrow">For Marketers</span>
            <h2 className="lp-section-title">
              Stop starting from a <span className="lp-title-gradient">blank page.</span>
            </h2>
            <p className="lp-section-sub">
              Vantage GenAI turns your historical data, brand voice, and customer reviews into
              high-converting campaigns across every channel in seconds. No prompt engineering required.
            </p>
          </div>

          <div className="lp-bento-grid">

            {/* Create */}
            <div className="lp-bento-card">
              <div className="lp-bento-card-icon lp-bento-icon-create">
                <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 20h9"/><path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4Z"/></svg>
              </div>
              <h3>Create at the speed of thought</h3>
              <p className="lp-bento-card-sub">Turn brief ideas into fully-fleshed campaigns instantly.</p>
              <ul className="lp-bento-feature-list">
                <li className="lp-bento-feature-item">
                  <div className="lp-bento-feature-dot"><svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3"><polyline points="20 6 9 17 4 12"/></svg></div>
                  <div className="lp-bento-feature-text">
                    <span className="lp-bento-feature-title">Plain English Generation</span>
                    <span className="lp-bento-feature-desc">Describe your campaign naturally. Get platform-ready copy instantly.</span>
                  </div>
                </li>
                <li className="lp-bento-feature-item">
                  <div className="lp-bento-feature-dot"><svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3"><polyline points="20 6 9 17 4 12"/></svg></div>
                  <div className="lp-bento-feature-text">
                    <span className="lp-bento-feature-title">Omnichannel Output</span>
                    <span className="lp-bento-feature-desc">Google Search, Facebook, Instagram, YouTube, and PMax — all in one click.</span>
                  </div>
                </li>
                <li className="lp-bento-feature-item">
                  <div className="lp-bento-feature-dot"><svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3"><polyline points="20 6 9 17 4 12"/></svg></div>
                  <div className="lp-bento-feature-text">
                    <span className="lp-bento-feature-title">Iterative Refinement</span>
                    <span className="lp-bento-feature-desc">Chat back: "Make it more urgent" or "Add the weekend offer". It remembers context.</span>
                  </div>
                </li>
                <li className="lp-bento-feature-item">
                  <div className="lp-bento-feature-dot"><svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3"><polyline points="20 6 9 17 4 12"/></svg></div>
                  <div className="lp-bento-feature-text">
                    <span className="lp-bento-feature-title">Brand Voice Baked In</span>
                    <span className="lp-bento-feature-desc">Your tone, keywords, and restrictions are hardcoded. The AI never goes off-brand.</span>
                  </div>
                </li>
              </ul>
            </div>

            {/* Target */}
            <div className="lp-bento-card">
              <div className="lp-bento-card-icon lp-bento-icon-target">
                <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="6"/><circle cx="12" cy="12" r="2"/></svg>
              </div>
              <h3>Target with precision</h3>
              <p className="lp-bento-card-sub">Let data, not guesswork, drive your messaging.</p>
              <ul className="lp-bento-feature-list">
                <li className="lp-bento-feature-item">
                  <div className="lp-bento-feature-dot"><svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3"><polyline points="20 6 9 17 4 12"/></svg></div>
                  <div className="lp-bento-feature-text">
                    <span className="lp-bento-feature-title">Review-Powered Messaging</span>
                    <span className="lp-bento-feature-desc">Automatically pulls your latest 4–5 star Google Reviews and turns customer sentiment into ad copy gold.</span>
                  </div>
                </li>
                <li className="lp-bento-feature-item">
                  <div className="lp-bento-feature-dot"><svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3"><polyline points="20 6 9 17 4 12"/></svg></div>
                  <div className="lp-bento-feature-text">
                    <span className="lp-bento-feature-title">Location-Aware</span>
                    <span className="lp-bento-feature-desc">Real-time Maps integration ensures your ads reference the exact right city or landmark.</span>
                  </div>
                </li>
                <li className="lp-bento-feature-item">
                  <div className="lp-bento-feature-dot"><svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3"><polyline points="20 6 9 17 4 12"/></svg></div>
                  <div className="lp-bento-feature-text">
                    <span className="lp-bento-feature-title">Audience Intent Detection</span>
                    <span className="lp-bento-feature-desc">Captures what your customer actually wants based on historical conversion data and writes to that intent.</span>
                  </div>
                </li>
              </ul>
            </div>

            {/* Plan */}
            <div className="lp-bento-card">
              <div className="lp-bento-card-icon lp-bento-icon-plan">
                <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="4" width="18" height="18" rx="2" ry="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>
              </div>
              <h3>Plan the full funnel</h3>
              <p className="lp-bento-card-sub">Move from single ads to cohesive, multi-touch campaigns.</p>
              <ul className="lp-bento-feature-list">
                <li className="lp-bento-feature-item">
                  <div className="lp-bento-feature-dot"><svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3"><polyline points="20 6 9 17 4 12"/></svg></div>
                  <div className="lp-bento-feature-text">
                    <span className="lp-bento-feature-title">Marketing Calendar</span>
                    <span className="lp-bento-feature-desc">Schedule campaigns across channels visually. See your full month at a glance.</span>
                  </div>
                </li>
                <li className="lp-bento-feature-item">
                  <div className="lp-bento-feature-dot"><svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3"><polyline points="20 6 9 17 4 12"/></svg></div>
                  <div className="lp-bento-feature-text">
                    <span className="lp-bento-feature-title">CRM Campaign Builder</span>
                    <span className="lp-bento-feature-desc">Build sequential outreach for Email, WhatsApp, and App Push in one cohesive flow.</span>
                  </div>
                </li>
                <li className="lp-bento-feature-item">
                  <div className="lp-bento-feature-dot"><svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3"><polyline points="20 6 9 17 4 12"/></svg></div>
                  <div className="lp-bento-feature-text">
                    <span className="lp-bento-feature-title">Brief Tracker</span>
                    <span className="lp-bento-feature-desc">Every campaign brief is saved, searchable, and reusable. No more lost briefs in email threads.</span>
                  </div>
                </li>
              </ul>
            </div>

            {/* Manage */}
            <div className="lp-bento-card">
              <div className="lp-bento-card-icon lp-bento-icon-manage">
                <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="2" y="3" width="20" height="14" rx="2" ry="2"/><line x1="8" y1="21" x2="16" y2="21"/><line x1="12" y1="17" x2="12" y2="21"/></svg>
              </div>
              <h3>Manage everything</h3>
              <p className="lp-bento-card-sub">Centralize your workflow in one intelligent dashboard.</p>
              <ul className="lp-bento-feature-list">
                <li className="lp-bento-feature-item">
                  <div className="lp-bento-feature-dot"><svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3"><polyline points="20 6 9 17 4 12"/></svg></div>
                  <div className="lp-bento-feature-text">
                    <span className="lp-bento-feature-title">Unified Dashboard</span>
                    <span className="lp-bento-feature-desc">No switching between ad managers. Handle Google, Meta, and CRM from one screen.</span>
                  </div>
                </li>
                <li className="lp-bento-feature-item">
                  <div className="lp-bento-feature-dot"><svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3"><polyline points="20 6 9 17 4 12"/></svg></div>
                  <div className="lp-bento-feature-text">
                    <span className="lp-bento-feature-title">AI Co-pilot Interface</span>
                    <span className="lp-bento-feature-desc">Talk to your AI like a colleague. Ask questions, get copy suggestions, and make changes naturally.</span>
                  </div>
                </li>
                <li className="lp-bento-feature-item">
                  <div className="lp-bento-feature-dot"><svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3"><polyline points="20 6 9 17 4 12"/></svg></div>
                  <div className="lp-bento-feature-text">
                    <span className="lp-bento-feature-title">Complete Copy History</span>
                    <span className="lp-bento-feature-desc">Every generation is saved. Go back, compare variants, and reuse past high-performing campaigns.</span>
                  </div>
                </li>
              </ul>
            </div>

          </div>
        </div>
      </section>

      {/* ── DOCS ── */}
      <section id="docs" className="lp-section">
        <div className="lp-section-inner">
          <div className="lp-section-header">
            <div className="lp-docs-eyebrow">
              <div className="lp-docs-status-dot" />
              SYSTEM STATUS: VERSION {APP_VERSION}
            </div>
            <h2 className="lp-section-title">
              Enterprise-grade infrastructure.<br />Zero maintenance.
            </h2>
            <p className="lp-section-sub">
              Explore the architecture, security models, and data pipelines powering Vantage GenAI.
              Built for scale, optimized for cost, and secured by design.
            </p>
          </div>

          {/* Architecture Flow Diagram */}
          <div className="lp-arch-flow">
            <div className="lp-arch-title">Data Pipeline &amp; Infrastructure Topology</div>
            <div className="lp-arch-container">
              <div className="lp-arch-row">
                <div className="lp-arch-node lp-arch-primary">
                  <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="3" y="3" width="18" height="18" rx="2"/><line x1="3" y1="9" x2="21" y2="9"/><line x1="9" y1="21" x2="9" y2="9"/></svg>
                  React Frontend (Vite SPA)
                </div>
              </div>
              <div className="lp-arch-line-v" />
              <div className="lp-arch-row">
                <div className="lp-arch-node" style={{background:'rgba(15,23,42,0.95)',borderColor:'rgba(255,255,255,0.18)',color:'#f1f5f9',boxShadow:'0 4px 20px rgba(0,0,0,0.4)'}}>
                  <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M18 8h1a4 4 0 0 1 0 8h-1"/><path d="M2 8h16v9a4 4 0 0 1-4 4H6a4 4 0 0 1-4-4V8z"/><line x1="6" y1="1" x2="6" y2="4"/><line x1="10" y1="1" x2="10" y2="4"/><line x1="14" y1="1" x2="14" y2="4"/></svg>
                  FastAPI Core (Cloud Run)
                </div>
              </div>
              <div className="lp-arch-line-v" />
              <div className="lp-arch-split" />
              <div className="lp-arch-row" style={{gap:'16px'}}>
                <div className="lp-arch-node lp-arch-ai">
                  <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M9.5 2A2.5 2.5 0 0 1 12 4.5v15a2.5 2.5 0 0 1-4.96.44 2.5 2.5 0 0 1-2.96-3.08 3 3 0 0 1-.34-5.58 2.5 2.5 0 0 1 1.32-4.24 2.5 2.5 0 0 1 1.98-3A2.5 2.5 0 0 1 9.5 2Z"/><path d="M14.5 2A2.5 2.5 0 0 0 12 4.5v15a2.5 2.5 0 0 0 4.96.44 2.5 2.5 0 0 0 2.96-3.08 3 3 0 0 0 .34-5.58 2.5 2.5 0 0 0-1.32-4.24 2.5 2.5 0 0 0-1.98-3A2.5 2.5 0 0 0 14.5 2Z"/></svg>
                  AI Engine
                </div>
                <div className="lp-arch-node lp-arch-data">
                  <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3"/><path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"/></svg>
                  Firestore DB
                </div>
                <div className="lp-arch-node lp-arch-data">
                  <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3"/></svg>
                  Places API &amp; Scraper
                </div>
              </div>
            </div>
          </div>

          {/* Technical Pillars */}
          <div className="lp-docs-grid">

            {/* AI & Data Architecture — spans 2 */}
            <div className="lp-docs-card lp-span-2">
              <div>
                <div className="lp-docs-card-header">
                  <div className="lp-docs-card-icon lp-docs-icon-ai">
                    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M9.5 2A2.5 2.5 0 0 1 12 4.5v15a2.5 2.5 0 0 1-4.96.44 2.5 2.5 0 0 1-2.96-3.08 3 3 0 0 1-.34-5.58 2.5 2.5 0 0 1 1.32-4.24 2.5 2.5 0 0 1 1.98-3A2.5 2.5 0 0 1 9.5 2Z"/><path d="M14.5 2A2.5 2.5 0 0 0 12 4.5v15a2.5 2.5 0 0 0 4.96.44 2.5 2.5 0 0 0 2.96-3.08 3 3 0 0 0 .34-5.58 2.5 2.5 0 0 0-1.32-4.24 2.5 2.5 0 0 0-1.98-3A2.5 2.5 0 0 0 14.5 2Z"/></svg>
                  </div>
                  <h3>AI &amp; Data Architecture</h3>
                </div>
                <p className="lp-docs-card-sub">The intelligence layer powering localized, brand-safe marketing generation.</p>
              </div>
              <ul className="lp-docs-feature-list">
                <li className="lp-docs-feature-item">
                  <div className="lp-docs-feature-bullet"><svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3"><polyline points="20 6 9 17 4 12"/></svg></div>
                  <div className="lp-docs-feature-text">
                    <span className="lp-docs-feature-mono">RAG (Retrieval-Augmented Generation) Engine</span>
                    <span className="lp-docs-feature-desc">Combines live context (scraped URLs, reviews, location data) with pre-processed historical ad performance insights stored in Firestore to ground every generation in real data.</span>
                  </div>
                </li>
                <li className="lp-docs-feature-item">
                  <div className="lp-docs-feature-bullet"><svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3"><polyline points="20 6 9 17 4 12"/></svg></div>
                  <div className="lp-docs-feature-text">
                    <span className="lp-docs-feature-mono">Multi-Model Support</span>
                    <span className="lp-docs-feature-desc">Switch between multiple AI models via admin settings. Balance speed vs. quality vs. cost per use case.</span>
                  </div>
                </li>
                <li className="lp-docs-feature-item">
                  <div className="lp-docs-feature-bullet"><svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3"><polyline points="20 6 9 17 4 12"/></svg></div>
                  <div className="lp-docs-feature-text">
                    <span className="lp-docs-feature-mono">Historical Data Ingestion Pipeline</span>
                    <span className="lp-docs-feature-desc">Upload past ad performance CSVs; the system ingests, analyzes, and stores AI-generated insights per brand/property — no manual tagging required.</span>
                  </div>
                </li>
                <li className="lp-docs-feature-item">
                  <div className="lp-docs-feature-bullet"><svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3"><polyline points="20 6 9 17 4 12"/></svg></div>
                  <div className="lp-docs-feature-text">
                    <span className="lp-docs-feature-mono">Brand Guardrails Enforcement</span>
                    <span className="lp-docs-feature-desc">Positive, negative, and restricted keyword lists are enforced strictly at the prompt-assembly layer — not post-processing.</span>
                  </div>
                </li>
              </ul>
            </div>

            {/* Security */}
            <div className="lp-docs-card">
              <div className="lp-docs-card-header">
                <div className="lp-docs-card-icon lp-docs-icon-security">
                  <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>
                </div>
                <h3>Security &amp; Access</h3>
              </div>
              <ul className="lp-docs-feature-list">
                <li className="lp-docs-feature-item">
                  <div className="lp-docs-feature-bullet"><svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3"><polyline points="20 6 9 17 4 12"/></svg></div>
                  <div className="lp-docs-feature-text">
                    <span className="lp-docs-feature-mono">Role-Based Access Control</span>
                    <span className="lp-docs-feature-desc">Admin and user roles with scoped permissions. Admins exclusively manage users, models, and training data.</span>
                  </div>
                </li>
                <li className="lp-docs-feature-item">
                  <div className="lp-docs-feature-bullet"><svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3"><polyline points="20 6 9 17 4 12"/></svg></div>
                  <div className="lp-docs-feature-text">
                    <span className="lp-docs-feature-mono">JWT Authentication</span>
                    <span className="lp-docs-feature-desc">Stateless, secure token-based authentication with audit-logged session tracking.</span>
                  </div>
                </li>
                <li className="lp-docs-feature-item">
                  <div className="lp-docs-feature-bullet"><svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3"><polyline points="20 6 9 17 4 12"/></svg></div>
                  <div className="lp-docs-feature-text">
                    <span className="lp-docs-feature-mono">Zero Raw Credentials</span>
                    <span className="lp-docs-feature-desc">Environment variables are injected at runtime; secrets never touch source code or containers.</span>
                  </div>
                </li>
              </ul>
            </div>

            {/* Infrastructure */}
            <div className="lp-docs-card">
              <div className="lp-docs-card-header">
                <div className="lp-docs-card-icon lp-docs-icon-infra">
                  <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polygon points="12 2 2 7 12 12 22 7 12 2"/><polyline points="2 17 12 22 22 17"/><polyline points="2 12 12 17 22 12"/></svg>
                </div>
                <h3>Infrastructure</h3>
              </div>
              <ul className="lp-docs-feature-list">
                <li className="lp-docs-feature-item">
                  <div className="lp-docs-feature-bullet"><svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3"><polyline points="20 6 9 17 4 12"/></svg></div>
                  <div className="lp-docs-feature-text">
                    <span className="lp-docs-feature-mono">Serverless &amp; Scale-to-Zero</span>
                    <span className="lp-docs-feature-desc">Deployed on Google Cloud Run (asia-south1); scales automatically based on traffic. No idle compute costs.</span>
                  </div>
                </li>
                <li className="lp-docs-feature-item">
                  <div className="lp-docs-feature-bullet"><svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3"><polyline points="20 6 9 17 4 12"/></svg></div>
                  <div className="lp-docs-feature-text">
                    <span className="lp-docs-feature-mono">Multi-stage Container</span>
                    <span className="lp-docs-feature-desc">Node 20 (frontend) and Python 3.12 (backend) merged in a single optimized Docker image via Google Cloud Build.</span>
                  </div>
                </li>
                <li className="lp-docs-feature-item">
                  <div className="lp-docs-feature-bullet"><svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3"><polyline points="20 6 9 17 4 12"/></svg></div>
                  <div className="lp-docs-feature-text">
                    <span className="lp-docs-feature-mono">Firestore System of Record</span>
                    <span className="lp-docs-feature-desc">All users, audit logs, brand data, and compact insights are stored in NoSQL Firestore. Zero database maintenance.</span>
                  </div>
                </li>
              </ul>
            </div>

            {/* Observability */}
            <div className="lp-docs-card">
              <div className="lp-docs-card-header">
                <div className="lp-docs-card-icon lp-docs-icon-metrics">
                  <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/></svg>
                </div>
                <h3>Observability &amp; Cost</h3>
              </div>
              <ul className="lp-docs-feature-list">
                <li className="lp-docs-feature-item">
                  <div className="lp-docs-feature-bullet"><svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3"><polyline points="20 6 9 17 4 12"/></svg></div>
                  <div className="lp-docs-feature-text">
                    <span className="lp-docs-feature-mono">Per-Request Cost Tracking</span>
                    <span className="lp-docs-feature-desc">Token usage and precise cost in INR are calculated per generation and refinement cycle, fully visible in admin logs.</span>
                  </div>
                </li>
                <li className="lp-docs-feature-item">
                  <div className="lp-docs-feature-bullet"><svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3"><polyline points="20 6 9 17 4 12"/></svg></div>
                  <div className="lp-docs-feature-text">
                    <span className="lp-docs-feature-mono">Usage Stats Per User</span>
                    <span className="lp-docs-feature-desc">Monitor total generations, tokens consumed, and cost breakdown per team member to identify power users.</span>
                  </div>
                </li>
                <li className="lp-docs-feature-item">
                  <div className="lp-docs-feature-bullet"><svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3"><polyline points="20 6 9 17 4 12"/></svg></div>
                  <div className="lp-docs-feature-text">
                    <span className="lp-docs-feature-mono">Complete Audit Trail</span>
                    <span className="lp-docs-feature-desc">Every action logs user ID, inputs, token count, cost, and latency. Exportable to CSV for compliance.</span>
                  </div>
                </li>
              </ul>
            </div>

            {/* API & Integrations */}
            <div className="lp-docs-card">
              <div className="lp-docs-card-header">
                <div className="lp-docs-card-icon lp-docs-icon-api">
                  <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/></svg>
                </div>
                <h3>API &amp; Integrations</h3>
              </div>
              <ul className="lp-docs-feature-list">
                <li className="lp-docs-feature-item">
                  <div className="lp-docs-feature-bullet"><svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3"><polyline points="20 6 9 17 4 12"/></svg></div>
                  <div className="lp-docs-feature-text">
                    <span className="lp-docs-feature-mono">REST API with OpenAPI Spec</span>
                    <span className="lp-docs-feature-desc">Full Swagger UI and ReDoc available at /api/docs. Completely headless-ready for integration into existing CI/CD or ERPs.</span>
                  </div>
                </li>
                <li className="lp-docs-feature-item">
                  <div className="lp-docs-feature-bullet"><svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3"><polyline points="20 6 9 17 4 12"/></svg></div>
                  <div className="lp-docs-feature-text">
                    <span className="lp-docs-feature-mono">Google Places Integration</span>
                    <span className="lp-docs-feature-desc">Real-time property search, ratings, review counts, and automatic 4–5 star review extraction via API.</span>
                  </div>
                </li>
                <li className="lp-docs-feature-item">
                  <div className="lp-docs-feature-bullet"><svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3"><polyline points="20 6 9 17 4 12"/></svg></div>
                  <div className="lp-docs-feature-text">
                    <span className="lp-docs-feature-mono">Web Scraper Engine</span>
                    <span className="lp-docs-feature-desc">Crawls target URLs 1-level deep automatically to extract property details, USPs, and amenities — eliminating manual copy-paste.</span>
                  </div>
                </li>
              </ul>
            </div>

            {/* The AI Brain — spans 2 */}
            <div className="lp-docs-card lp-span-2">
              <div>
                <div className="lp-docs-card-header">
                  <div className="lp-docs-card-icon lp-docs-icon-brain">
                    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M9.5 2A2.5 2.5 0 0 1 12 4.5v15a2.5 2.5 0 0 1-4.96.44 2.5 2.5 0 0 1-2.96-3.08 3 3 0 0 1-.34-5.58 2.5 2.5 0 0 1 1.32-4.24 2.5 2.5 0 0 1 1.98-3A2.5 2.5 0 0 1 9.5 2Z"/><path d="M14.5 2A2.5 2.5 0 0 0 12 4.5v15a2.5 2.5 0 0 0 4.96.44 2.5 2.5 0 0 0 2.96-3.08 3 3 0 0 0 .34-5.58 2.5 2.5 0 0 0-1.32-4.24 2.5 2.5 0 0 0-1.98-3A2.5 2.5 0 0 0 14.5 2Z"/></svg>
                  </div>
                  <h3>The AI Brain &amp; Continuous Training</h3>
                </div>
                <p className="lp-docs-card-sub">A self-optimizing, highly cost-effective intelligence layer that learns from open-ended inputs.</p>
              </div>
              <ul className="lp-docs-feature-list">
                <li className="lp-docs-feature-item">
                  <div className="lp-docs-feature-bullet"><svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3"><polyline points="20 6 9 17 4 12"/></svg></div>
                  <div className="lp-docs-feature-text">
                    <span className="lp-docs-feature-mono">Open-Ended Training Pipeline</span>
                    <span className="lp-docs-feature-desc">The backend accepts unstructured CSVs or open-text instructions. The AI acts as a data scientist, parsing metrics (CTR, Unsubscribes) to extract global best practices without rigid formatting constraints.</span>
                  </div>
                </li>
                <li className="lp-docs-feature-item">
                  <div className="lp-docs-feature-bullet"><svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3"><polyline points="20 6 9 17 4 12"/></svg></div>
                  <div className="lp-docs-feature-text">
                    <span className="lp-docs-feature-mono">Compact Insights Architecture</span>
                    <span className="lp-docs-feature-desc">By replacing heavy vector databases (like ChromaDB) with a distilled JSON 'Insights Document' in Firestore, the system drastically reduces payload size. This guarantees low-latency, token-efficient API calls for every generation.</span>
                  </div>
                </li>
                <li className="lp-docs-feature-item">
                  <div className="lp-docs-feature-bullet"><svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3"><polyline points="20 6 9 17 4 12"/></svg></div>
                  <div className="lp-docs-feature-text">
                    <span className="lp-docs-feature-mono">Ad-Hoc Model Retraining</span>
                    <span className="lp-docs-feature-desc">Administrators can pass plain-text instructions (e.g., "Prioritize the new loyalty program this month") to instantly retrain the model's behavior. The system updates the brain, tracking the exact timestamp in the audit log.</span>
                  </div>
                </li>
                <li className="lp-docs-feature-item">
                  <div className="lp-docs-feature-bullet"><svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3"><polyline points="20 6 9 17 4 12"/></svg></div>
                  <div className="lp-docs-feature-text">
                    <span className="lp-docs-feature-mono">Tokenized Cost Optimization</span>
                    <span className="lp-docs-feature-desc">Every generation is strictly tokenized. Synthesized data (like 150 scraped Google Reviews) is cached with a 30-day TTL. Repeated prompts fetch the cost-free cached insights rather than incurring recurring AI summarization costs.</span>
                  </div>
                </li>
              </ul>
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
          <span>Initialize Agent</span>
        </button>
        <div className="lp-footer-bottom">
          &copy; 2025 Vantage GenAI
        </div>
      </section>
    </div>
  );
}
