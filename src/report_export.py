"""
src/report_export.py
======================
Genera un informe PDF resumen del análisis comparativo de direcciones,
para que el usuario pueda descargarlo y compartirlo (p.ej. con su pareja
o familia) sin tener que volver a abrir la web.
"""

from datetime import datetime
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    HRFlowable,
)

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "outputs"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

COMPONENTE_LABELS = {
    "no2": "NO2 (ug/m3)",
    "pm10": "PM10 (ug/m3)",
    "pm25": "PM2.5 (ug/m3)",
    "ruido_db": "Estimated noise (dB)",
    "tiempo_deporte_min": "Sports access (min)",
    "tiempo_bici_min": "Bike lane access (min)",
    "tiempo_verde_min": "Green space access (min)",
    "tiempo_transporte_min": "Public transport (min)",
}


def _quitar_emojis(texto: str) -> str:
    """
    Quita emojis y otros caracteres fuera del rango Unicode básico (Latin
    + símbolos comunes) de un texto. Necesario porque reportlab con las
    fuentes estándar (Helvetica) no renderiza emojis — aparecerían como
    cuadrados negros en el PDF en vez del icono esperado.
    """
    return "".join(c for c in texto if ord(c) < 0x2100).strip(" -·")


def generar_informe_comparativo(resultados, perfil_usado, nombre_archivo=None):
    """
    Genera un PDF con el resumen del análisis comparativo de las
    direcciones evaluadas: IBUP de cada una, valores crudos por
    componente, y la zona/cluster asignado.

    Parameters
    ----------
    resultados : list of dict — la misma estructura que se guarda en
        st.session_state["resultados"] en app.py
    perfil_usado : str — nombre del perfil de usuario aplicado

    Returns
    -------
    Path al PDF generado
    """
    if nombre_archivo is None:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        nombre_archivo = f"mi_barrio_activo_{ts}.pdf"

    out_path = OUTPUT_DIR / nombre_archivo

    doc = SimpleDocTemplate(
        str(out_path),
        pagesize=A4,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
    )
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "TitleCustom", parent=styles["Title"], fontSize=18, spaceAfter=6, textColor=colors.HexColor("#2B2620")
    )
    subtitle_style = ParagraphStyle(
        "SubtitleCustom", parent=styles["Normal"], fontSize=10, textColor=colors.grey
    )
    h2_style = ParagraphStyle(
        "H2Custom", parent=styles["Heading2"], fontSize=13, spaceBefore=14, spaceAfter=6,
        textColor=colors.HexColor("#C65D3B"),
    )
    body_style = styles["Normal"]

    story = []

    story.append(Paragraph("Mi Barrio Activo y Sano — Comparative report", title_style))
    story.append(
        Paragraph(
            f"Generated on {datetime.now().strftime('%d/%m/%Y at %H:%M')} · "
            f"Profile applied: {perfil_usado}",
            subtitle_style,
        )
    )
    story.append(Spacer(1, 12))
    story.append(HRFlowable(width="100%", color=colors.lightgrey))
    story.append(Spacer(1, 12))

    # --- Resumen de IBUP por dirección ---
    story.append(Paragraph("Summary — Personal Urban Wellbeing Index", h2_style))
    tabla_resumen = [["Address", "IBUP", "Neighbourhood type"]]
    for r in resultados:
        ibup_val = r["ibup"]["ibup"]
        cluster_info = r.get("cluster_info")
        # Quitamos emojis del texto: reportlab con las fuentes estándar
        # (Helvetica) no renderiza emojis Unicode, aparecerían como
        # cuadrados negros en el PDF.
        etiqueta_cluster = _quitar_emojis(cluster_info["etiqueta"]) if cluster_info else "N/A"
        tabla_resumen.append([
            r["direccion"][:55],
            f"{ibup_val:.0f}/100" if ibup_val is not None else "N/A",
            etiqueta_cluster,
        ])

    t = Table(tabla_resumen, colWidths=[8.5 * cm, 2.5 * cm, 5.5 * cm])
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#C65D3B")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.lightgrey),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F2E9D8")]),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.append(t)
    story.append(Spacer(1, 16))

    # --- Detalle por componente ---
    story.append(Paragraph("Breakdown by component", h2_style))
    columnas_presentes = [c for c in COMPONENTE_LABELS if any(r["raw"].get(c) is not None for r in resultados)]
    tabla_detalle = [["Component"] + [r["direccion"][:25] for r in resultados]]
    for c in columnas_presentes:
        fila = [COMPONENTE_LABELS[c]]
        for r in resultados:
            val = r["raw"].get(c)
            fila.append(f"{val:.1f}" if val is not None else "N/A")
        tabla_detalle.append(fila)

    t2 = Table(tabla_detalle, colWidths=[4.5 * cm] + [round(12.0 / max(len(resultados), 1), 1) * cm] * len(resultados))
    t2.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#3D6B4F")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.lightgrey),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F2E9D8")]),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    story.append(t2)
    story.append(Spacer(1, 16))

    # --- Nota metodológica ---
    story.append(Paragraph("Methodological note", h2_style))
    nota_txt = (
        "Pollution values are estimated through spatial interpolation (IDW) from "
        "Valencia's real monitoring stations. Noise is an ESTIMATE based on nearby "
        "traffic intensity, not a certified measurement. Access times are calculated "
        "on Valencia's real street network (OpenStreetMap), not in a straight line. "
        "Academic project — UPV, Data Science degree."
    )
    story.append(Paragraph(nota_txt, body_style))

    doc.build(story)
    return out_path
