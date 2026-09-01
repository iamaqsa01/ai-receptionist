"""Dynamic context-aware onboarding — BusinessType / BusinessContext.

Covers the schema (app/schemas/clinic_settings.py) and the relaxed
first-onboarding gate (app/api/workspaces.py): Software Agency / Real Estate
/ Other workspaces onboard without doctors, services or seven-day clinic
hours, while Clinic and legacy (no business_type) payloads keep the existing
requirement. All context is stored in the existing
``ai_agents.config["clinic_settings"]`` JSON — no new table.
"""

from tests.conftest import auth_headers, create_workspace, register_and_login

AGENCY_CONTEXT = {
    "core_services": ["Web Development", "AI Automation", "Mobile Apps"],
    "minimum_pricing": "$1,000",
    "discovery_call_booking_link": "https://cal.com/nexcore/discovery",
}
REAL_ESTATE_CONTEXT = {
    "property_services": ["Residential Sales", "Commercial Leasing"],
    "areas_served": ["DHA Phase 5", "Gulberg", "Bahria Town"],
    "minimum_budget": "PKR 10,000,000",
    "viewing_booking_link": "https://calendly.com/agent/viewing",
}
OTHER_CONTEXT = {
    "custom_fields": {
        "Industry": "Legal Services",
        "Emergency Contact": "0300-1234567",
        "Consultation Type": "30-minute call",
    },
}
CLINIC_FULL = {
    "doctors": [{"name": "Dr. Sara Khan", "specialty": "Dermatology"}],
    "services": ["Consultation"],
    "business_hours": [
        {
            "day_of_week": d,
            "open_time": "09:00:00" if d < 5 else None,
            "close_time": "17:00:00" if d < 5 else None,
            "is_closed": d >= 5,
        }
        for d in range(7)
    ],
}


def _put(client, token, ws_id, body):
    return client.put(
        f"/api/v1/workspaces/{ws_id}/clinic-settings", headers=auth_headers(token), json=body
    )


def _get(client, token, ws_id):
    return client.get(f"/api/v1/workspaces/{ws_id}/clinic-settings", headers=auth_headers(token))


def _is_onboarded(client, token, ws_id):
    return client.get(f"/api/v1/workspaces/{ws_id}", headers=auth_headers(token)).json()["is_onboarded"]


# --- non-clinic onboarding: no doctors / services / hours required -------------

def test_software_agency_onboards_without_clinic_requirements(client):
    token = register_and_login(client, "agency-owner@example.com")
    ws_id = create_workspace(client, token, "NexCore Agency", "nexcore-agency", onboarded=False)

    r = _put(client, token, ws_id, {"business_type": "Software Agency", "business_context": AGENCY_CONTEXT})
    assert r.status_code == 200, r.text
    assert _is_onboarded(client, token, ws_id) is True

    body = r.json()
    assert body["business_type"] == "Software Agency"
    assert body["business_context"] == AGENCY_CONTEXT
    assert set(body["business_context"].keys()) == set(AGENCY_CONTEXT.keys())
    assert body["doctors"] == [] and body["services"] == []


def test_real_estate_onboards_without_clinic_requirements(client):
    token = register_and_login(client, "realestate-owner@example.com")
    ws_id = create_workspace(client, token, "Prime Estates", "prime-estates", onboarded=False)

    r = _put(client, token, ws_id, {"business_type": "Real Estate", "business_context": REAL_ESTATE_CONTEXT})
    assert r.status_code == 200, r.text
    assert _is_onboarded(client, token, ws_id) is True
    assert r.json()["business_context"] == REAL_ESTATE_CONTEXT


def test_other_onboards_with_custom_fields(client):
    token = register_and_login(client, "other-owner@example.com")
    ws_id = create_workspace(client, token, "Legal Co", "legal-co", onboarded=False)

    r = _put(client, token, ws_id, {"business_type": "Other", "business_context": OTHER_CONTEXT})
    assert r.status_code == 200, r.text
    assert _is_onboarded(client, token, ws_id) is True
    assert r.json()["business_context"]["custom_fields"] == OTHER_CONTEXT["custom_fields"]


# --- Clinic + legacy keep the existing requirement ---------------------------

