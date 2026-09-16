"""Isolated unit tests for deterministic synthetic data generation."""

from datetime import date

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.db.models  # noqa: F401
from app.db.base import Base
from app.db.models import Claim, Member
from app.db.seed import SeedDataExistsError, SeedOptions, seed_database

SMALL_SEED = SeedOptions(
    seed=7,
    facilities=2,
    providers=3,
    members=5,
    encounters=8,
    claims=6,
    appointments=4,
    start_date=date(2024, 1, 1),
    end_date=date(2024, 12, 31),
)


def _create_isolated_session() -> Session:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return Session(engine)


def _seed_snapshot() -> tuple[object, list[tuple[object, ...]]]:
    with _create_isolated_session() as session:
        with session.begin():
            counts = seed_database(session, SMALL_SEED)
        claims = session.execute(
            select(
                Claim.claim_external_id,
                Claim.service_date,
                Claim.submitted_amount,
                Claim.allowed_amount,
                Claim.paid_amount,
            ).order_by(Claim.id)
        ).all()
        return counts, [tuple(row) for row in claims]


def test_seed_is_deterministic_and_preserves_claim_invariants() -> None:
    first_counts, first_claims = _seed_snapshot()
    second_counts, second_claims = _seed_snapshot()

    assert first_counts == second_counts
    assert first_claims == second_claims
    assert first_counts.claims == SMALL_SEED.claims
    assert SMALL_SEED.claims <= first_counts.claim_lines <= SMALL_SEED.claims * 3
    assert all(
        SMALL_SEED.start_date <= service_date <= SMALL_SEED.end_date
        and paid <= allowed <= submitted
        for _, service_date, submitted, allowed, paid in first_claims
    )


def test_seed_uses_deterministic_external_ids_and_refuses_duplicates() -> None:
    with _create_isolated_session() as session:
        with session.begin():
            seed_database(session, SMALL_SEED)

        assert session.scalars(select(Member.member_external_id).order_by(Member.id)).all() == [
            "M000001",
            "M000002",
            "M000003",
            "M000004",
            "M000005",
        ]
        session.rollback()

        with pytest.raises(SeedDataExistsError, match="Refusing to seed non-empty"):
            seed_database(session, SMALL_SEED)
