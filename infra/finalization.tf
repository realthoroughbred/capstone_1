# Optional final-lab features. No scheduled writes or messages are enabled by default.
variable "enable_resource_healing" {
  type    = bool
  default = false
}
variable "resource_healing_dry_run" {
  type    = bool
  default = true
}
variable "enable_observability" {
  type    = bool
  default = false
}
variable "enable_slack_notifications" {
  type    = bool
  default = false
}
variable "slack_delivery_enabled" {
  type    = bool
  default = false
}
variable "slack_webhook_secret_arn" {
  description = "Existing approved webhook Secret ARN; never put the webhook value in Terraform."
  type        = string
  default     = ""
}
variable "source_commit" {
  type    = string
  default = "UNAVAILABLE"
  validation {
    condition     = var.source_commit == "UNAVAILABLE" || can(regex("^[0-9a-f]{40}$", var.source_commit))
    error_message = "Use the reviewed full source commit."
  }
}
locals {
  security_ops_enabled = var.enable_resource_healing || var.enable_slack_notifications
  result_log_groups = merge(
    var.enable_self_healing ? { sg = aws_cloudwatch_log_group.healing[0].name } : {},
    var.enable_inspector_response ? { inspector = aws_cloudwatch_log_group.inspector[0].name } : {},
    var.enable_resource_healing ? { sandbox = aws_cloudwatch_log_group.sandbox[0].name } : {}
  )
}
resource "aws_dynamodb_table" "security_ops" {
  count        = local.security_ops_enabled ? 1 : 0
  name         = "${var.project}-security-ops-receipts"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "id"
  attribute {
    name = "id"
    type = "S"
  }
  ttl {
    attribute_name = "expires_at"
    enabled        = true
  }
  server_side_encryption {
    enabled     = true
    kms_key_arn = aws_kms_key.project.arn
  }
  point_in_time_recovery { enabled = true }
}
resource "aws_s3_bucket" "sandbox" {
  count         = var.enable_resource_healing ? 1 : 0
  bucket        = "${var.project}-${var.aws_account_id}-${var.region}-healing-sandbox"
  force_destroy = false
  tags          = { Project = var.project, DemoOnly = "true" }
}
resource "aws_s3_bucket_public_access_block" "sandbox" {
  count                   = var.enable_resource_healing ? 1 : 0
  bucket                  = aws_s3_bucket.sandbox[0].id
  block_public_acls       = true
  ignore_public_acls      = true
  block_public_policy     = true
  restrict_public_buckets = true
}
resource "aws_s3_bucket_ownership_controls" "sandbox" {
  count  = var.enable_resource_healing ? 1 : 0
  bucket = aws_s3_bucket.sandbox[0].id
  rule { object_ownership = "BucketOwnerEnforced" }
}
resource "aws_s3_bucket_versioning" "sandbox" {
  count  = var.enable_resource_healing ? 1 : 0
  bucket = aws_s3_bucket.sandbox[0].id
  versioning_configuration { status = "Enabled" }
}
resource "aws_s3_bucket_server_side_encryption_configuration" "sandbox" {
  count  = var.enable_resource_healing ? 1 : 0
  bucket = aws_s3_bucket.sandbox[0].id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = aws_kms_key.project.arn
    }
  }
}
resource "aws_s3_bucket_lifecycle_configuration" "sandbox" {
  count  = var.enable_resource_healing ? 1 : 0
  bucket = aws_s3_bucket.sandbox[0].id
  rule {
    id     = "empty-test-bucket-safety"
    status = "Enabled"
    filter {}
    abort_incomplete_multipart_upload { days_after_initiation = 1 }
    expiration { days = 7 }
    noncurrent_version_expiration { noncurrent_days = 7 }
  }
}
resource "aws_s3_bucket_policy" "sandbox" {
  count  = var.enable_resource_healing ? 1 : 0
  bucket = aws_s3_bucket.sandbox[0].id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{ Effect = "Deny", Principal = "*", Action = "s3:*", Resource = [aws_s3_bucket.sandbox[0].arn, "${aws_s3_bucket.sandbox[0].arn}/*"],
    Condition = { Bool = { "aws:SecureTransport" = "false" } } }]
  })
}
resource "aws_iam_role" "sandbox_target" {
  count                = var.enable_resource_healing ? 1 : 0
  name                 = "${var.project}-healing-sandbox"
  path                 = "/${var.project}-sandbox/"
  permissions_boundary = var.iam_permissions_boundary_arn
  tags                 = { Project = var.project, DemoOnly = "true" }
  assume_role_policy = jsonencode({ Version = "2012-10-17", Statement = [
    { Effect = "Deny", Principal = { AWS = local.account_root }, Action = "sts:AssumeRole" }
  ] })
}
resource "aws_iam_role_policy" "sandbox_target" {
  count = var.enable_resource_healing ? 1 : 0
  role  = aws_iam_role.sandbox_target[0].id
  name  = "sandbox-deny-all"
  policy = jsonencode({ Version = "2012-10-17", Statement = [
    { Effect = "Deny", Action = "*", Resource = "*" }
  ] })
}
resource "aws_cloudwatch_log_group" "sandbox" {
  count             = var.enable_resource_healing ? 1 : 0
  name              = "/aws/lambda/${var.project}-resource-healing"
  retention_in_days = 365
  kms_key_id        = aws_kms_key.project.arn
}
resource "aws_iam_role" "sandbox_healer" {
  count                = var.enable_resource_healing ? 1 : 0
  name                 = "${var.project}-resource-healing"
  permissions_boundary = var.iam_permissions_boundary_arn
  assume_role_policy = jsonencode({ Version = "2012-10-17", Statement = [
    { Effect = "Allow", Principal = { Service = "lambda.amazonaws.com" }, Action = "sts:AssumeRole" }
  ] })
}
resource "aws_iam_role_policy" "sandbox_healer" {
  count = var.enable_resource_healing ? 1 : 0
  role  = aws_iam_role.sandbox_healer[0].id
  policy = jsonencode({ Version = "2012-10-17", Statement = [
    { Effect = "Allow", Action = "sts:GetCallerIdentity", Resource = "*" },
    { Effect = "Allow", Action = ["s3:GetBucketTagging", "s3:ListBucketVersions", "s3:GetBucketPublicAccessBlock", "s3:PutBucketPublicAccessBlock"], Resource = aws_s3_bucket.sandbox[0].arn },
    { Effect = "Allow", Action = ["iam:GetRole", "iam:GetRolePolicy", "iam:ListRolePolicies", "iam:ListAttachedRolePolicies", "iam:PutRolePolicy"], Resource = aws_iam_role.sandbox_target[0].arn },
    { Effect = "Allow", Action = ["dynamodb:PutItem", "dynamodb:UpdateItem"], Resource = aws_dynamodb_table.security_ops[0].arn },
    { Effect = "Allow", Action = "s3:PutObject", Resource = "${aws_s3_bucket.evidence[0].arn}/resource-healing/*" },
    { Effect = "Allow", Action = ["kms:GenerateDataKey", "kms:Decrypt"], Resource = aws_kms_key.project.arn },
    { Effect = "Allow", Action = ["logs:CreateLogStream", "logs:PutLogEvents"], Resource = "${aws_cloudwatch_log_group.sandbox[0].arn}:*" },
    { Effect = "Allow", Action = ["xray:PutTraceSegments", "xray:PutTelemetryRecords"], Resource = "*" },
    { Effect = "Allow", Action = "sqs:SendMessage", Resource = aws_sqs_queue.failures[0].arn }
  ] })
}
resource "aws_lambda_function" "sandbox_healer" {
  count                          = var.enable_resource_healing ? 1 : 0
  function_name                  = "${var.project}-resource-healing"
  role                           = aws_iam_role.sandbox_healer[0].arn
  runtime                        = "python3.12"
  handler                        = "resource_healing.lambda_handler"
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
      PROJECT             = var.project
      DRY_RUN             = tostring(var.resource_healing_dry_run)
      SOURCE_COMMIT       = var.source_commit
      SANDBOX_BUCKET      = aws_s3_bucket.sandbox[0].id
      SANDBOX_ROLE        = aws_iam_role.sandbox_target[0].name
      SCHEDULE_RULE_ARN   = aws_cloudwatch_event_rule.sandbox[0].arn
      IDEMPOTENCY_TABLE   = aws_dynamodb_table.security_ops[0].name
      EVIDENCE_BUCKET     = aws_s3_bucket.evidence[0].id
    }
  }
  depends_on = [aws_iam_role_policy.sandbox_healer, aws_cloudwatch_log_group.sandbox]
}
resource "aws_cloudwatch_event_rule" "sandbox" {
  count               = var.enable_resource_healing ? 1 : 0
  name                = "${var.project}-sandbox-drift-scan"
  schedule_expression = "rate(5 minutes)"
}
resource "aws_cloudwatch_event_target" "sandbox" {
  count = var.enable_resource_healing ? 1 : 0
  rule  = aws_cloudwatch_event_rule.sandbox[0].name
  arn   = aws_lambda_function.sandbox_healer[0].arn
  retry_policy {
    maximum_event_age_in_seconds = 3600
    maximum_retry_attempts       = 2
  }
  dead_letter_config { arn = aws_sqs_queue.failures[0].arn }
}
resource "aws_lambda_permission" "sandbox" {
  count          = var.enable_resource_healing ? 1 : 0
  action         = "lambda:InvokeFunction"
  function_name  = aws_lambda_function.sandbox_healer[0].function_name
  principal      = "events.amazonaws.com"
  source_arn     = aws_cloudwatch_event_rule.sandbox[0].arn
  source_account = var.aws_account_id
}
resource "aws_lambda_function_event_invoke_config" "sandbox" {
  count                        = var.enable_resource_healing ? 1 : 0
  function_name                = aws_lambda_function.sandbox_healer[0].function_name
  maximum_retry_attempts       = 2
  maximum_event_age_in_seconds = 3600
  destination_config {
    on_failure { destination = aws_sqs_queue.failures[0].arn }
  }
}
