# models/schemas.py
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime

class CareerRequest(BaseModel):
    skills: str = Field(
        ...,                    # ... means required, no default
        min_length=3,
        description="Comma-separated list of user's current skills",
        example="Python, SQL, Excel"
    )
    goal: str = Field(
        ...,
        min_length=3,
        description="User's target career role",
        example="Data Engineer"
    )
    experience: str = Field(
        ...,
        description="User's experience level",
        example="1-2 years"
    )


class CareerResponse(BaseModel):
    skill_gaps: str = Field(description="Agent 1 output — skill gap analysis")
    career_paths: str = Field(description="Agent 2 output — career path recommendations")
    roadmap: str = Field(description="Agent 3 output — 8-week learning plan")
    message: str = Field(description="Status message from the API")


class HealthResponse(BaseModel):
    status: str
    message: str


class AnalysisHistoryItem(BaseModel):
    """
    Represents one past career analysis.
    This schema matches the career_analyses DB table you'll create on Day 10.
    The field names here must match the column names there exactly.
    """
    id: str
    goal_input: str
    skills_input: str
    experience_input: str
    skill_gaps_output: str
    career_paths_output: str
    roadmap_output: str
    response_time_sec: float
    created_at: datetime

    class Config:
        # Allows SQLAlchemy model instances to be used directly
        # when you connect the real DB on Day 10
        from_attributes = True


class AnalysisHistoryResponse(BaseModel):
    """
    Wraps a list of past analyses with metadata.
    Returned by GET /user/history.
    """
    total: int
    analyses: List[AnalysisHistoryItem]


class SkillProgressUpdate(BaseModel):
    """
    Request body for POST /user/skills/progress.
    Used when the frontend checkbox is ticked for a skill.
    """
    skill_name: str = Field(..., min_length=1, example="Docker")
    status: str = Field(
        ...,
        pattern="^(not_started|in_progress|completed)$",
        example="completed",
        description="Must be: not_started, in_progress, or completed",
    )


class SkillProgressResponse(BaseModel):
    """Response after updating a skill's progress status."""
    skill_name: str
    status: str
    message: str


class DashboardResponse(BaseModel):
    """
    Data for the user's dashboard page.
    Aggregates stats from their analysis history.
    """
    total_analyses: int
    latest_goal: Optional[str]
    latest_match_score: Optional[str]
    skills_in_progress: int
    skills_completed: int
    latest_analysis: Optional[AnalysisHistoryItem]


class RegisterRequest(BaseModel):
    email: str = Field(..., example="user@example.com")
    password: str = Field(..., min_length=8, example="securepassword123")
    name: str = Field(..., min_length=1, example="Priya Sharma")


class LoginRequest(BaseModel):
    email: str = Field(..., example="user@example.com")
    password: str = Field(..., example="securepassword123")


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    message: str


class UserResponse(BaseModel):
    id: str
    email: str
    name: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True

