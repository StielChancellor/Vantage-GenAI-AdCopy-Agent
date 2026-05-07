import { createContext, useContext, useState, useEffect } from 'react';

const ThemeContext = createContext(null);

const DENSITIES = ['comfy', 'normal', 'dense'];

export function ThemeProvider({ children }) {
  // legacy `data-theme` (used by the existing app stylesheet) AND the new
  // `data-em-theme` (used by editorial-mono tokens) — kept in lockstep.
  const [theme, setTheme] = useState(() => localStorage.getItem('vantage-theme') || 'light');
  const [density, setDensity] = useState(() => {
    const saved = localStorage.getItem('vantage-density');
    return DENSITIES.includes(saved) ? saved : 'normal';
  });

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
    document.documentElement.setAttribute('data-em-theme', theme);
    localStorage.setItem('vantage-theme', theme);
  }, [theme]);

  useEffect(() => {
    document.documentElement.setAttribute('data-em-density', density);
    localStorage.setItem('vantage-density', density);
  }, [density]);

  const toggleTheme = () => setTheme(prev => (prev === 'dark' ? 'light' : 'dark'));

  return (
    <ThemeContext.Provider value={{ theme, toggleTheme, setTheme, density, setDensity }}>
      {children}
    </ThemeContext.Provider>
  );
}

export function useTheme() {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error('useTheme must be used within ThemeProvider');
  return ctx;
}
