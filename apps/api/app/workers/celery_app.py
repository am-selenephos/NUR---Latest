from celery import Celery

from app.core.config import get_settings

_s = get_settings()

celery = Celery(
    "nur",
    broker=_s.redis_url,
    backend=_s.redis_url,
    # `app.workers.agentic_tasks` was missing here, so a real worker booted with
    # `-A app.workers.celery_app` registered none of the Agency Plane tasks. The
    # dispatcher publishes `nur.agentic.execute_step`, which the worker would
    # reject as unknown — the whole outbox → dispatcher → worker chain was dead
    # in production. Tests never caught it because importing the module in a
    # test registers the tasks as a side effect.
    include=["app.workers.tasks", "app.workers.agentic_tasks"],
)
celery.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    task_acks_late=True,
    worker_hijack_root_logger=False,
    task_default_queue="nur_default",
    # Job payloads carry IDs only — never private raw text (constitution §17/§20).
)

_beat: dict = {}

if _s.omega_scheduled_consolidation:
    _beat["nur-omega-consolidate-due-owners"] = {
        "task": "nur.omega_consolidate_due_owners",
        "schedule": max(3600, int(_s.omega_consolidation_interval_hours) * 3600),
        "args": (),
    }

if _s.agentic_dispatch_enabled:
    # The Agency Plane's two background loops. Without these the outbox is a
    # table nothing drains and an abandoned lease is never reclaimed — the
    # durable spine would be correct and inert.
    _beat["nur-agentic-dispatch"] = {
        "task": "nur.agentic.dispatch",
        "schedule": max(1, int(_s.agentic_dispatch_interval_seconds)),
        "args": (),
        # A backlog must not accumulate one queued dispatcher run per tick while
        # a slow run is still draining; a later tick supersedes an older one.
        "options": {"expires": max(1, int(_s.agentic_dispatch_interval_seconds))},
    }
    _beat["nur-agentic-recover"] = {
        "task": "nur.agentic.recover",
        "schedule": max(5, int(_s.agentic_recovery_interval_seconds)),
        "args": (),
        "options": {"expires": max(5, int(_s.agentic_recovery_interval_seconds))},
    }

celery.conf.beat_schedule = _beat
