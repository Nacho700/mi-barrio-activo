"""
src/report.py
===============
Genera el informe PDF de incidencia ciudadana: evidencia cuantificada del
beneficio estimado de una mejora de infraestructura en una zona concreta,
pensado para llevar a una asociación de vecinos, petición municipal o
proceso de presupuestos participativos de Valencia.
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
    "no2": "Dióxido de nitrógeno (NO2)",
    "pm10": "Partículas en suspensión (PM10)",
    "pm25": "Partículas finas (PM2.5)",
    "tiempo_deporte_min": "Acceso a instalación deportiva",
    "tiempo_bici_min": "Acceso a carril bici",
    "tiempo_verde_min": "Acceso a zona verde",
}


def generar_informe_incidencia(direccion, simulacion, nombre_archivo=None):
    """
    Genera un PDF con el resultado de simulator.simulate_improvement().

    Parameters
    ----------
    direccion : str — dirección o descripción del punto evaluado
    simulacion : dict — resultado de simulate_improvement()
    nombre_archivo : str opcional — si no se da, se genera uno con timestamp

    Returns
    -------
    Path al PDF generado
    """
    if nombre_archivo is None:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        nombre_archivo = f"informe_incidencia_{ts}.pdf"

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
        "TitleCustom", parent=styles["Title"], fontSize=18, spaceAfter=6
    )
    subtitle_style = ParagraphStyle(
        "SubtitleCustom", parent=styles["Normal"], fontSize=10, textColor=colors.grey
    )
    h2_style = ParagraphStyle(
        "H2Custom", parent=styles["Heading2"], fontSize=13, spaceBefore=14, spaceAfter=6
    )
    body_style = styles["Normal"]

    story = []

    story.append(Paragraph("Informe de Incidencia Ciudadana", title_style))
    story.append(
        Paragraph(
            f"Generado con la aplicación <b>Mi Barrio Activo y Sano</b> · "
            f"{datetime.now().strftime('%d/%m/%Y %H:%M')}",
            subtitle_style,
        )
    )
    story.append(Spacer(1, 12))
    story.append(HRFlowable(width="100%", color=colors.lightgrey))
    story.append(Spacer(1, 12))

    story.append(Paragraph("Zona evaluada", h2_style))
    story.append(Paragraph(direccion, body_style))

    story.append(Paragraph("Mejora propuesta", h2_style))
    story.append(Paragraph(simulacion["tipo_mejora"], body_style))

    story.append(Paragraph("Resumen del impacto estimado", h2_style))
    ibup_antes = simulacion["antes"]["ibup"]
    ibup_despues = simulacion["despues"]["ibup"]
    diff = simulacion["diferencia_ibup"]

    resumen_txt = (
        f"El Índice de Bienestar Urbano Personal (IBUP) de esta zona pasaría de "
        f"<b>{ibup_antes}</b> a <b>{ibup_despues}</b> sobre 100 "
        f"({'+' if diff and diff > 0 else ''}{diff} puntos) si se implementara "
        f"esta mejora."
    )
    story.append(Paragraph(resumen_txt, body_style))
    story.append(Spacer(1, 10))

    # Tabla de componentes antes/después
    table_data = [["Componente", "Antes", "Después", "Diferencia"]]
    for key, label in COMPONENTE_LABELS.items():
        antes = simulacion["antes"]["componentes"].get(key)
        despues = simulacion["despues"]["componentes"].get(key)
        d = simulacion["diferencia_componentes"].get(key)
        if antes is None and despues is None:
            continue
        table_data.append(
            [
                label,
                f"{antes:.1f}" if antes is not None else "N/D",
                f"{despues:.1f}" if despues is not None else "N/D",
                f"{'+' if d and d > 0 else ''}{d:.1f}" if d is not None else "N/D",
            ]
        )

    table = Table(table_data, colWidths=[7 * cm, 3 * cm, 3 * cm, 3 * cm])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2E7D32")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.lightgrey),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F5F5F5")]),
                ("ALIGN", (1, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.append(table)
    story.append(Spacer(1, 16))

    story.append(Paragraph("Metodología", h2_style))
    metodologia_txt = (
        "La exposición a contaminación y ruido se estima mediante interpolación "
        "espacial (IDW) a partir de las estaciones de la Red de Vigilancia y "
        "Control de la Contaminación Atmosférica de València. El acceso a "
        "infraestructura (deporte, carril bici, zonas verdes) se calcula como "
        "tiempo a pie real por la red de calles (OpenStreetMap), no en línea "
        "recta. Esta simulación estima el efecto de añadir la infraestructura "
        "propuesta en accesibilidad y/o exposición; no modela cambios de "
        "tráfico inducido ni garantiza que el ayuntamiento vaya a ejecutar la "
        "obra. Se presenta como evidencia cuantificada de apoyo a una "
        "petición ciudadana, no como una predicción oficial."
    )
    story.append(Paragraph(metodologia_txt, body_style))

    story.append(Spacer(1, 16))
    story.append(Paragraph("Cómo usar este informe", h2_style))
    uso_txt = (
        "Este documento puede adjuntarse a una petición a la asociación de "
        "vecinos del barrio, a una solicitud al Ayuntamiento de València, o "
        "incorporarse a una propuesta dentro de un proceso de presupuestos "
        "participativos."
    )
    story.append(Paragraph(uso_txt, body_style))

    doc.build(story)
    return out_path
