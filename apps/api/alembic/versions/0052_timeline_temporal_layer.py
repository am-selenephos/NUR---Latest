"""Timeline — the temporal-intelligence layer over canonical records.

Timeline is not a fourth world model either. `timeline_events` (intelligence.py)
already carries the general object — event type, a truth-carrying `status`, links
to goal/objective/plan/project/person/group/orbit/prediction, `time_kind` — and
`scheduled_actions` (living.py) already is, structurally, the §4.14 "Time Block":
a System-scoped action with `scheduled_for`, `duration_minutes` and a status. The
composed views in this migration's API read both rather than inventing a third.

Dependencies reuse `map_edges` from 0051 rather than a new
`timeline_dependencies` table — the Timeline spec says so explicitly ("Reuse Map
dependencies where available"), and `map_edges` already has `DEPENDS_ON` in its
edge-type vocabulary, `timeline_event` in its ref-type vocabulary, and a
`user_confirmed` column that is exactly the "NUR must never mass-reschedule
silently" guarantee this surface needs. The specific dependency flavour (finish
before / start after / can overlap / requires decision / person / resource /
outcome) and any lag are carried in `edge_metadata`, which is schemaless JSONB
with no CHECK to alter — so reusing it costs no migration to 0051 at all.

What has no home anywhere and is added here:

  * `timeline_phases`            a period, e.g. "NUR Beta Completion". Nothing in
                                  NUR models a *span* of time as a first-class
                                  thing; a Plan is a container of steps, not dated.
  * `timeline_recurrences`       a repeating rhythm attached to a template entry.
                                  Glow streaks track consecutive days of an
                                  *achievement*; nothing tracks a recurring
                                  *commitment* with exact-vs-flexible cadence.
  * `timeline_reschedules`       append-only history. `reschedule_timeline_event`
                                  today overwrites `scheduled_for` in place — §29
                                  requires the original time, the new time and the
                                  reason to remain auditable, which an overwrite
                                  cannot do.
  * `timeline_reviews`           a persisted reflection session (daily / weekly /
                                  monthly / project / prediction), with its
                                  findings and the changes it produced.
  * `timeline_external_links`    schema only. No calendar provider is connected in
                                  this repository and none is requested by this
                                  migration — see the router's module docstring
                                  for the honesty label this carries at runtime.
  * `timeline_preferences`       one row per owner: view mode, zoom level, lane
                                  grouping, filters. Simpler than a saved-views
                                  system because the spec names one component
                                  (`TimelineSavedViews`) but never elaborates a
                                  multi-view requirement the way Map's saved views
                                  are elaborated in its own spec.

`timeline_events` itself gains the columns it was missing to carry a genuine
truth model rather than a single `status` string: planned end, actual start/end,
completion quality, time precision (exact / date-only / window / before-date /
after-dependency / flexible-week / horizon / unscheduled), a phase link, energy
type and a visibility scope — reusing the exact scope vocabulary
(`PRIVATE` / `SHARED_ORBIT` / `CAPSULE_ELIGIBLE`) 0051 already established for Map
annotations, so an owner learns one vocabulary rather than a different one per
surface.

Two rules from the spec are enforced here rather than left to services:

  * `date_precision = 'UNSCHEDULED'` requires every date field on the row to be
    NULL. "Unscheduled" cannot quietly carry a date — that is exactly the kind of
    fake precision §17 forbids.
  * A `completion_state` verdict (successful / partially successful / completed
    but ineffective / abandoned / failed) requires `actual_end_at` to be set: a
    quality judgement about something is not storable before the thing has an
    end.

Revision ID: 0052_timeline_temporal_layer
Revises: 0051_map_compositional_layer
"""

from __future__ import annotations

from alembic import op

revision = "0052_timeline_temporal_layer"
down_revision = "0051_map_compositional_layer"
branch_labels = None
depends_on = None

APP_ROLE = "nur_app"
OWNER_UUID = "NULLIF(current_setting('app.current_user_id', true), '')::uuid"
HAS_USER = (
    "current_setting('app.current_user_id', true) IS NOT NULL "
    "AND current_setting('app.current_user_id', true) <> ''"
)

NEW_TABLES = [
    "timeline_phases",
    "timeline_recurrences",
    "timeline_reschedules",
    "timeline_reviews",
    "timeline_external_links",
    "timeline_preferences",
]

# Every truth state actually in production use (PLANNED, COMPLETED, MISSED,
# CANCELLED, DUE — grepped from timeline.py, universe.py and insights.py) plus
# the ones the spec's §5 truth model adds and this repository had no way to
# express: SCHEDULED, IN_PROGRESS, PARTIALLY_COMPLETED, RESCHEDULED, OBSERVED,
# PREDICTED, INFERRED, IMPORTED, ARCHIVED.
STATUS_VALUES = (
    "PLANNED", "SCHEDULED", "IN_PROGRESS", "DUE", "COMPLETED",
    "PARTIALLY_COMPLETED", "MISSED", "RESCHEDULED", "CANCELLED", "OBSERVED",
    "PREDICTED", "INFERRED", "IMPORTED", "ARCHIVED",
)

