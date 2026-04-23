# test_dbconnections.py — final version
import os
from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL

db_user     = os.getenv("DB_USER")
db_password = os.getenv("DB_PASSWORD")
db_host     = os.getenv("DB_HOST")
db_port     = int(os.getenv("DB_PORT", "6543"))
db_name     = os.getenv("DB_NAME", "postgres")

print("--- Connection components ---")
print(f"Host:     {db_host}")
print(f"Port:     {db_port}")
print(f"User:     {db_user}")
print(f"Password: {db_password}")  # should show Baragath@260879
print(f"Database: {db_name}")
print("----------------------------")

url = URL.create(
    drivername="postgresql+psycopg2",
    username=db_user,
    password=db_password,
    host=db_host,
    port=db_port,
    database=db_name,
)

try:
    engine = create_engine(
        url,
        pool_pre_ping=True,
        connect_args={
            "connect_timeout": 10,
            "prepare_threshold": None,
        },
    )
    with engine.connect() as conn:
        result = conn.execute(text("SELECT version()"))
        row = result.fetchone()
        print(f"\nSUCCESS — {row[0][:60]}")
except Exception as e:
    print(f"\nFAILED — {e}")