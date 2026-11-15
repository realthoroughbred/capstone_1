variable "remediation_log_group_name" {
  description = "Existing dedicated CodeBuild CloudWatch log group configured in the external worker project."
  type        = string
  default     = ""
  validation {
    condition     = var.remediation_log_group_name == "" || can(regex("^/aws/codebuild/[A-Za-z0-9_-]+$", var.remediation_log_group_name))
    error_message = "Use the exact dedicated CodeBuild log group, not a wildcard."
  }
}
locals {
  notification_logs = merge(local.result_log_groups,
  var.enable_inspector_response && var.remediation_log_group_name != "" ? { worker = var.remediation_log_group_name } : {})
}
resource "aws_cloudwatch_dashboard" "security" {
  count          = var.enable_observability ? 1 : 0
  dashboard_name = "${var.project}-isms-p-demo"
  dashboard_body = jsonencode({ widgets = concat([
    { type = "text", x = 0, y = 0, width = 24, height = 3, properties = {
      markdown = "# ISMS-P selected technical controls\nSource: ${var.source_commit}. No data means NOT_TESTED. Handler duration is NOT end-to-end recovery time. The one-second target has not been demonstrated."
    } },
    { type = "log", x = 0, y = 3, width = 24, height = 6, properties = {
      region = var.region, title = "EKS audit: rejected requests and changes", view = "table",
      query  = "SOURCE '${aws_cloudwatch_log_group.cluster.name}' | fields @timestamp, verb, user.username, objectRef.namespace, objectRef.resource, responseStatus.code | filter @logStream like /kube-apiserver-audit/ | sort @timestamp desc | limit 50"
    } }
    ], [for index, name in values(local.notification_logs) : {
      type = "log", x = (index % 2) * 12, y = 9 + floor(index / 2) * 6, width = 12, height = 6,
      properties = { region = var.region, title = "Recovery results: ${name}", view = "table",
        query = "SOURCE '${name}' | fields @timestamp, status, resource_id, verification, source_commit, source_event_time, finished_at, handler_duration_ms | filter ispresent(status) | sort @timestamp desc | limit 50"
      }
    }], local.automation_enabled ? [
    { type = "metric", x = 0, y = 27, width = 24, height = 6, properties = {
      region  = var.region, title = "Unprocessed failures (not successful repairs)", stat = "Maximum", period = 60,
      metrics = [["AWS/SQS", "ApproximateNumberOfMessagesVisible", "QueueName", aws_sqs_queue.failures[0].name]]
    } }
  ] : []) })
}
resource "aws_cloudwatch_log_group" "notifications" {
  count             = var.enable_slack_notifications ? 1 : 0
  name              = "/aws/lambda/${var.project}-slack-notify"
  retention_in_days = 365
  kms_key_id        = aws_kms_key.project.arn
}
resource "aws_iam_role" "notifications" {
  count                = var.enable_slack_notifications ? 1 : 0
  name                 = "${var.project}-slack-notify"
  permissions_boundary = var.iam_permissions_boundary_arn
  assume_role_policy = jsonencode({ Version = "2012-10-17", Statement = [
    { Effect = "Allow", Principal = { Service = "lambda.amazonaws.com" }, Action = "sts:AssumeRole" }
  ] })
}
resource "aws_iam_role_policy" "notifications" {
  count = var.enable_slack_notifications ? 1 : 0
  role  = aws_iam_role.notifications[0].id
  policy = jsonencode({ Version = "2012-10-17", Statement = concat([
    { Effect = "Allow", Action = ["logs:CreateLogStream", "logs:PutLogEvents"], Resource = "${aws_cloudwatch_log_group.notifications[0].arn}:*" },
    { Effect = "Allow", Action = ["dynamodb:PutItem", "dynamodb:UpdateItem"], Resource = aws_dynamodb_table.security_ops[0].arn },
    { Effect = "Allow", Action = ["kms:Decrypt", "kms:GenerateDataKey"], Resource = aws_kms_key.project.arn },
    { Effect = "Allow", Action = ["xray:PutTraceSegments", "xray:PutTelemetryRecords"], Resource = "*" },
    { Effect = "Allow", Action = "sqs:SendMessage", Resource = aws_sqs_queue.failures[0].arn }
    ], var.slack_webhook_secret_arn == "" ? [] : [
    { Effect = "Allow", Action = "secretsmanager:GetSecretValue", Resource = var.slack_webhook_secret_arn }
  ]) })
}
resource "aws_lambda_function" "notifications" {
  count                          = var.enable_slack_notifications ? 1 : 0
  function_name                  = "${var.project}-slack-notify"
  role                           = aws_iam_role.notifications[0].arn
  runtime                        = "python3.12"
  handler                        = "slack_notify.lambda_handler"
  filename                       = data.archive_file.automation[0].output_path
  source_code_hash               = data.archive_file.automation[0].output_base64sha256
  timeout                        = 120
  memory_size                    = 128
  reserved_concurrent_executions = 1
  kms_key_arn                    = aws_kms_key.project.arn
  tracing_config { mode = "Active" }
  dead_letter_config { target_arn = aws_sqs_queue.failures[0].arn }
  environment {
    variables = {
      EXPECTED_ACCOUNT_ID = var.aws_account_id
      EXPECTED_REGION     = var.region
      DRY_RUN             = tostring(!var.slack_delivery_enabled)
      SLACK_ENABLED       = tostring(var.slack_delivery_enabled)
      SLACK_SECRET_ARN    = var.slack_webhook_secret_arn
      IDEMPOTENCY_TABLE   = aws_dynamodb_table.security_ops[0].name
      ALLOWED_LOG_GROUPS  = jsonencode(values(local.notification_logs))
    }
  }
  lifecycle {
    precondition {
      condition     = !var.slack_delivery_enabled || can(regex("^arn:aws:secretsmanager:${var.region}:${var.aws_account_id}:secret:.+$", var.slack_webhook_secret_arn))
      error_message = "Live Slack delivery needs an approved webhook Secret in this account/region."
    }
  }
  depends_on = [aws_iam_role_policy.notifications, aws_cloudwatch_log_group.notifications]
}
resource "aws_lambda_permission" "notifications" {
  for_each       = var.enable_slack_notifications ? local.notification_logs : {}
  action         = "lambda:InvokeFunction"
  function_name  = aws_lambda_function.notifications[0].function_name
  principal      = "logs.${var.region}.amazonaws.com"
  source_arn     = "arn:aws:logs:${var.region}:${var.aws_account_id}:log-group:${each.value}:*"
  source_account = var.aws_account_id
}
resource "aws_cloudwatch_log_subscription_filter" "notifications" {
  for_each        = var.enable_slack_notifications ? local.notification_logs : {}
  name            = "${var.project}-security-results"
  log_group_name  = each.value
  filter_pattern  = "{ $.status = * }"
  destination_arn = aws_lambda_function.notifications[0].arn
  depends_on      = [aws_lambda_permission.notifications]
}
resource "aws_lambda_function_event_invoke_config" "notifications" {
  count                        = var.enable_slack_notifications ? 1 : 0
  function_name                = aws_lambda_function.notifications[0].function_name
  maximum_retry_attempts       = 2
  maximum_event_age_in_seconds = 3600
  destination_config {
    on_failure { destination = aws_sqs_queue.failures[0].arn }
  }
}
output "finalization_contract" {
  value = {
    dashboard         = var.enable_observability ? aws_cloudwatch_dashboard.security[0].dashboard_name : null
    sandbox_bucket    = var.enable_resource_healing ? aws_s3_bucket.sandbox[0].id : null
    sandbox_role      = var.enable_resource_healing ? aws_iam_role.sandbox_target[0].name : null
    sandbox_lambda    = var.enable_resource_healing ? aws_lambda_function.sandbox_healer[0].function_name : null
    schedule_rule     = var.enable_resource_healing ? aws_cloudwatch_event_rule.sandbox[0].name : null
    evidence_bucket   = local.automation_enabled ? aws_s3_bucket.evidence[0].id : null
    notification_logs = local.notification_logs
  }
}
