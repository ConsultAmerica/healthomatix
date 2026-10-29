"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";

export type ThemeMode = "light" | "dark" | "contrast";

const STORAGE_KEY = "healthomatix-theme";

type ThemeContextValue = {
  theme: ThemeMode;
  setTheme: (theme: ThemeMode) => void;
  cycle: () => void;
};

const ThemeContext = createContext<ThemeContextValue>({
  theme: "light",
  setTheme: () => undefined,
  cycle: () => undefined,
});

function applyTheme(theme: ThemeMode) {
  document.documentElement.dataset.theme = theme;
  document.documentElement.style.colorScheme = theme === "light" ? "light" : "dark";
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<ThemeMode>("light");

  useEffect(() => {
    const stored = window.localStorage.getItem(STORAGE_KEY) as ThemeMode | null;
    const initial =
      stored === "dark" || stored === "contrast" || stored === "light" ? stored : "light";
    setThemeState(initial);
    applyTheme(initial);
  }, []);

  const setTheme = useCallback((next: ThemeMode) => {
    setThemeState(next);
    window.localStorage.setItem(STORAGE_KEY, next);
    applyTheme(next);
  }, []);

  const cycle = useCallback(() => {
    setTheme(theme === "light" ? "dark" : theme === "dark" ? "contrast" : "light");
  }, [setTheme, theme]);

  return <ThemeContext.Provider value={{ theme, setTheme, cycle }}>{children}</ThemeContext.Provider>;
}

export function useTheme() {
  return useContext(ThemeContext);
}

export function ThemeToggle({ compact = false }: { compact?: boolean }) {
  const { theme, cycle } = useTheme();
  const label =
    theme === "light" ? "Switch to dark mode" : theme === "dark" ? "Switch to high contrast" : "Switch to light mode";
  const short = theme === "light" ? "Light" : theme === "dark" ? "Dark" : "Contrast";
  return (
    <button
      className={`theme-toggle${compact ? " theme-toggle-compact" : ""}`}
      type="button"
      onClick={cycle}
      title={label}
      aria-label={label}
    >
      <span className="theme-toggle-swatch" aria-hidden="true" data-mode={theme} />
      {!compact && <span>{short}</span>}
    </button>
  );
}

/** Inline script to set theme before paint — paste into root layout. */
export const THEME_BOOT_SCRIPT = `(function(){try{var t=localStorage.getItem('${STORAGE_KEY}');if(t==='dark'||t==='contrast'||t==='light'){document.documentElement.dataset.theme=t;document.documentElement.style.colorScheme=t==='light'?'light':'dark';}}catch(e){}})();`;
