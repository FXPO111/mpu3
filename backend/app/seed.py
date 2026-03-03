from __future__ import annotations

import argparse

from app.db.session import SessionLocal
from app.db.seeds.seed_data import seed_products
from app.db.seeds.seed_questions import seed_topics_and_questions


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--only-missing",
        action="store_true",
        help="Only insert missing rows (do not overwrite existing records).",
    )
    parser.add_argument(
        "--with-questions",
        action="store_true",
        help="Also seed topics + interview questions (needed for realistic AI flow).",
    )
    args = parser.parse_args()

    with SessionLocal() as db:
        seed_products(db, only_missing=args.only_missing)

        if args.with_questions:
            seed_topics_and_questions(db, only_missing=True)

        db.commit()


if __name__ == "__main__":
    main()