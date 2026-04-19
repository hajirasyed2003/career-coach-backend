# services/data_fetcher.py
import os
import re
import time
import json
import logging

import httpx
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


# ── Skill Allowlist ────────────────────────────────────────────────────────────

TECH_SKILLS = {
    # Languages
    "python", "sql", "java", "scala", "r", "go", "golang", "javascript",
    "typescript", "bash", "shell", "rust", "c++", "c#", "ruby", "php",
    "swift", "kotlin", "matlab", "perl", "lua",
    # Data & ML frameworks
    "spark", "pyspark", "hadoop", "kafka", "airflow", "dbt", "flink",
    "hive", "presto", "trino", "nifi", "luigi", "prefect", "dagster",
    "pandas", "numpy", "scikit-learn", "tensorflow", "pytorch", "keras",
    "xgboost", "lightgbm", "mlflow", "kubeflow",
    # Cloud platforms
    "aws", "azure", "gcp", "s3", "ec2", "lambda", "glue", "emr",
    "redshift", "bigquery", "snowflake", "databricks", "synapse",
    "dataflow", "pubsub", "sagemaker", "vertex ai",
    # Databases
    "postgresql", "postgres", "mysql", "sqlite", "oracle", "sql server",
    "mongodb", "cassandra", "redis", "elasticsearch", "dynamodb",
    "neo4j", "couchdb", "influxdb", "clickhouse", "hbase",
    # BI & Visualisation
    "tableau", "power bi", "looker", "metabase", "superset", "grafana",
    "qlik", "domo",
    # DevOps & Infra
    "docker", "kubernetes", "k8s", "terraform", "ansible", "helm",
    "jenkins", "github actions", "gitlab ci", "ci/cd", "git",
    "linux", "unix",
    # Data concepts
    "etl", "elt", "data modeling", "data warehousing", "data lakehouse",
    "data lake", "streaming", "batch processing", "rest api", "graphql",
    "microservices", "event-driven", "olap", "oltp", "star schema",
    "data governance", "data quality", "data pipeline",
    # APIs & messaging
    "rest", "grpc", "rabbitmq", "celery", "fastapi", "flask", "django",
    "spring", "spark streaming",
}


def _allowlist_match(description: str) -> list[str]:
    """Fast pass: match description against known tech skill keywords."""
    text = description.lower()
    found = []
    for skill in TECH_SKILLS:
        pattern = r'\b' + re.escape(skill) + r'\b'
        if re.search(pattern, text):
            found.append(skill)
    return found


