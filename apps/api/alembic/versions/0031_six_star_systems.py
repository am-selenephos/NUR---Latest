"""Remap owner data from seven Star Systems to six.

Founder decision: Quiet Ambition becomes Ambition; Study is removed and Creation
takes its position; Money and Body are replaced by Growth and Introspection.

`system_slug` is a free-text column on many tables rather than a foreign key, so
nothing enforces referential integrity. Without this remap, every row written
against `quiet-ambition`, `study`, `money` or `body` would silently reference a
System that no longer exists — the rows would survive but disappear from every
System view, which is worse than a hard failure because it looks like data loss.

Mapping, and why:

    quiet-ambition -> ambition     pure rename, same meaning
    study          -> growth       deliberate learning is the clearest ancestor
                                   of capability growth
    money          -> growth       income and leverage are part of the same
                                   compounding-capability System now
    body           -> introspection   Introspection inherits self-reported state, and
                                   with it the medical operating boundary

`study` and `money` both fold into `growth`; that merge is intentional and not
reversible by slug alone, so the downgrade restores `quiet-ambition` and `body`
exactly and sends the merged rows back to `money`. That is recorded here rather
than hidden: a downgrade cannot recover which `growth` rows were once `study`.
"""

from alembic import op
import sqlalchemy as sa

revision = "0031_six_star_systems"
down_revision = "0030_project_execution_storage"
branch_labels = None
depends_on = None

# Every table carrying a free-text system_slug.
TABLES = (
    "system_actions",
    "goals",
    "system_diagnostics",
    "glow_transactions",
    "orbits",
    "am_projects",
    "community_posts",
    "community_rooms",
    "consultations",
    "plans",
    "timeline_events",
)

FORWARD = (
    ("quiet-ambition", "ambition"),
    ("study", "growth"),
    ("money", "growth"),
    ("body", "introspection"),
)

BACKWARD = (
    ("ambition", "quiet-ambition"),
    ("growth", "money"),
    ("introspection", "body"),
)

# System orbits are matched by *title*, not by slug (`owned_system_orbit` selects
# on `Orbit.title == definition.title`). Remapping slugs alone therefore leaves
# every existing owner without a resolvable orbit, and every System route answers
# 404. Titles must move with the slugs.
TITLES_FORWARD = (
    ("Quiet Ambition", "Ambition"),
    ("Money", "Growth"),
    ("Body", "Introspection"),
)

TITLES_BACKWARD = (
    ("Ambition", "Quiet Ambition"),
    ("Growth", "Money"),
    ("Introspection", "Body"),
)

# Study has no successor title: Creation took its position and no owner data
# should silently become Creation's. Its orbit is retired rather than renamed.
RETIRED_TITLES = ("Study",)


def _existing_tables(bind) -> set[str]:
    return set(sa.inspect(bind).get_table_names())


