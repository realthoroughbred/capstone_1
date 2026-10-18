output "cluster_name" {
  value = aws_eks_cluster.demo.name
}
output "region" {
  value = var.region
}
output "repository_url" {
  value = aws_ecr_repository.test.repository_url
}
output "repository_name" {
  value = aws_ecr_repository.test.name
}
output "demo_security_group_id" {
  value = aws_security_group.healing_demo.id
}
output "node_role_arn" {
  value = aws_iam_role.node.arn
}
output "addon_versions" {
  value = var.addon_versions
}
output "eso_role_arn" {
  value = aws_iam_role.eso.arn
}
output "kyverno_role_arn" {
  value = aws_iam_role.kyverno.arn
}
output "demo_secret_arn" {
  value = aws_secretsmanager_secret.demo.arn
}
output "github_deploy_role_arn" {
  value = try(aws_iam_role.github_deploy[0].arn, null)
}
output "sg_healing_function_name" {
  value = try(aws_lambda_function.healing[0].function_name, null)
}
output "config_rule_name" {
  value = try(aws_config_config_rule.restricted_ssh[0].name, null)
}
output "evidence_bucket" {
  value = try(aws_s3_bucket.evidence[0].id, null)
}
output "failure_queue_url" {
  value = try(aws_sqs_queue.failures[0].url, null)
}
output "inspector_function_name" {
  value = try(aws_lambda_function.inspector[0].function_name, null)
}
output "remediation_role_arn" {
  value = try(aws_iam_role.remediation[0].arn, null)
}
output "remediation_project_name" {
  value = var.enable_inspector_response ? var.remediation_codebuild_project_name : null
}
output "remediation_codebuild_contract" {
  description = "Apply these settings to the existing dedicated CodeBuild project only after network/cost approval. Protect project updates from the runtime role."
  value = var.enable_inspector_response ? {
    project_name   = var.remediation_codebuild_project_name
    service_role   = aws_iam_role.remediation[0].arn
    source_url     = "https://github.com/${var.github_repository}.git"
    source_version = var.remediation_source_revision
    buildspec      = "automation/buildspec-remediate.yml"
    privileged     = false
    log_group      = aws_cloudwatch_log_group.remediation[0].name
    encryption_key = aws_kms_key.project.arn
    artifacts = {
      type                = "S3"
      location            = aws_s3_bucket.evidence[0].id
      path                = "inspector"
      namespace_type      = "BUILD_ID"
      name                = "remediation"
      packaging           = "NONE"
      encryption_disabled = false
    }
    environment = merge(local.remediation_environment, {
      IDEMPOTENCY_TABLE = aws_dynamodb_table.remediation[0].name
      EVIDENCE_BUCKET   = aws_s3_bucket.evidence[0].id
    })
  } : null
}
