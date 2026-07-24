"""Initial BEACON schema v0

Revision ID: 001
Revises: 
Create Date: 2026-07-24

Tables: cameras, sightings, entities, whitelist, watchlist, claims, 
risk_cells, incidents, alerts, routes, evidence_chain
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # cameras table
    op.create_table(
        'cameras',
        sa.Column('id', sa.String(64), primary_key=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('location', sa.String(255), nullable=True),
        sa.Column('lat', sa.Float(), nullable=True),
        sa.Column('lng', sa.Float(), nullable=True),
        sa.Column('hex_id', sa.String(15), nullable=True),
        sa.Column('status', sa.String(32), nullable=False, server_default='active'),
        sa.Column('owner_id', sa.String(64), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
    )
    
    # entities table
    op.create_table(
        'entities',
        sa.Column('id', sa.String(64), primary_key=True),
        sa.Column('kind', sa.String(32), nullable=False),
        sa.Column('embedding_ref', sa.Text(), nullable=True),
        sa.Column('plate_text', sa.String(32), nullable=True),
        sa.Column('base_score', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('last_updated', sa.DateTime(), nullable=False),
        sa.Column('state', sa.String(32), nullable=False, server_default='observed'),
        sa.Column('first_seen', sa.DateTime(), nullable=False),
        sa.Column('last_seen', sa.DateTime(), nullable=False),
        sa.Column('sighting_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )
    op.create_index('idx_entities_state', 'entities', ['state'])
    op.create_index('idx_entities_plate', 'entities', ['plate_text'])
    
    # sightings table
    op.create_table(
        'sightings',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('camera_id', sa.String(64), sa.ForeignKey('cameras.id'), nullable=False),
        sa.Column('entity_id', sa.String(64), sa.ForeignKey('entities.id'), nullable=True),
        sa.Column('ts', sa.DateTime(), nullable=False),
        sa.Column('hex_id', sa.String(15), nullable=True),
        sa.Column('kind', sa.String(32), nullable=False),
        sa.Column('modality', sa.String(32), nullable=False),
        sa.Column('confidence', sa.Float(), nullable=False),
        sa.Column('bbox', sa.JSON(), nullable=True),
        sa.Column('embedding_ref', sa.Text(), nullable=True),
        sa.Column('plate_text', sa.String(32), nullable=True),
        sa.Column('plate_quality', sa.Float(), nullable=True),
        sa.Column('clip_ref', sa.String(255), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )
    op.create_index('idx_sightings_ts', 'sightings', ['ts'])
    op.create_index('idx_sightings_hex', 'sightings', ['hex_id', 'ts'])
    op.create_index('idx_sightings_entity', 'sightings', ['entity_id', 'ts'])
    
    # whitelist table
    op.create_table(
        'whitelist',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('entity_id', sa.String(64), sa.ForeignKey('entities.id'), nullable=False),
        sa.Column('hex_id', sa.String(15), nullable=False),
        sa.Column('kind', sa.String(32), nullable=False),
        sa.Column('label', sa.String(255), nullable=True),
        sa.Column('added_by', sa.String(64), nullable=False),
        sa.Column('added_at', sa.DateTime(), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=True),
    )
    op.create_index('idx_whitelist_entity_hex', 'whitelist', ['entity_id', 'hex_id'])
    
    # watchlist table
    op.create_table(
        'watchlist',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('entity_id', sa.String(64), sa.ForeignKey('entities.id'), nullable=False),
        sa.Column('reason', sa.Text(), nullable=False),
        sa.Column('verified_by', sa.String(64), nullable=False),
        sa.Column('verified_at', sa.DateTime(), nullable=False),
        sa.Column('active', sa.Boolean(), nullable=False, server_default='1'),
        sa.Column('expires_at', sa.DateTime(), nullable=True),
    )
    op.create_unique_constraint('uq_watchlist_entity', 'watchlist', ['entity_id'])
    
    # claims table
    op.create_table(
        'claims',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('claim_number', sa.String(64), nullable=False),
        sa.Column('claim_type', sa.String(64), nullable=False),
        sa.Column('suburb', sa.String(255), nullable=False),
        sa.Column('lat', sa.Float(), nullable=True),
        sa.Column('lng', sa.Float(), nullable=True),
        sa.Column('hex_id', sa.String(15), nullable=True),
        sa.Column('claim_date', sa.DateTime(), nullable=False),
        sa.Column('hour', sa.Integer(), nullable=True),
        sa.Column('hour_known', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('amount', sa.Float(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )
    op.create_unique_constraint('uq_claims_number', 'claims', ['claim_number'])
    op.create_index('idx_claims_hex_date', 'claims', ['hex_id', 'claim_date'])
    op.create_index('idx_claims_type', 'claims', ['claim_type'])
    
    # risk_cells table
    op.create_table(
        'risk_cells',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('hex_id', sa.String(15), nullable=False),
        sa.Column('forecast_date', sa.DateTime(), nullable=False),
        sa.Column('hour', sa.Integer(), nullable=False),
        sa.Column('risk_score', sa.Float(), nullable=False),
        sa.Column('top_factors', sa.JSON(), nullable=True),
        sa.Column('model_version', sa.String(32), nullable=False),
        sa.Column('generated_at', sa.DateTime(), nullable=False),
        sa.CheckConstraint('hour >= 0 AND hour < 24', name='check_hour_range'),
    )
    op.create_index('idx_risk_hex_time', 'risk_cells', ['hex_id', 'forecast_date', 'hour'])
    
    # incidents table
    op.create_table(
        'incidents',
        sa.Column('id', sa.String(64), primary_key=True),
        sa.Column('incident_type', sa.String(64), nullable=False),
        sa.Column('hex_id', sa.String(15), nullable=False),
        sa.Column('lat', sa.Float(), nullable=True),
        sa.Column('lng', sa.Float(), nullable=True),
        sa.Column('occurred_at', sa.DateTime(), nullable=False),
        sa.Column('reported_at', sa.DateTime(), nullable=False),
        sa.Column('status', sa.String(32), nullable=False, server_default='active'),
        sa.Column('severity', sa.String(32), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('related_entity_id', sa.String(64), sa.ForeignKey('entities.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )
    op.create_index('idx_incidents_hex_time', 'incidents', ['hex_id', 'occurred_at'])
    
    # alerts table
    op.create_table(
        'alerts',
        sa.Column('id', sa.String(64), primary_key=True),
        sa.Column('alert_type', sa.String(64), nullable=False),
        sa.Column('recipient_id', sa.String(64), nullable=False),
        sa.Column('recipient_type', sa.String(32), nullable=False),
        sa.Column('entity_id', sa.String(64), sa.ForeignKey('entities.id'), nullable=True),
        sa.Column('incident_id', sa.String(64), sa.ForeignKey('incidents.id'), nullable=True),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('severity', sa.String(32), nullable=False),
        sa.Column('status', sa.String(32), nullable=False, server_default='pending'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('acked_at', sa.DateTime(), nullable=True),
        sa.Column('acked_by', sa.String(64), nullable=True),
        sa.Column('cancel_window_expires', sa.DateTime(), nullable=True),
    )
    op.create_index('idx_alerts_recipient', 'alerts', ['recipient_id', 'status'])
    op.create_index('idx_alerts_created', 'alerts', ['created_at'])
    
    # routes table
    op.create_table(
        'routes',
        sa.Column('id', sa.String(64), primary_key=True),
        sa.Column('team_id', sa.String(64), nullable=False),
        sa.Column('shift_start', sa.DateTime(), nullable=False),
        sa.Column('shift_end', sa.DateTime(), nullable=False),
        sa.Column('stops', sa.JSON(), nullable=False),
        sa.Column('fuel_budget', sa.Float(), nullable=False),
        sa.Column('coverage_pct', sa.Float(), nullable=False),
        sa.Column('status', sa.String(32), nullable=False, server_default='planned'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )
    op.create_index('idx_routes_team_shift', 'routes', ['team_id', 'shift_start'])
    
    # evidence_chain table (hash-chained audit log)
    op.create_table(
        'evidence_chain',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('action', sa.String(64), nullable=False),
        sa.Column('actor_id', sa.String(64), nullable=False),
        sa.Column('target_type', sa.String(32), nullable=False),
        sa.Column('target_id', sa.String(64), nullable=False),
        sa.Column('details', sa.JSON(), nullable=True),
        sa.Column('ts', sa.DateTime(), nullable=False),
        sa.Column('prev_hash', sa.String(64), nullable=True),
        sa.Column('event_hash', sa.String(64), nullable=False),
    )
    op.create_index('idx_evidence_ts', 'evidence_chain', ['ts'])
    op.create_index('idx_evidence_target', 'evidence_chain', ['target_type', 'target_id'])


def downgrade() -> None:
    op.drop_table('evidence_chain')
    op.drop_table('routes')
    op.drop_table('alerts')
    op.drop_table('incidents')
    op.drop_table('risk_cells')
    op.drop_table('claims')
    op.drop_table('watchlist')
    op.drop_table('whitelist')
    op.drop_table('sightings')
    op.drop_table('entities')
    op.drop_table('cameras')
