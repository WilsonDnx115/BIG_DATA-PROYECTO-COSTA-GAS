# 0013 · Modelo base v6 y evidencia documental

- **Fecha:** 2026-10-10
- **Estado:** aceptada
- **Responsable del paquete:** Wilson Mirano, análisis y modelado

## Contexto

WP 0.8 corrige el catálogo y la línea base técnica según el informe v6 y los
hallazgos M1–M3 del Plan de Corrección. Las reglas sintéticas v2 tienen otras
definiciones. Faltan cuatro tablas normalizadas Silver/Gold y los registros de
validación documental; copiar cifras del informe no constituye una medición.

## Alternativas evaluadas

1. Adaptar los datos sintéticos v2 y publicarlos como evidencia v6. Descartada:
   cambia el significado de las señales y no verifica los resultados reales.
2. Mantener el z del costo por kg vendido sin separar roles y usar S1/S8 como
   etiquetas. Descartada: transporte necesita kg transportados; S8 no es
   resoluble y las etiquetas débiles no prueban precisión documental.
3. Separar la compatibilidad v2, declarar una interfaz normalizada y validar el
   modelo v6 mediante expedientes y revisión independiente. Elegida.

## Criterio

No inventar mediciones ni leer datos crudos. Conservar la ejecución sintética
existente para sus pruebas y permitir integración con WP 0.2 cuando sus tablas
estén disponibles. Priorizar por evidencia y percentil dentro de cada señal:
los puntajes de reglas diferentes no están calibrados entre sí.

## Consecuencia

- [Catálogo](../../src/signals/catalogo.yaml) S1–S12, seis módulos WP 0.8 y S8
  no resoluble; S12 conserva su entrega independiente WP 0.11.
- [Contratos](../../src/signals/contratos.py) normalizados, claves únicas y
  selección de columnas sin nombres ni documentos personales.
- [MAD](../../src/models/base_mad.py) sobre el log del combustible por tonelada,
  agrupado por rol, con ambas colas. MAD cero y volumen inválido quedan sin puntaje.
- [Evaluación](../../src/models/evaluacion_base.py) con top y control aleatorio
  ciego; métricas documentales ausentes como `null`. Kg de contexto no equivalen
  a pérdida y no se monetizan como tal.
- Módulos `*_fixture.py` y evidencias `*_fixture` para el pipeline v2. Los
  resultados de prueba v6 se exportan solo fuera del checkout o bajo `.build/`.
- El cierre medido de 4.2.3 y 4.2.4 queda pendiente de datos reales y revisión;
  detalles en [la evidencia del paquete](../evidencias/wp_0.8_modelo_base.md).
