import { afterEach, describe, expect, it, vi } from "vitest";
import { applyTheme, resolveTheme, setThemePref, themePref } from "./theme";

function mockSystem(dark) {
  window.matchMedia = vi.fn(() => ({
    matches: dark,
    addEventListener: vi.fn(),
  }));
}

describe("theme", () => {
  afterEach(() => {
    localStorage.clear();
    delete document.documentElement.dataset.theme;
  });

  it("follows the device by default", () => {
    mockSystem(true);
    expect(themePref()).toBe("system");
    expect(resolveTheme()).toBe("dark");
    mockSystem(false);
    expect(resolveTheme()).toBe("light");
  });

  it("remembers an explicit choice and sets data-theme", () => {
    mockSystem(false);
    setThemePref("dark");
    expect(themePref()).toBe("dark");
    expect(document.documentElement.dataset.theme).toBe("dark");
    setThemePref("system");
    expect(localStorage.getItem("mi_theme")).toBeNull();
    expect(document.documentElement.dataset.theme).toBe("light");
  });

  it("ignores junk in storage", () => {
    mockSystem(false);
    localStorage.setItem("mi_theme", "purple");
    expect(themePref()).toBe("system");
    expect(applyTheme()).toBe("light");
  });
});
