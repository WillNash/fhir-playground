"""
FHIR NZ Demo - FastAPI backend
================================
Routes
------
Clinical records (raw data layer)
  POST   /api/records              Create a new patient encounter record
  GET    /api/records              List / search records
  GET    /api/records/{id}         Get a single record
  PUT    /api/records/{id}         Update a record
  DELETE /api/records/{id}         Delete a record

FHIR layer
  POST   /api/records/{id}/convert  Convert clinical record -> FHIR Bundle
  GET    /api/fhir                  Search FHIR index
  GET    /api/fhir/{id}             Get a raw FHIR resource / Bundle JSON

Reference data
  GET    /api/ref/snomed/conditions
  GET    /api/ref/snomed/medications
  GET    /api/ref/snomed/allergens
  GET    /api/ref/snomed/smoking
  GET    /api/ref/ethnicity
  GET    /api/ref/regions
  GET    /api/ref/loinc/observations
  GET    /api/stats
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncGenerator

import httpx
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from . import hapi_client
from .converter import clinical_record_to_fhir_bundle, get_patient_id_from_bundle
from .db import (
    count_records,
    create_record,
    delete_record,
    get_record,
    init_db,
    list_records,
    set_fhir_bundle_id,
    update_record,
)
from .fhir_store import (
    count_resources,
    get_resource,
    init_fhir_store,
    list_all_index,
    save_resource,
    search_resources,
)
from .models import PatientRecord, PatientRecordUpdate
from .snomed import (
    ALCOHOL_STATUS,
    ALLERGENS,
    CONDITIONS,
    MEDICATIONS,
    NZ_ETHNICITY,
    NZ_REGIONS,
    OBSERVATIONS,
    SMOKING_STATUS,
)

# ---------------------------------------------------------------------------
# Application setup
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    init_db()
    init_fhir_store()
    await hapi_client.startup()
    try:
        yield
    finally:
        await hapi_client.shutdown()


app = FastAPI(
    title="FHIR NZ Demo",
    description="NZ-flavoured FHIR R4 exploration platform",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Clinical records API
# ---------------------------------------------------------------------------

@app.post("/api/records", status_code=201)
async def create_patient_record(record: PatientRecord) -> dict[str, Any]:
    return create_record(record.model_dump())


@app.get("/api/records")
async def list_patient_records(
    nhi: str | None = Query(None),
    family_name: str | None = Query(None),
    encounter_date: str | None = Query(None),
    limit: int = Query(50, le=200),
    offset: int = Query(0),
) -> list[dict[str, Any]]:
    return list_records(
        nhi=nhi,
        family_name=family_name,
        encounter_date=encounter_date,
        limit=limit,
        offset=offset,
    )


@app.get("/api/records/{record_id}")
async def get_patient_record(record_id: str) -> dict[str, Any]:
    rec = get_record(record_id)
    if not rec:
        raise HTTPException(status_code=404, detail="Record not found")
    return rec


@app.put("/api/records/{record_id}")
async def update_patient_record(
    record_id: str, updates: PatientRecordUpdate
) -> dict[str, Any]:
    data = updates.model_dump(exclude_unset=True)
    updated = update_record(record_id, data)
    if not updated:
        raise HTTPException(status_code=404, detail="Record not found")
    return updated


@app.delete("/api/records/{record_id}")
async def delete_patient_record(record_id: str) -> Response:
    if not delete_record(record_id):
        raise HTTPException(status_code=404, detail="Record not found")
    return Response(status_code=204)


# ---------------------------------------------------------------------------
# FHIR conversion
# ---------------------------------------------------------------------------

@app.post("/api/records/{record_id}/convert")
async def convert_to_fhir(record_id: str) -> dict[str, Any]:
    """Convert a clinical record to a FHIR R4 Bundle, persist locally, and POST to HAPI."""
    rec = get_record(record_id)
    if not rec:
        raise HTTPException(status_code=404, detail="Clinical record not found")

    bundle: dict[str, Any] = clinical_record_to_fhir_bundle(rec)

    # Persist locally (file store + SQLite index).
    bundle_id = save_resource(bundle, record_id=record_id)
    set_fhir_bundle_id(record_id, bundle_id)
    for entry in bundle.get("entry", []):
        resource: dict[str, Any] = entry.get("resource", {})
        if resource and resource.get("resourceType") != "Bundle":
            save_resource(resource, record_id=record_id)

    # POST transaction bundle to HAPI.
    # Failure is captured and reported but does not fail the route — HAPI is optional.
    hapi_result = await _post_bundle_to_hapi(bundle)

    return {
        "bundle_id": bundle_id,
        "resource_count": len(bundle.get("entry", [])),
        "patient_id": get_patient_id_from_bundle(bundle),
        "hapi": hapi_result,
        "bundle": bundle,
    }


async def _post_bundle_to_hapi(bundle: dict[str, Any]) -> dict[str, Any]:
    """POST a FHIR transaction bundle to HAPI and return a summary dict.

    Returns a status dict with ``"ok"`` or ``"unavailable"`` — never raises.
    """
    try:
        hapi_response = await hapi_client.post_bundle(bundle)
    except Exception as exc:  # HAPI is optional; surface the error without failing the route
        return {"status": "unavailable", "detail": str(exc)}

    hapi_patient_id: str | None = None
    for entry in hapi_response.get("entry", []):
        loc: str = entry.get("response", {}).get("location", "")
        if loc.startswith("Patient/"):
            hapi_patient_id = loc.split("/")[1].split("/_history")[0]
            break

    return {
        "status": "ok",
        "patient_id": hapi_patient_id,
        "entry_count": len(hapi_response.get("entry", [])),
    }


# ---------------------------------------------------------------------------
# FHIR store API
# ---------------------------------------------------------------------------

@app.get("/api/fhir/all")
async def list_all_fhir(
    limit: int = Query(100), offset: int = Query(0)
) -> list[dict[str, Any]]:
    return list_all_index(limit=limit, offset=offset)


@app.get("/api/fhir")
async def search_fhir(
    resource_type: str | None = Query(None),
    patient_id: str | None = Query(None),
    nhi_number: str | None = Query(None),
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    subject_name: str | None = Query(None),
    record_id: str | None = Query(None),
    limit: int = Query(50, le=200),
    offset: int = Query(0),
) -> list[dict[str, Any]]:
    return search_resources(
        resource_type=resource_type,
        patient_id=patient_id,
        nhi_number=nhi_number,
        date_from=date_from,
        date_to=date_to,
        subject_name=subject_name,
        record_id=record_id,
        limit=limit,
        offset=offset,
    )


@app.get("/api/fhir/{resource_id}")
async def get_fhir_resource(resource_id: str) -> JSONResponse:
    resource = get_resource(resource_id)
    if not resource:
        raise HTTPException(status_code=404, detail="FHIR resource not found")
    return JSONResponse(content=resource, media_type="application/fhir+json")


# ---------------------------------------------------------------------------
# Reference data endpoints (for populating dropdowns)
# ---------------------------------------------------------------------------

@app.get("/api/ref/snomed/conditions")
async def ref_conditions() -> dict[str, str]:
    return {k: v for k, v in CONDITIONS.items() if v}


@app.get("/api/ref/snomed/medications")
async def ref_medications() -> dict[str, Any]:
    return MEDICATIONS


@app.get("/api/ref/snomed/allergens")
async def ref_allergens() -> dict[str, str]:
    return ALLERGENS


@app.get("/api/ref/snomed/smoking")
async def ref_smoking() -> dict[str, str]:
    return SMOKING_STATUS


@app.get("/api/ref/snomed/alcohol")
async def ref_alcohol() -> dict[str, str]:
    return ALCOHOL_STATUS


@app.get("/api/ref/ethnicity")
async def ref_ethnicity() -> dict[str, str]:
    return NZ_ETHNICITY


@app.get("/api/ref/regions")
async def ref_regions() -> list[str]:
    return NZ_REGIONS


@app.get("/api/ref/loinc/observations")
async def ref_loinc() -> dict[str, Any]:
    return OBSERVATIONS


@app.get("/api/stats")
async def stats() -> dict[str, Any]:
    return {
        "clinical_records": count_records(),
        "fhir_resources": count_resources(),
    }


# ---------------------------------------------------------------------------
# HAPI FHIR server — status + transparent GET proxy
# ---------------------------------------------------------------------------

@app.get("/api/hapi-status")
async def get_hapi_status() -> dict[str, Any]:
    available = await hapi_client.is_available()
    starting = (not available) and await hapi_client.is_port_open()
    base: str = hapi_client.HAPI_BASE_URL
    root = base.removesuffix("/fhir")
    return {
        "available": available,
        "starting": starting,
        "url": base,
        "swagger_ui": f"{root}/fhir/swagger-ui/",
    }


@app.get("/api/hapi/{path:path}")
async def hapi_proxy(path: str, request: Request) -> JSONResponse:
    """Transparent GET proxy to HAPI.

    The frontend calls e.g.
      /api/hapi/Patient?identifier=…
      /api/hapi/Patient/abc123/$everything
    and this forwards the request verbatim.
    """
    params = dict(request.query_params)
    try:
        r = await hapi_client.proxy_get(path, params)
        return JSONResponse(
            content=r.json(),
            status_code=r.status_code,
            media_type="application/fhir+json",
        )
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="HAPI FHIR server is not reachable")
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=exc.response.status_code, detail=exc.response.text)


# ---------------------------------------------------------------------------
# Serve the frontend — must be LAST (catch-all route)
# ---------------------------------------------------------------------------

_FRONTEND_DIR = Path(__file__).parent.parent / "frontend"

if _FRONTEND_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=_FRONTEND_DIR), name="static")

    @app.get("/")
    async def serve_index() -> FileResponse:
        return FileResponse(_FRONTEND_DIR / "index.html")

    @app.get("/{full_path:path}")
    async def catch_all(full_path: str) -> FileResponse:  # noqa: ARG001
        return FileResponse(_FRONTEND_DIR / "index.html")
