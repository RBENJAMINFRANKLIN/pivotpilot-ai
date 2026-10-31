"""Maintenance commands.

    python -m app.cli init              # create/upgrade the database and load reference data
    python -m app.cli seed              # reload reference data only (idempotent)
    python -m app.cli cleanup-guests    # delete expired guest workspaces (run daily in production)
    python -m app.cli verify-resources  # link-check the curated catalogue (needs internet)
"""

import sys
from pathlib import Path

from alembic import command
from alembic.config import Config

from app.config import get_settings
from app.db import SessionLocal
from app.seed.load import load_reference_data


def migrate() -> None:
    root = Path(__file__).resolve().parent.parent
    cfg = Config(str(root / "alembic.ini"))
    cfg.set_main_option("script_location", str(root / "alembic"))
    cfg.attributes["database_url"] = get_settings().database_url
    command.upgrade(cfg, "head")


def main(argv: list[str]) -> int:
    cmd = argv[1] if len(argv) > 1 else "help"
    if cmd == "init":
        migrate()
        with SessionLocal() as db:
            print("reference data:", load_reference_data(db))
    elif cmd == "seed":
        with SessionLocal() as db:
            print("reference data:", load_reference_data(db))
    elif cmd == "cleanup-guests":
        from app.services.workspaces import cleanup_expired_guests

        with SessionLocal() as db:
            print("deleted guest workspaces:", cleanup_expired_guests(db))
    elif cmd == "verify-resources":
        from sqlalchemy import select

        from app.models import LearningResource
        from app.services.resources import verify_resource

        with SessionLocal() as db:
            for r in db.scalars(select(LearningResource)):
                print(f"{verify_resource(r):11} {r.canonical_url}")
            db.commit()
    else:
        print(__doc__)
        return 0 if cmd == "help" else 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
