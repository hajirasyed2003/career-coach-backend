# services/crew_service.py
import time
import logging
from crewai import Crew, Task, Process
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)
from groq import RateLimitError, APIError

from agents.skill_agent import create_skill_analyzer
from agents.market_agent import create_market_advisor
from agents.roadmap_agent import create_roadmap_planner
from services.rag_service import find_courses  # NEW — added Day 8

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def build_tasks_1_2(
    skill_agent,
    market_agent,
    skills: str,
    goal: str,
    experience: str,
    job_postings: str = "",
    salary_data: str = "",
) -> list:
    """
    Builds Task 1 (Skill Analyzer) and Task 2 (Market Advisor) only.
    These run first so their outputs can be extracted before RAG is called.

    Renamed from build_tasks() on Day 8 to support the two-phase crew approach.
    The original build_tasks() logic is preserved here exactly — only the
    function name and task3 removal changed.
    """
    job_context = (
        f"\n\nREAL JOB MARKET DATA (from live job postings):\n{job_postings}"
        if job_postings else
        "\n\n(Note: Using general market knowledge — real job data will be added in next phase)"
    )

    salary_context = (
        f"\n\nREAL SALARY DATA:\n{salary_data}"
        if salary_data else
        "\n\n(Note: Provide general salary estimates based on market knowledge)"
    )

    task1 = Task(
        description=f"""
        Analyze this job seeker's skills for their target role.

        USER PROFILE:
        - Current skills: {skills}
        - Target career role: {goal}
        - Experience level: {experience}
        {job_context}

        YOUR ANALYSIS TASK:
        1. Identify which of the user's skills are directly relevant to {goal} (strengths)
        2. Identify the critical skills that {goal} roles require but the user is MISSING
        3. Identify secondary/nice-to-have skills (secondary gaps)
        4. Calculate a skill match percentage (0–100%)

        Be specific. Focus on technical and domain-specific skills only.
        """,
        expected_output="""
        Structured skill gap analysis with:
        - Match Score percentage
        - Strengths: bullet list of relevant existing skills
        - Critical Gaps: must-have missing skills with explanation
        - Secondary Gaps: nice-to-have missing skills
        - Summary paragraph (2-3 sentences)
        """,
        agent=skill_agent,
    )

    task2 = Task(
        description=f"""
        Based on the skill gap analysis above, recommend career paths.

        USER PROFILE:
        - Current skills: {skills}
        - Target career role: {goal}
        - Experience level: {experience}
        {salary_context}

        Recommend exactly 3 realistic career paths ranging from most achievable
        to most ambitious. For each path provide:
        1. Job title
        2. Salary range (annual USD)
        3. Top 5 required skills
        4. Estimated months to qualify from current level
        5. Difficulty: Easy / Moderate / Challenging
        6. One sentence on why this suits the user
        """,
        expected_output="""
        Exactly 3 career paths, each with:
        job title, salary range, required skills, time to qualify,
        difficulty rating, and fit explanation.
        """,
        agent=market_agent,
    )

    return [task1, task2]


def build_task_3(
    roadmap_agent,
    skills: str,
    goal: str,
    experience: str,
    skill_gaps_output: str,
    career_paths_output: str,
    course_recommendations: str,
) -> Task:
    """
    Builds Task 3 (Roadmap Planner) with RAG course recommendations injected.
    Called AFTER Tasks 1 and 2 have run and their outputs are available as strings,
    and AFTER find_courses() has been called with the skill gaps.

    New on Day 8 — previously task3 was part of build_tasks().
    """
    return Task(
        description=f"""
        Using the skill gap analysis, career paths, AND real course recommendations
        below, build a structured 8-week learning roadmap.

        USER PROFILE:
        - Current skills: {skills}
        - Target career role: {goal}
        - Experience level: {experience}
        - Study time available: 1–2 hours per day

        SKILL GAP ANALYSIS (from Agent 1):
        {skill_gaps_output}

        CAREER PATH RECOMMENDATIONS (from Agent 2):
        {career_paths_output}

        REAL COURSE RECOMMENDATIONS (retrieved from knowledge base):
        {course_recommendations}

        REQUIREMENTS FOR THE ROADMAP:
        - Address critical gaps identified above in priority order
        - Build progressively (foundation → advanced)
        - Use the specific courses listed above where relevant — include their URLs
        - Include one hands-on mini-project per week
        - Keep it realistic for 1–2 hours/day
        - Week 1 should always start with the most foundational gap
        """,
        expected_output="""
        8-week roadmap where each week has:
        - Week number and focus title
        - 2-3 learning objectives
        - Named specific resources (use the courses provided above with their URLs)
        - One mini-project
        - Estimated daily time

        End with a brief next-steps paragraph for after week 8.
        """,
        agent=roadmap_agent,
    )


