import { useState } from "react";
import { setThemePref, themePref } from "../lib/theme";

const NEXT = { system: "light", light: "dark", dark: "system" };
const SHOW = {
  system: ["🖥️", "Theme: follows your device"],
  light: ["☀️", "Theme: light"],
  dark: ["🌙", "Theme: dark"],
};

// Cycles system → light → dark. The label says what's on now.
export default function ThemeToggle({ className = "" }) {
  const [pref, setPref] = useState(themePref);
  const [icon, label] = SHOW[pref];
  return (
    <button
      type="button"
      onClick={() => {
        const next = NEXT[pref];
        setThemePref(next);
        setPref(next);
      }}
      className={`grid h-9 w-9 place-items-center rounded-full text-base ring-1 ring-line transition hover:bg-surface ${className}`}
      aria-label={`${label}. Click to change.`}
      title={label}
    >
      <span aria-hidden="true">{icon}</span>
    </button>
  );
}
