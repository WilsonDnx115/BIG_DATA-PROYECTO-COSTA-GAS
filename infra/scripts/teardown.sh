#!/usr/bin/env bash
# Paso E.3 / 3.7.4: vacía los buckets y borra el stack. IRREVERSIBLE: pide confirmación.
# Uso: SUFIJO=equipo01 ./infra/scripts/teardown.sh            (todo)
#      SUFIJO=equipo01 ./infra/scripts/teardown.sh scaletest  (solo réplicas de 3.7)
set -euo pipefail
: "${SUFIJO:?Defina SUFIJO}"
REGION="${AWS_REGION:-us-east-1}"
LAGO="costagas-trujillo-lake-${SUFIJO}"

if [[ "${1:-}" == "scaletest" ]]; then
  aws s3 rm "s3://${LAGO}/scaletest/" --recursive
  exit 0
fi

read -r -p "Se borrarán s3://${LAGO}, s3://costagas-code-${SUFIJO} y el stack. Escriba el sufijo para confirmar: " ok
[[ "$ok" == "$SUFIJO" ]] || { echo "Cancelado"; exit 1; }

aws s3 rm "s3://${LAGO}" --recursive
aws cloudformation delete-stack --region "$REGION" --stack-name costagas-trujillo
aws cloudformation wait stack-delete-complete --region "$REGION" --stack-name costagas-trujillo
aws s3 rb "s3://costagas-code-${SUFIJO}" --force
echo "Desmontado. Registre el costo final de Cost Explorer en docs/evidencias/costo_real.md"
