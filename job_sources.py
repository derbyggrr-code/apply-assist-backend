"""
Real job listings via the Adzuna API (https://developer.adzuna.com/).
Free tier: sign up, get app_id + app_key, ~250 calls/month on the free plan
(check current limits on their site — they do change).

Swap this module out if you'd rather use JSearch/RapidAPI, LinkedIn, etc. —
everything else in the backend only depends on `fetch_jobs()` returning the
normalized dict shape used by models.Job.
"""
import re
import httpx

from app.config import settings

STOPWORDS = {
    "and", "the", "for", "with", "a", "an", "of", "in", "to", "on", "is", "are",
    "as", "at", "by", "this", "that", "from", "or", "be", "have", "has",
}


def extract_keywords(text: str) -> set:
    words = re.findall(r"[a-z0-9+.#]+", text.lower())
    return {w for w in words if len(w) > 2 and w not in STOPWORDS}


def score_job(keyword_set: set, tags: list[str]) -> int:
    if not tags:
        return 35
    hits = sum(1 for tag in tags if any(w in keyword_set for w in tag.split(" ")))
    pct = round((hits / len(tags)) * 100)
    bonus = 15 if keyword_set else 0
    return max(35, min(97, pct + bonus))


async def fetch_jobs(query: str = "", location: str = "", results_per_page: int = 20) -> list[dict]:
    """Hits Adzuna's /jobs/{country}/search/1 endpoint and returns a list of
    normalized job dicts ready to upsert into the Job table."""
    if not settings.adzuna_app_id or not settings.adzuna_app_key:
        raise RuntimeError(
            "ADZUNA_APP_ID / ADZUNA_APP_KEY not set. Get free keys at "
            "https://developer.adzuna.com/ and put them in your .env file."
        )

    url = f"https://api.adzuna.com/v1/api/jobs/{settings.adzuna_country}/search/1"
    params = {
        "app_id": settings.adzuna_app_id,
        "app_key": settings.adzuna_app_key,
        "results_per_page": results_per_page,
        "what": query,
        "where": location,
        "content-type": "application/json",
    }
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()

    jobs = []
    for item in data.get("results", []):
        salary_min = item.get("salary_min")
        salary_max = item.get("salary_max")
        salary = ""
        if salary_min and salary_max:
            salary = f"₹{int(salary_min):,} - ₹{int(salary_max):,}"
        elif salary_min:
            salary = f"₹{int(salary_min):,}+"

        category = (item.get("category") or {}).get("label", "")
        title = item.get("title", "")
        tags = list({t.lower() for t in re.findall(r"[A-Za-z][A-Za-z0-9+.#]{2,}", f"{title} {category}")})

        jobs.append({
            "external_id": str(item.get("id")),
            "role": title,
            "company": (item.get("company") or {}).get("display_name", "Unknown"),
            "location": (item.get("location") or {}).get("display_name", ""),
            "salary": salary,
            "remote": "remote" in (item.get("description", "") or "").lower(),
            "tags": tags[:12],
            "desc": item.get("description", ""),
            "apply_url": item.get("redirect_url", ""),
            "source": "adzuna",
        })
    return jobs
