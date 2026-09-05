from typing import Optional, List, Dict, Any
from pydantic import BaseModel


class PrefsIn(BaseModel):
    role: str = ""
    location: str = "Any"
    experience: str = "0-2 years"
    minSalary: str = ""
    remoteOnly: bool = False


class ProfileIn(BaseModel):
    resumeText: str = ""
    parsedProfile: Optional[Dict[str, Any]] = None
    prefs: Optional[PrefsIn] = None


class ProfileOut(BaseModel):
    resumeText: str
    parsedProfile: Optional[Dict[str, Any]]
    prefs: Dict[str, Any]

    class Config:
        from_attributes = True


class ParseResumeIn(BaseModel):
    resumeText: str


class JobOut(BaseModel):
    id: int
    role: str
    company: str
    location: str
    salary: Optional[str] = None
    remote: bool = False
    tags: List[str] = []
    desc: Optional[str] = None
    apply_url: Optional[str] = None
    score: Optional[int] = None

    class Config:
        from_attributes = True


class ImportedJobIn(BaseModel):
    """Shape the browser extension sends for each scraped listing."""
    external_id: str          # e.g. the LinkedIn/Naukri job posting URL or id
    role: str
    company: str
    location: str = ""
    salary: Optional[str] = ""
    remote: bool = False
    desc: Optional[str] = ""
    apply_url: str
    source: str  # "linkedin" or "naukri"


class ImportJobsIn(BaseModel):
    jobs: List[ImportedJobIn]


class TailorIn(BaseModel):
    job_id: int


class TailoredOut(BaseModel):
    bullets: List[str]
    coverLetter: str


class InterviewPrepOut(BaseModel):
    questions: List[Dict[str, str]]


class TrackerStatusIn(BaseModel):
    job_id: int
    status: str


class TrackerEntryOut(BaseModel):
    id: int
    job: JobOut
    status: str
    tailored: Optional[Dict[str, Any]] = None
    interview_prep: Optional[Dict[str, Any]] = None
    added_at: str

    class Config:
        from_attributes = True
