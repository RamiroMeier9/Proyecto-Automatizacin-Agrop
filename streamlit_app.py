from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

from inta_forrajes.csv_io import read_alternatives
from inta_forrajes.evidence import EvidenceCatalog
from inta_forrajes.forward_curve import build_forward_curve, option_implied_volatility
from inta_forrajes.pipeline import Pipeline


ROOT = Path(__file__).resolve().parent
pipeline = Pipeline(ROOT)

st.set_page_config(page_title="INTA Forrajes", page_icon="🌱", layout="wide")
st.title("Evaluación económica de alternativas forrajeras")
st.caption("Prototipo académico para discusión con INTA Coronel Suárez — no es una recomendación oficial.")

with st.sidebar:
    st.header("Actualización")
    if st.button("Importar archivos manuales", width="stretch"):
        result = pipeline.import_manual()
        st.success(f"Importados: {result['prices']} precios y {result['a3_quotes']} cotizaciones")
    if st.button("Actualizar fuentes", width="stretch"):
        with st.spinner("Consultando fuentes habilitadas…"):
            st.json(pipeline.update())
    st.caption("Las fuentes sin credenciales se omiten y quedan identificadas.")

prices = pipeline.storage.latest_prices()
quotes = pipeline.storage.latest_a3_quotes()
sync_status = pipeline.storage.sync_status()
alternatives = read_alternatives(ROOT / "data" / "manual" / "alternatives.csv")
evidence_catalog = EvidenceCatalog(ROOT / "data" / "reference")

summary_tab, evidence_tab, costs_tab, futures_tab, options_tab, data_tab, quality_tab = st.tabs(
    ["Resumen", "Evidencia regional", "Costos", "Futuros", "Opciones", "Datos", "Calidad"]
)

with summary_tab:
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Series de precios", len(prices))
    col2.metric("Contratos A3", len(quotes))
    col3.metric("Alternativas", len(alternatives))
    pending = sum(item.validation_status.lower() != "validado" for item in alternatives)
    col4.metric("Alternativas por validar", pending)
    st.info(
        "El tablero conserva la diferencia entre datos de mercado, presupuestos manuales y "
        "supuestos técnicos. Un faltante se muestra como faltante; nunca se reemplaza por cero."
    )

with evidence_tab:
    studies = evidence_catalog.studies()
    observations = evidence_catalog.observations()
    treatments = evidence_catalog.treatments()
    coverage = evidence_catalog.coverage()
    cols = st.columns(4)
    cols[0].metric("Trabajos catalogados", coverage["studies"])
    cols[1].metric("Observaciones", coverage["observations"])
    cols[2].metric("Años con datos", coverage["years"])
    cols[3].metric("Tratamientos", coverage["treatments"])

    st.subheader("Trabajos y alcance")
    st.dataframe(pd.DataFrame(studies), width="stretch", hide_index=True)

    cost_rows = [row for row in observations if row.get("metric") == "implantation_cost"]
    if cost_rows:
        cost_frame = pd.DataFrame(cost_rows)
        cost_frame["value"] = pd.to_numeric(cost_frame["value"], errors="coerce")
        figure = px.bar(
            cost_frame,
            x="alternative_id",
            y="value",
            title="Costos publicados por INTA en 2023 — referencia histórica",
        )
        figure.update_layout(xaxis_title="Alternativa", yaxis_title="ARS de 2023 por ha")
        st.plotly_chart(figure, width="stretch")

    annual_rows = [row for row in observations if row.get("observation_id", "").startswith("mean_yield_")]
    if annual_rows:
        annual_frame = pd.DataFrame(annual_rows)
        annual_frame["value"] = pd.to_numeric(annual_frame["value"], errors="coerce")
        annual_frame["rainfall_mm"] = pd.to_numeric(annual_frame["rainfall_mm"], errors="coerce")
        yield_figure = px.scatter(
            annual_frame,
            x="rainfall_mm",
            y="value",
            text="year",
            title="Ensayo El Sendero: lluvia y rendimiento medio observado",
        )
        yield_figure.update_traces(marker={"size": 14})
        yield_figure.update_layout(xaxis_title="Precipitación durante la evaluación (mm)", yaxis_title="kg MS/ha")
        st.plotly_chart(yield_figure, width="stretch")
        st.caption("Son sólo dos campañas: la figura describe lo observado y no prueba por sí sola causalidad.")

    with st.expander("Ver los 17 tratamientos del ensayo 2020–2021"):
        st.dataframe(pd.DataFrame(treatments), width="stretch", hide_index=True)

    st.info(
        "La aplicación no elegirá una alternativa como ‘la mejor’ sin definir ambiente y objetivo. "
        "Separará, como mínimo, costo por kg de materia seca, estabilidad entre campañas, duración, "
        "aporte al bache invernal y resultado económico bajo precios actuales."
    )

