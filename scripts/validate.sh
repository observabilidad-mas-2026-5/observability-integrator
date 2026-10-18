#!/usr/bin/env bash
# Validación de solo lectura. No crea ni modifica recursos.
set -Eeuo pipefail
REGION="${AWS_REGION:-us-east-2}"
VPC_ID="${VPC_ID:-vpc-051c9d747227ae6ab}"
FLOW_LOG_ID="${FLOW_LOG_ID:-fl-0e0e19a230315a65d}"
LOG_GROUP="${LOG_GROUP:-/aws/vpc/observability-integrator/flow-logs}"
METRIC_FILTER="${METRIC_FILTER:-ModuleC-RejectedFlowRecords}"
ALARM_NAME="${ALARM_NAME:-module-c-vpc-rejected-flows-high}"
DASHBOARD_NAME="${DASHBOARD_NAME:-module-c-security-observability}"
command -v aws >/dev/null || { echo "ERROR: AWS CLI no disponible" >&2; exit 1; }
echo "== Identidad =="; aws sts get-caller-identity --region "$REGION" --output table
echo "== VPC Flow Logs =="; aws ec2 describe-flow-logs --region "$REGION" --filter "Name=flow-log-id,Values=$FLOW_LOG_ID" --query 'FlowLogs[].{Id:FlowLogId,VPC:ResourceId,Traffic:TrafficType,Status:FlowLogStatus,Delivery:DeliverLogsStatus,Destination:LogDestination}' --output table
echo "== VPC =="; aws ec2 describe-vpcs --region "$REGION" --vpc-ids "$VPC_ID" --query 'Vpcs[].{VpcId:VpcId,Cidr:CidrBlock,State:State}' --output table
echo "== Log group =="; aws logs describe-log-groups --region "$REGION" --log-group-name-prefix "$LOG_GROUP" --query "logGroups[?logGroupName=='$LOG_GROUP'].{Name:logGroupName,RetentionDays:retentionInDays}" --output table
echo "== Metric filter =="; aws logs describe-metric-filters --region "$REGION" --log-group-name "$LOG_GROUP" --query "metricFilters[?filterName=='$METRIC_FILTER']" --output json
echo "== Alarm =="; aws cloudwatch describe-alarms --region "$REGION" --alarm-names "$ALARM_NAME" --output json
echo "== Dashboard =="; aws cloudwatch get-dashboard --region "$REGION" --dashboard-name "$DASHBOARD_NAME" --output json
echo "Validación de solo lectura finalizada."
