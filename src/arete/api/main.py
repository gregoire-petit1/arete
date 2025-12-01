from fastapi import FastAPI
from pydantic import BaseModel
from dotenv import load_dotenv
from arete.dataio.db import connect
from arete.api.routes import router as api_router

load_dotenv()
app = FastAPI(title="Arete API", version="0.1.0")


class SessionRequest(BaseModel):
    date: str
    objectif: str
    dispo_min: int
    fatigue: int
    rpe_moy7j: float | None = None


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/plan/jour")
def plan_jour(req: SessionRequest):
    return {"seance": "EF 45' + 6x100m", "cible": {"fc": "70-75% FCM", "allure": "Z2"}}


@app.get("/log/recent")
def log_recent(n: int = 5):
    if n < 1 or n > 100:
        n = 5  # Default to safe value
    con = connect(read_only=True)
    try:
        df = con.execute(
            """
            SELECT date, sport, type, duree_min, distance_km, rpe
            FROM app.training_log
            ORDER BY date DESC
            LIMIT ?
            """,
            [n],
        ).fetch_df()
        return {"rows": df.to_dict(orient="records")}
    finally:
        con.close()


# Routes CRUD (sessions/user/objectives/records)
app.include_router(api_router)
