"""Grammar-based workout notation parser (Lark, LALR).

Prototype replacement for the regex cascade in ``_parse_simple_format``.
Each non-empty line is parsed independently against a small grammar that
describes the user's shorthand:

    Bench press 4x8 80kg                       name + sets
    Squat 3x5 @100kg RPE 8                     with RPE
    4x8 @80 bench press r2'                    sets, weight, then name (terse)
    5x20 leg raises                            sets then name
    3@100, 1@105, 1@110 squat r2'              descending singles
    bench press : 6@80kg, 4@100kg, 2x1@110kg   colon form
    horizontal pull 2x8@100kg r1'30            mixed form
    (10,6,5) squat @100                        explicit rep list
    (dips) 3x amrap                            finisher
    5x(8-10 pull ups @20kg, 15 dips) r2'       circuit
    EMOM 20' (odd: 10 pull ups, even: 10 chin ups)
    r1'30                                      standalone rest -> previous exercise

Output shape is identical to ``_parse_simple_format`` (list of exercise dicts).
"""

from __future__ import annotations

import re
from typing import Any

from lark import Lark, Token, Transformer, UnexpectedInput

GRAMMAR = r"""
start: rest_line | circuit | emom | finisher | rep_list | prefix_form | name_form

rest_line: REST

circuit: CIRCUIT_HEAD item ("," item)* ")" weight? REST? RPE?
item: REPS? name weight?

emom: EMOM_HEAD "(" emom_item ("," emom_item)* ")"
emom_item: WORD ":" REPS name

finisher: "(" name ")" setspec weight? REST? RPE?

rep_list: "(" REPS ("," REPS)+ ")" name weight? REST? RPE?

prefix_form: setspec ("," setspec)* name weight? REST? RPE?

name_form: name ":"? setspec ("," setspec)* RPE? REST? RPE?

setspec: (SETSXREPS | REPS) weight?
weight: WEIGHT | BAREWEIGHT
name: WORD+

CIRCUIT_HEAD.6: /\d+\s*x\s*(\d+e?)?\(/i
EMOM_HEAD.6:    /emom\s*\d+'?/i
REST.5:         /r\s?\d+'\d{0,2}/i
RPE.5:          /rpe\s*\d+(\.\d+)?/i
SETSXREPS.4:    /\d+\s*x\s*(\d+(-\d+)?e?|f\b|failure|amrap)/i
BAREWEIGHT.4:   /\d+(\.\d+)?\s*kg/i
WEIGHT.3:       /@\s*\d+(\.\d+)?\s*(kg)?/i
REPS.1:         /\d+(-\d+)?e?/
WORD.0:         /[a-zA-Z][a-zA-Z'\-]*/

%import common.WS
%ignore WS
"""

_PARSER = Lark(GRAMMAR, parser="lalr", lexer="contextual")

_NUM = re.compile(r"\d+(?:\.\d+)?")


# --------------------------------------------------------------------------- #
# Token helpers
# --------------------------------------------------------------------------- #
def _weight_value(tok: Token | None) -> float | None:
    if tok is None:
        return None
    m = _NUM.search(str(tok))
    return float(m.group()) if m else None


def _rest_seconds(tok: Token | None) -> int | None:
    if tok is None:
        return None
    m = re.match(r"r\s?(\d+)'(\d{0,2})", str(tok), re.I)
    if not m:
        return None
    return int(m.group(1)) * 60 + (int(m.group(2)) if m.group(2) else 0)


def _rpe_value(tok: Token | None) -> float | None:
    if tok is None:
        return None
    m = _NUM.search(str(tok))
    return float(m.group()) if m else None


def _reps_spec(text: str) -> dict[str, Any]:
    """Parse '8', '8-10', '15e', 'F', 'amrap' into reps/target/flags."""
    t = text.strip().lower()
    if t in {"f", "failure", "amrap"}:
        return {"reps": None, "target": None, "failure": True, "unilateral": False}
    unilateral = t.endswith("e")
    if unilateral:
        t = t[:-1]
    lo = int(t.split("-")[0])
    return {"reps": lo, "target": t, "failure": False, "unilateral": unilateral}