@retry(
    retry=retry_if_exception_type(RateLimitError),
    wait=wait_exponential(multiplier=1, min=10, max=60),
    stop=stop_after_attempt(3),
)
def _run_crew_with_retry(crew: Crew) -> object:
    """
    Wraps crew.kickoff() with retry logic.
    If Groq returns a 429 RateLimitError, waits 10s then 20s then 40s before giving up.
    Decorated separately so tenacity can retry just the kickoff call.
    Unchanged from Day 5.
    """
    return crew.kickoff()


def run_crew(
    skills: str,
    goal: str,
    experience: str,
    job_postings: str = "",
    salary_data: str = "",
) -> dict:
    """
    Main entry point called by main.py.

    Two-phase approach introduced on Day 8:
      Phase 1 — Run Tasks 1 and 2 (Skill Analyzer + Market Advisor)
      RAG     — Call find_courses() with Agent 1's skill gap output
      Phase 2 — Run Task 3 (Roadmap Planner) with RAG results injected

    The function signature is unchanged from Day 6 — main.py needs no updates.
    """
    start_time = time.time()
    logger.info(f"Starting crew pipeline for goal='{goal}'")

    # Instantiate fresh agents per request (stateless — important for concurrency)
    skill_agent   = create_skill_analyzer()
    market_agent  = create_market_advisor()
    roadmap_agent = create_roadmap_planner()

    # ── Phase 1: Run Tasks 1 and 2 ────────────────────────────────────────────
    # We need Agent 1's skill gap text as a string before we can query ChromaDB.
    # Running Tasks 1 and 2 as their own crew gives us that intermediate output.
    logger.info("Phase 1: Running Skill Analyzer and Market Advisor agents...")

    tasks_1_2 = build_tasks_1_2(
        skill_agent=skill_agent,
        market_agent=market_agent,
        skills=skills,
        goal=goal,
        experience=experience,
        job_postings=job_postings,
        salary_data=salary_data,
    )

    partial_crew = Crew(
        agents=[skill_agent, market_agent],
        tasks=tasks_1_2,
        process=Process.sequential,
        verbose=True,
    )

    partial_output = _run_crew_with_retry(partial_crew)

    skill_gaps_output   = partial_output.tasks_output[0].raw
    career_paths_output = partial_output.tasks_output[1].raw

    logger.info("Phase 1 complete — skill gaps and career paths generated")

    # ── RAG: Query ChromaDB with real skill gap text ───────────────────────────
    # Agent 1's output is used directly as the semantic search query.
    # ChromaDB finds the 5 most semantically similar courses from courses.json.
    logger.info("Querying ChromaDB for course recommendations...")
    course_recommendations = find_courses(skill_gaps_output, n_results=5)
    logger.info("Course recommendations retrieved from ChromaDB")

    # ── Phase 2: Run Task 3 with RAG-enriched context ─────────────────────────
    # Agent 3 now sees Agent 1 output + Agent 2 output + real course URLs.
    # This is what makes the roadmap cite specific courses instead of generic advice.
    logger.info("Phase 2: Running Roadmap Planner agent with RAG context...")

    task3 = build_task_3(
        roadmap_agent=roadmap_agent,
        skills=skills,
        goal=goal,
        experience=experience,
        skill_gaps_output=skill_gaps_output,
        career_paths_output=career_paths_output,
        course_recommendations=course_recommendations,
    )

    final_crew = Crew(
        agents=[roadmap_agent],
        tasks=[task3],
        process=Process.sequential,
        verbose=True,
    )

    final_output = _run_crew_with_retry(final_crew)
    roadmap_output = final_output.tasks_output[0].raw

    elapsed = round(time.time() - start_time, 2)
    logger.info(f"Full pipeline complete in {elapsed}s")

    # Return dict shape is identical to Day 5/6 — main.py needs no changes
    return {
        "skill_gaps":        skill_gaps_output,
        "career_paths":      career_paths_output,
        "roadmap":           roadmap_output,
        "response_time_sec": elapsed,
    }