def test_clinic_business_type_still_requires_doctors_services_hours(client):
    token = register_and_login(client, "clinic-strict-owner@example.com")
    ws_id = create_workspace(client, token, "Strict Clinic", "strict-clinic", onboarded=False)

    r = _put(client, token, ws_id, {
        "business_type": "Clinic",
        "business_context": {"doctor_specializations": ["Dermatology"]},
    })
    assert r.status_code == 422
    assert "doctor is required" in r.json()["detail"].lower()

    r = _put(client, token, ws_id, {
        "business_type": "Clinic",
        "business_context": {"doctor_specializations": ["Dermatology"]},
        **CLINIC_FULL,
    })
    assert r.status_code == 200, r.text
    assert _is_onboarded(client, token, ws_id) is True
    assert r.json()["business_context"] == {"doctor_specializations": ["Dermatology"]}


def test_legacy_payload_without_business_type_still_gated_then_works(client):
    token = register_and_login(client, "legacy-owner@example.com")
    ws_id = create_workspace(client, token, "Legacy Clinic", "legacy-clinic", onboarded=False)

    assert _put(client, token, ws_id, {"services": ["X"]}).status_code == 422

    r = _put(client, token, ws_id, CLINIC_FULL)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["business_type"] is None
    assert body["business_context"] == {}


# --- validation ------------------------------------------------------------

def test_invalid_booking_urls_rejected(client):
    token = register_and_login(client, "badurl-owner@example.com")
    for i, bad_link in enumerate(["notaurl", "ftp://x.y", "www.example.com", "javascript:alert(1)", "http://"]):
        ws_id = create_workspace(client, token, f"BadURL {i}", f"badurl-{i}", onboarded=False)
        r = _put(client, token, ws_id, {
            "business_type": "Software Agency",
            "business_context": {
                "core_services": ["x"],
                "minimum_pricing": "1",
                "discovery_call_booking_link": bad_link,
            },
        })
        assert r.status_code == 422, f"{bad_link!r} should be rejected, got {r.status_code}"


def test_valid_booking_urls_accepted(client):
    token = register_and_login(client, "goodurl-owner@example.com")
    for i, link in enumerate(["https://example.com/book", "http://localhost:3000/x", "https://a.co/b?c=d&e=f"]):
        ws_id = create_workspace(client, token, f"GoodURL {i}", f"goodurl-{i}", onboarded=False)
        r = _put(client, token, ws_id, {
            "business_type": "Software Agency",
            "business_context": {"core_services": ["x"], "minimum_pricing": "1", "discovery_call_booking_link": link},
        })
        assert r.status_code == 200, r.text


def test_blank_and_bad_custom_fields_rejected(client):
    token = register_and_login(client, "customval-owner@example.com")
    ws_id = create_workspace(client, token, "CV", "cv-clinic", onboarded=False)

    assert _put(client, token, ws_id, {
        "business_type": "Other", "business_context": {"custom_fields": {"  ": "v"}},
    }).status_code == 422
    assert _put(client, token, ws_id, {
        "business_type": "Other", "business_context": {"custom_fields": {"k": "   "}},
    }).status_code == 422


def test_blank_list_entries_rejected(client):
    token = register_and_login(client, "blanklist-owner@example.com")
    ws_id = create_workspace(client, token, "BL", "bl-clinic", onboarded=False)
    r = _put(client, token, ws_id, {
        "business_type": "Software Agency",
        "business_context": {
            "core_services": ["Web", "  "],
            "minimum_pricing": "1",
            "discovery_call_booking_link": "https://a.b/c",
        },
    })
    assert r.status_code == 422


def test_wrong_business_context_keys_rejected(client):
    token = register_and_login(client, "wrongkeys-owner@example.com")
    ws_id = create_workspace(client, token, "WK", "wk-clinic", onboarded=False)
    r = _put(client, token, ws_id, {
        "business_type": "Software Agency",
        "business_context": {
            "core_services": ["x"],
            "minimum_pricing": "1",
            "discovery_call_booking_link": "https://a.b/c",
            "property_services": ["y"],  # a Real Estate key
        },
    })
    assert r.status_code == 422


def test_context_without_business_type_rejected(client):
    token = register_and_login(client, "notype-owner@example.com")
    ws_id = create_workspace(client, token, "NT", "nt-clinic", onboarded=False)
    r = _put(client, token, ws_id, {**CLINIC_FULL, "business_context": {"core_services": ["x"]}})
    assert r.status_code == 422


def test_unknown_business_type_rejected(client):
    token = register_and_login(client, "unktype-owner@example.com")
    ws_id = create_workspace(client, token, "UK", "uk-clinic", onboarded=False)
    r = _put(client, token, ws_id, {**CLINIC_FULL, "business_type": "Bakery"})
    assert r.status_code == 422


# --- round trip: GET -> edit -> PUT -> GET ---------------------------------

