"""Geocoding service — hybrid approach:
1. Normalize location description
2. Try Geocoding API first
3. Fall back to Places Autocomplete + Place Details if geocoding fails,
   returns low confidence, or returns no bounds.
"""
import httpx
from typing import Optional, Dict, Any
from loguru import logger
from geoalchemy2.shape import from_shape
from shapely.geometry import box

from app.core.config import settings
from app.utils.data_cleaner import DataCleaner

_data_cleaner = DataCleaner()

# ---------------------------------------------------------------------------
# Location description normalizer
# Maps common abbreviations and shorthand used in MYTO documents to full
# city/state names that Google Maps resolves accurately.
# ---------------------------------------------------------------------------
_LOCATION_NORMALIZER: Dict[str, str] = {
    # Port Harcourt
    "PH": "Port Harcourt, Rivers State",
    "PORT HARCOURT": "Port Harcourt, Rivers State",
    "PHC": "Port Harcourt, Rivers State",
    # Abuja / FCT
    "ABUJA": "Abuja, FCT",
    "FCT": "Abuja, FCT",
    "GRA": "GRA, Abuja, FCT",
    "WUSE": "Wuse, Abuja, FCT",
    "GARKI": "Garki, Abuja, FCT",
    "GARKI 1": "Garki 1, Abuja, FCT",
    "MAITAMA": "Maitama, Abuja, FCT",
    "ASOKORO": "Asokoro, Abuja, FCT",
    "GWARINPA": "Gwarinpa, Abuja, FCT",
    "KATAMPE": "Katampe, Abuja, FCT",
    "KATAMPE EXTENSION": "Katampe Extension, Abuja, FCT",
    # Uyo / Akwa Ibom
    "UYO": "Uyo, Akwa Ibom State",
    "IKOT EKPENE": "Ikot Ekpene, Akwa Ibom State",
    "EKET": "Eket, Akwa Ibom State",
    "AKWA IBOM": "Akwa Ibom State",
    # Enugu
    "ENUGU": "Enugu, Enugu State",
    "NTIGHA": "Ntigha, Enugu State",
    "OBOSI": "Obosi, Anambra State",
    "NIMO": "Nimo, Anambra State",
    # Lagos
    "LAGOS": "Lagos, Lagos State",
    "IKEJA": "Ikeja, Lagos State",
    "VI": "Victoria Island, Lagos State",
    "VICTORIA ISLAND": "Victoria Island, Lagos State",
    "LEKKI": "Lekki, Lagos State",
    # Kano
    "KANO": "Kano, Kano State",
    # Ibadan
    "IBADAN": "Ibadan, Oyo State",
    # Kaduna
    "KADUNA": "Kaduna, Kaduna State",
    # Benin
    "BENIN": "Benin City, Edo State",
    "BENIN CITY": "Benin City, Edo State",
    # Owerri
    "OWERRI": "Owerri, Imo State",
    # Calabar
    "CALABAR": "Calabar, Cross River State",
    # Jos
    "JOS": "Jos, Plateau State",
    # Asaba
    "ASABA": "Asaba, Delta State",
    # Warri
    "WARRI": "Warri, Delta State",
}


def normalize_location(location_description: str) -> str:
    """
    Normalize a location description to a full city/state string.
    Falls back to the original value if no mapping exists.
    """
    if not location_description:
        return ""
    key = location_description.strip().upper()
    return _LOCATION_NORMALIZER.get(key, location_description.strip())


# ---------------------------------------------------------------------------
# Geocoding API
# ---------------------------------------------------------------------------

_GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"
_AUTOCOMPLETE_URL = "https://maps.googleapis.com/maps/api/place/autocomplete/json"
_PLACE_DETAILS_URL = "https://maps.googleapis.com/maps/api/place/details/json"

# Result types that indicate a low-quality geocoding result
_LOW_CONFIDENCE_TYPES = {"country", "administrative_area_level_1", "administrative_area_level_2"}


def _is_low_confidence(result: Dict[str, Any]) -> bool:
    """
    Return True if the geocoding result is too broad to be useful.
    e.g. matched at country or state level instead of street/locality.
    """
    types = set(result.get("types", []))
    return bool(types & _LOW_CONFIDENCE_TYPES)


def bounds_to_polygon(bounds: Dict[str, Any]) -> Optional[Any]:
    """Convert Google Maps bounds dict to a PostGIS POLYGON geometry."""
    if not bounds:
        return None
    try:
        ne = bounds.get("northeast", {})
        sw = bounds.get("southwest", {})
        ne_lat, ne_lng = ne.get("lat"), ne.get("lng")
        sw_lat, sw_lng = sw.get("lat"), sw.get("lng")
        if None in (ne_lat, ne_lng, sw_lat, sw_lng):
            return None
        return from_shape(box(sw_lng, sw_lat, ne_lng, ne_lat), srid=4326)
    except Exception as e:
        logger.error(f"Error converting bounds to polygon: {e}")
        return None


