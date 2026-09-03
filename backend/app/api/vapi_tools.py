import logging
import uuid
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, status
from phonenumbers import (
    PhoneNumberFormat,
    format_number,
    is_valid_number,
    parse,
    region_code_for_number,
)
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.qualification.validators import validate_name, validate_phone
from app.ai.scheduling.outcomes import BookingOutcome
from app.database.session import get_db
from app.integrations.vapi.security import (
    create_availability_token,
    decode_availability_token,
    verify_vapi_tool_request,
)
from app.models.phone_number import PhoneNumber
from app.models.provider import Provider
from app.models.service import Service
from app.models.workspace import Workspace
from app.services.phone_numbers import normalize_e164
from app.schemas.vapi import (
    FLAT_TOOL_CALL_NAME,
    BookAppointmentArguments,
    CheckAvailabilityArguments,
    VapiToolCall,
    VapiToolRequest,
    VapiToolResponse,
    VapiToolResult,
)
from app.services.scheduling import AppointmentBookingRequest, AppointmentSchedulingService

logger = logging.getLogger(__name__)

# Explicit per-workspace routes: the workspace is named in the URL.
router = APIRouter(
    prefix="/integrations/vapi/workspaces/{workspace_id}/tools",
    tags=["vapi-tools"],
    dependencies=[Depends(verify_vapi_tool_request)],
)

# Dynamic routes: the workspace is resolved from the call's phone number.
# Same Vapi authentication as the explicit routes — an unauthenticated or
# wrongly-signed request never reaches availability or booking.
dynamic_router = APIRouter(
    prefix="/integrations/vapi/tools",
    tags=["vapi-tools"],
    dependencies=[Depends(verify_vapi_tool_request)],
)


def _result(tool_call: VapiToolCall, result: dict) -> VapiToolResult:
    return VapiToolResult(toolCallId=tool_call.id, result=result)


def _argument_error(tool_call: VapiToolCall, exc: ValidationError) -> VapiToolResult:
    """Name the offending fields.

    Joining the raw messages produced "Field required; Field required",
    which tells the assistant nothing it can act on. Naming each field
    lets it ask the caller for what is actually missing.
    """
    details = []
    missing = []
    for error in exc.errors():
        field = ".".join(str(part) for part in error["loc"]) or "body"
        details.append(f"{field}: {error['msg']}")
        if error["type"] == "missing":
            missing.append(field)
    return _result(
        tool_call,
        {
            "success": False,
            "code": "INVALID_ARGUMENTS",
            "message": "; ".join(details),
            "missing_arguments": missing,
        },
    )


def _workspace_or_404(db: Session, workspace_id: uuid.UUID) -> Workspace:
    workspace = db.get(Workspace, workspace_id)
    if workspace is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")
    return workspace


def _workspace_from_vapi_request(db: Session, payload: VapiToolRequest) -> Workspace:
    """Resolve the workspace for a dynamic-routed Vapi call from its phone number.

    The dialed number decides the workspace; the caller's number is only a
    fallback (see ``VapiToolRequest.routing_phone_numbers``). The caller can
    never supply a ``workspace_id`` on this path.
    """
    candidates = [normalize_e164(number) for number in payload.routing_phone_numbers]
    candidates = [number for number in candidates if number]
    if not candidates:
        logger.info("vapi dynamic routing: request carried no usable phone number")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The Vapi call phone number is required for routing.",
        )

    for number in candidates:
        phone_number = db.execute(
            select(PhoneNumber).where(PhoneNumber.number == number)
        ).scalar_one_or_none()
        if phone_number is not None:
            workspace = _workspace_or_404(db, phone_number.workspace_id)
            logger.info(
                "vapi dynamic routing: resolved workspace %s", workspace.id
            )
            return workspace

    logger.info(
        "vapi dynamic routing: no workspace assigned to any candidate number (%d tried)",
        len(candidates),
    )
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="No workspace is assigned to this phone number.",
    )


def _active_service_names(db: Session, workspace_id: uuid.UUID) -> list[str]:
    return list(
        db.execute(
            select(Service.name)
            .where(Service.workspace_id == workspace_id, Service.is_active.is_(True))
            .order_by(Service.name)
        ).scalars()
    )


