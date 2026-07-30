"""Add the consent-provenance columns for databases already past 0043.

0043 was released without `invalidated_from` / `invalidated_at` /
`invalidation_reason`, and they were added to it *in place* afterwards. Alembic
records a revision as applied and never re-runs it, so every database that had
already reached 0043 was stamped as having those columns while its
`agent_approvals` table did not have them. A fresh install got them; an existing
one never would.

That was not theoretical. A running NUR instance stamped at 0048 — with 0046's
`execution_attempt`, 0047's boundary functions and 0048's `event_seq` all present
— raised `column agent_approvals.invalidated_from does not exist` on the first
step the worker tried to execute, because `load_step_approval` selects the whole
mapped row. The Agency Plane was unusable on that database, and no test caught it:
every test builds its schema from scratch, where the edited 0043 does apply.

The lesson is the ordinary one about migrations, learned the ordinary way: a
released revision is immutable, and a change to it has to be a new revision. This
is that revision. It is idempotent, so a database that already received the
columns from the edited 0043 is unaffected.

Deliberately additive only. Provenance for rows invalidated *before* this ran is
genuinely unrecoverable — the original decision was overwritten and there is
nowhere to read it back from — and inventing a value would fabricate audit
history. Those rows keep NULL provenance, which is the honest record of "we do
not know", and every invalidation from here on carries its own.

Revision ID: 0049_consent_provenance_backfill
Revises: 0048_event_sequence_counter
"""

from __future__ import annotations

from alembic import op

revision = "0049_consent_provenance_backfill"
down_revision = "0048_event_sequence_counter"
branch_labels = None
depends_on = None

COLUMNS = [
    ("invalidated_from", "varchar(20)"),
    ("invalidated_at", "timestamptz"),
    ("invalidation_reason", "text"),
]


def upgrade() -> None:
    for name, column_type in COLUMNS:
        op.execute(
            f"ALTER TABLE agent_approvals ADD COLUMN IF NOT EXISTS {name} {column_type}"
        )


def downgrade() -> None:
    # Left in place on downgrade. 0043 also declares these columns, so dropping
    # them here would leave a database that rolled back only this revision
    # missing columns its own recorded revision claims to have — reintroducing
    # exactly the drift this migration exists to repair.
    pass
