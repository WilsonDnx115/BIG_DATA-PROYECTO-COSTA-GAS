# Línea base del negocio — paso 1.4.1

## Qué se implementó y qué se midió

`src/quality/linea_base.py` calcula la línea base directamente desde archivos de
Bronze, sin consultar Silver, sin eliminar las filas con errores ni rellenar
identificadores. Publica agregados en `docs/evidencias/linea_base.json`.

La evidencia incluida corresponde **exclusivamente a la muestra sintética**
generada por `src/common/muestra.py`, semilla 42, 25 unidades. No reproduce los
35 archivos de la empresa ni demuestra pérdidas reales. La fecha de entrega en
Bronze es 2026-10-11 (fecha UTC del entorno); no es el período de las operaciones.

| Métrica | Resultado de esta ejecución | Alcance o límite |
|---|---|---|
| Días de producción con residuo cero | No disponible (`stock: null`) | La muestra actual no contiene producción; no se interpreta como cero días. El cálculo está probado con fixtures sintéticas. |
| Registros con SCOP disponible | 10 122; 96.8798 % de compras dentro del alcance | Filas del contrato `aba_02`, 2016–2024. No equivale a 29 órdenes F05 del informe v6. |
| Incidencias por campo clave | 1 753 ocurrencias de controles; desglose por fuente/campo en JSON | Una fila puede fallar varios controles. No equivale a 16 o 23 problemas catalogados. |
| RUC/DNI con longitud inválida | 28 de 125 filas: 22.4 %; 25.9259 % sobre los 108 informados | 17 vacíos y 13 RUC con dígito verificador inválido se cuentan por separado. |
| Precio del balón de 10 kg por canal | Ver tabla siguiente | Precio por balón del contrato `com_19`, en soles, sobre Bronze 2016–2024. |

| Canal | Mínimo S/ | Máximo S/ |
|---|---:|---:|
| MAYORISTA | 10.81 | 22.26 |
| MINORISTA | 13.12 | 27.78 |
| DIRECTO | 14.57 | 30.36 |

El rango global sintético es S/ 10.81–30.36. Para 2020, el script calcula también
P5 = S/ 18.14, P95 = S/ 26.54 y mediana = S/ 23.43, para distinguir los percentiles
del mínimo y máximo.

## Diferencias entre PLAN.md y el informe recibido

Fuente documental: `Proyecto_BigData_CostaGas_Trujillo_final_v6.docx`, sección
1.4, Tabla 1.5 y sección 3.3. El documento fue consultado para definir las
referencias; sus cifras no se inyectan como resultados calculados.

| Indicador | Referencia de PLAN.md | Referencia del informe v6 | Tratamiento |
|---|---|---|---|
| Producción con residuo cero | 22 de 22 días | 31 de 31 días en octubre de 2018; 0 cierres medidos físicamente | Se informa cobertura y residuo; cero no prueba una medición independiente. |
| Registros/órdenes SCOP | 79 | 29 órdenes con placa, enero–julio de 2023, fuente F05 | No confundir órdenes, facturas, filas con número y números distintos. El contrato actual `aba_02` corresponde a la muestra v2, no al inventario v3. |
| Problemas de calidad | 16 incidencias | 23 problemas documentados, 10 de impacto alto | Las ocurrencias fila/control se desglosan; no se comparan como si fueran el catálogo de problemas. |
| Precio B10 | S/ 17.45–24.15 | S/ 19.11–29.91 (P5–P95), mediana S/ 21.44, 2020 | Se calculan mínimo, máximo y percentiles por separado, con ventana 2020 explícita. |
| Documentos de longitud inválida | Solicita porcentaje, sin cifra de referencia | 23 de longitud inválida y 85 vacíos en el maestro del grupo | Se calcula con denominador declarado; no se transforma 23 en porcentaje sin el total del grupo. |

La muestra sintética tiene otros períodos, volúmenes y anomalías inyectadas;
por ello difiere de ambas referencias. No se ajustan los datos ni los umbrales
para forzar las cifras del informe. El JSON incluye una comparación automática,
con estados `difiere`, `no_disponible`, `no_comparable` o `coincide_numericamente`.
Una coincidencia numérica tampoco acredita reproducción con datos reales.

## Definiciones de las métricas

- **Stock:** `stock_inicial + produccion - ventas - bonificaciones - stock_final`.
  Se evalúan filas con fecha dentro del alcance y todos los términos numéricos.
  Los días con más de un registro se excluyen del cálculo y se reportan. Se usa
  tolerancia absoluta `TOL_RESIDUO_STOCK` (por defecto 0.000001), sin tolerancia
  relativa. Se cuentan las producciones negativas como advertencia de ajustes;
  no se afirma que el stock final haya sido medido físicamente.
