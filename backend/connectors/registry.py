"""Connector registry.

Central lookup mapping a connector id to its :class:`SourceConnector` factory,
so the ingestion layer can resolve a connector without importing each module
directly (spec §3.2).
"""

from collections.abc import Callable

from .acb import build_acb_connector
from .base import SourceConnector
from .feb import build_primera_feb_connector, build_segunda_feb_connector

#: Mapping of connector id -> zero-argument factory returning a connector.
CONNECTOR_FACTORIES: dict[str, Callable[[], SourceConnector]] = {
    "acb": build_acb_connector,
    "feb-primera": build_primera_feb_connector,
    "feb-segunda": build_segunda_feb_connector,
}


def get_connector(connector_id: str) -> SourceConnector:
    """Resolve and instantiate a connector by its identifier.

    Parameters
    ----------
    connector_id : str
        Registered connector id (e.g. "acb", "feb-primera").

    Returns
    -------
    SourceConnector
        A freshly constructed connector instance.

    Raises
    ------
    KeyError
        If no connector is registered under ``connector_id``.
    """
    try:
        factory = CONNECTOR_FACTORIES[connector_id]
    except KeyError as exc:
        raise KeyError(f"Unknown connector id: {connector_id!r}") from exc
    return factory()
