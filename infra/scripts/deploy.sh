#!/usr/bin/env bash
# Paso 2.4.3 / WP 0.2: empaqueta src/, lo sube al bucket de código y despliega el stack.
# Costo en reposo: US$ 0.00 (solo S3 por GB y las ejecuciones). Detalle por recurso en stack.yaml.
#
# Lee de .env (no versionado) o del entorno:
#   PROYECTO_SUFIJO   sufijo único del bucket (minúsculas, 3-20 caracteres)
#   COSTAGAS_CORREOS  de 1 a 4 correos separados por coma, para las alertas de AWS Budgets
#   AWS_REGION        us-east-2 (ADR 0011)        AWS_PROFILE  costagas
#
# Uso (Git Bash, desde la raíz del repositorio):  ./infra/scripts/deploy.sh
#      Solo validar, sin crear nada:              ./infra/scripts/deploy.sh --validar
set -euo pipefail
cd "$(dirname "$0")/../.."          # rutas relativas: evita problemas con espacios y con Git Bash en Windows

leer_env() {                        # valor de una clave de .env, sin ejecutar el archivo
  [[ -f .env ]] && grep -E "^$1=" .env | tail -1 | cut -d= -f2- | tr -d '"\r' || true
}
SUFIJO="${SUFIJO:-$(leer_env PROYECTO_SUFIJO)}"
CORREOS="${CORREOS:-$(leer_env COSTAGAS_CORREOS)}"
export AWS_REGION="${AWS_REGION:-$(leer_env AWS_REGION)}"
export AWS_REGION="${AWS_REGION:-us-east-2}"
export AWS_DEFAULT_REGION="$AWS_REGION"
export AWS_PROFILE="${AWS_PROFILE:-costagas}"

: "${SUFIJO:?Defina PROYECTO_SUFIJO en .env (minúsculas, 3-20 caracteres)}"
: "${CORREOS:?Defina COSTAGAS_CORREOS en .env (1 a 4 correos separados por coma)}"
IFS=',' read -r C1 C2 C3 C4 _ <<< "${CORREOS// /},,,,"

STACK="costagas-trujillo"
LAGO="costagas-trujillo-lake-${SUFIJO}"
CODE_BUCKET="costagas-code-${SUFIJO}"
PLANTILLA="infra/cloudformation/stack.yaml"
BUILD=".build"

echo ">> Identidad: $(aws sts get-caller-identity --query Arn --output text) · región ${AWS_REGION}"

echo ">> Validando plantilla"
aws cloudformation validate-template --template-body "file://${PLANTILLA}" > /dev/null
if [[ "${1:-}" == "--validar" ]]; then echo ">> Plantilla válida. No se creó nada."; exit 0; fi

echo ">> Sal de seudonimización en Parameter Store"
if ! aws ssm get-parameter --name /costagas/seudonimo/sal > /dev/null 2>&1; then
  echo "   FALTA el parámetro /costagas/seudonimo/sal. Créelo una sola vez (SecureString, sin costo):"
  echo '   aws ssm put-parameter --name /costagas/seudonimo/sal --type SecureString --value "<texto-secreto>" --profile costagas'
  exit 1
fi

echo ">> Bucket de código ${CODE_BUCKET}"
if ! aws s3api head-bucket --bucket "$CODE_BUCKET" 2>/dev/null; then
  if [[ "$AWS_REGION" == "us-east-1" ]]; then
    aws s3api create-bucket --bucket "$CODE_BUCKET" > /dev/null
  else
    aws s3api create-bucket --bucket "$CODE_BUCKET" \
      --create-bucket-configuration "LocationConstraint=${AWS_REGION}" > /dev/null
  fi
  aws s3api put-public-access-block --bucket "$CODE_BUCKET" --public-access-block-configuration \
    BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
fi

echo ">> Empaquetando src/ + openpyxl (sin datos ni credenciales)"
rm -rf "$BUILD" && mkdir -p "$BUILD/pkg"
python -m pip install --quiet --no-compile --target "$BUILD/pkg" openpyxl
python - <<'PY'
import pathlib
import zipfile

build = pathlib.Path(".build")
with zipfile.ZipFile(build / "costagas_src.zip", "w", zipfile.ZIP_DEFLATED) as z:
    for f in sorted(pathlib.Path("src").rglob("*.py")):
        z.write(f, f.as_posix())
    pkg = build / "pkg"
    for f in sorted(pkg.rglob("*")):
        if f.is_file() and "__pycache__" not in f.parts and not f.parent.name.endswith(".dist-info"):
            z.write(f, f.relative_to(pkg).as_posix())
PY
aws s3 cp "$BUILD/costagas_src.zip" "s3://${CODE_BUCKET}/_code/costagas_src.zip" --sse AES256 --only-show-errors
aws s3 cp src/silver_to_gold/conciliacion.py "s3://${CODE_BUCKET}/_code/glue_conciliacion.py" --sse AES256 --only-show-errors

echo ">> Desplegando stack ${STACK}"
aws cloudformation deploy --stack-name "$STACK" --template-file "$PLANTILLA" \
  --capabilities CAPABILITY_NAMED_IAM --no-fail-on-empty-changeset \
  --parameter-overrides Sufijo="$SUFIJO" Correo1="$C1" Correo2="$C2" Correo3="$C3" Correo4="$C4"

# Si el stack ya existía, actualizar el código de la Lambda
aws lambda update-function-code --function-name costagas-bronze-to-silver \
  --s3-bucket "$CODE_BUCKET" --s3-key _code/costagas_src.zip > /dev/null

echo ">> Creando prefijos de las capas (2.1.2)"
for p in bronze/ silver/ gold/ _manifests/ scaletest/ athena-results/ sparkui/; do
  aws s3api put-object --bucket "$LAGO" --key "$p" --server-side-encryption AES256 > /dev/null
done

rm -rf "$BUILD"
echo ">> Listo. LAKE_URI=s3://${LAGO}"
