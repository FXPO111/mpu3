from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.domain.models import Product, Question, Rubric, Topic


@dataclass(frozen=True)
class SeedProductSpec:
    code: str
    plan: str
    name: str
    price_cents: int
    valid_days: int
    ai_credits: int


DEFAULT_PLAN_PRODUCTS: tuple[SeedProductSpec, ...] = (
    SeedProductSpec(code="PLAN_START", plan="start", name="Start", price_cents=23000, valid_days=14, ai_credits=1200),
    SeedProductSpec(code="PLAN_PRO", plan="pro", name="Pro", price_cents=70000, valid_days=30, ai_credits=8000),
    SeedProductSpec(code="PLAN_INTENSIVE", plan="intensive", name="Intensive", price_cents=150000, valid_days=45, ai_credits=15000),
)


DEFAULT_EXTRA_PRODUCTS: tuple[dict[str, object], ...] = (
    {"code": "AI_PACK_50", "type": "ai_pack", "name_de": "AI 50", "name_en": "AI 50", "price_cents": 4900, "currency": "EUR", "metadata_json": {"credits": 50}},
    {"code": "CALL_60", "type": "booking", "name_de": "Beratung 60", "name_en": "Consultation 60", "price_cents": 9900, "currency": "EUR", "metadata_json": {}},
)


SEED_TAG = "default_plans_v1"


def seed_questions(db: Session):
    topic = Topic(slug="alcohol", title_de="Alkohol", title_en="Alcohol")
    db.add(topic)
    db.flush()
    db.add(Question(topic_id=topic.id, level=2, question_de="Was hat sich seit dem Vorfall verändert?", question_en="What changed after the incident?", intent="behavioral change", tags=["change", "responsibility"]))


def seed_rubrics(db: Session):
    db.add_all([
        Rubric(code="clarity", title_de="Klarheit", title_en="Clarity", description="Clear narrative"),
        Rubric(code="responsibility", title_de="Verantwortung", title_en="Responsibility", description="Owns responsibility"),
    ])


def seed_products(db: Session, *, only_missing: bool = False) -> dict[str, int]:
    stats = {"created": 0, "updated": 0, "skipped": 0}

    for spec in DEFAULT_PLAN_PRODUCTS:
        product = db.query(Product).filter(Product.code == spec.code).one_or_none()

        if product is None:
            db.add(
                Product(
                    code=spec.code,
                    type="program",
                    name_de=spec.name,
                    name_en=spec.name,
                    price_cents=spec.price_cents,
                    currency="EUR",
                    metadata_json={"plan": spec.plan, "valid_days": spec.valid_days, "ai_credits": spec.ai_credits, "seed_tag": SEED_TAG},
                    active=True,
                )
            )
            stats["created"] += 1
            continue

        changed = False
        if product.type != "program":
            product.type = "program"
            changed = True
        if not product.name_de:
            product.name_de = spec.name
            changed = True
        if not product.name_en:
            product.name_en = spec.name
            changed = True
        if not product.currency:
            product.currency = "EUR"
            changed = True
        if product.metadata_json is None:
            product.metadata_json = {}
            changed = True

        metadata = dict(product.metadata_json or {})
        if metadata.get("plan") != spec.plan:
            metadata["plan"] = spec.plan
            changed = True
        if int(metadata.get("valid_days", 0) or 0) != spec.valid_days:
            metadata["valid_days"] = spec.valid_days
            changed = True
        if int(metadata.get("ai_credits", -1) or 0) != spec.ai_credits:
            metadata["ai_credits"] = spec.ai_credits
            changed = True
        if not metadata.get("seed_tag"):
            metadata["seed_tag"] = SEED_TAG
            changed = True
        if changed:
            product.metadata_json = metadata

        if changed:
            stats["updated"] += 1
        else:
            stats["skipped"] += 1

    for extra in DEFAULT_EXTRA_PRODUCTS:
        exists = db.query(Product).filter(Product.code == str(extra["code"])).one_or_none()
        if exists:
            continue
        db.add(Product(**extra))

    return stats