DATE_PRECISIONS = (
    "EXACT", "DATE_ONLY", "WINDOW", "BEFORE_DATE", "AFTER_DEPENDENCY",
    "FLEXIBLE_WEEK", "HORIZON", "UNSCHEDULED",
)

COMPLETION_STATES = (
    "SUCCESSFUL", "PARTIALLY_SUCCESSFUL", "COMPLETED_BUT_INEFFECTIVE",
    "ABANDONED_INTENTIONALLY", "FAILED", "UNKNOWN",
)

ENERGY_TYPES = (
    "LOW_ENERGY", "MODERATE_FOCUS", "DEEP_WORK", "SOCIAL", "EMOTIONAL",
    "PHYSICAL", "ADMINISTRATIVE",
)

# Reused verbatim from 0051's map_layer vocabulary, so an owner learns one
# privacy vocabulary rather than a different word set per surface.
VISIBILITY_SCOPES = ("PRIVATE", "SHARED_ORBIT", "CAPSULE_ELIGIBLE")

PHASE_STATUSES = ("UPCOMING", "ACTIVE", "COMPLETED", "ARCHIVED")

RECURRENCE_MODES = ("EXACT", "FLEXIBLE")

RESCHEDULE_SOURCES = ("OWNER", "NUR_SUGGESTED", "RIPPLE", "IMPORT_SYNC")

REVIEW_TYPES = ("DAILY", "WEEKLY", "MONTHLY", "PROJECT", "PREDICTION")

SYNC_DIRECTIONS = ("IMPORT_ONLY", "TWO_WAY")

SYNC_STATUSES = ("CONNECTED", "DISCONNECTED", "ERROR")

VIEW_MODES = ("FLOW", "CALENDAR", "HORIZONS", "REVIEW")

ZOOM_LEVELS = ("LIFE_YEAR", "QUARTER", "MONTH", "WEEK", "DAY")

LANE_GROUPINGS = ("UNIFIED", "SYSTEM", "PLAN", "PERSON", "OBJECT_TYPE", "STATUS")

# Columns `timeline_events` was missing to carry a genuine truth model. Added to
# the canonical table on purpose — see module docstring.
TIMELINE_EVENT_COLUMNS = [
    ("ends_at", "timestamptz"),
    ("all_day", "boolean NOT NULL DEFAULT false"),
    ("timezone_name", "varchar(64)"),
    ("date_precision", "varchar(24) NOT NULL DEFAULT 'EXACT'"),
    ("earliest_at", "timestamptz"),
    ("latest_at", "timestamptz"),
    ("actual_start_at", "timestamptz"),
    ("actual_end_at", "timestamptz"),
    ("completion_state", "varchar(32)"),
    ("phase_id", "uuid"),
    ("visibility_scope", "varchar(24) NOT NULL DEFAULT 'PRIVATE'"),
    ("energy_type", "varchar(24)"),
]


