# services/crew_service.py
import time
from crewai import Crew, Task, Process
from agents.skill_agent import create_skill_analyzer
from agents.market_agent import create_market_advisor
from agents.roadmap_agent import create_roadmap_planner


def run_crew(skills: str, goal: str, experience: str) -> dict:
    """
    The main entry point called by main.py's /career/analyze endpoint.

    Creates agents fresh per request (stateless — important for production).
    Builds 3 Tasks with real prompt instructions.
    Runs them sequentially via CrewAI.
    Returns a dict with all three outputs.

    Args:
        skills: comma-separated user skills, e.g. "Python, SQL, Excel"
        goal: target career role, e.g. "Data Engineer"
        experience: experience level, e.g. "1-2 years"

    Returns:
        dict with keys: skill_gaps, career_paths, roadmap, response_time_sec
    """

    start_time = time.time()

    # ── 1. Instantiate agents ─────────────────────────────────────────────────
    # Fresh agents per request ensures no state leaks between users
    skill_agent   = create_skill_analyzer()
    market_agent  = create_market_advisor()
    roadmap_agent = create_roadmap_planner()

    # ── 2. Define Task 1 — Skill Gap Analysis ─────────────────────────────────
    # The description IS the prompt content for this task.
    # {skills}, {goal}, {experience} are filled in from function args above.
    # "expected_output" guides the agent on format — not enforced, but strongly followed.
    task1 = Task(
        description=f"""
        You are analyzing a job seeker's skills for their target role.

        USER PROFILE:
        - Current skills: {skills}
        - Target career role: {goal}
        - Experience level: {experience}

        YOUR ANALYSIS TASK:
        1. Identify which of the user's skills are directly relevant to {goal} roles (strengths)
        2. Identify the critical skills that {goal} roles require but the user is MISSING (critical gaps)
        3. Identify secondary/nice-to-have skills that would strengthen their profile (secondary gaps)
        4. Calculate a skill match percentage (0-100%) based on how many required skills they have

        Be specific. Do not list generic skills like "communication" or "problem-solving".
        Focus only on technical and domain-specific skills relevant to {goal}.
        """,

        expected_output="""
        A structured skill gap analysis containing:
        - Match percentage score (e.g. "Match Score: 45%")
        - Strengths: list of user's relevant existing skills (bullet points)
        - Critical Gaps: list of must-have missing skills with brief explanation of why each matters
        - Secondary Gaps: list of nice-to-have skills
        - Brief summary paragraph (2-3 sentences) explaining the overall situation
        """,

        agent=skill_agent,
    )

    # ── 3. Define Task 2 — Career Path Recommendations ────────────────────────
    # CrewAI automatically appends Task 1's output to this task's context.
    # The agent will see the full skill gap analysis when it runs.
    task2 = Task(
        description=f"""
        Based on the skill gap analysis above, recommend career paths for this user.

        USER PROFILE:
        - Current skills: {skills}
        - Target career role: {goal}
        - Experience level: {experience}

        YOUR TASK:
        Recommend exactly 3 career paths that are realistic given the user's current skills
        and the identified gaps. The paths should range from most achievable (using existing
        skills) to most ambitious (requiring significant upskilling).

        For each career path provide:
        1. Job title
        2. Salary range (annual, in USD)
        3. Top 5 required skills for this role
        4. Estimated time to qualify from user's current level (in months)
        5. Difficulty rating: Easy / Moderate / Challenging
        6. One sentence on why this path suits the user's profile
        """,

        expected_output="""
        Exactly 3 career path recommendations, each formatted clearly with:
        - Path title/job role
        - Salary range
        - Required skills list
        - Time to qualify
        - Difficulty rating
        - Why it suits this user
        """,

        agent=market_agent,
    )

    # ── 4. Define Task 3 — Learning Roadmap ───────────────────────────────────
    # This agent sees Task 1 output (skill gaps) AND Task 2 output (career paths).
    # It uses both to build a targeted, progressive learning plan.
    task3 = Task(
        description=f"""
        Using the skill gap analysis and career path recommendations above,
        build a structured 8-week learning roadmap for this user.

        USER PROFILE:
        - Current skills: {skills}
        - Target career role: {goal}
        - Experience level: {experience}
        - Available study time: approximately 1-2 hours per day

        YOUR TASK:
        Create a week-by-week learning plan that:
        1. Addresses the critical skill gaps identified in the analysis
        2. Builds progressively (foundation skills first, advanced skills later)
        3. Includes specific learning resources for each week
        4. Includes a hands-on mini-project for each week to apply learning
        5. Is realistic for someone studying 1-2 hours per day

        Focus on free or widely available resources (YouTube, official docs,
        freeCodeCamp, fast.ai, etc.) — not paid courses unless they are industry standard.
        """,

        expected_output="""
        An 8-week structured learning roadmap with each week containing:
        - Week number and focus area title
        - Learning objectives for the week (2-3 bullet points)
        - Specific resources (name the resource, not just the category)
        - Mini-project to build/practice that week's skills
        - Estimated daily time commitment

        End with a brief encouragement paragraph and next steps after week 8.
        """,

        agent=roadmap_agent,
    )

    # ── 5. Assemble and run the Crew ──────────────────────────────────────────
    crew = Crew(
        agents=[skill_agent, market_agent, roadmap_agent],
        tasks=[task1, task2, task3],
        process=Process.sequential,  # task1 → task2 → task3, each seeing previous outputs
        verbose=True,                # prints crew-level orchestration logs to terminal
    )

    # This is the blocking call — takes 30–90 seconds.
    # On Day 5 you'll run this in a FastAPI background task.
    crew_output = crew.kickoff()

    elapsed = round(time.time() - start_time, 2)

    # ── 6. Extract outputs ────────────────────────────────────────────────────
    # crew_output.tasks_output is a list matching your tasks list order
    # Each element has a .raw attribute containing the agent's full text response
    return {
        "skill_gaps":    crew_output.tasks_output[0].raw,
        "career_paths":  crew_output.tasks_output[1].raw,
        "roadmap":       crew_output.tasks_output[2].raw,
        "response_time_sec": elapsed,
    }