import datetime as dt
import logging

from fastapi import FastAPI, Depends, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from app.config import settings
from app.database import Base, engine, get_db
from app import models, schemas, ai_service
from app.job_sources import fetch_jobs, extract_keywords, score_job
from app.email_service import send_email, build_digest_text
from app.scheduler import start_scheduler, refresh_jobs_job

logging.basicConfig(level=logging.INFO)
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Apply Assist API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup():
    start_scheduler()
    # Warm the jobs table on first boot if it's empty.
    db = next(get_db())
    if db.query(models.Job).count() == 0:
        try:
            refresh_jobs_job()
        except Exception as e:
            logging.warning(f"Initial job fetch skipped: {e}")


def _get_or_create_profile(db: Session) -> models.Profile:
    profile = db.query(models.Profile).first()
    if not profile:
        profile = models.Profile(id=1, resume_text="", parsed_profile={}, prefs={})
        db.add(profile)
        db.commit()
        db.refresh(profile)
    return profile


# ---------- Profile ----------

@app.get("/api/profile", response_model=schemas.ProfileOut)
def get_profile(db: Session = Depends(get_db)):
    profile = _get_or_create_profile(db)
    return schemas.ProfileOut(
        resumeText=profile.resume_text,
        parsedProfile=profile.parsed_profile,
        prefs=profile.prefs or {},
    )


@app.put("/api/profile", response_model=schemas.ProfileOut)
def save_profile(body: schemas.ProfileIn, db: Session = Depends(get_db)):
    profile = _get_or_create_profile(db)
    profile.resume_text = body.resumeText
    if body.parsedProfile is not None:
        profile.parsed_profile = body.parsedProfile
    if body.prefs is not None:
        profile.prefs = body.prefs.model_dump()
    db.commit()
    db.refresh(profile)
    return schemas.ProfileOut(
        resumeText=profile.resume_text,
        parsedProfile=profile.parsed_profile,
        prefs=profile.prefs or {},
    )


@app.post("/api/profile/parse-resume", response_model=schemas.ProfileOut)
def parse_resume(body: schemas.ParseResumeIn, db: Session = Depends(get_db)):
    try:
        parsed = ai_service.parse_resume(body.resumeText)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Resume parsing failed: {e}")

    profile = _get_or_create_profile(db)
    profile.resume_text = body.resumeText
    profile.parsed_profile = parsed
    db.commit()
    db.refresh(profile)
    return schemas.ProfileOut(
        resumeText=profile.resume_text,
        parsedProfile=profile.parsed_profile,
        prefs=profile.prefs or {},
    )


# ---------- Jobs ----------

@app.get("/api/jobs", response_model=list[schemas.JobOut])
def list_jobs(db: Session = Depends(get_db)):
    profile = _get_or_create_profile(db)
    keyword_source = ""
    if profile.parsed_profile:
        keyword_source = " ".join(profile.parsed_profile.get("skills", []))
    keyword_source += " " + (profile.resume_text or "")
    keywords = extract_keywords(keyword_source)

    jobs = db.query(models.Job).order_by(models.Job.fetched_at.desc()).all()
    out = []
    for j in jobs:
        out.append(schemas.JobOut(
            id=j.id, role=j.role, company=j.company, location=j.location,
            salary=j.salary, remote=j.remote, tags=j.tags or [], desc=j.desc,
            apply_url=j.apply_url, score=score_job(keywords, j.tags or []),
        ))
    out.sort(key=lambda j: j.score or 0, reverse=True)
    return out


@app.post("/api/jobs/refresh")
async def refresh_jobs(db: Session = Depends(get_db)):
    """Manually trigger a fetch from Adzuna right now (in addition to the
    daily scheduled refresh)."""
    profile = _get_or_create_profile(db)
    query = (profile.prefs or {}).get("role", "")
    location = (profile.prefs or {}).get("location", "")
    if location == "Any":
        location = ""
    try:
        jobs = await fetch_jobs(query=query, location=location)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))

    added, updated = 0, 0
    for j in jobs:
        existing = db.query(models.Job).filter_by(external_id=j["external_id"]).first()
        if existing:
            for k, v in j.items():
                setattr(existing, k, v)
            updated += 1
        else:
            db.add(models.Job(**j))
            added += 1
    db.commit()
    return {"added": added, "updated": updated}


# ---------- Browser extension import ----------

def verify_extension_key(x_extension_key: str = Header(default="")):
    if not settings.extension_api_key or x_extension_key != settings.extension_api_key:
        raise HTTPException(status_code=401, detail="Invalid or missing extension key")


