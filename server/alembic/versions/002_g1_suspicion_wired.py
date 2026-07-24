"""G1: suspicion scorer wired, alerts ack/cancel, member WS filtering

Revision ID: 002
Revises: 001
Create Date: 2026-07-24

No schema changes for G1 — all suspicion factors are computed at runtime
from existing tables (sightings, cameras, whitelist, claims, incidents).
This migration is a version-chain marker only.

Schema additions will land in 003 if G2 requires pgvector or H3 columns.
"""
from typing import Sequence, Union
from alembic import op

revision: str = '002'
down_revision: Union[str, None] = '001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # No schema changes — scorer reads from existing tables.
    pass


def downgrade() -> None:
    pass
