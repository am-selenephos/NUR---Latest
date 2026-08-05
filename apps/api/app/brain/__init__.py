"""NUR Brain plane — provider boundary, model routing, cognition, critic, synthesis.

The Brain plane never persists owner data directly; it receives a CognitiveTaskPacket
from the Mind plane and returns a CognitiveResult.  All durable state lives in existing
Agency Spine tables (ModelRun, CognitiveEvent, omega_*).
"""
