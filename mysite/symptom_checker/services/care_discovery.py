from __future__ import annotations

import json
from urllib import error as urlerror
from urllib import parse as urlparse
from urllib import request as urlrequest

from django.conf import settings


def discover_nearby_care_centers(
    *, location: str, specialty: str = "", limit: int = 24, radius_m: int = 5000
) -> list[dict]:
    provider = (getattr(settings, "CARE_DISCOVERY_PROVIDER", "osm") or "osm").strip().lower()
    providers = {
        "osm": _discover_osm,
        "here": _discover_here,
        "tomtom": _discover_tomtom,
    }
    order = [provider] + [name for name in ("osm", "here", "tomtom") if name != provider]

    seen: set[str] = set()
    merged: list[dict] = []
    for name in order:
        fn = providers.get(name)
        if not fn:
            continue
        rows = fn(location=location, specialty=specialty, limit=limit, radius_m=radius_m)
        for row in rows:
            key = f"{str(row.get('name') or '').strip().lower()}|{str(row.get('city') or '').strip().lower()}"
            if not key or key in seen:
                continue
            seen.add(key)
            merged.append(row)
            if len(merged) >= limit:
                return merged
    return merged


def geocode_location(location: str) -> tuple[float, float] | None:
    return _nominatim_geocode(location)


def suggest_locations(query: str, *, limit: int = 6) -> list[str]:
    cleaned = (query or "").strip()
    if len(cleaned) < 2:
        return []
    max_items = max(4, min(limit, 20))
    queries = [
        {"q": cleaned, "countrycodes": "in"},
        {"q": f"{cleaned}, India", "countrycodes": "in"},
        {"q": cleaned},
    ]
    suggestions: list[str] = []
    seen: set[str] = set()
    for query_params in queries:
        params = {
            **query_params,
            "format": "jsonv2",
            "addressdetails": 1,
            "limit": max_items,
        }
        url = "https://nominatim.openstreetmap.org/search?" + urlparse.urlencode(params)
        payload = _fetch_json(url)
        if not isinstance(payload, list):
            continue
        for row in payload:
            label = (row.get("display_name") or "").strip()
            if not label:
                continue
            key = label.lower()
            if key in seen:
                continue
            seen.add(key)
            suggestions.append(label)
            if len(suggestions) >= max_items:
                return suggestions
    return suggestions


def _discover_osm(*, location: str, specialty: str, limit: int, radius_m: int) -> list[dict]:
    center = _nominatim_geocode(location)
    if not center:
        return []

    lat, lon = center
    radius_m = max(500, min(int(radius_m or 5000), 50000))
    overpass_query = f"""
[out:json][timeout:20];
(
  node(around:{radius_m},{lat},{lon})["amenity"="clinic"];
  way(around:{radius_m},{lat},{lon})["amenity"="clinic"];
  relation(around:{radius_m},{lat},{lon})["amenity"="clinic"];
  node(around:{radius_m},{lat},{lon})["healthcare"="clinic"];
  way(around:{radius_m},{lat},{lon})["healthcare"="clinic"];
  relation(around:{radius_m},{lat},{lon})["healthcare"="clinic"];
  node(around:{radius_m},{lat},{lon})["healthcare"="hospital"];
  way(around:{radius_m},{lat},{lon})["healthcare"="hospital"];
  relation(around:{radius_m},{lat},{lon})["healthcare"="hospital"];
  node(around:{radius_m},{lat},{lon})["amenity"="hospital"];
  way(around:{radius_m},{lat},{lon})["amenity"="hospital"];
  relation(around:{radius_m},{lat},{lon})["amenity"="hospital"];
  node(around:{radius_m},{lat},{lon})["healthcare"="centre"];
  way(around:{radius_m},{lat},{lon})["healthcare"="centre"];
  relation(around:{radius_m},{lat},{lon})["healthcare"="centre"];
);
out center {max(60, min(limit * 12, 300))};
"""
    payload = _fetch_overpass(overpass_query)
    elements = payload.get("elements") or []
    centers: list[tuple[float, dict]] = []
    seen: set[str] = set()
    for el in elements:
        tags = el.get("tags") or {}
        name = (tags.get("name") or "").strip() or "Nearby Clinic"
        city = tags.get("addr:city") or tags.get("addr:state") or location
        spec_hint = (
            tags.get("healthcare:speciality")
            or tags.get("healthcare:speciality:en")
            or tags.get("description")
            or specialty
            or "General Medicine"
        )
        facility_type = (
            tags.get("healthcare")
            or tags.get("amenity")
            or "clinic"
        )
        key = f"{name.lower()}|{str(city).lower()}"
        if key in seen:
            continue

        seen.add(key)

        center_point = el.get("center") or {}
        el_lat = el.get("lat", center_point.get("lat"))
        el_lon = el.get("lon", center_point.get("lon"))
        distance_km = _distance_km(lat, lon, el_lat, el_lon)
        if distance_km > (radius_m / 1000.0):
            continue

        centers.append(
            (
                distance_km,
                {
                    "name": name,
                    "specialization": str(spec_hint).strip()[:80],
                    "facility_type": str(facility_type).strip()[:40],
                    "city": str(city).strip()[:80],
                    "phone": (tags.get("phone") or tags.get("contact:phone") or "N/A").strip(),
                    "email": (tags.get("email") or tags.get("contact:email") or "N/A").strip(),
                    "latitude": el_lat,
                    "longitude": el_lon,
                    "distance_km": round(distance_km, 2),
                    "map_search_url": _osm_map_link(el_lat, el_lon, name, str(city)),
                    "source": "OpenStreetMap",
                },
            )
        )

    centers.sort(key=lambda row: row[0])
    return [row[1] for row in centers[:limit]]