def _setspec_value(tok: Token) -> tuple[int, dict[str, Any]]:
    """SETSXREPS '4x8-10' -> (4, spec); REPS '6' -> (1, spec)."""
    s = str(tok)
    if tok.type == "SETSXREPS":
        n, rest = re.split(r"\s*x\s*", s, maxsplit=1, flags=re.I)
        return int(n), _reps_spec(rest)
    return 1, _reps_spec(s)


def _make_sets(
    count: int,
    spec: dict[str, Any],
    weight: float | None,
    rest_sec: int | None,
    rpe: float | None,
    start: int = 1,
) -> list[dict[str, Any]]:
    return [
        {
            "set_number": start + i,
            "reps": spec["reps"],
            "weight_kg": weight,
            "rpe": rpe,
            "is_warmup": False,
            "is_failure": spec["failure"],
            "rest_sec": rest_sec,
        }
        for i in range(count)
    ]


def _exercise(
    name: str,
    sets: list[dict[str, Any]],
    target_reps: str | None,
    notes: str | None = None,
) -> dict[str, Any]:
    return {
        "name": name,
        "exercise_id": None,  # matched later by the caller (catalog lookup)
        "sets": sets,
        "notes": notes,
        "target_reps": target_reps,
    }


def _split_children(children: list[Any]) -> dict[str, Any]:
    """Bucket a rule's children by kind (tokens by type, trees by data)."""
    out: dict[str, Any] = {"setspecs": [], "items": [], "reps": []}
    for c in children:
        if isinstance(c, Token):
            if c.type == "REPS":
                out["reps"].append(c)
            else:
                out[c.type] = c
        elif isinstance(c, dict):
            kind = c.pop("_kind")
            if kind in ("setspec", "item"):
                out[kind + "s"].append(c)
            else:
                out[kind] = c
    return out


