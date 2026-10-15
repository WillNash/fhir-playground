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
  GET    /api/ref/snomed/observations
  GET    /api/ref/snomed/medications
  GET    /api/ref/snomed/allergens
  GET    /api/ref/snomed/smoking
  GET    /api/ref/ethnicity
  GET    /api/ref/regions
  GET    /api/ref/loinc/observations
  GET    /api/stats
"""
from __future__ import annotations
import os
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, Response

from .db import (
    init_db, create_record, get_record, update_record, delete_record,
    list_records, set_fhir_bundle_id, count_records,
)
from .fhir_store import (
    init_fhir_store, save_resource, get_resource,
    search_resources, list_all_index, count_resources,
)
from .converter import clinical_record_to_fhir_bundle, get_patient_id_from_bundle
from .models import PatientRecord, PatientRecordUpdate
from .snomed import (
    CONDITIONS, OBSERVATIONS, MEDICATIONS, ALLERGENS,
    SMOKING_STATUS, NZ_ETHNICITY, NZ_REGIONS, ALCOHOL_STATUS,
)

app = FastAPI(
    title="FHIR NZ Demo",
    description="NZ-flavoured FHIR R4 exploration platform",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup() -> None:
    init_db()
    init_fhir_store()


# ---------------------------------------------------------------------------
# Clinical records API
# ---------------------------------------------------------------------------

@app.post("/api/records", status_code=201)
async def create_patient_record(record: PatientRecord) -> Dict[str, Any]:
    data = record.model_dump()
    saved = create_record(data)
    return saved


@app.get("/api/records")
async def list_patient_records(
    nhi: Optional[str] = Query(None),
    family_name: Optional[str] = Query(None),
    encounter_date: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
    offset: int = Query(0),
) -> List[Dict[str, Any]]:
    return list_records(nhi=nhi, family_name=family_name,
                         encounter_date=encounter_date, limit=limit, offset=offset)


@app.get("/api/records/{record_id}")
async def get_patient_record(record_id: str) -> Dict[str, Any]:
    rec = get_record(record_id)
    if not rec:
        raise HTTPException(status_code=404, detail="Record not found")
    return rec


@app.put("/api/records/{record_id}")
async def update_patient_record(record_id: str, updates: PatientRecordUpdate) -> Dict[str, Any]:
    data = {k: v for k, v in updates.model_dump().items() if v is not None}
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
async def convert_to_fhir(record_id: str) -> Dict[str, Any]:
    """Convert a clinical record to a FHIR R4 Bundle and persist it."""
    rec = get_record(record_id)
    if not rec:
        raise HTTPException(status_code=404, detail="Clinical record not found")

    bundle = clinical_record_to_fhir_bundle(rec)
    bundle_id = save_resource(bundle, record_id=record_id)
    set_fhir_bundle_id(record_id, bundle_id)

    # Persist each individual resource so the FHIR Store shows one row per resource
    for entry in bundle.get("entry", []):
        resource = entry.get("resource", {})
        if resource and resource.get("resourceType") != "Bundle":
            save_resource(resource, record_id=record_id)

    return {
        "bundle_id": bundle_id,
        "resource_count": len(bundle.get("entry", [])),
        "patient_id": get_patient_id_from_bundle(bundle),
        "bundle": bundle,
    }


# ---------------------------------------------------------------------------
# FHIR store API
# ---------------------------------------------------------------------------

@app.get("/api/fhir/all")
async def list_all_fhir(limit: int = Query(100), offset: int = Query(0)) -> List[Dict[str, Any]]:
    return list_all_index(limit=limit, offset=offset)


@app.get("/api/fhir")
async def search_fhir(
    resource_type: Optional[str] = Query(None),
    patient_id: Optional[str] = Query(None),
    nhi_number: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    subject_name: Optional[str] = Query(None),
    record_id: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
    offset: int = Query(0),
) -> List[Dict[str, Any]]:
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
async def get_fhir_resource(resource_id: str) -> Any:
    resource = get_resource(resource_id)
    if not resource:
        raise HTTPException(status_code=404, detail="FHIR resource not found")
    return JSONResponse(content=resource, media_type="application/fhir+json")


# ---------------------------------------------------------------------------
# Reference data endpoints (for populating dropdowns)
# ---------------------------------------------------------------------------

@app.get("/api/ref/snomed/conditions")
async def ref_conditions() -> Dict[str, str]:
    return {k: v for k, v in CONDITIONS.items() if v}


@app.get("/api/ref/snomed/observations")
async def ref_observations() -> Dict[str, Any]:
    return OBSERVATIONS


@app.get("/api/ref/snomed/medications")
async def ref_medications() -> Dict[str, Any]:
    return MEDICATIONS


@app.get("/api/ref/snomed/allergens")
async def ref_allergens() -> Dict[str, str]:
    return ALLERGENS


@app.get("/api/ref/snomed/smoking")
async def ref_smoking() -> Dict[str, str]:
    return SMOKING_STATUS


@app.get("/api/ref/snomed/alcohol")
async def ref_alcohol() -> Dict[str, str]:
    return ALCOHOL_STATUS


@app.get("/api/ref/ethnicity")
async def ref_ethnicity() -> Dict[str, str]:
    return NZ_ETHNICITY


@app.get("/api/ref/regions")
async def ref_regions() -> List[str]:
    return NZ_REGIONS


@app.get("/api/ref/loinc/observations")
async def ref_loinc() -> Dict[str, Any]:
    return OBSERVATIONS


@app.get("/api/stats")
async def stats() -> Dict[str, Any]:
    return {
        "clinical_records": count_records(),
        "fhir_resources": count_resources(),
    }


# ---------------------------------------------------------------------------
# Serve the frontend — must be LAST (catch-all route)
# ---------------------------------------------------------------------------

FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend")

if os.path.isdir(FRONTEND_DIR):
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

    @app.get("/")
    async def serve_index() -> FileResponse:
        return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))

    @app.get("/{full_path:path}")
    async def catch_all(full_path: str) -> FileResponse:
        return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))
