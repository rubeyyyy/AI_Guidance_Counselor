"""Email ownership and single-use registration/recovery challenges.

Existing accounts are preserved, but not silently marked as verified. Recovery
proves ownership and sets a fresh password before their next login.
"""
from alembic import op
import sqlalchemy as sa
revision = '0003_email_verification'
down_revision = '0002_auth'


def upgrade():
    op.add_column('users', sa.Column('email_verified_at', sa.DateTime, nullable=True))
    op.create_table('email_challenges',
        sa.Column('id', sa.String(43), primary_key=True),
        sa.Column('email', sa.String(254), nullable=False, index=True),
        sa.Column('user_id', sa.Integer, sa.ForeignKey('users.id'), nullable=True, index=True),
        sa.Column('purpose', sa.String(20), nullable=False),
        sa.Column('code_hash', sa.String(64), nullable=False),
        sa.Column('password_hash', sa.String(255), nullable=True),
        sa.Column('display_name', sa.String(100), nullable=True),
        sa.Column('created_at', sa.DateTime, nullable=False),
        sa.Column('sent_at', sa.DateTime, nullable=False),
        sa.Column('expires_at', sa.DateTime, nullable=False, index=True),
        sa.Column('attempts', sa.Integer, nullable=False),
        sa.Column('consumed_at', sa.DateTime, nullable=True),
        sa.CheckConstraint("purpose IN ('registration', 'password_reset')"),
        sa.CheckConstraint('attempts >= 0'))
    op.execute(sa.text('UPDATE auth_sessions SET revoked_at = CURRENT_TIMESTAMP WHERE revoked_at IS NULL AND user_id IS NOT NULL'))


def downgrade():
    op.drop_table('email_challenges')
    with op.batch_alter_table('users') as batch:
        batch.drop_column('email_verified_at')