with costs_tab:
    if not alternatives:
        st.warning("No hay alternativas cargadas.")
    else:
        labels = {item.name: item.alternative_id for item in alternatives}
        selected_name = st.selectbox("Alternativa", list(labels))
        selected_alternative = next(item for item in alternatives if item.alternative_id == labels[selected_name])
        rate_percent = st.number_input("Tasa de descuento anual (%)", 0.0, 200.0, 10.0, 0.5)
        default_yield = float(selected_alternative.yield_dm_kg_ha or 0)
        yield_value = st.number_input(
            "Rendimiento anual (kg MS/ha)",
            min_value=0.0,
            value=default_yield,
            step=100.0,
            help=(
                f"Referencia histórica: {selected_alternative.yield_low_dm_kg_ha or 's/d'} a "
                f"{selected_alternative.yield_high_dm_kg_ha or 's/d'} kg MS/ha."
            ),
        )
        result = pipeline.evaluate(labels[selected_name], rate_percent / 100, yield_value or None)
        metrics = st.columns(5)
        metrics[0].metric(
            "Costo presente/ha",
            "Pendiente" if not result.cost_complete else f"$ {result.present_value_cost_ha:,.0f}",
        )
        metrics[1].metric(
            "Costo anual equivalente/ha",
            "Pendiente" if not result.cost_complete else f"$ {result.equivalent_annual_cost_ha:,.0f}",
        )
        metrics[2].metric(
            "Costo/kg MS producida",
            "Pendiente" if result.cost_per_kg_produced_dm is None else f"$ {result.cost_per_kg_produced_dm:,.2f}",
        )
        metrics[3].metric(
            "Costo/kg MS aprovechada",
            "Pendiente" if result.cost_per_kg_usable_dm is None else f"$ {result.cost_per_kg_usable_dm:,.2f}",
        )
        metrics[4].metric(
            "Costo/kg carne equivalente",
            "Pendiente" if result.cost_per_kg_meat_equivalent is None else f"$ {result.cost_per_kg_meat_equivalent:,.2f}",
        )
        if result.missing_inputs:
            st.warning("Faltan datos para cerrar el cálculo: " + "; ".join(result.missing_inputs))
        st.subheader("Costos computados por año")
        st.dataframe(
            pd.DataFrame(
                [{"Año": year, "Costo": value} for year, value in result.cash_costs_by_year.items()]
            ),
            width="stretch",
            hide_index=True,
        )

with futures_tab:
    futures = [row for row in quotes if row.get("instrument_type") == "future"]
    if not futures:
        st.info("Todavía no hay futuros cargados. Complete la watchlist de A3 o el CSV manual.")
    else:
        underlying_values = sorted({row.get("underlying") or "Sin clasificar" for row in futures})
        underlying = st.selectbox("Subyacente", underlying_values)
        selected = [row for row in futures if (row.get("underlying") or "Sin clasificar") == underlying]
        spot = st.number_input("Precio disponible comparable (opcional)", min_value=0.0, value=0.0)
        curve = build_forward_curve(selected, spot_price=spot or None)
        frame = pd.DataFrame(curve)
        if not frame.empty:
            figure = px.line(frame, x="maturity_date", y="future_price", markers=True, hover_name="symbol")
            figure.update_layout(xaxis_title="Vencimiento", yaxis_title="Precio")
            st.plotly_chart(figure, width="stretch")
            st.dataframe(frame, width="stretch", hide_index=True)
        st.caption(
            "La curva es una referencia de precios pactados hoy. No equivale a una predicción pura: "
            "también refleja base, tasa, acarreo, estacionalidad, cobertura y liquidez."
        )

with options_tab:
    option_rows = [row for row in quotes if row.get("instrument_type") == "option"]
    future_rows = [row for row in quotes if row.get("instrument_type") == "future"]
    if not option_rows or not future_rows:
        st.info("Para calcular volatilidad implícita se necesitan opciones y el futuro correspondiente.")
    else:
        risk_free = st.number_input("Tasa libre de riesgo anual (%)", 0.0, 300.0, 10.0, 0.5) / 100
        future_map = {
            (row.get("symbol"), row.get("maturity_date")): next(
                (float(row[key]) for key in ("settlement", "last") if row.get(key) is not None),
                None,
            )
            for row in future_rows
        }
        enriched = []
        for row in option_rows:
            future_price = future_map.get((row.get("underlying"), row.get("maturity_date")))
            implied = option_implied_volatility(row, future_price, risk_free_rate=risk_free) if future_price else None
            enriched.append({**row, "future_price": future_price, "implied_volatility": implied})
        st.dataframe(pd.DataFrame(enriched), width="stretch", hide_index=True)
        st.caption("Una opción sin precio, strike, tipo, vencimiento o futuro comparable queda sin cálculo.")

with data_tab:
    st.subheader("Últimos precios")
    if prices:
        st.dataframe(pd.DataFrame(prices), width="stretch", hide_index=True)
    else:
        st.info("Todavía no se importaron precios válidos.")
    st.subheader("Últimas cotizaciones A3")
    if quotes:
        st.dataframe(pd.DataFrame(quotes), width="stretch", hide_index=True)
    else:
        st.info("Todavía no se importaron cotizaciones.")

with quality_tab:
    st.subheader("Estado de las fuentes")
    if sync_status:
        st.dataframe(pd.DataFrame(sync_status), width="stretch", hide_index=True)
    else:
        st.info("Aún no se ejecutó ninguna actualización.")
    st.subheader("Supuestos técnicos")
    st.dataframe(pd.DataFrame([asdict(item) for item in alternatives]), width="stretch", hide_index=True)
