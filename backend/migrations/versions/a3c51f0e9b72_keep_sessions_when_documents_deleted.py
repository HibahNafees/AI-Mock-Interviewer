"""keep sessions when their documents are deleted (T-13)

Revision ID: a3c51f0e9b72
Revises: decf95ca3bdb
Create Date: 2026-10-09 19:20:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a3c51f0e9b72'
down_revision = 'decf95ca3bdb'
branch_labels = None
depends_on = None

COLUMNS = ("resume_id", "jd_id")
# SQLite reflects these FKs without names; this convention names them for batch mode.
CONVENTION = {"fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s"}


def _swap(ondelete):
    inspector = sa.inspect(op.get_bind())
    existing = {
        fk["constrained_columns"][0]: fk["name"]
        for fk in inspector.get_foreign_keys("sessions")
        if fk["constrained_columns"][0] in COLUMNS
    }
    with op.batch_alter_table("sessions", naming_convention=CONVENTION) as batch_op:
        for col in COLUMNS:
            name = existing.get(col) or f"fk_sessions_{col}_documents"
            batch_op.drop_constraint(name, type_="foreignkey")
            batch_op.create_foreign_key(
                f"fk_sessions_{col}_documents", "documents", [col], ["id"], ondelete=ondelete
            )


def upgrade():
    _swap("SET NULL")


def downgrade():
    _swap("CASCADE")
