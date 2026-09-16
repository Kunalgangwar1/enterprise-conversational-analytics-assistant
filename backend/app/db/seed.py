"""Deterministic synthetic healthcare data seeding for local development."""

from __future__ import annotations

import argparse
import logging
import random
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal

from faker import Faker
from sqlalchemy import delete, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import Appointment, Claim, ClaimLine, Encounter, Facility, Member, Provider
from app.db.session import SessionLocal

LOGGER = logging.getLogger(__name__)

DEFAULT_START_DATE = date(2024, 1, 1)
DEFAULT_END_DATE = date(2026, 8, 31)
LOCAL_ENVIRONMENTS = {"dev", "development", "local", "test"}

FACILITY_TYPES = ("Hospital", "Clinic", "Urgent Care", "Ambulatory Center")
SPECIALTIES = (
    "Primary Care",
    "Cardiology",
    "Orthopedics",
    "Dermatology",
    "Neurology",
    "Endocrinology",
)
ENCOUNTER_TYPES = ("outpatient", "inpatient", "emergency", "telehealth")
ENCOUNTER_STATUSES = ("completed", "cancelled", "in_progress")
CLAIM_STATUSES = ("submitted", "pending", "paid", "denied", "adjusted")
PAYER_TYPES = ("commercial", "medicare", "medicaid", "self_pay")
APPOINTMENT_STATUSES = ("scheduled", "completed", "cancelled", "no_show")
REASON_CATEGORIES = ("preventive", "new_symptom", "follow_up", "chronic_care", "procedure")
DIAGNOSIS_CODES = ("SYN-D01", "SYN-D02", "SYN-D03", "SYN-D04", "SYN-D05", "SYN-D06")
PROCEDURE_CODES = ("SYN-P01", "SYN-P02", "SYN-P03", "SYN-P04", "SYN-P05")
STATES = ("AZ", "CA", "CO", "FL", "GA", "IL", "MA", "NC", "NY", "OH", "TX", "WA")


class SeedConfigurationError(ValueError):
    """Raised for incompatible synthetic-data generation options."""


class SeedDataExistsError(RuntimeError):
    """Raised when seeding would duplicate existing target-table data."""


@dataclass(frozen=True)
class SeedOptions:
    """Sizes and deterministic controls for a seed run."""

    seed: int = 42
    members: int = 500
    providers: int = 80
    facilities: int = 12
    encounters: int = 3_000
    claims: int = 2_500
    appointments: int = 1_500
    start_date: date = DEFAULT_START_DATE
    end_date: date = DEFAULT_END_DATE


@dataclass(frozen=True)
class SeedCounts:
    """Rows prepared by a completed seed transaction."""

    facilities: int
    providers: int
    members: int
    encounters: int
    claims: int
    claim_lines: int
    appointments: int


_TARGET_MODELS = (Facility, Provider, Member, Encounter, Claim, ClaimLine, Appointment)
_DELETE_ORDER = (ClaimLine, Claim, Appointment, Encounter, Provider, Facility, Member)


def _validate_options(options: SeedOptions) -> None:
    if options.start_date > options.end_date:
        raise SeedConfigurationError("start date must be on or before end date")

    counts = {
        "members": options.members,
        "providers": options.providers,
        "facilities": options.facilities,
        "encounters": options.encounters,
        "claims": options.claims,
        "appointments": options.appointments,
    }
    negative_counts = [name for name, value in counts.items() if value < 0]
    if negative_counts:
        raise SeedConfigurationError(f"counts cannot be negative: {', '.join(negative_counts)}")
    if options.providers and not options.facilities:
        raise SeedConfigurationError("providers require at least one facility")
    if (options.encounters or options.claims or options.appointments) and not options.members:
        raise SeedConfigurationError("encounters, claims, and appointments require members")
    if (options.encounters or options.claims or options.appointments) and not options.providers:
        raise SeedConfigurationError("encounters, claims, and appointments require providers")


def _random_date(rng: random.Random, start_date: date, end_date: date) -> date:
    day_offset = rng.randint(0, (end_date - start_date).days)
    return start_date + timedelta(days=day_offset)


