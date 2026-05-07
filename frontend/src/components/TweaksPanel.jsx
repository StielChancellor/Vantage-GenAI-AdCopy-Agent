/**
 * TweaksPanel — floating bottom-right control for theme + density.
 *
 * Mirrors the design's tweaks panel pattern (see vantage2-0 handoff). Closed
 * by default, opens on the FAB. Persists via ThemeContext (which writes to
 * localStorage and `data-em-theme` / `data-em-density` on <html>).
 */
import { useState } from 'react';
import { Sliders, Sun, Moon, X } from 'lucide-react';
import { useTheme } from '../contexts/ThemeContext';

const DENSITIES = [
  { v: 'comfy', label: 'Comfy' },
  { v: 'normal', label: 'Normal' },
  { v: 'dense', label: 'Dense' },
];

export default function TweaksPanel() {
  const [open, setOpen] = useState(false);
  const { theme, toggleTheme, density, setDensity } = useTheme();

  if (!open) {
    return (
      <button
        type="button"
        className="em-tweaks-toggle"
        onClick={() => setOpen(true)}
        title="Tweaks (theme · density)"
        aria-label="Open tweaks panel"
      >
        <Sliders size={18} />
      </button>
    );
  }

  return (
    <div className="em-tweaks" role="dialog" aria-label="Tweaks">
      <div className="row">
        <span className="em-mono-label">Tweaks</span>
        <button type="button" onClick={() => setOpen(false)} className="em-btn ghost sm" aria-label="Close">
          <X size={14} />
        </button>
      </div>

      <div className="row">
        <label>Theme</label>
        <div className="em-mode-toggle">
          <button aria-selected={theme === 'light'} onClick={() => theme !== 'light' && toggleTheme()}>
            <Sun size={11} /> Light
          </button>
          <button aria-selected={theme === 'dark'} onClick={() => theme !== 'dark' && toggleTheme()}>
            <Moon size={11} /> Dark
          </button>
        </div>
      </div>

      <div className="row">
        <label>Density</label>
        <div className="em-mode-toggle">
          {DENSITIES.map((d) => (
            <button
              key={d.v}
              aria-selected={density === d.v}
              onClick={() => setDensity(d.v)}
            >
              {d.label}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
