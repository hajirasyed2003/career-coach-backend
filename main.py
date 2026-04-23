# main.py — updated with lifespan and RAG integration
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from groq import RateLimitError, APIError
from tenacity import RetryError

import uuid
from datetime import datetime, timezone
from models.schemas import (
    CareerRequest, CareerResponse, HealthResponse,
    AnalysisHistoryItem, AnalysisHistoryResponse,
    SkillProgressUpdate, SkillProgressResponse,
    DashboardResponse,
)

from services.crew_service import run_crew
from services.data_fetcher import fetch_job_postings, fetch_salary_data
from services.rag_service import seed_courses  # NEW
from services.rag_service import find_courses 

from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from models.database import get_db
from models.db_models import User
from models.schemas import (
    RegisterRequest, LoginRequest, TokenResponse,
    UserResponse, CareerRequest, CareerResponse, HealthResponse,
    AnalysisHistoryItem, AnalysisHistoryResponse,
    SkillProgressUpdate, SkillProgressResponse, DashboardResponse,
)
from services.auth_service import create_access_token, decode_token
from services.user_service import (
    create_user, authenticate_user, get_user_by_id,
    save_analysis, get_user_analyses, upsert_skill_progress,
)

# OAuth2PasswordBearer tells FastAPI where to find the token
# The tokenUrl is used by Swagger UI to show the "Authorize" button
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    """
    FastAPI dependency injected into every protected endpoint.
    Extracts user_id from JWT, looks up the user in DB, returns the User object.
    Raises 401 if token is invalid or user doesn't exist.

    Usage in endpoint:
        async def my_endpoint(current_user: User = Depends(get_current_user)):
    """
    user_id = decode_token(token)
    user = get_user_by_id(db, user_id)

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Runs on server startup (before accepting requests) and shutdown.
    The code before `yield` runs at startup.
    The code after `yield` runs at shutdown.
    """
    # ── Startup ──────────────────────────────────────────────────────────────
    logger.info("Server starting up — seeding ChromaDB...")
    try:
        count = seed_courses()  # skips if already seeded; fast on subsequent starts
        logger.info(f"ChromaDB ready with {count} courses")
    except Exception as e:
        # Don't crash the server if seeding fails — log and continue
        # The rag_service will return a graceful fallback message if queried
        logger.error(f"ChromaDB seeding failed on startup: {e}")

    yield  # Server is now running and accepting requests

    # ── Shutdown ─────────────────────────────────────────────────────────────
    logger.info("Server shutting down")


app = FastAPI(
    title="AI Career Coach API",
    description="Multi-agent career coaching system powered by CrewAI and Groq",
    version="1.0.0",
    lifespan=lifespan,  # attach the lifespan handler
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", response_model=HealthResponse, tags=["System"])
async def health_check():
    return HealthResponse(status="ok", message="Career Coach API is running")

@app.get("/health/rag", tags=["System"])
async def rag_health():
    """
    Tests that ChromaDB is seeded and retrieval works.
    Returns sample course recommendations for 'Python data engineering'.
    Useful for debugging RAG issues without running the full pipeline.
    """
    try:
        sample = find_courses("Python, SQL, data engineering", n_results=3)
        return {
            "status": "ok",
            "message": "ChromaDB is seeded and retrieval is working",
            "sample_courses": sample,
        }
    except Exception as e:
        return {
            "status": "error",
            "message": str(e),
        }

# Updated /career/analyze endpoint in main.py
# Replace your existing one with this

@app.post("/career/analyze", response_model=CareerResponse, tags=["Career"])
async def analyze_career(
    request: CareerRequest,
    current_user: User = Depends(get_current_user),  # NOW REQUIRES AUTH
    db: Session = Depends(get_db),
):
    logger.info(
        f"Analysis request from user={current_user.email}, "
        f"goal='{request.goal}'"
    )

    try:
        job_postings = fetch_job_postings(request.goal)
        salary_data  = fetch_salary_data(request.goal)

        result = run_crew(
            skills=request.skills,
            goal=request.goal,
            experience=request.experience,
            job_postings=job_postings,
            salary_data=salary_data,
        )

        # Save to database — new on Day 10
        save_analysis(
            db=db,
            user_id=str(current_user.id),
            skills=request.skills,
            goal=request.goal,
            experience=request.experience,
            skill_gaps=result["skill_gaps"],
            career_paths=result["career_paths"],
            roadmap=result["roadmap"],
            response_time_sec=result["response_time_sec"],
        )
        logger.info(f"Analysis saved to DB for user={current_user.email}")

        return CareerResponse(
            skill_gaps=result["skill_gaps"],
            career_paths=result["career_paths"],
            roadmap=result["roadmap"],
            message=(
                f"Analysis complete in {result['response_time_sec']}s — "
                f"saved to your history"
            ),
        )

    except RetryError:
        raise HTTPException(status_code=429, detail="AI service rate-limited. Wait 60s.")
    except RateLimitError:
        raise HTTPException(status_code=429, detail="AI service rate limit reached.")
    except APIError as e:
        logger.error(f"Groq APIError: {e}")
        raise HTTPException(status_code=503, detail="AI service temporarily unavailable.")
    except Exception as e:
        logger.exception(f"Unexpected error: {e}")
        raise HTTPException(status_code=500, detail="An unexpected error occurred.")


# Update /user/history to use real DB
@app.get("/user/history", response_model=AnalysisHistoryResponse, tags=["User"])
async def get_user_history(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    analyses = get_user_analyses(db=db, user_id=str(current_user.id))
    items = [
        AnalysisHistoryItem(
            id=str(a.id),
            goal_input=a.goal_input,
            skills_input=a.skills_input,
            experience_input=a.experience_input,
            skill_gaps_output=a.skill_gaps_output,
            career_paths_output=a.career_paths_output,
            roadmap_output=a.roadmap_output,
            response_time_sec=a.response_time_sec or 0.0,
            created_at=a.created_at,
        )
        for a in analyses
    ]
    return AnalysisHistoryResponse(total=len(items), analyses=items)


# Update /user/skills/progress to use real DB
@app.post("/user/skills/progress", response_model=SkillProgressResponse, tags=["User"])
async def update_skill_progress(
    update: SkillProgressUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    upsert_skill_progress(
        db=db,
        user_id=str(current_user.id),
        skill_name=update.skill_name,
        status=update.status,
    )
    return SkillProgressResponse(
        skill_name=update.skill_name,
        status=update.status,
        message=f"Skill '{update.skill_name}' updated to '{update.status}'",
    )

    
@app.get(
    "/user/dashboard",
    response_model=DashboardResponse,
    tags=["User"],
    summary="Get aggregated stats for the user's dashboard",
)
async def get_user_dashboard():
    """
    Returns aggregated stats for the dashboard page.
    Day 9: Returns mock data.
    Day 13: Real query aggregating from career_analyses and skill_progress tables.
    """
    return DashboardResponse(
        total_analyses=1,
        latest_goal="Data Engineer",
        latest_match_score="35%",
        skills_in_progress=3,
        skills_completed=1,
        latest_analysis=None,
    )

# Auth endpoints — add to main.py

@app.post("/auth/register", response_model=TokenResponse, tags=["Auth"])
async def register(request: RegisterRequest, db: Session = Depends(get_db)):
    """
    Creates a new user account and returns a JWT token immediately.
    No email verification for now — user is logged in right after registration.
    """
    user = create_user(
        db=db,
        email=request.email,
        password=request.password,
        name=request.name,
    )
    token = create_access_token(str(user.id))

    return TokenResponse(
        access_token=token,
        token_type="bearer",
        message=f"Welcome, {user.name}! Your account has been created.",
    )


@app.post("/auth/login", response_model=TokenResponse, tags=["Auth"])
async def login(request: LoginRequest, db: Session = Depends(get_db)):
    """
    Authenticates an existing user and returns a JWT token.
    The token expires after ACCESS_TOKEN_EXPIRE_MINUTES (default 30 minutes).
    """
    user = authenticate_user(db=db, email=request.email, password=request.password)
    token = create_access_token(str(user.id))

    return TokenResponse(
        access_token=token,
        token_type="bearer",
        message=f"Welcome back, {user.name}!",
    )


@app.get("/auth/me", response_model=UserResponse, tags=["Auth"])
async def get_me(current_user: User = Depends(get_current_user)):
    """Returns the currently authenticated user's profile. Tests that auth works."""
    return UserResponse(
        id=str(current_user.id),
        email=current_user.email,
        name=current_user.name,
        created_at=current_user.created_at,
    )