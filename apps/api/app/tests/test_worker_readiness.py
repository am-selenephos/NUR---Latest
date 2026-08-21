"""Celery's production delivery policy is explicit and settings-backed."""

import pytest
from pydantic import ValidationError

from app.core.config import Settings, get_settings
from app.workers.celery_app import celery


def test_celery_worker_policy_matches_runtime_settings() -> None:
    settings = get_settings()

    assert celery.conf.worker_concurrency == settings.celery_worker_concurrency
    assert (
        celery.conf.worker_prefetch_multiplier
        == settings.celery_worker_prefetch_multiplier
    )
    assert celery.conf.task_acks_late is settings.celery_task_acks_late
    assert (
        celery.conf.task_reject_on_worker_lost
        is settings.celery_task_reject_on_worker_lost
    )
    assert (
        celery.conf.task_soft_time_limit
        == settings.celery_task_soft_time_limit_seconds
    )
    assert celery.conf.task_time_limit == settings.celery_task_time_limit_seconds
    assert celery.conf.broker_connection_retry_on_startup is True


def test_project_run_recovery_is_scheduled_with_a_bounded_interval() -> None:
    settings = get_settings()
    schedule = celery.conf.beat_schedule["nur-project-run-recovery"]

    assert schedule["task"] == "nur.reconcile_project_runs"
    assert schedule["args"] == ()
    assert schedule["schedule"] == settings.project_run_recovery_interval_seconds
    assert schedule["options"]["expires"] == settings.project_run_recovery_interval_seconds


def test_celery_defaults_are_bounded_and_recoverable() -> None:
    settings = Settings(_env_file=None)

    assert settings.celery_worker_concurrency == 2
    assert settings.celery_worker_prefetch_multiplier == 1
    assert settings.celery_task_acks_late is True
    assert settings.celery_task_reject_on_worker_lost is True
    assert (
        settings.celery_task_soft_time_limit_seconds
        < settings.celery_task_time_limit_seconds
    )
    assert settings.project_run_recovery_enabled is True
    assert 60 <= settings.project_run_recovery_interval_seconds <= 3600
    assert 1 <= settings.project_run_recovery_owner_batch <= 100
    assert 1 <= settings.project_run_recovery_run_batch <= 100


def test_celery_rejects_an_unordered_time_limit() -> None:
    with pytest.raises(ValidationError, match="must be lower"):
        Settings(
            _env_file=None,
            celery_task_soft_time_limit_seconds=180,
            celery_task_time_limit_seconds=180,
        )
