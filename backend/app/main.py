from pathlib import Path

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.schemas import HealthResponse, PredictionResponse, StudentData
from app.services.history_store import HistoryStore
from app.services.stress_model import model_status, predict_stress
from app.services.user_store import UserStore

app = FastAPI(
    title="MindTrack Stress Detection API",
    description="RESTful API untuk deteksi tingkat stres mahasiswa berbasis model deep learning.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

history_store = HistoryStore()
user_store = UserStore()
FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"


# ── Auth schemas ────────────────────────────────────────────────────────────

class AuthPayload(BaseModel):
    username: str
    password: str

class AuthResponse(BaseModel):
    username: str
    token: str


# ── Auth endpoints ──────────────────────────────────────────────────────────

@app.post("/api/auth/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
def register(payload: AuthPayload):
    username = payload.username.strip()
    password = payload.password

    if not username or not password:
        raise HTTPException(status_code=400, detail="Username dan password wajib diisi.")
    if len(username) < 3:
        raise HTTPException(status_code=400, detail="Username minimal 3 karakter.")
    if len(password) < 6:
        raise HTTPException(status_code=400, detail="Password minimal 6 karakter.")
    if user_store.username_exists(username):
        raise HTTPException(status_code=409, detail="Username sudah digunakan.")

    return user_store.register(username, password)


@app.post("/api/auth/login", response_model=AuthResponse)
def login(payload: AuthPayload):
    username = payload.username.strip()
    password = payload.password

    if not username or not password:
        raise HTTPException(status_code=400, detail="Username dan password wajib diisi.")

    result = user_store.login(username, password)
    if result is None:
        raise HTTPException(status_code=401, detail="Username atau password salah.")

    return result


# ── Health ──────────────────────────────────────────────────────────────────

@app.get("/api/health", response_model=HealthResponse)
def health_check():
    status_data = model_status()
    return HealthResponse(
        status="ok",
        service="mindtrack-api",
        model_loaded=status_data["loaded"],
        model_available=status_data["available"],
        model_mode=status_data["mode"],
        n_models=status_data["n_models"],
        version="1.0.0",
        detail=status_data["detail"],
    )


# ── Predictions ─────────────────────────────────────────────────────────────

@app.post(
    "/api/predictions",
    response_model=PredictionResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_prediction(payload: StudentData):
    try:
        prediction = predict_stress(payload)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return history_store.add(prediction)


@app.get("/api/predictions", response_model=list[PredictionResponse])
def list_predictions():
    return history_store.all()


@app.get("/api/predictions/{prediction_id}", response_model=PredictionResponse)
def get_prediction(prediction_id: str):
    prediction = history_store.get(prediction_id)
    if prediction is None:
        raise HTTPException(status_code=404, detail="Prediction not found")
    return prediction


@app.delete("/api/predictions/{prediction_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_prediction(prediction_id: str):
    deleted = history_store.delete(prediction_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Prediction not found")
    return None


# ── Frontend static serving ─────────────────────────────────────────────────

if FRONTEND_DIST.exists():
    app.mount(
        "/assets",
        StaticFiles(directory=FRONTEND_DIST / "assets"),
        name="frontend-assets",
    )


@app.get("/", include_in_schema=False)
def serve_frontend_index():
    index_path = FRONTEND_DIST / "index.html"
    if not index_path.exists():
        raise HTTPException(status_code=404, detail="Frontend build not found. Run `npm run build` in frontend.")
    return FileResponse(index_path)


@app.get("/{path:path}", include_in_schema=False)
def serve_frontend_app(path: str):
    if path.startswith(("api/", "docs", "openapi.json", "redoc")):
        raise HTTPException(status_code=404, detail="Not found")

    requested_file = FRONTEND_DIST / path
    if requested_file.exists() and requested_file.is_file():
        return FileResponse(requested_file)

    index_path = FRONTEND_DIST / "index.html"
    if not index_path.exists():
        raise HTTPException(status_code=404, detail="Frontend build not found. Run `npm run build` in frontend.")
    return FileResponse(index_path)