def _remap(pairs: tuple[tuple[str, str], ...]) -> None:
    """Remap slugs, reporting how many rows each table actually changed.

    These tables carry FORCE ROW LEVEL SECURITY and the migration role is not the
    policy subject, so an UPDATE issued normally matches **zero rows and raises
    nothing** — the migration would report success while changing nothing. FORCE
    is therefore lifted per table for the duration of the statement and restored
    immediately, and the affected row count is asserted rather than assumed.
    """
    bind = op.get_bind()
    present = _existing_tables(bind)
    for table in TABLES:
        if table not in present:
            continue
        columns = {column["name"] for column in sa.inspect(bind).get_columns(table)}
        if "system_slug" not in columns:
            continue

        forced = bind.execute(
            sa.text("SELECT relforcerowsecurity FROM pg_class WHERE relname = :t"),
            {"t": table},
        ).scalar()
        if forced:
            bind.execute(sa.text(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY"))
        try:
            for old, new in pairs:
                remaining = bind.execute(
                    sa.text(
                        f"SELECT count(*) FROM {table} WHERE system_slug = :old"  # noqa: S608
                    ),
                    {"old": old},
                ).scalar_one()
                if not remaining:
                    continue
                bind.execute(
                    sa.text(
                        f"UPDATE {table} SET system_slug = :new WHERE system_slug = :old"  # noqa: S608
                    ),
                    {"new": new, "old": old},
                )
                left = bind.execute(
                    sa.text(
                        f"SELECT count(*) FROM {table} WHERE system_slug = :old"  # noqa: S608
                    ),
                    {"old": old},
                ).scalar_one()
                if left:
                    raise RuntimeError(
                        f"{table}.system_slug still holds {left} '{old}' rows after remap; "
                        "the update was filtered instead of applied"
                    )
        finally:
            if forced:
                bind.execute(sa.text(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY"))


def _remap_orbit_titles(pairs: tuple[tuple[str, str], ...]) -> None:
    """Rename System orbits, lifting FORCE RLS exactly as `_remap` does."""
    bind = op.get_bind()
    if "orbits" not in _existing_tables(bind):
        return
    forced = bind.execute(
        sa.text("SELECT relforcerowsecurity FROM pg_class WHERE relname = 'orbits'")
    ).scalar()
    if forced:
        bind.execute(sa.text("ALTER TABLE orbits NO FORCE ROW LEVEL SECURITY"))
    try:
        for old, new in pairs:
            # An owner may already hold an orbit under the new title — the
            # registration seed creates the current System set, so a blind rename
            # produces two active orbits with the same title for one owner and
            # every System lookup then fails with MultipleResultsFound.
            # Where both exist, the superseded orbit is archived instead of
            # renamed; its rows are preserved and it simply stops resolving.
            bind.execute(
                sa.text(
                    "UPDATE orbits AS superseded SET status = 'ARCHIVED' "
                    "WHERE superseded.title = :old AND superseded.status = 'ACTIVE' "
                    "AND EXISTS ("
                    "  SELECT 1 FROM orbits AS keeper "
                    "  WHERE keeper.owner_user_id = superseded.owner_user_id "
                    "    AND keeper.title = :new AND keeper.status = 'ACTIVE'"
                    ")"
                ),
                {"new": new, "old": old},
            )
            bind.execute(
                sa.text("UPDATE orbits SET title = :new WHERE title = :old AND status = 'ACTIVE'"),
                {"new": new, "old": old},
            )
            left = bind.execute(
                sa.text("SELECT count(*) FROM orbits WHERE title = :old AND status = 'ACTIVE'"),
                {"old": old},
            ).scalar_one()
            if left:
                raise RuntimeError(
                    f"orbits.title still holds {left} active '{old}' rows after remap; "
                    "the update was filtered instead of applied"
                )

        # Whatever the path in, one owner must never end with two active orbits
        # sharing a title — that is what breaks every System route.
        duplicates = bind.execute(sa.text(
            "SELECT count(*) FROM ("
            "  SELECT owner_user_id, title FROM orbits WHERE status = 'ACTIVE' "
            "  GROUP BY owner_user_id, title HAVING count(*) > 1"
            ") AS d"
        )).scalar_one()
        if duplicates:
            # Keep the oldest, archive the rest: the earliest orbit carries the
            # owner's longest history.
            bind.execute(sa.text(
                "UPDATE orbits SET status = 'ARCHIVED' WHERE id IN ("
                "  SELECT id FROM ("
                "    SELECT id, row_number() OVER ("
                "      PARTITION BY owner_user_id, title ORDER BY created_at, id"
                "    ) AS rn FROM orbits WHERE status = 'ACTIVE'"
                "  ) ranked WHERE ranked.rn > 1"
                ")"
            ))
    finally:
        if forced:
            bind.execute(sa.text("ALTER TABLE orbits FORCE ROW LEVEL SECURITY"))


def _retire_orbits(titles: tuple[str, ...]) -> None:
    """Archive orbits whose System no longer exists, preserving their rows."""
    bind = op.get_bind()
    if "orbits" not in _existing_tables(bind):
        return
    columns = {column["name"] for column in sa.inspect(bind).get_columns("orbits")}
    if "status" not in columns:
        return
    forced = bind.execute(
        sa.text("SELECT relforcerowsecurity FROM pg_class WHERE relname = 'orbits'")
    ).scalar()
    if forced:
        bind.execute(sa.text("ALTER TABLE orbits NO FORCE ROW LEVEL SECURITY"))
    try:
        for title in titles:
            # Archived, never deleted: the owner's history stays intact and the
            # orbit simply stops resolving as an active System.
            bind.execute(
                sa.text(
                    "UPDATE orbits SET status = 'ARCHIVED' "
                    "WHERE title = :title AND status = 'ACTIVE'"
                ),
                {"title": title},
            )
    finally:
        if forced:
            bind.execute(sa.text("ALTER TABLE orbits FORCE ROW LEVEL SECURITY"))


def upgrade() -> None:
    _remap(FORWARD)
    _remap_orbit_titles(TITLES_FORWARD)
    _retire_orbits(RETIRED_TITLES)


def downgrade() -> None:
    _remap(BACKWARD)
    _remap_orbit_titles(TITLES_BACKWARD)