def _active_provider_names(db: Session, workspace_id: uuid.UUID) -> list[str]:
    return list(
        db.execute(
            select(Provider.name)
            .where(Provider.workspace_id == workspace_id, Provider.is_active.is_(True))
            .order_by(Provider.name)
        ).scalars()
    )


def _first_free_provider(
    db: Session,
    scheduling: AppointmentSchedulingService,
    workspace: Workspace,
    service,
    start_time: datetime,
):
    """Pick a doctor who is actually free, when the caller named none.

    Mirrors how availability offers slots: any active provider will do,
    so long as the slot is genuinely open for them.
    """
    providers = db.execute(
        select(Provider)
        .where(Provider.workspace_id == workspace.id, Provider.is_active.is_(True))
        .order_by(Provider.name)
    ).scalars()
    for provider in providers:
        if scheduling.is_slot_available(
            workspace, service, provider, start_time, enforce_business_hours=True
        ):
            return provider
    return None


def _caller_region(payload: VapiToolRequest) -> str | None:
    """Country to read a patient number against when it has no country code.

    The caller's own number decides this, not the number they dialled.
    ``routing_phone_numbers`` puts the dialled number first because that
    is what identifies the clinic, but a Pakistani patient ringing a US
    clinic line would then have "0324 5929020" read as American and
    rejected. Reversed, the caller comes first and the clinic line is
    only a fallback.
    """
    for number in reversed(payload.routing_phone_numbers):
        try:
            parsed = parse(number, None)
        except Exception:
            continue
        region = region_code_for_number(parsed)
        if region:
            return region
    return None


def _normalize_patient_phone(number: str, region: str | None) -> str | None:
    """Return a patient phone in E.164, or None when it cannot be read.

    Deliberately more forgiving than ``normalize_e164``, which routing
    uses: a clinic line is configured once by staff and can be required
    to carry its country code, but a patient says their number out loud
    in local form ("0300 1234567") far more often than in E.164.
    Parsing against no region rejected almost every real booking. An
    explicit country code is still tried first so it always wins.
    """
    cleaned = (number or "").strip()
    if not cleaned:
        return None
    for candidate_region in (None, region):
        if candidate_region is None and not cleaned.startswith("+"):
            continue
        try:
            parsed = parse(cleaned, candidate_region)
        except Exception:
            continue
        if is_valid_number(parsed):
            return format_number(parsed, PhoneNumberFormat.E164)
    return None


def _log_booking_response(
    workspace_id: uuid.UUID,
    call_id: str | None,
    response: VapiToolResponse,
) -> None:
    """Record what booking actually returned to Vapi.

    Without this a failed booking is invisible from the outside: the
    caller is told something went wrong and the access log shows a 200.
    """
    logger.info(
        "vapi book-appointment complete: %d result(s), %d booked",
        len(response.results),
        sum(item.result.get("success") is True for item in response.results),
        extra={
            "event": "vapi_book_appointment_response",
            "vapi_workspace_id": str(workspace_id),
            "vapi_call_id": call_id,
            "results": [
                {
                    "tool_call_id": item.tool_call_id,
                    "success": item.result.get("success"),
                    "code": item.result.get("code"),
                    "message": item.result.get("message"),
                    "appointment_id": item.result.get("appointment_id"),
                }
                for item in response.results
            ],
        },
    )


