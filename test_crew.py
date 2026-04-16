# test_crew.py  (delete after Day 4 testing)
from services.crew_service import run_crew

print("=" * 60)
print("TESTING FULL 3-AGENT CREW PIPELINE")
print("This will take 30–90 seconds. Watch the verbose logs below.")
print("=" * 60)

# Use a simple, realistic test case
result = run_crew(
    skills="Python, SQL, Excel, basic statistics",
    goal="Data Engineer",
    experience="1-2 years"
)

print("\n" + "=" * 60)
print("AGENT 1 OUTPUT — Skill Gap Analysis")
print("=" * 60)
print(result["skill_gaps"])

print("\n" + "=" * 60)
print("AGENT 2 OUTPUT — Career Paths")
print("=" * 60)
print(result["career_paths"])

print("\n" + "=" * 60)
print("AGENT 3 OUTPUT — Learning Roadmap")
print("=" * 60)
print(result["roadmap"])

print("\n" + "=" * 60)
print(f"Total pipeline time: {result['response_time_sec']} seconds")
print("=" * 60)