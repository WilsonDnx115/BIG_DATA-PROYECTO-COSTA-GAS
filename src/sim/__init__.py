"""Simulación para validar el detector de desvíos (commits A16 a A18).

Dos escenarios sobre la misma serie:

* **A**: operación sin robos, calibrada con los agregados publicados de 2020. Sirve
  para fijar el umbral del detector con un presupuesto de falsas alarmas.
* **B**: el mismo escenario A con robos inyectados desde una especificación que **no
  está en el repositorio**, para medir la detección sin que quien diseñó el detector
  sepa dónde están.

Nada de aquí es un dato de la empresa: son series sintéticas con identificadores
ficticios. Se escriben solo en `sim/`, nunca en Silver ni en Gold.
"""
