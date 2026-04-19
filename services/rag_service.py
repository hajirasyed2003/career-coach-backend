# services/rag_service.py
import os
import json
import logging
from pathlib import Path

import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────────

# PersistentClient stores embeddings to disk so they survive server restarts.
# This path is relative to wherever you run uvicorn from (the backend root).
CHROMA_DB_PATH = "./chroma_db"
COLLECTION_NAME = "career_courses"

# all-MiniLM-L6-v2 is the sweet spot for this use case:
# - 384-dimensional vectors (small = fast)
# - Excellent semantic similarity for English text
# - Downloads ~90MB on first run, cached locally after that
EMBEDDING_MODEL = "all-MiniLM-L6-v2"

# Path to your course seed data
COURSES_DATA_PATH = Path(__file__).parent.parent / "data" / "courses.json"


# ── Module-level singletons ────────────────────────────────────────────────────
# These are created once when the module is first imported, then reused.
# Creating a SentenceTransformer model is expensive (~2 seconds) — you don't
# want to recreate it on every request.

_client: chromadb.PersistentClient = None
_collection: chromadb.Collection = None
_embedding_model: SentenceTransformer = None


def _get_embedding_model() -> SentenceTransformer:
    """Returns the singleton SentenceTransformer model, loading it on first call."""
    global _embedding_model
    if _embedding_model is None:
        logger.info(f"Loading embedding model '{EMBEDDING_MODEL}'...")
        _embedding_model = SentenceTransformer(EMBEDDING_MODEL)
        logger.info("Embedding model loaded successfully")
    return _embedding_model


def _get_collection() -> chromadb.Collection:
    """
    Returns the singleton ChromaDB collection.
    Creates the client and collection on first call.
    """
    global _client, _collection

    if _collection is None:
        logger.info(f"Initialising ChromaDB at path: {CHROMA_DB_PATH}")
        _client = chromadb.PersistentClient(
            path=CHROMA_DB_PATH,
            settings=Settings(anonymized_telemetry=False),
        )
        # get_or_create_collection: safe to call multiple times —
        # returns existing collection if it already exists on disk
        _collection = _client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},  # use cosine similarity (not L2)
        )
        logger.info(
            f"ChromaDB collection '{COLLECTION_NAME}' ready "
            f"({_collection.count()} documents)"
        )

    return _collection


# ── Seeding ────────────────────────────────────────────────────────────────────

def seed_courses(force_reseed: bool = False) -> int:
    """
    Loads courses from data/courses.json and inserts them into ChromaDB.
    Safe to call on every startup — skips seeding if collection already
    has documents (unless force_reseed=True).

    Args:
        force_reseed: if True, deletes existing collection and reseeds.
                      Use this when you update courses.json.

    Returns:
        Number of courses in the collection after seeding.
    """
    collection = _get_collection()
    model = _get_embedding_model()

    existing_count = collection.count()

    if existing_count > 0 and not force_reseed:
        logger.info(
            f"ChromaDB already has {existing_count} courses — skipping seed. "
            f"Run seed_courses(force_reseed=True) to re-seed."
        )
        return existing_count

    if force_reseed and existing_count > 0:
        logger.info("force_reseed=True — deleting existing collection and re-seeding")
        _client.delete_collection(COLLECTION_NAME)
        # Re-create after deletion
        global _collection
        _collection = _client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
        collection = _collection

    # Load course data
    if not COURSES_DATA_PATH.exists():
        raise FileNotFoundError(
            f"Course data file not found at {COURSES_DATA_PATH}. "
            f"Create data/courses.json before seeding."
        )

    with open(COURSES_DATA_PATH, "r") as f:
        courses = json.load(f)

    logger.info(f"Seeding {len(courses)} courses into ChromaDB...")

    # Prepare data for batch insertion
    ids        = [c["id"] for c in courses]
    # The 'skills' field is what gets embedded — it's the searchable text
    documents  = [c["skills"] for c in courses]
    metadatas  = [
        {
            "title":          c["title"],
            "platform":       c["platform"],
            "url":            c["url"],
            "level":          c["level"],
            "duration_hours": str(c["duration_hours"]),  # ChromaDB requires str metadata
            "free":           str(c["free"]),
        }
        for c in courses
    ]

    # Generate embeddings for all courses at once (batch is faster than one-by-one)
    logger.info("Generating embeddings for all courses...")
    embeddings = model.encode(documents, show_progress_bar=True).tolist()
    logger.info(f"Generated {len(embeddings)} embeddings, each with "
                f"{len(embeddings[0])} dimensions")

    # Insert everything into ChromaDB
    collection.add(
        ids=ids,
        documents=documents,
        embeddings=embeddings,
        metadatas=metadatas,
    )

    final_count = collection.count()
    logger.info(f"Seeding complete — {final_count} courses now in ChromaDB")
    return final_count


# ── Querying ───────────────────────────────────────────────────────────────────

def find_courses(skill_gaps: str, n_results: int = 5) -> str:
    """
    Finds the most relevant courses for the given skill gaps using
    semantic similarity search in ChromaDB.

    Args:
        skill_gaps: a text description of the user's skill gaps,
                    e.g. "Docker, Kubernetes, Apache Spark, Airflow"
                    This is typically Agent 1's output or the critical_gaps section.
        n_results: number of courses to return (default 5)

    Returns:
        Formatted string of course recommendations ready to inject into
        Agent 3's Task prompt.
    """
    collection = _get_collection()
    model = _get_embedding_model()

    if collection.count() == 0:
        logger.warning("ChromaDB collection is empty — run seed_courses() first")
        return "(Course recommendations unavailable — knowledge base not seeded)"

    # Convert skill gaps text into a query vector
    logger.info(f"Querying ChromaDB for: '{skill_gaps[:80]}...'")
    query_embedding = model.encode([skill_gaps]).tolist()

    # Query ChromaDB — returns n_results closest vectors
    results = collection.query(
        query_embeddings=query_embedding,
        n_results=min(n_results, collection.count()),  # can't request more than exist
        include=["metadatas", "distances"],             # distances = similarity scores
    )

    metadatas = results["metadatas"][0]   # list of metadata dicts
    distances = results["distances"][0]   # list of distances (lower = more similar)

    if not metadatas:
        return "(No relevant courses found for the identified skill gaps)"

    # Format results for prompt injection
    formatted_lines = []
    for i, (meta, dist) in enumerate(zip(metadatas, distances), start=1):
        # Convert cosine distance to similarity percentage for readability
        # distance=0 means identical, distance=2 means opposite
        # For cosine space: similarity = 1 - (distance / 2) gives 0–1 range
        similarity_pct = round((1 - dist / 2) * 100)

        formatted_lines.append(
            f"Course {i}: {meta['title']}\n"
            f"  Platform: {meta['platform']}\n"
            f"  URL: {meta['url']}\n"
            f"  Level: {meta['level']} | "
            f"Duration: ~{meta['duration_hours']} hours | "
            f"Free: {meta['free']}\n"
            f"  Relevance: {similarity_pct}%"
        )

    formatted = "\n\n".join(formatted_lines)
    logger.info(f"Found {len(metadatas)} relevant courses for skill gaps")
    return formatted