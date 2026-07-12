"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import { globalSearch } from "@/lib/api";
import type { SearchResults } from "@/lib/api";

const NAV_LINKS = [
  { href: "/ligas",      label: "Ligas" },
  { href: "/equipos",    label: "Equipos" },
  { href: "/jugadores",  label: "Jugadores" },
  { href: "/comparar",   label: "Comparar" },
  { href: "/lideres",    label: "Líderes" },
  { href: "/glosario",   label: "Glosario" },
  { href: "/acerca-de",  label: "Acerca de" },
];

// ── Icons (inline SVG, no extra dependency) ───────────────────────────────────

function SunIcon() {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width="18"
      height="18"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41" />
    </svg>
  );
}

function MoonIcon() {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width="18"
      height="18"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
    </svg>
  );
}

function HamburgerIcon() {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width="20"
      height="20"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <line x1="4" y1="6" x2="20" y2="6" />
      <line x1="4" y1="12" x2="20" y2="12" />
      <line x1="4" y1="18" x2="20" y2="18" />
    </svg>
  );
}

function CloseIcon() {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width="20"
      height="20"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <line x1="18" y1="6" x2="6" y2="18" />
      <line x1="6" y1="6" x2="18" y2="18" />
    </svg>
  );
}

function SearchIcon() {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width="15"
      height="15"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <circle cx="11" cy="11" r="8" />
      <line x1="21" y1="21" x2="16.65" y2="16.65" />
    </svg>
  );
}

// ── Theme toggle ──────────────────────────────────────────────────────────────

function ThemeToggle() {
  const [dark, setDark] = useState<boolean | null>(null);

  useEffect(() => {
    setDark(document.documentElement.classList.contains("dark"));
  }, []);

  function toggle() {
    const next = !dark;
    document.documentElement.classList.toggle("dark", next);
    try {
      localStorage.setItem("theme", next ? "dark" : "light");
    } catch {
      // Private browsing may throw; silently ignore.
    }
    setDark(next);
  }

  return (
    <button
      onClick={toggle}
      aria-label={dark ? "Cambiar a modo claro" : "Cambiar a modo oscuro"}
      className="flex h-8 w-8 items-center justify-center rounded-lg text-zinc-500 transition-colors hover:bg-zinc-100 hover:text-zinc-900 dark:text-zinc-400 dark:hover:bg-zinc-800 dark:hover:text-zinc-100"
    >
      {dark === null ? <span className="h-4 w-4" /> : dark ? <SunIcon /> : <MoonIcon />}
    </button>
  );
}

// ── Global search bar (desktop inline, keyboard-navigable) ────────────────────

const SEARCH_DEBOUNCE_MS = 280;

