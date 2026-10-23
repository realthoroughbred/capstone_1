resource "aws_s3_bucket" "evidence" {
  #checkov:skip=CKV_AWS_144:Dedicated regional lab evidence uses versioning and retention; cross-region replication adds unapproved cost.
  #checkov:skip=CKV_AWS_18:No sensitive workload data is stored; bucket delivery and Lambda execution are audited in CloudWatch. Add an organization access-log sink before production.
  #checkov:skip=CKV2_AWS_62:Evidence is consumed explicitly by report/export commands; no event consumer is required.
  count         = local.automation_enabled ? 1 : 0
  bucket        = "${var.project}-${var.aws_account_id}-${var.region}-evidence"
  force_destroy = false
}
resource "aws_s3_bucket_public_access_block" "evidence" {
  count                   = local.automation_enabled ? 1 : 0
  bucket                  = aws_s3_bucket.evidence[0].id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}
resource "aws_s3_bucket_ownership_controls" "evidence" {
  count  = local.automation_enabled ? 1 : 0
  bucket = aws_s3_bucket.evidence[0].id
  rule { object_ownership = "BucketOwnerEnforced" }
}
resource "aws_s3_bucket_versioning" "evidence" {
  count  = local.automation_enabled ? 1 : 0
  bucket = aws_s3_bucket.evidence[0].id
  versioning_configuration { status = "Enabled" }
}
resource "aws_s3_bucket_server_side_encryption_configuration" "evidence" {
  count  = local.automation_enabled ? 1 : 0
  bucket = aws_s3_bucket.evidence[0].id
  rule {
    bucket_key_enabled = true
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = aws_kms_key.project.arn
    }
  }
}
resource "aws_s3_bucket_lifecycle_configuration" "evidence" {
  count  = local.automation_enabled ? 1 : 0
  bucket = aws_s3_bucket.evidence[0].id
  rule {
    id     = "retain-evidence-one-year"
    status = "Enabled"
    filter {}
    expiration { days = 365 }
    noncurrent_version_expiration { noncurrent_days = 365 }
    abort_incomplete_multipart_upload { days_after_initiation = 7 }
  }
}
resource "aws_s3_bucket_policy" "evidence" {
  count  = local.automation_enabled ? 1 : 0
  bucket = aws_s3_bucket.evidence[0].id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      { Sid = "DenyInsecureTransport", Effect = "Deny", Principal = "*", Action = "s3:*", Resource = [aws_s3_bucket.evidence[0].arn, "${aws_s3_bucket.evidence[0].arn}/*"], Condition = { Bool = { "aws:SecureTransport" = "false" } } },
      { Sid = "ConfigCheck", Effect = "Allow", Principal = { Service = "config.amazonaws.com" }, Action = ["s3:GetBucketAcl", "s3:ListBucket"], Resource = aws_s3_bucket.evidence[0].arn, Condition = { StringEquals = { "AWS:SourceAccount" = var.aws_account_id } } },
      { Sid = "ConfigWrite", Effect = "Allow", Principal = { Service = "config.amazonaws.com" }, Action = "s3:PutObject", Resource = "${aws_s3_bucket.evidence[0].arn}/config/AWSLogs/${var.aws_account_id}/Config/*", Condition = { StringEquals = { "AWS:SourceAccount" = var.aws_account_id, "s3:x-amz-acl" = "bucket-owner-full-control" } } }
    ]
  })
}

