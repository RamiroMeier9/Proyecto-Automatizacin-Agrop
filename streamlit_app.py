from __future__ import annotations

import json
import math
import os
import re
import unicodedata
from dataclasses import replace
from datetime import date
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

from inta_forrajes.csv_io import read_alternatives, read_rows
from inta_forrajes.evidence import EvidenceCatalog
from inta_forrajes.forward_curve import build_forward_curve, option_implied_volatility
from inta_forrajes.models import PriceObservation
from inta_forrajes.pipeline import Pipeline


ROOT = Path(__file__).resolve().parent

st.set_page_config(
    page_title="Panel agropecuario regional",
    page_icon="🌾",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    :root {
        --verde-900: #143d32;
        --verde-700: #23624e;
        --verde-500: #3f8a6b;
        --tinta: #1e2d29;
        --gris: #63706b;
        --borde: #dce6e1;
        --fondo: #f6f9f7;
    }
    .stApp { background: var(--fondo); color: var(--tinta); }
    .block-container { max-width: 1280px; padding-top: 1.6rem; padding-bottom: 3rem; }
    [data-testid="stSidebar"] { background: #eef5f1; border-right: 1px solid var(--borde); }
    h1, h2, h3 { color: var(--verde-900); letter-spacing: -0.02em; }
    p, label, [data-testid="stMarkdownContainer"] { line-height: 1.55; }
    .hero {
        background: linear-gradient(125deg, #143d32 0%, #23624e 62%, #3f8a6b 100%);
        border-radius: 22px;
        padding: 2.2rem 2.4rem;
        color: white;
        margin-bottom: 1.35rem;
        box-shadow: 0 16px 40px rgba(20, 61, 50, 0.16);
    }
    .hero h1 { color: white; font-size: clamp(2rem, 4vw, 3.2rem); margin: 0.25rem 0 0.65rem; }
    .hero p { color: #e7f4ee; max-width: 820px; font-size: 1.05rem; margin: 0; }
    .eyebrow { font-size: 0.78rem; font-weight: 750; letter-spacing: 0.12em; text-transform: uppercase; color: #bfe3d3; }
    .page-kicker { color: var(--verde-700); font-size: 0.78rem; font-weight: 750; letter-spacing: 0.11em; text-transform: uppercase; margin-bottom: 0.25rem; }
    .page-subtitle { color: var(--gris); font-size: 1.02rem; margin-top: -0.45rem; margin-bottom: 1.25rem; max-width: 900px; }
    [data-testid="stMetric"] {
        background: white;
        border: 1px solid var(--borde);
        border-radius: 16px;
        padding: 1rem 1.05rem;
        box-shadow: 0 7px 22px rgba(31, 75, 61, 0.055);
    }
    [data-testid="stMetricLabel"] { color: var(--gris); }
    [data-testid="stMetricValue"] { color: var(--verde-900); }
    div[data-testid="stVerticalBlockBorderWrapper"] {
        background: white;
        border-color: var(--borde) !important;
        border-radius: 16px;
        box-shadow: 0 7px 20px rgba(31, 75, 61, 0.045);
    }
    .stButton > button, .stDownloadButton > button {
        border-radius: 10px;
        min-height: 2.65rem;
        border-color: #aec8bc;
        font-weight: 650;
    }
    .stButton > button[kind="primary"] { background: var(--verde-700); border-color: var(--verde-700); }
    [data-baseweb="tab-list"] { gap: 0.35rem; }
    [data-baseweb="tab"] { border-radius: 10px; padding-left: 1rem; padding-right: 1rem; }
    footer { visibility: hidden; }
    </style>
    """,
    unsafe_allow_html=True,
)


def titulo_pagina(seccion: str, titulo: str, descripcion: str) -> None:
    st.markdown(f'<div class="page-kicker">{seccion}</div>', unsafe_allow_html=True)
    st.title(titulo)
    st.markdown(f'<div class="page-subtitle">{descripcion}</div>', unsafe_allow_html=True)


def numero(valor: object) -> float | None:
    if valor is None:
        return None
    try:
        convertido = float(valor)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(convertido) else convertido


def moneda(valor: float | None, codigo: str = "ARS", decimales: int = 0) -> str:
    if valor is None:
        return "Sin dato"
    simbolo = "US$" if codigo.upper() == "USD" else "$"
    formateado = f"{valor:,.{decimales}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{simbolo} {formateado}"


def fecha_visible(valor: object) -> str:
    if not valor:
        return "Sin actualización"
    parsed = pd.to_datetime(valor, errors="coerce")
    if pd.isna(parsed):
        return str(valor)
    return parsed.strftime("%d/%m/%Y %H:%M")


def codigo_manual(nombre: str) -> str:
    normalizado = unicodedata.normalize("NFKD", nombre).encode("ascii", "ignore").decode("ascii")
    normalizado = re.sub(r"[^A-Za-z0-9]+", "_", normalizado).strip("_").upper()
    return f"MANUAL_{normalizado or 'INSUMO'}"


def nombre_producto(codigo: str) -> str:
    texto = (codigo or "").upper()
    if "MAI" in texto:
        return "Maíz"
    if "SOJ" in texto:
        return "Soja"
    if "TRI" in texto:
        return "Trigo"
    if "DOL" in texto or "DLR" in texto:
        return "Dólar"
    return codigo or "Sin clasificar"


def precio_referencia(fila: dict) -> float | None:
    for campo in ("settlement", "last", "bid", "ask"):
        valor = numero(fila.get(campo))
        if valor is not None:
            return valor
    return None


FUENTES = {
    "bcra": "Tipo de cambio BCRA",
    "a3_agro_marketdata": "Futuros y opciones A3",
    "a3_marketdata_official": "Reporte autenticado A3",
    "a3_trading_realtime": "Mercado A3 en tiempo real",
    "sio_granos": "Operaciones SIO-Granos",
    "manual_csv": "Datos cargados manualmente",
}

ESTADOS = {
    "ok": "Actualizada",
    "skipped": "Pendiente de credencial",
    "error": "Revisar conexión",
}


pipeline = Pipeline(ROOT)
if "datos_iniciales_cargados" not in st.session_state:
    pipeline.import_public_snapshot()
    pipeline.import_manual()
    st.session_state["datos_iniciales_cargados"] = True


with st.sidebar:
    st.markdown("## 🌾 Panel Agro")
    st.caption("Coronel Suárez · costos, escenarios y mercados")
    pagina = st.radio(
        "Navegación",
        [
            "Inicio",
            "Costos y escenarios",
            "Mercados A3",
            "Carga manual",
            "Base regional",
            "Calidad de datos",
        ],
        label_visibility="collapsed",
    )
    st.divider()
    if st.button("Actualizar todas las fuentes", type="primary", width="stretch"):
        with st.spinner("Consultando las fuentes habilitadas…"):
            resultado_actualizacion = pipeline.update()
            pipeline.write_public_snapshot()
        st.session_state["ultima_actualizacion_manual"] = resultado_actualizacion

    resultado_actualizacion = st.session_state.get("ultima_actualizacion_manual")
    if resultado_actualizacion:
        correctas = sum(item["status"] == "ok" for item in resultado_actualizacion)
        errores = sum(item["status"] == "error" for item in resultado_actualizacion)
        if errores:
            st.warning(f"{correctas} fuentes actualizadas y {errores} para revisar.")
        else:
            st.success(f"{correctas} fuentes actualizadas.")
    st.caption(
        "Las fuentes con credenciales se activan automáticamente cuando el secreto correspondiente está configurado."
    )


prices = pipeline.storage.latest_prices()
quotes = pipeline.storage.latest_a3_quotes()
sync_status = pipeline.storage.sync_status()
alternatives = read_alternatives(ROOT / "data" / "manual" / "alternatives.csv")
evidence_catalog = EvidenceCatalog(ROOT / "data" / "reference")


if pagina == "Inicio":
    st.markdown(
        """
        <section class="hero">
            <div class="eyebrow">Herramienta de evaluación regional</div>
            <h1>Decisiones forrajeras con números claros</h1>
            <p>Un panel para reunir costos actuales, supuestos productivos, antecedentes regionales y señales de los mercados de futuros. Los datos automáticos y los datos manuales se mantienen diferenciados.</p>
        </section>
        """,
        unsafe_allow_html=True,
    )
    futuros = [fila for fila in quotes if fila.get("instrument_type") == "future"]
    opciones = [fila for fila in quotes if fila.get("instrument_type") == "option"]
    manuales = [fila for fila in prices if fila.get("source") == "manual"]
    metricas = st.columns(4)
    metricas[0].metric("Alternativas productivas", len(alternatives))
    metricas[1].metric("Contratos de futuros", len(futuros))
    metricas[2].metric("Opciones registradas", len(opciones))
    metricas[3].metric("Precios manuales completos", len(manuales))

    st.subheader("Estado de la información")
    estados_por_fuente = {fila["source"]: fila for fila in sync_status}
    tarjetas = st.columns(3)
    for columna, clave in zip(tarjetas, ["a3_agro_marketdata", "bcra", "manual_csv"]):
        estado = estados_por_fuente.get(clave)
        with columna.container(border=True):
            st.markdown(f"**{FUENTES[clave]}**")
            if estado:
                st.write(ESTADOS.get(estado["status"], estado["status"]))
                st.caption(f"Último proceso: {fecha_visible(estado['finished_at'])}")
                st.caption(f"Registros incorporados: {estado['rows_written']}")
            else:
                st.write("Todavía sin ejecutar")
                st.caption("Usá el botón de actualización o completá los datos manuales.")

    izquierda, derecha = st.columns([1.25, 1])
    with izquierda.container(border=True):
        st.subheader("Qué responde el panel")
        st.write(
            "Permite estimar cuánto cuesta implantar y mantener cada alternativa, cuánto representa por kilogramo de materia seca y cómo cambia el resultado cuando varían rendimiento, tasa o precios."
        )
        st.write(
            "La curva de futuros aporta una referencia sobre precios pactados hoy para distintos vencimientos. No se interpreta como una predicción segura."
        )
    with derecha.container(border=True):
        st.subheader("Para completar un cálculo")
        st.write("1. Actualizá las fuentes automáticas.")
        st.write("2. Cargá los precios locales faltantes.")
        st.write("3. Revisá los supuestos productivos.")
        st.write("4. Compará escenarios en Costos y escenarios.")


elif pagina == "Costos y escenarios":
    titulo_pagina(
        "Evaluación económica",
        "Costos y escenarios",
        "Compará alternativas con precios vigentes y supuestos productivos explícitos. Los faltantes nunca se reemplazan por cero.",
    )
    if not alternatives:
        st.warning("No hay alternativas productivas cargadas.")
    else:
        nombres = {item.name: item.alternative_id for item in alternatives}
        seleccion = st.selectbox("Alternativa a evaluar", list(nombres))
        alternativa = next(item for item in alternatives if item.alternative_id == nombres[seleccion])
        controles = st.columns(3)
        tasa = controles[0].number_input(
            "Tasa de descuento anual (%)", min_value=0.0, max_value=200.0, value=10.0, step=0.5
        )
        rendimiento = controles[1].number_input(
            "Rendimiento esperado (kg MS/ha)",
            min_value=0.0,
            value=float(alternativa.yield_dm_kg_ha or 0),
            step=100.0,
        )
        controles[2].metric("Vida útil considerada", f"{alternativa.useful_life_years} año(s)")
        resultado = pipeline.evaluate(alternativa.alternative_id, tasa / 100, rendimiento or None)
        resultados = st.columns(4)
        resultados[0].metric(
            "Costo presente por ha",
            moneda(resultado.present_value_cost_ha) if resultado.cost_complete else "Pendiente",
        )
        resultados[1].metric(
            "Costo anual equivalente",
            moneda(resultado.equivalent_annual_cost_ha) if resultado.cost_complete else "Pendiente",
        )
        resultados[2].metric(
            "Costo por kg MS aprovechada", moneda(resultado.cost_per_kg_usable_dm, decimales=2)
        )
        resultados[3].metric(
            "Costo por kg de carne equivalente",
            moneda(resultado.cost_per_kg_meat_equivalent, decimales=2),
        )
        if resultado.missing_inputs:
            st.warning(
                "Faltan precios o parámetros para cerrar el cálculo: "
                + "; ".join(resultado.missing_inputs)
                + ". Completalos en Carga manual."
            )
        else:
            st.success("El cálculo utiliza todos los precios y parámetros necesarios.")

        st.subheader("Sensibilidad al rendimiento")
        rendimientos = sorted(
            {
                valor
                for valor in (
                    alternativa.yield_low_dm_kg_ha,
                    alternativa.yield_dm_kg_ha,
                    alternativa.yield_high_dm_kg_ha,
                    rendimiento,
                )
                if valor is not None and valor > 0
            }
        )
        escenarios = []
        for valor in rendimientos:
            evaluacion = pipeline.evaluate(alternativa.alternative_id, tasa / 100, valor)
            escenarios.append(
                {
                    "Rendimiento (kg MS/ha)": valor,
                    "Costo por kg MS aprovechada": evaluacion.cost_per_kg_usable_dm,
                    "Costo anual por ha": evaluacion.equivalent_annual_cost_ha if evaluacion.cost_complete else None,
                }
            )
        escenario_frame = pd.DataFrame(escenarios)
        if not escenario_frame.empty and escenario_frame["Costo por kg MS aprovechada"].notna().any():
            figura = px.line(
                escenario_frame,
                x="Rendimiento (kg MS/ha)",
                y="Costo por kg MS aprovechada",
                markers=True,
                color_discrete_sequence=["#23624e"],
            )
            figura.update_layout(margin=dict(l=10, r=10, t=20, b=10), yaxis_title="ARS por kg MS")
            st.plotly_chart(figura, width="stretch")
        else:
            st.info("La sensibilidad aparecerá cuando se completen los precios de los insumos.")
        with st.expander("Ver costos por año"):
            st.dataframe(
                pd.DataFrame(
                    [
                        {"Año del proyecto": año, "Costo estimado": costo}
                        for año, costo in resultado.cash_costs_by_year.items()
                    ]
                ),
                width="stretch",
                hide_index=True,
            )


elif pagina == "Mercados A3":
    titulo_pagina(
        "Información de mercado",
        "Futuros y opciones de A3",
        "Consultá precios de ajuste, vencimientos, volumen e interés abierto. La información pública se actualiza automáticamente; el reporte autenticado se habilita mediante un secreto privado.",
    )
    futuros = [fila for fila in quotes if fila.get("instrument_type") == "future"]
    opciones = [fila for fila in quotes if fila.get("instrument_type") == "option"]
    cabecera = st.columns(3)
    cabecera[0].metric("Futuros disponibles", len(futuros))
    cabecera[1].metric("Opciones disponibles", len(opciones))
    cabecera[2].metric("API autenticada", "Configurada" if os.getenv("A3_MD_API_KEY") else "Sin clave activa")

    tab_futuros, tab_opciones, tab_oficial = st.tabs(
        ["Curva de futuros", "Opciones", "Reporte autenticado"]
    )
    with tab_futuros:
        if not futuros:
            st.info("Todavía no hay futuros cargados. Presioná Actualizar todas las fuentes.")
        else:
            productos = sorted({nombre_producto(fila.get("underlying", "")) for fila in futuros})
            producto = st.selectbox("Producto", productos, key="producto_futuros")
            seleccionados = [fila for fila in futuros if nombre_producto(fila.get("underlying", "")) == producto]
            curva = build_forward_curve(seleccionados)
            if curva:
                curva_frame = pd.DataFrame(curva).rename(
                    columns={
                        "symbol": "Contrato",
                        "maturity_date": "Vencimiento",
                        "future_price": "Precio futuro",
                        "basis": "Base",
                    }
                )
                curva_frame["Vencimiento"] = pd.to_datetime(curva_frame["Vencimiento"], errors="coerce")
                figura = px.line(
                    curva_frame,
                    x="Vencimiento",
                    y="Precio futuro",
                    markers=True,
                    hover_name="Contrato",
                    color_discrete_sequence=["#23624e"],
                )
                figura.update_layout(margin=dict(l=10, r=10, t=20, b=10), yaxis_title="USD por tonelada")
                st.plotly_chart(figura, width="stretch")
            tabla_futuros = pd.DataFrame(
                [
                    {
                        "Producto": nombre_producto(fila.get("underlying", "")),
                        "Contrato": fila.get("symbol"),
                        "Vencimiento": fila.get("maturity_date"),
                        "Precio de referencia": precio_referencia(fila),
                        "Volumen": fila.get("volume"),
                        "Interés abierto": fila.get("open_interest"),
                    }
                    for fila in seleccionados
                ]
            )
            st.dataframe(tabla_futuros, width="stretch", hide_index=True)
            st.caption("La curva refleja precios negociados para vencimientos futuros; no constituye una proyección garantizada.")

    with tab_opciones:
        if not opciones:
            st.info("Todavía no hay opciones cargadas.")
        else:
            productos_opciones = sorted({nombre_producto(fila.get("underlying", "")) for fila in opciones})
            producto_opcion = st.selectbox("Producto", productos_opciones, key="producto_opciones")
            tasa_libre = st.number_input(
                "Tasa anual para calcular volatilidad implícita (%)", 0.0, 300.0, 10.0, 0.5
            ) / 100
            future_map = {
                (fila.get("symbol"), fila.get("maturity_date")): precio_referencia(fila)
                for fila in futuros
            }
            filas = []
            for fila in opciones:
                if nombre_producto(fila.get("underlying", "")) != producto_opcion:
                    continue
                futuro = future_map.get((fila.get("underlying"), fila.get("maturity_date")))
                volatilidad = option_implied_volatility(fila, futuro, risk_free_rate=tasa_libre) if futuro else None
                filas.append(
                    {
                        "Contrato": fila.get("symbol"),
                        "Tipo": "Compra" if fila.get("option_type") == "call" else "Venta",
                        "Precio de ejercicio": fila.get("strike"),
                        "Precio de referencia": precio_referencia(fila),
                        "Futuro comparable": futuro,
                        "Volatilidad implícita": volatilidad,
                        "Volumen": fila.get("volume"),
                    }
                )
            st.dataframe(pd.DataFrame(filas), width="stretch", hide_index=True)

    with tab_oficial:
        ruta_oficial = pipeline.paths.official_a3_snapshot
        if ruta_oficial.exists():
            documento = json.loads(ruta_oficial.read_text(encoding="utf-8"))
            st.success(f"Reporte autenticado disponible para {documento.get('report_date', 'fecha no identificada')}.")
            datos = documento.get("data")
            if isinstance(datos, list):
                st.dataframe(pd.json_normalize(datos), width="stretch", hide_index=True)
            elif isinstance(datos, dict):
                st.dataframe(pd.json_normalize([datos]), width="stretch", hide_index=True)
        else:
            st.info("No hay un reporte autenticado guardado. Para habilitarlo se necesita una clave UAT nueva configurada como secreto.")


elif pagina == "Carga manual":
    titulo_pagina(
        "Datos que requieren validación local",
        "Carga manual",
        "Completá sólo la información que no puede obtenerse automáticamente: presupuestos locales y supuestos productivos. Cada valor queda fechado y puede descargarse como respaldo.",
    )
    tab_precios, tab_supuestos = st.tabs(["Precios e insumos", "Supuestos productivos"])
    with tab_precios:
        catalogo = read_rows(ROOT / "data" / "manual" / "manual_prices.csv")
        ultimos = {fila["series_id"]: fila for fila in prices if fila.get("source") == "manual"}
        filas_editor = []
        for item in catalogo:
            codigo = str(item.get("series_id", "")).strip()
            if not codigo:
                continue
            ultimo = ultimos.get(codigo, {})
            fecha_valor = ultimo.get("observed_at") or item.get("observed_at") or date.today().isoformat()
            filas_editor.append(
                {
                    "Código": codigo,
                    "Insumo": item.get("item") or ultimo.get("item") or codigo,
                    "Precio unitario": numero(ultimo.get("value")) or numero(item.get("value")),
                    "Moneda": ultimo.get("currency") or item.get("currency") or "ARS",
                    "Unidad": ultimo.get("unit") or item.get("unit") or "",
                    "Fecha": pd.to_datetime(fecha_valor, errors="coerce").date(),
                    "Observación": item.get("notes", ""),
                }
            )
        editor = st.data_editor(
            pd.DataFrame(filas_editor),
            width="stretch",
            hide_index=True,
            num_rows="fixed",
            disabled=["Código", "Insumo"],
            column_config={
                "Precio unitario": st.column_config.NumberColumn(min_value=0.0, format="%.2f"),
                "Moneda": st.column_config.SelectboxColumn(options=["ARS", "USD"]),
                "Fecha": st.column_config.DateColumn(format="DD/MM/YYYY"),
                "Observación": st.column_config.TextColumn(width="large"),
            },
            key="editor_precios_manuales",
        )
        acciones = st.columns([1, 1, 2])
        if acciones[0].button("Guardar precios", type="primary", width="stretch"):
            observaciones = []
            for fila in editor.to_dict("records"):
                valor = numero(fila.get("Precio unitario"))
                if valor is None:
                    continue
                fecha_fila = fila.get("Fecha")
                fecha_iso = fecha_fila.isoformat() if hasattr(fecha_fila, "isoformat") else pd.to_datetime(fecha_fila).date().isoformat()
                observaciones.append(
                    PriceObservation(
                        observed_at=fecha_iso,
                        series_id=str(fila["Código"]),
                        item=str(fila["Insumo"]),
                        value=valor,
                        currency=str(fila.get("Moneda") or "ARS"),
                        unit=str(fila.get("Unidad") or ""),
                        source="manual",
                        ingestion_method="formulario",
                        metadata={"notes": str(fila.get("Observación") or "")},
                    )
                )
            guardados = pipeline.save_manual_prices(observaciones)
            st.success(f"Se guardaron {guardados} precios con su fecha y unidad.")
        acciones[1].download_button(
            "Descargar respaldo",
            data=editor.to_csv(index=False).encode("utf-8-sig"),
            file_name=f"precios_manuales_{date.today().isoformat()}.csv",
            mime="text/csv",
            width="stretch",
        )

        with st.expander("Agregar un insumo que no figura en la tabla"):
            with st.form("nuevo_insumo"):
                nombre = st.text_input("Nombre del insumo o labor")
                columnas = st.columns(4)
                valor = columnas[0].number_input("Precio unitario", min_value=0.0, value=0.0)
                moneda_codigo = columnas[1].selectbox("Moneda", ["ARS", "USD"])
                unidad = columnas[2].selectbox("Unidad", ["kg", "l", "ha", "t", "unidad"])
                fecha_nueva = columnas[3].date_input("Fecha", value=date.today())
                observacion = st.text_input("Observación opcional")
                enviar = st.form_submit_button("Guardar nuevo insumo", type="primary")
                if enviar:
                    if not nombre.strip() or valor <= 0:
                        st.error("Ingresá un nombre y un precio mayor que cero.")
                    else:
                        pipeline.save_manual_prices(
                            [
                                PriceObservation(
                                    observed_at=fecha_nueva.isoformat(),
                                    series_id=codigo_manual(nombre),
                                    item=nombre.strip(),
                                    value=float(valor),
                                    currency=moneda_codigo,
                                    unit=unidad,
                                    source="manual",
                                    ingestion_method="formulario",
                                    metadata={"notes": observacion},
                                )
                            ]
                        )
                        st.success("El nuevo insumo quedó guardado.")
        st.caption(
            "En la copia de GitHub Desktop, los cambios quedan en el archivo local y en SQLite. En una publicación web conviene descargar el respaldo, porque el almacenamiento del servidor puede reiniciarse."
        )

    with tab_supuestos:
        supuestos = pd.DataFrame(
            [
                {
                    "Código": item.alternative_id,
                    "Alternativa": item.name,
                    "Vida útil (años)": item.useful_life_years,
                    "Rendimiento base": item.yield_dm_kg_ha,
                    "Rendimiento mínimo": item.yield_low_dm_kg_ha,
                    "Rendimiento máximo": item.yield_high_dm_kg_ha,
                    "Aprovechamiento (%)": item.utilization_rate * 100 if item.utilization_rate is not None else None,
                    "kg MS por kg de carne": item.conversion_kg_dm_per_kg_meat,
                    "Ambiente": item.soil_position,
                    "Sistema": item.establishment_system,
                }
                for item in alternatives
            ]
        )
        editor_supuestos = st.data_editor(
            supuestos,
            width="stretch",
            hide_index=True,
            num_rows="fixed",
            disabled=["Código", "Alternativa"],
            column_config={
                "Vida útil (años)": st.column_config.NumberColumn(min_value=1, step=1),
                "Rendimiento base": st.column_config.NumberColumn(min_value=0.0, format="%.0f"),
                "Rendimiento mínimo": st.column_config.NumberColumn(min_value=0.0, format="%.0f"),
                "Rendimiento máximo": st.column_config.NumberColumn(min_value=0.0, format="%.0f"),
                "Aprovechamiento (%)": st.column_config.NumberColumn(min_value=0.0, max_value=100.0),
            },
            key="editor_supuestos",
        )
        if st.button("Guardar supuestos", type="primary"):
            originales = {item.alternative_id: item for item in alternatives}
            editados = []
            for fila in editor_supuestos.to_dict("records"):
                original = originales[str(fila["Código"])]
                aprovechamiento = numero(fila.get("Aprovechamiento (%)"))
                editados.append(
                    replace(
                        original,
                        useful_life_years=int(numero(fila.get("Vida útil (años)")) or 1),
                        yield_dm_kg_ha=numero(fila.get("Rendimiento base")),
                        yield_low_dm_kg_ha=numero(fila.get("Rendimiento mínimo")),
                        yield_high_dm_kg_ha=numero(fila.get("Rendimiento máximo")),
                        utilization_rate=aprovechamiento / 100 if aprovechamiento is not None else None,
                        conversion_kg_dm_per_kg_meat=numero(fila.get("kg MS por kg de carne")),
                        soil_position=str(fila.get("Ambiente") or ""),
                        establishment_system=str(fila.get("Sistema") or ""),
                    )
                )
            cantidad = pipeline.save_alternatives(editados)
            st.success(f"Se guardaron los supuestos de {cantidad} alternativas.")
        st.info(
            "Los rendimientos históricos funcionan como punto de partida. Antes de una recomendación deben validarse según lote, ambiente, año y objetivo productivo."
        )


elif pagina == "Base regional":
    titulo_pagina(
        "Antecedentes técnicos",
        "Base regional",
        "Síntesis de información productiva y económica relevante para el sudoeste bonaerense. La pantalla prioriza los resultados y evita mostrar autores o nombres personales.",
    )
    observaciones = evidence_catalog.observations()
    tratamientos = evidence_catalog.treatments()
    cobertura = evidence_catalog.coverage()
    resumen = st.columns(4)
    resumen[0].metric("Conjuntos de antecedentes", cobertura["studies"])
    resumen[1].metric("Observaciones catalogadas", cobertura["observations"])
    resumen[2].metric("Años representados", cobertura["years"])
    resumen[3].metric("Tratamientos productivos", cobertura["treatments"])

    st.subheader("Costos históricos de implantación")
    nombres_alternativas = {item.alternative_id: item.name for item in alternatives}
    costos = [fila for fila in observaciones if fila.get("metric") == "implantation_cost"]
    if costos:
        frame_costos = pd.DataFrame(
            [
                {
                    "Alternativa": nombres_alternativas.get(fila.get("alternative_id"), fila.get("alternative_id")),
                    "Costo histórico por ha": numero(fila.get("value")),
                    "Año": fila.get("year"),
                }
                for fila in costos
            ]
        )
        figura_costos = px.bar(
            frame_costos,
            x="Alternativa",
            y="Costo histórico por ha",
            color_discrete_sequence=["#3f8a6b"],
        )
        figura_costos.update_layout(margin=dict(l=10, r=10, t=20, b=10), xaxis_title="")
        st.plotly_chart(figura_costos, width="stretch")
        st.caption("Valores nominales históricos. No deben compararse con precios actuales sin actualización.")

    st.subheader("Campañas productivas observadas")
    campañas = [fila for fila in observaciones if str(fila.get("observation_id", "")).startswith("mean_yield_")]
    if campañas:
        frame_campañas = pd.DataFrame(
            [
                {
                    "Campaña": fila.get("year"),
                    "Rendimiento medio (kg MS/ha)": numero(fila.get("value")),
                    "Precipitación (mm)": numero(fila.get("rainfall_mm")),
                }
                for fila in campañas
            ]
        )
        figura_campañas = px.scatter(
            frame_campañas,
            x="Precipitación (mm)",
            y="Rendimiento medio (kg MS/ha)",
            text="Campaña",
            color_discrete_sequence=["#23624e"],
        )
        figura_campañas.update_traces(marker={"size": 16})
        figura_campañas.update_layout(margin=dict(l=10, r=10, t=20, b=10))
        st.plotly_chart(figura_campañas, width="stretch")
        st.caption("La cantidad de campañas es reducida: la relación observada sirve como referencia, no como estimación causal.")

    with st.expander("Ver tratamientos relevados"):
        tabla_tratamientos = pd.DataFrame(
            [
                {
                    "Tratamiento": fila.get("treatment"),
                    "Especie principal": fila.get("grass_species"),
                    "Cultivar": fila.get("grass_cultivar"),
                    "Dosis principal (kg/ha)": numero(fila.get("grass_dose_kg_ha")),
                    "Leguminosa": fila.get("vicia_species"),
                    "Dosis de leguminosa (kg/ha)": numero(fila.get("vicia_dose_kg_ha")),
                }
                for fila in tratamientos
            ]
        )
        st.dataframe(tabla_tratamientos, width="stretch", hide_index=True)


elif pagina == "Calidad de datos":
    titulo_pagina(
        "Transparencia y control",
        "Calidad de datos",
        "Revisá qué fuente se actualizó, qué requiere credenciales y qué valores todavía dependen de una carga manual.",
    )
    estados = [
        {
            "Fuente": FUENTES.get(fila["source"], fila["source"]),
            "Estado": ESTADOS.get(fila["status"], fila["status"]),
            "Última ejecución": fecha_visible(fila["finished_at"]),
            "Registros": fila["rows_written"],
        }
        for fila in sync_status
    ]
    if estados:
        st.dataframe(pd.DataFrame(estados), width="stretch", hide_index=True)
    else:
        st.info("Todavía no hay procesos registrados.")

    cobertura = st.columns(3)
    cobertura[0].metric("Series de precios vigentes", len([fila for fila in prices if fila.get("value") is not None]))
    cobertura[1].metric("Cotizaciones A3", len(quotes))
    cobertura[2].metric(
        "Alternativas por validar", sum(item.validation_status.lower() != "validado" for item in alternatives)
    )

    st.subheader("Credenciales opcionales")
    credenciales = pd.DataFrame(
        [
            {
                "Integración": "Reporte formal A3",
                "Estado": "Configurada" if os.getenv("A3_MD_API_KEY") else "Falta clave privada",
                "Variable": "A3_MD_API_KEY",
            },
            {
                "Integración": "SIO-Granos",
                "Estado": "Configurada" if os.getenv("SIO_TOKEN") and os.getenv("SIO_CUIT") else "Faltan token y CUIT",
                "Variable": "SIO_TOKEN + SIO_CUIT",
            },
            {
                "Integración": "A3 Trading en tiempo real",
                "Estado": "Configurada" if os.getenv("A3_USERNAME") and os.getenv("A3_PASSWORD") else "Sin credenciales",
                "Variable": "A3_USERNAME + A3_PASSWORD",
            },
        ]
    )
    st.dataframe(credenciales, width="stretch", hide_index=True)
    st.caption("La pantalla informa si una credencial existe, pero nunca muestra su contenido.")

    with st.expander("Detalle técnico de las últimas conexiones"):
        detalles = pd.DataFrame(sync_status)
        if not detalles.empty:
            detalles = detalles.rename(
                columns={
                    "source": "fuente",
                    "started_at": "inicio",
                    "finished_at": "fin",
                    "status": "estado",
                    "rows_written": "registros",
                    "message": "detalle",
                }
            )
            columnas = [columna for columna in ["fuente", "inicio", "fin", "estado", "registros", "detalle"] if columna in detalles]
            st.dataframe(detalles[columnas], width="stretch", hide_index=True)


st.divider()
st.caption(
    "Prototipo académico de apoyo a la evaluación. Las decisiones productivas y comerciales requieren validación técnica y revisión de la calidad de cada dato."
)