@router.post("/check-availability", response_model=VapiToolResponse)
def check_availability(
    workspace_id: uuid.UUID,
    payload: VapiToolRequest,
    db: Session = Depends(get_db),
) -> VapiToolResponse:
    workspace = _workspace_or_404(db, workspace_id)
    scheduling = AppointmentSchedulingService(db)
    results: list[VapiToolResult] = []

    for tool_call in payload.message.tool_call_list:
        if tool_call.name not in ("check_availability", FLAT_TOOL_CALL_NAME):
            results.append(_result(tool_call, {"success": False, "code": "INVALID_TOOL", "message": "Expected check_availability"}))
            continue
        try:
            args = CheckAvailabilityArguments.model_validate(tool_call.arguments)
        except ValidationError as exc:
            results.append(_argument_error(tool_call, exc))
            continue

        service = scheduling.resolve_service(
            workspace.id, service_id=args.service_id, service_name=args.service_name
        )
        if service is None:
            # The assistant has no other way to learn what this clinic
            # offers, so it guesses, and a caller speaking Urdu makes it
            # guess in Urdu -- which never matches an English service
            # name. Returning the real list lets the call recover in one
            # turn instead of dead-ending in an apology.
            results.append(
                _result(
                    tool_call,
                    {
                        "success": False,
                        "code": "SERVICE_NOT_FOUND",
                        "message": (
                            "That service was not found. Read the available services to "
                            "the caller, ask which one they need, and check again using "
                            "the name exactly as listed."
                        ),
                        "available_services": _active_service_names(db, workspace.id),
                    },
                )
            )
            continue

        provider_requested = args.provider_id is not None or args.provider_name is not None
        provider = scheduling.resolve_provider(
            workspace.id, provider_id=args.provider_id, provider_name=args.provider_name
        )
        if provider_requested and provider is None and (args.provider_name or "").strip().lower() not in {
            "any", "no preference", "no_preference"
        }:
            results.append(
                _result(
                    tool_call,
                    {
                        "success": False,
                        "code": "PROVIDER_NOT_FOUND",
                        "message": (
                            "That doctor was not found. Read the available doctors to the "
                            "caller, or omit the doctor entirely if they have no preference."
                        ),
                        "available_providers": _active_provider_names(db, workspace.id),
                    },
                )
            )
            continue

        try:
            availability = scheduling.find_available_slots(
                workspace,
                service,
                preferred_date=args.preferred_date,
                preferred_time=args.preferred_time,
                provider=provider,
                max_slots=args.max_slots,
            )
        except ValueError as exc:
            results.append(_result(tool_call, {"success": False, "code": "INVALID_CLINIC_TIMEZONE", "message": str(exc)}))
            continue

        clinic_tz = ZoneInfo(workspace.timezone)
        slots = []
        for slot in availability.slots:
            token = create_availability_token(
                workspace_id=workspace.id,
                service_id=service.id,
                provider_id=slot.provider.id,
                start_time=slot.start_time,
                end_time=slot.end_time,
            )
            start_local = slot.start_time.astimezone(clinic_tz)
            end_local = slot.end_time.astimezone(clinic_tz)
            slots.append(
                {
                    "provider_id": str(slot.provider.id),
                    "provider_name": slot.provider.name,
                    "start_time": start_local.isoformat(),
                    "end_time": end_local.isoformat(),
                    "availability_token": token,
                }
            )

        result = {
            "success": bool(slots),
            "code": availability.code or "AVAILABLE",
            "message": availability.message or "Available appointment slots were found.",
            "timezone": workspace.timezone,
            "service": {
                "id": str(service.id),
                "name": service.name,
                "duration_minutes": service.duration_minutes,
            },
            "available_slots": slots,
            "availability_token": slots[0]["availability_token"] if slots else None,
        }
        results.append(_result(tool_call, result))

    return VapiToolResponse(results=results)


