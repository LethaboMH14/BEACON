"""Face embeddings store — face_embeddings

Revision ID: 004
Revises: 003
Create Date: 2026-07-25

Entity.embedding_ref and Sighting.embedding_ref have existed since 001 as
designed indirection to "embedding storage", but no such storage was ever
built. The consequence was silent and load-bearing: POST /v1/sightings only
ran entity resolution when plate_text was present, so a face sighting stored
entity_id=NULL — no entity, no suspicion score, no repeat-offender matching.
Faces were detected-and-forgotten while plates were tracked.

This table is that missing store: one row per observed face view, several per
entity, matched by cosine similarity in suspicion/face_resolution.py.
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '004'
down_revision: Union[str, None] = '003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'face_embeddings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('entity_id', sa.String(length=64), nullable=False),
        sa.Column('sighting_id', sa.Integer(), nullable=True),
        sa.Column('vector', sa.JSON(), nullable=False),
        sa.Column('dim', sa.Integer(), nullable=False, server_default='512'),
        sa.Column('model', sa.String(length=64), nullable=False, server_default='buffalo_l'),
        sa.Column('det_score', sa.Float(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['entity_id'], ['entities.id'], ),
        sa.ForeignKeyConstraint(['sighting_id'], ['sightings.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_face_embeddings_entity', 'face_embeddings', ['entity_id'])


def downgrade() -> None:
    op.drop_index('idx_face_embeddings_entity', table_name='face_embeddings')
    op.drop_table('face_embeddings')
