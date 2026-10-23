"""Add users, revocable sessions and rate-limit records without claiming students."""
from alembic import op
import sqlalchemy as sa
revision = '0002_auth'
down_revision = '0001_legacy'


def upgrade():
    op.create_table('users',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('email', sa.String(254), nullable=False, unique=True),
        sa.Column('password_hash', sa.String(255), nullable=False),
        sa.Column('role', sa.String(20), nullable=False),
        sa.Column('created_at', sa.DateTime, nullable=False),
        sa.Column('is_active', sa.Boolean, nullable=False),
        sa.Column('student_id', sa.Integer, sa.ForeignKey('students.id'), unique=True),
        sa.CheckConstraint("role IN ('student', 'counselor')"),
        sa.CheckConstraint("role = 'student' OR student_id IS NULL"))
    op.create_table('auth_sessions',
        sa.Column('token_hash', sa.String(64), primary_key=True),
        sa.Column('user_id', sa.Integer, sa.ForeignKey('users.id'), index=True),
        sa.Column('csrf_hash', sa.String(64), nullable=False),
        sa.Column('created_at', sa.DateTime, nullable=False),
        sa.Column('expires_at', sa.DateTime, nullable=False, index=True),
        sa.Column('revoked_at', sa.DateTime))
    op.create_table('auth_attempts',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('key_hash', sa.String(64), nullable=False, index=True),
        sa.Column('created_at', sa.DateTime, nullable=False, index=True))


def downgrade():
    op.drop_table('auth_attempts')
    op.drop_table('auth_sessions')
    op.drop_table('users')
