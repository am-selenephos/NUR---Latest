"""Database and RLS isolation tests for Hardness / Self-Directed Learning Plane V1."""
from __future__ import annotations

import uuid
import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.cognition.correction_service import persist_user_correction
from app.learning.hardness.candidates import ingest_candidate_from_signal
from app.learning.hardness.schemas import LearningSignalKind
from app.learning.hardness.signals import create_signal_from_owner_correction
from app.models.hardness import LearningSignalRecord
from app.tests.conftest import register_user

SET_USER = "SELECT set_config('app.current_user_id', :uid, true)"


async def test_hardness_tables_rls_owner_isolation(client, app_engine):
    """Verify owner isolation across all 5 Hardness plane tables for SELECT, UPDATE, DELETE."""
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

    # Verify User A cannot read User B's rows in any of the 5 tables
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

    # Unauthenticated / default deny without context
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


async def test_forged_inserts_independently_denied_by_rls(client, app_engine):
    """Verify forged INSERTs across each table fail independently due to RLS WITH CHECK policy."""
    ra, _, _ = await register_user(client)
    client.cookies.clear()
    rb, _, _ = await register_user(client)
    uid_a, uid_b = ra.json()["id"], rb.json()["id"]

    # 1. Forged learning_signal
    async with app_engine.connect() as conn:
        await conn.execute(text(SET_USER), {"uid": uid_b})
        with pytest.raises(DBAPIError) as exc_info:
            await conn.execute(
                text("""
                    INSERT INTO learning_signals (id, owner_user_id, signal_kind, task_class, summary)
                    VALUES (:id, :uid_a, 'OWNER_CORRECTION', 'cognition', 'Forged Signal')
                """),
                {"id": str(uuid.uuid4()), "uid_a": uid_a},
            )
            await conn.commit()
        assert "row-level security" in str(exc_info.value).lower()

    # 2. Forged learning_candidate
    async with app_engine.connect() as conn:
        await conn.execute(text(SET_USER), {"uid": uid_b})
        with pytest.raises(DBAPIError) as exc_info:
            await conn.execute(
                text("""
                    INSERT INTO learning_candidates (id, owner_user_id, fingerprint, signal_kind, task_class, learning_scope)
                    VALUES (:id, :uid_a, 'fp_forged', 'OWNER_CORRECTION', 'cognition', 'OWNER_LOCAL')
                """),
                {"id": str(uuid.uuid4()), "uid_a": uid_a},
            )
            await conn.commit()
        assert "row-level security" in str(exc_info.value).lower()

    # 3. Forged curriculum_snapshot
    async with app_engine.connect() as conn:
        await conn.execute(text(SET_USER), {"uid": uid_b})
        with pytest.raises(DBAPIError) as exc_info:
            await conn.execute(
                text("""
                    INSERT INTO curriculum_snapshots (
                        id, owner_user_id, selector_policy_version, intervention,
                        dataset_hash, privacy_manifest_hash, provenance_manifest_hash
                    )
                    VALUES (:id, :uid_a, 'hardness-selector-v1', 'NO_CHANGE', 'hash_f', 'priv_f', 'prov_f')
                """),
                {"id": str(uuid.uuid4()), "uid_a": uid_a},
            )
            await conn.commit()
        assert "row-level security" in str(exc_info.value).lower()

    # 4. Forged training_experiment
    async with app_engine.connect() as conn:
        await conn.execute(text(SET_USER), {"uid": uid_b})
        with pytest.raises(DBAPIError) as exc_info:
            await conn.execute(
                text("""
                    INSERT INTO training_experiments (
                        id, owner_user_id, base_checkpoint_id, curriculum_id, curriculum_hash, intervention, hypothesis
                    )
                    VALUES (:id, :uid_a, 'base_v1', :cid, 'hash_f', 'NO_CHANGE', 'Hypothesis F')
                """),
                {"id": str(uuid.uuid4()), "uid_a": uid_a, "cid": str(uuid.uuid4())},
            )
            await conn.commit()
        assert "row-level security" in str(exc_info.value).lower()

    # 5. Forged learning_promotion_proposal
    async with app_engine.connect() as conn:
        await conn.execute(text(SET_USER), {"uid": uid_b})
        with pytest.raises(DBAPIError) as exc_info:
            await conn.execute(
                text("""
                    INSERT INTO learning_promotion_proposals (
                        id, owner_user_id, experiment_id, candidate_checkpoint_id, base_checkpoint_id,
                        target_metric_delta, general_regression_delta, critical_gates_passed,
                        recommendation, rationale
                    )
                    VALUES (
                        :id, :uid_a, :eid, 'cand_f', 'base_v1', 0.10, 0.001, true,
                        'PROMOTION_CANDIDATE', 'Rationale F'
                    )
                """),
                {"id": str(uuid.uuid4()), "uid_a": uid_a, "eid": str(uuid.uuid4())},
            )
            await conn.commit()
        assert "row-level security" in str(exc_info.value).lower()


