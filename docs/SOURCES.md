# Fuentes y trazabilidad

## Evidencia regional

- [INTA: costos de implantación de pasturas y verdeos 2023](https://repositorio.inta.gob.ar/xmlui/bitstream/handle/20.500.12123/14066/INTA_CRBsAsSur_EEACesareoNaredo_Arroquy_Gonzalo_Pasturas_verdeos_invierno.pdf)
- [INTA: producción de verdeos puros y mezclas con vicia](https://repositorio.inta.gob.ar/bitstream/handle/20.500.12123/13568/INTA_CRBsAsSur_EEACesareoNaredo_Morris_D_Verdeos_invierno_producci%C3%B3n.pdf)

El material de Economía Agraria localizado en el Drive del estudiante se usa como orientación metodológica, pero no se copia al repositorio. Allí aparecen como ejes la comparación de alternativas productivas, la Unidad Económica Agraria, los precios relativos y las series históricas regionales.

## Datos de mercado

- [A3 Mercados: APIs y documentación](https://a3mercados.com.ar/tecnologia/apis)
- [A3 Mercados: datos de mercado](https://a3mercados.com.ar/info-de-mercado/datos-de-mercado)
- [A3 Mercados: visor de Market Data](https://marketdata.mae.com.ar/)
- [BCRA: APIs públicas](https://www.bcra.gob.ar/apis-banco-central/)
- [SIO-Granos](https://www.siogranos.com.ar/)

La API formal de Market Data usa el header `x-api-key`. Las claves se leen desde variables de entorno; nunca deben incorporarse a archivos versionados. Para futuros y opciones agropecuarias el MVP también consume los datos de cierre expuestos por el visor público de A3, conservando fecha, contrato, volumen, interés abierto y precio de ajuste.

## Regla de interpretación

Los precios futuros no son una predicción puntual. Para convertirlos en una referencia útil para Coronel Suárez es necesario compararlos con un precio disponible de producto, calidad, moneda, unidad, fecha y plaza compatibles, y explicitar la base o el ajuste de transporte aplicado.
