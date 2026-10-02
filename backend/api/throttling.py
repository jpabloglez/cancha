"""Rate limiting for the public API."""

from typing import TYPE_CHECKING

from rest_framework.request import Request
from rest_framework.throttling import AnonRateThrottle

if TYPE_CHECKING:  # DRF imports this module while loading views; avoid a cycle.
    from rest_framework.views import APIView


class ExternalClientThrottle(AnonRateThrottle):
    """Per-client-IP limit that only applies to traffic arriving via the proxy.

    The reverse proxy (Caddy) sets ``X-Forwarded-For`` to the real client, so
    requests that carry it come from the public internet and are counted per
    client IP (``NUM_PROXIES`` makes DRF read the proxy-appended address).
    Requests without it come from inside the compose network — the Next.js
    server-side rendering calls the backend directly, all from one IP — and are
    exempt, otherwise every page render would share a single bucket.

    Notes
    -----
    ``cache_page`` answers before the view runs, so cached responses are not
    counted; the limit protects the uncached (database-backed) paths.
    """

    scope = "anon"

    def get_cache_key(self, request: Request, view: "APIView") -> str | None:
        """Return the throttle key, or ``None`` to skip internal requests.

        Parameters
        ----------
        request : rest_framework.request.Request
            Incoming request.
        view : rest_framework.views.APIView
            The view being called.

        Returns
        -------
        str or None
            Cache key for the client, or ``None`` when no limit applies.
        """
        if "HTTP_X_FORWARDED_FOR" not in request.META:
            return None
        return super().get_cache_key(request, view)
