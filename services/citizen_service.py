"""
YugKrit - Citizen service.

Citizens register with their Aadhaar number as an identity credential. To
protect privacy, YugKrit never stores the full Aadhaar number: only a
one-way SHA-256 hash (for duplicate-account detection) and the last 4
digits (for display, e.g. "XXXX-XXXX-1234"). A Government IT Cell officer
manually validates and approves each citizen profile — this stands in for
a real Aadhaar e-KYC API integration, which is out of scope for this
reference implementation.
"""

import hashlib
from database.database import db
from database.models import CitizenProfile
from utils.validators import validate_aadhaar, ValidationError
from services.audit_service import log_action
from services.notification_service import notify


def hash_aadhaar(aadhaar_number):
    cleaned = validate_aadhaar(aadhaar_number)
    return hashlib.sha256(cleaned.encode("utf-8")).hexdigest(), cleaned[-4:]


def register_citizen(user, aadhaar_number, address=None, city=None, district=None, state=None):
    aadhaar_hash, last4 = hash_aadhaar(aadhaar_number)

    if CitizenProfile.query.filter_by(aadhaar_hash=aadhaar_hash).first():
        raise ValidationError("An account already exists for this Aadhaar number.", code="AADHAAR_EXISTS")

    profile = CitizenProfile(
        user_id=user.id, aadhaar_hash=aadhaar_hash, aadhaar_last4=last4,
        address=address, city=city, district=district, state=state,
        verification_status="PENDING",
    )
    db.session.add(profile)
    db.session.commit()
    return profile


def verify_citizen(citizen, it_cell_user, approve=True, reason=None):
    from datetime import datetime
    previous = citizen.verification_status
    citizen.verification_status = "VERIFIED" if approve else "REJECTED"
    citizen.verified_by_id = it_cell_user.id
    citizen.verified_at = datetime.utcnow()
    if not approve:
        citizen.rejection_reason = reason
    db.session.commit()

    log_action(it_cell_user, "CITIZEN_VERIFY" if approve else "CITIZEN_REJECT",
               "CitizenProfile", citizen.id, previous, citizen.verification_status, reason)
    notify(citizen.user, "Aadhaar verification update",
           f"Your citizen profile has been {'verified' if approve else 'rejected'}.",
           link="/dashboard/citizen")
    return citizen