- **SCOP:** número de filas con número no vacío en `aba_02`, dentro de
  `ANIO_INI`–`ANIO_FIN`. Se mantienen duplicados de una entrega para auditarlos;
  no se cuenta una reentrega del mismo archivo como una nueva operación.
- **Incidencias:** fechas ausentes, inválidas o fuera del alcance; celdas
  obligatorias vacías; números no convertibles, booleanos o no finitos; kg,
  precio, tipo de cambio y capacidad no positivos; placas no normalizables;
  documentos de formato/longitud inválida o RUC con verificador incorrecto;
  producción negativa; stock/ventas/bonificaciones negativos; líneas no enteras
  o negativas y duplicados por clave declarada. Los múltiples fallos de un
  campo en una misma fila se cuentan una sola vez. El control `clave_unica`
  cuenta duplicados adicionales al primero. También se cuentan filas afectadas
  por fuente sin duplicar una fila entre controles.
- **RUC/DNI:** longitud 8 u 11 antes de cualquier relleno de ceros. Se elimina
  únicamente el sufijo decimal `.0` de un entero almacenado así. Los vacíos,
  caracteres no numéricos y fallos del dígito verificador se reportan aparte.
  El porcentaje principal tiene como denominador todas las filas del maestro;
  se incluye otro porcentaje sobre documentos informados. No se consulta SUNAT.
- **Precio B10:** solo `id_producto = B10`, precio positivo y finito. Se asume
  `Price` en S/ por balón de 10 kg, según el generador y contrato actuales; no se
  multiplica por diez. Precios por kg requieren un contrato distinto. Los
  precios sin canal se incluyen en el rango global y se cuentan aparte.

## Fuentes, contratos y selección de entregas

Los contratos están declarados en `schemas.FUENTES_LINEA_BASE`:

| Código | Ruta relativa en Bronze | Uso |
|---|---|---|
| `aba_02` | `interno/estructurado/abastecimiento/aba_02/` | SCOP y controles de compras |
| `com_19` | `interno/estructurado/comercial/com_19/` | Precio B10 y controles de ventas |
| `red_02` | `interno/estructurado/redes/red_02/` | Documentos y controles del maestro |
| `pro_01` | `interno/estructurado/produccion/pro_01/` | Ecuación de stock |

Cada archivo vive bajo `fecha_carga=YYYY-MM-DD/`. Por defecto se lee la última
versión de cada archivo lógico dentro de su fuente; `--fecha-carga` selecciona
solo una entrega. No se deduplican las filas originales dentro de la entrega.
Si se renombra un archivo al reentregarlo, se considera otro archivo lógico.

Se usan los lectores CSV UTF-8 y Excel (primera hoja) existentes del proyecto,
con soporte de rutas locales y S3. La lectura S3 fue probada con dobles de
prueba, no contra un bucket real. Archivos sin las columnas declaradas fallan
explícitamente; no se adivinan encabezados ni se publican filas originales.
Las fuentes ausentes se informan como `null`. Si todas faltan, el comando falla.

**Contrato de producción local:** `FECHA`, `Stock inicial`, `Producción`,
`Ventas`, `Bonificaciones`, `Stock final`. Representa los conceptos de F36 del
informe, pero estos encabezados no han sido verificados sobre el archivo real.
`pro_01` es un código local; no se añade a los handlers de Silver. Antes de
reproducir la línea base real, se necesita un inventario autorizado de los
encabezados v3 y su correspondencia con estos contratos. La prohibición de leer
`data/raw/` durante el desarrollo sigue vigente.

Los contratos actuales no tienen columna de planta: la entrega debe estar ya
limitada a Trujillo. Los errores de fecha se auditan en todas las filas, pero
las métricas temporales solo usan fechas dentro del alcance configurado.

## Reproducción local y validación

Desde la raíz del repositorio, con el entorno virtual activado:

```bash
python -m src.common.muestra --unidades 25 --semilla 42
python -m src.ingest.internos --origen data/sample/entrega --fecha-carga 2026-10-11
python -m src.quality.linea_base --fecha-carga 2026-10-11 --tipo-datos sinteticos
python -m pytest -o addopts='' -q tests/test_linea_base.py
```

`--salida` permite escribir el JSON en otra ubicación sin reemplazar la evidencia
versionada. `--tipo-datos` registra la declaración del operador (`sinteticos`,
`reales` o `no_declarado`); no detecta automáticamente el origen ni certifica
una reproducción real. El pipeline existente puede seguir llamando `calcular()`;
su resultado se etiqueta `no_declarado` si no se especifica el tipo.

Las pruebas ejercitan las cinco métricas, producción incompleta y fechas
repetidas, reentregas, lectura Excel, lectura S3 simulada, fuentes ausentes,
contratos inválidos, separación entre longitud y dígito verificador, precios por
balón y ausencia de identificadores en el JSON. No se requieren recursos AWS.