def _discover_here(*, location: str, specialty: str, limit: int, radius_m: int) -> list[dict]:
    api_key = (getattr(settings, "HERE_API_KEY", "") or "").strip()
    if not api_key:
        return []

    center = _nominatim_geocode(location)
    if not center:
        return []
    lat, lon = center

    query = "clinic hospital"
    params = {
        "apiKey": api_key,
        "q": query,
        "at": f"{lat},{lon}",
        "limit": max(1, min(limit * 2, 50)),
    }
    url = "https://discover.search.hereapi.com/v1/discover?" + urlparse.urlencode(params)
    payload = _fetch_json(url)
    items = payload.get("items") or []
    centers: list[dict] = []
    for item in items:
        position = item.get("position") or {}
        address = item.get("address") or {}
        categories = item.get("categories") or []
        facility_type = (categories[0].get("name") if categories and isinstance(categories[0], dict) else "Clinic/Hospital")
        distance_km = _distance_km(lat, lon, position.get("lat"), position.get("lng"))
        if distance_km > (radius_m / 1000.0):
            continue
        centers.append(
            {
                "name": (item.get("title") or "Nearby Clinic").strip(),
                "specialization": "General Care",
                "facility_type": str(facility_type).strip(),
                "city": (address.get("city") or address.get("county") or location).strip(),
                "phone": _first_phone(item) or "N/A",
                "email": "N/A",
                "latitude": position.get("lat"),
                "longitude": position.get("lng"),
                "distance_km": round(distance_km, 2),
                "map_search_url": item.get("href")
                or _map_search_link(item.get("title", ""), address.get("label", location)),
                "source": "HERE Places",
            }
        )
    centers.sort(key=lambda row: row.get("distance_km", 9999))
    return centers[:limit]