def _quoted(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


DDL = f"""
CREATE TABLE timeline_phases (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name varchar(300) NOT NULL,
    description text,
    starts_at timestamptz,
    ends_at timestamptz,
    status varchar(16) NOT NULL DEFAULT 'UPCOMING',
    primary_system_slug varchar(48),
    phase_metadata jsonb NOT NULL DEFAULT '{{}}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_timeline_phase_status CHECK (status IN ({_quoted(PHASE_STATUSES)})),
    CONSTRAINT ck_timeline_phase_name_not_blank CHECK (btrim(name) <> ''),
    CONSTRAINT ck_timeline_phase_span CHECK (
        starts_at IS NULL OR ends_at IS NULL OR ends_at >= starts_at
    )
);
CREATE INDEX ix_timeline_phases_owner ON timeline_phases (owner_user_id, starts_at);

CREATE TABLE timeline_recurrences (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    timeline_event_id uuid NOT NULL REFERENCES timeline_events(id) ON DELETE CASCADE,
    recurrence_rule text NOT NULL,
    recurrence_mode varchar(16) NOT NULL DEFAULT 'EXACT',
    target_frequency integer,
    starts_at timestamptz NOT NULL,
    ends_at timestamptz,
    paused_at timestamptz,
    recurrence_metadata jsonb NOT NULL DEFAULT '{{}}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_timeline_recurrence_mode CHECK (
        recurrence_mode IN ({_quoted(RECURRENCE_MODES)})
    ),
    CONSTRAINT ck_timeline_recurrence_rule_not_blank CHECK (btrim(recurrence_rule) <> ''),
    -- A flexible rhythm ("three times a week, not fixed days") needs a target
    -- count to measure against; an exact one is fully specified by the rule.
    CONSTRAINT ck_timeline_recurrence_flexible_needs_target CHECK (
        recurrence_mode = 'EXACT' OR target_frequency IS NOT NULL
    ),
    CONSTRAINT uq_timeline_recurrence_one_per_entry UNIQUE (timeline_event_id)
);
CREATE INDEX ix_timeline_recurrences_owner ON timeline_recurrences (owner_user_id);

CREATE TABLE timeline_reschedules (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    timeline_event_id uuid NOT NULL REFERENCES timeline_events(id) ON DELETE CASCADE,
    previous_start_at timestamptz,
    previous_end_at timestamptz,
    new_start_at timestamptz,
    new_end_at timestamptz,
    reason text,
    source varchar(24) NOT NULL DEFAULT 'OWNER',
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_timeline_reschedule_source CHECK (source IN ({_quoted(RESCHEDULE_SOURCES)}))
);
CREATE INDEX ix_timeline_reschedules_entry
    ON timeline_reschedules (timeline_event_id, created_at DESC);

CREATE TABLE timeline_reviews (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    review_type varchar(24) NOT NULL,
    period_start timestamptz NOT NULL,
    period_end timestamptz NOT NULL,
    summary text,
    findings jsonb NOT NULL DEFAULT '[]'::jsonb,
    accepted_changes jsonb NOT NULL DEFAULT '[]'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_timeline_review_type CHECK (review_type IN ({_quoted(REVIEW_TYPES)})),
    CONSTRAINT ck_timeline_review_period CHECK (period_end >= period_start)
);
CREATE INDEX ix_timeline_reviews_owner
    ON timeline_reviews (owner_user_id, review_type, period_start DESC);

CREATE TABLE timeline_external_links (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    timeline_event_id uuid NOT NULL REFERENCES timeline_events(id) ON DELETE CASCADE,
    provider varchar(48) NOT NULL,
    external_id varchar(200) NOT NULL,
    sync_direction varchar(16) NOT NULL DEFAULT 'IMPORT_ONLY',
    sync_status varchar(24) NOT NULL DEFAULT 'DISCONNECTED',
    last_synced_at timestamptz,
    external_metadata jsonb NOT NULL DEFAULT '{{}}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_timeline_external_direction CHECK (
        sync_direction IN ({_quoted(SYNC_DIRECTIONS)})
    ),
    CONSTRAINT ck_timeline_external_status CHECK (sync_status IN ({_quoted(SYNC_STATUSES)})),
    CONSTRAINT uq_timeline_external_identity UNIQUE (owner_user_id, provider, external_id)
);
CREATE INDEX ix_timeline_external_links_entry ON timeline_external_links (timeline_event_id);

CREATE TABLE timeline_preferences (
    owner_user_id uuid PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    view_mode varchar(16) NOT NULL DEFAULT 'FLOW',
    zoom_level varchar(16) NOT NULL DEFAULT 'MONTH',
    lane_grouping varchar(16) NOT NULL DEFAULT 'UNIFIED',
    filters jsonb NOT NULL DEFAULT '{{}}'::jsonb,
    timezone_name varchar(64),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_timeline_pref_view_mode CHECK (view_mode IN ({_quoted(VIEW_MODES)})),
    CONSTRAINT ck_timeline_pref_zoom CHECK (zoom_level IN ({_quoted(ZOOM_LEVELS)})),
    CONSTRAINT ck_timeline_pref_lane CHECK (lane_grouping IN ({_quoted(LANE_GROUPINGS)}))
);
"""


def _statements(ddl: str) -> list[str]:
    """Split a DDL document into statements, ignoring `;` inside `--` comments.

    Same splitter as 0050 and 0051, same reason: asyncpg prepares every statement
    and a prepared statement holds exactly one command, and a plain
    `ddl.split(";")` previously cut a CREATE TABLE in half on a semicolon inside a
    comment.
    """
    cleaned: list[str] = []
    for line in ddl.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("--"):
            continue
        if "--" in line:
            line = line[: line.index("--")]
        cleaned.append(line)
    return [part.strip() for part in "\n".join(cleaned).split(";") if part.strip()]


def _owner_all(table: str) -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY p_{table}_owner_select ON {table} FOR SELECT TO {APP_ROLE} "
        f"USING ({HAS_USER} AND owner_user_id = {OWNER_UUID})"
    )
    op.execute(
        f"CREATE POLICY p_{table}_owner_insert ON {table} FOR INSERT TO {APP_ROLE} "
        f"WITH CHECK ({HAS_USER} AND owner_user_id = {OWNER_UUID})"
    )
    op.execute(
        f"CREATE POLICY p_{table}_owner_update ON {table} FOR UPDATE TO {APP_ROLE} "
        f"USING ({HAS_USER} AND owner_user_id = {OWNER_UUID}) "
        f"WITH CHECK (owner_user_id = {OWNER_UUID})"
    )
    op.execute(
        f"CREATE POLICY p_{table}_owner_delete ON {table} FOR DELETE TO {APP_ROLE} "
        f"USING ({HAS_USER} AND owner_user_id = {OWNER_UUID})"
    )


