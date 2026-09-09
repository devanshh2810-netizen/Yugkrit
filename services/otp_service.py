"""
YugKrit - OTP (One-Time Password) service for mobile-number login.

DEV-MODE SMS DELIVERY NOTICE
----------------------------
This reference implementation has no real SMS gateway wired in (e.g.
Twilio, MSG91, AWS SNS). Instead, `send_otp()` "delivers" the OTP by
returning it to the caller so it can be shown directly on-screen, clearly
labelled as a development-mode shortcut. To go live, replace the body of
`_dispatch_sms()` below with a real provider call and remove the
`dev_otp` value from what gets shown to the user.

Security notes (kept consistent with the rest of the codebase):
- The OTP code itself is never stored in plain text — only a SHA-256 hash.
- Codes expire after `OTP_EXPIRY_MINUTES` and are rate-limited by both a
  minimum resend interval and a maximum verification-attempt count.
"""

import hashlib
import os
import random
from datetime import datetime, timedelta

from database.database import db
from database.models import OTPCode, User
from utils.validators import validate_phone_required, validate_otp_code, ValidationError

OTP_EXPIRY_MINUTES = 10
OTP_RESEND_COOLDOWN_SECONDS = 30
DEV_MODE = os.environ.get("FLASK_DEBUG", "1") == "1"


def _hash_code(code):
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def _dispatch_sms(phone, code):
    """Stand-in for a real SMS gateway integration. In dev mode we simply
    return the code so it can be surfaced in the UI; in production this
    would call an SMS provider and return nothing sensitive."""
    if DEV_MODE:
        return code
    # TODO: integrate a real SMS provider here, e.g.:
    #   twilio_client.messages.create(to=phone, body=f"Your YugKrit OTP is {code}")
    return None


def request_otp(phone, purpose="LOGIN"):
    """Generate, hash, store, and 'send' a fresh OTP for the given phone
    number. Returns (otp_record, dev_otp) where dev_otp is only populated
    in development mode for on-screen display."""
    phone = validate_phone_required(phone)

    recent = (OTPCode.query.filter_by(phone=phone, purpose=purpose)
              .order_by(OTPCode.created_at.desc()).first())
    if recent and not recent.is_expired():
        seconds_since = (datetime.utcnow() - recent.created_at).total_seconds()
        if seconds_since < OTP_RESEND_COOLDOWN_SECONDS:
            wait = int(OTP_RESEND_COOLDOWN_SECONDS - seconds_since)
            raise ValidationError(f"Please wait {wait}s before requesting another OTP.",
                                   code="OTP_COOLDOWN")

    code = f"{random.randint(0, 999999):06d}"
    record = OTPCode(
        phone=phone, purpose=purpose, code_hash=_hash_code(code),
        expires_at=datetime.utcnow() + timedelta(minutes=OTP_EXPIRY_MINUTES),
    )
    db.session.add(record)
    db.session.commit()

    dev_otp = _dispatch_sms(phone, code)
    return record, dev_otp


def verify_otp(phone, code, purpose="LOGIN"):
    """Verify a submitted OTP for a phone number. Returns the matching User
    for LOGIN purpose (raises ValidationError on any failure)."""
    phone = validate_phone_required(phone)
    code = validate_otp_code(code)

    record = (OTPCode.query.filter_by(phone=phone, purpose=purpose, is_verified=False)
              .order_by(OTPCode.created_at.desc()).first())
    if not record:
        raise ValidationError("No pending OTP request found for this number. Please request a new one.",
                               code="OTP_NOT_FOUND")
    if record.is_expired():
        raise ValidationError("This OTP has expired. Please request a new one.", code="OTP_EXPIRED")
    if record.is_exhausted():
        raise ValidationError("Too many incorrect attempts. Please request a new OTP.",
                               code="OTP_EXHAUSTED")

    if _hash_code(code) != record.code_hash:
        record.attempts += 1
        db.session.commit()
        remaining = record.max_attempts - record.attempts
        raise ValidationError(f"Incorrect OTP. {max(remaining, 0)} attempt(s) remaining.",
                               code="OTP_INCORRECT")

    record.is_verified = True
    db.session.commit()

    if purpose == "LOGIN":
        user = User.query.filter_by(phone=phone).first()
        if not user:
            raise ValidationError("No account found with this mobile number.", code="PHONE_NOT_FOUND")
        if not user.is_active:
            raise ValidationError("This account has been deactivated.", code="ACCOUNT_INACTIVE")
        user.is_phone_verified = True
        db.session.commit()
        return user

    return None
