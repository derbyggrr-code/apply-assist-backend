import datetime as dt

from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, ForeignKey, JSON, UniqueConstraint
from sqlalchemy.orm import relationship

from app.database import Base


class Profile(Base):
    """Single-user profile: resume text, parsed structure, and search preferences.
    (Extend with a user_id / auth layer if you need multi-user support.)"""
    __tablename__ = "profiles"

    id = Column(Integer, primary_key=True, default=1)
    resume_text = Column(Text, default="")
    parsed_profile = Column(JSON, default=dict)   # {skills, experience, education}
    prefs = Column(JSON, default=dict)            # {role, location, experience, minSalary, remoteOnly}
    updated_at = Column(DateTime, default=dt.datetime.utcnow, onupdate=dt.datetime.utcnow)


class Job(Base):
    """Jobs pulled from the aggregator API (Adzuna). Cached locally so the
    frontend and scheduler don't need to hit the external API on every request."""
    __tablename__ = "jobs"

    id = Column(Integer, primary_key=True)
    external_id = Column(String, unique=True, index=True)  # Adzuna's job id, dedupe key
    role = Column(String)
    company = Column(String)
    location = Column(String)
    salary = Column(String)
    remote = Column(Boolean, default=False)
    tags = Column(JSON, default=list)
    desc = Column(Text)
    apply_url = Column(String)
    source = Column(String, default="adzuna")
    fetched_at = Column(DateTime, default=dt.datetime.utcnow)

    tracker_entries = relationship("TrackerEntry", back_populates="job", cascade="all, delete-orphan")


class TrackerEntry(Base):
    """A job the user has saved/applied to, with status + optional cached
    tailored resume/cover-letter and interview prep."""
    __tablename__ = "tracker_entries"
    __table_args__ = (UniqueConstraint("job_id", name="uq_tracker_job"),)

    id = Column(Integer, primary_key=True)
    job_id = Column(Integer, ForeignKey("jobs.id"))
    status = Column(String, default="Saved")  # Saved, Applied, Interview, Offer, Rejected
    tailored = Column(JSON, nullable=True)       # {bullets: [...], coverLetter: "..."}
    interview_prep = Column(JSON, nullable=True) # {questions: [{question, tip}]}
    added_at = Column(DateTime, default=dt.datetime.utcnow)
    updated_at = Column(DateTime, default=dt.datetime.utcnow, onupdate=dt.datetime.utcnow)

    job = relationship("Job", back_populates="tracker_entries")
