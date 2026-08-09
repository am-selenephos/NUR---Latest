"""Agentic Insights projection, evidence lifecycle, and owner review plane.

Revision ID: 0058_agentic_insights_engine
Revises: 0057_agent_owner_lifecycle
"""

from alembic import op


revision = "0058_agentic_insights_engine"
down_revision = "0057_agent_owner_lifecycle"
branch_labels = None
depends_on = None

APP_ROLE = "nur_app"
OWNER_UUID = "NULLIF(current_setting('app.current_user_id', true), '')::uuid"
HAS_USER = (
    "current_setting('app.current_user_id', true) IS NOT NULL "
    "AND current_setting('app.current_user_id', true) <> ''"
)

NEW_TABLES = (
    "insight_patterns",
    "insight_evidence_relations",
    "insight_feedback",
    "insight_projection_checkpoints",
    "insight_projection_runs",
)


def _owner_policy(table: str, grants: str = "SELECT, INSERT, UPDATE") -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY {table}_owner_isolation ON {table} "
        f"USING ({HAS_USER} AND owner_user_id = {OWNER_UUID}) "
        f"WITH CHECK ({HAS_USER} AND owner_user_id = {OWNER_UUID})"
    )
    op.execute(f"GRANT {grants} ON {table} TO {APP_ROLE}")


