"""Baseline existing student schema; safely adopt an existing unversioned database.

The baseline is frozen independently of application metadata. Existing tables are
left intact; missing legacy tables are created for fresh installations.
"""
from alembic import op
import sqlalchemy as sa
revision = '0001_legacy'
down_revision = None


def upgrade():
    metadata = sa.MetaData()
    sa.Table('students', metadata,
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('display_name', sa.String(100)),
        sa.Column('assessment_answers', sa.JSON, nullable=False),
        sa.Column('created_at', sa.DateTime, nullable=False))
    sa.Table('questionnaires', metadata,
        sa.Column('id', sa.String(100), primary_key=True),
        sa.Column('title', sa.String(200), nullable=False),
        sa.Column('is_sample', sa.Boolean, nullable=False))
    sa.Table('assessment_questions', metadata,
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('questionnaire_id', sa.String(100), sa.ForeignKey('questionnaires.id'), nullable=False),
        sa.Column('key', sa.String(100), nullable=False), sa.Column('prompt', sa.String, nullable=False),
        sa.Column('response_type', sa.String(30), nullable=False), sa.Column('required', sa.Boolean, nullable=False),
        sa.Column('display_order', sa.Integer, nullable=False), sa.Column('options', sa.JSON, nullable=False),
        sa.UniqueConstraint('questionnaire_id', 'key'))
    sa.Table('student_answers', metadata,
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('student_id', sa.Integer, sa.ForeignKey('students.id'), nullable=False),
        sa.Column('question_id', sa.Integer, sa.ForeignKey('assessment_questions.id'), nullable=False),
        sa.Column('value', sa.JSON, nullable=False), sa.UniqueConstraint('student_id', 'question_id'))
    sa.Table('conversations', metadata,
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('student_id', sa.Integer, sa.ForeignKey('students.id'), nullable=False, index=True),
        sa.Column('questionnaire_id', sa.String(100), sa.ForeignKey('questionnaires.id'), nullable=False),
        sa.Column('created_at', sa.DateTime, nullable=False))
    sa.Table('conversation_messages', metadata,
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('conversation_id', sa.Integer, sa.ForeignKey('conversations.id'), nullable=False, index=True),
        sa.Column('role', sa.String(20), nullable=False), sa.Column('content', sa.Text, nullable=False),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('reply_to_message_id', sa.Integer, sa.ForeignKey('conversation_messages.id'), unique=True),
        sa.Column('created_at', sa.DateTime, nullable=False),
        sa.CheckConstraint("role IN ('user', 'assistant')"),
        sa.CheckConstraint("status IN ('pending', 'completed', 'failed')"))
    metadata.create_all(op.get_bind(), checkfirst=True)


def downgrade():
    raise RuntimeError('Baseline downgrade is disabled to preserve student data. Restore a reviewed backup instead.')
