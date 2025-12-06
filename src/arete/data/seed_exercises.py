"""
Seed the exercises catalog into DuckDB and ChromaDB.
"""

import json
from datetime import datetime
from pathlib import Path

# Add parent to path for imports
import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from arete.data.exercises_catalog import EXERCISES_CATALOG, MUSCLES
from arete.dataio.db import connect


def create_exercises_table():
    """Create the exercises table in DuckDB."""
    conn = connect()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS exercises (
            id VARCHAR PRIMARY KEY,
            name VARCHAR NOT NULL,
            name_fr VARCHAR,
            category VARCHAR NOT NULL,
            equipment JSON,
            primary_muscles JSON NOT NULL,
            secondary_muscles JSON,
            movement_pattern VARCHAR,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS muscles (
            id VARCHAR PRIMARY KEY,
            name VARCHAR NOT NULL
        )
    """)

    conn.commit()
    conn.close()
    print("✓ Tables created")


def seed_muscles():
    """Seed muscles into DuckDB."""
    conn = connect()

    # Clear existing
    conn.execute("DELETE FROM muscles")

    # Insert all muscles
    for muscle_id, muscle_name in MUSCLES.items():
        conn.execute("INSERT INTO muscles (id, name) VALUES (?, ?)", [muscle_id, muscle_name])

    conn.commit()
    conn.close()
    print(f"✓ Seeded {len(MUSCLES)} muscles")


def seed_exercises():
    """Seed exercises into DuckDB."""
    conn = connect()

    # Clear existing
    conn.execute("DELETE FROM exercises")

    # Insert all exercises
    for ex in EXERCISES_CATALOG:
        conn.execute(
            """
            INSERT INTO exercises (
                id, name, name_fr, category, equipment,
                primary_muscles, secondary_muscles, movement_pattern
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
            [
                ex["id"],
                ex["name"],
                ex.get("name_fr"),
                ex["category"],
                json.dumps(ex.get("equipment", [])),
                json.dumps(ex["primary_muscles"]),
                json.dumps(ex.get("secondary_muscles", [])),
                ex.get("movement_pattern"),
            ],
        )

    conn.commit()
    conn.close()
    print(f"✓ Seeded {len(EXERCISES_CATALOG)} exercises")


def seed_exercises_to_chromadb():
    """Add exercise knowledge to ChromaDB for RAG."""
    try:
        from arete.rag.knowledge_base import KnowledgeBase, Document
    except ImportError:
        print("⚠ ChromaDB not available, skipping RAG seeding")
        return

    kb = KnowledgeBase()

    documents = []

    for ex in EXERCISES_CATALOG:
        # Create a rich description for RAG
        primary = ", ".join(ex["primary_muscles"])
        secondary = ", ".join(ex.get("secondary_muscles", []))
        equipment = ", ".join(ex.get("equipment", []))

        content = f"""Exercise: {ex["name"]} ({ex.get("name_fr", "")})
Category: {ex["category"]}
Movement Pattern: {ex.get("movement_pattern", "compound")}
Equipment: {equipment}
Primary Muscles: {primary}
Secondary Muscles: {secondary}

This exercise primarily targets the {primary}. {f"Secondary muscles involved include {secondary}." if secondary else ""}
Equipment needed: {equipment if equipment else "bodyweight only"}.
Movement type: {ex.get("movement_pattern", "compound")}."""

        doc = Document(
            id=f"ex_{ex['id']}",
            content=content,
            metadata={
                "type": "exercise",
                "exercise_id": ex["id"],
                "category": ex["category"],
                "primary_muscles": primary,
                "movement_pattern": ex.get("movement_pattern", ""),
            },
        )
        documents.append(doc)

    # Add to ChromaDB exercises collection
    count = kb.add_documents(
        collection="exercises",
        documents=documents,
    )

    print(f"✓ Added {count} exercises to ChromaDB RAG")


def seed_muscle_groups_to_chromadb():
    """Add muscle group knowledge to ChromaDB for RAG."""
    try:
        from arete.rag.knowledge_base import KnowledgeBase, Document
    except ImportError:
        print("⚠ ChromaDB not available, skipping muscle group seeding")
        return

    kb = KnowledgeBase()

    # Group muscles by body region
    muscle_groups = {
        "upper_push": {
            "muscles": ["chest", "front_delts", "side_delts", "triceps"],
            "description": "Upper body pushing muscles including chest (pectorals), shoulders (anterior and lateral deltoids), and triceps. These muscles are trained with exercises like bench press, shoulder press, dips, and lateral raises.",
        },
        "upper_pull": {
            "muscles": ["lats", "rhomboids", "rear_delts", "traps", "biceps", "forearms"],
            "description": "Upper body pulling muscles including back (latissimus dorsi, rhomboids), rear shoulders (posterior deltoids), traps, biceps, and forearms. These muscles are trained with exercises like pull-ups, rows, and curls.",
        },
        "core": {
            "muscles": ["abs", "obliques", "lower_back"],
            "description": "Core muscles including rectus abdominis, obliques, and erector spinae. These muscles provide stability and are trained with exercises like crunches, leg raises, and planks.",
        },
        "lower_body": {
            "muscles": ["quads", "hamstrings", "glutes", "calves", "hip_flexors", "adductors"],
            "description": "Lower body muscles including quadriceps, hamstrings, glutes, calves, hip flexors, and adductors. These muscles are trained with squats, deadlifts, lunges, and calf raises.",
        },
    }

    documents = []

    for group_id, group_data in muscle_groups.items():
        muscles_str = ", ".join([MUSCLES.get(m, m) for m in group_data["muscles"]])
        content = f"""Muscle Group: {group_id.replace("_", " ").title()}
Muscles: {muscles_str}

{group_data["description"]}

For balanced training, ensure you train both pushing and pulling movements equally. 
Monitor volume per muscle group to prevent overtraining and ensure adequate recovery."""

        doc = Document(
            id=f"muscle_group_{group_id}",
            content=content,
            metadata={
                "type": "muscle_group",
                "group_id": group_id,
                "muscles": muscles_str,
            },
        )
        documents.append(doc)

    count = kb.add_documents(
        collection="exercises",
        documents=documents,
    )

    print(f"✓ Added {count} muscle groups to ChromaDB RAG")


def main():
    """Run all seeding operations."""
    print("🌱 Seeding exercises and muscles...")
    print()

    # DuckDB
    create_exercises_table()
    seed_muscles()
    seed_exercises()

    # ChromaDB (RAG)
    print()
    print("📚 Seeding RAG knowledge base...")
    seed_exercises_to_chromadb()
    seed_muscle_groups_to_chromadb()

    print()
    print("✅ Done!")


if __name__ == "__main__":
    main()
