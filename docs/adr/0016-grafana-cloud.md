# 0016 · Tablero en Grafana Cloud en lugar de Power BI Desktop

- **Fecha:** 2026-11-12
- **Estado:** aceptada
- **Responsable:** Oftcher Anghelo Alcántara Pérez (Calidad y documentación)
- **Reemplaza a:** [0010 · Tablero en Power BI Desktop](0010-power-bi-desktop.md)

## Contexto
El sistema no entrega un documento: publica tablas y vistas en Gold y un tablero que debe
reflejar cada carga en minutos. La arquitectura encadena todo por eventos y busca que una
entrega nueva se vea en menos de 5 minutos, sin que nadie abra un equipo ni ejecute nada.

El [ADR 0010](0010-power-bi-desktop.md) eligió Power BI Desktop solo porque QuickSight cobra por
usuario. Al llegar a la capa de consumo quedó claro que esa opción no cumple el requisito: Power
BI Desktop es una **aplicación local**, su archivo `.pbix` no se publica ni se refresca solo, y
la gerencia no puede entrar desde el navegador. Publicarlo exigiría Power BI Service, que a su
vez necesita una puerta de enlace instalada en un equipo local encendido.

## Alternativas evaluadas
1. **Power BI Desktop.** Descartada: es local, no se refresca solo y no hay forma gratuita de
   publicarlo.
2. **Power BI Service.** Descartada: exige una puerta de enlace en un equipo local permanente.
3. **Amazon QuickSight.** Descartada: cobra por usuario al mes y está en la lista de servicios
   prohibidos por costo fijo de `CLAUDE.md`.
4. **Grafana Cloud, plan gratuito.** Elegida.

## Criterio
- El plan gratuito cubre el uso del proyecto: menos de 10 usuarios y un refresco por minuto.
- Tiene complemento oficial de Amazon Athena, así que consulta Gold sin servicios intermedios.
- Está en la nube y se refresca solo: la gerencia entra desde el navegador, sin instalar nada y
  sin acceso a la consola de AWS.
- No añade costo fijo: lo que se paga es Athena por consulta, y cada página hace una sola
  consulta por refresco cuyos paneles comparten el resultado, de modo que el gasto depende de
  las horas de tablero abierto y no del número de paneles.

## Consecuencia
- Origen de datos Amazon Athena en Grafana Cloud: región `us-east-2`
  ([ADR 0011](0011-region-us-east-2.md)), workgroup `costagas-wg`, base `costagas_gold` y salida
  `athena-results/`.
- Lo consulta el usuario técnico **`svc-dashboard`**, cuya política `costagas-dashboard-lectura`
  solo permite leer Gold: no puede leer Bronze ni Silver. Su clave vive únicamente en Grafana
  Cloud, cifrada, y se rota cada 90 días y en cada cambio de roles. **Nunca en el repositorio.**
- Seis páginas (Tabla 4.11 del informe): Resumen, Balance y unidades, Bandeja de alertas,
  Mercado, Semáforo de unidades y Revisión ciega. El paso 4.4.4 de [PLAN.md](../../PLAN.md)
  detalla el contenido y el usuario de cada una.
- La página «Revisión ciega» oculta la columna de probabilidad y el puntaje de rareza y presenta
  los casos en orden aleatorio, para que la lista no anticipe al revisor qué espera el modelo.
- Desaparecen `dashboard/costagas.pbix` y el conector ODBC de Athena; los paneles exportados se
  guardan en `dashboard/grafana/` y la conexión en `dashboard/conexion.md`.
- El informe ya recoge el cambio en su bitácora, con fecha 12/11/2026.