function GlobalSearch() {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchResults | null>(null);
  const [open, setOpen] = useState(false);
  const [activeIdx, setActiveIdx] = useState(-1);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const search = useCallback((q: string) => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    if (q.trim().length < 2) {
      setResults(null);
      setOpen(false);
      return;
    }
    debounceRef.current = setTimeout(() => {
      globalSearch(q.trim())
        .then((r) => {
          setResults(r);
          const total = r.teams.length + r.players.length + r.leagues.length;
          setOpen(total > 0);
          setActiveIdx(-1);
        })
        .catch(() => {/* ignore */});
    }, SEARCH_DEBOUNCE_MS);
  }, []);

  useEffect(() => {
    search(query);
  }, [query, search]);

  // Flatten all results into a navigable list with their destination URLs.
  const flatItems: { label: string; sub: string; href: string }[] = results
    ? [
        ...results.leagues.map((l) => ({
          label: l.name,
          sub: "Liga",
          href: `/ligas/${l.slug}`,
        })),
        ...results.teams.map((t) => ({
          label: t.name,
          sub: "Equipo",
          href: `/equipos/${t.slug}`,
        })),
        ...results.players.map((p) => ({
          label: p.displayName || `${p.firstName} ${p.lastName}`,
          sub: "Jugador",
          href: `/jugadores/${p.slug}`,
        })),
      ]
    : [];

  function navigate(href: string) {
    setOpen(false);
    setQuery("");
    setResults(null);
    router.push(href);
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (!open || flatItems.length === 0) return;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActiveIdx((i) => Math.min(i + 1, flatItems.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActiveIdx((i) => Math.max(i - 1, -1));
    } else if (e.key === "Enter" && activeIdx >= 0) {
      e.preventDefault();
      navigate(flatItems[activeIdx].href);
    } else if (e.key === "Escape") {
      setOpen(false);
      inputRef.current?.blur();
    }
  }

  return (
    <div className="relative hidden md:block">
      <div className="flex items-center gap-1.5 rounded-lg border border-zinc-300 bg-white px-2.5 py-1.5 text-sm text-zinc-500 dark:border-zinc-700 dark:bg-zinc-900">
        <SearchIcon />
        <input
          ref={inputRef}
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onFocus={() => results && flatItems.length > 0 && setOpen(true)}
          onBlur={() => setTimeout(() => setOpen(false), 150)}
          onKeyDown={handleKeyDown}
          placeholder="Buscar…"
          aria-label="Buscar equipos, jugadores o ligas"
          className="w-36 bg-transparent outline-none placeholder-zinc-400 dark:text-zinc-100 lg:w-48"
        />
      </div>

      {open && flatItems.length > 0 && (
        <ul
          role="listbox"
          className="absolute right-0 top-full z-50 mt-1 w-64 rounded-lg border border-zinc-200 bg-white shadow-lg dark:border-zinc-700 dark:bg-zinc-900"
        >
          {flatItems.map((item, i) => (
            <li key={item.href} role="option" aria-selected={i === activeIdx}>
              <button
                onMouseDown={() => navigate(item.href)}
                className={`flex w-full items-center justify-between gap-2 px-3 py-2 text-left text-sm ${
                  i === activeIdx
                    ? "bg-zinc-100 dark:bg-zinc-800"
                    : "hover:bg-zinc-50 dark:hover:bg-zinc-800"
                }`}
              >
                <span className="truncate font-medium">{item.label}</span>
                <span className="shrink-0 rounded bg-zinc-100 px-1.5 py-0.5 text-[10px] text-zinc-500 dark:bg-zinc-700 dark:text-zinc-400">
                  {item.sub}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

// ── NavBar ────────────────────────────────────────────────────────────────────

export function NavBar() {
  const [mobileOpen, setMobileOpen] = useState(false);

  return (
    <header className="sticky top-0 z-40 border-b border-zinc-200 bg-white/90 backdrop-blur dark:border-zinc-800 dark:bg-zinc-950/90">
      <nav className="mx-auto flex max-w-5xl items-center gap-3 px-4 py-3">
        {/* Brand */}
        <Link
          href="/"
          className="flex-shrink-0 font-bold text-court hover:opacity-80"
          onClick={() => setMobileOpen(false)}
        >
          Basket Stats
        </Link>

        {/* Desktop nav links */}
        <ul className="hidden flex-1 items-center gap-1 md:flex">
          {NAV_LINKS.map((link) => (
            <li key={link.href}>
              <Link
                href={link.href}
                className="rounded-md px-3 py-1.5 text-sm text-zinc-700 transition-colors hover:bg-zinc-100 hover:text-zinc-900 dark:text-zinc-300 dark:hover:bg-zinc-800 dark:hover:text-zinc-100"
              >
                {link.label}
              </Link>
            </li>
          ))}
        </ul>

        {/* Spacer on mobile */}
        <div className="flex-1 md:hidden" />

        {/* Global search (desktop only) */}
        <GlobalSearch />

        {/* Theme toggle */}
        <ThemeToggle />

        {/* Hamburger (mobile only) */}
        <button
          aria-label={mobileOpen ? "Cerrar menú" : "Abrir menú"}
          aria-expanded={mobileOpen}
          onClick={() => setMobileOpen((o) => !o)}
          className="flex h-8 w-8 items-center justify-center rounded-lg text-zinc-500 transition-colors hover:bg-zinc-100 hover:text-zinc-900 dark:text-zinc-400 dark:hover:bg-zinc-800 dark:hover:text-zinc-100 md:hidden"
        >
          {mobileOpen ? <CloseIcon /> : <HamburgerIcon />}
        </button>
      </nav>

      {/* Mobile dropdown */}
      {mobileOpen && (
        <div className="border-t border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-950 md:hidden">
          <ul className="mx-auto max-w-5xl space-y-1 px-4 py-3">
            {NAV_LINKS.map((link) => (
              <li key={link.href}>
                <Link
                  href={link.href}
                  onClick={() => setMobileOpen(false)}
                  className="block rounded-md px-3 py-2 text-sm text-zinc-700 transition-colors hover:bg-zinc-100 hover:text-zinc-900 dark:text-zinc-300 dark:hover:bg-zinc-800 dark:hover:text-zinc-100"
                >
                  {link.label}
                </Link>
              </li>
            ))}
          </ul>
        </div>
      )}
    </header>
  );
}
