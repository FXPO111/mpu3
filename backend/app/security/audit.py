from sqlalchemy.orm import Session

from app.domain.models import AuditLog


def log_action(db: Session, action: str, entity_type: str, entity_id: str, actor_user_id=None, payload=None):
    db.add(
        AuditLog(
            actor_user_id=actor_user_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            payload_json=payload or {},
        )
    )