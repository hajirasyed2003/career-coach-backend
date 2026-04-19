# test_data_fetcher.py  (delete after testing)
from services.data_fetcher import fetch_job_postings, fetch_salary_data

print("=" * 60)
print("TEST 1: JSearch — Job Postings")
print("=" * 60)
job_data = fetch_job_postings("Data Engineer")
print(job_data)

print("\n" + "=" * 60)
print("TEST 2: Adzuna — Salary Data")
print("=" * 60)
salary_data = fetch_salary_data("Data Engineer")
print(salary_data)

print("\n" + "=" * 60)
print("TEST 3: Cache hit (second call should log 'Cache HIT')")
print("=" * 60)
job_data_again = fetch_job_postings("Data Engineer")
print("Length same as before:", len(job_data_again) == len(job_data))