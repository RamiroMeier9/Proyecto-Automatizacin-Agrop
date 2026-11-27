# Arquitectura

## Principio rector

El programa separa tres capas que deben poder auditarse por separado:

1. **Dato observado:** precio, cotización o variable obtenida de una fuente, con fecha, unidad y método de ingreso.
2. **Supuesto técnico:** dosis, vida útil, rendimiento, aprovechamiento y conversión productiva validados por INTA.
3. **Cálculo económico:** transformación reproducible de los dos grupos anteriores en indicadores comparables.

Esta separación evita que una actualización de mercado cambie silenciosamente un coeficiente productivo y permite volver a calcular un informe histórico con los datos vigentes en esa fecha.

## Componentes

- `connectors/`: clientes de sólo lectura para BCRA, SIO-Granos y A3.
- `csv_io.py`: importación manual y normalización de plantillas.
- `storage.py`: persistencia SQLite e historial de sincronización.
- `economics.py`: costo presente, costo anual equivalente, costos unitarios y equilibrio.
- `forward_curve.py`: curva de futuros, base, tasa implícita de curva y Black-76.
- `pipeline.py`: coordinación de las actualizaciones sin acoplar una fuente con otra.
- `streamlit_app.py`: presentación y control de calidad.

## Criterios de seguridad y calidad

- Las credenciales sólo se leen desde variables de entorno.
- El conector de A3 no contiene métodos para enviar, modificar o cancelar órdenes.
- Una fuente caída no borra observaciones anteriores.
- Un valor faltante no se convierte en cero.
- Los precios de distinto producto, moneda, unidad o lugar de entrega no se promedian entre sí.
- Los snapshots incluyen la fecha de generación y el estado de cada fuente.

## Etapas posteriores

El siguiente incremento debería incorporar clima e índices forrajeros como escenarios explícitos. Una sequía, por ejemplo, no debe alterar directamente el precio de la semilla: debe modificar el rendimiento esperado o su distribución y quedar identificada como escenario.
