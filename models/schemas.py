# models/schemas.py
from pydantic import BaseModel, Field
from typing import Optional


class CareerRequest(BaseModel):
    """
    What the frontend sends when a user submits the career form.
    All three fields are required.
    """
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
    """
    What the API returns after running the 3-agent pipeline.
    For Day 2, these will be placeholder strings.
    On Day 5, these will be real agent outputs.
    """
    skill_gaps: str = Field(description="Agent 1 output — skill gap analysis")
    career_paths: str = Field(description="Agent 2 output — career path recommendations")
    roadmap: str = Field(description="Agent 3 output — 8-week learning plan")
    message: str = Field(description="Status message from the API")


class HealthResponse(BaseModel):
    """Used by GET /health — keeps Render from sleeping."""
    status: str
    message: str