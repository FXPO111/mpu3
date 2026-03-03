def can_access_offline(city_for_offline: str | None, requested_city: str | None) -> bool:
    if not city_for_offline:
        return True
    return city_for_offline.lower() == (requested_city or "").lower()