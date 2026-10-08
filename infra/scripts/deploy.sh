#!/usr/bin/env bash
# Paso 2.4.3: empaqueta src/, lo sube al bucket de código y despliega el stack.
# Costo: el bucket de código pesa < 1 MB (≈ US$ 0.00). Revisar el costo del stack en stack.yaml.
# Uso: SUFIJO=equipo01 CORREOS=a@x.com,b@y.com ./infra/scripts/deploy.sh
set -euo pipefail
: "${SUFIJO:?Defina SUFIJO (minúsculas, 3-20 caracteres)}"
: "${CORREOS:?Defina CORREOS para AWS Budgets}"
REGION="${AWS_REGION:-us-east-1}"
STACK="costagas-trujillo"
CODE_BUCKET="costagas-code-${SUFIJO}"
RAIZ="$(cd "$(dirname "$0")/../.." && pwd)"
TMP="$(mktemp -d)"

echo ">> Validando plantilla"
aws cloudformation validate-template --region "$REGION" \
  --template-body "file://${RAIZ}/infra/cloudformation/stack.yaml" > /dev/null

echo ">> Bucket de código ${CODE_BUCKET}"
if ! aws s3api head-bucket --bucket "$CODE_BUCKET" 2>/dev/null; then
  aws s3api create-bucket --bucket "$CODE_BUCKET" --region "$REGION"
  aws s3api put-public-access-block --bucket "$CODE_BUCKET" --public-access-block-configuration \
    BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
fi

echo ">> Empaquetando src/ (sin datos ni credenciales)"
(cd "$RAIZ" && python -c "
import zipfile, pathlib
with zipfile.ZipFile('${TMP}/costagas_src.zip', 'w', zipfile.ZIP_DEFLATED) as z:
    for f in pathlib.Path('src').rglob('*.py'):
        z.write(f)
")
aws s3 cp "${TMP}/costagas_src.zip" "s3://${CODE_BUCKET}/_code/costagas_src.zip" --sse AES256
aws s3 cp "${RAIZ}/src/silver_to_gold/conciliacion.py" "s3://${CODE_BUCKET}/_code/glue_conciliacion.py" --sse AES256

echo ">> Desplegando stack ${STACK}"
aws cloudformation deploy --region "$REGION" --stack-name "$STACK" \
  --template-file "${RAIZ}/infra/cloudformation/stack.yaml" \
  --capabilities CAPABILITY_IAM \
  --parameter-overrides Sufijo="$SUFIJO" CorreosAlerta="$CORREOS"

# Si el stack ya existía, actualizar el código de la Lambda
aws lambda update-function-code --region "$REGION" --function-name costagas-bronze-to-silver \
  --s3-bucket "$CODE_BUCKET" --s3-key _code/costagas_src.zip > /dev/null

echo ">> Creando prefijos de las capas (2.1.2)"
LAGO="costagas-trujillo-lake-${SUFIJO}"
for p in bronze/ silver/ gold/ _manifests/ scaletest/ athena-results/; do
  aws s3api put-object --bucket "$LAGO" --key "$p" --server-side-encryption AES256 > /dev/null
done

echo ">> Listo. LAKE_URI=s3://${LAGO}"
rm -rf "$TMP"
