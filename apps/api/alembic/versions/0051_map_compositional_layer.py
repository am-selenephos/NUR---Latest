"""Map — the compositional and causal layer over canonical NUR records.

Map is not a new world model. Systems, goals, objectives, plans, plan steps,
actions, decisions, outcomes, predictions, research, signals, people and timeline
events all already exist and are already owner-scoped, and `/api/v1/map` already
composes most of them into a node/edge graph. Duplicating any of them would
create two tables both claiming to be "the goal", which is the parallel-truth
failure that reuse-first exists to prevent.

So this migration adds only what Map genuinely needs and nowhere has:

  * `map_views`            saved Universe/Focus/Paths/Decisions views
  * `map_layouts`          owner-positioned nodes, per view and per viewport
  * `map_edges`            semantic relationships the owner drew or accepted
  * `map_suggestions`      candidate proposals awaiting owner review
  * `map_annotations`      owner notes attached to any canonical entity
  * `map_decision_options` the options, trade-offs and reversibility of a
                           canonical `decisions` row, which today stores only a
                           statement, a rationale and a status
  * `map_blockers`         an addressable blocker. Today a "blocker" in the graph
                           is any `system_actions` row whose status is MISSED, or
                           a bare string inside `system_diagnostics.blockers`.
                           Neither can say what it affects, what evidence it
                           rests on, whether the owner agrees it is real, or how
                           it was resolved, so neither can be acted on.

`predictions` is **extended, not replaced**, the same way `people` was extended
for Orbit in 0050: it gains assumptions, confidence, horizon, review date, a
resolution verdict and the learning that came out of it.

Four rules the spec states in prose are enforced here in the schema instead, so
no service, route or UI can quietly bypass them:

  * A prediction cannot be stored as certainty. `ck_predictions_never_certain`
    requires `confidence` to sit strictly between 0 and 1, so "Never represent
    prediction as certainty" is a stored guarantee rather than a rendering habit.
  * A suggestion cannot exist without a readable explanation, so the "Why?"
    action on every candidate always has something true to show.
  * An edge NUR inferred must name what it inferred from
    (`ck_map_edge_inference_needs_source`), and no inferred edge counts as part
    of the map until `user_confirmed` is set — "never infer and permanently
    create a relationship without user acceptance" becomes a column, not a code
    path.
  * A psychological, emotional or relational blocker that NUR inferred may not
    reach `OPEN` — it stays `PROPOSED` until `confirmed_by_owner`. §20 says NUR
    must not label such conditions as fact; this makes asserting one impossible
    rather than merely discouraged.

Revision ID: 0051_map_compositional_layer
Revises: 0050_orbit_relational_world
"""

from __future__ import annotations

from alembic import op

revision = "0051_map_compositional_layer"
down_revision = "0050_orbit_relational_world"
branch_labels = None
depends_on = None

APP_ROLE = "nur_app"
OWNER_UUID = "NULLIF(current_setting('app.current_user_id', true), '')::uuid"
HAS_USER = (
    "current_setting('app.current_user_id', true) IS NOT NULL "
    "AND current_setting('app.current_user_id', true) <> ''"
)

NEW_TABLES = [
    "map_views",
    "map_layouts",
    "map_edges",
    "map_suggestions",
    "map_annotations",
    "map_decision_options",
    "map_blockers",
]

# Canonical entity kinds a Map row may point at. Constrained so a typo cannot
# create a layout or annotation that no graph will ever be able to resolve.
REF_TYPES = (
    "nur",
    "system",
    "goal",
    "objective",
    "plan",
    "plan_step",
    "action",
    "scheduled_action",
    "decision",
    "decision_option",
    "blocker",
    "outcome",
    "prediction",
    "insight",
    "person",
    "group",
    "orbit",
    "timeline_event",
    "research_source",
    "web_signal",
    "project",
    "project_task",
    "journal_entry",
    "experiment",
    "hypothesis",
)

EDGE_TYPES = (
    "PART_OF",
    "DEPENDS_ON",
    "SUPPORTS",
    "ENABLES",
    "BLOCKS",
    "CONTRADICTS",
    "LEADS_TO",
    "EVIDENCE_FOR",
    "INVOLVES",
    "PREDICTED_TO_PRODUCE",
)

SUGGESTION_TYPES = (
    "CONNECTION",
    "DEPENDENCY",
    "BLOCKER",
    "CONFLICTING_GOAL",
    "DUPLICATE_PLAN",
    "STALE_ASSUMPTION",
    "PATH",
    "SYSTEM_IMBALANCE",
)