@router.post("/book-appointment", response_model=VapiToolResponse)
def book_appointment(
    workspace_id: uuid.UUID,
    payload: VapiToolRequest,
    db: Session = Depends(get_db),
) -> VapiToolResponse:
    workspace = _workspace_or_404(db, workspace_id)
    scheduling = AppointmentSchedulingService(db)
    results: list[VapiToolResult] = []

    for tool_call in payload.message.tool_call_list:
        if tool_call.name not in ("book_appointment", FLAT_TOOL_CALL_NAME):
            results.append(_result(tool_call, {"success": False, "code": "INVALID_TOOL", "message": "Expected book_appointment"}))
            continue
        try:
            args = BookAppointmentArguments.model_validate(tool_call.arguments)
        except ValidationError as exc:
            results.append(_argument_error(tool_call, exc))
            continue

        # The call id is only an idempotency key. A payload that omits the
        # call object is still a valid booking request, so fall back to
        # the tool call id (unique per Vapi invocation, and replayed
        # unchanged on a Vapi retry) rather than refusing outright.
        idempotency_call_id = payload.call_id or f"vapi-tool:{tool_call.id}"
        if not payload.call_id:
            logger.warning(
                "vapi book-appointment: no call id on the request, keying idempotency on tool call %s",
                tool_call.id,
                extra={
                    "event": "vapi_book_appointment_missing_call_id",
                    "vapi_workspace_id": str(workspace_id),
                    "vapi_tool_call_id": tool_call.id,
                },
            )
        if not validate_name(args.patient_name):
            results.append(_result(tool_call, {"success": False, "code": "INVALID_PATIENT_NAME", "message": "A valid patient name is required."}))
            continue
        patient_phone = _normalize_patient_phone(args.patient_phone, _caller_region(payload))
        if patient_phone is None or not validate_phone(patient_phone):
            results.append(
                _result(
                    tool_call,
                    {
                        "success": False,
                        "code": "INVALID_PATIENT_PHONE",
                        "message": "That phone number could not be read. Ask the caller to repeat it, including the country code.",
                    },
                )
            )
            continue

        if args.availability_token:
            try:
                token = decode_availability_token(args.availability_token)
            except ValueError as exc:
                results.append(_result(tool_call, {"success": False, "code": "INVALID_AVAILABILITY_TOKEN", "message": str(exc)}))
                continue
            if token.workspace_id != workspace.id:
                results.append(_result(tool_call, {"success": False, "code": "INVALID_AVAILABILITY_TOKEN", "message": "The token belongs to another clinic."}))
                continue

            service = scheduling.resolve_service(workspace.id, service_id=token.service_id)
            provider = scheduling.resolve_provider(workspace.id, provider_id=token.provider_id)
            if service is None or provider is None:
                results.append(_result(tool_call, {"success": False, "code": "CONFIGURATION_CHANGED", "message": "The service or provider is no longer available."}))
                continue
            expected_end = token.start_time.astimezone(timezone.utc) + timedelta(minutes=service.duration_minutes)
            if token.end_time.astimezone(timezone.utc) != expected_end:
                results.append(_result(tool_call, {"success": False, "code": "INVALID_AVAILABILITY_TOKEN", "message": "The token duration is invalid."}))
                continue
            start_time = token.start_time
        else:
            # No token: the caller named a time and the assistant passed it
            # straight through. Everything is re-resolved and re-checked
            # here, so this path grants nothing the token path did not.
            service = scheduling.resolve_service(
                workspace.id, service_id=args.service_id, service_name=args.service_name
            )
            if service is None:
                results.append(
                    _result(
                        tool_call,
                        {
                            "success": False,
                            "code": "SERVICE_NOT_FOUND",
                            "message": (
                                "That service was not found. Read the available services to "
                                "the caller and book using the name exactly as listed."
                            ),
                            "available_services": _active_service_names(db, workspace.id),
                        },
                    )
                )
                continue
            try:
                clinic_zone = ZoneInfo(workspace.timezone)
            except Exception as exc:
                results.append(_result(tool_call, {"success": False, "code": "INVALID_CLINIC_TIMEZONE", "message": str(exc)}))
                continue
            start_time = datetime.combine(
                args.preferred_date, args.preferred_time, tzinfo=clinic_zone
            )
            provider = scheduling.resolve_provider(
                workspace.id, provider_name=args.provider_name
            )
            if provider is None:
                provider = _first_free_provider(db, scheduling, workspace, service, start_time)
            if provider is None:
                results.append(
                    _result(
                        tool_call,
                        {
                            "success": False,
                            "code": "SLOT_TAKEN",
                            "message": (
                                "No doctor is free at that time. Check availability again "
                                "and offer the caller the times that come back."
                            ),
                        },
                    )
                )
                continue

        note = f"Booked via Vapi ({service.name})"
        if args.reason:
            note += f" - {args.reason}"
        # An exception escaping here becomes a bare HTTP 500, which reaches
        # Vapi as no tool result at all: the assistant has nothing to say
        # and the caller hears silence or a false confirmation. A live call
        # always gets a result back, even when the booking fails.
        try:
            booking = scheduling.book_appointment(
                AppointmentBookingRequest(
                    workspace=workspace,
                    service=service,
                    provider=provider,
                    start_time=start_time,
                    patient_name=args.patient_name,
                    patient_phone=patient_phone,
                    patient_email=str(args.patient_email) if args.patient_email else None,
                    notes=note,
                    source="Vapi",
                    vapi_call_id=idempotency_call_id,
                    vapi_tool_call_id=tool_call.id,
                    enforce_business_hours=True,
                )
            )
        except Exception:
            db.rollback()
            logger.exception(
                "vapi book-appointment failed for workspace %s",
                workspace_id,
                extra={
                    "event": "vapi_book_appointment_failed",
                    "vapi_workspace_id": str(workspace_id),
                    "vapi_call_id": payload.call_id,
                    "vapi_tool_call_id": tool_call.id,
                },
            )
            results.append(
                _result(
                    tool_call,
                    {
                        "success": False,
                        "code": "BOOKING_FAILED",
                        "message": "The appointment could not be saved. Offer to take a message or transfer the caller.",
                    },
                )
            )
            continue

        if booking.outcome == BookingOutcome.DUPLICATE:
            results.append(_result(tool_call, {"success": False, "code": "DUPLICATE_BOOKING", "message": "This patient already has an overlapping appointment."}))
            continue
        if booking.outcome == BookingOutcome.CONFLICT or booking.appointment is None:
            results.append(_result(tool_call, {"success": False, "code": "SLOT_TAKEN", "message": "That appointment slot is no longer available. Please check availability again."}))
            continue

        appointment = booking.appointment
        db.refresh(appointment)
        clinic_tz = ZoneInfo(workspace.timezone)
        results.append(
            _result(
                tool_call,
                {
                    "success": True,
                    "code": "BOOKED",
                    "status": appointment.status,
                    "appointment_id": str(appointment.id),
                    "service": {"id": str(service.id), "name": service.name},
                    "provider": {"id": str(provider.id), "name": provider.name},
                    "start_time": appointment.start_time.replace(tzinfo=timezone.utc).astimezone(clinic_tz).isoformat()
                    if appointment.start_time.tzinfo is None
                    else appointment.start_time.astimezone(clinic_tz).isoformat(),
                    "end_time": appointment.end_time.replace(tzinfo=timezone.utc).astimezone(clinic_tz).isoformat()
                    if appointment.end_time.tzinfo is None
                    else appointment.end_time.astimezone(clinic_tz).isoformat(),
                    "timezone": workspace.timezone,
                    "calendar_synced": bool(appointment.external_calendar_event_id),
                    "idempotent_replay": booking.idempotent_replay,
                    "message": "The appointment is confirmed.",
                },
            )
        )

    response = VapiToolResponse(results=results)
    _log_booking_response(workspace_id, payload.call_id, response)
    return response


@dynamic_router.post("/check-availability", response_model=VapiToolResponse)
def check_availability_for_vapi_number(
    payload: VapiToolRequest,
    db: Session = Depends(get_db),
) -> VapiToolResponse:
    """Phone-number-routed availability check.

    Vapi is authenticated by the router-level dependency; the workspace is
    then resolved from the dialed/caller number before the same business
    logic as the explicit per-workspace route runs.
    """
    workspace = _workspace_from_vapi_request(db, payload)
    response = check_availability(workspace.id, payload, db)
    logger.info(
        "vapi dynamic check-availability complete for workspace %s: %d result(s)",
        workspace.id,
        len(response.results),
    )
    return response


@dynamic_router.post("/book-appointment", response_model=VapiToolResponse)
def book_appointment_for_vapi_number(
    payload: VapiToolRequest,
    db: Session = Depends(get_db),
) -> VapiToolResponse:
    """Phone-number-routed booking. Same auth + routing as the check above."""
    workspace = _workspace_from_vapi_request(db, payload)
    response = book_appointment(workspace.id, payload, db)
    logger.info(
        "vapi dynamic book-appointment complete for workspace %s: %d result(s)",
        workspace.id,
        len(response.results),
    )
    return response
