#!/usr/bin/env bash
# Inicia una consulta Logs Insights de solo lectura.
set -Eeuo pipefail
REGION="${AWS_REGION:-us-east-2}"
LOG_GROUP="${LOG_GROUP:-/aws/vpc/observability-integrator/flow-logs}"
LOOKBACK_MINUTES="${LOOKBACK_MINUTES:-60}"
[[ "$LOOKBACK_MINUTES" =~ ^[0-9]+$ ]] && (( LOOKBACK_MINUTES > 0 )) || { echo "LOOKBACK_MINUTES debe ser > 0" >&2; exit 2; }
END_TIME=$(date +%s); START_TIME=$((END_TIME - LOOKBACK_MINUTES * 60))
QUERY='fields @timestamp, @message
| filter @message like /REJECT/
| sort @timestamp desc
| limit 100'
QUERY_ID=$(aws logs start-query --region "$REGION" --log-group-name "$LOG_GROUP" --start-time "$START_TIME" --end-time "$END_TIME" --query-string "$QUERY" --query queryId --output text)
echo "Query ID: $QUERY_ID"
echo "Ver resultados: aws logs get-query-results --region $REGION --query-id $QUERY_ID"
