import argparse
import json

from sqlalchemy import select

from app.core.config import settings
from app.db.models import Role, User
from app.db.session import SessionLocal
from app.services.answering import answer
from app.services.embeddings import ensure_active_index, get_embedder
from app.services.generation import get_generator


def main():
    if not settings.database_url.endswith("/knowledge_eval"):
        raise SystemExit("Refusing to run: DATABASE_URL must point to the knowledge_eval database.")
    ap = argparse.ArgumentParser()
    ap.add_argument("--role", required=True, choices=["support", "operations", "hr"])
    ap.add_argument("question")
    args = ap.parse_args()

    embedder = get_embedder()
    with SessionLocal() as db:
        index_id = ensure_active_index(db, embedder)
        email = f"eval-{args.role}@local.test"
        user = db.scalar(select(User).where(User.email == email))
        if user is None:
            user = User(email=email, password_hash="!disabled", role=Role(args.role))
            db.add(user)
            db.commit()
        judge = get_generator(settings.judge_model) if settings.judge_model else None
        result = answer(db, user, args.question, embedder, index_id, get_generator(),
                        debug=True, judge=judge)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()