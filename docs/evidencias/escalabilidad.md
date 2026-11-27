# Prueba de escalabilidad · Tabla 3.11 (W24)

Qué mide: hasta dónde llega **una sola máquina** (escalado vertical, Lambda) y
qué gana el **escalado horizontal** (Glue con 2 y con 5 trabajadores) sobre el
mismo universo.

Estado: **las filas de AWS están PENDIENTES DE EJECUCIÓN.** Requieren W11 (la
primera corrida real del job de Gold), que a su vez espera W09 y los contratos
de producción y gastos. Lo medido hasta hoy es la parte local, que está abajo
con su fecha. Ninguna celda de este archivo lleva un número estimado: lo que no
se corrió dice «pendiente».

## 1. Medido: motor local, 26/11/2026

Corrida real de `python -m src.scaletest.replicar --factores 1 10 100 --motores pandas`
sobre la muestra sintética de `data/sample/entrega` (4 CSV, 9 487 filas, 0.66 MB
en 1×). Máquina: Windows 11, 16 núcleos, Python 3.12.

| factor | motor | mb_entrada | filas | grupos | segundos | memoria_pico_mb |
|---|---|---|---|---|---|---|
| 1 | pandas (vertical) | 0.66 | 9 487 | 4 151 | 0.05 | 2.6 |
| 10 | pandas (vertical) | 6.58 | 94 870 | 4 151 | 0.13 | 15.2 |
| 100 | pandas (vertical) | 65.83 | 948 700 | 4 151 | 0.82 | 142.9 |

Lectura: la memoria pico crece de forma casi lineal con el volumen (2.6 → 15.2 →
142.9 MB, es decir ×55 al multiplicar los datos por 100), que es exactamente el
comportamiento que agota a Lambda cuando el volumen sube. El tiempo crece menos
que el volumen porque el número de grupos no cambia: la agregación se mantiene,
lo que crece es la lectura.

**Lo que esta tabla no es.** Mide el motor sobre la muestra sintética, no la
entrega real de 114 MB de la Tabla 3.11. El 1× del informe son los 35 archivos
de la empresa; aquí el 1× es la muestra de 0.66 MB. No se pueden comparar las
dos escalas ni presentar estas cifras como el resultado de la prueba del
informe: son la verificación de que el procedimiento y la medición funcionan.

## 2. Pendiente: Tabla 3.11 en AWS

| Datos | Tamaño | Motor | Resultado | Costo (US$) | Estado |
|---|---|---|---|---|---|
| Internos 1× | 114 MB | Lambda (3 GB) | duración y memoria máxima (línea REPORT) | 0.00 | pendiente |
| Internos 10× | 1.14 GB | Lambda (10 GB) | duración y memoria máxima cerca de 10 240 MB | 0.00 | pendiente |
| Internos 100× | 11.4 GB | Lambda (10 GB) | memoria o tiempo agotado | 0.00 | pendiente |
| Internos 100× | 11.4 GB | Glue (2 y 5 trabajadores) | duración con 2 y con 5 | 0.15 | pendiente |
| GDELT 2020 real | 2 a 7 GB comprimidos | Lambda (una función) | duración o tiempo agotado | 0.00 | pendiente |
| GDELT 2020 real | 2 a 7 GB comprimidos | Spark: MapReduce en DataFrames (Glue, 5) | duración en la Spark UI | incluido | pendiente |
| GDELT 2020 real | 2 a 7 GB comprimidos | Spark: misma lógica con RDD (Glue, 5) | duración frente a DataFrames | incluido | pendiente |

Las dos últimas filas las cubre `src/glue/mapreduce_sql.py`, que ya tiene las
dos versiones (`construir` en SQL y `mapear_reducir_rdd`) y una prueba que
comprueba que dan los mismos totales; en AWS falta medir sus tiempos.

## 3. Procedimiento de la corrida en AWS

**Antes de lanzarla: avisar al equipo.** Es la única prueba del proyecto que
cuesta dinero (≈ US$ 0.10 a 0.15) y sube `GlueTrabajadores` a 5.

1. Replicar y conservar las réplicas en el lago:

   ```
   python -m src.scaletest.replicar --factores 1 10 100 --motores pandas --conservar
   ```

2. Subir a 10 GB la Lambda y lanzar 1×, 10× y 100×:

   ```
   aws cloudformation deploy --stack-name costagas-trujillo \
     --template-file infra/cloudformation/stack.yaml \
     --parameter-overrides LambdaMemoriaMB=10240 \
     --capabilities CAPABILITY_NAMED_IAM --profile costagas
   ```

   `LambdaMemoriaMB` admite 1024, 3008 y 10240; el 1× se mide con 3008.

3. Glue con 2 y luego con 5 trabajadores, en FLEX:

   ```
   aws glue start-job-run --job-name costagas-gold-conciliacion \
     --execution-class FLEX --profile costagas
   ```

   Los 5 trabajadores se piden con `--parameter-overrides GlueTrabajadores=5`
   en el despliegue, **solo durante la prueba**.

4. Recoger las medidas reales (no se estiman: se leen de CloudWatch y del
   historial del job):

   ```
   python -m src.scaletest.aws --lambda costagas-bronze-to-silver --job costagas-gold-conciliacion
   ```

5. Al terminar, dejar todo como estaba:

   ```
   aws cloudformation deploy --stack-name costagas-trujillo \
     --template-file infra/cloudformation/stack.yaml \
     --parameter-overrides LambdaMemoriaMB=3008 GlueTrabajadores=2 \
     --capabilities CAPABILITY_NAMED_IAM --profile costagas
   python -m src.scaletest.replicar --factores 1 --motores pandas   # borra sim/escala/
   ```

   Los tiempos se toman de la **Spark UI** dentro del job y no del tiempo total
   de la corrida: FLEX puede tardar en arrancar y la espera en la cola no debe
   contaminar la comparación entre 2 y 5 trabajadores.

## 4. Capturas que faltan adjuntar

- `capturas/escala_lambda_1x_report.png` — línea REPORT de la invocación 1×.
- `capturas/escala_lambda_10x_report.png` — ídem 10×, memoria cerca del límite.
- `capturas/escala_lambda_100x_agotada.png` — la invocación que se agota.
- `capturas/escala_glue_2_vs_5.png` — historial del job con las dos corridas.
- `capturas/escala_sparkui_df_vs_rdd.png` — las dos etapas en la Spark UI.

## 5. Nota de datos

Las réplicas son datos **sintéticos para medir**, derivados de la muestra: cada
copia desplaza placas y documentos para que las uniones sigan siendo válidas.
No entran a Silver ni a Gold, no se publican como cifras del negocio y se borran
al terminar. GDELT real sí alimenta el análisis.
