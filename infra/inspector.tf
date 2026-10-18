locals {
  remediation_project_arn = "arn:aws:codebuild:${var.region}:${var.aws_account_id}:project/${var.remediation_codebuild_project_name}"
  approval_parameter_arn  = "arn:aws:ssm:${var.region}:${var.aws_account_id}:parameter${var.approved_image_parameter_name}"
  remediation_environment = {
    DRY_RUN                  = tostring(var.inspector_dry_run)
    EXPECTED_ACCOUNT_ID      = var.aws_account_id
    EXPECTED_REGION          = var.region
    PROJECT                  = var.project
    ECR_REPOSITORY           = aws_ecr_repository.test.name
    APPROVED_IMAGE_PARAMETER = var.approved_image_parameter_name
    CLUSTER_NAME             = aws_eks_cluster.demo.name
    DEPLOY_NAMESPACE         = "demo"
    DEPLOYMENT               = "server"
    DEPLOY_CONTAINER         = "test"
    SIGNING_IDENTITY         = "https://github.com/${var.github_repository}/.github/workflows/${var.signing_workflow}@refs/heads/main"
    SIGNING_ISSUER           = "https://token.actions.githubusercontent.com"
  }
}

# Registry scanning is account/region-wide. Opt in only after checking existing settings.
resource "aws_ecr_registry_scanning_configuration" "enhanced" {
  count     = var.enable_inspector_response ? 1 : 0
  scan_type = "ENHANCED"
  rule {
    scan_frequency = "CONTINUOUS_SCAN"
    repository_filter {
      filter      = aws_ecr_repository.test.name
      filter_type = "WILDCARD"
    }
  }
}
resource "aws_dynamodb_table" "remediation" {
  count        = var.enable_inspector_response ? 1 : 0
  name         = "${var.project}-image-remediation"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "id"
  attribute {
    name = "id"
    type = "S"
  }
  point_in_time_recovery { enabled = true }
  server_side_encryption {
    enabled     = true
    kms_key_arn = aws_kms_key.project.arn
  }
  # No TTL: event replay must not silently become eligible to mutate again.
}
resource "aws_cloudwatch_log_group" "inspector" {
  count             = var.enable_inspector_response ? 1 : 0
  name              = "/aws/lambda/${var.project}-inspector-response"
  retention_in_days = 365
  kms_key_id        = aws_kms_key.project.arn
}
resource "aws_cloudwatch_log_group" "remediation" {
  count             = var.enable_inspector_response ? 1 : 0
  name              = "/aws/codebuild/${var.project}-image-remediation"
  retention_in_days = 365
  kms_key_id        = aws_kms_key.project.arn
}
resource "aws_iam_role" "remediation" {
  permissions_boundary = var.iam_permissions_boundary_arn
  count = var.enable_inspector_response ? 1 : 0
  name  = "${var.project}-image-remediation"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{ Effect = "Allow", Action = "sts:AssumeRole", Principal = { Service = "codebuild.amazonaws.com" },
      Condition = { StringEquals = { "aws:SourceAccount" = var.aws_account_id }, ArnEquals = { "aws:SourceArn" = "arn:aws:codebuild:${var.region}:${var.aws_account_id}:project/${var.remediation_codebuild_project_name}" } }
    }]
  })
}
resource "aws_iam_role_policy" "remediation" {
  #checkov:skip=CKV_AWS_355:GetAuthorizationToken and GetCallerIdentity require wildcard resources; cluster, repository, approval and state writes are narrowly scoped.
  count = var.enable_inspector_response ? 1 : 0
  role  = aws_iam_role.remediation[0].id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      { Effect = "Allow", Action = ["ecr:GetAuthorizationToken", "sts:GetCallerIdentity"], Resource = "*" },
      { Effect = "Allow", Action = ["ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer", "ecr:BatchCheckLayerAvailability", "ecr:DescribeImages", "ecr:DescribeImageScanFindings"], Resource = aws_ecr_repository.test.arn },
      { Effect = "Allow", Action = ["eks:DescribeCluster"], Resource = aws_eks_cluster.demo.arn },
      { Effect = "Allow", Action = ["ssm:GetParameter"], Resource = local.approval_parameter_arn },
      { Effect = "Allow", Action = ["dynamodb:GetItem", "dynamodb:UpdateItem"], Resource = aws_dynamodb_table.remediation[0].arn },
      { Effect = "Allow", Action = ["s3:PutObject"], Resource = "${aws_s3_bucket.evidence[0].arn}/inspector/*" },
      { Effect = "Allow", Action = ["s3:GetBucketAcl", "s3:GetBucketLocation"], Resource = aws_s3_bucket.evidence[0].arn },
      { Effect = "Allow", Action = ["kms:GenerateDataKey", "kms:Decrypt", "kms:DescribeKey"], Resource = aws_kms_key.project.arn },
      { Effect = "Allow", Action = ["logs:CreateLogStream", "logs:PutLogEvents"], Resource = "${aws_cloudwatch_log_group.remediation[0].arn}:*" }
    ]
  })
}
resource "aws_eks_access_entry" "remediation" {
  count             = var.enable_inspector_response ? 1 : 0
  cluster_name      = aws_eks_cluster.demo.name
  principal_arn     = aws_iam_role.remediation[0].arn
  kubernetes_groups = ["team4:image-remediator"]
  type              = "STANDARD"
}