def upgrade() -> None:
    op.execute("""
        ALTER TABLE omega_experiences
            ADD COLUMN source_domain varchar(48) NOT NULL DEFAULT 'UNKNOWN',
            ADD COLUMN features jsonb NOT NULL DEFAULT '{}'::jsonb,
            ADD COLUMN explicitness varchar(32) NOT NULL DEFAULT 'SYSTEM_OBSERVED',
            ADD COLUMN retention_policy varchar(32) NOT NULL DEFAULT 'SOURCE_BOUND',
            ADD COLUMN observed_at timestamptz NOT NULL DEFAULT now(),
            ADD COLUMN invalidated_at timestamptz,
            ADD COLUMN source_fingerprint varchar(64),
            ADD CONSTRAINT ck_omega_experience_explicitness CHECK (
                explicitness IN ('OWNER_EXPLICIT','SYSTEM_OBSERVED','MODEL_INFERRED')
            ),
            ADD CONSTRAINT ck_omega_experience_retention CHECK (
                retention_policy IN ('SOURCE_BOUND','OWNER_LIFECYCLE','EPHEMERAL')
            )
    """)
    op.execute("""
        UPDATE omega_experiences SET
            source_domain = CASE
                WHEN event_kind = 'JOURNAL_ENTRY' THEN 'JOURNAL'
                WHEN event_kind IN ('PLAN_CREATED','PLAN_STEP') THEN 'PLAN'
                WHEN event_kind = 'OUTCOME_REPORTED' THEN 'OUTCOME'
                WHEN event_kind = 'TALK_TURN' THEN 'TALK'
                WHEN event_kind = 'USER_CORRECTION' THEN 'CORRECTION'
                ELSE 'SYSTEM'
            END,
            explicitness = CASE
                WHEN provenance_label IN ('OWNER_WRITTEN','USER_CORRECTION')
                    THEN 'OWNER_EXPLICIT'
                WHEN provenance_label = 'MODEL_GENERATED' THEN 'MODEL_INFERRED'
                ELSE 'SYSTEM_OBSERVED'
            END,
            observed_at = created_at
    """)
    op.execute("""
        CREATE INDEX ix_omega_experiences_owner_domain_time
            ON omega_experiences(owner_user_id, source_domain, observed_at DESC)
            WHERE invalidated_at IS NULL
    """)
    op.execute("""
        CREATE UNIQUE INDEX uq_omega_experience_owner_source
            ON omega_experiences(owner_user_id, source_kind, source_id)
            WHERE source_id IS NOT NULL
    """)

    op.execute("""
        CREATE TABLE insight_patterns (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            owner_user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            fingerprint varchar(64) NOT NULL,
            pattern_type varchar(48) NOT NULL,
            time_scale varchar(24) NOT NULL,
            source_domains jsonb NOT NULL DEFAULT '[]'::jsonb,
            feature_summary jsonb NOT NULL DEFAULT '{}'::jsonb,
            support_count integer NOT NULL DEFAULT 0 CHECK (support_count >= 0),
            counter_count integer NOT NULL DEFAULT 0 CHECK (counter_count >= 0),
            source_diversity integer NOT NULL DEFAULT 0 CHECK (source_diversity >= 0),
            first_observed_at timestamptz,
            last_observed_at timestamptz,
            status varchar(24) NOT NULL DEFAULT 'ACTIVE' CHECK (
                status IN ('ACTIVE','SUPERSEDED','RETRACTED')
            ),
            version integer NOT NULL DEFAULT 1 CHECK (version >= 1),
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_insight_patterns_owner_fingerprint UNIQUE(owner_user_id, fingerprint)
        )
    """)
    op.execute("""
        CREATE INDEX ix_insight_patterns_owner_status
            ON insight_patterns(owner_user_id, status, updated_at DESC)
    """)

    op.execute("""
        ALTER TABLE insights
            ADD COLUMN pattern_id uuid REFERENCES insight_patterns(id) ON DELETE SET NULL,
            ADD COLUMN parent_insight_id uuid REFERENCES insights(id) ON DELETE SET NULL,
            ADD COLUMN lifecycle_status varchar(32) NOT NULL DEFAULT 'CANDIDATE',
            ADD COLUMN epistemic_state varchar(32) NOT NULL DEFAULT 'INFERRED',
            ADD COLUMN insight_version integer NOT NULL DEFAULT 1,
            ADD COLUMN pattern_fingerprint varchar(64),
            ADD COLUMN evidence_digest varchar(64),
            ADD COLUMN time_scale varchar(24) NOT NULL DEFAULT 'FAST',
            ADD COLUMN time_window_start timestamptz,
            ADD COLUMN time_window_end timestamptz,
            ADD COLUMN source_domains jsonb NOT NULL DEFAULT '[]'::jsonb,
            ADD COLUMN source_diversity integer NOT NULL DEFAULT 0,
            ADD COLUMN alternative_explanations jsonb NOT NULL DEFAULT '[]'::jsonb,
            ADD COLUMN assumptions jsonb NOT NULL DEFAULT '[]'::jsonb,
            ADD COLUMN contradictions jsonb NOT NULL DEFAULT '[]'::jsonb,
            ADD COLUMN confidence_basis jsonb NOT NULL DEFAULT '{}'::jsonb,
            ADD COLUMN quality_dimensions jsonb NOT NULL DEFAULT '{}'::jsonb,
            ADD COLUMN quality_policy_version varchar(48) NOT NULL DEFAULT 'agentic-insights-quality-v1',
            ADD COLUMN calibration_target varchar(48),
            ADD COLUMN surfaced_at timestamptz,
            ADD COLUMN reviewed_at timestamptz,
            ADD COLUMN cooldown_until timestamptz,
            ADD COLUMN source_invalidated_at timestamptz,
            ADD CONSTRAINT ck_insights_lifecycle CHECK (
                lifecycle_status IN (
                    'CANDIDATE','REVIEW_REQUIRED','SURFACED','OWNER_CONFIRMED',
                    'OWNER_CORRECTED','OWNER_REJECTED','RESOLVED','SUPERSEDED','RETRACTED'
                )
            ),
            ADD CONSTRAINT ck_insights_epistemic_state CHECK (
                epistemic_state IN (
                    'OBSERVED','INFERRED','HYPOTHESIS','UNCERTAIN',
                    'NEEDS_OWNER_CONFIRMATION'
                )
            ),
            ADD CONSTRAINT ck_insights_version CHECK (insight_version >= 1),
            ADD CONSTRAINT ck_insights_source_diversity CHECK (source_diversity >= 0),
            ADD CONSTRAINT ck_insights_time_scale CHECK (
                time_scale IN ('FAST','DAILY_WEEKLY','LONGITUDINAL')
            )
    """)
    op.execute("""
        UPDATE insights SET
            lifecycle_status = CASE status
                WHEN 'ACCEPTED' THEN 'OWNER_CONFIRMED'
                WHEN 'REJECTED' THEN 'OWNER_REJECTED'
                WHEN 'CORRECTED' THEN 'OWNER_CORRECTED'
                WHEN 'ARCHIVED' THEN 'RESOLVED'
                ELSE 'CANDIDATE'
            END,
            source_diversity = jsonb_array_length(source_event_ids)
                + jsonb_array_length(source_memory_ids)
                + jsonb_array_length(source_research_ids)
    """)
    op.execute("""
        CREATE INDEX ix_insights_owner_lifecycle
            ON insights(owner_user_id, lifecycle_status, updated_at DESC)
    """)
    op.execute("""
        CREATE INDEX ix_insights_owner_pattern
            ON insights(owner_user_id, pattern_fingerprint, insight_version DESC)
            WHERE pattern_fingerprint IS NOT NULL
    """)

    op.execute("""
        CREATE TABLE insight_evidence_relations (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            owner_user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            insight_id uuid NOT NULL REFERENCES insights(id) ON DELETE CASCADE,
            observation_id uuid REFERENCES omega_experiences(id) ON DELETE SET NULL,
            source_event_id uuid REFERENCES cognitive_events(id) ON DELETE SET NULL,
            source_domain_event_id uuid REFERENCES domain_events(id) ON DELETE SET NULL,
            source_insight_id uuid REFERENCES insights(id) ON DELETE SET NULL,
            source_feedback_id uuid,
            source_kind varchar(48) NOT NULL,
            source_id uuid NOT NULL,
            source_domain varchar(48) NOT NULL,
            relation varchar(24) NOT NULL CHECK (
                relation IN ('SUPPORTS','CONTRADICTS','QUALIFIES','DERIVED_FROM')
            ),
            provenance_label varchar(64) NOT NULL,
            explicitness varchar(32) NOT NULL CHECK (
                explicitness IN ('OWNER_EXPLICIT','SYSTEM_OBSERVED','MODEL_INFERRED')
            ),
            confidence double precision NOT NULL DEFAULT 0.5 CHECK (
                confidence >= 0 AND confidence <= 1
            ),
            source_fingerprint varchar(64),
            evidence_summary varchar(1000),
            source_occurred_at timestamptz,
            insight_version integer NOT NULL DEFAULT 1 CHECK (insight_version >= 1),
            invalidated_at timestamptz,
            invalidation_reason varchar(160),
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_insight_evidence_relation UNIQUE(
                owner_user_id, insight_id, source_kind, source_id, relation, insight_version
            )
        )
    """)
    op.execute("""
        CREATE INDEX ix_insight_evidence_owner_insight
            ON insight_evidence_relations(owner_user_id, insight_id, relation, created_at)
    """)
    op.execute("""
        CREATE INDEX ix_insight_evidence_source
            ON insight_evidence_relations(owner_user_id, source_kind, source_id)
            WHERE invalidated_at IS NULL
    """)

    op.execute("""
        CREATE TABLE insight_feedback (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            owner_user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            insight_id uuid NOT NULL REFERENCES insights(id) ON DELETE CASCADE,
            action varchar(32) NOT NULL CHECK (
                action IN (
                    'THIS_FITS','NOT_RIGHT','CORRECT_NUR','SHOW_EVIDENCE',
                    'EXPLORE_DEEPER','MAKE_A_PLAN','ADD_TO_TIMELINE',
                    'OPEN_IN_MAP','OPEN_ORBIT','WHY_DID_THIS_CHANGE'
                )
            ),
            correction_text text,
            prior_lifecycle_status varchar(32) NOT NULL,
            next_lifecycle_status varchar(32) NOT NULL,
            evidence_digest varchar(64),
            insight_version integer NOT NULL CHECK (insight_version >= 1),
            source_correction_id uuid REFERENCES user_corrections(id) ON DELETE SET NULL,
            created_at timestamptz NOT NULL DEFAULT now()
        )
    """)
    op.execute("""
        CREATE INDEX ix_insight_feedback_owner_created
            ON insight_feedback(owner_user_id, created_at DESC)
    """)
    op.execute("""
        CREATE INDEX ix_insight_feedback_owner_insight
            ON insight_feedback(owner_user_id, insight_id, created_at DESC)
    """)

    op.execute("""
        CREATE TABLE insight_projection_checkpoints (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            owner_user_id uuid NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
            last_cognitive_event_at timestamptz,
            last_cognitive_event_id uuid,
            last_domain_event_at timestamptz,
            last_domain_event_id uuid,
            pending_event_count integer NOT NULL DEFAULT 0 CHECK (pending_event_count >= 0),
            pending_since timestamptz,
            next_eligible_at timestamptz,
            last_run_at timestamptz,
            last_run_status varchar(24),
            claim_token uuid,
            claimed_by varchar(160),
            lease_expires_at timestamptz,
            attempt_count integer NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
            max_attempts integer NOT NULL DEFAULT 5 CHECK (max_attempts BETWEEN 1 AND 20),
            last_error_class varchar(120),
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT ck_insight_checkpoint_claim_shape CHECK (
                (claim_token IS NULL AND claimed_by IS NULL AND lease_expires_at IS NULL)
                OR
                (claim_token IS NOT NULL AND claimed_by IS NOT NULL AND lease_expires_at IS NOT NULL)
            )
        )
    """)
    op.execute("""
        CREATE INDEX ix_insight_checkpoint_due
            ON insight_projection_checkpoints(next_eligible_at, pending_since)
            WHERE pending_event_count > 0
    """)

    op.execute("""
        CREATE TABLE insight_projection_runs (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            owner_user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            idempotency_key varchar(160) NOT NULL,
            run_kind varchar(24) NOT NULL CHECK (
                run_kind IN ('EVENT','MANUAL','DAILY','WEEKLY')
            ),
            status varchar(24) NOT NULL DEFAULT 'STARTED' CHECK (
                status IN ('STARTED','COMPLETED','FAILED','SUPPRESSED')
            ),
            max_observations integer NOT NULL CHECK (max_observations > 0),
            processed_observations integer NOT NULL DEFAULT 0 CHECK (processed_observations >= 0),
            invalidated_relations integer NOT NULL DEFAULT 0 CHECK (invalidated_relations >= 0),
            generated_candidates integer NOT NULL DEFAULT 0 CHECK (generated_candidates >= 0),
            surfaced_insight_id uuid REFERENCES insights(id) ON DELETE SET NULL,
            self_insight_id uuid REFERENCES insights(id) ON DELETE SET NULL,
            suppressed_insight_id uuid REFERENCES insights(id) ON DELETE SET NULL,
            suppressed_reason varchar(80),
            quality_policy_version varchar(48) NOT NULL,
            input_counts jsonb NOT NULL DEFAULT '{}'::jsonb,
            error_class varchar(120),
            created_at timestamptz NOT NULL DEFAULT now(),
            completed_at timestamptz
        )
    """)
    op.execute("""
        CREATE INDEX ix_insight_runs_owner_created
            ON insight_projection_runs(owner_user_id, created_at DESC)
    """)
    op.execute("""
        CREATE UNIQUE INDEX uq_insight_projection_run_idempotency
            ON insight_projection_runs(owner_user_id, idempotency_key)
    """)
    op.execute("""
        CREATE UNIQUE INDEX uq_insight_projection_active_run
            ON insight_projection_runs(owner_user_id)
            WHERE status = 'STARTED'
    """)

    # Every owner-scoped child is bound to a parent carrying the same owner.
    # RLS limits visible rows; these composite FKs also reject forged references.
    for statement in (
        "ALTER TABLE cognitive_events ADD CONSTRAINT uq_cognitive_event_id_owner "
        "UNIQUE (id, owner_user_id)",
        "ALTER TABLE domain_events ADD CONSTRAINT uq_domain_event_id_owner "
        "UNIQUE (id, owner_user_id)",
        "ALTER TABLE omega_experiences ADD CONSTRAINT uq_omega_experience_id_owner "
        "UNIQUE (id, owner_user_id)",
        "ALTER TABLE insights ADD CONSTRAINT uq_insight_id_owner "
        "UNIQUE (id, owner_user_id)",
        "ALTER TABLE insight_patterns ADD CONSTRAINT uq_insight_pattern_id_owner "
        "UNIQUE (id, owner_user_id)",
        "ALTER TABLE insights ADD CONSTRAINT fk_insight_pattern_owner "
        "FOREIGN KEY (pattern_id, owner_user_id) "
        "REFERENCES insight_patterns(id, owner_user_id) ON DELETE SET NULL (pattern_id)",
        "ALTER TABLE insights ADD CONSTRAINT fk_insight_parent_owner "
        "FOREIGN KEY (parent_insight_id, owner_user_id) "
        "REFERENCES insights(id, owner_user_id) ON DELETE SET NULL (parent_insight_id)",
        "ALTER TABLE insight_evidence_relations ADD CONSTRAINT fk_insight_evidence_insight_owner "
        "FOREIGN KEY (insight_id, owner_user_id) "
        "REFERENCES insights(id, owner_user_id) ON DELETE CASCADE",
        "ALTER TABLE insight_evidence_relations ADD CONSTRAINT fk_insight_evidence_observation_owner "
        "FOREIGN KEY (observation_id, owner_user_id) "
        "REFERENCES omega_experiences(id, owner_user_id) ON DELETE SET NULL (observation_id)",
        "ALTER TABLE insight_evidence_relations ADD CONSTRAINT fk_insight_evidence_event_owner "
        "FOREIGN KEY (source_event_id, owner_user_id) "
        "REFERENCES cognitive_events(id, owner_user_id) ON DELETE SET NULL (source_event_id)",
        "ALTER TABLE insight_evidence_relations ADD CONSTRAINT fk_insight_evidence_domain_event_owner "
        "FOREIGN KEY (source_domain_event_id, owner_user_id) "
        "REFERENCES domain_events(id, owner_user_id) ON DELETE SET NULL (source_domain_event_id)",
        "ALTER TABLE insight_feedback ADD CONSTRAINT uq_insight_feedback_id_owner "
        "UNIQUE (id, owner_user_id)",
        "ALTER TABLE insight_evidence_relations ADD CONSTRAINT fk_insight_evidence_source_insight_owner "
        "FOREIGN KEY (source_insight_id, owner_user_id) "
        "REFERENCES insights(id, owner_user_id) ON DELETE SET NULL (source_insight_id)",
        "ALTER TABLE insight_evidence_relations ADD CONSTRAINT fk_insight_evidence_source_feedback_owner "
        "FOREIGN KEY (source_feedback_id, owner_user_id) "
        "REFERENCES insight_feedback(id, owner_user_id) ON DELETE SET NULL (source_feedback_id)",
        "ALTER TABLE insight_feedback ADD CONSTRAINT fk_insight_feedback_insight_owner "
        "FOREIGN KEY (insight_id, owner_user_id) "
        "REFERENCES insights(id, owner_user_id) ON DELETE CASCADE",
        "ALTER TABLE insight_feedback ADD CONSTRAINT fk_insight_feedback_correction_owner "
        "FOREIGN KEY (owner_user_id, source_correction_id) "
        "REFERENCES user_corrections(owner_user_id, id) "
        "ON DELETE SET NULL (source_correction_id)",
        "ALTER TABLE insight_projection_runs ADD CONSTRAINT fk_insight_run_surfaced_owner "
        "FOREIGN KEY (surfaced_insight_id, owner_user_id) "
        "REFERENCES insights(id, owner_user_id) ON DELETE SET NULL (surfaced_insight_id)",
        "ALTER TABLE insight_projection_runs ADD CONSTRAINT fk_insight_run_self_owner "
        "FOREIGN KEY (self_insight_id, owner_user_id) "
        "REFERENCES insights(id, owner_user_id) ON DELETE SET NULL (self_insight_id)",
        "ALTER TABLE insight_projection_runs ADD CONSTRAINT fk_insight_run_suppressed_owner "
        "FOREIGN KEY (suppressed_insight_id, owner_user_id) "
        "REFERENCES insights(id, owner_user_id) ON DELETE SET NULL (suppressed_insight_id)",
    ):
        op.execute(statement)

    op.execute("""
        CREATE UNIQUE INDEX uq_insight_owner_pattern_evidence
            ON insights(owner_user_id, pattern_fingerprint, evidence_digest)
            WHERE pattern_fingerprint IS NOT NULL AND evidence_digest IS NOT NULL
    """)
    op.execute("""
        CREATE UNIQUE INDEX uq_insight_owner_pattern_version
            ON insights(owner_user_id, pattern_fingerprint, insight_version)
            WHERE pattern_fingerprint IS NOT NULL
    """)

    # Repair the preceding migration's cross-owner retry/purge hazard.
    op.execute(
        "ALTER TABLE agent_workflows DROP CONSTRAINT IF EXISTS "
        "agent_workflows_retry_of_workflow_id_fkey"
    )
    op.execute(
        "ALTER TABLE agent_workflows ADD CONSTRAINT fk_agent_workflow_retry_owner "
        "FOREIGN KEY (retry_of_workflow_id, owner_user_id) "
        "REFERENCES agent_workflows(id, owner_user_id) "
        "ON DELETE SET NULL (retry_of_workflow_id)"
    )

    for table in NEW_TABLES:
        grants = "SELECT, INSERT" if table == "insight_feedback" else "SELECT, INSERT, UPDATE"
        _owner_policy(table, grants)

    # Migration 0054 created the canonical ledger but omitted runtime grants;
    # the old service therefore wrote CognitiveEvent JSON instead of this table.
    op.execute(f"GRANT SELECT, INSERT ON why_changed_records TO {APP_ROLE}")

    op.execute("""
        CREATE OR REPLACE FUNCTION nur_validate_insight_evidence_source()
        RETURNS trigger
        LANGUAGE plpgsql
        SECURITY INVOKER
        SET search_path = public
        AS $$
        DECLARE source_ok boolean := false;
        BEGIN
            CASE NEW.source_kind
                WHEN 'COGNITIVE_EVENT' THEN
                    source_ok := NEW.source_event_id = NEW.source_id AND EXISTS (
                        SELECT 1 FROM cognitive_events
                        WHERE id = NEW.source_id AND owner_user_id = NEW.owner_user_id
                    );
                WHEN 'DOMAIN_EVENT' THEN
                    source_ok := NEW.source_domain_event_id = NEW.source_id AND EXISTS (
                        SELECT 1 FROM domain_events
                        WHERE id = NEW.source_id AND owner_user_id = NEW.owner_user_id
                    );
                WHEN 'INSIGHT' THEN
                    source_ok := NEW.source_insight_id = NEW.source_id AND EXISTS (
                        SELECT 1 FROM insights
                        WHERE id = NEW.source_id AND owner_user_id = NEW.owner_user_id
                    );
                WHEN 'INSIGHT_FEEDBACK' THEN
                    source_ok := NEW.source_feedback_id = NEW.source_id AND EXISTS (
                        SELECT 1 FROM insight_feedback
                        WHERE id = NEW.source_id AND owner_user_id = NEW.owner_user_id
                    );
                WHEN 'JOURNAL_ENTRY' THEN
                    source_ok := EXISTS (SELECT 1 FROM journal_entries WHERE id = NEW.source_id AND owner_user_id = NEW.owner_user_id);
                WHEN 'PLAN' THEN
                    source_ok := EXISTS (SELECT 1 FROM plans WHERE id = NEW.source_id AND owner_user_id = NEW.owner_user_id);
                WHEN 'PLAN_STEP' THEN
                    source_ok := EXISTS (SELECT 1 FROM plan_steps WHERE id = NEW.source_id AND owner_user_id = NEW.owner_user_id);
                WHEN 'OUTCOME' THEN
                    source_ok := EXISTS (SELECT 1 FROM outcomes WHERE id = NEW.source_id AND owner_user_id = NEW.owner_user_id);
                WHEN 'SYSTEM_ACTION' THEN
                    source_ok := EXISTS (SELECT 1 FROM system_actions WHERE id = NEW.source_id AND owner_user_id = NEW.owner_user_id);
                WHEN 'GOAL' THEN
                    source_ok := EXISTS (SELECT 1 FROM goals WHERE id = NEW.source_id AND owner_user_id = NEW.owner_user_id);
                WHEN 'AM_PROJECT' THEN
                    source_ok := EXISTS (SELECT 1 FROM am_projects WHERE id = NEW.source_id AND owner_user_id = NEW.owner_user_id);
                WHEN 'TIMELINE_EVENT' THEN
                    source_ok := EXISTS (SELECT 1 FROM timeline_events WHERE id = NEW.source_id AND owner_user_id = NEW.owner_user_id);
                WHEN 'OMEGA_CLAIM' THEN
                    source_ok := EXISTS (SELECT 1 FROM omega_claims WHERE id = NEW.source_id AND owner_user_id = NEW.owner_user_id);
                WHEN 'USER_CORRECTION' THEN
                    source_ok := EXISTS (SELECT 1 FROM user_corrections WHERE id = NEW.source_id AND owner_user_id = NEW.owner_user_id);
                WHEN 'RESEARCH_SOURCE_NOTE' THEN
                    source_ok := EXISTS (SELECT 1 FROM research_source_notes WHERE id = NEW.source_id AND owner_user_id = NEW.owner_user_id);
                WHEN 'ORBIT' THEN
                    source_ok := EXISTS (SELECT 1 FROM orbits WHERE id = NEW.source_id AND owner_user_id = NEW.owner_user_id);
                WHEN 'PERSON' THEN
                    source_ok := EXISTS (SELECT 1 FROM people WHERE id = NEW.source_id AND owner_user_id = NEW.owner_user_id);
                WHEN 'PREDICTION' THEN
                    source_ok := EXISTS (SELECT 1 FROM predictions WHERE id = NEW.source_id AND owner_user_id = NEW.owner_user_id);
                WHEN 'AGENT_WORKFLOW' THEN
                    source_ok := EXISTS (SELECT 1 FROM agent_workflows WHERE id = NEW.source_id AND owner_user_id = NEW.owner_user_id);
                ELSE
                    source_ok := false;
            END CASE;
            IF NOT source_ok THEN
                RAISE EXCEPTION 'invalid or cross-owner Insight evidence source'
                    USING ERRCODE = '23503';
            END IF;
            RETURN NEW;
        END;
        $$
    """)
    op.execute("""
        CREATE TRIGGER trg_insight_evidence_source_integrity
        BEFORE INSERT OR UPDATE OF owner_user_id, source_kind, source_id,
            source_event_id, source_domain_event_id, source_insight_id,
            source_feedback_id
        ON insight_evidence_relations
        FOR EACH ROW EXECUTE FUNCTION nur_validate_insight_evidence_source()
    """)

    op.execute("""
        CREATE OR REPLACE FUNCTION nur_mark_insight_projection_pending()
        RETURNS trigger
        LANGUAGE plpgsql
        SECURITY INVOKER
        SET search_path = public
        AS $$
        BEGIN
            INSERT INTO insight_projection_checkpoints(
                owner_user_id, pending_event_count, pending_since, next_eligible_at,
                created_at, updated_at
            ) VALUES (NEW.owner_user_id, 1, now(), now(), now(), now())
            ON CONFLICT (owner_user_id) DO UPDATE SET
                pending_event_count = LEAST(
                    insight_projection_checkpoints.pending_event_count + 1, 100000
                ),
                pending_since = COALESCE(
                    insight_projection_checkpoints.pending_since, EXCLUDED.pending_since
                ),
                next_eligible_at = LEAST(
                    COALESCE(insight_projection_checkpoints.next_eligible_at, EXCLUDED.next_eligible_at),
                    EXCLUDED.next_eligible_at
                ),
                attempt_count = 0,
                last_error_class = NULL,
                updated_at = now();
            RETURN NEW;
        END;
        $$
    """)
    op.execute("""
        CREATE TRIGGER trg_cognitive_event_insight_pending
        AFTER INSERT ON cognitive_events
        FOR EACH ROW
        WHEN (
            NEW.source_ref IS NULL OR (
                NEW.source_ref NOT LIKE 'insight:%'
                AND NEW.source_ref NOT LIKE 'why_changed:%'
            )
        )
        EXECUTE FUNCTION nur_mark_insight_projection_pending()
    """)
    op.execute("""
        CREATE TRIGGER trg_domain_event_insight_pending
        AFTER INSERT ON domain_events
        FOR EACH ROW
        WHEN (NEW.event_type NOT LIKE 'insight.%')
        EXECUTE FUNCTION nur_mark_insight_projection_pending()
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_domain_event_insight_pending ON domain_events")
    op.execute("DROP TRIGGER IF EXISTS trg_cognitive_event_insight_pending ON cognitive_events")
    op.execute("DROP FUNCTION IF EXISTS nur_mark_insight_projection_pending()")
    op.execute(
        "DROP TRIGGER IF EXISTS trg_insight_evidence_source_integrity "
        "ON insight_evidence_relations"
    )
    op.execute("DROP FUNCTION IF EXISTS nur_validate_insight_evidence_source()")
    op.execute("REVOKE SELECT, INSERT ON why_changed_records FROM nur_app")
    op.execute(
        "ALTER TABLE agent_workflows DROP CONSTRAINT IF EXISTS "
        "fk_agent_workflow_retry_owner"
    )
    op.execute(
        "ALTER TABLE agent_workflows ADD CONSTRAINT "
        "agent_workflows_retry_of_workflow_id_fkey "
        "FOREIGN KEY (retry_of_workflow_id) REFERENCES agent_workflows(id) "
        "ON DELETE RESTRICT"
    )
    for table in reversed(NEW_TABLES):
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
    op.execute("DROP INDEX IF EXISTS uq_insight_owner_pattern_version")
    op.execute("DROP INDEX IF EXISTS uq_insight_owner_pattern_evidence")
    op.execute("DROP INDEX IF EXISTS ix_insights_owner_pattern")
    op.execute("DROP INDEX IF EXISTS ix_insights_owner_lifecycle")
    op.execute("ALTER TABLE insights DROP CONSTRAINT IF EXISTS fk_insight_parent_owner")
    op.execute("ALTER TABLE insights DROP CONSTRAINT IF EXISTS fk_insight_pattern_owner")
    for constraint in (
        "ck_insights_time_scale",
        "ck_insights_source_diversity",
        "ck_insights_version",
        "ck_insights_epistemic_state",
        "ck_insights_lifecycle",
    ):
        op.execute(f"ALTER TABLE insights DROP CONSTRAINT IF EXISTS {constraint}")
    for column in (
        "source_invalidated_at", "cooldown_until", "reviewed_at", "surfaced_at",
        "calibration_target", "quality_policy_version", "quality_dimensions",
        "confidence_basis", "contradictions", "assumptions",
        "alternative_explanations", "source_diversity", "source_domains",
        "time_window_end", "time_window_start", "time_scale", "evidence_digest",
        "pattern_fingerprint", "insight_version", "epistemic_state",
        "lifecycle_status", "parent_insight_id", "pattern_id",
    ):
        op.execute(f"ALTER TABLE insights DROP COLUMN IF EXISTS {column}")
    op.execute("ALTER TABLE insights DROP CONSTRAINT IF EXISTS uq_insight_id_owner")
    op.execute(
        "ALTER TABLE omega_experiences DROP CONSTRAINT IF EXISTS "
        "uq_omega_experience_id_owner"
    )
    op.execute(
        "ALTER TABLE domain_events DROP CONSTRAINT IF EXISTS uq_domain_event_id_owner"
    )
    op.execute(
        "ALTER TABLE cognitive_events DROP CONSTRAINT IF EXISTS uq_cognitive_event_id_owner"
    )
    op.execute("DROP TABLE IF EXISTS insight_patterns CASCADE")
    op.execute("DROP INDEX IF EXISTS uq_omega_experience_owner_source")
    op.execute("DROP INDEX IF EXISTS ix_omega_experiences_owner_domain_time")
    op.execute("ALTER TABLE omega_experiences DROP CONSTRAINT IF EXISTS ck_omega_experience_retention")
    op.execute("ALTER TABLE omega_experiences DROP CONSTRAINT IF EXISTS ck_omega_experience_explicitness")
    for column in (
        "source_fingerprint", "invalidated_at", "observed_at", "retention_policy",
        "explicitness", "features", "source_domain",
    ):
        op.execute(f"ALTER TABLE omega_experiences DROP COLUMN IF EXISTS {column}")
