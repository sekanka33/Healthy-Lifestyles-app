from functools import lru_cache
from zoneinfo import available_timezones


@lru_cache
def _zones() -> frozenset[str]:
    return frozenset(available_timezones()) | {"UTC"}


def validate_timezone(v: str) -> str:
    """Accept only real IANA zone names (e.g. "Africa/Johannesburg")."""
    if v not in _zones():
        raise ValueError("Unknown time zone")
    return v
