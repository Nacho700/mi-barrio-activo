"""
src/geocoding.py
=================
Convierte una dirección escrita por el usuario ("Calle San Vicente 100,
Valencia") en coordenadas (lat, lon).

HISTORIAL — por qué se usa ArcGIS y no solo Nominatim:
Nominatim (el geocodificador gratuito de OpenStreetMap) aplica bloqueos
agresivos por IP a tráfico que detecta como "uso intensivo", y esto
incluye IPs compartidas como las de Streamlit Community Cloud — se
confirmó en producción que Nominatim devolvía error 403 (Forbidden) de
forma consistente, no por límite de 1 req/segundo sino por bloqueo
directo de la IP de origen. Por eso el geocodificador principal aquí es
ArcGIS (Esri), que tiene un nivel gratuito sin API key vía geopy y mayor
tolerancia a IPs compartidas. Nominatim se mantiene como fallback por si
ArcGIS fallara en algún momento.
"""

import time

from geopy.geocoders import ArcGIS, Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderServiceError, GeocoderUnavailable

_geolocator_principal = ArcGIS(timeout=10)
_geolocator_fallback = Nominatim(
    user_agent="MiBarrioActivoYSano-ProyectoUPV-DataScience/1.0",
    timeout=10,
)

_ERRORES_RECUPERABLES = (GeocoderTimedOut, GeocoderUnavailable, GeocoderServiceError)


class GeocodingServiceError(Exception):
    """El servicio de geocodificación falló (red, timeout, bloqueo) — no es que la dirección no exista."""
    pass


def _intentar_geocodificar(geolocator, query, max_retries=2):
    """
    Intenta geocodificar con un geolocator dado. Devuelve la Location si
    tiene éxito, None si el servicio respondió pero no encontró nada, o
    lanza una excepción si el servicio falló tras los reintentos.
    """
    last_error = None
    for intento in range(max_retries):
        try:
            return geolocator.geocode(query)
        except _ERRORES_RECUPERABLES as e:
            last_error = e
            time.sleep(1.0 * (intento + 1))
        except Exception as e:
            last_error = e
            time.sleep(1.0 * (intento + 1))
    raise GeocodingServiceError(str(last_error))


def geocode_address(address: str, city_hint="Valencia, España"):
    """
    Devuelve {"lat": .., "lon": .., "direccion_completa": ..} si encuentra
    la dirección, o None si ningún geocodificador encontró nada.

    Prueba primero ArcGIS; si ArcGIS falla por completo (no solo "no
    encontrado", sino error de servicio), prueba Nominatim como fallback.
    Solo lanza GeocodingServiceError si AMBOS fallan — esto NO significa
    que la dirección esté mal escrita, significa que los dos servicios de
    geocodificación gratuitos fallaron.
    """
    query = address if "valencia" in address.lower() else f"{address}, {city_hint}"

    try:
        location = _intentar_geocodificar(_geolocator_principal, query)
        if location is not None:
            return {
                "lat": location.latitude,
                "lon": location.longitude,
                "direccion_completa": location.address,
            }
        # ArcGIS respondió pero no encontró nada — antes de rendirnos,
        # probamos también con Nominatim por si tiene mejor cobertura
        # para esta dirección concreta.
    except GeocodingServiceError:
        pass  # ArcGIS falló como servicio; probamos el fallback

    try:
        location = _intentar_geocodificar(_geolocator_fallback, query)
        if location is None:
            return None
        return {
            "lat": location.latitude,
            "lon": location.longitude,
            "direccion_completa": location.address,
        }
    except GeocodingServiceError as e:
        raise GeocodingServiceError(
            f"Tanto ArcGIS como Nominatim (los dos geocodificadores "
            f"gratuitos usados) fallaron al buscar '{address}'. Esto NO "
            f"significa que la dirección esté mal escrita — es un fallo "
            f"temporal de ambos servicios externos. Último error: {e}"
        )