def _llm_extract_skills(description: str) -> list[str]:
    """
    LLM fallback: call Claude to extract skills when the allowlist
    returns fewer than 3 hits. Truncates description to 2000 chars
    to keep token usage low.
    """
    prompt = (
        "Extract only the technical skills, tools, programming languages, "
        "frameworks, and cloud platforms required from this job description. "
        "Exclude soft skills, locations, and company names. "
        "Return ONLY a JSON array of lowercase strings, no explanation, "
        "no markdown fences.\n\n"
        f"Job description:\n{description[:2000]}"
    )

    try:
        response = httpx.post(
            "https://api.anthropic.com/v1/messages",
            headers={"Content-Type": "application/json"},
            json={
                "model": "claude-sonnet-4-20250514",
                "max_tokens": 300,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=15.0,
        )
        response.raise_for_status()
        raw_text = response.json()["content"][0]["text"].strip()

        # Strip accidental markdown fences if the model adds them
        raw_text = re.sub(r"^```json|^```|```$", "", raw_text, flags=re.MULTILINE).strip()

        skills = json.loads(raw_text)
        if isinstance(skills, list):
            return [str(s).lower() for s in skills][:12]

    except json.JSONDecodeError:
        logger.warning("LLM skill extraction returned non-JSON — skipping")
    except httpx.HTTPStatusError as e:
        logger.error(f"Claude API HTTP error during skill extraction: {e.response.status_code}")
    except Exception as e:
        logger.exception(f"Unexpected error in LLM skill extraction: {e}")

    return []


def extract_skills_from_description(description: str) -> list[str]:
    """
    Hybrid skill extractor:
      1. Fast allowlist match — handles ~80 % of cases with zero false positives.
      2. LLM fallback (Claude) — kicks in only when allowlist returns < 3 skills,
         covering niche tools and newly released technologies not yet in the list.

    Args:
        description: raw job description text

    Returns:
        Deduplicated list of technical skill strings (up to 12).
    """
    if not description:
        return []

    # Pass 1 — allowlist
    found = _allowlist_match(description)
    if len(found) >= 3:
        logger.debug(f"Allowlist matched {len(found)} skills — skipping LLM")
        return found[:12]

    # Pass 2 — LLM fallback
    logger.info("Allowlist returned < 3 skills — falling back to LLM extraction")
    llm_skills = _llm_extract_skills(description)

    # Merge: allowlist results first, then any LLM additions
    merged = found[:]
    seen = {s.lower() for s in merged}
    for skill in llm_skills:
        if skill.lower() not in seen:
            merged.append(skill)
            seen.add(skill.lower())

    return merged[:12] if merged else ["Skills not clearly specified"]


# ── Simple in-memory cache ─────────────────────────────────────────────────────
# TTL of 24 hours — job market data doesn't change hour-to-hour.
# Replace with Redis in production.

_cache: dict = {}
CACHE_TTL_SECONDS = 60 * 60 * 24  # 24 hours


def _get_cache(key: str):
    """Returns cached value if it exists and hasn't expired."""
    if key in _cache:
        value, timestamp = _cache[key]
        if time.time() - timestamp < CACHE_TTL_SECONDS:
            logger.info(f"Cache HIT for key: {key}")
            return value
        del _cache[key]  # expired
    logger.info(f"Cache MISS for key: {key}")
    return None


def _set_cache(key: str, value):
    _cache[key] = (value, time.time())


# ── JSearch — Real Job Postings ────────────────────────────────────────────────

def fetch_job_postings(role: str, num_results: int = 10) -> str:
    """
    Fetches real job postings from JSearch API for the given role.
    Returns a formatted string ready to inject into an agent Task prompt.
    Falls back gracefully if the API call fails.

    Args:
        role:        target job role, e.g. "Data Engineer"
        num_results: how many postings to fetch (default 10)

    Returns:
        Formatted string of job postings with required skills extracted,
        or a fallback message if the API fails.
    """
    cache_key = f"jsearch:{role.lower().replace(' ', '_')}"
    cached = _get_cache(cache_key)
    if cached:
        return cached

    api_key = os.getenv("JSEARCH_API_KEY")
    if not api_key:
        logger.warning("JSEARCH_API_KEY not set — skipping job postings fetch")
        return "(Job postings unavailable — API key not configured)"

    headers = {
        "X-RapidAPI-Key": api_key,
        "X-RapidAPI-Host": "jsearch.p.rapidapi.com",
    }
    params = {
        "query": f"{role} jobs",
        "num_pages": "1",
        "date_posted": "month",
        "employment_types": "FULLTIME",
    }

    try:
        with httpx.Client(timeout=60.0) as client:
            response = client.get(
                "https://jsearch.p.rapidapi.com/search",
                headers=headers,
                params=params,
            )
            response.raise_for_status()
            data = response.json()

        jobs = data.get("data", [])[:num_results]

        if not jobs:
            logger.warning(f"JSearch returned 0 jobs for role='{role}'")
            return f"(No job postings found for '{role}' — using general market knowledge)"

        formatted_lines = []
        for i, job in enumerate(jobs, start=1):
            title   = job.get("job_title", "Unknown Title")
            company = job.get("employer_name", "Unknown Company")

            # Prefer structured skills field; fall back to hybrid extractor
            api_skills = job.get("job_required_skills") or []
            if isinstance(api_skills, list) and api_skills:
                skills_str = ", ".join(api_skills[:12])
            else:
                desc = job.get("job_description", "")
                extracted = extract_skills_from_description(desc)
                skills_str = ", ".join(extracted) if extracted else "Skills not clearly specified"

            # ✅ Bug fix: append is now always outside the if/else
            formatted_lines.append(
                f"Job {i}: {title} at {company}\n"
                f"  Required skills: {skills_str}"
            )

        result = "\n\n".join(formatted_lines)
        _set_cache(cache_key, result)
        logger.info(f"Fetched {len(jobs)} job postings for role='{role}'")
        return result

    except httpx.TimeoutException:
        logger.error(f"JSearch API timed out for role='{role}'")
        return "(Job postings unavailable — API timeout)"

    except httpx.HTTPStatusError as e:
        logger.error(f"JSearch API HTTP error: {e.response.status_code}")
        if e.response.status_code == 429:
            return "(Job postings unavailable — API rate limit reached)"
        return "(Job postings unavailable — API error)"

    except Exception as e:
        logger.exception(f"Unexpected error fetching job postings: {e}")
        return "(Job postings unavailable — unexpected error)"


# ── Adzuna — Real Salary Data ──────────────────────────────────────────────────

def fetch_salary_data(role: str) -> str:
    """
    Fetches real salary data from Adzuna for the given role.
    Returns a formatted string ready to inject into an agent Task prompt.
    Falls back gracefully if the API call fails.

    Args:
        role: target job role, e.g. "Data Engineer"

    Returns:
        Formatted salary data string, or fallback message.
    """
    cache_key = f"adzuna:{role.lower().replace(' ', '_')}"
    cached = _get_cache(cache_key)
    if cached:
        return cached

    app_id  = os.getenv("ADZUNA_APP_ID")
    app_key = os.getenv("ADZUNA_APP_KEY")

    if not app_id or not app_key:
        logger.warning("ADZUNA_APP_ID or ADZUNA_APP_KEY not set — skipping salary fetch")
        return "(Salary data unavailable — API credentials not configured)"

    params = {
        "app_id":           app_id,
        "app_key":          app_key,
        "what":             role,
        "results_per_page": 10,
    }

    try:
        with httpx.Client(timeout=60.0) as client:
            response = client.get(
                "https://api.adzuna.com/v1/api/jobs/us/search/1",
                params=params,
            )
            response.raise_for_status()
            data = response.json()

        jobs = data.get("results", [])

        if not jobs:
            logger.warning(f"Adzuna returned 0 results for role='{role}'")
            return f"(No salary data found for '{role}')"

        salaries = []
        for job in jobs:
            sal_min = job.get("salary_min")
            sal_max = job.get("salary_max")
            title   = job.get("title", "")
            if sal_min and sal_max:
                salaries.append({
                    "title": title,
                    "min":   int(sal_min),
                    "max":   int(sal_max),
                    "avg":   int((sal_min + sal_max) / 2),
                })

        if not salaries:
            return f"(Salary figures not available in Adzuna results for '{role}')"

        avg_min     = int(sum(s["min"] for s in salaries) / len(salaries))
        avg_max     = int(sum(s["max"] for s in salaries) / len(salaries))
        overall_avg = int((avg_min + avg_max) / 2)

        listings = "\n".join(
            f"  - {s['title']}: ${s['min']:,} – ${s['max']:,}/yr (avg ${s['avg']:,})"
            for s in salaries[:5]
        )

        result = (
            f"Salary data for '{role}' roles (US market, {len(salaries)} listings):\n"
            f"  Average range: ${avg_min:,} – ${avg_max:,}/yr\n"
            f"  Overall average: ${overall_avg:,}/yr\n\n"
            f"Individual listings:\n{listings}"
        )

        _set_cache(cache_key, result)
        logger.info(f"Fetched salary data for role='{role}': avg ${overall_avg:,}")
        return result

    except httpx.TimeoutException:
        logger.error(f"Adzuna API timed out for role='{role}'")
        return "(Salary data unavailable — API timeout)"

    except httpx.HTTPStatusError as e:
        logger.error(f"Adzuna API HTTP error: {e.response.status_code}")
        return "(Salary data unavailable — API error)"

    except Exception as e:
        logger.exception(f"Unexpected error fetching salary data: {e}")
        return "(Salary data unavailable — unexpected error)"