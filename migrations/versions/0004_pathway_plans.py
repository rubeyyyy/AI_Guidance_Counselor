"""Persist each student's assessment-based roadmap and progress."""
from alembic import op
import sqlalchemy as sa

revision = '0004_pathway_plans'
down_revision = '0003_email_verification'


def upgrade():
    op.create_table('pathway_plans',
        sa.Column('student_id', sa.Integer, sa.ForeignKey('students.id'), primary_key=True),
        sa.Column('data', sa.JSON, nullable=False))


def downgrade():
    op.drop_table('pathway_plans')
