"""
Async HTTP client for the HAPI FHIR JPA server.

All requests use Content-Type / Accept: application/fhir+json per the FHIR spec.
HAPI_BASE_URL is read from the environment; defaults to http://localhost:8080/fhir.
"""

import asyncio
import os
from urllib.parse import urlparse

import httpx

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

HAPI_BASE_URL: str = os.environ.get("HAPI_BASE_URL", "http://localhost:8080/fhir")

_FHIR_HEADERS: dict[str, str] = {
    "Content-Type": "application/fhir+json",
    "Accept": "application/fhir+json",
}

# FHIR JSON payloads arrive as arbitrary objects — Any is warranted here.
FhirResource = dict[str, object]  # type: ignore[type-arg]

# ---------------------------------------------------------------------------
# Shared client lifecycle — call startup() / shutdown() from the app lifespan
# ---------------------------------------------------------------------------

_shared_client: httpx.AsyncClient | None = None


async def startup() -> None:
    """Create the shared AsyncClient. Call once from the FastAPI lifespan."""
    global _shared_client
    _shared_client = httpx.AsyncClient(base_url=HAPI_BASE_URL, headers=_FHIR_HEADERS)


async def shutdown() -> None:
    """Close the shared AsyncClient. Call once on app shutdown."""
    global _shared_client
    if _shared_client is not None:
        await _shared_client.aclose()
        _shared_client = None


def _client() -> httpx.AsyncClient:
    if _shared_client is None:
        raise RuntimeError("HAPI client not started — call await hapi_client.startup() first")
    return _shared_client


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def post_bundle(bundle: dict[str, object]) -> dict[str, object]:
    """POST a FHIR transaction bundle and return the transaction-response Bundle."""
    response = await _client().post("/", json=bundle, timeout=60.0)
    response.raise_for_status()
    return response.json()  # type: ignore[no-any-return]  # external JSON


async def get_resource(resource_type: str, resource_id: str) -> dict[str, object]:
    """Read a single FHIR resource by type and logical ID."""
    response = await _client().get(f"/{resource_type}/{resource_id}", timeout=15.0)
    response.raise_for_status()
    return response.json()  # type: ignore[no-any-return]  # external JSON


async def search(
    resource_type: str,
    params: dict[str, str] | None = None,
) -> dict[str, object]:
    """Run a FHIR search and return the resulting searchset Bundle."""
    response = await _client().get(f"/{resource_type}", params=params or {}, timeout=20.0)
    response.raise_for_status()
    return response.json()  # type: ignore[no-any-return]  # external JSON


async def patient_everything(
    patient_id: str,
    params: dict[str, str] | None = None,
) -> dict[str, object]:
    """Fetch all resources linked to a patient via GET /Patient/{id}/$everything."""
    response = await _client().get(
        f"/Patient/{patient_id}/$everything", params=params or {}, timeout=60.0
    )
    response.raise_for_status()
    return response.json()  # type: ignore[no-any-return]  # external JSON


async def capability_statement() -> dict[str, object]:
    """Return the server's CapabilityStatement from GET /metadata.

    Also used as the liveness probe — see ``is_available``.
    """
    response = await _client().get("/metadata", timeout=10.0)
    response.raise_for_status()
    return response.json()  # type: ignore[no-any-return]  # external JSON


async def proxy_get(path: str, params: dict[str, str]) -> httpx.Response:
    """Forward an arbitrary GET to HAPI and return the raw response.

    Unlike the other functions here, this deliberately does *not* call
    ``raise_for_status`` — the caller is responsible for forwarding the
    HAPI status code and body verbatim.
    """
    return await _client().get(f"/{path}", params=params, timeout=30.0)


# ---------------------------------------------------------------------------
# Health / readiness probes
# ---------------------------------------------------------------------------


async def is_available() -> bool:
    """Return True if HAPI responds successfully to a metadata request.

    Swallows all exceptions because this is a boolean probe, not a data call.
    """
    try:
        await capability_statement()
        return True
    except Exception:  # noqa: BLE001 — intentional: any failure means unavailable
        return False


async def is_port_open() -> bool:
    """Return True if the TCP port is accepting connections.

    A successful TCP handshake means the container is up, though Spring Boot
    may still be initialising — use ``is_available`` for a full readiness
    check.
    """
    parsed = urlparse(HAPI_BASE_URL)
    host: str = parsed.hostname or "localhost"
    port: int = parsed.port or 8080

    try:
        _, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port),
            timeout=1.0,
        )
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:  # noqa: BLE001 — best-effort close; ignore OS errors
            pass
        return True
    except Exception:  # noqa: BLE001 — any connection failure means port closed
        return False
