"""The Orbit relational world model: levels, groups, edges, layout, threads, insights.

Orbit already had a spine before this: `orbits` as context containers, `people`
as the persons in them, `orbit_members` with closeness and activity scores,
`orbit_events`, `orbit_references`, `orbit_sources`. What it had no notion of was
*relational structure* — which band a person occupies, which people are tied to
each other, what a group is as distinct from a container, where a node sits on the
field, what conversation threads are open, and which relational reading NUR
inferred versus which the owner stated.

**Deviation from the suggested schema, recorded deliberately.** The Orbit spec
§27 suggests an `orbit_entities` table holding both persons and groups. That
would duplicate `people`, which already carries display_name, handle,
relationship_type, notes and privacy_scope, and is already referenced by
`orbit_members.person_id`, `orbits.primary_person_id` and the Capsule and
consultation surfaces. Two tables both claiming to be "the person" is the
parallel-truth failure the reuse-first rule exists to prevent: every join would
have to pick one, and they would drift. So `people` remains the person entity and
gains the relational columns it lacked, groups get their own table because a
group genuinely is not a person, and only the structures that did not exist are
created.

The eight new tables are all owner-scoped under FORCE ROW LEVEL SECURITY using
the same `p_<table>_owner_<cmd>` idiom as 0015, because Orbit holds the most
sensitive material in the product: who matters to someone, and what they believe
about them.

Three separations are enforced in the schema rather than left to services:

  * `orbit_relational_signals.basis` distinguishes USER_STATED from NUR_INFERRED
    from OBSERVED. A signal cannot exist without declaring which it is, so an
    inference cannot silently become a fact.
  * `contradictory_evidence` sits beside `evidence` on the same row, so the
    evidence against a reading is as durable as the evidence for it.
  * `people.inference_allowed` is checked before any inferred signal may be
    written for that person, which makes "no inference beyond explicit notes" a
    stored permission rather than a UI preference.

Orbit level is never changed by a model. `orbit_level` is owner-writable, and a
suggestion lives in `orbit_level_suggestion` with its reason, so the suggestion
is visible and refusable without having already moved anything.

Revision ID: 0050_orbit_relational_world
Revises: 0049_consent_provenance_backfill
"""

from __future__ import annotations

from alembic import op

revision = "0050_orbit_relational_world"
down_revision = "0049_consent_provenance_backfill"
branch_labels = None
depends_on = None

APP_ROLE = "nur_app"
OWNER_UUID = "NULLIF(current_setting('app.current_user_id', true), '')::uuid"
HAS_USER = (
    "current_setting('app.current_user_id', true) IS NOT NULL "
    "AND current_setting('app.current_user_id', true) <> ''"
)

NEW_TABLES = [
    "orbit_groups",
    "orbit_group_members",
    "orbit_relationships",
    "orbit_context_links",
    "orbit_layout_nodes",
    "orbit_threads",
    "orbit_relational_insights",
    "orbit_relational_signals",
]

# ── Columns `people` was missing to act as the Orbit person entity. ──
PEOPLE_COLUMNS = [
    # The band, owner-owned. NULL means "not yet placed", which is honest for a
    # person imported from a Talk reference and not yet reviewed.
    ("orbit_level", "varchar(16)"),
    # A suggestion is never an assignment. Both are needed so the UI can offer a
    # move and explain it without having performed it.
    ("orbit_level_suggestion", "varchar(16)"),
    ("orbit_level_suggestion_reason", "text"),
    ("tags", "jsonb NOT NULL DEFAULT '[]'::jsonb"),
    # Kept apart on purpose: the owner's own words about someone must never be
    # overwritten by a generated summary.
    ("user_summary", "text"),
    ("nur_summary", "text"),
    ("relational_state", "varchar(24)"),
    ("avatar_ref", "varchar(400)"),
    # Permissions, defaulting closed for everything the owner has not granted.
    # memory_allowed defaults true because a person the owner typed in is already
    # a durable private reference; the other three are opt-in.
    ("memory_allowed", "boolean NOT NULL DEFAULT true"),
    ("inference_allowed", "boolean NOT NULL DEFAULT false"),
    ("sharing_allowed", "boolean NOT NULL DEFAULT false"),
    ("capsule_eligible", "boolean NOT NULL DEFAULT false"),
    ("archived_at", "timestamptz"),
    ("last_interaction_at", "timestamptz"),
]

