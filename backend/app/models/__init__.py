"""Import every model so Base.metadata is complete (used by Alembic and tests)."""

from app.models.admin import AdminSession, AdminUser, AuditLog
from app.models.analytics import UserActivityDay
from app.models.billing import EmailMessage, Job, PaymentTransaction, SubscriptionEntitlement, WebhookEvent
from app.models.fitness import FitnessGoal, HealthConnection, Workout, WorkoutPoint
from app.models.hydration import HydrationEntry, HydrationGoal
from app.models.integrations import (
    ActivityRecommendation,
    CalendarEventRecord,
    OAuthConnection,
    OAuthState,
    WeatherCache,
)
from app.models.medication import Medication, MedicationDose
from app.models.user import (
    EmailPreferences,
    NotificationPreferences,
    OneTimeCode,
    RateLimitBucket,
    RefreshToken,
    User,
    UserPreferences,
)

__all__ = [
    "AdminSession", "AdminUser", "AuditLog", "UserActivityDay",
    "ActivityRecommendation", "CalendarEventRecord", "EmailMessage", "EmailPreferences", "FitnessGoal",
    "HealthConnection", "HydrationEntry", "HydrationGoal", "Job", "Medication", "MedicationDose",
    "NotificationPreferences", "OAuthConnection", "OAuthState", "OneTimeCode", "PaymentTransaction",
    "RateLimitBucket", "RefreshToken", "SubscriptionEntitlement", "User", "UserPreferences",
    "WeatherCache", "WebhookEvent", "Workout", "WorkoutPoint",
]
