"""Server-authoritative Glow ledger, progression, and engagement policy spine."""

from alembic import op


revision = "0026_glow_progression_spine"
down_revision = "0025_billing_revenue_spine"
branch_labels = None
depends_on = None

APP_ROLE = "nur_app"
UID = "NULLIF(current_setting('app.current_user_id', true), '')::uuid"
HAS_USER = (
    "current_setting('app.current_user_id', true) IS NOT NULL AND "
    "current_setting('app.current_user_id', true) <> ''"
)


def _owner_policies(table: str, *, update: bool = False) -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    privileges = "SELECT, INSERT, UPDATE" if update else "SELECT, INSERT"
    op.execute(f"GRANT {privileges} ON {table} TO {APP_ROLE}")
    op.execute(
        f"CREATE POLICY p_{table}_owner_select ON {table} FOR SELECT TO {APP_ROLE} "
        f"USING ({HAS_USER} AND owner_user_id = {UID})"
    )
    op.execute(
        f"CREATE POLICY p_{table}_owner_insert ON {table} FOR INSERT TO {APP_ROLE} "
        f"WITH CHECK ({HAS_USER} AND owner_user_id = {UID})"
    )
    if update:
        op.execute(
            f"CREATE POLICY p_{table}_owner_update ON {table} FOR UPDATE TO {APP_ROLE} "
            f"USING ({HAS_USER} AND owner_user_id = {UID}) "
            f"WITH CHECK (owner_user_id = {UID})"
        )