resource "aws_iam_role" "inspector" {
  permissions_boundary = var.iam_permissions_boundary_arn
  count = var.enable_inspector_response ? 1 : 0
  name  = "${var.project}-inspector-response"
  assume_role_policy = jsonencode({
    Version   = "2012-10-17"
    Statement = [{ Effect = "Allow", Action = "sts:AssumeRole", Principal = { Service = "lambda.amazonaws.com" } }]
  })
}
resource "aws_iam_role_policy" "inspector" {
  #checkov:skip=CKV_AWS_355:Inspector ListFindings and STS GetCallerIdentity require wildcard resources; code verifies account, repository, severity and finding digest.
  count = var.enable_inspector_response ? 1 : 0
  role  = aws_iam_role.inspector[0].id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      { Effect = "Allow", Action = ["inspector2:ListFindings", "sts:GetCallerIdentity"], Resource = "*" },
      { Effect = "Allow", Action = ["ecr:DescribeImages", "ecr:DescribeImageScanFindings"], Resource = aws_ecr_repository.test.arn },
      { Effect = "Allow", Action = ["ssm:GetParameter"], Resource = local.approval_parameter_arn },
      { Effect = "Allow", Action = ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem"], Resource = aws_dynamodb_table.remediation[0].arn },
      { Effect = "Allow", Action = ["codebuild:StartBuild", "codebuild:BatchGetProjects"], Resource = local.remediation_project_arn },
      { Effect = "Allow", Action = ["logs:CreateLogStream", "logs:PutLogEvents"], Resource = "${aws_cloudwatch_log_group.inspector[0].arn}:*" },
      { Effect = "Allow", Action = ["xray:PutTraceSegments", "xray:PutTelemetryRecords"], Resource = "*" },
      { Effect = "Allow", Action = ["s3:PutObject"], Resource = "${aws_s3_bucket.evidence[0].arn}/inspector/*" },
      { Effect = "Allow", Action = ["kms:GenerateDataKey", "kms:Decrypt", "kms:DescribeKey"], Resource = aws_kms_key.project.arn },
      { Effect = "Allow", Action = ["sqs:SendMessage"], Resource = aws_sqs_queue.failures[0].arn }
    ]
  })
}
resource "aws_lambda_function" "inspector" {
  #checkov:skip=CKV_AWS_117:API-only Lambda needs no VPC access; the external CodeBuild project has separately approved cluster connectivity.
  #checkov:skip=CKV_AWS_272:Code signing requires separately approved AWS Signer infrastructure; source archive hash tracks reviewed code.
  count                          = var.enable_inspector_response ? 1 : 0
  function_name                  = "${var.project}-inspector-response"
  role                           = aws_iam_role.inspector[0].arn
  runtime                        = "python3.12"
  handler                        = "inspector_response.lambda_handler"
  filename                       = data.archive_file.automation[0].output_path
  source_code_hash               = data.archive_file.automation[0].output_base64sha256
  timeout                        = 60
  memory_size                    = 256
  reserved_concurrent_executions = 1
  kms_key_arn                    = aws_kms_key.project.arn
  tracing_config { mode = "Active" }
  dead_letter_config { target_arn = aws_sqs_queue.failures[0].arn }
  environment {
    variables = merge(local.remediation_environment, {
      CODEBUILD_PROJECT           = var.remediation_codebuild_project_name
      REMEDIATION_SOURCE_REVISION = var.remediation_source_revision
      REMEDIATION_SOURCE_URL      = "https://github.com/${var.github_repository}.git"
      CODEBUILD_SERVICE_ROLE_ARN  = aws_iam_role.remediation[0].arn
      IDEMPOTENCY_TABLE           = aws_dynamodb_table.remediation[0].name
      EVIDENCE_BUCKET             = aws_s3_bucket.evidence[0].id
    })
  }
  lifecycle {
    precondition {
      condition     = var.remediation_codebuild_project_name != "" && can(regex("^[0-9a-f]{40}$", var.remediation_source_revision))
      error_message = "Configure an existing dedicated CodeBuild project with a reviewed commit, fixed environment, the exported role and network access to EKS. Standard hosted CodeBuild cannot reach the restricted API."
    }
  }
  depends_on = [aws_iam_role_policy.inspector, aws_cloudwatch_log_group.inspector]
}
resource "aws_lambda_function_event_invoke_config" "inspector" {
  count                        = var.enable_inspector_response ? 1 : 0
  function_name                = aws_lambda_function.inspector[0].function_name
  maximum_event_age_in_seconds = 3600
  maximum_retry_attempts       = 2
  destination_config {
    on_failure { destination = aws_sqs_queue.failures[0].arn }
  }
}
resource "aws_cloudwatch_event_rule" "inspector" {
  count = var.enable_inspector_response ? 1 : 0
  name  = "${var.project}-inspector-critical-high"
  event_pattern = jsonencode({
    source = ["aws.inspector2"], "detail-type" = ["Inspector2 Finding"], account = [var.aws_account_id], region = [var.region]
    detail = { status = ["ACTIVE"], severity = ["HIGH", "CRITICAL"], type = ["PACKAGE_VULNERABILITY"], resources = { type = ["AWS_ECR_CONTAINER_IMAGE"], details = { awsEcrContainerImage = { repositoryName = [aws_ecr_repository.test.name] } } } }
  })
}
resource "aws_cloudwatch_event_target" "inspector" {
  count = var.enable_inspector_response ? 1 : 0
  rule  = aws_cloudwatch_event_rule.inspector[0].name
  arn   = aws_lambda_function.inspector[0].arn
  retry_policy {
    maximum_event_age_in_seconds = 3600
    maximum_retry_attempts       = 2
  }
  dead_letter_config { arn = aws_sqs_queue.failures[0].arn }
}
resource "aws_lambda_permission" "inspector" {
  count          = var.enable_inspector_response ? 1 : 0
  statement_id   = "AllowInspectorEvent"
  action         = "lambda:InvokeFunction"
  function_name  = aws_lambda_function.inspector[0].function_name
  principal      = "events.amazonaws.com"
  source_arn     = aws_cloudwatch_event_rule.inspector[0].arn
  source_account = var.aws_account_id
}
resource "aws_cloudwatch_event_rule" "build_failure" {
  count = var.enable_inspector_response ? 1 : 0
  name  = "${var.project}-remediation-build-failure"
  event_pattern = jsonencode({
    source = ["aws.codebuild"], "detail-type" = ["CodeBuild Build State Change"], account = [var.aws_account_id], region = [var.region]
    detail = { "project-name" = [var.remediation_codebuild_project_name], "build-status" = ["FAILED", "FAULT", "STOPPED", "TIMED_OUT"] }
  })
}
resource "aws_cloudwatch_event_target" "build_failure" {
  count = var.enable_inspector_response ? 1 : 0
  rule  = aws_cloudwatch_event_rule.build_failure[0].name
  arn   = aws_sqs_queue.failures[0].arn
}
resource "aws_sqs_queue_policy" "failures" {
  count     = local.automation_enabled ? 1 : 0
  queue_url = aws_sqs_queue.failures[0].id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{ Effect = "Allow", Principal = { Service = "events.amazonaws.com" }, Action = "sqs:SendMessage", Resource = aws_sqs_queue.failures[0].arn,
      Condition = { ArnEquals = { "aws:SourceArn" = concat(
        var.enable_self_healing ? [aws_cloudwatch_event_rule.restricted_ssh[0].arn] : [],
        var.enable_inspector_response ? [aws_cloudwatch_event_rule.inspector[0].arn, aws_cloudwatch_event_rule.build_failure[0].arn] : []
      ) } }
    }]
  })
}
