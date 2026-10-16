"""
Async HTTP client for the HAPI FHIR JPA server.

All calls use Content-Type / Accept: application/fhir+json per the FHIR spec.
HAPI_BASE_URL is read from the environment (default: http://localhost:8080/fhir).
"""
from __future__ import annotations
import os
from typing import Any, Dict, Optional

import httpx

HAPI_BASE_URL = os.environ.get("HAPI_BASE_URL", "http://localhost:8080/fhir")

_FHIR_HEADERS = {
    "Content-Type": "application/fhir+json",
    "Accept": "application/fhir+json",
}


async def post_bundle(bundle: Dict[str, Any]) -> Dict[str, Any]:
    """POST a FHIR transaction bundle. Returns the transaction-response Bundle."""
    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{HAPI_BASE_URL}/",
            json=bundle,
            headers=_FHIR_HEADERS,
            timeout=60.0,
        )
        r.raise_for_status()
        return r.json()


async def get_resource(resource_type: str, resource_id: str) -> Dict[str, Any]:
    """Read a single resource by type and ID."""
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{HAPI_BASE_URL}/{resource_type}/{resource_id}",
            headers={"Accept": "application/fhir+json"},
            timeout=15.0,
        )
        r.raise_for_status()
        return r.json()


async def search(
    resource_type: str,
    params: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """FHIR search — returns a searchset Bundle."""
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{HAPI_BASE_URL}/{resource_type}",
            params=params or {},
            headers={"Accept": "application/fhir+json"},
            timeout=20.0,
        )
        r.raise_for_status()
        return r.json()


async def patient_everything(
    patient_id: str,
    params: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """GET /Patient/{id}/$everything — all resources linked to a patient."""
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{HAPI_BASE_URL}/Patient/{patient_id}/$everything",
            params=params or {},
            headers={"Accept": "application/fhir+json"},
            timeout=60.0,
        )
        r.raise_for_status()
        return r.json()


async def capability_statement() -> Dict[str, Any]:
    """GET /metadata — HAPI CapabilityStatement (used for health check)."""
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{HAPI_BASE_URL}/metadata",
            headers={"Accept": "application/fhir+json"},
            timeout=10.0,
        )
        r.raise_for_status()
        return r.json()


async def proxy_get(path: str, params: Dict[str, str]) -> httpx.Response:
    """Forward an arbitrary GET request to HAPI and return the raw response."""
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{HAPI_BASE_URL}/{path}",
            params=params,
            headers={"Accept": "application/fhir+json"},
            timeout=30.0,
        )
        return r


async def is_available() -> bool:
    try:
        await capability_statement()
        return True
    except Exception:
        return False