def test_get_edit_put_get_preserves_business_context(client):
    token = register_and_login(client, "roundtrip-owner@example.com")
    ws_id = create_workspace(client, token, "RT Agency", "rt-agency", onboarded=False)

    assert _put(client, token, ws_id, {
        "business_type": "Software Agency", "business_context": AGENCY_CONTEXT,
    }).status_code == 200

    got = _get(client, token, ws_id).json()
    assert got["business_type"] == "Software Agency"
    assert got["business_context"] == AGENCY_CONTEXT

    # Re-send the whole object with one unrelated edit — the wizard/settings do this.
    edited = {k: v for k, v in got.items() if k != "workspace_id"}
    edited["agent_tone"] = "Friendly"
    edited["business_context"]["minimum_pricing"] = "$2,500"
    assert _put(client, token, ws_id, edited).status_code == 200

    got2 = _get(client, token, ws_id).json()
    assert got2["agent_tone"] == "Friendly"
    assert got2["business_type"] == "Software Agency"
    assert got2["business_context"]["minimum_pricing"] == "$2,500"
    assert got2["business_context"]["core_services"] == AGENCY_CONTEXT["core_services"]


def test_switching_type_on_resave_replaces_context(client):
    token = register_and_login(client, "switch-owner@example.com")
    ws_id = create_workspace(client, token, "Switch Co", "switch-co", onboarded=False)

    assert _put(client, token, ws_id, {
        "business_type": "Software Agency", "business_context": AGENCY_CONTEXT,
    }).status_code == 200
    assert _put(client, token, ws_id, {
        "business_type": "Other", "business_context": OTHER_CONTEXT,
    }).status_code == 200

    got = _get(client, token, ws_id).json()
    assert got["business_type"] == "Other"
    assert got["business_context"] == OTHER_CONTEXT
    assert "core_services" not in got["business_context"]


def test_settings_style_partial_update_replaces_context_and_keeps_the_rest(client):
    """The Settings "Business context" tab does GET-full -> merge
    {business_type, business_context} -> PUT-full (ClinicConfig.save). Switching
    type must replace business_context wholesale while every unrelated key
    (agent_tone, emergency_protocol, general_info, …) is preserved."""
    token = register_and_login(client, "settings-bc-owner@example.com")
    ws_id = create_workspace(client, token, "Settings BC Clinic", "settings-bc", onboarded=False)

    # A fully-configured Clinic with an agency-style context is impossible, so
    # start onboarded as a Clinic and give it a Clinic context + real settings.
    first = {
        **CLINIC_FULL,
        "business_type": "Clinic",
        "business_context": {"doctor_specializations": ["Dermatology"], "appointment_booking_link": "https://c.example/book"},
        "emergency_protocol": "Call 1122 then transfer to on-call staff.",
        "agent_tone": "Empathetic",
        "general_info": {"address": "1 Main St", "accepted_payment_methods": ["Cash"]},
    }
    assert _put(client, token, ws_id, first).status_code == 200

    current = {k: v for k, v in _get(client, token, ws_id).json().items() if k != "workspace_id"}
    # emulate ClinicConfig.save({business_type: "Other", business_context: {...}})
    merged = {**current, "business_type": "Other", "business_context": {"custom_fields": {"Industry": "Legal"}}}
    assert _put(client, token, ws_id, merged).status_code == 200

    got = _get(client, token, ws_id).json()
    assert got["business_type"] == "Other"
    assert got["business_context"] == {"custom_fields": {"Industry": "Legal"}}
    assert "doctor_specializations" not in got["business_context"]
    assert "appointment_booking_link" not in got["business_context"]
    # unrelated settings untouched
    assert got["emergency_protocol"] == "Call 1122 then transfer to on-call staff."
    assert got["agent_tone"] == "Empathetic"
    assert got["general_info"]["accepted_payment_methods"] == ["Cash"]
    assert len(got["doctors"]) == 1 and got["doctors"][0]["name"] == "Dr. Sara Khan"


def test_settings_can_clear_business_type_to_none(client):
    token = register_and_login(client, "settings-clear-owner@example.com")
    ws_id = create_workspace(client, token, "Clearable", "clearable", onboarded=False)
    assert _put(client, token, ws_id, {"business_type": "Software Agency", "business_context": AGENCY_CONTEXT}).status_code == 200

    current = {k: v for k, v in _get(client, token, ws_id).json().items() if k != "workspace_id"}
    merged = {**current, "business_type": None, "business_context": {}}
    assert _put(client, token, ws_id, merged).status_code == 200

    got = _get(client, token, ws_id).json()
    assert got["business_type"] is None
    assert got["business_context"] == {}