@app.post("/api/jobs/import")
def import_jobs(
    body: schemas.ImportJobsIn,
    db: Session = Depends(get_db),
    _auth: None = Depends(verify_extension_key),
):
    """Accepts jobs scraped by the browser extension from LinkedIn/Naukri
    pages the user is already viewing. Requires the X-Extension-Key header
    to match EXTENSION_API_KEY in .env, so random callers can't write here."""
    added, updated = 0, 0
    for j in body.jobs:
        existing = db.query(models.Job).filter_by(external_id=j.external_id).first()
        if existing:
            for k, v in j.model_dump().items():
                setattr(existing, k, v)
            updated += 1
        else:
            db.add(models.Job(**j.model_dump()))
            added += 1
    db.commit()
    return {"added": added, "updated": updated}


# ---------- Tailoring / interview prep ----------

def _job_to_dict(job: models.Job) -> dict:
    return {"role": job.role, "company": job.company, "location": job.location, "desc": job.desc or ""}


@app.post("/api/jobs/{job_id}/tailor", response_model=schemas.TailoredOut)
def tailor(job_id: int, db: Session = Depends(get_db)):
    job = db.query(models.Job).get(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    profile = _get_or_create_profile(db)
    if not profile.parsed_profile:
        raise HTTPException(400, "Parse your resume first")

    try:
        tailored = ai_service.tailor_application(profile.parsed_profile, _job_to_dict(job))
    except Exception as e:
        raise HTTPException(502, f"Tailoring failed: {e}")

    entry = db.query(models.TrackerEntry).filter_by(job_id=job_id).first()
    if entry:
        entry.tailored = tailored
        db.commit()
    return schemas.TailoredOut(**tailored)


@app.post("/api/jobs/{job_id}/interview-prep", response_model=schemas.InterviewPrepOut)
def interview_prep(job_id: int, db: Session = Depends(get_db)):
    job = db.query(models.Job).get(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    profile = _get_or_create_profile(db)
    if not profile.parsed_profile:
        raise HTTPException(400, "Parse your resume first")

    try:
        prep = ai_service.generate_interview_prep(profile.parsed_profile, _job_to_dict(job))
    except Exception as e:
        raise HTTPException(502, f"Interview prep failed: {e}")

    entry = db.query(models.TrackerEntry).filter_by(job_id=job_id).first()
    if entry:
        entry.interview_prep = prep
        db.commit()
    return schemas.InterviewPrepOut(**prep)


# ---------- Tracker ----------

@app.get("/api/tracker", response_model=list[schemas.TrackerEntryOut])
def get_tracker(db: Session = Depends(get_db)):
    entries = db.query(models.TrackerEntry).all()
    return [
        schemas.TrackerEntryOut(
            id=e.id,
            job=schemas.JobOut.model_validate(e.job),
            status=e.status,
            tailored=e.tailored,
            interview_prep=e.interview_prep,
            added_at=e.added_at.isoformat(),
        )
        for e in entries
    ]


@app.post("/api/tracker", response_model=schemas.TrackerEntryOut)
def add_to_tracker(body: schemas.TrackerStatusIn, db: Session = Depends(get_db)):
    job = db.query(models.Job).get(body.job_id)
    if not job:
        raise HTTPException(404, "Job not found")

    entry = db.query(models.TrackerEntry).filter_by(job_id=body.job_id).first()
    if not entry:
        entry = models.TrackerEntry(job_id=body.job_id, status=body.status or "Saved")
        db.add(entry)
    else:
        entry.status = body.status
    db.commit()
    db.refresh(entry)
    return schemas.TrackerEntryOut(
        id=entry.id, job=schemas.JobOut.model_validate(job), status=entry.status,
        tailored=entry.tailored, interview_prep=entry.interview_prep,
        added_at=entry.added_at.isoformat(),
    )


@app.delete("/api/tracker/{entry_id}")
def remove_from_tracker(entry_id: int, db: Session = Depends(get_db)):
    entry = db.query(models.TrackerEntry).get(entry_id)
    if not entry:
        raise HTTPException(404, "Tracker entry not found")
    db.delete(entry)
    db.commit()
    return {"ok": True}


# ---------- Digest ----------

@app.get("/api/digest")
def get_digest(db: Session = Depends(get_db)):
    entries = db.query(models.TrackerEntry).all()
    payload = [{"status": e.status, "job": {"role": e.job.role, "company": e.job.company, "location": e.job.location}} for e in entries]
    return {"text": build_digest_text(payload)}


@app.post("/api/digest/send")
def send_digest_now(db: Session = Depends(get_db)):
    entries = db.query(models.TrackerEntry).all()
    payload = [{"status": e.status, "job": {"role": e.job.role, "company": e.job.company, "location": e.job.location}} for e in entries]
    text = build_digest_text(payload)
    try:
        send_email("Your Apply Assist digest", text)
    except Exception as e:
        raise HTTPException(502, str(e))
    return {"ok": True, "sent_at": dt.datetime.utcnow().isoformat()}


@app.get("/api/health")
def health():
    return {"status": "ok"}
