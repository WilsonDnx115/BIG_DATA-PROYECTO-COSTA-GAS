# Guía para el equipo: avisos por correo, Grafana Cloud y claves

Proyecto Costa Gas Trujillo · cuenta AWS «Hold My Coffee» · región `us-east-2`.
Cada paso indica quién lo hace. Nadie comparte contraseñas ni claves por chat o por correo: cada clave se pega directamente donde se usa.

---

## 1. Confirmar la suscripción a los avisos (cada integrante, 1 minuto)

Al desplegar el stack, AWS envía un correo a cada dirección de la lista de alertas del proyecto.

1. Busca en tu bandeja (y en *Spam* o *Promociones*) un correo de **AWS Notifications** `<no-reply@sns.amazonaws.com>` con el asunto **«AWS Notification - Subscription Confirmation»**.
2. Revisa que en el texto aparezca el tema **costagas-alertas-operacion**. El primer integrante de la lista recibe además **costagas-alertas-negocio**.
3. Haz clic en **Confirm subscription**. Se abre una página que dice **«Subscription confirmed!»**. Listo.

> **Ojo:** el 25/11/2026 el primer intento de despliegue se revirtió, así que puede que recibas **dos** correos de confirmación. Usa el **más reciente**. El primero apunta a un tema que ya no existe y mostrará un error si lo abres.

Qué recibirás desde entonces:
- **costagas-alertas-operacion:** un correo si falla una Lambda, si una corrida de Glue falla o vence, o si hay eventos en la cola de fallas.
- **costagas-alertas-negocio:** un correo cuando el modelo marca una factura o una variable cambia de distribución (PSI > 0.2).

Si no te llegó, avisa al titular para que revise tu dirección en el stack. El enlace de confirmación vence a los 3 días; después, el titular reenvía la invitación desde la consola de SNS («Request confirmation»).

**No hagas clic en «Unsubscribe»**: dejarías de recibir los avisos del proyecto.

---

## 2. Cuenta de Grafana Cloud (titular, 5 minutos, gratis)

1. Entra a **grafana.com** → **Create free account**. Usa el correo del equipo y una contraseña propia.
2. Elige un nombre para el stack, por ejemplo `costagas`, y la región más cercana (**US**).
3. Al terminar, entra a tu instancia `https://<nombre>.grafana.net`.

Plan: **Free**. No pide tarjeta para el uso del proyecto.

---

## 3. Clave del usuario técnico `svc-dashboard` (titular, 2 minutos)

`svc-dashboard` solo puede leer Gold y consultar en el workgroup `costagas-wg`. Su clave solo vive en Grafana.

1. En la consola de AWS: **IAM → Usuarios → svc-dashboard → Credenciales de seguridad → Crear clave de acceso**.
2. Caso de uso: **Aplicación ejecutada fuera de AWS**. Descripción: `grafana-cloud`.
3. Copia el **ID de clave de acceso** y la **clave de acceso secreta**. La secreta se muestra **una sola vez**.
4. Pégalas directamente en Grafana (paso 4). No las guardes en archivos, en el repositorio ni en el chat.
5. Rótala cada 90 días: crea una nueva, actualízala en Grafana y desactiva la anterior.

---

## 4. Conectar Grafana con Athena (titular, 3 minutos)

1. En Grafana: **Connections → Add new connection →** busca **Amazon Athena** → **Install**, si lo pide, y luego **Add new data source**.
2. Completa:
   - **Authentication Provider:** *Access & secret key* → pega las dos claves del paso 3.
   - **Default Region:** `us-east-2`.
   - **Data Source:** `AwsDataCatalog`.
   - **Database:** `costagas_gold`.
   - **Workgroup:** `costagas-wg`.
   - **Output Location:** déjalo vacío (el workgroup ya la define).
3. **Save & test**. Debe decir que la conexión es correcta.

Mientras Gold no tenga tablas, la prueba conecta pero la lista de tablas aparece vacía. Es normal.

---

## 5. Clave de la YouTube Data API v3 (titular, 5 minutos, gratis)

1. Entra a **console.cloud.google.com** con una cuenta de Google del equipo y crea un proyecto llamado `costagas-youtube`.
2. **APIs y servicios → Biblioteca →** busca **YouTube Data API v3** → **Habilitar**.
3. **Credenciales → Crear credenciales → Clave de API**. Luego **Restringir clave**: en «Restricciones de API» elige solo *YouTube Data API v3*.
4. Guarda la clave en AWS (no en el repositorio), desde CloudShell:
   `aws ssm put-parameter --name /costagas/youtube/api_key --type SecureString --value "<pega aquí la clave>"`
   Solo la lee la Lambda `costagas-extractor-youtube`.

Cuota gratuita: 10 000 unidades al día. Las búsquedas del proyecto usan unas 2 000.

---

## 6. Rotación de claves de acceso (Frank y Wilson, 2 minutos cada uno)

Desde la Semana 8, Wilson tiene ingeniería de datos y Frank tiene análisis y modelado. Cada uno, con su propio perfil:

1. `aws iam create-access-key --user-name <tu.usuario> --profile costagas`
2. `aws configure --profile costagas` y pega la clave nueva.
3. `aws sts get-caller-identity --profile costagas` debe mostrar tu usuario.
4. `aws iam delete-access-key --user-name <tu.usuario> --access-key-id <ID de la clave anterior> --profile costagas`

---

## Lista de control

| Paso | Quién | Hecho |
|---|---|---|
| 1. Confirmar la suscripción de SNS | Cada integrante | ☐ Frank ☐ Wilson ☐ Anghelo ☐ Bruno |
| 2. Cuenta de Grafana Cloud | Titular | ☐ |
| 3. Clave de `svc-dashboard` | Titular | ☐ |
| 4. Origen de datos Athena en Grafana | Titular | ☐ |
| 5. Clave de YouTube en Parameter Store | Titular | ☐ |
| 6. Rotación de claves | Frank y Wilson | ☐ Frank ☐ Wilson |
