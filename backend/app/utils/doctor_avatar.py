"""Professional placeholder photos for doctors who have not uploaded a profile image."""
from __future__ import annotations

_CROP = "w=160&h=160&fit=crop&crop=face"

# Verified working Unsplash doctor headshots only.
_MALE_PLACEHOLDER_PHOTOS = [
    f"https://images.unsplash.com/photo-1612349317150-e413f6a5b16d?{_CROP}",
    f"https://images.unsplash.com/photo-1559839734-2b71ea197ec2?{_CROP}",
    f"https://images.unsplash.com/photo-1472099645785-5658abf4ff4e?{_CROP}",
    f"https://images.unsplash.com/photo-1560250097-0b93528c311a?{_CROP}",
    f"https://images.unsplash.com/photo-1576091160399-112ba8d25d1d?{_CROP}",
]

_FEMALE_PLACEHOLDER_PHOTOS = [
    f"https://images.unsplash.com/photo-1594824476967-48c8b964273f?{_CROP}",
    f"https://images.unsplash.com/photo-1551601651-2a8555f1a136?{_CROP}",
    f"https://images.unsplash.com/photo-1573496359142-b8d87734a5a2?{_CROP}",
    f"https://images.unsplash.com/photo-1584982751601-97dcc096659c?{_CROP}",
    f"https://images.unsplash.com/photo-1594824476967-48c8b964273f?{_CROP}&sat=-20",
]

_FEMALE_FIRST_NAMES = frozenset(
    {
        "anita", "priya", "meera", "kavita", "lakshmi", "deepa", "anjali", "neha", "pooja",
        "shalini", "divya", "ritu", "sneha", "nandini", "lata", "sunita", "pallavi", "rekha",
        "jyoti", "nisha", "swati", "radhika", "kiran", "ishita", "smita", "leela", "farah",
        "uma", "bharti", "shweta", "madhuri", "geeta", "parul", "alka", "christina",
    }
)


def is_legacy_cartoon_avatar(url: str | None) -> bool:
    if not url:
        return False
    lowered = url.lower()
    return "dicebear.com" in lowered or "avataaars" in lowered


def is_uploaded_profile_photo(url: str | None) -> bool:
    """True for real doctor uploads — not generated placeholders."""
    if not url or is_legacy_cartoon_avatar(url):
        return False
    lowered = url.lower()
    return "images.unsplash.com" not in lowered and "dicebear.com" not in lowered


def _pick_from_pool(seed: str, pool: list[str]) -> str:
    idx = sum(ord(ch) for ch in seed) % len(pool)
    return pool[idx]


def default_doctor_avatar_url(name: str, *, female: bool | None = None) -> str:
    """Deterministic professional headshot until the doctor uploads their own photo."""
    if female is None:
        first = name.replace("Dr.", "").strip().split()[0].lower() if name else ""
        female = first in _FEMALE_FIRST_NAMES
    pool = _FEMALE_PLACEHOLDER_PHOTOS if female else _MALE_PLACEHOLDER_PHOTOS
    return _pick_from_pool(name, pool)


def resolve_doctor_profile_image_url(name: str, url: str | None) -> str | None:
    """Use uploaded photo when present; otherwise return a professional placeholder."""
    if is_uploaded_profile_photo(url):
        return url
    if not name:
        return _MALE_PLACEHOLDER_PHOTOS[0]
    return default_doctor_avatar_url(name)
