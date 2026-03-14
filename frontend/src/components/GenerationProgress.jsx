import { useState, useEffect } from 'react';
import { Globe, Database, FileText, Sparkles, CheckCircle } from 'lucide-react';

const STEPS = [
  { id: 'scrape', label: 'Scraping website content', icon: Globe },
  { id: 'history', label: 'Checking historic ad database', icon: Database },
  { id: 'usp', label: 'Analyzing brand USP sheet', icon: FileText },
  { id: 'generate', label: 'Generating optimized ad copy', icon: Sparkles },
];

export default function GenerationProgress() {
  const [activeStep, setActiveStep] = useState(0);
  const [elapsed, setElapsed] = useState(0);

  // Cycle through steps to simulate progress
  useEffect(() => {
    const interval = setInterval(() => {
      setActiveStep((prev) => {
        if (prev < STEPS.length - 1) return prev + 1;
        return prev; // Stay on last step
      });
    }, 3500);
    return () => clearInterval(interval);
  }, []);

  // Track elapsed time
  useEffect(() => {
    const timer = setInterval(() => {
      setElapsed((prev) => prev + 1);
    }, 1000);
    return () => clearInterval(timer);
  }, []);

  return (
    <div className="gen-progress">
      <div className="gen-progress-spinner" />
      <div className="gen-progress-title">Crafting Your Ad Copy</div>
      <div className="gen-steps">
        {STEPS.map((step, i) => {
          const Icon = step.icon;
          let state = 'pending';
          if (i < activeStep) state = 'done';
          else if (i === activeStep) state = 'active';

          return (
            <div key={step.id} className={`gen-step ${state}`}>
              <div className="gen-step-icon">
                {state === 'done' ? (
                  <CheckCircle size={18} />
                ) : state === 'active' ? (
                  <div className="spinner-sm" />
                ) : (
                  <Icon size={16} />
                )}
              </div>
              <span className="gen-step-label">{step.label}</span>
            </div>
          );
        })}
      </div>
      <div className="gen-elapsed">
        {elapsed}s elapsed
      </div>
    </div>
  );
}
