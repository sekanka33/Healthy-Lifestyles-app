"""hydration reminder defaults: every 90 minutes, quiet 22:00-07:00

Until now no screen could change these settings, so existing rows still hold the old defaults unless
someone called the API directly. Only rows that have never been switched on are moved.

Revision ID: 0002
Revises: 0001
"""
from typing import Sequence, Union

from alembic import op


revision: str = '0002'
down_revision: Union[str, None] = '0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "UPDATE notification_preferences SET hydration_reminder_interval_minutes = 90 "
        "WHERE hydration_reminders_enabled = false AND hydration_reminder_interval_minutes = 120"
    )
    op.execute(
        "UPDATE notification_preferences SET quiet_hours_start = '22:00:00', quiet_hours_end = '07:00:00' "
        "WHERE hydration_reminders_enabled = false AND quiet_hours_start IS NULL AND quiet_hours_end IS NULL"
    )


def downgrade() -> None:
    # Nothing to undo: the old defaults are not worth restoring over values people may have since chosen.
    pass
