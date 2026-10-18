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

import csv
import io

from . import hapi_client
from .converter import build_patient, clinical_record_to_fhir_bundle, get_patient_id_from_bundle
from .data_dictionary import DATA_DICTIONARY, EVENTS, MISSING_DATA_CODES
from .db import (
    count_records,
    create_event,
    create_patient,
    create_record,
    delete_event,
    delete_patient,
    delete_record,
    get_audit_log,
    get_event_record,
    get_instrument_audit_log,
    get_instrument_data,
    get_or_create_record_event,
    get_patient,
    get_record,
    get_record_status,
    init_db,
    list_events,
    list_instrument_event_map,
    list_patients,
    list_records,
    set_fhir_bundle_id,
    set_instrument_event_map,
    update_event,
    update_patient,
    update_record,
    upsert_instrument_data,
)
from .fhir_store import (
    count_resources,
    get_resource,
    init_fhir_store,
    list_all_index,
    save_resource,
    search_resources,
)
from .models import InstrumentSubmission, PatientCreate, PatientRecord, PatientRecordUpdate, PatientUpdate
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
    try:
        return create_record(record.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


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


async def _put_patient_to_hapi(resource: dict[str, Any]) -> dict[str, Any]:
    """PUT a FHIR Patient resource directly to HAPI and return a summary dict. Never raises."""
    try:
        hapi_response = await hapi_client.put_resource("Patient", resource["id"], resource)
    except Exception as exc:
        return {"status": "unavailable", "detail": str(exc)}
    return {"status": "ok", "patient_id": hapi_response.get("id")}


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


@app.post("/api/patients/{patient_id}/convert")
async def convert_patient_to_fhir(patient_id: str) -> dict[str, Any]:
    """Convert a patient's demographics to a FHIR Patient resource, persist locally, and PUT to HAPI."""
    patient = get_patient(patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    resource: dict[str, Any] = build_patient(patient)
    resource_id = save_resource(resource)
    hapi_result = await _put_patient_to_hapi(resource)

    return {
        "resource_id": resource_id,
        "fhir_patient_id": resource["id"],
        "hapi": hapi_result,
        "resource": resource,
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
# Audit log
# ---------------------------------------------------------------------------

@app.get("/api/records/{record_id}/audit")
async def get_record_audit(record_id: str) -> list[dict[str, Any]]:
    return get_audit_log(record_id)


# ---------------------------------------------------------------------------
# Patients list
# ---------------------------------------------------------------------------

@app.post("/api/patients", status_code=201)
async def create_patient_handler(patient: PatientCreate) -> dict[str, Any]:
    return create_patient(patient.model_dump())


@app.get("/api/patients/{patient_id}")
async def get_patient_handler(patient_id: str) -> dict[str, Any]:
    p = get_patient(patient_id)
    if not p:
        raise HTTPException(status_code=404, detail="Patient not found")
    return p


@app.put("/api/patients/{patient_id}")
async def update_patient_handler(patient_id: str, updates: PatientUpdate) -> dict[str, Any]:
    data = updates.model_dump(exclude_unset=True)
    updated = update_patient(patient_id, data)
    if not updated:
        raise HTTPException(status_code=404, detail="Patient not found")
    return updated


@app.delete("/api/patients/{patient_id}")
async def delete_patient_handler(patient_id: str) -> Response:
    if not delete_patient(patient_id):
        raise HTTPException(status_code=404, detail="Patient not found")
    return Response(status_code=204)


@app.get("/api/patients")
async def list_all_patients(
    nhi: str | None = Query(None),
    family_name: str | None = Query(None),
    limit: int = Query(50, le=200),
    offset: int = Query(0),
) -> list[dict[str, Any]]:
    return list_patients(nhi=nhi, family_name=family_name, limit=limit, offset=offset)


# ---------------------------------------------------------------------------
# REDCap instrument / event routes
# ---------------------------------------------------------------------------

@app.get("/api/patients/{patient_id}/record-status")
async def get_patient_record_status(patient_id: str) -> dict[str, Any]:
    if not get_patient(patient_id):
        raise HTTPException(status_code=404, detail="Patient not found")
    return get_record_status(patient_id)


@app.get("/api/patients/{patient_id}/events/{event_name}/instruments/{instrument}")
async def get_instrument_handler(
    patient_id: str, event_name: str, instrument: str
) -> dict[str, Any]:
    if not get_patient(patient_id):
        raise HTTPException(status_code=404, detail="Patient not found")
    try:
        return get_instrument_data(patient_id, event_name, instrument)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/api/patients/{patient_id}/events/{event_name}/instruments/{instrument}")
async def upsert_instrument_handler(
    patient_id: str, event_name: str, instrument: str, body: InstrumentSubmission
) -> dict[str, Any]:
    if not get_patient(patient_id):
        raise HTTPException(status_code=404, detail="Patient not found")
    try:
        return upsert_instrument_data(
            patient_id, event_name, instrument,
            body.fields, body.completion_status, body.instance,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.get("/api/instrument-event-map")
async def get_instrument_event_map() -> list[dict[str, Any]]:
    return list_instrument_event_map()


@app.put("/api/instrument-event-map/{event_id}/{form_name}")
async def update_instrument_event_map(
    event_id: int, form_name: str, body: dict[str, Any]
) -> Response:
    enabled = bool(body.get("enabled", True))
    set_instrument_event_map(event_id, form_name, enabled)
    return Response(status_code=204)


@app.get("/api/patients/{patient_id}/events/{event_name}/instruments/{instrument}/audit")
async def get_instrument_audit_handler(
    patient_id: str, event_name: str, instrument: str
) -> list[dict[str, Any]]:
    if not get_patient(patient_id):
        raise HTTPException(status_code=404, detail="Patient not found")
    try:
        re_id = get_or_create_record_event(patient_id, event_name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return get_instrument_audit_log(re_id)


@app.post("/api/patients/{patient_id}/events/{event_name}/convert")
async def convert_event_to_fhir(patient_id: str, event_name: str) -> dict[str, Any]:
    """Convert all instrument data for a patient at a given event into a FHIR Bundle."""
    if not get_patient(patient_id):
        raise HTTPException(status_code=404, detail="Patient not found")

    rec = get_event_record(patient_id, event_name)
    if not rec:
        raise HTTPException(
            status_code=404,
            detail=f"No data recorded for patient {patient_id!r} at event {event_name!r}",
        )

    bundle: dict[str, Any] = clinical_record_to_fhir_bundle(rec)

    bundle_id = save_resource(bundle, record_id=rec["record_id"])
    for entry in bundle.get("entry", []):
        resource: dict[str, Any] = entry.get("resource", {})
        if resource and resource.get("resourceType") != "Bundle":
            save_resource(resource, record_id=rec["record_id"])

    hapi_result = await _post_bundle_to_hapi(bundle)

    return {
        "bundle_id": bundle_id,
        "resource_count": len(bundle.get("entry", [])),
        "patient_id": get_patient_id_from_bundle(bundle),
        "event_name": event_name,
        "hapi": hapi_result,
        "bundle": bundle,
    }


# ---------------------------------------------------------------------------
# Data dictionary
# ---------------------------------------------------------------------------

@app.get("/api/data-dictionary")
async def get_data_dictionary() -> list[dict[str, Any]]:
    return DATA_DICTIONARY


@app.get("/api/data-dictionary.csv")
async def get_data_dictionary_csv() -> Response:
    headers_map = [
        ("variable_field_name",                       "Variable / Field Name"),
        ("form_name",                                 "Form Name"),
        ("section_header",                            "Section Header"),
        ("field_type",                                "Field Type"),
        ("field_label",                               "Field Label"),
        ("choices_calculations_slider_labels",         "Choices, Calculations, OR Slider Labels"),
        ("field_note",                                "Field Note"),
        ("text_validation_type_or_show_slider_number", "Text Validation Type OR Show Slider Number"),
        ("text_validation_min",                       "Text Validation Min"),
        ("text_validation_max",                       "Text Validation Max"),
        ("identifier",                                "Identifier?"),
        ("branching_logic",                           "Branching Logic (Show field only if...)"),
        ("required_field",                            "Required Field?"),
        ("custom_alignment",                          "Custom Alignment"),
        ("question_number_surveys_only",              "Question Number (surveys only)"),
        ("matrix_group_name",                         "Matrix Group Name"),
        ("matrix_ranking",                            "Matrix Ranking?"),
        ("field_annotation",                          "Field Annotation"),
    ]
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([h for _, h in headers_map])
    for field in DATA_DICTIONARY:
        writer.writerow([field.get(k, "") or "" for k, _ in headers_map])
    return Response(
        content=buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="data_dictionary.csv"'},
    )


# ---------------------------------------------------------------------------
# Reference data — events and missing codes
# ---------------------------------------------------------------------------

@app.get("/api/ref/events")
async def ref_events() -> list[dict[str, Any]]:
    return list_events()


# ---------------------------------------------------------------------------
# Event management
# ---------------------------------------------------------------------------

@app.get("/api/events")
async def list_events_handler() -> list[dict[str, Any]]:
    return list_events()


@app.post("/api/events", status_code=201)
async def create_event_handler(body: dict[str, Any]) -> dict[str, Any]:
    label = (body.get("event_label") or "").strip()
    if not label:
        raise HTTPException(status_code=422, detail="event_label is required")
    return create_event(label)


@app.put("/api/events/{event_id}")
async def update_event_handler(event_id: int, body: dict[str, Any]) -> dict[str, Any]:
    result = update_event(
        event_id,
        event_label=body.get("event_label") or None,
        event_order=body.get("event_order"),
    )
    if not result:
        raise HTTPException(status_code=404, detail="Event not found")
    return result


@app.delete("/api/events/{event_id}")
async def delete_event_handler(event_id: int) -> Response:
    if not delete_event(event_id):
        raise HTTPException(status_code=404, detail="Event not found")
    return Response(status_code=204)


@app.get("/api/ref/missing-codes")
async def ref_missing_codes() -> list[dict[str, Any]]:
    return MISSING_DATA_CODES


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
