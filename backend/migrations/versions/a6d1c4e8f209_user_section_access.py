"""add per-user section access

Revision ID: a6d1c4e8f209
Revises: f4b8d6e2a731
Create Date: 2026-09-04 00:00:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "a6d1c4e8f209"
down_revision: Union[str, Sequence[str], None] = "f4b8d6e2a731"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("section_access", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "section_access")
