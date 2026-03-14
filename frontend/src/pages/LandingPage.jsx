import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';

export default function LandingPage() {
  const canvasRef = useRef(null);
  const animFrameRef = useRef(null);
  const stateRef = useRef({
    waves: [],
    dataNodes: [],
    windParticles: [],
    time: 0,
    targetMouseX: 0,
    targetMouseY: 0,
    currentMouseX: 0,
    currentMouseY: 0,
    prevMouseX: 0,
    prevMouseY: 0,
    isTouch: false,
    width: 0,
    height: 0,
  });
  const navigate = useNavigate();
  const [btnText, setBtnText] = useState('Initialize Workspace');
  const [btnStyle, setBtnStyle] = useState({});

  useEffect(() => {
    const canvas = canvasRef.current;
    const ctx = canvas.getContext('2d');
    const s = stateRef.current;

    s.width = canvas.width = window.innerWidth;
    s.height = canvas.height = window.innerHeight;
    s.targetMouseX = s.width / 2;
    s.targetMouseY = s.height / 2;
    s.currentMouseX = s.width / 2;
    s.currentMouseY = s.height / 2;
    s.prevMouseX = s.width / 2;
    s.prevMouseY = s.height / 2;

    const colors = [
      'rgba(6, 182, 212, 0.4)',
      'rgba(139, 92, 246, 0.4)',
      'rgba(37, 99, 235, 0.4)',
    ];
    const magneticRadius = 250;
    const snapRadius = 100;

    class Wave {
      constructor(index) {
        this.color = colors[index % colors.length];
        this.yOffset = s.height * 0.5 + (Math.random() * 200 - 100);
        this.amplitude = 80 + Math.random() * 120;
        this.frequency = 0.001 + Math.random() * 0.002;
        this.speed = 0.01 + Math.random() * 0.01;
        this.phase = Math.random() * Math.PI * 2;
        this.thickness = 1 + Math.random() * 1.5;
      }
      calculateY(x, time, mx, my) {
        let y = this.yOffset + Math.sin(x * this.frequency + this.phase + time * this.speed) * this.amplitude;
        y += Math.cos(x * this.frequency * 2 + time * this.speed * 1.5) * (this.amplitude * 0.3);
        const dx = x - mx;
        const dy = y - my;
        const distance = Math.sqrt(dx * dx + dy * dy);
        if (distance < magneticRadius) {
          let force = 1 - (distance / magneticRadius);
          force = force * force * (3 - 2 * force);
          y -= dy * force * 0.4;
        }
        return y;
      }
      draw(ctx, time, mx, my) {
        ctx.beginPath();
        ctx.moveTo(0, this.calculateY(0, time, mx, my));
        for (let x = 15; x <= s.width; x += 15) {
          ctx.lineTo(x, this.calculateY(x, time, mx, my));
        }
        ctx.strokeStyle = this.color;
        ctx.lineWidth = this.thickness;
        ctx.stroke();
      }
    }

    class DataNode {
      constructor(wave) {
        this.wave = wave;
        this.progress = Math.random() * s.width;
        this.speed = 1 + Math.random() * 2;
        this.baseSize = Math.random() * 1.5 + 1;
        this.opacity = 0;
      }
      draw(ctx, time, mx, my) {
        this.progress += this.speed;
        if (this.progress > s.width + 50) this.progress = -50;
        const x = this.progress;
        const y = this.wave.calculateY(x, time, mx, my);
        const dx = x - mx;
        const dy = y - my;
        const dist = Math.sqrt(dx * dx + dy * dy);
        const targetOpacity = dist < magneticRadius ? 1 - (dist / magneticRadius) : 0.1;
        this.opacity += (targetOpacity - this.opacity) * 0.1;
        if (this.opacity > 0.05) {
          ctx.beginPath();
          ctx.arc(x, y, this.baseSize + (this.opacity * 2), 0, Math.PI * 2);
          ctx.fillStyle = `rgba(255, 255, 255, ${this.opacity})`;
          ctx.fill();
          if (dist < snapRadius) {
            ctx.beginPath();
            ctx.moveTo(x, y);
            ctx.lineTo(mx, my);
            ctx.strokeStyle = `rgba(255, 255, 255, ${this.opacity * 0.5})`;
            ctx.lineWidth = 0.5;
            ctx.stroke();
          }
        }
      }
    }

    class WindParticle {
      constructor(x, y, vx, vy) {
        this.x = x;
        this.y = y;
        this.vx = -vx * 0.12 + (Math.random() - 0.5) * 2;
        this.vy = -vy * 0.12 + (Math.random() - 0.5) * 2 - 0.5;
        this.life = 1.0;
        this.decay = Math.random() * 0.02 + 0.015;
        this.size = Math.random() * 2.5 + 0.5;
        this.color = Math.random() > 0.5 ? 'rgba(6, 182, 212,' : 'rgba(139, 92, 246,';
      }
      draw(ctx) {
        this.x += this.vx;
        this.y += this.vy;
        this.life -= this.decay;
        if (this.life > 0) {
          ctx.beginPath();
          ctx.arc(this.x, this.y, this.size * this.life, 0, Math.PI * 2);
          ctx.fillStyle = this.color + (this.life * 0.6) + ')';
          ctx.fill();
        }
      }
    }

    function initWaves() {
      s.waves = [];
      s.dataNodes = [];
      const numWaves = window.innerWidth < 768 ? 4 : 7;
      for (let i = 0; i < numWaves; i++) {
        const w = new Wave(i);
        s.waves.push(w);
        const numNodes = 10 + Math.floor(Math.random() * 5);
        for (let j = 0; j < numNodes; j++) {
          s.dataNodes.push(new DataNode(w));
        }
      }
    }

    function animate() {
      ctx.clearRect(0, 0, s.width, s.height);
      s.time += 1;
      s.currentMouseX += (s.targetMouseX - s.currentMouseX) * 0.1;
      s.currentMouseY += (s.targetMouseY - s.currentMouseY) * 0.1;

      // Update CSS vars for spotlight
      document.documentElement.style.setProperty('--lp-mouse-x', `${s.currentMouseX}px`);
      document.documentElement.style.setProperty('--lp-mouse-y', `${s.currentMouseY}px`);

      const mx = s.currentMouseX;
      const my = s.currentMouseY;

      s.waves.forEach(w => w.draw(ctx, s.time, mx, my));
      s.dataNodes.forEach(n => n.draw(ctx, s.time, mx, my));

      // Wind particles
      const mouseVx = mx - s.prevMouseX;
      const mouseVy = my - s.prevMouseY;
      const mouseSpeed = Math.sqrt(mouseVx * mouseVx + mouseVy * mouseVy);

      if (mouseSpeed > 0.5) {
        const spawnCount = Math.min(Math.floor(mouseSpeed * 0.4), 8);
        for (let i = 0; i < spawnCount; i++) {
          const ox = mx - (mouseVx * (i / spawnCount));
          const oy = my - (mouseVy * (i / spawnCount));
          s.windParticles.push(new WindParticle(ox, oy, mouseVx, mouseVy));
        }
      }
      if (Math.random() > 0.6 && !s.isTouch) {
        s.windParticles.push(new WindParticle(mx, my, 0, -2));
      }
      for (let i = s.windParticles.length - 1; i >= 0; i--) {
        s.windParticles[i].draw(ctx);
        if (s.windParticles[i].life <= 0) {
          s.windParticles.splice(i, 1);
        }
      }
      s.prevMouseX = mx;
      s.prevMouseY = my;
      animFrameRef.current = requestAnimationFrame(animate);
    }

    const handleMouseMove = (e) => {
      if (!s.isTouch) {
        s.targetMouseX = e.clientX;
        s.targetMouseY = e.clientY;
      }
    };
    const handleTouchStart = (e) => {
      s.isTouch = true;
      s.targetMouseX = e.touches[0].clientX;
      s.targetMouseY = e.touches[0].clientY;
    };
    const handleTouchMove = (e) => {
      s.targetMouseX = e.touches[0].clientX;
      s.targetMouseY = e.touches[0].clientY;
    };
    const handleTouchEnd = () => {
      setTimeout(() => { s.isTouch = false; }, 500);
    };
    const handleResize = () => {
      s.width = canvas.width = window.innerWidth;
      s.height = canvas.height = window.innerHeight;
      initWaves();
    };

    window.addEventListener('mousemove', handleMouseMove);
    window.addEventListener('touchstart', handleTouchStart, { passive: true });
    window.addEventListener('touchmove', handleTouchMove, { passive: true });
    window.addEventListener('touchend', handleTouchEnd);
    window.addEventListener('resize', handleResize);

    initWaves();
    animate();

    return () => {
      cancelAnimationFrame(animFrameRef.current);
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('touchstart', handleTouchStart);
      window.removeEventListener('touchmove', handleTouchMove);
      window.removeEventListener('touchend', handleTouchEnd);
      window.removeEventListener('resize', handleResize);
    };
  }, []);

  const handleStart = () => {
    setBtnText('Authenticating...');
    setBtnStyle({ opacity: 0.7, pointerEvents: 'none' });
    // Speed up waves for effect
    const s = stateRef.current;
    s.waves.forEach(w => { w.speed *= 5; w.amplitude *= 1.2; });
    s.targetMouseX = s.width / 2;
    s.targetMouseY = s.height / 2;

    setTimeout(() => {
      setBtnText('Access Granted');
      setBtnStyle({ background: '#06B6D4', color: '#000', opacity: 1, pointerEvents: 'none' });
      setTimeout(() => {
        navigate('/login');
      }, 800);
    }, 1200);
  };

  return (
    <div className="lp-root">
      <div className="lp-spotlight" />
      <div className="lp-canvas-container">
        <canvas ref={canvasRef} />
      </div>
      <div className="lp-overlay" />
      <div className="lp-content">
        <nav className="lp-nav">
          <div className="lp-logo">
            <div className="lp-logo-mark" />
            Vantage GenAI
          </div>
          <button className="lp-login-btn" onClick={handleStart}>
            Sign In
          </button>
        </nav>
        <main className="lp-hero">
          <div className="lp-badge">
            <div className="lp-badge-dot" />
            v2.0 RAG Engine Now Live
          </div>
          <h1 className="lp-title">
            <span className="lp-text-gradient">Data-driven copy.</span>
            <br />
            <span className="lp-text-gradient-primary">Engineered to convert.</span>
          </h1>
          <p className="lp-subtitle">
            Ingest historical performance, brand USPs, and real-time reviews to generate highly optimized ad copy for Google, Meta, and beyond.
          </p>
          <div className="lp-cta-group">
            <button className="lp-cta-primary" onClick={handleStart} style={btnStyle}>
              {btnText}
            </button>
          </div>
        </main>
      </div>
    </div>
  );
}
