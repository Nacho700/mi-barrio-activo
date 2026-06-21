"""
src/geocoding.py
=================
Convierte una dirección escrita por el usuario ("Calle San Vicente 100,
Valencia") en coordenadas (lat, lon) usando Nominatim (OpenStreetMap),
que es gratuito y no requiere API key.
"""

from geopy.geocoders import Nominatim
from geopy.extra.rate_limiter import RateLimiter

_geolocator = Nominatim(user_agent="mi-barrio-activo-upv")
_geocode = RateLimiter(_geolocator.geocode, min_delay_seconds=1)


def geocode_address(address: str, city_hint="Valencia, España"):
    """
    Devuelve {"lat": .., "lon": .., "direccion_completa": ..} o None si no
    se encuentra la dirección.
    """
    query = address if "valencia" in address.lower() else f"{address}, {city_hint}"
    location = _geocode(query)
    if location is None:
        return None
    return {
        "lat": location.latitude,
        "lon": location.longitude,
        "direccion_completa": location.address,
    }
