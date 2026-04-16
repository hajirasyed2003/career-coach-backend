# main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import os
from services.crew_service import run_crew

from models.schemas import CareerRequest, CareerResponse, HealthResponse

# Load environment variables from .env
load_dotenv()

# Create the FastAPI application
app = FastAPI(
    title="AI Career Coach API",
    description="Multi-agent career coaching system powered by CrewAI and Groq",
    version="1.0.0",
)

# CORS — allows the Next.js frontend to call this API
# During development, allow all origins. In production, restrict to your Vercel URL.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],           # Replace "*" with Vercel URL in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", response_model=HealthResponse, tags=["System"])
async def health_check():
    """
    GET /health
    UptimeRobot pings this every 5 minutes to keep Render from sleeping.
    Always returns 200 OK with a status message.
    """
    return HealthResponse(
        status="ok",
        message="Career Coach API is running"
    )


@app.post("/career/analyze", response_model=CareerResponse, tags=["Career"])
async def analyze_career(request: CareerRequest):
    """
    POST /career/analyze
    Now runs the real 3-agent CrewAI pipeline.
    Warning: takes 30-90 seconds. Phase 2 will add async + streaming.
    """
    result = run_crew(
        skills=request.skills,
        goal=request.goal,
        experience=request.experience
    )

    return CareerResponse(
        skill_gaps=result["skill_gaps"],
        career_paths=result["career_paths"],
        roadmap=result["roadmap"],
        message=f"Analysis complete in {result['response_time_sec']}s"
    )