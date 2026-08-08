"""Database and RLS isolation tests for Hardness / Self-Directed Learning Plane V1."""
from __future__ import annotations

import uuid
import pytest
from sqlalchemy import text

from app.tests.conftest import register_user

SET_USER = "SELECT set_config('app.current_user_id', :uid, true)"


async def test_hardness_tables_rls_owner_isolation(client, app_engine):
    # Register two distinct users
    ra, _, _ = await register_user(client)
    client.cookies.clear()
    rb, _, _ = await register_user(client)
    uid_a, uid_b = ra.json()["id"], rb.json()["id"]

    # Populate data under User A and User B
    async with app_engine.connect() as conn:
        # Context = User A
        await conn.execute(text(SET_USER), {"uid": uid_a})
        sig_a_id = str(uuid.uuid4())
        await conn.execute(
            text("""
                INSERT INTO learning_signals (id, owner_user_id, signal_kind, task_class, summary)
                VALUES (:id, :uid, 'OWNER_CORRECTION', 'cognition', 'Signal A')
            """),
            {"id": sig_a_id, "uid": uid_a},
        )
        cand_a_id = str(uuid.uuid4())
        await conn.execute(
            text("""
                INSERT INTO learning_candidates (id, owner_user_id, fingerprint, signal_kind, task_class, learning_scope)
                VALUES (:id, :uid, 'fp_a', 'OWNER_CORRECTION', 'cognition', 'OWNER_LOCAL')
            """),
            {"id": cand_a_id, "uid": uid_a},
        )
        curr_a_id = str(uuid.uuid4())
        await conn.execute(
            text("""
                INSERT INTO curriculum_snapshots (
                    id, owner_user_id, selector_policy_version, intervention,
                    dataset_hash, privacy_manifest_hash, provenance_manifest_hash
                )
                VALUES (:id, :uid, 'hardness-selector-v1', 'NO_CHANGE', 'hash_a', 'priv_a', 'prov_a')
            """),
            {"id": curr_a_id, "uid": uid_a},
        )
        exp_a_id = str(uuid.uuid4())
        await conn.execute(
            text("""
                INSERT INTO training_experiments (
                    id, owner_user_id, base_checkpoint_id, curriculum_id, curriculum_hash, intervention, hypothesis
                )
                VALUES (:id, :uid, 'base_v1', :cid, 'hash_a', 'NO_CHANGE', 'Hypothesis A')
            """),
            {"id": exp_a_id, "uid": uid_a, "cid": curr_a_id},
        )
        prop_a_id = str(uuid.uuid4())
        await conn.execute(
            text("""
                INSERT INTO learning_promotion_proposals (
                    id, owner_user_id, experiment_id, candidate_checkpoint_id, base_checkpoint_id,
                    target_metric_delta, general_regression_delta, critical_gates_passed,
                    recommendation, rationale
                )
                VALUES (
                    :id, :uid, :eid, 'cand_a', 'base_v1', 0.10, 0.001, true,
                    'PROMOTION_CANDIDATE', 'Rationale A'
                )
            """),
            {"id": prop_a_id, "uid": uid_a, "eid": exp_a_id},
        )
        await conn.commit()

    async with app_engine.connect() as conn:
        # Context = User B
        await conn.execute(text(SET_USER), {"uid": uid_b})
        sig_b_id = str(uuid.uuid4())
        await conn.execute(
            text("""
                INSERT INTO learning_signals (id, owner_user_id, signal_kind, task_class, summary)
                VALUES (:id, :uid, 'OWNER_CORRECTION', 'cognition', 'Signal B')
            """),
            {"id": sig_b_id, "uid": uid_b},
        )
        cand_b_id = str(uuid.uuid4())
        await conn.execute(
            text("""
                INSERT INTO learning_candidates (id, owner_user_id, fingerprint, signal_kind, task_class, learning_scope)
                VALUES (:id, :uid, 'fp_b', 'OWNER_CORRECTION', 'cognition', 'OWNER_LOCAL')
            """),
            {"id": cand_b_id, "uid": uid_b},
        )
        curr_b_id = str(uuid.uuid4())
        await conn.execute(
            text("""
                INSERT INTO curriculum_snapshots (
                    id, owner_user_id, selector_policy_version, intervention,
                    dataset_hash, privacy_manifest_hash, provenance_manifest_hash
                )
                VALUES (:id, :uid, 'hardness-selector-v1', 'NO_CHANGE', 'hash_b', 'priv_b', 'prov_b')
            """),
            {"id": curr_b_id, "uid": uid_b},
        )
        exp_b_id = str(uuid.uuid4())
        await conn.execute(
            text("""
                INSERT INTO training_experiments (
                    id, owner_user_id, base_checkpoint_id, curriculum_id, curriculum_hash, intervention, hypothesis
                )
                VALUES (:id, :uid, 'base_v1', :cid, 'hash_b', 'NO_CHANGE', 'Hypothesis B')
            """),
            {"id": exp_b_id, "uid": uid_b, "cid": curr_b_id},
        )
        prop_b_id = str(uuid.uuid4())
        await conn.execute(
            text("""
                INSERT INTO learning_promotion_proposals (
                    id, owner_user_id, experiment_id, candidate_checkpoint_id, base_checkpoint_id,
                    target_metric_delta, general_regression_delta, critical_gates_passed,
                    recommendation, rationale
                )
                VALUES (
                    :id, :uid, :eid, 'cand_b', 'base_v1', 0.08, 0.002, true,
                    'PROMOTION_CANDIDATE', 'Rationale B'
                )
            """),
            {"id": prop_b_id, "uid": uid_b, "eid": exp_b_id},
        )
        await conn.commit()

    # Now verify User A cannot read User B's rows in any of the 5 tables
    async with app_engine.connect() as conn:
        await conn.execute(text(SET_USER), {"uid": uid_a})

        count_sig = (await conn.execute(text("SELECT count(*) FROM learning_signals"))).scalar_one()
        count_cand = (await conn.execute(text("SELECT count(*) FROM learning_candidates"))).scalar_one()
        count_curr = (await conn.execute(text("SELECT count(*) FROM curriculum_snapshots"))).scalar_one()
        count_exp = (await conn.execute(text("SELECT count(*) FROM training_experiments"))).scalar_one()
        count_prop = (await conn.execute(text("SELECT count(*) FROM learning_promotion_proposals"))).scalar_one()

        assert count_sig == 1
        assert count_cand == 1
        assert count_curr == 1
        assert count_exp == 1
        assert count_prop == 1

        # 1. Verify individual cross-owner SELECT (0 rows for B's specific IDs)
        assert (await conn.execute(text("SELECT count(*) FROM learning_signals WHERE id=:id"), {"id": sig_b_id})).scalar_one() == 0
        assert (await conn.execute(text("SELECT count(*) FROM learning_candidates WHERE id=:id"), {"id": cand_b_id})).scalar_one() == 0
        assert (await conn.execute(text("SELECT count(*) FROM curriculum_snapshots WHERE id=:id"), {"id": curr_b_id})).scalar_one() == 0
        assert (await conn.execute(text("SELECT count(*) FROM training_experiments WHERE id=:id"), {"id": exp_b_id})).scalar_one() == 0
        assert (await conn.execute(text("SELECT count(*) FROM learning_promotion_proposals WHERE id=:id"), {"id": prop_b_id})).scalar_one() == 0

        # 2. Verify individual cross-owner UPDATE (0 rows affected)
        assert (await conn.execute(text("UPDATE learning_signals SET summary='Hacked' WHERE id=:id"), {"id": sig_b_id})).rowcount == 0
        assert (await conn.execute(text("UPDATE learning_candidates SET status='REJECTED' WHERE id=:id"), {"id": cand_b_id})).rowcount == 0
        assert (await conn.execute(text("UPDATE curriculum_snapshots SET intervention='SFT' WHERE id=:id"), {"id": curr_b_id})).rowcount == 0
        assert (await conn.execute(text("UPDATE training_experiments SET status='FAILED' WHERE id=:id"), {"id": exp_b_id})).rowcount == 0
        assert (await conn.execute(text("UPDATE learning_promotion_proposals SET recommendation='REJECTED' WHERE id=:id"), {"id": prop_b_id})).rowcount == 0

        # 3. Verify individual cross-owner DELETE (0 rows affected)
        assert (await conn.execute(text("DELETE FROM learning_signals WHERE id=:id"), {"id": sig_b_id})).rowcount == 0
        assert (await conn.execute(text("DELETE FROM learning_candidates WHERE id=:id"), {"id": cand_b_id})).rowcount == 0
        assert (await conn.execute(text("DELETE FROM curriculum_snapshots WHERE id=:id"), {"id": curr_b_id})).rowcount == 0
        assert (await conn.execute(text("DELETE FROM training_experiments WHERE id=:id"), {"id": exp_b_id})).rowcount == 0
        assert (await conn.execute(text("DELETE FROM learning_promotion_proposals WHERE id=:id"), {"id": prop_b_id})).rowcount == 0

    # 4. Verify forged INSERT denial (User B trying to insert a row with owner_user_id = User A)
    import asyncpg
    async with app_engine.connect() as conn:
        await conn.execute(text(SET_USER), {"uid": uid_b})

        # Forged learning_signal
        with pytest.raises((Exception, asyncpg.exceptions.InsufficientPrivilegeError)):
            await conn.execute(
                text("""
                    INSERT INTO learning_signals (id, owner_user_id, signal_kind, task_class, summary)
                    VALUES (:id, :uid_a, 'OWNER_CORRECTION', 'cognition', 'Forged Signal')
                """),
                {"id": str(uuid.uuid4()), "uid_a": uid_a},
            )
            await conn.commit()

        # Forged learning_candidate
        with pytest.raises((Exception, asyncpg.exceptions.InsufficientPrivilegeError)):
            await conn.execute(
                text("""
                    INSERT INTO learning_candidates (id, owner_user_id, fingerprint, signal_kind, task_class, learning_scope)
                    VALUES (:id, :uid_a, 'fp_forged', 'OWNER_CORRECTION', 'cognition', 'OWNER_LOCAL')
                """),
                {"id": str(uuid.uuid4()), "uid_a": uid_a},
            )
            await conn.commit()

    # 5. Unauthenticated / default deny without context
    async with app_engine.connect() as conn:
        count_sig_anon = (await conn.execute(text("SELECT count(*) FROM learning_signals"))).scalar_one()
        count_cand_anon = (await conn.execute(text("SELECT count(*) FROM learning_candidates"))).scalar_one()
        count_curr_anon = (await conn.execute(text("SELECT count(*) FROM curriculum_snapshots"))).scalar_one()
        count_exp_anon = (await conn.execute(text("SELECT count(*) FROM training_experiments"))).scalar_one()
        count_prop_anon = (await conn.execute(text("SELECT count(*) FROM learning_promotion_proposals"))).scalar_one()

        assert count_sig_anon == 0
        assert count_cand_anon == 0
        assert count_curr_anon == 0
        assert count_exp_anon == 0
        assert count_prop_anon == 0

