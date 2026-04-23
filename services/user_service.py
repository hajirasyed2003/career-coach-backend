# services/user_service.py
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session
from fastapi import HTTPException, status

from models.db_models import User, UserProfile, CareerAnalysis, SkillProgress
from services.auth_service import hash_password, verify_password


def get_user_by_email(db: Session, email: str) -> Optional[User]:
    """Returns a User row by email, or None if not found."""
    return db.query(User).filter(User.email == email.lower()).first()


def get_user_by_id(db: Session, user_id: str) -> Optional[User]:
    """Returns a User row by UUID, or None if not found."""
    return db.query(User).filter(User.id == user_id).first()


def create_user(db: Session, email: str, password: str, name: str) -> User:
    """
    Creates a new user row and their profile row in one transaction.
    Raises 400 if email is already registered.

    The profile row is created immediately (empty) so every user
    always has a profile — avoids nullable checks everywhere else.
    """
    # Check for existing user
    existing = get_user_by_email(db, email)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="An account with this email already exists",
        )

    # Create user row
    new_user = User(
        email=email.lower().strip(),
        name=name.strip(),
        hashed_password=hash_password(password),
    )
    db.add(new_user)
    db.flush()  # flush to get the auto-generated UUID before committing

    # Create empty profile row linked to this user
    profile = UserProfile(user_id=new_user.id)
    db.add(profile)

    db.commit()
    db.refresh(new_user)
    return new_user


def authenticate_user(db: Session, email: str, password: str) -> User:
    """
    Verifies email + password combination.
    Raises 401 if either is wrong.

    Note: same error message for wrong email and wrong password intentionally —
    you don't want to reveal which one is wrong (security best practice).
    """
    user = get_user_by_email(db, email)

    if not user or not verify_password(password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account has been deactivated",
        )

    return user


def save_analysis(
    db: Session,
    user_id: str,
    skills: str,
    goal: str,
    experience: str,
    skill_gaps: str,
    career_paths: str,
    roadmap: str,
    response_time_sec: float,
) -> CareerAnalysis:
    """
    Saves a completed career analysis to the database.
    Also updates the user's profile with their latest goal and skills.
    Called at the end of POST /career/analyze after the crew finishes.
    """
    # Save the analysis
    analysis = CareerAnalysis(
        user_id=user_id,
        skills_input=skills,
        goal_input=goal,
        experience_input=experience,
        skill_gaps_output=skill_gaps,
        career_paths_output=career_paths,
        roadmap_output=roadmap,
        response_time_sec=response_time_sec,
    )
    db.add(analysis)

    # Update the user's profile with their latest info
    profile = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
    if profile:
        profile.current_skills   = skills
        profile.target_role      = goal
        profile.experience_level = experience

    db.commit()
    db.refresh(analysis)
    return analysis


def get_user_analyses(db: Session, user_id: str) -> list[CareerAnalysis]:
    """Returns all analyses for a user, newest first."""
    return (
        db.query(CareerAnalysis)
        .filter(CareerAnalysis.user_id == user_id)
        .order_by(CareerAnalysis.created_at.desc())
        .all()
    )


def upsert_skill_progress(
    db: Session, user_id: str, skill_name: str, status: str
) -> SkillProgress:
    """
    Creates or updates a skill progress row.
    'Upsert' = update if exists, insert if not.
    """
    existing = (
        db.query(SkillProgress)
        .filter(
            SkillProgress.user_id == user_id,
            SkillProgress.skill_name == skill_name,
        )
        .first()
    )

    if existing:
        existing.status = status
        db.commit()
        db.refresh(existing)
        return existing

    new_progress = SkillProgress(
        user_id=user_id,
        skill_name=skill_name,
        status=status,
    )
    db.add(new_progress)
    db.commit()
    db.refresh(new_progress)
    return new_progress