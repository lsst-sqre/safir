"""V2 schema

Revision ID: e843cec7e694
Revises: a6e49b57e3c9
Create Date: 2024-09-10 23:16:17.755569+00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e843cec7e694"
down_revision: str | None = "a6e49b57e3c9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column("users", sa.Column("email", sa.String(), nullable=True))
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column("users", "email")
    # ### end Alembic commands ###