async def test_owner_bound_composite_foreign_keys(client, app_engine):
    """Verify that composite foreign keys enforce owner alignment between experiments/curriculum, proposals/experiments, and signals/corrections."""
    ra, _, _ = await register_user(client)
    client.cookies.clear()
    rb, _, _ = await register_user(client)
    uid_a, uid_b = ra.json()["id"], rb.json()["id"]

    curr_a_id = str(uuid.uuid4())
    exp_a_id = str(uuid.uuid4())

    # User A creates a valid curriculum and experiment
    async with app_engine.connect() as conn:
        await conn.execute(text(SET_USER), {"uid": uid_a})
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
        await conn.execute(
            text("""
                INSERT INTO training_experiments (
                    id, owner_user_id, base_checkpoint_id, curriculum_id, curriculum_hash, intervention, hypothesis
                )
                VALUES (:id, :uid, 'base_v1', :cid, 'hash_a', 'NO_CHANGE', 'Exp A')
            """),
            {"id": exp_a_id, "uid": uid_a, "cid": curr_a_id},
        )
        await conn.commit()

    # 1. User B tries to create an experiment pointing to User A's curriculum (under User B's owner_user_id)
    async with app_engine.connect() as conn:
        await conn.execute(text(SET_USER), {"uid": uid_b})
        with pytest.raises(DBAPIError) as exc_info:
            await conn.execute(
                text("""
                    INSERT INTO training_experiments (
                        id, owner_user_id, base_checkpoint_id, curriculum_id, curriculum_hash, intervention, hypothesis
                    )
                    VALUES (:id, :uid_b, 'base_v1', :cid_a, 'hash_a', 'NO_CHANGE', 'Cross owner exp')
                """),
                {"id": str(uuid.uuid4()), "uid_b": uid_b, "cid_a": curr_a_id},
            )
            await conn.commit()
        assert "fk_training_experiments_curriculum_owner" in str(exc_info.value).lower() or "foreign key" in str(exc_info.value).lower()

    # 2. User B tries to create a proposal pointing to User A's experiment
    async with app_engine.connect() as conn:
        await conn.execute(text(SET_USER), {"uid": uid_b})
        with pytest.raises(DBAPIError) as exc_info:
            await conn.execute(
                text("""
                    INSERT INTO learning_promotion_proposals (
                        id, owner_user_id, experiment_id, candidate_checkpoint_id, base_checkpoint_id,
                        target_metric_delta, general_regression_delta, critical_gates_passed,
                        recommendation, rationale
                    )
                    VALUES (
                        :id, :uid_b, :eid_a, 'cand_b', 'base_v1', 0.10, 0.001, true,
                        'PROMOTION_CANDIDATE', 'Cross owner prop'
                    )
                """),
                {"id": str(uuid.uuid4()), "uid_b": uid_b, "eid_a": exp_a_id},
            )
            await conn.commit()
        assert "fk_learning_promotion_proposals_experiment_owner" in str(exc_info.value).lower() or "foreign key" in str(exc_info.value).lower()

    # 3. User B tries to create a learning_signal pointing to User A's correction
    session_maker = async_sessionmaker(app_engine, expire_on_commit=False, class_=AsyncSession)
    async with session_maker() as db_session:
        await db_session.execute(text(SET_USER), {"uid": uid_a})
        corr_a = await persist_user_correction(
            db_session,
            owner_user_id=uuid.UUID(uid_a),
            orbit_id=None,
            target_event_id=None,
            correction_text="User A correction",
            reason="test composite FK",
        )
        await db_session.commit()

    async with app_engine.connect() as conn:
        await conn.execute(text(SET_USER), {"uid": uid_b})
        with pytest.raises(DBAPIError) as exc_info:
            await conn.execute(
                text("""
                    INSERT INTO learning_signals (
                        id, owner_user_id, signal_kind, task_class, summary, source_correction_id
                    )
                    VALUES (:id, :uid_b, 'OWNER_CORRECTION', 'cognition', 'Cross owner signal', :corr_a_id)
                """),
                {"id": str(uuid.uuid4()), "uid_b": uid_b, "corr_a_id": str(corr_a.id)},
            )
            await conn.commit()
        assert "fk_learning_signals_user_corrections_owner" in str(exc_info.value).lower() or "foreign key" in str(exc_info.value).lower()


