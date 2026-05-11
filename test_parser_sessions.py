#!/usr/bin/env python
"""Test the workout parser with real user sessions."""

from arete.llm.workout_parser import _parse_simple_format

SESSIONS = {
    "05/12/25": """5x(8-10 weighted pull ups @20kg, 15 db lateral raises @20) r2'
5x(10 pulls ups, 15 db lateral raises @20) r1'30
5x(10 chin ups, 15 dips) r1'30""",
    "07/12/25": """4x(15 strict bb swing @13kg, 10 pull ups) r1'30
horizontal pull 2x8@100kg r1'30
4x(12 pec fly @20, 10 chin ups) r1'30""",
    "07/12/25 - bench (descending)": """6@80, 4@100, 2@105 bench press r2'30""",
    "09/12/25": """10x(10 pull ups, 15 dips) r2'
10x(10 chin ups, 15 db lateral raises @20kg) r2'
5x20 leg raises""",
    "11/12/25": """3@100, 1@105, 1@110, 1@115, 1@120 heavy bench press r2'
3x5 pause bench @80 r2'
5x(10 kb RDL @32kg, 15e db rows @22.5kg) r2'
5x(10 wide pull ups, 15 dips) r2'""",
    "12/12/25 - EMOM": """EMOM 20' (odd: 10 pull ups, even: 10 chin ups)""",
    "15/12/25 - leg raises": """5x20 leg raises""",
}


def test_session(date_str: str, text: str):
    print(f"\n{'=' * 60}")
    print(f"SESSION {date_str}")
    print(f"{'=' * 60}")
    print(f"Input:\n{text}\n")

    result = _parse_simple_format(text)

    if not result:
        print("❌ NOT PARSED by regex (would need LLM)")
        return

    print(f"✅ PARSED: {len(result)} exercises")
    for ex in result:
        sets = ex.get("sets", [])
        ex_id = ex.get("exercise_id")
        target = ex.get("target_reps")
        notes = ex.get("notes")

        matched = "✓" if ex_id else "?"
        print(f"\n  [{matched}] {ex['name']}")
        print(f"      exercise_id: {ex_id}")
        print(f"      target_reps: {target}")
        print(f"      sets: {len(sets)}")
        if notes:
            print(f"      notes: {notes}")

        if sets:
            # Show first and last set if different weights
            s = sets[0]
            rest = s.get("rest_sec")
            rest_str = f"{rest // 60}'{rest % 60:02d}" if rest else "None"
            print(
                f"      → set1: reps={s.get('reps')}, weight={s.get('weight_kg')}kg, rest={rest_str}"
            )

            if len(sets) > 1:
                last = sets[-1]
                if last.get("weight_kg") != s.get("weight_kg") or last.get("reps") != s.get("reps"):
                    print(
                        f"      → set{len(sets)}: reps={last.get('reps')}, weight={last.get('weight_kg')}kg"
                    )


if __name__ == "__main__":
    for date_str, text in SESSIONS.items():
        test_session(date_str, text)

    print("\n" + "=" * 60)
    print("FORMATS SUPPORTÉS:")
    print("=" * 60)
    print("""
✅ Circuits: 5x(8 pull ups @20kg, 10 dips) r2'
✅ Traditional: Bench press 4x8 @80kg RPE 8
✅ Reversed: 5x20 leg raises
✅ Descending: 3@100, 1@105, 1@110 bench press r2'
✅ EMOM: EMOM 20' (odd: 10 pull ups, even: 10 chin ups)
✅ Range reps: 8-10
✅ Failure: xF, AMRAP, failure
✅ Rest time: r2', r1'30
✅ Unilateral: 15e (each side)
""")