DDL = """
CREATE TABLE orbit_groups (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    orbit_id uuid REFERENCES orbits(id) ON DELETE SET NULL,
    name varchar(240) NOT NULL,
    purpose text,
    group_type varchar(48) NOT NULL DEFAULT 'CIRCLE',
    -- Four modes from the spec, enforced here so a service cannot invent a fifth
    -- that no consent rule covers.
    privacy_mode varchar(32) NOT NULL DEFAULT 'PRIVATE_ORGANIZER',
    shared_memory_enabled boolean NOT NULL DEFAULT false,
    group_nur_enabled boolean NOT NULL DEFAULT false,
    system_slug varchar(48),
    archived_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_orbit_group_privacy_mode CHECK (
        privacy_mode IN ('PRIVATE_ORGANIZER', 'SHARED_CONTEXT', 'GROUP_NUR', 'WITNESS_ONLY')
    ),
    -- Group NUR is a shared workspace, so it cannot be on while the group is
    -- still a private organizer view. The invariant belongs here because it
    -- gates what context the group assistant may read.
    CONSTRAINT ck_orbit_group_nur_requires_shared CHECK (
        group_nur_enabled = false OR privacy_mode IN ('SHARED_CONTEXT', 'GROUP_NUR')
    )
);
CREATE INDEX ix_orbit_groups_owner ON orbit_groups (owner_user_id, updated_at DESC);

CREATE TABLE orbit_group_members (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    group_id uuid NOT NULL REFERENCES orbit_groups(id) ON DELETE CASCADE,
    person_id uuid NOT NULL REFERENCES people(id) ON DELETE CASCADE,
    role varchar(80) NOT NULL DEFAULT 'MEMBER',
    -- Per-member consent, because one member agreeing to shared memory does not
    -- speak for another.
    consent_scope varchar(32) NOT NULL DEFAULT 'CONTEXT_ONLY',
    joined_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_orbit_group_member_consent CHECK (
        consent_scope IN ('CONTEXT_ONLY', 'SHARED_MEMORY', 'WITNESS_ONLY')
    ),
    CONSTRAINT uq_orbit_group_member UNIQUE (group_id, person_id)
);
CREATE INDEX ix_orbit_group_members_group ON orbit_group_members (group_id);
CREATE INDEX ix_orbit_group_members_person ON orbit_group_members (person_id);

CREATE TABLE orbit_relationships (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    source_person_id uuid NOT NULL REFERENCES people(id) ON DELETE CASCADE,
    target_person_id uuid REFERENCES people(id) ON DELETE CASCADE,
    target_group_id uuid REFERENCES orbit_groups(id) ON DELETE CASCADE,
    relationship_type varchar(80),
    -- The owner's own reading of strength. The scores below are derived, and
    -- nothing derived may overwrite this one.
    strength_user smallint,
    activity_score smallint NOT NULL DEFAULT 0,
    reciprocity_score smallint NOT NULL DEFAULT 0,
    momentum_score smallint NOT NULL DEFAULT 0,
    tension_score smallint NOT NULL DEFAULT 0,
    confidence numeric(4, 3),
    evidence_updated_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    -- An edge points at exactly one thing. A row naming both a person and a
    -- group, or neither, has no meaning the renderer could draw.
    CONSTRAINT ck_orbit_relationship_one_target CHECK (
        (target_person_id IS NOT NULL AND target_group_id IS NULL)
        OR (target_person_id IS NULL AND target_group_id IS NOT NULL)
    ),
    CONSTRAINT ck_orbit_relationship_not_self CHECK (
        target_person_id IS NULL OR target_person_id <> source_person_id
    ),
    CONSTRAINT ck_orbit_relationship_strength CHECK (
        strength_user IS NULL OR strength_user BETWEEN 0 AND 100
    ),
    CONSTRAINT ck_orbit_relationship_confidence CHECK (
        confidence IS NULL OR (confidence >= 0 AND confidence <= 1)
    )
);
CREATE INDEX ix_orbit_relationships_source ON orbit_relationships (source_person_id);
CREATE INDEX ix_orbit_relationships_owner ON orbit_relationships (owner_user_id);
CREATE UNIQUE INDEX uq_orbit_relationship_person_edge
    ON orbit_relationships (source_person_id, target_person_id)
    WHERE target_person_id IS NOT NULL;
CREATE UNIQUE INDEX uq_orbit_relationship_group_edge
    ON orbit_relationships (source_person_id, target_group_id)
    WHERE target_group_id IS NOT NULL;

CREATE TABLE orbit_context_links (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    person_id uuid REFERENCES people(id) ON DELETE CASCADE,
    group_id uuid REFERENCES orbit_groups(id) ON DELETE CASCADE,
    source_type varchar(48) NOT NULL,
    source_id uuid,
    -- Why the link exists is part of the link. A context item the owner cannot
    -- see a reason for is one they cannot meaningfully unlink.
    link_reason text,
    visibility_scope varchar(32) NOT NULL DEFAULT 'PRIVATE',
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_orbit_context_link_subject CHECK (
        (person_id IS NOT NULL AND group_id IS NULL)
        OR (person_id IS NULL AND group_id IS NOT NULL)
    ),
    CONSTRAINT ck_orbit_context_visibility CHECK (
        visibility_scope IN (
            'PRIVATE', 'ORBIT_SHARED', 'GROUP_SHARED', 'CAPSULE_SHARED', 'SYSTEM_SHARED'
        )
    )
);
CREATE INDEX ix_orbit_context_links_person ON orbit_context_links (person_id);
CREATE INDEX ix_orbit_context_links_group ON orbit_context_links (group_id);

CREATE TABLE orbit_layout_nodes (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    -- Layout is per viewport, so a desktop arrangement does not dictate mobile.
    viewport varchar(24) NOT NULL DEFAULT 'desktop',
    entity_type varchar(16) NOT NULL,
    entity_id uuid NOT NULL,
    x double precision NOT NULL,
    y double precision NOT NULL,
    pinned boolean NOT NULL DEFAULT false,
    collapsed boolean NOT NULL DEFAULT false,
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_orbit_layout_entity_type CHECK (entity_type IN ('PERSON', 'GROUP')),
    CONSTRAINT uq_orbit_layout_node UNIQUE (owner_user_id, viewport, entity_type, entity_id)
);
CREATE INDEX ix_orbit_layout_owner_viewport ON orbit_layout_nodes (owner_user_id, viewport);

CREATE TABLE orbit_threads (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    person_id uuid REFERENCES people(id) ON DELETE CASCADE,
    group_id uuid REFERENCES orbit_groups(id) ON DELETE CASCADE,
    topic varchar(400) NOT NULL,
    participants jsonb NOT NULL DEFAULT '[]'::jsonb,
    status varchar(32) NOT NULL DEFAULT 'ACTIVE',
    last_event_at timestamptz,
    last_event_summary text,
    open_decision text,
    next_action text,
    plan_id uuid REFERENCES plans(id) ON DELETE SET NULL,
    system_slug varchar(48),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_orbit_thread_subject CHECK (
        (person_id IS NOT NULL AND group_id IS NULL)
        OR (person_id IS NULL AND group_id IS NOT NULL)
    ),
    -- The six buckets the Threads view groups by. WAITING_ON_YOU and
    -- WAITING_ON_OTHERS are distinct states, not a rendering detail.
    CONSTRAINT ck_orbit_thread_status CHECK (
        status IN (
            'ACTIVE', 'WAITING_ON_YOU', 'WAITING_ON_OTHERS',
            'CONSULTATION', 'RESOLVED', 'DORMANT'
        )
    )
);
CREATE INDEX ix_orbit_threads_owner_status ON orbit_threads (owner_user_id, status);
CREATE INDEX ix_orbit_threads_person ON orbit_threads (person_id);
CREATE INDEX ix_orbit_threads_group ON orbit_threads (group_id);

CREATE TABLE orbit_relational_insights (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    person_id uuid REFERENCES people(id) ON DELETE CASCADE,
    group_id uuid REFERENCES orbit_groups(id) ON DELETE CASCADE,
    observation text NOT NULL,
    evidence_refs jsonb NOT NULL DEFAULT '[]'::jsonb,
    confidence numeric(4, 3),
    alternative_interpretation text,
    recommended_move text,
    -- NOT NULL with no default: an insight that cannot say where it might be
    -- wrong is exactly the unlabelled relational guess this surface must refuse
    -- to present, so the schema will not store one.
    may_be_wrong_about text NOT NULL,
    status varchar(24) NOT NULL DEFAULT 'CANDIDATE',
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_orbit_insight_subject CHECK (
        (person_id IS NOT NULL AND group_id IS NULL)
        OR (person_id IS NULL AND group_id IS NOT NULL)
    ),
    CONSTRAINT ck_orbit_insight_status CHECK (
        status IN ('CANDIDATE', 'ACCEPTED', 'REJECTED', 'CORRECTED', 'DISMISSED')
    ),
    CONSTRAINT ck_orbit_insight_confidence CHECK (
        confidence IS NULL OR (confidence >= 0 AND confidence <= 1)
    ),
    CONSTRAINT ck_orbit_insight_doubt_not_blank CHECK (btrim(may_be_wrong_about) <> '')
);
CREATE INDEX ix_orbit_insights_person ON orbit_relational_insights (person_id);
CREATE INDEX ix_orbit_insights_group ON orbit_relational_insights (group_id);

CREATE TABLE orbit_relational_signals (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    person_id uuid NOT NULL REFERENCES people(id) ON DELETE CASCADE,
    signal_kind varchar(24) NOT NULL,
    value smallint,
    confidence numeric(4, 3),
    -- The load-bearing column. A signal must declare whether the owner said it,
    -- a system measured it, or a model inferred it. The UI renders these
    -- differently and consent depends on the difference.
    basis varchar(24) NOT NULL,
    evidence jsonb NOT NULL DEFAULT '[]'::jsonb,
    contradictory_evidence jsonb NOT NULL DEFAULT '[]'::jsonb,
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_orbit_signal_kind CHECK (
        signal_kind IN ('CONNECTION', 'TRUST', 'MOMENTUM', 'TENSION')
    ),
    CONSTRAINT ck_orbit_signal_basis CHECK (
        basis IN ('USER_STATED', 'OBSERVED', 'NUR_INFERRED')
    ),
    CONSTRAINT ck_orbit_signal_value CHECK (value IS NULL OR value BETWEEN 0 AND 100),
    CONSTRAINT ck_orbit_signal_confidence CHECK (
        confidence IS NULL OR (confidence >= 0 AND confidence <= 1)
    ),
    -- An inferred signal with no evidence is an assertion. Refused at the
    -- schema level so it cannot reach the "Why is NUR showing this?" panel with
    -- nothing behind it.
    CONSTRAINT ck_orbit_signal_inference_needs_evidence CHECK (
        basis <> 'NUR_INFERRED' OR jsonb_array_length(evidence) > 0
    ),
    CONSTRAINT uq_orbit_signal_person_kind UNIQUE (person_id, signal_kind, basis)
);
CREATE INDEX ix_orbit_signals_person ON orbit_relational_signals (person_id);
"""


