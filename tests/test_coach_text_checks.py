"""The text checks themselves, on written examples."""

from coach_text_checks import briefing_problems, feedback_problems

GOOD = (
    "Sur 28 jours ta charge reste stable (ACWR 1,08), mais ta fraîcheur à -20 "
    "sur 42 jours dit que la fatigue s'installe. Aujourd'hui, fais ta séance de "
    "force en gardant 2 répétitions en réserve."
)


def test_a_good_briefing_passes():
    assert briefing_problems(GOOD) == []


def test_reasoning_leaked_in_english_is_caught():
    leaked = "Let me analyze the user's request carefully. " + GOOD
    assert "leaked reasoning in English" in briefing_problems(leaked)


def test_a_list_and_a_missing_action_are_caught():
    problems = briefing_problems("- Charge 1,08 sur 28 jours\n- Fraîcheur -20 pour toi")
    assert "a list" in problems and "no action for today" in problems


def test_a_safety_classifier_reply_is_caught():
    # What openrouter/free once returned for a briefing.
    assert briefing_problems("User Safety: safe")


def test_a_short_feedback_passes():
    assert (
        feedback_problems("Belle sortie de 20 km, tu as bien géré la descente.") == []
    )