# Columns `predictions` was missing to carry a reviewable future rather than a
# bare statement. Added to the canonical table on purpose — see module docstring.
PREDICTION_COLUMNS = [
    ("assumptions", "jsonb NOT NULL DEFAULT '[]'::jsonb"),
    ("confidence", "numeric(4, 3)"),
    ("horizon_days", "integer"),
    ("review_by", "timestamptz"),
    ("resolution", "varchar(24)"),
    ("learning", "text"),
]


def _quoted(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


DDL = f"""
CREATE TABLE map_views (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name varchar(200) NOT NULL,
    view_type varchar(24) NOT NULL,
    root_entity_type varchar(32),
    root_entity_id uuid,
    filters jsonb NOT NULL DEFAULT '{{}}'::jsonb,
    is_default boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_map_view_type CHECK (
        view_type IN ('UNIVERSE', 'FOCUS', 'PATHS', 'DECISIONS')
    ),
    CONSTRAINT ck_map_view_root_type CHECK (
        root_entity_type IS NULL OR root_entity_type IN ({_quoted(REF_TYPES)})
    ),
    -- A Focus view is focus *on* something. Without a root it would render the
    -- Universe while claiming to be focused.
    CONSTRAINT ck_map_view_focus_needs_root CHECK (
        view_type <> 'FOCUS'
        OR (root_entity_type IS NOT NULL AND root_entity_id IS NOT NULL)
    ),
    CONSTRAINT ck_map_view_name_not_blank CHECK (btrim(name) <> '')
);
CREATE INDEX ix_map_views_owner ON map_views (owner_user_id, updated_at DESC);
CREATE UNIQUE INDEX uq_map_views_one_default ON map_views (owner_user_id)
    WHERE is_default;

CREATE TABLE map_layouts (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    map_view_id uuid NOT NULL REFERENCES map_views(id) ON DELETE CASCADE,
    viewport_key varchar(32) NOT NULL DEFAULT 'desktop',
    node_ref_type varchar(32) NOT NULL,
    node_ref_id varchar(64) NOT NULL,
    x double precision NOT NULL,
    y double precision NOT NULL,
    pinned boolean NOT NULL DEFAULT false,
    collapsed boolean NOT NULL DEFAULT false,
    layer integer NOT NULL DEFAULT 0,
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_map_layout_ref_type CHECK (
        node_ref_type IN ({_quoted(REF_TYPES)})
    ),
    CONSTRAINT uq_map_layout_node UNIQUE (
        owner_user_id, map_view_id, viewport_key, node_ref_type, node_ref_id
    )
);
CREATE INDEX ix_map_layouts_view ON map_layouts (map_view_id, viewport_key);

CREATE TABLE map_edges (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    source_ref_type varchar(32) NOT NULL,
    source_ref_id varchar(64) NOT NULL,
    target_ref_type varchar(32) NOT NULL,
    target_ref_id varchar(64) NOT NULL,
    edge_type varchar(32) NOT NULL,
    direction varchar(16) NOT NULL DEFAULT 'DIRECTED',
    user_confirmed boolean NOT NULL DEFAULT false,
    inference_source varchar(64),
    confidence numeric(4, 3),
    note text,
    edge_metadata jsonb NOT NULL DEFAULT '{{}}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_map_edge_source_type CHECK (
        source_ref_type IN ({_quoted(REF_TYPES)})
    ),
    CONSTRAINT ck_map_edge_target_type CHECK (
        target_ref_type IN ({_quoted(REF_TYPES)})
    ),
    CONSTRAINT ck_map_edge_type CHECK (edge_type IN ({_quoted(EDGE_TYPES)})),
    CONSTRAINT ck_map_edge_direction CHECK (
        direction IN ('DIRECTED', 'BIDIRECTIONAL')
    ),
    CONSTRAINT ck_map_edge_not_self CHECK (
        NOT (source_ref_type = target_ref_type AND source_ref_id = target_ref_id)
    ),
    -- An edge NUR proposed has to say what it read to propose it. An edge the
    -- owner drew needs no source, because the owner is the source.
    CONSTRAINT ck_map_edge_inference_needs_source CHECK (
        user_confirmed OR inference_source IS NOT NULL
    ),
    CONSTRAINT ck_map_edge_confidence_range CHECK (
        confidence IS NULL OR (confidence > 0 AND confidence <= 1)
    ),
    CONSTRAINT uq_map_edge_unique UNIQUE (
        owner_user_id, source_ref_type, source_ref_id,
        target_ref_type, target_ref_id, edge_type
    )
);
CREATE INDEX ix_map_edges_source ON map_edges (owner_user_id, source_ref_type, source_ref_id);
CREATE INDEX ix_map_edges_target ON map_edges (owner_user_id, target_ref_type, target_ref_id);

CREATE TABLE map_suggestions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    suggestion_type varchar(32) NOT NULL,
    source_refs jsonb NOT NULL DEFAULT '[]'::jsonb,
    proposed_payload jsonb NOT NULL,
    explanation text NOT NULL,
    may_be_wrong_about text NOT NULL,
    confidence numeric(4, 3),
    status varchar(16) NOT NULL DEFAULT 'PENDING',
    suppressed_kind boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT now(),
    reviewed_at timestamptz,
    CONSTRAINT ck_map_suggestion_type CHECK (
        suggestion_type IN ({_quoted(SUGGESTION_TYPES)})
    ),
    CONSTRAINT ck_map_suggestion_status CHECK (
        status IN ('PENDING', 'ACCEPTED', 'REJECTED', 'SUPERSEDED')
    ),
    -- Every candidate node carries a "Why?" action, so a suggestion that cannot
    -- explain itself must not be storable.
    CONSTRAINT ck_map_suggestion_has_explanation CHECK (btrim(explanation) <> ''),
    CONSTRAINT ck_map_suggestion_states_doubt CHECK (btrim(may_be_wrong_about) <> ''),
    -- A reviewed suggestion has to record when, so accept/reject is auditable.
    CONSTRAINT ck_map_suggestion_reviewed_at CHECK (
        status IN ('PENDING', 'SUPERSEDED') OR reviewed_at IS NOT NULL
    ),
    CONSTRAINT ck_map_suggestion_confidence_range CHECK (
        confidence IS NULL OR (confidence > 0 AND confidence < 1)
    ),
    -- Inference has to rest on something the owner can go and look at.
    CONSTRAINT ck_map_suggestion_has_source CHECK (
        jsonb_array_length(source_refs) > 0
    )
);
CREATE INDEX ix_map_suggestions_pending ON map_suggestions (owner_user_id, created_at DESC)
    WHERE status = 'PENDING';

CREATE TABLE map_annotations (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    entity_ref_type varchar(32) NOT NULL,
    entity_ref_id varchar(64) NOT NULL,
    body text NOT NULL,
    visibility_scope varchar(24) NOT NULL DEFAULT 'PRIVATE',
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_map_annotation_ref_type CHECK (
        entity_ref_type IN ({_quoted(REF_TYPES)})
    ),
    CONSTRAINT ck_map_annotation_scope CHECK (
        visibility_scope IN ('PRIVATE', 'SHARED_ORBIT', 'CAPSULE_ELIGIBLE')
    ),
    CONSTRAINT ck_map_annotation_body_not_blank CHECK (btrim(body) <> '')
);
CREATE INDEX ix_map_annotations_entity
    ON map_annotations (owner_user_id, entity_ref_type, entity_ref_id);

CREATE TABLE map_decision_options (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    decision_id uuid NOT NULL REFERENCES decisions(id) ON DELETE CASCADE,
    label varchar(300) NOT NULL,
    summary text,
    benefits jsonb NOT NULL DEFAULT '[]'::jsonb,
    costs jsonb NOT NULL DEFAULT '[]'::jsonb,
    risks jsonb NOT NULL DEFAULT '[]'::jsonb,
    dependencies jsonb NOT NULL DEFAULT '[]'::jsonb,
    evidence jsonb NOT NULL DEFAULT '[]'::jsonb,
    predicted_consequences text,
    reversibility varchar(24) NOT NULL DEFAULT 'EASY',
    time_horizon varchar(48),
    effort varchar(24),
    position integer NOT NULL DEFAULT 0,
    chosen_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_map_option_reversibility CHECK (
        reversibility IN ('EASY', 'COSTLY', 'MOSTLY_IRREVERSIBLE')
    ),
    CONSTRAINT ck_map_option_label_not_blank CHECK (btrim(label) <> '')
);
CREATE INDEX ix_map_decision_options_decision
    ON map_decision_options (decision_id, position);
-- One chosen option per decision. A decision with two winners is not resolved.
CREATE UNIQUE INDEX uq_map_decision_one_choice
    ON map_decision_options (decision_id) WHERE chosen_at IS NOT NULL;

CREATE TABLE map_blockers (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title varchar(500) NOT NULL,
    description text,
    system_slug varchar(48),
    category varchar(32) NOT NULL DEFAULT 'PRACTICAL',
    basis varchar(20) NOT NULL,
    evidence jsonb NOT NULL DEFAULT '[]'::jsonb,
    affects jsonb NOT NULL DEFAULT '[]'::jsonb,
    possible_responses jsonb NOT NULL DEFAULT '[]'::jsonb,
    status varchar(16) NOT NULL DEFAULT 'PROPOSED',
    confirmed_by_owner boolean NOT NULL DEFAULT false,
    resolved_at timestamptz,
    resolution_note text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_map_blocker_basis CHECK (
        basis IN ('USER_STATED', 'OBSERVED', 'NUR_INFERRED')
    ),
    CONSTRAINT ck_map_blocker_category CHECK (
        category IN ('PRACTICAL', 'TECHNICAL', 'FINANCIAL', 'TIME',
                     'KNOWLEDGE', 'EMOTIONAL', 'PSYCHOLOGICAL', 'RELATIONAL',
                     'HEALTH', 'EXTERNAL')
    ),
    CONSTRAINT ck_map_blocker_status CHECK (
        status IN ('PROPOSED', 'OPEN', 'RESOLVED', 'CHALLENGED', 'DISMISSED')
    ),
    CONSTRAINT ck_map_blocker_title_not_blank CHECK (btrim(title) <> ''),
    -- Same rule as an inferred Orbit signal: an inference must point at what it
    -- was inferred from, or it is an assertion wearing evidence's clothes.
    CONSTRAINT ck_map_blocker_inference_needs_evidence CHECK (
        basis <> 'NUR_INFERRED' OR jsonb_array_length(evidence) > 0
    ),
    -- §20: NUR must not label an emotional, psychological or relational
    -- condition as fact. Such a blocker stays PROPOSED until the owner confirms
    -- it, so the assertion is unreachable rather than merely discouraged.
    CONSTRAINT ck_map_blocker_sensitive_needs_owner CHECK (
        basis <> 'NUR_INFERRED'
        OR category NOT IN ('EMOTIONAL', 'PSYCHOLOGICAL', 'RELATIONAL')
        OR confirmed_by_owner
        OR status = 'PROPOSED'
    ),
    CONSTRAINT ck_map_blocker_resolved_at CHECK (
        status <> 'RESOLVED' OR resolved_at IS NOT NULL
    )
);
CREATE INDEX ix_map_blockers_owner_status
    ON map_blockers (owner_user_id, status, updated_at DESC);
"""


def _statements(ddl: str) -> list[str]:
    """Split a DDL document into statements, ignoring `;` inside `--` comments.

    Same splitter as 0050, and for the same reason: asyncpg prepares every
    statement and a prepared statement holds exactly one command, and a plain
    `split(";")` cut a CREATE TABLE in half on a semicolon inside a comment.
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
    for name, column_type in PREDICTION_COLUMNS:
        op.execute(
            f"ALTER TABLE predictions ADD COLUMN IF NOT EXISTS {name} {column_type}"
        )
    op.execute(
        "ALTER TABLE predictions ADD CONSTRAINT ck_predictions_never_certain CHECK ("
        "confidence IS NULL OR (confidence > 0 AND confidence < 1))"
    )
    op.execute(
        "ALTER TABLE predictions ADD CONSTRAINT ck_predictions_resolution CHECK ("
        "resolution IS NULL OR resolution IN "
        "('CONFIRMED', 'PARTIALLY_CONFIRMED', 'CONTRADICTED'))"
    )
    op.execute(
        "ALTER TABLE predictions ADD CONSTRAINT ck_predictions_resolution_resolved_at "
        "CHECK (resolution IS NULL OR resolved_at IS NOT NULL)"
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
        "ck_predictions_resolution_resolved_at",
        "ck_predictions_resolution",
        "ck_predictions_never_certain",
    ):
        op.execute(f"ALTER TABLE predictions DROP CONSTRAINT IF EXISTS {constraint}")
    for name, _type in reversed(PREDICTION_COLUMNS):
        op.execute(f"ALTER TABLE predictions DROP COLUMN IF EXISTS {name}")
