#!/usr/bin/env bash
# Paso E.3 / 3.7.4: vacía los buckets y borra el stack. IRREVERSIBLE: pide confirmación.
# Uso: ./infra/scripts/teardown.sh            (todo)
#      ./infra/scripts/teardown.sh scaletest  (solo réplicas de 3.7)
# Lee PROYECTO_SUFIJO y AWS_REGION de .env; usa el perfil costagas.
set -euo pipefail
cd "$(dirname "$0")/../.."

leer_env() { [[ -f .env ]] && grep -E "^$1=" .env | tail -1 | cut -d= -f2- | tr -d '"\r' || true; }
SUFIJO="${SUFIJO:-$(leer_env PROYECTO_SUFIJO)}"
export AWS_REGION="${AWS_REGION:-$(leer_env AWS_REGION)}"
export AWS_REGION="${AWS_REGION:-us-east-2}"
export AWS_DEFAULT_REGION="$AWS_REGION"
export AWS_PROFILE="${AWS_PROFILE:-costagas}"
: "${SUFIJO:?Defina PROYECTO_SUFIJO en .env}"
LAGO="costagas-trujillo-lake-${SUFIJO}"

if [[ "${1:-}" == "scaletest" ]]; then
  aws s3 rm "s3://${LAGO}/scaletest/" --recursive
  exit 0
fi

read -r -p "Se borrarán s3://${LAGO}, s3://costagas-code-${SUFIJO} y el stack. Escriba el sufijo para confirmar: " ok
[[ "$ok" == "$SUFIJO" ]] || { echo "Cancelado"; exit 1; }

aws s3 rm "s3://${LAGO}" --recursive
aws cloudformation delete-stack --stack-name costagas-trujillo
aws cloudformation wait stack-delete-complete --stack-name costagas-trujillo
aws s3 rb "s3://costagas-code-${SUFIJO}" --force
echo "Desmontado. Registre el costo final de Cost Explorer en docs/evidencias/costo_real.md"
