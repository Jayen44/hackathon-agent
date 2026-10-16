"use client";

export function ThemeToggle() {
  const toggle = () => {
    const el = document.documentElement;
    const cur = el.getAttribute("data-theme") ?? (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
    const next = cur === "dark" ? "light" : "dark";
    el.setAttribute("data-theme", next);
    try { localStorage.setItem("theme", next); } catch { /* private mode */ }
  };
  return (
    <button type="button" onClick={toggle} className="rounded border border-line px-2 py-1 text-xs text-muted hover:text-fg" aria-label="Toggle light or dark theme">
      Theme
    </button>
  );
}
