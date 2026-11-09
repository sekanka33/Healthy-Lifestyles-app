"""Role-based access control for the admin dashboard. The backend is the only enforcement point:
every admin endpoint declares the permission it needs via `require_permission(...)`.

Permission names mirror `admin/src/nav.ts`. Add a permission here first, then use it.
"""

PERMISSIONS: dict[str, str] = {
    "dashboard.read": "View the overview dashboard (revenue figures also need payments.read)",
    "users.read": "View user accounts (no health records)",
    "users.manage": "Suspend and reactivate user accounts",
    "users.delete": "Permanently delete user accounts",
    "subscriptions.read": "View subscriptions and their history",
    "payments.read": "View payments, revenue and refunds",
    "plans.read": "View the plan catalogue",
    "plans.manage": "Change plans and advertised pricing",
    "features.read": "View aggregated feature usage (water, medication, fitness)",
    "emails.read": "View email delivery logs and templates",
    "emails.resend": "Resend eligible emails",
    "analytics.read": "View analytics",
    "reports.read": "View reports",
    "reports.export": "Export CSV / PDF reports",
    "support.read": "View support tickets and feedback",
    "support.manage": "Update and respond to support tickets",
    "system.read": "View API and system health",
    "admins.manage": "Create admins and change roles",
    "audit.read": "View audit logs",
    "settings.read": "View application settings",
    "settings.manage": "Change application settings",
}

ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "owner": frozenset(PERMISSIONS),
    "admin": frozenset({
        "dashboard.read", "users.read", "users.manage", "subscriptions.read", "plans.read",
        "features.read", "emails.read", "emails.resend", "analytics.read", "reports.read", "reports.export",
        "support.read", "support.manage", "system.read", "settings.read",
    }),
    "support": frozenset({"dashboard.read", "users.read", "support.read", "support.manage", "emails.read"}),
    "finance": frozenset({
        "dashboard.read", "subscriptions.read", "payments.read", "plans.read", "analytics.read",
        "reports.read", "reports.export",
    }),
    "technical": frozenset({"dashboard.read", "system.read", "features.read", "emails.read", "audit.read"}),
}

ROLE_LABELS = {
    "owner": "Owner",
    "admin": "Admin",
    "support": "Support Agent",
    "finance": "Finance Manager",
    "technical": "Technical Admin",
}


def permissions_for(role: str) -> frozenset[str]:
    return ROLE_PERMISSIONS.get(role, frozenset())


def has_permission(role: str, permission: str) -> bool:
    if permission not in PERMISSIONS:  # a typo must fail closed, loudly
        raise ValueError(f"Unknown admin permission: {permission}")
    return permission in permissions_for(role)