async def test_learning_signal_idempotency_and_recurrence(client, app_engine):
    """Verify that exact signal redelivery returns identical signal and does NOT increment recurrence,
    while distinct corrections DO increment recurrence."""
    ra, _, _ = await register_user(client)
    uid_a = uuid.UUID(ra.json()["id"])

    session_maker = async_sessionmaker(app_engine, expire_on_commit=False, class_=AsyncSession)
    async with session_maker() as db_session:
        await db_session.execute(text(SET_USER), {"uid": str(uid_a)})

        corr_1 = await persist_user_correction(
            db_session,
            owner_user_id=uid_a,
            orbit_id=None,
            target_event_id=None,
            correction_text="Use strict typing in all endpoints",
            reason="type safety",
        )
        corr_2 = await persist_user_correction(
            db_session,
            owner_user_id=uid_a,
            orbit_id=None,
            target_event_id=None,
            correction_text="Use strict typing in all endpoints",
            reason="type safety",
        )
        await db_session.flush()

        # 1. Fetch signal 1 generated for correction 1
        stmt_sig1 = select(LearningSignalRecord).where(
            LearningSignalRecord.owner_user_id == uid_a,
            LearningSignalRecord.source_correction_id == corr_1.id,
        )
        sig_1 = (await db_session.execute(stmt_sig1)).scalar_one()

        # 2. Redelivery attempt of the exact same correction 1
        sig_1_dup = await create_signal_from_owner_correction(
            db_session,
            owner_user_id=uid_a,
            orbit_id=None,
            correction_text="Use strict typing in all endpoints",
            reason="type safety",
            source_correction_id=corr_1.id,
        )
        # Must return the exact same signal row without duplicate insert
        assert sig_1_dup.id == sig_1.id

        # 3. Ingest candidate from sig_1 (initial occurrence = 1)
        cand = await ingest_candidate_from_signal(
            db_session,
            signal=sig_1,
            failure_signature="missing strict typing",
            desired_behavior="enforce strict typing everywhere",
        )
        assert cand.recurrence_count == 1

        # 4. Re-ingest from sig_1_dup (redelivery) -> recurrence_count must NOT change (stays 1)
        cand_after_dup = await ingest_candidate_from_signal(
            db_session,
            signal=sig_1_dup,
            failure_signature="missing strict typing",
            desired_behavior="enforce strict typing everywhere",
        )
        assert cand_after_dup.id == cand.id
        assert cand_after_dup.recurrence_count == 1

        # 5. Fetch signal 2 generated for correction 2
        stmt_sig2 = select(LearningSignalRecord).where(
            LearningSignalRecord.owner_user_id == uid_a,
            LearningSignalRecord.source_correction_id == corr_2.id,
        )
        sig_2 = (await db_session.execute(stmt_sig2)).scalar_one()
        assert sig_2.id != sig_1.id
        assert sig_2.source_correction_id == corr_2.id

        # 6. Ingest candidate from distinct sig_2 -> recurrence_count MUST increment to 2
        cand_after_sig2 = await ingest_candidate_from_signal(
            db_session,
            signal=sig_2,
            failure_signature="missing strict typing",
            desired_behavior="enforce strict typing everywhere",
        )
        assert cand_after_sig2.id == cand.id
        assert cand_after_sig2.recurrence_count == 2
        assert f"signal:{sig_1.id}" in cand_after_sig2.source_refs
        assert f"signal:{sig_2.id}" in cand_after_sig2.source_refs


