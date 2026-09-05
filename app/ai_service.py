"""
Server-side calls to the Anthropic API. Unlike the original frontend artifact
(which called api.anthropic.com directly from the browser — fine inside
Claude.ai's sandbox, but NOT safe once you deploy your own site, since it
would expose your API key), all model calls now happen here, on the backend,
using a key that lives only in your .env file.
"""
import json
import re

from anthropic import Anthropic

from app.config import settings

_client = None


def get_client() -> Anthropic:
    global _client
    if _client is None:
        if not settings.anthropic_api_key:
            raise RuntimeError("ANTHROPIC_API_KEY not set in .env")
        _client = Anthropic(api_key=settings.anthropic_api_key)
    return _client


def _call_json(prompt: str, max_tokens: int = 1200) -> dict:
    client = get_client()
    resp = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    text = "".join(b.text for b in resp.content if b.type == "text")
    cleaned = re.sub(r"```json|```", "", text).strip()
    return json.loads(cleaned)


def parse_resume(resume_text: str) -> dict:
    prompt = f"""Respond ONLY with valid JSON, no markdown fences. Shape:
{{"skills": ["..."], "experience": [{{"title":"", "company":"", "duration":"", "highlights":["..."]}}], "education": [{{"degree":"", "institution":"", "year":""}}]}}.
Extract a structured profile from this resume text:
\"\"\"
{resume_text}
\"\"\""""
    return _call_json(prompt)


def tailor_application(parsed_profile: dict, job: dict) -> dict:
    prompt = f"""Respond ONLY with valid JSON, no markdown fences. Shape:
{{"bullets": ["...", "...", "..."], "coverLetter": "..."}}.

Candidate profile: {json.dumps(parsed_profile)}

Job posting:
Role: {job['role']}
Company: {job['company']}
Description: {job['desc']}

Write 3-5 tailored resume bullet points (quantified where plausible, using the
candidate's real experience) and a concise 3-paragraph cover letter for this
specific role. Do not invent experience the candidate doesn't have."""
    return _call_json(prompt, max_tokens=1500)


def generate_interview_prep(parsed_profile: dict, job: dict) -> dict:
    prompt = f"""Respond ONLY with valid JSON, no markdown fences. Shape:
{{"questions": [{{"question": "...", "tip": "..."}}]}}.

Candidate profile: {json.dumps(parsed_profile)}
Job: {job['role']} at {job['company']}
Description: {job['desc']}

Generate 5 likely interview questions for this specific role (mix of
behavioral and role-specific technical/domain questions) with a short
one-line tip for each on how the candidate should approach answering,
grounded in their actual background."""
    return _call_json(prompt, max_tokens=1200)