resource "aws_iam_role" "config" {
  permissions_boundary = var.iam_permissions_boundary_arn
  count                = var.enable_self_healing && var.create_config_recorder ? 1 : 0
  name                 = "${var.project}-config-recorder"
  assume_role_policy = jsonencode({
    Version   = "2012-10-17"
    Statement = [{ Effect = "Allow", Action = "sts:AssumeRole", Principal = { Service = "config.amazonaws.com" }, Condition = { StringEquals = { "AWS:SourceAccount" = var.aws_account_id } } }]
  })
}
resource "aws_iam_role_policy" "config" {
  #checkov:skip=CKV_AWS_355:Config uses EC2 Describe APIs for resource relationships and PutEvaluations for rule results. These APIs use wildcard resources; region is constrained and recording remains SecurityGroup-only. No EC2 write is granted.
  count = var.enable_self_healing && var.create_config_recorder ? 1 : 0
  role  = aws_iam_role.config[0].id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      { Effect = "Allow", Action = ["ec2:Describe*"], Resource = "*", Condition = { StringEquals = { "aws:RequestedRegion" = var.region } } },
      { Effect = "Allow", Action = ["config:PutEvaluations"], Resource = "*", Condition = { StringEquals = { "aws:RequestedRegion" = var.region } } },
      { Effect = "Allow", Action = ["s3:GetBucketAcl", "s3:ListBucket"], Resource = aws_s3_bucket.evidence[0].arn },
      { Effect = "Allow", Action = ["s3:PutObject"], Resource = "${aws_s3_bucket.evidence[0].arn}/config/AWSLogs/${var.aws_account_id}/Config/*", Condition = { StringEquals = { "s3:x-amz-acl" = "bucket-owner-full-control" } } },
      { Effect = "Allow", Action = ["kms:GenerateDataKey", "kms:Decrypt"], Resource = aws_kms_key.project.arn }
    ]
  })
}
resource "aws_config_configuration_recorder" "demo" {
  #checkov:skip=CKV2_AWS_48:Dedicated lab recorder intentionally records SecurityGroup only to bound evaluation scope and charges; existing organization recorders are preserved.
  count    = var.enable_self_healing && var.create_config_recorder ? 1 : 0
  name     = "${var.project}-security-groups"
  role_arn = aws_iam_role.config[0].arn
  recording_group {
    all_supported                 = false
    include_global_resource_types = false
    resource_types                = ["AWS::EC2::SecurityGroup"]
  }
  depends_on = [aws_iam_role_policy.config]
}
resource "aws_config_delivery_channel" "demo" {
  count          = var.enable_self_healing && var.create_config_recorder ? 1 : 0
  name           = "${var.project}-security-groups"
  s3_bucket_name = aws_s3_bucket.evidence[0].id
  s3_key_prefix  = "config"
  s3_kms_key_arn = aws_kms_key.project.arn
  depends_on     = [aws_config_configuration_recorder.demo, aws_s3_bucket_policy.evidence]
}
resource "aws_config_configuration_recorder_status" "demo" {
  #checkov:skip=CKV2_AWS_45:Recorder is enabled continuously for SecurityGroup only, the explicit experiment scope; this is not an account-wide compliance baseline.
  count      = var.enable_self_healing && var.create_config_recorder ? 1 : 0
  name       = aws_config_configuration_recorder.demo[0].name
  is_enabled = true
  depends_on = [aws_config_delivery_channel.demo]
}
resource "aws_config_config_rule" "restricted_ssh" {
  count = var.enable_self_healing ? 1 : 0
  name  = "${var.project}-restricted-ssh"
  source {
    owner             = "AWS"
    source_identifier = "INCOMING_SSH_DISABLED"
  }
  scope {
    compliance_resource_types = ["AWS::EC2::SecurityGroup"]
    compliance_resource_id    = aws_security_group.healing_demo.id
  }
  lifecycle {
    precondition {
      condition     = var.create_config_recorder || var.existing_config_recorder_name != ""
      error_message = "Inspect existing regional Config recorder first. Name the running recorder or explicitly opt in to creating one in a dedicated account."
    }
  }
  depends_on = [aws_config_configuration_recorder_status.demo]
}