async def test_persist_user_correction_atomic_signal_linkage(client, app_engine):
    """Verify that persist_user_correction creates UserCorrection, CognitiveEvent, and LearningSignalRecord atomically."""
    ra, _, _ = await register_user(client)
    uid_a = uuid.UUID(ra.json()["id"])

    session_maker = async_sessionmaker(app_engine, expire_on_commit=False, class_=AsyncSession)
    async with session_maker() as db_session:
        await db_session.execute(text(SET_USER), {"uid": str(uid_a)})

        corr = await persist_user_correction(
            db_session,
            owner_user_id=uid_a,
            orbit_id=None,
            target_event_id=None,
            correction_text="Prefer async generators over batch loading",
            reason="streaming efficiency",
        )

        assert corr.id is not None
        assert corr.owner_user_id == uid_a

        # Verify that a corresponding LearningSignalRecord exists linking to this correction
        stmt = select(LearningSignalRecord).where(
            LearningSignalRecord.owner_user_id == uid_a,
            LearningSignalRecord.source_correction_id == corr.id,
        )
        sig = (await db_session.execute(stmt)).scalar_one()
        assert sig.signal_kind == LearningSignalKind.OWNER_CORRECTION.value
        assert "Prefer async generators" in sig.summary
        assert sig.source_correction_id == corr.id
        await db_session.commit()


async def test_user_correction_cascade_deletes_learning_signal(client, app_engine):
    """Verify that deleting a UserCorrection cascades and removes its LearningSignalRecord."""
    ra, _, _ = await register_user(client)
    uid_a = uuid.UUID(ra.json()["id"])

    session_maker = async_sessionmaker(app_engine, expire_on_commit=False, class_=AsyncSession)
    async with session_maker() as db_session:
        await db_session.execute(text(SET_USER), {"uid": str(uid_a)})

        corr = await persist_user_correction(
            db_session,
            owner_user_id=uid_a,
            orbit_id=None,
            target_event_id=None,
            correction_text="Test cascade delete behavior",
            reason="cascade verification",
        )
        await db_session.flush()

        # Confirm signal exists
        stmt = select(LearningSignalRecord).where(
            LearningSignalRecord.owner_user_id == uid_a,
            LearningSignalRecord.source_correction_id == corr.id,
        )
        sig = (await db_session.execute(stmt)).scalar_one_or_none()
        assert sig is not None

        # Delete the UserCorrection directly
        from app.models import UserCorrection
        corr_to_del = await db_session.get(UserCorrection, corr.id)
        assert corr_to_del is not None
        await db_session.delete(corr_to_del)
        await db_session.flush()

        # Confirm signal was deleted via ON DELETE CASCADE
        sig_after = (await db_session.execute(stmt)).scalar_one_or_none()
        assert sig_after is None


