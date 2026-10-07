"""seed permission matrix

Revision ID: 94a1fedfb71d
Revises: ad92c4ac5ccb
Create Date: 2026-10-07 21:41:15.880796

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '94a1fedfb71d'
down_revision: Union[str, Sequence[str], None] = 'ad92c4ac5ccb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

MATRIX = [
    ("support", "general"), ("support", "support"),
    ("operations", "general"), ("operations", "support"), ("operations", "operations"),
    ("hr", "general"), ("hr", "hr"),
]


def upgrade() -> None:
    """Insert Alex's approved role-to-group permission matrix."""
    table = sa.table(
        "role_group_access",
        sa.column("role", sa.String),
        sa.column("access_group", sa.String),
    )
    op.bulk_insert(table, [{"role": r, "access_group": g} for r, g in MATRIX])


def downgrade() -> None:
    """Remove the permission matrix."""
    op.execute("DELETE FROM role_group_access")