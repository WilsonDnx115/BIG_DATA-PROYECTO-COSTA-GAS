# Pruebas de mínimo privilegio · usuario `frank.trelles`

- **Fecha:** 2026-10-10
- **Ejecutó:** Frank Trelles, desde su terminal, con el perfil `costagas` de la AWS CLI
- **Usuario de IAM:** `frank.trelles` (rol del equipo: ingeniería de datos, Semanas 2–7)
- **Políticas adjuntas:** `costagas-base` + `costagas-ingenieria-datos`
- **Región del proyecto:** `us-east-2` (Ohio), asignada por el plan gratuito de AWS
- **Sustenta:** informe, sección 3.8 (Tabla 3.12) · Plan de Corrección, hallazgo C7 y WP 1.6

Ninguna salida de este archivo contiene credenciales. El número de cuenta y el `UserId` son identificadores, no secretos.

## Resumen

| # | Prueba | Resultado esperado | Resultado obtenido |
|---|---|---|---|
| 1 | Identidad de la sesión | Usuario `frank.trelles` | Correcto |
| 2 | Crear un usuario de IAM | Denegado por `costagas-base` | Correcto: `explicit deny` |
| 3 | Operar fuera de `us-east-2` | Denegado por `costagas-base` | Correcto: `explicit deny` |
| 4 | Operar dentro de `us-east-2` | Permitido | Correcto: lista vacía |
| 5 | Listar buckets de S3 | Permitido | Correcto: lista vacía |

## 1. Identidad de la sesión

La terminal usa el usuario de la persona, no la cuenta del titular ni un usuario compartido.

```text
> aws sts get-caller-identity --profile costagas
{
    "UserId": "AIDA3ERFKUYNGFYUBCPSZ",
    "Account": "765656213018",
    "Arn": "arn:aws:iam::765656213018:user/frank.trelles"
}
```

## 2. Solo el titular gestiona identidades

Aunque el perfil de ingeniería puede crear roles de servicio `costagas-*`, no puede crear usuarios. La denegación explícita de `costagas-base` prevalece sobre cualquier permiso.

```text
> aws iam create-user --user-name prueba --profile costagas

aws: [ERROR]: An error occurred (AccessDenied) when calling the CreateUser operation: User: arn:aws:iam::765656213018:user/frank.trelles is not authorized to perform: iam:CreateUser on resource: arn:aws:iam::765656213018:user/prueba with an explicit deny in an identity-based policy: arn:aws:iam::765656213018:policy/costagas-base
```

## 3. Región única

Toda acción fuera de `us-east-2` se deniega, salvo los servicios globales (IAM, STS, Budgets, Cost Explorer).

```text
> aws lambda list-functions --region us-east-1 --profile costagas

aws: [ERROR]: An error occurred (AccessDeniedException) when calling the ListFunctions operation: User: arn:aws:iam::765656213018:user/frank.trelles is not authorized to perform: lambda:ListFunctions on resource: * with an explicit deny in an identity-based policy: arn:aws:iam::765656213018:policy/costagas-base
```

## 4. Dentro de la región del proyecto sí puede operar

La misma consulta en `us-east-2` funciona. La lista está vacía porque el lago aún no se ha desplegado.

```text
> aws lambda list-functions --region us-east-2 --profile costagas
{
    "Functions": []
}
```

## 5. Listado de buckets

```text
> aws s3api list-buckets --profile costagas --query "Buckets[].Name"
[]
```

## Pendiente

- Repetir las pruebas 1 a 3 con `wilson.mirano`, `anghelo.alcantara` y `bruno.ordonez`.
- Después del despliegue: con los perfiles de analítica y gobierno, listar `bronze/` debe devolver `AccessDenied`, y escribir en `gold/` también.
- Capturas de la consola: lista de políticas `costagas-*` y lista de usuarios con MFA activo.
