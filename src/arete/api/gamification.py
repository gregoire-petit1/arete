"""HTTP boundary for the opt-in athlete RPG."""

import duckdb
from fastapi import APIRouter, HTTPException, Query

from arete.services import gamification as game

router = APIRouter(tags=["gamification"])


def _call(operation, *args):
    try:
        return operation(*args)
    except game.GameError as exc:
        raise HTTPException(409, str(exc)) from None
    except duckdb.TransactionException:
        raise HTTPException(
            409,
            "Une autre écriture est en cours. Actualise pour vérifier son résultat.",
        ) from None


@router.get("/settings/gamification")
def preference():
    return game.preference()


@router.patch("/settings/gamification")
def set_preference(body: game.Preference):
    return _call(game.set_preference, body)


@router.get("/gamification")
def snapshot(offset: int = Query(0, ge=0, le=100000)):
    return game.snapshot(offset)


@router.post("/gamification/sync")
def sync():
    return _call(game.sync)


@router.post("/gamification/purchases")
def purchase(body: game.Purchase):
    return _call(game.purchase, body)


@router.put("/gamification/equipment")
def equip(body: game.Equip):
    return _call(game.equip, body)


@router.put("/gamification/appearance")
def appearance(body: game.Appearance):
    return _call(game.appearance, body)
