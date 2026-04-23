# test_stress.py  (delete after testing)
import time
import logging
logging.basicConfig(level=logging.INFO)

from services.data_fetcher import fetch_job_postings, fetch_salary_data
from services.rag_service import seed_courses, find_courses
from services.crew_service import run_crew

# Ensure ChromaDB is seeded before stress testing
print("Ensuring ChromaDB is seeded...")
seed_courses()
print("ChromaDB ready\n")

TEST_PROFILES = [
    {
        "label": "Profile 1 — Junior Dev → Data Engineer",
        "skills": "Python, SQL, Excel, basic statistics",
        "goal": "Data Engineer",
        "experience": "1-2 years",
    },
    {
        "label": "Profile 2 — Frontend Dev → Full Stack",
        "skills": "React, JavaScript, HTML, CSS, Git",
        "goal": "Full Stack Developer",
        "experience": "2-3 years",
    },
    {
        "label": "Profile 3 — Analyst → ML Engineer",
        "skills": "Excel, SQL, basic Python, statistics, Tableau",
        "goal": "Machine Learning Engineer",
        "experience": "3-5 years",
    },
]

results = []

for profile in TEST_PROFILES:
    print("=" * 70)
    print(f"RUNNING: {profile['label']}")
    print("=" * 70)

    start = time.time()

    # Fetch real market data for this profile
    job_postings = fetch_job_postings(profile["goal"])
    salary_data  = fetch_salary_data(profile["goal"])

    result = run_crew(
        skills=profile["skills"],
        goal=profile["goal"],
        experience=profile["experience"],
        job_postings=job_postings,
        salary_data=salary_data,
    )

    elapsed = time.time() - start

    # Verification checks
    checks = {
        "skill_gaps has content":        len(result["skill_gaps"]) > 100,
        "skill_gaps mentions match %":   "%" in result["skill_gaps"],
        "career_paths has 3 paths":      result["career_paths"].count("Path") >= 3
                                         or result["career_paths"].count("1.") >= 1,
        "roadmap has week structure":    "Week" in result["roadmap"],
        "roadmap has URLs":              "http" in result["roadmap"],
        "response time under 120s":      result["response_time_sec"] < 120,
    }

    print(f"\nVerification checks for {profile['label']}:")
    all_passed = True
    for check, passed in checks.items():
        status = "PASS" if passed else "FAIL"
        print(f"  [{status}] {check}")
        if not passed:
            all_passed = False

    results.append({
        "profile": profile["label"],
        "all_passed": all_passed,
        "time": round(elapsed, 1),
    })

    print(f"\nTime taken: {round(elapsed, 1)}s")

    # Wait between profiles to avoid Groq rate limits
    if profile != TEST_PROFILES[-1]:
        print("\nWaiting 90 seconds before next profile (Groq rate limit)...")
        time.sleep(90)

# Summary
print("\n" + "=" * 70)
print("STRESS TEST SUMMARY")
print("=" * 70)
for r in results:
    status = "ALL PASS" if r["all_passed"] else "SOME FAILED"
    print(f"  {r['profile']}: {status} ({r['time']}s)")