# --------------------------------------------------------------------------- #
# Transformer: parse tree -> list[dict] exercises (or {"rest": seconds})
# --------------------------------------------------------------------------- #
class _ToExercises(Transformer):
    def name(self, words: list[Token]) -> dict[str, Any]:
        return {"_kind": "name", "value": " ".join(str(w) for w in words)}

    def weight(self, toks: list[Token]) -> dict[str, Any]:
        return {"_kind": "weight", "value": _weight_value(toks[0])}

    def setspec(self, children: list[Any]) -> dict[str, Any]:
        count, spec = _setspec_value(children[0])
        weight = children[1]["value"] if len(children) > 1 else None
        return {"_kind": "setspec", "count": count, "spec": spec, "weight": weight}

    def item(self, children: list[Any]) -> dict[str, Any]:
        b = _split_children(children)
        return {
            "_kind": "item",
            "spec": _reps_spec(str(b["reps"][0])) if b["reps"] else None,
            "name": b["name"]["value"],
            "weight": b.get("weight", {}).get("value"),
        }

    def emom_item(self, children: list[Any]) -> dict[str, Any]:
        b = _split_children(children)
        return {
            "_kind": "item",
            "spec": _reps_spec(str(b["reps"][0])),
            "name": b["name"]["value"],
            "weight": None,
        }

    # ---- line forms -------------------------------------------------------
    def rest_line(self, toks: list[Token]) -> dict[str, Any]:
        return {"rest": _rest_seconds(toks[0])}

    def _from_setspecs(self, b: dict[str, Any], notes: str | None = None) -> list[dict]:
        name = b["name"]["value"]
        fallback_weight = b.get("weight", {}).get("value")
        rest = _rest_seconds(b.get("REST"))
        rpe = _rpe_value(b.get("RPE"))
        sets: list[dict[str, Any]] = []
        for ss in b["setspecs"]:
            w = ss["weight"] if ss["weight"] is not None else fallback_weight
            sets += _make_sets(
                ss["count"], ss["spec"], w, rest, rpe, start=len(sets) + 1
            )
        targets = {ss["spec"]["target"] for ss in b["setspecs"]}
        target = targets.pop() if len(targets) == 1 else None
        unilateral = any(ss["spec"]["unilateral"] for ss in b["setspecs"])
        if unilateral:
            notes = "each side" if notes is None else f"{notes}, each side"
        return [_exercise(name, sets, target, notes)]

    def prefix_form(self, children: list[Any]) -> list[dict]:
        return self._from_setspecs(_split_children(children))

    def name_form(self, children: list[Any]) -> list[dict]:
        return self._from_setspecs(_split_children(children))

    def finisher(self, children: list[Any]) -> list[dict]:
        return self._from_setspecs(_split_children(children), notes="finisher")

    def rep_list(self, children: list[Any]) -> list[dict]:
        b = _split_children(children)
        weight = b.get("weight", {}).get("value")
        rest = _rest_seconds(b.get("REST"))
        rpe = _rpe_value(b.get("RPE"))
        sets: list[dict[str, Any]] = []
        for tok in b["reps"]:
            sets += _make_sets(
                1, _reps_spec(str(tok)), weight, rest, rpe, start=len(sets) + 1
            )
        target = "/".join(str(t) for t in b["reps"])
        return [_exercise(b["name"]["value"], sets, target)]

    def circuit(self, children: list[Any]) -> list[dict]:
        b = _split_children(children)
        head = str(b["CIRCUIT_HEAD"])
        m = re.match(r"(\d+)\s*x\s*(\d+e?)?\(", head, re.I)
        assert m
        rounds = int(m.group(1))
        default_spec = _reps_spec(m.group(2)) if m.group(2) else None
        global_weight = b.get("weight", {}).get("value")
        rest = _rest_seconds(b.get("REST"))
        rpe = _rpe_value(b.get("RPE"))
        exercises = []
        for it in b["items"]:
            spec = it["spec"] or default_spec
            if spec is None:  # "5x(pull ups, dips)" without any rep count
                spec = {
                    "reps": None,
                    "target": None,
                    "failure": False,
                    "unilateral": False,
                }
            w = it["weight"] if it["weight"] is not None else global_weight
            notes = "each side" if spec and spec["unilateral"] else None
            exercises.append(
                _exercise(
                    it["name"],
                    _make_sets(rounds, spec, w, rest, rpe),
                    spec["target"],
                    notes,
                )
            )
        return exercises

    def emom(self, children: list[Any]) -> list[dict]:
        b = _split_children(children)
        minutes = int(_NUM.search(str(b["EMOM_HEAD"])).group())  # type: ignore[union-attr]
        n_sets = max(minutes // 2, 1)
        return [
            _exercise(
                it["name"],
                _make_sets(n_sets, it["spec"], None, 60, None),
                it["spec"]["target"],
                notes=f"EMOM {minutes}'",
            )
            for it in b["items"]
        ]

    def start(self, children: list[Any]) -> Any:
        return children[0]


_TRANSFORM = _ToExercises()


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #
def parse_line(line: str) -> list[dict] | dict | None:
    """Parse one line. Returns exercises, {"rest": sec}, or None if unparseable."""
    try:
        tree = _PARSER.parse(line.strip())
    except UnexpectedInput:
        return None
    return _TRANSFORM.transform(tree)


def parse_workout_grammar(text: str) -> list[dict] | None:
    """Parse a whole workout text. Same contract as ``_parse_simple_format``.

    Unparseable lines are skipped (the caller may fall back to the LLM for them);
    a standalone rest line applies its rest to every set of the previous line's
    exercises. Returns None when no exercise could be parsed.
    """
    exercises: list[dict] = []
    last_line_exercises: list[dict] = []
    for raw in text.strip().split("\n"):
        line = raw.strip()
        if not line:
            continue
        result = parse_line(line)
        if result is None:
            continue
        if isinstance(result, dict):  # standalone rest
            for ex in last_line_exercises:
                for s in ex["sets"]:
                    s["rest_sec"] = result["rest"]
            continue
        exercises.extend(result)
        last_line_exercises = result
    return exercises or None


def unparsed_lines(text: str) -> list[str]:
    """Lines the grammar rejects (candidates for the LLM fallback)."""
    return [
        ln.strip()
        for ln in text.strip().split("\n")
        if ln.strip() and parse_line(ln) is None
    ]
