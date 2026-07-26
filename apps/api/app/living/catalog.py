"""Founder-locked definitions for NUR's six Star Systems."""

from dataclasses import dataclass


@dataclass(frozen=True)
class SystemDefinition:
    slug: str
    title: str
    definition: str
    questions: tuple[str, ...]
    checklist: tuple[str, ...]
    ignored_prediction: str
    followed_prediction: str


SYSTEMS: tuple[SystemDefinition, ...] = (
    SystemDefinition(
        slug="ambition",
        title="Ambition",
        definition=(
            "Private hunger, discipline, identity, long-range desire, self-respect, "
            "and work that matters even when nobody applauds."
        ),
        questions=(
            "What do you want but keep minimizing?",
            "What would make this week feel less wasted?",
            "What are you scared to admit you care about?",
            "What is one action nobody needs to see?",
            "Are you protecting your ambition or starving it?",
            "What would your future self be angry you ignored?",
        ),
        checklist=(
            "Define one private goal.",
            "Write why it matters.",
            "Choose one 20-minute move.",
            "Remove one performative task.",
            "Log one quiet win.",
            "Return tomorrow.",
        ),
        ignored_prediction="Open loops are likely to harden into drift and resentment.",
        followed_prediction="Repeated private movement is likely to stabilize identity and confidence.",
    ),
    SystemDefinition(
        slug="rebuild",
        title="Rebuild",
        definition=(
            "Anything damaged, collapsed, lost, neglected, or needing repair: body, "
            "mind, money, trust, relationships, rhythm, home, work, or project."
        ),
        questions=(
            "What needs rebuilding?",
            "Is it relationship, body, mind, money, work, home, project, or trust?",
            "What is still salvageable?",
            "What is not worth saving?",
            "What is the smallest stabilizing action?",
            "What keeps re-breaking it?",
            "What support or boundary is needed?",
        ),
        checklist=(
            "Name the broken area.",
            "Choose the rebuild type.",
            "Define the first repair action.",
            "Remove one repeating damage source.",
            "Create a recovery timeline.",
            "Mark the first repair.",
            "Return with an outcome.",
        ),
        ignored_prediction="The same damage source is likely to repeat without a smaller repair and boundary.",
        followed_prediction="Small stable repairs are likely to restore capacity before ambition expands.",
    ),
    SystemDefinition(
        slug="creation",
        title="Creation",
        definition=(
            "Making things: art, writing, product, code, business, content, systems, "
            "projects, ideas, releases, and deliverables."
        ),
        questions=(
            "What are you making?",
            "Is it an idea, draft, prototype, product, release, content, or art?",
            "What is the current state?",
            "What proves progress?",
            "What is the smallest shippable piece?",
            "What keeps delaying release?",
            "What needs review?",
        ),
        checklist=(
            "Create the project.",
            "Define the deliverable.",
            "Create one task.",
            "Attach evidence.",
            "Run and review the work.",
            "Ship one milestone.",
            "Log the outcome.",
        ),
        ignored_prediction="The work is likely to stall in ideation, avoidance, or review without a shippable edge.",
        followed_prediction="A small reviewed deliverable is likely to turn imagination into momentum.",
    ),
    SystemDefinition(
        slug="growth",
        title="Growth",
        definition=(
            "Expansion of capability: skill, learning, income, leverage, mastery, and "
            "the compounding progress that changes what you are able to do."
        ),
        questions=(
            "What capability are you trying to grow?",
            "Is this skill, knowledge, income, leverage, or reach?",
            "What can you already do that you could not before?",
            "What is the bottleneck holding the next level?",
            "What proves the growth is real and not just effort?",
            "What is the next deliberate session or move?",
        ),
        checklist=(
            "Name the capability.",
            "Define what proof of growth looks like.",
            "Create one deliberate practice or earning block.",
            "Complete one session.",
            "Record what changed.",
            "Return the outcome to the timeline.",
        ),
        ignored_prediction="Effort without a proof of change is likely to feel busy while capability stays flat.",
        followed_prediction="Deliberate practice with recorded evidence is likely to compound into real capability.",
    ),
    SystemDefinition(
        slug="introspection",
        title="Introspection",
        definition=(
            "Honest awareness of your own state: energy, capacity, meaning, patterns, "
            "what is actually happening beneath the activity, and what it is telling you."
        ),
        questions=(
            "What is actually true about your state right now?",
            "Energy and capacity from 0 to 10?",
            "What pattern keeps repeating?",
            "What are you avoiding noticing?",
            "What does this week want you to understand?",
            "What is one honest thing to write down?",
        ),
        checklist=(
            "Check state and capacity honestly.",
            "Write one unfiltered observation.",
            "Name the pattern.",
            "Decide whether it needs rest, repair, or a decision.",
            "Log the reflection.",
            "Return to it once more later.",
        ),
        ignored_prediction="Activity without review is likely to repeat the same pattern at higher cost.",
        followed_prediction="Recorded honest review is likely to surface the pattern early enough to change it.",
    ),
    SystemDefinition(
        slug="connection",
        title="Connection",
        definition=(
            "People, relationships, community, conversation, repair, support, group "
            "belonging, boundaries, and social energy."
        ),
        questions=(
            "Who are you thinking about?",
            "Is this support, conflict, repair, distance, or collaboration?",
            "What is unsaid?",
            "What is the next conversation?",
            "Does this need a boundary?",
            "Does this need a council or group NUR?",
        ),
        checklist=(
            "Add the person or orbit.",
            "Log the open conversation.",
            "Send one clear message.",
            "Attempt repair where appropriate.",
            "Set a boundary where needed.",
            "Start a council when multiple people are involved.",
            "Return the outcome.",
        ),
        ignored_prediction="Unspoken loops are likely to accumulate tension or distance.",
        followed_prediction="A clear conversation or boundary is likely to reduce relational ambiguity.",
    ),
)

BY_SLUG = {system.slug: system for system in SYSTEMS}
BY_TITLE = {system.title: system for system in SYSTEMS}


def require_system(slug: str) -> SystemDefinition:
    try:
        return BY_SLUG[slug]
    except KeyError as exc:
        raise KeyError(f"Unknown NUR System: {slug}") from exc