def _scheduled_datetime(rng: random.Random, start_date: date, end_date: date) -> datetime:
    scheduled_date = _random_date(rng, start_date, end_date)
    scheduled_time = time(hour=rng.randint(8, 17), minute=rng.choice((0, 15, 30, 45)))
    return datetime.combine(scheduled_date, scheduled_time, tzinfo=UTC)


def _decimal_from_cents(cents: int) -> Decimal:
    return Decimal(cents).scaleb(-2)


def _existing_row_counts(session: Session) -> dict[str, int]:
    return {
        model.__tablename__: session.scalar(select(func.count()).select_from(model)) or 0
        for model in _TARGET_MODELS
    }


def _prepare_target_tables(session: Session, reset: bool) -> None:
    existing_counts = _existing_row_counts(session)
    populated = {name: count for name, count in existing_counts.items() if count}
    if populated and not reset:
        summary = ", ".join(f"{name}={count}" for name, count in populated.items())
        raise SeedDataExistsError(
            f"Refusing to seed non-empty target tables ({summary}). "
            "Use --reset explicitly for local development reseeding."
        )
    if reset:
        for model in _DELETE_ORDER:
            session.execute(delete(model))


def _build_facilities(
    fake: Faker, rng: random.Random, count: int, created_at: datetime
) -> list[Facility]:
    return [
        Facility(
            facility_external_id=f"F{index:04d}",
            name=f"{fake.company()} {rng.choice(FACILITY_TYPES)}",
            facility_type=rng.choice(FACILITY_TYPES),
            city=fake.city(),
            state=rng.choice(STATES),
            created_at=created_at,
        )
        for index in range(1, count + 1)
    ]


def _build_providers(
    fake: Faker,
    rng: random.Random,
    count: int,
    facilities: list[Facility],
    created_at: datetime,
) -> list[Provider]:
    providers: list[Provider] = []
    for index in range(1, count + 1):
        facility = rng.choice(facilities)
        providers.append(
            Provider(
                provider_external_id=f"P{index:05d}",
                synthetic_npi=f"999{index:07d}",
                first_name=fake.first_name(),
                last_name=fake.last_name(),
                specialty=rng.choice(SPECIALTIES),
                facility_id=facility.id,
                created_at=created_at,
            )
        )
    return providers


def _build_members(
    fake: Faker, rng: random.Random, count: int, created_at: datetime
) -> list[Member]:
    members: list[Member] = []
    for index in range(1, count + 1):
        enrollment_start = _random_date(rng, date(2020, 1, 1), DEFAULT_START_DATE)
        enrollment_end = None
        if rng.random() < 0.15:
            enrollment_end = _random_date(rng, enrollment_start, DEFAULT_END_DATE)
        members.append(
            Member(
                member_external_id=f"M{index:06d}",
                first_name=fake.first_name(),
                last_name=fake.last_name(),
                date_of_birth=_random_date(rng, date(1935, 1, 1), date(2008, 12, 31)),
                sex_at_birth=rng.choice(("female", "male", "intersex", "unknown")),
                state=rng.choice(STATES),
                email=fake.unique.email(),
                phone=fake.numerify("(###) ###-####"),
                enrollment_start=enrollment_start,
                enrollment_end=enrollment_end,
                created_at=created_at,
            )
        )
    return members


def _build_encounters(
    rng: random.Random,
    count: int,
    members: list[Member],
    providers: list[Provider],
    start_date: date,
    end_date: date,
    created_at: datetime,
) -> list[Encounter]:
    encounters: list[Encounter] = []
    for index in range(1, count + 1):
        member = rng.choice(members)
        provider = rng.choice(providers)
        encounters.append(
            Encounter(
                encounter_external_id=f"E{index:07d}",
                member_id=member.id,
                provider_id=provider.id,
                facility_id=provider.facility_id,
                encounter_date=_random_date(rng, start_date, end_date),
                encounter_type=rng.choice(ENCOUNTER_TYPES),
                primary_diagnosis_code=rng.choice(DIAGNOSIS_CODES),
                status=rng.choices(ENCOUNTER_STATUSES, weights=(85, 10, 5), k=1)[0],
                created_at=created_at,
            )
        )
    return encounters


