# main.py — updated with lifespan and RAG integration
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from groq import RateLimitError, APIError
from tenacity import RetryError

from models.schemas import CareerRequest, CareerResponse, HealthResponse
from services.crew_service import run_crew
from services.data_fetcher import fetch_job_postings, fetch_salary_data
from services.rag_service import seed_courses  # NEW
from services.rag_service import find_courses 

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
        
@app.post(
    "/career/analyze",
    response_model=CareerResponse,
    tags=["Career"],
    summary="Run the full 3-agent career analysis pipeline",
)
async def analyze_career(request: CareerRequest):
    logger.info(f"Analysis request: goal='{request.goal}', experience='{request.experience}'")

    try:
        # Fetch real market data (cached after first call per role)
        logger.info("Fetching market data...")
        job_postings = fetch_job_postings(request.goal)
        salary_data  = fetch_salary_data(request.goal)

        # Run the crew — RAG is now handled inside crew_service
        result = run_crew(
            skills=request.skills,
            goal=request.goal,
            experience=request.experience,
            job_postings=job_postings,
            salary_data=salary_data,
        )

        return CareerResponse(
            skill_gaps=result["skill_gaps"],
            career_paths=result["career_paths"],
            roadmap=result["roadmap"],
            message=(
                f"Analysis complete in {result['response_time_sec']}s "
                f"(grounded in real job data + RAG course recommendations)"
            ),
        )

    except RetryError:
        logger.error("Groq rate limit hit after all retries")
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="AI service rate-limited. Please wait 60 seconds and retry.",
        )
    except RateLimitError:
        logger.error("Unexpected RateLimitError")
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="AI service rate limit reached. Please try again shortly.",
        )
    except APIError as e:
        logger.error(f"Groq APIError: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI service temporarily unavailable.",
        )
    except Exception as e:
        logger.exception(f"Unexpected error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred. Please try again.",
        )