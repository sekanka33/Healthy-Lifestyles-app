import os

# Tests must never touch a real database, mail server or third-party API.
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("EMAIL_PROVIDER", "disabled")
os.environ.setdefault("JWT_SECRET", "test-secret-test-secret-test-secret")