def _claim_amounts(rng: random.Random, status: str) -> tuple[Decimal, Decimal, Decimal]:
    submitted_cents = rng.randint(5_000, 500_000)
    allowed_cents = rng.randint(submitted_cents * 55 // 100, submitted_cents)
    if status == "denied":
        paid_cents = 0
    elif status in {"submitted", "pending"}:
        paid_cents = rng.randint(0, allowed_cents)
    else:
        paid_cents = rng.randint(allowed_cents * 70 // 100, allowed_cents)
    return tuple(
        _decimal_from_cents(value) for value in (submitted_cents, allowed_cents, paid_cents)
    )


def _build_claims(
    rng: random.Random,
    count: int,
    members: list[Member],
    providers: list[Provider],
    encounters: list[Encounter],
    start_date: date,
    end_date: date,
    created_at: datetime,
) -> list[Claim]:
    claims: list[Claim] = []
    for index in range(1, count + 1):
        encounter = rng.choice(encounters) if encounters and rng.random() < 0.85 else None
        member_id = encounter.member_id if encounter else rng.choice(members).id
        provider_id = encounter.provider_id if encounter else rng.choice(providers).id
        service_date = (
            encounter.encounter_date if encounter else _random_date(rng, start_date, end_date)
        )
        claim_status = rng.choice(CLAIM_STATUSES)
        submitted, allowed, paid = _claim_amounts(rng, claim_status)
        claims.append(
            Claim(
                claim_external_id=f"C{index:07d}",
                member_id=member_id,
                provider_id=provider_id,
                encounter_id=encounter.id if encounter else None,
                service_date=service_date,
                submitted_amount=submitted,
                allowed_amount=allowed,
                paid_amount=paid,
                claim_status=claim_status,
                payer_type=rng.choice(PAYER_TYPES),
                created_at=created_at,
            )
        )
    return claims


def _build_claim_lines(
    rng: random.Random, claims: list[Claim], created_at: datetime
) -> list[ClaimLine]:
    claim_lines: list[ClaimLine] = []
    for claim in claims:
        for line_number in range(1, rng.randint(1, 3) + 1):
            billed_cents = rng.randint(1_000, 200_000)
            allowed_cents = rng.randint(billed_cents * 50 // 100, billed_cents)
            paid_cents = 0 if claim.claim_status == "denied" else rng.randint(0, allowed_cents)
            claim_lines.append(
                ClaimLine(
                    claim_id=claim.id,
                    line_number=line_number,
                    procedure_code=rng.choice(PROCEDURE_CODES),
                    diagnosis_code=rng.choice(DIAGNOSIS_CODES),
                    service_units=rng.randint(1, 5),
                    billed_amount=_decimal_from_cents(billed_cents),
                    allowed_amount=_decimal_from_cents(allowed_cents),
                    paid_amount=_decimal_from_cents(paid_cents),
                    created_at=created_at,
                )
            )
    return claim_lines


def _build_appointments(
    rng: random.Random,
    count: int,
    members: list[Member],
    providers: list[Provider],
    start_date: date,
    end_date: date,
    created_at: datetime,
) -> list[Appointment]:
    appointments: list[Appointment] = []
    for index in range(1, count + 1):
        member = rng.choice(members)
        provider = rng.choice(providers)
        appointments.append(
            Appointment(
                appointment_external_id=f"A{index:07d}",
                member_id=member.id,
                provider_id=provider.id,
                facility_id=provider.facility_id,
                scheduled_at=_scheduled_datetime(rng, start_date, end_date),
                status=rng.choice(APPOINTMENT_STATUSES),
                reason_category=rng.choice(REASON_CATEGORIES),
                created_at=created_at,
            )
        )
    return appointments


def seed_database(session: Session, options: SeedOptions, *, reset: bool = False) -> SeedCounts:
    """Prepare a deterministic synthetic dataset in the current transaction."""
    _validate_options(options)
    _prepare_target_tables(session, reset)

    rng = random.Random(options.seed)
    Faker.seed(options.seed)
    fake = Faker("en_US")
    fake.seed_instance(options.seed)
    created_at = datetime.combine(options.end_date + timedelta(days=1), time.min, tzinfo=UTC)

    facilities = _build_facilities(fake, rng, options.facilities, created_at)
    session.add_all(facilities)
    session.flush()

    providers = _build_providers(fake, rng, options.providers, facilities, created_at)
    members = _build_members(fake, rng, options.members, created_at)
    session.add_all([*providers, *members])
    session.flush()

    encounters = _build_encounters(
        rng,
        options.encounters,
        members,
        providers,
        options.start_date,
        options.end_date,
        created_at,
    )
    session.add_all(encounters)
    session.flush()

    claims = _build_claims(
        rng,
        options.claims,
        members,
        providers,
        encounters,
        options.start_date,
        options.end_date,
        created_at,
    )
    session.add_all(claims)
    session.flush()

    claim_lines = _build_claim_lines(rng, claims, created_at)
    appointments = _build_appointments(
        rng,
        options.appointments,
        members,
        providers,
        options.start_date,
        options.end_date,
        created_at,
    )
    session.add_all([*claim_lines, *appointments])
    session.flush()

    return SeedCounts(
        facilities=len(facilities),
        providers=len(providers),
        members=len(members),
        encounters=len(encounters),
        claims=len(claims),
        claim_lines=len(claim_lines),
        appointments=len(appointments),
    )


def _non_negative_int(raw_value: str) -> int:
    value = int(raw_value)
    if value < 0:
        raise argparse.ArgumentTypeError("must be zero or greater")
    return value


def _iso_date(raw_value: str) -> date:
    try:
        return date.fromisoformat(raw_value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must use YYYY-MM-DD format") from exc


def build_parser() -> argparse.ArgumentParser:
    """Build the local synthetic-data command-line parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--members", type=_non_negative_int, default=500)
    parser.add_argument("--providers", type=_non_negative_int, default=80)
    parser.add_argument("--facilities", type=_non_negative_int, default=12)
    parser.add_argument("--encounters", type=_non_negative_int, default=3_000)
    parser.add_argument("--claims", type=_non_negative_int, default=2_500)
    parser.add_argument("--appointments", type=_non_negative_int, default=1_500)
    parser.add_argument("--start-date", type=_iso_date, default=DEFAULT_START_DATE)
    parser.add_argument("--end-date", type=_iso_date, default=DEFAULT_END_DATE)
    parser.add_argument(
        "--reset",
        action="store_true",
        help="delete existing synthetic target rows before seeding (local development only)",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the deterministic local seed operation."""
    parser = build_parser()
    args = parser.parse_args(argv)
    settings = get_settings()
    if args.reset and settings.app_env.lower() not in LOCAL_ENVIRONMENTS:
        parser.error("--reset is allowed only when APP_ENV is local, development, dev, or test")

    options = SeedOptions(
        seed=args.seed,
        members=args.members,
        providers=args.providers,
        facilities=args.facilities,
        encounters=args.encounters,
        claims=args.claims,
        appointments=args.appointments,
        start_date=args.start_date,
        end_date=args.end_date,
    )

    logging.basicConfig(
        level=settings.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    try:
        with SessionLocal.begin() as session:
            counts = seed_database(session, options, reset=args.reset)
    except (SeedConfigurationError, SeedDataExistsError, SQLAlchemyError) as exc:
        LOGGER.error("Synthetic seed failed: %s", exc)
        return 1

    LOGGER.info(
        "Synthetic seed complete: facilities=%d providers=%d members=%d encounters=%d "
        "claims=%d claim_lines=%d appointments=%d",
        counts.facilities,
        counts.providers,
        counts.members,
        counts.encounters,
        counts.claims,
        counts.claim_lines,
        counts.appointments,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
