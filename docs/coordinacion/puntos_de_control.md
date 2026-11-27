# Acuerdo de los tres puntos de control con la gerencia

Proyecto Costa Gas Trujillo · preparado por Coordinación para la conformidad de la gerencia de planta.
Referencias: informe v16, Tabla 4.8i y Figura 4.6; `docs/Plan_Implementacion_Codigo_v15.md`,
bloque 3 (controles preventivos).

**Estado:** propuesta del equipo, **pendiente de conformidad**. Los umbrales marcados «propuesta»
son valores de trabajo del equipo; rigen solo cuando la gerencia los firma en la sección 5.

## 1. Principios comunes

- Un color rojo o ámbar es una **alerta para revisar con documentos**, no un robo confirmado. La
  decisión final la toma la persona responsable con el expediente a la vista.
- El sistema retiene o avisa; **no castiga ni acusa**. Las alertas se muestran con identificadores
  seudonimizados; no se publican nombres, DNI ni RUC de personas naturales.
- Toda revisión queda registrada en el portal (solo inserción, ADR 0019).
- Si una fuente de Silver incumple sus metas de calidad, el control afectado se informa como
  «sin dato confiable», no como verde.

## 2. Punto 1 · Antes del pago (tesorería)

| Aspecto | Acuerdo propuesto |
|---|---|
| Qué se controla | Cada factura de compra de GLP antes de pagarla |
| Herramienta | Control previo al pago en el portal: rojo, ámbar o verde por factura en menos de 5 s |
| Señales | S12 (factura ausente o con kg distinto entre tesorería y logística), S2 (SCOP ausente o repetido), S3 (precio fuera de lo pactado), S4 (carga sobre la capacidad autorizada), S6 (tipo de cambio distinto del oficial) |
| Quién actúa | Tesorería |
| Verde | Se paga según el procedimiento habitual |
| Ámbar | Se paga después de revisar el documento que originó el aviso, en el mismo día |
| Rojo | Se retiene el pago hasta tener el segundo registro (orden SCOP o guía) que explique la diferencia; plazo de revisión: 2 días hábiles |
| Umbral | S3: precio más de 5 % sobre lo pactado (`TOL_PRECIO_COMPRA`, propuesta). S6: tipo de cambio que difiere del oficial en más de 1 % (`TOL_TIPO_CAMBIO`, propuesta). S12: diferencia de kg entre tesorería y logística mayor que ____ % (a fijar por la gerencia; `config.py` aún no tiene este parámetro) |

## 3. Punto 2 · Antes del despacho (jefatura de planta)

| Aspecto | Acuerdo propuesto |
|---|---|
| Qué se controla | Cada unidad (cisterna o reparto) antes de su siguiente carga |
| Herramienta | Semáforo diario de unidades: correo a las 6:30 y página «Semáforo de unidades» de Grafana |
| Señales | KPI 4 (combustible por tonelada, z robusto por rol), S1 (placa cargada distinta de la facturada), S7 (unidad no habilitada para GLP), S9 (combustible sin venta o carga proporcional) |
| Quién actúa | Jefatura de planta |
| Verde | Despacho normal |
| Ámbar | Despacho normal; la jefatura revisa el expediente de la unidad en la semana |
| Rojo | Antes de cargar, la jefatura verifica la orden SCOP y la guía de la unidad; si la unidad no está habilitada para GLP (S7), no se carga |
| Umbral | Rojo: \|z\| > 3.5 del log de S/ por tonelada dentro de su rol (`UMBRAL_Z_MAD`), propuesta del modelo base. Ámbar: ____ (a fijar por la gerencia) |

## 4. Punto 3 · Antes de la siguiente entrega a un cliente (comercial)

| Aspecto | Acuerdo propuesto |
|---|---|
| Qué se controla | Cada distribuidor o cliente antes de su siguiente pedido |
| Herramienta | Revisión por cliente dentro de `v_semaforo_unidades` y del tablero |
| Señales | S5 (volumen a distribuidor superior a su capacidad) y S10 (precio de venta bajo la mediana de su canal) |
| Quién actúa | Área comercial |
| Verde | Entrega normal |
| Ámbar | Entrega normal; comercial confirma el precio o la capacidad antes del cierre de mes |
| Rojo | Antes de la siguiente entrega, comercial revisa el contrato, la capacidad registrada y el precio pactado del cliente |
| Umbral | S10: precio más de 10 % bajo la mediana del canal (`TOL_PRECIO_S10`, propuesta). S5: volumen del mes mayor que ____ veces la capacidad registrada (a fijar por la gerencia) |

## 5. Umbral de planta (KPI 1) y conformidad

| Indicador | Referencia propuesta | Valor que fija la gerencia |
|---|---|---|
| KPI 1 · diferencia no explicada de planta | 2 % de lo comprado (`UMBRAL_KPI_DIF`) | ____ % |
| Merma técnica de planta | No fijada por la empresa; el equipo usa 0.5 % como supuesto de trabajo (`MERMA_TECNICA_PCT`) | ____ % · fuente: ____________ |

Mientras la gerencia no fije la merma técnica, el tablero muestra el KPI 1 sin merma y con la
leyenda «sin merma fijada» en el valor con merma.

**Conformidad de la gerencia**

| | |
|---|---|
| Cargo | |
| Fecha | |
| Conformidad (sí / con observaciones / no) | |
| Observaciones | |

El documento firmado (con nombre y firma) se guarda fuera del repositorio, con la empresa; aquí
solo se anotan el cargo, la fecha y los valores acordados.

Los valores firmados se registran en `.env` o en SSM por ingeniería de datos y se anotan en
`docs/coordinacion/actas.md` con su fecha. Un cambio posterior de umbral requiere una nueva
conformidad.
