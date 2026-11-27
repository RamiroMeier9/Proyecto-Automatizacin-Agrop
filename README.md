# INTA Forrajes — evaluación económica reproducible

Prototipo académico para una posible PPS en INTA Coronel Suárez. El proyecto reúne precios automáticos y cargas manuales, calcula costos de implantación y mantenimiento de alternativas forrajeras y permite incorporar futuros y opciones de A3 Mercados como información de expectativas y cobertura.

> **Alcance:** no es una aplicación oficial de INTA ni de A3 Mercados. Los resultados requieren validación técnica con el equipo de INTA antes de usarse para recomendaciones productivas o decisiones comerciales.

## Qué resuelve el MVP

- Guarda observaciones en SQLite con fecha, fuente, unidad y trazabilidad.
- Actualiza automáticamente el tipo de cambio de referencia desde la API pública del BCRA.
- Integra SIO-Granos cuando se proporcionan CUIT y token.
- Actualiza cierres históricos de futuros y opciones agropecuarias desde el visor de A3.
- Deja preparada la API formal de A3 mediante `x-api-key` y la conexión Trading REST para una etapa posterior.
- Cataloga trabajos regionales, campañas, tratamientos y condiciones ambientales para no comparar evidencia incompatible.
- Permite importar precios, coeficientes técnicos y cotizaciones de A3 mediante CSV cuando no existe API o el acceso todavía no fue habilitado.
- Calcula costo por hectárea, costo anual equivalente, costo por kg de materia seca aprovechada, costo por kg de carne equivalente, valor actual neto y punto de equilibrio.
- Construye una curva de futuros, bases respecto del precio disponible y volatilidad implícita de opciones mediante Black-76.
- Presenta los resultados en un tablero Streamlit.

## Inicio rápido

Requiere Python 3.11 o posterior.

```bash
python -m venv .venv
source .venv/bin/activate        # En Windows: .venv\Scripts\activate
pip install -e ".[app,dev]"
cp .env.example .env
python -m inta_forrajes.cli init-db
python -m inta_forrajes.cli import-manual
streamlit run streamlit_app.py
```

El núcleo de cálculo y las pruebas usan únicamente la biblioteca estándar. Streamlit, pandas y Plotly se instalan sólo para el tablero.

## Flujo de datos

1. `update` consulta las fuentes automáticas habilitadas y conserva cada observación con su fecha de origen.
2. `import-manual` incorpora los CSV de `data/manual/` sin borrar datos históricos.
3. El motor económico toma cantidades técnicas de `recipes.csv` y las vincula con precios mediante `price_series_id`.
4. El tablero muestra faltantes de precio o de coeficientes; no los reemplaza silenciosamente por cero.

Comandos principales:

```bash
python -m inta_forrajes.cli update
python -m inta_forrajes.cli update --source bcra
python -m inta_forrajes.cli update --source a3
python -m inta_forrajes.cli publish-public
python -m inta_forrajes.cli discover-a3
python -m inta_forrajes.cli evaluate --alternative pastura_loma_directa
python -m unittest discover -s tests -v
```

## A3 Mercados

El MVP consulta automáticamente los cierres agropecuarios que A3 expone en su visor de Market Data, incluidos precio de ajuste, último, volumen e interés abierto. Para la API formal se admite `A3_MD_API_KEY` mediante el header `x-api-key`; durante el desarrollo debe utilizarse UAT. También permanece disponible el conector Trading REST, que solicita un token con `X-Username` y `X-Password` y permite consultar una watchlist específica.

Nunca se guardan credenciales dentro del repositorio. Si una integración no está disponible, se puede completar `data/manual/a3_quotes.csv` con una exportación controlada.

La curva de futuros **no se presenta como un pronóstico seguro**. Refleja precios negociados hoy para distintos vencimientos y puede incorporar expectativas, costo de acarreo, tasa, estacionalidad, riesgo y base local. Las opciones permiten añadir información sobre volatilidad y escenarios, pero su interpretación exige liquidez suficiente.

## Datos manuales

- `manual_prices.csv`: presupuestos de semillas, fertilizantes, herbicidas, labores y otros insumos.
- `alternatives.csv`: vida útil, rendimiento de materia seca, porcentaje de aprovechamiento y conversión productiva.
- `recipes.csv`: cantidades requeridas por alternativa y año.
- `a3_quotes.csv`: vía alternativa para futuros y opciones.

Los antecedentes públicos ya incorporados están en `data/reference/`: informe de costos 2023 de Gonzalo Arroquy, ensayo de verdeos 2020–2021 de Darío Morris y colaboradores, tratamientos y contexto anual. Los coeficientes provenientes de esos trabajos están marcados como referencias históricas que deben revalidarse.

Los archivos entregados son plantillas. Los campos numéricos vacíos son deliberados: deben acordarse con Gonzalo Arroquy y el equipo de INTA, o reemplazarse por datos documentados.

## Automatización en GitHub

El workflow `.github/workflows/update-data.yml` se ejecuta cinco veces por día hábil, aproximadamente a las 08:17, 11:17, 14:17, 17:17 y 20:17 de Argentina. GitHub puede demorar algunos minutos el inicio. También puede lanzarse manualmente desde la pestaña **Actions**.

Cada ejecución consulta BCRA y el visor agropecuario público de A3. Si encuentra información nueva, actualiza `data/public/latest.json` y crea un commit automático en `main`. Por eso, al usar **Fetch origin** y luego **Pull origin** en GitHub Desktop, la copia local recibe los datos publicados más recientes.

El archivo público se genera con una lista cerrada de campos y fuentes. No incluye la base SQLite, credenciales, respuestas autenticadas de A3 ni datos privados de SIO-Granos. Esas integraciones pueden añadirse luego como secretos y conservarse en artefactos privados, sin mezclarlas con el archivo versionado.

## Próximas etapas sugeridas

1. Validar con INTA las alternativas, dosis, rendimientos y vida útil.
2. Regenerar la API-Key compartida, configurar UAT como secreto y obtener el token de SIO-Granos.
3. Añadir combustibles, clima y precios locales con conectores separados y pruebas de calidad.
4. Incorporar escenarios climáticos y productivos, no un único rendimiento promedio.
5. Publicar el repositorio sólo después de definir privacidad, licencia y responsable de mantenimiento.

La arquitectura y el diccionario de datos están en `docs/`.