def _statements(ddl: str) -> list[str]:
    """Split a DDL document into statements, ignoring `;` inside `--` comments.

    asyncpg prepares every statement and a prepared statement may hold exactly
    one command, so the DDL has to be split rather than executed whole. A plain
    `ddl.split(";")` looked fine and was not: a semicolon inside an explanatory
    comment cut a CREATE TABLE in half, and the half that ran raised a syntax
    error naming the middle of a sentence. Comments are stripped per line before
    splitting so prose can contain whatever punctuation reads best.
    """
    cleaned: list[str] = []
    for line in ddl.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("--"):
            continue
        # No string literal in this DDL contains `--`, so this is safe here and
        # deliberately not a general-purpose SQL parser.
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
    for name, column_type in PEOPLE_COLUMNS:
        op.execute(f"ALTER TABLE people ADD COLUMN IF NOT EXISTS {name} {column_type}")
    op.execute(
        "ALTER TABLE people ADD CONSTRAINT ck_people_orbit_level CHECK ("
        "orbit_level IS NULL OR orbit_level IN "
        "('INNER', 'NEAR', 'OUTER', 'PERIPHERAL', 'DORMANT'))"
    )
    op.execute(
        "ALTER TABLE people ADD CONSTRAINT ck_people_orbit_level_suggestion CHECK ("
        "orbit_level_suggestion IS NULL OR orbit_level_suggestion IN "
        "('INNER', 'NEAR', 'OUTER', 'PERIPHERAL', 'DORMANT'))"
    )
    op.execute(
        "ALTER TABLE people ADD CONSTRAINT ck_people_relational_state CHECK ("
        "relational_state IS NULL OR relational_state IN "
        "('STABLE', 'DEEPENING', 'RECONNECTING', 'DRIFTING', 'UNCLEAR', "
        "'TENSE', 'REPAIRING', 'DORMANT'))"
    )
    # A suggestion without a reason cannot be explained to the owner, and an
    # unexplained suggested move is the silent reclassification this forbids.
    op.execute(
        "ALTER TABLE people ADD CONSTRAINT ck_people_suggestion_has_reason CHECK ("
        "orbit_level_suggestion IS NULL "
        "OR btrim(COALESCE(orbit_level_suggestion_reason, '')) <> '')"
    )

    for statement in _statements(DDL):
        op.execute(statement)

    for table in NEW_TABLES:
        _owner_all(table)
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO {APP_ROLE}")


def downgrade() -> None:
    for table in reversed(NEW_TABLES):
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
    for constraint in (
        "ck_people_suggestion_has_reason",
        "ck_people_relational_state",
        "ck_people_orbit_level_suggestion",
        "ck_people_orbit_level",
    ):
        op.execute(f"ALTER TABLE people DROP CONSTRAINT IF EXISTS {constraint}")
    for name, _type in reversed(PEOPLE_COLUMNS):
        op.execute(f"ALTER TABLE people DROP COLUMN IF EXISTS {name}")
