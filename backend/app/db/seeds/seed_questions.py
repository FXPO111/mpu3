from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.models import Question, Topic


DEFAULT_TOPICS: list[dict[str, str]] = [
    {"slug": "alcohol", "title_de": "Alkohol", "title_en": "Alcohol"},
    {"slug": "drugs", "title_de": "Drogen", "title_en": "Drugs"},
    {"slug": "points", "title_de": "Punkte / Verkehrsverstöße", "title_en": "Points / traffic violations"},
    {"slug": "incident", "title_de": "Vorfall / Kontrolle", "title_en": "Incident / police stop"},
]

DEFAULT_QUESTIONS: list[dict[str, Any]] = [
    {
        "topic": "alcohol",
        "level": 1,
        "intent": "timeline",
        "tags": ["facts", "timeline"],
        "question_de": "Wann und in welchem Kontext haben Sie zuletzt Alkohol konsumiert? Bitte nennen Sie Datum/Zeitraum und Menge.",
        "question_en": "When and in what context did you last drink alcohol? Please give date/timeframe and amount.",
    },
    {
        "topic": "alcohol",
        "level": 2,
        "intent": "responsibility",
        "tags": ["responsibility", "mpu"],
        "question_de": "Welche konkreten Fehler haben Sie damals gemacht, und was wäre heute anders?",
        "question_en": "What concrete mistakes did you make back then, and what would you do differently today?",
    },
    {
        "topic": "alcohol",
        "level": 2,
        "intent": "change_plan",
        "tags": ["plan", "prevention"],
        "question_de": "Welche Regeln haben Sie heute zum Thema Alkohol (z.B. 0.0, Anlässe, Grenzen) und wie setzen Sie die um?",
        "question_en": "What rules do you follow today regarding alcohol (e.g., 0.0, occasions, limits), and how do you enforce them?",
    },
    {
        "topic": "drugs",
        "level": 1,
        "intent": "facts",
        "tags": ["facts", "use"],
        "question_de": "Welche Substanzen haben Sie konsumiert, wie häufig und wann war der letzte Konsum?",
        "question_en": "Which substances did you use, how often, and when was the last use?",
    },
    {
        "topic": "drugs",
        "level": 2,
        "intent": "insight",
        "tags": ["triggers", "motives"],
        "question_de": "Welche Auslöser haben zum Konsum geführt (Stress, Umfeld, Emotionen) und wie erkennen Sie diese heute frühzeitig?",
        "question_en": "Which triggers led to your use (stress, environment, emotions) and how do you recognize them early today?",
    },
    {
        "topic": "drugs",
        "level": 3,
        "intent": "prevention",
        "tags": ["relapse_prevention", "strategy"],
        "question_de": "Wie sieht Ihr Rückfallpräventionsplan konkret aus (Warnsignale, Maßnahmen, Ansprechpartner)?",
        "question_en": "What does your relapse prevention plan look like (warning signs, actions, contacts)?",
    },
    {
        "topic": "points",
        "level": 1,
        "intent": "pattern",
        "tags": ["pattern", "driving"],
        "question_de": "Welche wiederkehrenden Muster haben zu den Verkehrsverstößen geführt (Zeitdruck, Aggression, Unachtsamkeit)?",
        "question_en": "What recurring patterns led to the traffic violations (time pressure, aggression, inattention)?",
    },
    {
        "topic": "points",
        "level": 2,
        "intent": "behavior_change",
        "tags": ["behavior", "habits"],
        "question_de": "Welche konkreten neuen Gewohnheiten haben Sie im Straßenverkehr eingeführt und seit wann?",
        "question_en": "Which concrete new driving habits have you introduced, and since when?",
    },
    {
        "topic": "incident",
        "level": 1,
        "intent": "incident_facts",
        "tags": ["incident", "facts"],
        "question_de": "Beschreiben Sie den Vorfall sachlich: Was ist passiert, wo, wann, wer war beteiligt?",
        "question_en": "Describe the incident factually: what happened, where, when, who was involved?",
    },
    {
        "topic": "incident",
        "level": 2,
        "intent": "learning",
        "tags": ["learning", "responsibility"],
        "question_de": "Was haben Sie aus dem Vorfall gelernt und welche konkreten Maßnahmen verhindern eine Wiederholung?",
        "question_en": "What did you learn from the incident, and which concrete measures prevent it from happening again?",
    },
]


def seed_topics_and_questions(db: Session, *, only_missing: bool = True) -> dict[str, int]:
    created_topics = 0
    created_questions = 0
    skipped_questions = 0

    topic_by_slug: dict[str, Topic] = {}
    for t in DEFAULT_TOPICS:
        slug = t["slug"]
        existing = db.scalar(select(Topic).where(Topic.slug == slug))
        if existing:
            topic_by_slug[slug] = existing
            if only_missing:
                changed = False
                if not (existing.title_de or "").strip():
                    existing.title_de = t["title_de"]
                    changed = True
                if not (existing.title_en or "").strip():
                    existing.title_en = t["title_en"]
                    changed = True
                if changed:
                    db.flush()
            continue

        topic = Topic(slug=slug, title_de=t["title_de"], title_en=t["title_en"])
        db.add(topic)
        db.flush()
        topic_by_slug[slug] = topic
        created_topics += 1

    for q in DEFAULT_QUESTIONS:
        slug = q["topic"]
        topic = topic_by_slug.get(slug)
        if not topic:
            continue

        exists = db.scalar(
            select(Question.id).where(
                Question.topic_id == topic.id,
                Question.question_de == q["question_de"],
            )
        )
        if exists:
            skipped_questions += 1
            continue

        question = Question(
            topic_id=topic.id,
            level=int(q["level"]),
            question_de=q["question_de"],
            question_en=q["question_en"],
            intent=str(q["intent"]),
            tags=list(q.get("tags") or []),
        )
        db.add(question)
        created_questions += 1

    db.flush()
    return {
        "created_topics": created_topics,
        "created_questions": created_questions,
        "skipped_questions": skipped_questions,
    }