def _discover_tomtom(*, location: str, specialty: str, limit: int, radius_m: int) -> list[dict]:
    api_key = (getattr(settings, "TOMTOM_API_KEY", "") or "").strip()
    if not api_key:
        return []

    center = _nominatim_geocode(location)
    if not center:
        return []
    lat, lon = center

    query = urlparse.quote("clinic hospital")
    params = {
        "key": api_key,
        "countrySet": "IN",
        "lat": lat,
        "lon": lon,
        "radius": max(500, min(int(radius_m or 5000), 10000)),
        "limit": max(1, min(limit * 2, 50)),
    }
    url = f"https://api.tomtom.com/search/2/poiSearch/{query}.json?" + urlparse.urlencode(params)
    payload = _fetch_json(url)
    results = payload.get("results") or []
    centers: list[dict] = []
    for row in results:
        address = row.get("address") or {}
        pos = row.get("position") or {}
        poi = row.get("poi") or {}
        distance_km = _distance_km(lat, lon, pos.get("lat"), pos.get("lon"))
        if distance_km > (radius_m / 1000.0):
            continue
        centers.append(
            {
                "name": (poi.get("name") or "Nearby Clinic").strip(),
                "specialization": "General Care",
                "facility_type": (poi.get("categories", ["Clinic/Hospital"])[0] if isinstance(poi.get("categories"), list) and poi.get("categories") else "Clinic/Hospital"),
                "city": (address.get("municipality") or location).strip(),
                "phone": "N/A",
                "email": "N/A",
                "latitude": pos.get("lat"),
                "longitude": pos.get("lon"),
                "distance_km": round(distance_km, 2),
                "map_search_url": _map_search_link(
                    poi.get("name", ""),
                    address.get("freeformAddress", location),
                ),
                "source": "TomTom Places",
            }
        )
    centers.sort(key=lambda row: row.get("distance_km", 9999))
    return centers[:limit]


def _fetch_json(url: str):
    req = urlrequest.Request(
        url,
        headers={"Accept": "application/json", "User-Agent": _user_agent()},
        method="GET",
    )
    try:
        with urlrequest.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urlerror.HTTPError:
        return {}
    except Exception:
        return {}


def _map_search_link(name: str, location: str) -> str:
    query = urlparse.quote_plus(f"{name} {location}".strip())
    return f"https://www.google.com/maps/search/?api=1&query={query}"


def _osm_map_link(lat: float | None, lon: float | None, name: str, city: str) -> str:
    if lat is None or lon is None:
        query = urlparse.quote_plus(f"{name} {city}".strip())
        return f"https://www.openstreetmap.org/search?query={query}"
    return f"https://www.openstreetmap.org/?mlat={lat}&mlon={lon}#map=16/{lat}/{lon}"


def _nominatim_geocode(location: str) -> tuple[float, float] | None:
    if not location:
        return None
    queries = [f"{location}, India", location]
    for raw_query in queries:
        params = {
            "q": raw_query,
            "format": "jsonv2",
            "limit": 1,
            "countrycodes": "in",
        }
        url = "https://nominatim.openstreetmap.org/search?" + urlparse.urlencode(params)
        payload = _fetch_json(url)
        if not isinstance(payload, list) or not payload:
            continue
        try:
            return float(payload[0]["lat"]), float(payload[0]["lon"])
        except Exception:
            continue
    return None


def _fetch_overpass(query: str):
    endpoints = [
        "https://overpass-api.de/api/interpreter",
        "https://lz4.overpass-api.de/api/interpreter",
        "https://overpass.kumi.systems/api/interpreter",
    ]
    data = urlparse.urlencode({"data": query}).encode("utf-8")
    for endpoint in endpoints:
        req = urlrequest.Request(
            endpoint,
            data=data,
            headers={
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "Accept": "application/json",
                "User-Agent": _user_agent(),
            },
            method="POST",
        )
        try:
            with urlrequest.urlopen(req, timeout=25) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception:
            continue
    return {}


def _user_agent() -> str:
    ua = (getattr(settings, "OSM_USER_AGENT", "") or "").strip()
    if ua:
        return ua
    return "HealthSync/1.0 (local-dev)"


def _first_phone(item: dict) -> str | None:
    contacts = item.get("contacts") or []
    for contact in contacts:
        phones = contact.get("phone") or []
        for phone in phones:
            value = (phone.get("value") or "").strip()
            if value:
                return value
    return None


def _distance_km(lat1: float, lon1: float, lat2: float | None, lon2: float | None) -> float:
    if lat2 is None or lon2 is None:
        return 9999.0
    from math import cos, radians, sqrt

    x = radians(lon2 - lon1) * cos(radians((lat1 + lat2) / 2.0))
    y = radians(lat2 - lat1)
    return 6371.0 * sqrt(x * x + y * y)
