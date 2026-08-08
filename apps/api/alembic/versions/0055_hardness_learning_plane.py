"""Hardness / Self-Directed Learning Plane V1 — learning signals, candidates, curriculum, experiments, and promotion proposals with forced RLS.

Revision ID: 0055_hardness_learning_plane
Revises: 0054_why_changed_ledger
"""
from __future__ import annotations

from alembic import op

revision = "0055_hardness_learning_plane"
down_revision = "0054_why_changed_ledger"
branch_labels = None
depends_on = None

APP_ROLE = "nur_app"
OWNER_UUID = "NULLIF(current_setting('app.current_user_id', true), '')::uuid"
HAS_USER = (
    "current_setting('app.current_user_id', true) IS NOT NULL "
    "AND current_setting('app.current_user_id', true) <> ''"
)

NEW_TABLES = [
    "learning_signals",
    "learning_candidates",
    "curriculum_snapshots",
    "training_experiments",
    "learning_promotion_proposals",
]

DDL = """
ALTER TABLE user_corrections ADD CONSTRAINT uq_user_corrections_owner_id UNIQUE (owner_user_id, id);

CREATE TABLE learning_signals (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    orbit_id uuid REFERENCES orbits(id) ON DELETE SET NULL,
    source_event_id uuid REFERENCES cognitive_events(id) ON DELETE SET NULL,
    source_correction_id uuid,
    idempotency_key varchar(128),
    signal_kind varchar(48) NOT NULL,
    capability_id varchar(64),
    task_class varchar(64) NOT NULL,
    summary text NOT NULL,
    structured_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT fk_learning_signals_user_corrections_owner
        FOREIGN KEY (owner_user_id, source_correction_id)
        REFERENCES user_corrections(owner_user_id, id)
        ON DELETE SET NULL,
    CONSTRAINT ck_learning_signals_kind CHECK (
        signal_kind IN (
            'OWNER_CORRECTION', 'VERIFIED_FAILURE', 'TOOL_FAILURE',
            'OUTCOME_MISS', 'CRITIC_DISAGREEMENT', 'CALIBRATION_ERROR',
            'CONTRADICTION', 'CAPABILITY_GAP', 'SUCCESSFUL_NOVEL_SOLUTION'
        )
    )
);
CREATE INDEX ix_learning_signals_owner_kind ON learning_signals (owner_user_id, signal_kind);
CREATE INDEX ix_learning_signals_owner_created ON learning_signals (owner_user_id, created_at DESC);
CREATE UNIQUE INDEX uq_learning_signals_owner_correction ON learning_signals (owner_user_id, source_correction_id) WHERE source_correction_id IS NOT NULL;
CREATE UNIQUE INDEX uq_learning_signals_owner_idempotency ON learning_signals (owner_user_id, idempotency_key) WHERE idempotency_key IS NOT NULL;

CREATE TABLE learning_candidates (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    fingerprint varchar(64) NOT NULL,
    signal_kind varchar(48) NOT NULL,
    capability_id varchar(64),
    task_class varchar(64) NOT NULL,
    failure_signature text,
    desired_behavior text,
    novelty_score integer NOT NULL DEFAULT 0,
    recurrence_score integer NOT NULL DEFAULT 0,
    impact_score integer NOT NULL DEFAULT 0,
    uncertainty_score integer NOT NULL DEFAULT 0,
    counterexample_value integer NOT NULL DEFAULT 0,
    transferability_score integer NOT NULL DEFAULT 0,
    recency_score integer NOT NULL DEFAULT 0,
    poisoning_risk integer NOT NULL DEFAULT 0,
    privacy_risk integer NOT NULL DEFAULT 0,
    contamination_risk integer NOT NULL DEFAULT 0,
    learning_scope varchar(32) NOT NULL DEFAULT 'OWNER_LOCAL',
    status varchar(24) NOT NULL DEFAULT 'CANDIDATE',
    risk_status varchar(24) NOT NULL DEFAULT 'UNASSESSED',
    selection_score integer,
    learning_value integer,
    risk_penalty integer,
    redundancy_penalty integer,
    selection_policy_version varchar(32),
    selection_rationale text,
    reason_codes jsonb NOT NULL DEFAULT '[]'::jsonb,
    source_refs jsonb NOT NULL DEFAULT '[]'::jsonb,
    recurrence_count integer NOT NULL DEFAULT 1,
    last_seen_at timestamptz NOT NULL DEFAULT now(),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_learning_candidates_owner_fingerprint UNIQUE (owner_user_id, fingerprint),
    CONSTRAINT ck_learning_candidates_status CHECK (
        status IN ('CANDIDATE', 'SELECTED', 'REJECTED', 'DEFERRED')
    ),
    CONSTRAINT ck_learning_candidates_risk_status CHECK (
        risk_status IN ('UNASSESSED', 'ASSESSED')
    ),
    CONSTRAINT ck_learning_candidates_scope CHECK (
        learning_scope IN ('OWNER_LOCAL', 'PRIVATE_MODEL', 'GLOBAL_PRODUCT')
    ),
    CONSTRAINT ck_learning_candidates_novelty CHECK (novelty_score BETWEEN 0 AND 10000),
    CONSTRAINT ck_learning_candidates_recurrence CHECK (recurrence_score BETWEEN 0 AND 10000),
    CONSTRAINT ck_learning_candidates_impact CHECK (impact_score BETWEEN 0 AND 10000),
    CONSTRAINT ck_learning_candidates_uncertainty CHECK (uncertainty_score BETWEEN 0 AND 10000),
    CONSTRAINT ck_learning_candidates_counterexample CHECK (counterexample_value BETWEEN 0 AND 10000),
    CONSTRAINT ck_learning_candidates_transferability CHECK (transferability_score BETWEEN 0 AND 10000),
    CONSTRAINT ck_learning_candidates_recency CHECK (recency_score BETWEEN 0 AND 10000),
    CONSTRAINT ck_learning_candidates_poisoning CHECK (poisoning_risk BETWEEN 0 AND 10000),
    CONSTRAINT ck_learning_candidates_privacy CHECK (privacy_risk BETWEEN 0 AND 10000),
    CONSTRAINT ck_learning_candidates_contamination CHECK (contamination_risk BETWEEN 0 AND 10000)
);
CREATE INDEX ix_learning_candidates_owner_status ON learning_candidates (owner_user_id, status);
CREATE INDEX ix_learning_candidates_owner_updated ON learning_candidates (owner_user_id, updated_at DESC);

CREATE TABLE curriculum_snapshots (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    selector_policy_version varchar(32) NOT NULL,
    target_capabilities jsonb NOT NULL DEFAULT '[]'::jsonb,
    intervention varchar(32) NOT NULL,
    dataset_hash varchar(64) NOT NULL,
    dataset_manifest jsonb NOT NULL DEFAULT '{}'::jsonb,
    ordered_candidate_ids jsonb NOT NULL DEFAULT '[]'::jsonb,
    train_ids jsonb NOT NULL DEFAULT '[]'::jsonb,
    validation_ids jsonb NOT NULL DEFAULT '[]'::jsonb,
    heldout_ids jsonb NOT NULL DEFAULT '[]'::jsonb,
    privacy_manifest_hash varchar(64) NOT NULL,
    provenance_manifest_hash varchar(64) NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_curriculum_snapshots_owner_id UNIQUE (owner_user_id, id),
    CONSTRAINT ck_curriculum_intervention CHECK (
        intervention IN (
            'NO_CHANGE', 'MEMORY_UPDATE', 'RETRIEVAL_POLICY', 'ROUTER_POLICY',
            'CONTEXT_RECIPE', 'PROMPT_EXPERIMENT', 'SYNTHETIC_DATA', 'SFT',
            'PREFERENCE_TRAINING', 'RL', 'CODE_CHANGE_PROPOSAL'
        )
    )
);
CREATE INDEX ix_curriculum_snapshots_owner ON curriculum_snapshots (owner_user_id, created_at DESC);
CREATE INDEX ix_curriculum_snapshots_hash ON curriculum_snapshots (dataset_hash);

CREATE TABLE training_experiments (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    base_checkpoint_id varchar(64) NOT NULL,
    curriculum_id uuid NOT NULL,
    curriculum_hash varchar(64) NOT NULL,
    intervention varchar(32) NOT NULL,
    target_capabilities jsonb NOT NULL DEFAULT '[]'::jsonb,
    hypothesis text NOT NULL,
    success_metrics jsonb NOT NULL DEFAULT '{}'::jsonb,
    critical_regression_gates jsonb NOT NULL DEFAULT '[]'::jsonb,
    max_cost_cents integer NOT NULL DEFAULT 0,
    trainer_type varchar(32) NOT NULL DEFAULT 'DRY_RUN',
    status varchar(24) NOT NULL DEFAULT 'CREATED',
    candidate_artifact_hash varchar(64),
    candidate_metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_training_experiments_owner_id UNIQUE (owner_user_id, id),
    CONSTRAINT fk_training_experiments_curriculum_owner FOREIGN KEY (owner_user_id, curriculum_id) REFERENCES curriculum_snapshots(owner_user_id, id) ON DELETE CASCADE,
    CONSTRAINT ck_training_experiments_status CHECK (
        status IN ('CREATED', 'TRAINING', 'COMPLETED', 'FAILED', 'ABORTED')
    ),
    CONSTRAINT ck_training_experiments_trainer CHECK (
        trainer_type IN ('DRY_RUN')
    )
);
CREATE INDEX ix_training_experiments_owner ON training_experiments (owner_user_id, status, created_at DESC);

CREATE TABLE learning_promotion_proposals (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    experiment_id uuid NOT NULL,
    candidate_checkpoint_id varchar(64) NOT NULL,
    base_checkpoint_id varchar(64) NOT NULL,
    target_metric_delta double precision NOT NULL,
    general_regression_delta double precision NOT NULL,
    critical_gates_passed boolean NOT NULL,
    evaluation_summary jsonb NOT NULL DEFAULT '{}'::jsonb,
    recommendation varchar(32) NOT NULL,
    uncertainty_score integer NOT NULL DEFAULT 0,
    rationale text NOT NULL,
    why_changed_ref varchar(128),
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT fk_promotion_proposals_experiment_owner FOREIGN KEY (owner_user_id, experiment_id) REFERENCES training_experiments(owner_user_id, id) ON DELETE CASCADE,
    CONSTRAINT ck_promotion_recommendation CHECK (
        recommendation IN ('PROMOTION_CANDIDATE', 'REJECTED', 'DRY_RUN_VALIDATED', 'INSUFFICIENT_EVIDENCE')
    ),
    CONSTRAINT ck_promotion_uncertainty CHECK (uncertainty_score BETWEEN 0 AND 10000)
);
CREATE INDEX ix_promotion_proposals_owner ON learning_promotion_proposals (owner_user_id, recommendation, created_at DESC);
"""


def _statements(ddl: str) -> list[str]:
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
    for statement in _statements(DDL):
        op.execute(statement)

    for table in NEW_TABLES:
        _owner_all(table)
        op.execute(f"REVOKE ALL ON {table} FROM PUBLIC")
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO {APP_ROLE}")


def downgrade() -> None:
    for table in reversed(NEW_TABLES):
        op.execute(f"DROP POLICY IF EXISTS p_{table}_owner_select ON {table}")
        op.execute(f"DROP POLICY IF EXISTS p_{table}_owner_insert ON {table}")
        op.execute(f"DROP POLICY IF EXISTS p_{table}_owner_update ON {table}")
        op.execute(f"DROP POLICY IF EXISTS p_{table}_owner_delete ON {table}")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
        op.execute(f"REVOKE ALL ON {table} FROM {APP_ROLE}")
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")

    op.execute("ALTER TABLE user_corrections DROP CONSTRAINT IF EXISTS uq_user_corrections_owner_id")