async def _geocode(address: str) -> Optional[Dict[str, Any]]:
    """Call the Geocoding API. Returns None on failure or low-confidence result."""
    params = {"address": address, "key": settings.GOOGLE_MAPS_API_KEY}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(_GEOCODE_URL, params=params)
        if resp.status_code != 200:
            logger.warning(f"Geocoding HTTP {resp.status_code} for: {address}")
            return None
        data = resp.json()
        if data.get("status") != "OK" or not data.get("results"):
            logger.debug(f"Geocoding no result for: {address} — {data.get('status')}")
            return None

        result = data["results"][0]

        if _is_low_confidence(result):
            logger.debug(f"Geocoding low confidence for: {address} — types: {result.get('types')}")
            return None

        geometry = result.get("geometry", {})
        location = geometry.get("location", {})
        bounds = geometry.get("bounds") or geometry.get("viewport")

        # Reject if no bounds returned (too imprecise for polygon storage)
        if not bounds:
            logger.debug(f"Geocoding returned no bounds for: {address}")
            return None

        return {
            "latitude": location.get("lat"),
            "longitude": location.get("lng"),
            "place_id": result.get("place_id"),
            "formatted_address": result.get("formatted_address"),
            "bounds": bounds,
            "source": "geocoding",
        }
    except Exception as e:
        logger.error(f"Geocoding error for '{address}': {e}", exc_info=True)
        return None


async def _autocomplete_then_details(address: str) -> Optional[Dict[str, Any]]:
    """
    Fallback: Places Autocomplete → first prediction → Place Details.
    Returns coordinates, bounds, and formatted_address.
    """
    # Step 1: Autocomplete
    ac_params = {
        "input": address,
        "key": settings.GOOGLE_MAPS_API_KEY,
        "components": "country:ng",  # restrict to Nigeria
        "language": "en",
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            ac_resp = await client.get(_AUTOCOMPLETE_URL, params=ac_params)
        if ac_resp.status_code != 200:
            logger.warning(f"Autocomplete HTTP {ac_resp.status_code} for: {address}")
            return None
        ac_data = ac_resp.json()
        predictions = ac_data.get("predictions", [])
        if not predictions:
            logger.debug(f"Autocomplete no predictions for: {address}")
            return None

        place_id = predictions[0].get("place_id")
        if not place_id:
            return None

        logger.debug(f"Autocomplete first prediction: {predictions[0].get('description')} (place_id={place_id})")

        # Step 2: Place Details
        det_params = {
            "place_id": place_id,
            "fields": "geometry,formatted_address,place_id",
            "key": settings.GOOGLE_MAPS_API_KEY,
        }
        async with httpx.AsyncClient(timeout=10.0) as client:
            det_resp = await client.get(_PLACE_DETAILS_URL, params=det_params)
        if det_resp.status_code != 200:
            logger.warning(f"Place Details HTTP {det_resp.status_code} for place_id={place_id}")
            return None
        det_data = det_resp.json()
        detail = det_data.get("result", {})
        geometry = detail.get("geometry", {})
        location = geometry.get("location", {})
        bounds = geometry.get("bounds") or geometry.get("viewport")

        return {
            "latitude": location.get("lat"),
            "longitude": location.get("lng"),
            "place_id": place_id,
            "formatted_address": detail.get("formatted_address"),
            "bounds": bounds,
            "source": "autocomplete",
        }
    except Exception as e:
        logger.error(f"Autocomplete/Details error for '{address}': {e}", exc_info=True)
        return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def geocode_address(
    street_name: str,
    location_description: str = "",
) -> Optional[Dict[str, Any]]:
    """
    Geocode a street address using the hybrid approach:

    1. Normalize the location description
    2. Try Geocoding API
    3. If it fails, returns no bounds, or is low confidence →
       fall back to Autocomplete + Place Details

    Returns a dict with: latitude, longitude, place_id,
    formatted_address, bounds (raw dict), source.
    Returns None if both methods fail.
    """
    if not settings.GOOGLE_MAPS_API_KEY:
        logger.error("GOOGLE_MAPS_API_KEY not configured")
        return None

    normalized_location = normalize_location(location_description)
    parts = [street_name]
    if normalized_location:
        parts.append(normalized_location)
    parts.append("Nigeria")
    address = ", ".join(p for p in parts if p)

    logger.debug(f"Geocoding: {address}")

    # Step 1: Try Geocoding API
    result = await _geocode(address)
    if result:
        logger.debug(f"Geocoding succeeded for: {address} (source=geocoding)")
        return result

    # Step 2: Fall back to Autocomplete + Place Details
    logger.debug(f"Falling back to Autocomplete for: {address}")
    result = await _autocomplete_then_details(address)
    if result:
        logger.debug(f"Autocomplete succeeded for: {address} (source=autocomplete)")
        return result

    logger.warning(f"Both geocoding methods failed for: {address}")
    return None


class GeocodingService:
    """
    Thin wrapper kept for backward compatibility with existing callers
    that use GeocodingService.geocode_address() and
    GeocodingService.bounds_to_polygon().
    """

    @staticmethod
    async def geocode_address(address: str) -> Optional[Dict[str, Any]]:
        """
        Legacy single-string interface.
        Splits on the last ', Nigeria' suffix if present, otherwise
        passes the full string as the street name.
        """
        # Strip trailing ', Nigeria' if present so we don't double-append it
        clean = address.removesuffix(", Nigeria").removesuffix(",Nigeria").strip()
        return await geocode_address(clean)

    @staticmethod
    def bounds_to_polygon(bounds: Dict[str, Any]) -> Optional[Any]:
        return bounds_to_polygon(bounds)
