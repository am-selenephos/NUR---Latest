"""Queue payloads carry IDs, never the graph or owner text.

Serialising a plan into a message would put private content in Redis, grow the
payload with the plan, and let a stale message resurrect a plan version the owner
has already revised. This asserts the task signatures cannot accept those things.
"""

import inspect

from app.workers import agentic_tasks


def _params(task):
    return list(inspect.signature(task.__wrapped__).parameters)


def test_step_task_accepts_only_ids_and_a_traceparent():
    assert _params(agentic_tasks.execute_agentic_step_task) == [
        "step_id", "owner_user_id", "workflow_id", "traceparent",
    ]


def test_no_agentic_task_accepts_a_payload_body():
    forbidden = {
        "arguments", "payload", "context", "plan", "steps", "graph", "text",
        "body", "content", "prompt", "memory", "journal", "state",
    }
    for name in ("execute_agentic_step_task", "recover_agentic_steps_task",
                 "unlock_agentic_dependants_task"):
        task = getattr(agentic_tasks, name)
        leaked = forbidden & set(_params(task))
        assert not leaked, f"{name} accepts {sorted(leaked)} — that is not an ID"


def test_tasks_use_late_acknowledgement_where_they_do_work():
    """acks_late is what makes a killed worker's message redeliverable. It is
    only safe because the claim makes redelivery idempotent."""
    assert agentic_tasks.execute_agentic_step_task.acks_late is True


def test_recovery_task_is_not_owner_scoped_by_signature():
    """The sweep spans owners by design; requiring an owner id would force it to
    enumerate every owner first, which is slower and more privileged."""
    assert "owner_user_id" not in _params(agentic_tasks.recover_agentic_steps_task)
