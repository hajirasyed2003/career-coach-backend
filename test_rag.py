# test_rag.py  (delete after testing)
import logging
logging.basicConfig(level=logging.INFO)

from services.rag_service import seed_courses, find_courses

print("=" * 60)
print("STEP 1: Seed ChromaDB with course data")
print("=" * 60)
count = seed_courses()
print(f"Total courses in ChromaDB: {count}")

print("\n" + "=" * 60)
print("STEP 2: Test retrieval — Docker and Kubernetes gaps")
print("=" * 60)
results = find_courses("Docker, Kubernetes, container orchestration, DevOps")
print(results)

print("\n" + "=" * 60)
print("STEP 3: Test retrieval — Data Engineering gaps")
print("=" * 60)
results = find_courses("Apache Spark, Airflow, dbt, pipeline orchestration, big data")
print(results)

print("\n" + "=" * 60)
print("STEP 4: Test retrieval — ML Engineer gaps")
print("=" * 60)
results = find_courses("machine learning, TensorFlow, model deployment, MLOps")
print(results)

print("\n" + "=" * 60)
print("STEP 5: Test that second run skips re-seeding")
print("=" * 60)
count2 = seed_courses()  # should log 'skipping seed' and not regenerate embeddings
print(f"Count on second call: {count2}")