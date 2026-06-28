"""Headless-browser fetch for JavaScript-rendered sources (spec §7).

Used by sources that render content client-side (e.g. ACB.com, a Next.js app).
Playwright is imported lazily so connectors that don't need a browser (FEB) work
without it installed, and so the dependency is only required where it's used.
"""

from .http import DEFAULT_USER_AGENT


def fetch_rendered(
    url: str,
    *,
    timeout_ms: int = 30000,
    wait_selector: str | None = None,
    wait_until: str = "networkidle",
) -> str:
    """Return the fully-rendered HTML of a JavaScript-driven page.

    Parameters
    ----------
    url : str
        Absolute URL to render.
    timeout_ms : int
        Navigation / selector timeout in milliseconds.
    wait_selector : str or None
        Optional CSS selector to wait for before returning (ensures the data
        has been injected into the DOM).
    wait_until : str
        Playwright load state to wait for (default "networkidle").

    Returns
    -------
    str
        The rendered page HTML.

    Raises
    ------
    RuntimeError
        If Playwright (and its browser) is not installed.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:  # pragma: no cover - exercised only without dep
        raise RuntimeError(
            "Playwright is required for JavaScript-rendered sources (e.g. ACB). "
            "Install it and run `python -m playwright install chromium`."
        ) from exc

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            context = browser.new_context(user_agent=DEFAULT_USER_AGENT)
            page = context.new_page()
            page.goto(url, timeout=timeout_ms, wait_until=wait_until)
            if wait_selector:
                page.wait_for_selector(wait_selector, timeout=timeout_ms)
            return page.content()
        finally:
            browser.close()
