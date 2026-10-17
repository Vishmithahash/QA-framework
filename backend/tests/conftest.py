import os

# Ensure a mock DATABASE_URL is present for all test collections and runs
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql://fake_user:fake_password@localhost:5432/fake_db?sslmode=require",
)