def upgrade() -> None:
    op.execute("ALTER TABLE glow_rules ADD COLUMN rule_version INTEGER NOT NULL DEFAULT 1 CHECK (rule_version >= 1)")
    op.execute("ALTER TABLE glow_rules ADD COLUMN default_multiplier NUMERIC(8,3) NOT NULL DEFAULT 1 CHECK (default_multiplier BETWEEN 0 AND 3)")
    op.execute("ALTER TABLE glow_rules ADD COLUMN multiplier_reason VARCHAR(120) NOT NULL DEFAULT 'BASE'")
    op.execute("ALTER TABLE glow_balances ADD COLUMN spent_points INTEGER NOT NULL DEFAULT 0 CHECK (spent_points >= 0)")
    op.execute("ALTER TABLE glow_balances ADD COLUMN reversal_debt INTEGER NOT NULL DEFAULT 0 CHECK (reversal_debt >= 0)")

    op.execute("ALTER TABLE glow_transactions ADD COLUMN source_event_id UUID REFERENCES domain_events(id) ON DELETE CASCADE")
    op.execute("ALTER TABLE glow_transactions ADD COLUMN multiplier_reason VARCHAR(120) NOT NULL DEFAULT 'BASE'")
    op.execute("ALTER TABLE glow_transactions ADD COLUMN rule_version INTEGER NOT NULL DEFAULT 1 CHECK (rule_version >= 1)")
    op.execute("ALTER TABLE glow_transactions ADD COLUMN anti_abuse_state VARCHAR(24) NOT NULL DEFAULT 'CLEAR'")
    op.execute("ALTER TABLE glow_transactions ADD COLUMN timezone VARCHAR(64) NOT NULL DEFAULT 'UTC'")
    op.execute("ALTER TABLE glow_transactions ADD COLUMN local_date DATE")
    # The backfill below runs as the migration role, which is not the RLS policy
    # subject (`nur_app`) and does not hold BYPASSRLS. With FORCE ROW LEVEL
    # SECURITY on, its INSERT and UPDATE match zero rows *silently*, and the
    # SET NOT NULL that follows then fails with "contains null values" on any
    # database that already holds Glow rows. It only ever succeeded on empty
    # databases, which is why the test suite never caught it.
    #
    # FORCE is lifted for the duration of the backfill and restored immediately
    # afterwards, so the tables spend no time outside RLS beyond this migration.
    op.execute("ALTER TABLE glow_transactions NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE domain_events NO FORCE ROW LEVEL SECURITY")

    op.execute("""
        INSERT INTO domain_events(
            owner_user_id, event_type, aggregate_type, aggregate_id,
            event_payload, idempotency_key, occurred_at
        )
        SELECT owner_user_id, 'glow.source.backfilled.v1', source_kind, source_id,
               jsonb_build_object('glow_event_type', event_type, 'migration', '0026'),
               'glow-source-backfill:' || id::text, created_at
        FROM glow_transactions
        ON CONFLICT (owner_user_id, idempotency_key) DO NOTHING
    """)
    op.execute("""
        UPDATE glow_transactions AS transaction
        SET source_event_id = event.id,
            local_date = (transaction.created_at AT TIME ZONE 'UTC')::date
        FROM domain_events AS event
        WHERE event.owner_user_id = transaction.owner_user_id
          AND event.idempotency_key = 'glow-source-backfill:' || transaction.id::text
    """)
    # Any row the join still could not resolve would fail the NOT NULL below with
    # the same opaque error, so surface it as an explicit, actionable failure.
    op.execute("""
        DO $$
        DECLARE orphaned integer;
        BEGIN
            SELECT count(*) INTO orphaned FROM glow_transactions WHERE source_event_id IS NULL;
            IF orphaned > 0 THEN
                RAISE EXCEPTION
                    'glow_transactions has % rows with no backfilled source event; '
                    'the domain_events backfill did not resolve them', orphaned;
            END IF;
        END $$;
    """)

    op.execute("ALTER TABLE glow_transactions FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE domain_events FORCE ROW LEVEL SECURITY")

    op.execute("ALTER TABLE glow_transactions ALTER COLUMN source_event_id SET NOT NULL")
    op.execute("ALTER TABLE glow_transactions ALTER COLUMN local_date SET NOT NULL")
    op.execute("CREATE INDEX ix_glow_transactions_owner_local_date ON glow_transactions(owner_user_id, local_date DESC)")
    op.execute("CREATE INDEX ix_glow_transactions_source_event ON glow_transactions(source_event_id)")

    op.execute("ALTER TABLE glow_streaks ADD COLUMN last_event_at TIMESTAMPTZ")
    op.execute("ALTER TABLE glow_streaks ADD COLUMN timezone VARCHAR(64) NOT NULL DEFAULT 'UTC'")
    op.execute("ALTER TABLE glow_streaks ADD COLUMN checkpoint_count INTEGER NOT NULL DEFAULT 0 CHECK (checkpoint_count >= 0)")
    op.execute("ALTER TABLE glow_streaks ADD COLUMN next_reward_at INTEGER NOT NULL DEFAULT 7 CHECK (next_reward_at >= 1)")
    op.execute("ALTER TABLE glow_streaks ADD COLUMN grace_until TIMESTAMPTZ")
    op.execute("ALTER TABLE glow_streaks ADD COLUMN state_reason VARCHAR(160) NOT NULL DEFAULT 'VERIFIED_EVENT'")
    op.execute("UPDATE glow_streaks SET last_event_at = updated_at WHERE last_event_date IS NOT NULL")

    op.execute("ALTER TABLE glow_achievements ADD COLUMN revoked_at TIMESTAMPTZ")
    op.execute("ALTER TABLE glow_achievements ADD COLUMN revocation_reason VARCHAR(500)")
    op.execute("ALTER TABLE notification_preferences ADD COLUMN in_app_enabled BOOLEAN NOT NULL DEFAULT true")
    op.execute("ALTER TABLE notification_preferences ADD COLUMN paused_until TIMESTAMPTZ")
    op.execute("ALTER TABLE notification_preferences ADD COLUMN max_daily INTEGER NOT NULL DEFAULT 3 CHECK (max_daily BETWEEN 0 AND 20)")
    op.execute("ALTER TABLE notifications ADD COLUMN idempotency_key VARCHAR(240)")
    op.execute("CREATE UNIQUE INDEX uq_notifications_owner_idempotency ON notifications(owner_user_id, idempotency_key) WHERE idempotency_key IS NOT NULL")

    op.execute("""
        CREATE TABLE glow_source_claims (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            owner_user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            event_type TEXT NOT NULL,
            source_kind TEXT NOT NULL,
            source_id UUID NOT NULL,
            source_event_id UUID NOT NULL REFERENCES domain_events(id) ON DELETE CASCADE,
            transaction_id UUID NOT NULL UNIQUE REFERENCES glow_transactions(id) ON DELETE CASCADE,
            claimed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_glow_source_claim UNIQUE(owner_user_id, event_type, source_kind, source_id)
        )
    """)
    op.execute("CREATE INDEX ix_glow_source_claim_owner_source ON glow_source_claims(owner_user_id, source_kind, source_id)")

    op.execute("""
        CREATE TABLE glow_reversals (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            owner_user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            transaction_id UUID NOT NULL UNIQUE REFERENCES glow_transactions(id) ON DELETE CASCADE,
            source_event_id UUID NOT NULL REFERENCES domain_events(id) ON DELETE CASCADE,
            points INTEGER NOT NULL CHECK (points > 0),
            balance_effect INTEGER NOT NULL CHECK (balance_effect BETWEEN 0 AND points),
            debt_effect INTEGER NOT NULL CHECK (debt_effect BETWEEN 0 AND points),
            reason VARCHAR(500) NOT NULL,
            actor_type VARCHAR(24) NOT NULL CHECK (actor_type IN ('SYSTEM','OWNER','REVIEWER')),
            actor_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
            idempotency_key VARCHAR(240) NOT NULL,
            reversed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE(owner_user_id, idempotency_key),
            CHECK (balance_effect + debt_effect = points)
        )
    """)
    op.execute("CREATE INDEX ix_glow_reversals_owner_created ON glow_reversals(owner_user_id, reversed_at DESC)")

    op.execute("""
        WITH ranked AS (
            SELECT id, owner_user_id, event_type, source_kind, source_id,
                   row_number() OVER (
                       PARTITION BY owner_user_id, event_type, source_kind, source_id
                       ORDER BY created_at, id
                   ) AS occurrence
            FROM glow_transactions
        )
        INSERT INTO glow_source_claims(
            owner_user_id, event_type, source_kind, source_id,
            source_event_id, transaction_id, claimed_at
        )
        SELECT transaction.owner_user_id, transaction.event_type,
               transaction.source_kind, transaction.source_id,
               transaction.source_event_id, transaction.id, transaction.created_at
        FROM glow_transactions AS transaction
        JOIN ranked ON ranked.id = transaction.id
        WHERE ranked.occurrence = 1
    """)
    op.execute("""
        WITH duplicates AS (
            SELECT transaction.*,
                   row_number() OVER (
                       PARTITION BY owner_user_id, event_type, source_kind, source_id
                       ORDER BY created_at, id
                   ) AS occurrence
            FROM glow_transactions AS transaction
        )
        INSERT INTO domain_events(
            owner_user_id, event_type, aggregate_type, aggregate_id,
            event_payload, idempotency_key, occurred_at
        )
        SELECT owner_user_id, 'glow.reversed.v1', 'glow_transaction', id,
               jsonb_build_object('reason_code', 'DUPLICATE_SOURCE_RECONCILIATION'),
               'glow-reversal-migration:' || id::text, now()
        FROM duplicates
        WHERE occurrence > 1
        ON CONFLICT (owner_user_id, idempotency_key) DO NOTHING
    """)
    op.execute("""
        WITH duplicates AS (
            SELECT transaction.*,
                   row_number() OVER (
                       PARTITION BY owner_user_id, event_type, source_kind, source_id
                       ORDER BY created_at, id
                   ) AS occurrence
            FROM glow_transactions AS transaction
        )
        INSERT INTO glow_reversals(
            owner_user_id, transaction_id, source_event_id, points,
            balance_effect, debt_effect, reason, actor_type, idempotency_key, reversed_at
        )
        SELECT duplicate.owner_user_id, duplicate.id, event.id, duplicate.final_points,
               duplicate.final_points, 0, 'Duplicate source claim reconciled during migration.',
               'SYSTEM', 'migration-duplicate:' || duplicate.id::text, now()
        FROM duplicates AS duplicate
        JOIN domain_events AS event
          ON event.owner_user_id = duplicate.owner_user_id
         AND event.idempotency_key = 'glow-reversal-migration:' || duplicate.id::text
        WHERE duplicate.occurrence > 1
    """)
    op.execute("""
        UPDATE glow_balances AS balance
        SET lifetime_points = active.total,
            balance = active.total,
            updated_at = now()
        FROM (
            SELECT transaction.owner_user_id,
                   COALESCE(sum(transaction.final_points) FILTER (WHERE reversal.id IS NULL), 0)::integer AS total
            FROM glow_transactions AS transaction
            LEFT JOIN glow_reversals AS reversal ON reversal.transaction_id = transaction.id
            GROUP BY transaction.owner_user_id
        ) AS active
        WHERE active.owner_user_id = balance.owner_user_id
    """)

    op.execute("""
        CREATE TABLE glow_fraud_flags (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            owner_user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            transaction_id UUID REFERENCES glow_transactions(id) ON DELETE SET NULL,
            source_kind VARCHAR(80) NOT NULL,
            source_id UUID NOT NULL,
            signal_type VARCHAR(64) NOT NULL,
            severity VARCHAR(16) NOT NULL CHECK (severity IN ('LOW','MEDIUM','HIGH')),
            status VARCHAR(24) NOT NULL DEFAULT 'OPEN' CHECK (status IN ('OPEN','DISMISSED','CONFIRMED')),
            idempotency_key VARCHAR(240) NOT NULL,
            signal_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE(owner_user_id, idempotency_key)
        )
    """)
    op.execute("CREATE INDEX ix_glow_fraud_owner_status ON glow_fraud_flags(owner_user_id, status, created_at DESC)")

    op.execute("""
        CREATE TABLE streak_definitions (
            streak_key VARCHAR(80) PRIMARY KEY,
            title VARCHAR(160) NOT NULL,
            eligible_event_types JSONB NOT NULL,
            grace_hours INTEGER NOT NULL DEFAULT 0 CHECK (grace_hours BETWEEN 0 AND 48),
            repair_cost INTEGER NOT NULL CHECK (repair_cost >= 0),
            checkpoint_interval INTEGER NOT NULL CHECK (checkpoint_interval >= 1),
            rule_version INTEGER NOT NULL CHECK (rule_version >= 1),
            active BOOLEAN NOT NULL DEFAULT true
        )
    """)
    op.execute("GRANT SELECT ON streak_definitions TO nur_app")
    op.execute("""
        INSERT INTO streak_definitions(
            streak_key, title, eligible_event_types, grace_hours,
            repair_cost, checkpoint_interval, rule_version
        ) VALUES
          ('daily_orbit', 'Daily Orbit', '["daily_checkin"]', 6, 10, 7, 1),
          ('talk', 'Talk', '["talk_meaningful"]', 0, 10, 7, 1),
          ('journal', 'Journal', '["journal_saved"]', 0, 10, 7, 1),
          ('plan_movement', 'Plan Movement', '["plan_created","plan_step_completed","task_made_smaller"]', 0, 10, 7, 1),
          ('outcome_return', 'Outcome Return', '["outcome_returned","missed_step_returned"]', 12, 10, 3, 1),
          ('consultation', 'Consultation', '["consultation_return"]', 0, 15, 3, 1)
    """)
    op.execute("""
        CREATE TABLE streak_events (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            owner_user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            streak_id UUID NOT NULL REFERENCES glow_streaks(id) ON DELETE CASCADE,
            transaction_id UUID REFERENCES glow_transactions(id) ON DELETE CASCADE,
            event_kind VARCHAR(24) NOT NULL CHECK (event_kind IN ('AWARDED','REPAIRED','REVERSED')),
            local_date DATE NOT NULL,
            timezone VARCHAR(64) NOT NULL,
            idempotency_key VARCHAR(240) NOT NULL,
            event_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
            occurred_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE(owner_user_id, idempotency_key)
        )
    """)
    op.execute("CREATE INDEX ix_streak_events_owner_streak_date ON streak_events(owner_user_id, streak_id, local_date)")
    op.execute("""
        CREATE TABLE streak_repairs (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            owner_user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            streak_id UUID NOT NULL REFERENCES glow_streaks(id) ON DELETE CASCADE,
            repaired_local_date DATE NOT NULL,
            cost_points INTEGER NOT NULL CHECK (cost_points >= 0),
            idempotency_key VARCHAR(240) NOT NULL,
            status VARCHAR(24) NOT NULL CHECK (status IN ('APPLIED','REVERSED')),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE(owner_user_id, idempotency_key),
            UNIQUE(owner_user_id, streak_id, repaired_local_date)
        )
    """)

    op.execute("""
        CREATE TABLE quest_templates (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            quest_key VARCHAR(100) NOT NULL,
            rule_version INTEGER NOT NULL CHECK (rule_version >= 1),
            cadence VARCHAR(16) NOT NULL CHECK (cadence IN ('DAILY','WEEKLY')),
            title VARCHAR(240) NOT NULL,
            target_event_types JSONB NOT NULL,
            base_target INTEGER NOT NULL CHECK (base_target >= 1),
            low_capacity_target INTEGER NOT NULL CHECK (low_capacity_target >= 1),
            reward_points INTEGER NOT NULL CHECK (reward_points >= 0),
            difficulty VARCHAR(24) NOT NULL,
            rationale VARCHAR(500) NOT NULL,
            active BOOLEAN NOT NULL DEFAULT true,
            CONSTRAINT uq_quest_template_version UNIQUE(quest_key, rule_version)
        )
    """)
    op.execute("GRANT SELECT ON quest_templates TO nur_app")
    op.execute("""
        INSERT INTO quest_templates(
            quest_key, rule_version, cadence, title, target_event_types,
            base_target, low_capacity_target, reward_points, difficulty, rationale
        ) VALUES
          ('private_continuity', 1, 'DAILY', 'Return to one private thread',
           '["daily_checkin","journal_saved","talk_meaningful"]', 1, 1, 3, 'GENTLE',
           'One verified private action keeps continuity without rewarding time spent.'),
          ('meaningful_movement', 1, 'DAILY', 'Move one real thing',
           '["plan_step_completed","system.action_marked","missed_step_returned","outcome_returned","project.task_completed"]',
           1, 1, 3, 'FOCUSED', 'One server-confirmed movement or Return.'),
          ('three_returns', 1, 'WEEKLY', 'Return with evidence',
           '["outcome_returned","missed_step_returned","consultation_return","project.evidence_verified"]',
           3, 1, 10, 'DEEP', 'Returned outcomes count more than raw creation volume.')
    """)
    op.execute("""
        CREATE TABLE user_quests (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            owner_user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            template_id UUID NOT NULL REFERENCES quest_templates(id) ON DELETE RESTRICT,
            local_period_key VARCHAR(32) NOT NULL,
            timezone VARCHAR(64) NOT NULL,
            period_start TIMESTAMPTZ NOT NULL,
            period_end TIMESTAMPTZ NOT NULL,
            target_count INTEGER NOT NULL CHECK (target_count >= 1),
            progress_count INTEGER NOT NULL DEFAULT 0 CHECK (progress_count >= 0),
            status VARCHAR(24) NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE','COMPLETED','CLAIMED','EXPIRED')),
            completed_at TIMESTAMPTZ,
            claimed_at TIMESTAMPTZ,
            claim_transaction_id UUID REFERENCES glow_transactions(id) ON DELETE SET NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_user_quest_period UNIQUE(owner_user_id, template_id, local_period_key),
            CHECK (period_end > period_start)
        )
    """)
    op.execute("CREATE INDEX ix_user_quests_owner_period ON user_quests(owner_user_id, period_end DESC)")
    op.execute("""
        INSERT INTO glow_rules(
            event_type, base_points, daily_cap, weekly_cap, spam_window_seconds,
            action_type, requires_persistence, description, rule_version
        ) VALUES
          ('quest.daily_claimed', 3, 6, 42, 0, 'quest.daily_claimed', true,
           'A completed persisted daily quest claimed by its owner.', 1),
          ('quest.weekly_claimed', 10, NULL, 10, 0, 'quest.weekly_claimed', true,
           'A completed persisted weekly mission claimed by its owner.', 1)
        ON CONFLICT (event_type) DO NOTHING
    """)

    op.execute("""
        CREATE TABLE level_definitions (
            level INTEGER PRIMARY KEY CHECK (level >= 1),
            level_key VARCHAR(80) NOT NULL UNIQUE,
            title VARCHAR(160) NOT NULL,
            threshold INTEGER NOT NULL UNIQUE CHECK (threshold >= 0),
            unlock_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
            active BOOLEAN NOT NULL DEFAULT true
        )
    """)
    op.execute("GRANT SELECT ON level_definitions TO nur_app")
    op.execute("""
        INSERT INTO level_definitions(level, level_key, title, threshold, unlock_metadata) VALUES
          (1, 'signal', 'Orbit Seed', 0, '{"constellation_stage":"seed"}'),
          (2, 'spark', 'Ember', 50, '{"constellation_stage":"spark"}'),
          (3, 'pathway', 'Star Builder', 150, '{"constellation_stage":"pathway"}'),
          (4, 'orbit', 'Orbit Keeper', 350, '{"constellation_stage":"orbit"}'),
          (5, 'constellation', 'Constellation', 700, '{"constellation_stage":"constellation"}'),
          (6, 'system', 'System', 1200, '{"constellation_stage":"system"}'),
          (7, 'living_intelligence', 'Living Intelligence', 2000, '{"constellation_stage":"living_intelligence"}')
    """)
    op.execute("""
        CREATE TABLE user_levels (
            owner_user_id UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
            level INTEGER NOT NULL REFERENCES level_definitions(level) ON DELETE RESTRICT,
            lifetime_points INTEGER NOT NULL CHECK (lifetime_points >= 0),
            reached_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("""
        CREATE TABLE level_events (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            owner_user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            level INTEGER NOT NULL,
            event_kind VARCHAR(24) NOT NULL CHECK (event_kind IN ('REACHED','REVERSED')),
            source_transaction_id UUID REFERENCES glow_transactions(id) ON DELETE CASCADE,
            source_reversal_id UUID REFERENCES glow_reversals(id) ON DELETE CASCADE,
            idempotency_key VARCHAR(240) NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE(owner_user_id, idempotency_key)
        )
    """)

    op.execute("""
        CREATE TABLE achievement_definitions (
            achievement_key VARCHAR(100) PRIMARY KEY,
            title VARCHAR(200) NOT NULL,
            threshold INTEGER NOT NULL CHECK (threshold >= 1),
            rule_version INTEGER NOT NULL CHECK (rule_version >= 1),
            reversible BOOLEAN NOT NULL DEFAULT true,
            active BOOLEAN NOT NULL DEFAULT true
        )
    """)
    op.execute("GRANT SELECT ON achievement_definitions TO nur_app")
    op.execute("""
        INSERT INTO achievement_definitions(
            achievement_key, title, threshold, rule_version
        ) VALUES
          ('first_glow', 'First verified Glow', 1, 1),
          ('ember_50', 'Fifty source-linked Glow', 50, 1),
          ('star_builder_150', 'One hundred fifty source-linked Glow', 150, 1),
          ('orbit_keeper_350', 'Three hundred fifty source-linked Glow', 350, 1),
          ('constellation_700', 'Seven hundred source-linked Glow', 700, 1),
          ('system_1200', 'Twelve hundred source-linked Glow', 1200, 1),
          ('living_intelligence_2000', 'Two thousand source-linked Glow', 2000, 1)
    """)
    op.execute("""
        CREATE TABLE achievement_events (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            owner_user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            achievement_key VARCHAR(100) NOT NULL,
            event_kind VARCHAR(24) NOT NULL CHECK (event_kind IN ('UNLOCKED','REVOKED','RESTORED')),
            source_transaction_id UUID REFERENCES glow_transactions(id) ON DELETE CASCADE,
            source_reversal_id UUID REFERENCES glow_reversals(id) ON DELETE CASCADE,
            idempotency_key VARCHAR(240) NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE(owner_user_id, idempotency_key)
        )
    """)

    op.execute("""
        CREATE TABLE reward_inventory (
            reward_key VARCHAR(100) PRIMARY KEY,
            title VARCHAR(200) NOT NULL,
            category VARCHAR(48) NOT NULL,
            cost_points INTEGER NOT NULL CHECK (cost_points >= 0),
            minimum_level INTEGER NOT NULL REFERENCES level_definitions(level) ON DELETE RESTRICT,
            reward_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
            active BOOLEAN NOT NULL DEFAULT true
        )
    """)
    op.execute("GRANT SELECT ON reward_inventory TO nur_app")
    op.execute("""
        INSERT INTO reward_inventory(
            reward_key, title, category, cost_points, minimum_level, reward_metadata
        ) VALUES
          ('nebula_accent', 'Nebula accent', 'COSMETIC', 10, 1, '{"effect":"nebula_accent"}'),
          ('orbit_frame', 'Orbit frame', 'COSMETIC', 25, 2, '{"effect":"orbit_frame"}'),
          ('reflection_lens', 'Reflection lens', 'TEMPLATE', 40, 2, '{"effect":"reflection_lens"}')
    """)
    op.execute("""
        CREATE TABLE user_rewards (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            owner_user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            reward_key VARCHAR(100) NOT NULL REFERENCES reward_inventory(reward_key) ON DELETE RESTRICT,
            cost_points INTEGER NOT NULL CHECK (cost_points >= 0),
            idempotency_key VARCHAR(240) NOT NULL,
            status VARCHAR(24) NOT NULL CHECK (status IN ('REDEEMED','REVOKED')),
            redeemed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE(owner_user_id, idempotency_key),
            UNIQUE(owner_user_id, reward_key)
        )
    """)

    op.execute("""
        CREATE TABLE engagement_experiment_definitions (
            experiment_key VARCHAR(100) PRIMARY KEY,
            hypothesis VARCHAR(500) NOT NULL,
            primary_metric VARCHAR(120) NOT NULL,
            guardrail_metrics JSONB NOT NULL,
            variants JSONB NOT NULL,
            target_cohort JSONB NOT NULL,
            sample_rule JSONB NOT NULL,
            stop_rule JSONB NOT NULL,
            status VARCHAR(24) NOT NULL CHECK (status IN ('DRAFT','ACTIVE','STOPPED','ROLLED_BACK')),
            version INTEGER NOT NULL CHECK (version >= 1),
            started_at TIMESTAMPTZ,
            stopped_at TIMESTAMPTZ
        )
    """)
    op.execute("GRANT SELECT ON engagement_experiment_definitions TO nur_app")
    op.execute("""
        INSERT INTO engagement_experiment_definitions(
            experiment_key, hypothesis, primary_metric, guardrail_metrics,
            variants, target_cohort, sample_rule, stop_rule, status, version
        ) VALUES (
            'reward_acknowledgement_timing',
            'A calm verified acknowledgement improves meaningful returns without increasing distress.',
            'meaningful_action_week',
            '["notification_opt_out","sleep_complaint","distress_report"]',
            '["immediate_verified","next_surface_verified"]',
            jsonb_build_object('age_gate', '18+', 'crisis_excluded', true),
            jsonb_build_object('minimum_exposures', 500, 'maximum_days', 21),
            jsonb_build_object('stop_on_guardrail_regression', true),
            'DRAFT', 1
        )
    """)
    op.execute("""
        CREATE TABLE engagement_experiment_assignments (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            owner_user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            experiment_key VARCHAR(100) NOT NULL,
            experiment_version INTEGER NOT NULL,
            variant VARCHAR(80) NOT NULL,
            assignment_digest VARCHAR(64) NOT NULL,
            assigned_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_engagement_experiment_assignment
              UNIQUE(owner_user_id, experiment_key, experiment_version)
        )
    """)
    op.execute("""
        CREATE TABLE engagement_experiment_exposures (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            owner_user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            assignment_id UUID NOT NULL REFERENCES engagement_experiment_assignments(id) ON DELETE CASCADE,
            surface VARCHAR(80) NOT NULL,
            idempotency_key VARCHAR(240) NOT NULL,
            exposure_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
            exposed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE(owner_user_id, idempotency_key)
        )
    """)

    op.execute("""
        CREATE TABLE notification_deliveries (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            owner_user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            notification_id UUID NOT NULL REFERENCES notifications(id) ON DELETE CASCADE,
            channel VARCHAR(24) NOT NULL CHECK (channel IN ('IN_APP','PUSH','EMAIL')),
            status VARCHAR(24) NOT NULL CHECK (status IN ('PENDING','DELIVERED','FAILED','SUPPRESSED')),
            idempotency_key VARCHAR(240) NOT NULL,
            attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
            provider_message_id VARCHAR(240),
            failure_code VARCHAR(80),
            deliver_after TIMESTAMPTZ NOT NULL,
            delivered_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE(owner_user_id, idempotency_key)
        )
    """)
    op.execute("CREATE INDEX ix_notification_deliveries_due ON notification_deliveries(status, deliver_after)")

    for table in (
        "glow_source_claims", "glow_reversals", "glow_fraud_flags",
        "streak_events", "streak_repairs", "level_events", "achievement_events",
        "user_rewards", "engagement_experiment_assignments",
        "engagement_experiment_exposures",
    ):
        _owner_policies(table)
    for table in ("user_quests", "user_levels", "notification_deliveries"):
        _owner_policies(table, update=True)

    op.execute("REVOKE UPDATE, DELETE ON glow_transactions FROM nur_app")
    op.execute("DROP POLICY IF EXISTS p_glow_transactions_owner_update ON glow_transactions")
    op.execute("DROP POLICY IF EXISTS p_glow_transactions_owner_delete ON glow_transactions")
    op.execute("REVOKE UPDATE, DELETE ON glow_reward_events FROM nur_app")
    op.execute("DROP POLICY IF EXISTS p_glow_reward_events_owner_update ON glow_reward_events")
    op.execute("DROP POLICY IF EXISTS p_glow_reward_events_owner_delete ON glow_reward_events")


def downgrade() -> None:
    op.execute("GRANT UPDATE, DELETE ON glow_transactions TO nur_app")
    op.execute(
        f"CREATE POLICY p_glow_transactions_owner_update ON glow_transactions FOR UPDATE TO {APP_ROLE} "
        f"USING ({HAS_USER} AND owner_user_id = {UID}) WITH CHECK (owner_user_id = {UID})"
    )
    op.execute(
        f"CREATE POLICY p_glow_transactions_owner_delete ON glow_transactions FOR DELETE TO {APP_ROLE} "
        f"USING ({HAS_USER} AND owner_user_id = {UID})"
    )
    op.execute("GRANT UPDATE, DELETE ON glow_reward_events TO nur_app")
    op.execute(
        f"CREATE POLICY p_glow_reward_events_owner_update ON glow_reward_events FOR UPDATE TO {APP_ROLE} "
        f"USING ({HAS_USER} AND owner_user_id = {UID}) WITH CHECK (owner_user_id = {UID})"
    )
    op.execute(
        f"CREATE POLICY p_glow_reward_events_owner_delete ON glow_reward_events FOR DELETE TO {APP_ROLE} "
        f"USING ({HAS_USER} AND owner_user_id = {UID})"
    )
    for table in (
        "notification_deliveries",
        "engagement_experiment_exposures",
        "engagement_experiment_assignments",
        "engagement_experiment_definitions",
        "user_rewards",
        "reward_inventory",
        "achievement_events",
        "achievement_definitions",
        "level_events",
        "user_levels",
        "level_definitions",
        "user_quests",
        "quest_templates",
        "streak_repairs",
        "streak_events",
        "streak_definitions",
        "glow_fraud_flags",
        "glow_source_claims",
        "glow_reversals",
    ):
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
    op.execute("DELETE FROM glow_rules WHERE event_type IN ('quest.daily_claimed','quest.weekly_claimed')")
    op.execute("DROP INDEX IF EXISTS uq_notifications_owner_idempotency")
    op.execute("ALTER TABLE notifications DROP COLUMN IF EXISTS idempotency_key")
    for column in ("max_daily", "paused_until", "in_app_enabled"):
        op.execute(f"ALTER TABLE notification_preferences DROP COLUMN IF EXISTS {column}")
    for column in ("revocation_reason", "revoked_at"):
        op.execute(f"ALTER TABLE glow_achievements DROP COLUMN IF EXISTS {column}")
    for column in (
        "state_reason", "grace_until", "next_reward_at", "checkpoint_count",
        "timezone", "last_event_at",
    ):
        op.execute(f"ALTER TABLE glow_streaks DROP COLUMN IF EXISTS {column}")
    op.execute("DROP INDEX IF EXISTS ix_glow_transactions_source_event")
    op.execute("DROP INDEX IF EXISTS ix_glow_transactions_owner_local_date")
    for column in (
        "local_date", "timezone", "anti_abuse_state", "rule_version",
        "multiplier_reason", "source_event_id",
    ):
        op.execute(f"ALTER TABLE glow_transactions DROP COLUMN IF EXISTS {column}")
    for column in ("reversal_debt", "spent_points"):
        op.execute(f"ALTER TABLE glow_balances DROP COLUMN IF EXISTS {column}")
    for column in ("multiplier_reason", "default_multiplier", "rule_version"):
        op.execute(f"ALTER TABLE glow_rules DROP COLUMN IF EXISTS {column}")
    op.execute("DELETE FROM domain_events WHERE idempotency_key LIKE 'glow-source-backfill:%' OR idempotency_key LIKE 'glow-reversal-migration:%'")
