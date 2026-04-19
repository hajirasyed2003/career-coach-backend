# main.py — full updated file
import logging
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from groq import RateLimitError, APIError
from tenacity import RetryError
from models.schemas import CareerRequest, CareerResponse, HealthResponse
from services.crew_service import run_crew
from services.data_fetcher import fetch_job_postings, fetch_salary_data

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="AI Career Coach API",
    description="Multi-agent career coaching system powered by CrewAI and Groq",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],     # Restrict to Vercel URL in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", response_model=HealthResponse, tags=["System"])
async def health_check():
    return HealthResponse(status="ok", message="Career Coach API is running")



@app.post(
    "/career/analyze",
    response_model=CareerResponse,
    tags=["Career"],
    summary="Run the full 3-agent career analysis pipeline",
)
async def analyze_career(request: CareerRequest):
    """
    Full pipeline with real market data injection:
    1. Fetch live job postings for the target role (JSearch)
    2. Fetch real salary data for the target role (Adzuna)
    3. Inject both into agent Task prompts
    4. Run 3-agent CrewAI pipeline
    5. Return structured analysis
    """
    logger.info(
        f"Analysis request: goal='{request.goal}', "
        f"experience='{request.experience}'"
    )

    try:
        # ── Step 1: Fetch real market data ──────────────────────────────────
        # These calls are fast (cached after first call per role)
        logger.info("Fetching job market data...")
        job_postings = fetch_job_postings(request.goal)
        salary_data  = fetch_salary_data(request.goal)
        logger.info("Market data ready — starting crew pipeline")

        # ── Step 2: Run crew with real data injected ─────────────────────────
        result = run_crew(
            skills=request.skills,
            goal=request.goal,
            experience=request.experience,
            job_postings=job_postings,  # now passing real data
            salary_data=salary_data,    # now passing real data
        )

        return CareerResponse(
            skill_gaps=result["skill_gaps"],
            career_paths=result["career_paths"],
            roadmap=result["roadmap"],
            message=f"Analysis complete in {result['response_time_sec']}s "
                    f"(grounded in real job market data)",
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