def upgrade() -> None:
    for name, column_type in TIMELINE_EVENT_COLUMNS:
        op.execute(
            f"ALTER TABLE timeline_events ADD COLUMN IF NOT EXISTS {name} {column_type}"
        )

    for statement in _statements(DDL):
        op.execute(statement)

    op.execute(
        "ALTER TABLE timeline_events ADD CONSTRAINT fk_timeline_events_phase "
        "FOREIGN KEY (phase_id) REFERENCES timeline_phases(id) ON DELETE SET NULL"
    )
    # 0015 already put an unnamed inline CHECK on this column restricting it to
    # the five original values (Postgres auto-named it
    # `timeline_events_status_check`). Adding a second, wider CHECK beside it
    # would not replace that one — both apply, ANDed together — so every new
    # vocabulary word (SCHEDULED, IN_PROGRESS, RESCHEDULED, OBSERVED, PREDICTED,
    # INFERRED, IMPORTED, PARTIALLY_COMPLETED, ARCHIVED) would still be rejected
    # by the old constraint even though this migration means to allow it. The old
    # one has to go before the new one can mean anything.
    op.execute(
        "ALTER TABLE timeline_events DROP CONSTRAINT IF EXISTS timeline_events_status_check"
    )
    op.execute(
        "ALTER TABLE timeline_events ADD CONSTRAINT ck_timeline_event_status "
        f"CHECK (status IN ({_quoted(STATUS_VALUES)}))"
    )
    op.execute(
        "ALTER TABLE timeline_events ADD CONSTRAINT ck_timeline_event_precision "
        f"CHECK (date_precision IN ({_quoted(DATE_PRECISIONS)}))"
    )
    op.execute(
        "ALTER TABLE timeline_events ADD CONSTRAINT ck_timeline_event_completion_state "
        f"CHECK (completion_state IS NULL OR completion_state IN ({_quoted(COMPLETION_STATES)}))"
    )
    op.execute(
        "ALTER TABLE timeline_events ADD CONSTRAINT ck_timeline_event_energy_type "
        f"CHECK (energy_type IS NULL OR energy_type IN ({_quoted(ENERGY_TYPES)}))"
    )
    op.execute(
        "ALTER TABLE timeline_events ADD CONSTRAINT ck_timeline_event_visibility "
        f"CHECK (visibility_scope IN ({_quoted(VISIBILITY_SCOPES)}))"
    )
    # §17: "Unscheduled" cannot quietly carry a date. Every date-bearing column
    # must be NULL for that precision, so the holding field is honest about
    # holding nothing.
    op.execute(
        "ALTER TABLE timeline_events ADD CONSTRAINT ck_timeline_event_unscheduled_has_no_date "
        "CHECK (date_precision <> 'UNSCHEDULED' OR ("
        "scheduled_for IS NULL AND ends_at IS NULL "
        "AND earliest_at IS NULL AND latest_at IS NULL))"
    )
    # A completion-quality verdict is not storable before the thing has an end.
    op.execute(
        "ALTER TABLE timeline_events ADD CONSTRAINT ck_timeline_event_completion_needs_actual "
        "CHECK (completion_state IS NULL OR actual_end_at IS NOT NULL)"
    )

    for table in NEW_TABLES:
        _owner_all(table)
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO {APP_ROLE}")


def downgrade() -> None:
    for table in reversed(NEW_TABLES):
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
    for constraint in (
        "ck_timeline_event_completion_needs_actual",
        "ck_timeline_event_unscheduled_has_no_date",
        "ck_timeline_event_visibility",
        "ck_timeline_event_energy_type",
        "ck_timeline_event_completion_state",
        "ck_timeline_event_precision",
        "ck_timeline_event_status",
        "fk_timeline_events_phase",
    ):
        op.execute(f"ALTER TABLE timeline_events DROP CONSTRAINT IF EXISTS {constraint}")
    # Restore 0015's original constraint so a downgrade leaves the table exactly
    # as 0015 left it, not merely unconstrained.
    op.execute(
        "ALTER TABLE timeline_events ADD CONSTRAINT timeline_events_status_check "
        "CHECK (status IN ('PLANNED','DUE','COMPLETED','MISSED','CANCELLED'))"
    )
    for name, _type in reversed(TIMELINE_EVENT_COLUMNS):
        op.execute(f"ALTER TABLE timeline_events DROP COLUMN IF EXISTS {name}")
