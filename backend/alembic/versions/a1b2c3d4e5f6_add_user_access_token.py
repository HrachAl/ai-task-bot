"""add users.access_token (per-user dashboard key)

Revision ID: a1b2c3d4e5f6
Revises: cd2b26f44810
Create Date: 2026-08-31 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = 'cd2b26f44810'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Nullable first so existing rows survive, then backfilled, then locked
    # down: a single step would fail on any database that already has users.
    op.add_column('users', sa.Column('access_token', sa.String(length=64), nullable=True))
    op.execute(
        "UPDATE users SET access_token = "
        "replace(md5(random()::text || clock_timestamp()::text || id::text) || "
        "md5(random()::text || id::text), '-', '') "
        "WHERE access_token IS NULL"
    )
    op.alter_column('users', 'access_token', nullable=False)
    op.create_index(op.f('ix_users_access_token'), 'users', ['access_token'], unique=True)


def downgrade() -> None:
    op.drop_index(op.f('ix_users_access_token'), table_name='users')
    op.drop_column('users', 'access_token')
