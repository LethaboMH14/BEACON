"""G3: camera health — cameras.last_seen_at

Revision ID: 003
Revises: 002
Create Date: 2026-07-25

team/SBU.md backlog: auto-registration (G2) creates a Camera row on first
sighting but nothing ever tracked when a camera was last heard from, so
ops had no signal if a laptop's webcam/mic agent silently died mid-demo.
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '003'
down_revision: Union[str, None] = '002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('cameras', sa.Column('last_seen_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column('cameras', 'last_seen_at')
