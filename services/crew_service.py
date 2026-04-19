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

# Set up logging — prints to terminal with timestamps
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def build_tasks(skill_agent, market_agent, roadmap_agent,
                skills: str, goal: str, experience: str,
                job_postings: str = "", salary_data: str = "") -> list:
    """
    Builds the 3 Task objects.
    Separated from run_crew() so Day 6 can pass job_postings and salary_data
    into the task descriptions without changing the run logic.

    job_postings and salary_data default to empty string for Day 5.
    On Day 6, real data strings will be passed in from data_fetcher.py.
    """

    # Prepare context strings — empty on Day 5, real data on Day 6
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

    task3 = Task(
        description=f"""
        Using the skill gaps and career paths above, build an 8-week learning roadmap.

        USER PROFILE:
        - Current skills: {skills}
        - Target career role: {goal}
        - Experience level: {experience}
        - Study time available: 1–2 hours per day

        Requirements:
        - Address critical gaps identified in the analysis
        - Build progressively (foundation → advanced)
        - Name specific free resources (YouTube channels, official docs, freeCodeCamp, fast.ai)
        - Include one hands-on mini-project per week
        - Keep it realistic for 1–2 hours/day
        """,
        expected_output="""
        8-week roadmap where each week has:
        - Week number and focus title
        - 2-3 learning objectives
        - Named specific resources
        - One mini-project
        - Estimated daily time

        End with a brief next-steps paragraph for after week 8.
        """,
        agent=roadmap_agent,
    )

    return [task1, task2, task3]


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
    Day 5: job_postings and salary_data are empty strings.
    Day 6: real data strings are passed in from data_fetcher.py.
    """
    start_time = time.time()

    logger.info(f"Starting crew pipeline for goal='{goal}'")

    # Instantiate fresh agents per request
    skill_agent   = create_skill_analyzer()
    market_agent  = create_market_advisor()
    roadmap_agent = create_roadmap_planner()

    # Build tasks (with or without real data injected)
    tasks = build_tasks(
        skill_agent, market_agent, roadmap_agent,
        skills, goal, experience,
        job_postings, salary_data,
    )

    crew = Crew(
        agents=[skill_agent, market_agent, roadmap_agent],
        tasks=tasks,
        process=Process.sequential,
        verbose=True,
    )

    # Run with automatic retry on rate limit
    crew_output = _run_crew_with_retry(crew)

    elapsed = round(time.time() - start_time, 2)
    logger.info(f"Crew pipeline completed in {elapsed}s")

    return {
        "skill_gaps":        crew_output.tasks_output[0].raw,
        "career_paths":      crew_output.tasks_output[1].raw,
        "roadmap":           crew_output.tasks_output[2].raw,
        "response_time_sec": elapsed,
    }