data "archive_file" "automation" {
  count       = local.automation_enabled ? 1 : 0
  type        = "zip"
  output_path = "${path.module}/automation.zip"
  dynamic "source" {
    for_each = toset(["common.py", "sg_healing.py", "inspector_response.py"])
    content {
      filename = source.value
      content  = file("${path.module}/../automation/${source.value}")
    }
  }
}
resource "aws_sqs_queue" "failures" {
  #checkov:skip=CKV_AWS_27:SQS-managed SSE encrypts non-secret failure event envelopes; no customer-managed queue key is needed for this lab.
  count                     = local.automation_enabled ? 1 : 0
  name                      = "${var.project}-automation-failures"
  message_retention_seconds = 1209600
  sqs_managed_sse_enabled   = true
}
resource "aws_cloudwatch_metric_alarm" "failures" {
  count               = local.automation_enabled ? 1 : 0
  alarm_name          = "${var.project}-automation-failure-queue"
  alarm_description   = "Inspect SQS failure events and CloudWatch logs; automatic retry exhausted or CodeBuild failed."
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "ApproximateNumberOfMessagesVisible"
  namespace           = "AWS/SQS"
  period              = 60
  statistic           = "Maximum"
  threshold           = 0
  treat_missing_data  = "notBreaching"
  dimensions          = { QueueName = aws_sqs_queue.failures[0].name }
  alarm_actions       = var.notification_topic_arn == "" ? [] : [var.notification_topic_arn]
}
resource "aws_cloudwatch_log_group" "healing" {
  count             = var.enable_self_healing ? 1 : 0
  name              = "/aws/lambda/${var.project}-sg-healing"
  retention_in_days = 365
  kms_key_id        = aws_kms_key.project.arn
}
resource "aws_iam_role" "healing" {
  permissions_boundary = var.iam_permissions_boundary_arn
  count                = var.enable_self_healing ? 1 : 0
  name                 = "${var.project}-sg-healing"
  assume_role_policy = jsonencode({
    Version   = "2012-10-17"
    Statement = [{ Effect = "Allow", Action = "sts:AssumeRole", Principal = { Service = "lambda.amazonaws.com" } }]
  })
}
resource "aws_iam_role_policy" "healing" {
  #checkov:skip=CKV_AWS_355:EC2 Describe and STS caller identity do not support resource-level IAM. Mutation is restricted to one tagged unattached demo SG.
  count = var.enable_self_healing ? 1 : 0
  role  = aws_iam_role.healing[0].id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      { Effect = "Allow", Action = ["sts:GetCallerIdentity", "ec2:DescribeSecurityGroups", "ec2:DescribeSecurityGroupRules", "ec2:DescribeNetworkInterfaces"], Resource = "*" },
      { Effect = "Allow", Action = ["ec2:RevokeSecurityGroupIngress"], Resource = aws_security_group.healing_demo.arn, Condition = { StringEquals = { "ec2:ResourceTag/Project" = var.project, "ec2:ResourceTag/DemoOnly" = "true" } } },
      { Effect = "Allow", Action = ["logs:CreateLogStream", "logs:PutLogEvents"], Resource = "${aws_cloudwatch_log_group.healing[0].arn}:*" },
      { Effect = "Allow", Action = ["xray:PutTraceSegments", "xray:PutTelemetryRecords"], Resource = "*" },
      { Effect = "Allow", Action = ["s3:PutObject"], Resource = "${aws_s3_bucket.evidence[0].arn}/sg-healing/*" },
      { Effect = "Allow", Action = ["kms:GenerateDataKey", "kms:Decrypt"], Resource = aws_kms_key.project.arn, Condition = { StringEquals = { "kms:ViaService" = "s3.${var.region}.amazonaws.com" } } },
      { Effect = "Allow", Action = ["kms:Decrypt"], Resource = aws_kms_key.project.arn },
      { Effect = "Allow", Action = ["sqs:SendMessage"], Resource = aws_sqs_queue.failures[0].arn }
    ]
  })
}
resource "aws_lambda_function" "healing" {
  #checkov:skip=CKV_AWS_117:API-only Lambda needs no private network access; VPC attachment would require NAT or billed endpoints.
  #checkov:skip=CKV_AWS_272:Lambda code signing requires separately approved AWS Signer infrastructure; archive source hash tracks reviewed code.
  count                          = var.enable_self_healing ? 1 : 0
  function_name                  = "${var.project}-sg-healing"
  role                           = aws_iam_role.healing[0].arn
  runtime                        = "python3.12"
  handler                        = "sg_healing.lambda_handler"
  filename                       = data.archive_file.automation[0].output_path
  source_code_hash               = data.archive_file.automation[0].output_base64sha256
  timeout                        = 60
  memory_size                    = 128
  reserved_concurrent_executions = var.healing_use_unreserved_concurrency_for_demo ? -1 : 1
  kms_key_arn                    = aws_kms_key.project.arn
  tracing_config { mode = "Active" }
  dead_letter_config { target_arn = aws_sqs_queue.failures[0].arn }
  environment {
    variables = {
      DRY_RUN                    = tostring(var.healing_dry_run)
      EXPECTED_ACCOUNT_ID        = var.aws_account_id
      EXPECTED_REGION            = var.region
      PROJECT                    = var.project
      ALLOWED_SECURITY_GROUP_IDS = aws_security_group.healing_demo.id
      CONFIG_RULE_NAME           = aws_config_config_rule.restricted_ssh[0].name
      EVIDENCE_BUCKET            = aws_s3_bucket.evidence[0].id
    }
  }
  depends_on = [aws_iam_role_policy.healing, aws_cloudwatch_log_group.healing]
}
resource "aws_lambda_function_event_invoke_config" "healing" {
  count                        = var.enable_self_healing ? 1 : 0
  function_name                = aws_lambda_function.healing[0].function_name
  maximum_event_age_in_seconds = 3600
  maximum_retry_attempts       = 2
  destination_config {
    on_failure { destination = aws_sqs_queue.failures[0].arn }
  }
}
resource "aws_cloudwatch_event_rule" "restricted_ssh" {
  count = var.enable_self_healing ? 1 : 0
  name  = "${var.project}-restricted-ssh"
  event_pattern = jsonencode({
    source = ["aws.config"], "detail-type" = ["Config Rules Compliance Change"], account = [var.aws_account_id], region = [var.region]
    detail = { configRuleName = [aws_config_config_rule.restricted_ssh[0].name], resourceId = [aws_security_group.healing_demo.id], resourceType = ["AWS::EC2::SecurityGroup"], newEvaluationResult = { complianceType = ["NON_COMPLIANT"] } }
  })
}
resource "aws_cloudwatch_event_target" "healing" {
  count = var.enable_self_healing ? 1 : 0
  rule  = aws_cloudwatch_event_rule.restricted_ssh[0].name
  arn   = aws_lambda_function.healing[0].arn
  retry_policy {
    maximum_event_age_in_seconds = 3600
    maximum_retry_attempts       = 2
  }
  dead_letter_config { arn = aws_sqs_queue.failures[0].arn }
}
resource "aws_lambda_permission" "healing" {
  count          = var.enable_self_healing ? 1 : 0
  statement_id   = "AllowRestrictedSSHEvent"
  action         = "lambda:InvokeFunction"
  function_name  = aws_lambda_function.healing[0].function_name
  principal      = "events.amazonaws.com"
  source_arn     = aws_cloudwatch_event_rule.restricted_ssh[0].arn
  source_account = var.aws_account_id
}
