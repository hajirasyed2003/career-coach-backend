# models/db_models.py
import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    Column, String, Float, DateTime, Boolean,
    Text, ForeignKey, Enum as SAEnum,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship, declarative_base

Base = declarative_base()


def _now():
    """Returns current UTC time. Used as default for created_at columns."""
    return datetime.now(timezone.utc)


class User(Base):
    """
    Core identity table. One row per registered user.
    Passwords are NEVER stored in plain text — only bcrypt hashes.
    """
    __tablename__ = "users"

    id             = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email          = Column(String(255), unique=True, nullable=False, index=True)
    name           = Column(String(255), nullable=True)
    hashed_password = Column(String(255), nullable=False)
    created_at     = Column(DateTime(timezone=True), default=_now, nullable=False)
    is_active      = Column(Boolean, default=True, nullable=False)

    # Relationships — lets you do user.analyses, user.profile, user.skill_progress
    profile         = relationship("UserProfile", back_populates="user", uselist=False)
    analyses        = relationship("CareerAnalysis", back_populates="user",
                                   order_by="CareerAnalysis.created_at.desc()")
    skill_progress  = relationship("SkillProgress", back_populates="user")

    def __repr__(self):
        return f"<User id={self.id} email={self.email}>"


class UserProfile(Base):
    """
    Extended user data. Separated from users for clean normalisation.
    Updated whenever the user runs a new analysis.
    """
    __tablename__ = "user_profiles"

    id               = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id          = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
                              unique=True, nullable=False)
    current_skills   = Column(Text, nullable=True)     # e.g. "Python, SQL, Excel"
    target_role      = Column(String(255), nullable=True)
    experience_level = Column(String(100), nullable=True)
    learned_skills   = Column(Text, nullable=True)     # comma-separated completed skills
    updated_at       = Column(DateTime(timezone=True), default=_now, onupdate=_now)

    user = relationship("User", back_populates="profile")

    def __repr__(self):
        return f"<UserProfile user_id={self.user_id} role={self.target_role}>"


class CareerAnalysis(Base):
    """
    Full record of every analysis run. Append-only — never delete rows.
    The full agent outputs are stored as Text so nothing is lost.
    Evaluation metrics are stored alongside for the dashboard.
    """
    __tablename__ = "career_analyses"

    id                   = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id              = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
                                  nullable=False, index=True)

    # Inputs stored so history page can show what was submitted
    skills_input         = Column(Text, nullable=False)
    goal_input           = Column(String(255), nullable=False)
    experience_input     = Column(String(100), nullable=False)

    # Full agent outputs
    skill_gaps_output    = Column(Text, nullable=False)
    career_paths_output  = Column(Text, nullable=False)
    roadmap_output       = Column(Text, nullable=False)

    # Metrics (populated even without evaluation service for now)
    response_time_sec    = Column(Float, nullable=True)

    created_at           = Column(DateTime(timezone=True), default=_now, nullable=False)

    user = relationship("User", back_populates="analyses")

    def __repr__(self):
        return f"<CareerAnalysis id={self.id} goal={self.goal_input}>"


class SkillProgress(Base):
    """
    Tracks each skill's learning status per user.
    One row per (user, skill) combination.
    Updated when the frontend checkbox is ticked.
    """
    __tablename__ = "skill_progress"

    id          = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id     = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
                         nullable=False, index=True)
    skill_name  = Column(String(255), nullable=False)
    status      = Column(
        SAEnum("not_started", "in_progress", "completed", name="skill_status_enum"),
        default="not_started",
        nullable=False,
    )
    updated_at  = Column(DateTime(timezone=True), default=_now, onupdate=_now)

    user = relationship("User", back_populates="skill_progress")

    def __repr__(self):
        return f"<SkillProgress user_id={self.user_id} skill={self.skill_name} status={self.status}>"