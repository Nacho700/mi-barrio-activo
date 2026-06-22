"""
src/geocoding.py
=================
Convierte una dirección escrita por el usuario ("Calle San Vicente 100,
Valencia") en coordenadas (lat, lon) usando Nominatim (OpenStreetMap),
que es gratuito y no requiere API key.

IMPORTANTE sobre fiabilidad: Nominatim es un servicio gratuito con límites
de uso (máx. ~1 petición/segundo, y puede bloquear temporalmente si detecta
uso intensivo desde una IP compartida, como las de Streamlit Cloud). Si
Nominatim falla (timeout, bloqueo, error de servicio), este módulo NO debe
devolver "dirección no encontrada" — eso confundiría al usuario haciéndole
pensar que escribió mal la dirección cuando en realidad el servicio externo
falló. Por eso se distingue explícitamente entre:
  - GeocodingNotFoundError: la dirección no existe / no se pudo interpretar
  - GeocodingServiceError: el servicio de geocodificación falló (reintentar)
"""

import time

from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderServiceError, GeocoderUnavailable

_geolocator = Nominatim(
    user_agent="MiBarrioActivoYSano-ProyectoUPV-DataScience/1.0",
    timeout=10,
)


class GeocodingServiceError(Exception):
    """El servicio de geocodificación falló (red, timeout, bloqueo) — no es que la dirección no exista."""
    pass


def geocode_address(address: str, city_hint="Valencia, España", max_retries=3):
    """
    Devuelve {"lat": .., "lon": .., "direccion_completa": ..} si encuentra
    la dirección, o None si Nominatim respondió pero no encontró nada.

    Lanza GeocodingServiceError si el servicio falla repetidamente tras
    max_retries intentos (esto NO significa que la dirección esté mal
    escrita — significa que Nominatim no respondió correctamente).
    """
    query = address if "valencia" in address.lower() else f"{address}, {city_hint}"

    last_error = None
    for intento in range(max_retries):
        try:
            location = _geolocator.geocode(query)
            if location is None:
                return None  # Nominatim respondió OK, pero no encontró la dirección
            return {
                "lat": location.latitude,
                "lon": location.longitude,
                "direccion_completa": location.address,
            }
        except (GeocoderTimedOut, GeocoderUnavailable, GeocoderServiceError) as e:
            last_error = e
            time.sleep(1.5 * (intento + 1))  # backoff progresivo
        except Exception as e:
            # Cualquier otro error inesperado también se trata como fallo
            # de servicio, no como "dirección no encontrada", para no
            # confundir al usuario.
            last_error = e
            time.sleep(1.5 * (intento + 1))

    raise GeocodingServiceError(
        f"El servicio de geocodificación (Nominatim) no respondió tras "
        f"{max_retries} intentos. Esto NO significa que la dirección esté "
        f"mal escrita — es un fallo temporal del servicio externo gratuito. "
        f"Último error: {last_error}"
    )
