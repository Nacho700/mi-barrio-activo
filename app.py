"""
app.py
=======
Página principal de "Mi Barrio Activo y Sano".
Ejecutar con: streamlit run app.py
"""

import streamlit as st

st.set_page_config(
    page_title="Mi Barrio Activo y Sano",
    page_icon="🏃",
    layout="wide",
)

st.title("🏃 Mi Barrio Activo y Sano")
st.subheader("Decide dónde vivir en Valencia con datos, no solo con intuición")

st.markdown(
    """
Cuando buscas piso, miras precio y metros cuadrados — pero casi nunca puedes
saber objetivamente **cuánto ruido tendrás a las 8 de la mañana**, **cuánta
contaminación vas a respirar cada día**, o **a cuántos minutos a pie está el
parque o el polideportivo más cercano**.

Esta aplicación combina datos abiertos del Ayuntamiento de València
(contaminación, ruido, arbolado, carril bici, instalaciones deportivas) en
un **Índice de Bienestar Urbano Personal (IBUP)** para que puedas:
"""
)

col1, col2, col3 = st.columns(3)

with col1:
    st.markdown("### 📊 Comparar")
    st.markdown(
        "Compara hasta 3 direcciones candidatas (pisos que estás valorando) "
        "lado a lado en un radar de bienestar urbano."
    )

with col2:
    st.markdown("### 🗺️ Tu rutina real")
    st.markdown(
        "Introduce tu rutina diaria o sube un GPX de tus entrenos y calcula "
        "tu exposición acumulada, no solo la de un punto fijo."
    )

with col3:
    st.markdown("### 📄 Incidencia ciudadana")
    st.markdown(
        "Simula una mejora (carril bici, árbol, pista deportiva) cerca de "
        "ti y genera un informe con evidencia cuantificada para defenderla."
    )

st.divider()

st.info(
    "👈 Usa el menú de la izquierda para navegar entre **Comparador**, "
    "**Mi rutina** y **Simulador de incidencia**.",
    icon="ℹ️",
)

with st.expander("ℹ️ Metodología y fuentes de datos"):
    st.markdown(
        """
**Fuentes de datos** (Open Data València, Ajuntament de València):
- Estaciones de contaminación atmosférica y ruido (Red de Vigilancia)
- Inventario de arbolado y zonas verdes
- Itinerarios ciclistas (carril bici)
- Instalaciones deportivas municipales
- Red de calles peatonal: OpenStreetMap (vía OSMnx)

**Métodos de Data Science aplicados:**
1. **Interpolación espacial (IDW)** para estimar contaminación/ruido en
   cualquier punto a partir de las estaciones fijas.
2. **Grafo de calles real** (NetworkX/OSMnx) para calcular tiempos a pie
   reales, no distancias en línea recta.
3. **Índice compuesto ponderable** por el propio usuario según lo que más
   le importe.
4. **Simulación antes/después** para cuantificar el impacto estimado de una
   mejora de infraestructura concreta.

Proyecto académico — UPV, Grado en Ciencia de Datos.
        """
    )
