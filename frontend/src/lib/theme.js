import { useEffect, useState } from "react";

const THEME_KEY = "mi_theme";
const PREFS = ["system", "light", "dark"];
const listeners = new Set();

// The user's choice: 'system' (follow the device), 'light' or 'dark'.
export function themePref() {
  try {
    const saved = localStorage.getItem(THEME_KEY);
    if (PREFS.includes(saved)) return saved;
  } catch {
    // Storage unavailable: follow the device.
  }
  return "system";
}

function systemDark() {
  return (
    typeof window !== "undefined" &&
    Boolean(window.matchMedia?.("(prefers-color-scheme: dark)").matches)
  );
}

export function resolveTheme(pref = themePref()) {
  if (pref === "system") return systemDark() ? "dark" : "light";
  return pref;
}

// Sets <html data-theme>, which index.css keys the dark palette on. index.html
// runs the same logic inline before the app loads, so pages never flash light.
export function applyTheme(pref = themePref()) {
  const theme = resolveTheme(pref);
  document.documentElement.dataset.theme = theme;
  listeners.forEach((fn) => fn(theme));
  return theme;
}

export function setThemePref(pref) {
  try {
    if (pref === "system") localStorage.removeItem(THEME_KEY);
    else localStorage.setItem(THEME_KEY, pref);
  } catch {
    // Storage unavailable: the choice lasts for this page only.
  }
  applyTheme(pref);
}

if (typeof window !== "undefined" && window.matchMedia) {
  window
    .matchMedia("(prefers-color-scheme: dark)")
    .addEventListener?.("change", () => {
      if (themePref() === "system") applyTheme("system");
    });
}

// The theme in effect right now ('light' | 'dark'), for widgets that take a
// theme prop (code editor, whiteboard).
export function useTheme() {
  const [theme, setTheme] = useState(() => resolveTheme());
  useEffect(() => {
    listeners.add(setTheme);
    return () => listeners.delete(setTheme);
  }, []);
  return theme;
}
