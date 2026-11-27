# Diccionario de datos

## Precios

| Campo | Significado |
|---|---|
| `observed_at` | Fecha de la observación en la fuente. |
| `series_id` | Identificador estable usado para vincular una receta con un precio. |
| `item` | Descripción legible. |
| `value` | Valor numérico; nunca se guarda vacío ni se presume cero. |
| `currency` | Moneda ISO cuando está disponible. |
| `unit` | Unidad económica o física, por ejemplo ARS/kg o USD/t. |
| `source` | Organismo, mercado o indicación `manual`. |
| `ingestion_method` | `api` o `csv`. |

## Alternativas y recetas

| Campo | Significado |
|---|---|
| `useful_life_years` | Horizonte durante el cual se anualiza la implantación. |
| `yield_dm_kg_ha` | Rendimiento anual esperado de materia seca por hectárea. |
| `utilization_rate` | Fracción realmente aprovechada por los animales, de 0 a 1. |
| `conversion_kg_dm_per_kg_meat` | Materia seca necesaria para un kg de carne equivalente. |
| `year` | Año en que ocurre el costo; 0 es implantación. |
| `quantity` | Dosis o cantidad física por hectárea. |
| `price_series_id` | Serie de precios que valoriza la cantidad. |
| `manual_unit_price` | Reemplazo explícito para un escenario; tiene prioridad sobre la serie. |

## A3

| Campo | Significado |
|---|---|
| `symbol` | Símbolo exacto reconocido por A3. |
| `instrument_type` | `future` u `option`. |
| `maturity_date` | Vencimiento contractual. |
| `settlement` | Precio de ajuste; referencia prioritaria para futuros. |
| `last` | Último precio operado. |
| `bid` / `ask` | Mejor compra y mejor venta. |
| `open_interest` | Interés abierto. |
| `volume` | Volumen operado. |
| `strike` | Precio de ejercicio de una opción. |
| `option_type` | `call` o `put`. |

La base y la tasa anualizada de la curva sólo son comparables si el precio disponible y el futuro representan el mismo producto, calidad, moneda, unidad y plaza, o si se documenta el ajuste aplicado.
