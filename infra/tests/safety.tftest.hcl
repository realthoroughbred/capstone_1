# Mock plans exercise both resource graphs without credentials or cloud resources.
# They do not validate real AWS account permissions, quotas, availability or IAM evaluation.
mock_provider "aws" {}

override_data {
  target = data.aws_availability_zones.available
  values = { names = ["ap-northeast-2a", "ap-northeast-2c"] }
}

variables {
  aws_account_id     = "123456789012"
  admin_public_cidrs = ["203.0.113.10/32"]
  operator_principal_arns = {
    operator = "arn:aws:iam::123456789012:role/demo-operator"
  }
  # Synthetic test inputs; deployment must use queried regional add-on versions.
  addon_versions = {
    vpc-cni    = "v1.21.1-eksbuild.1"
    kube-proxy = "v1.35.0-eksbuild.1"
    coredns    = "v1.13.1-eksbuild.1"
  }
}

run "default_cost_and_mutation_guards" {
  command = plan
  assert {
    condition     = length(aws_lambda_function.healing) == 0 && length(aws_lambda_function.inspector) == 0 && length(aws_ecr_registry_scanning_configuration.enhanced) == 0
    error_message = "Config/Inspector automation and enhanced scanning must remain opt-in."
  }
  assert {
    condition     = aws_eks_cluster.demo.vpc_config[0].public_access_cidrs == toset(["203.0.113.10/32"])
    error_message = "The EKS API must stay limited to approved operator CIDRs."
  }
  assert {
    condition     = aws_launch_template.node.metadata_options[0].http_tokens == "required" && aws_launch_template.node.metadata_options[0].http_put_response_hop_limit == 1
    error_message = "Unprivileged Pods must not inherit the node instance profile through IMDS."
  }
  assert {
    condition     = aws_ecr_repository.test.image_tag_mutability == "IMMUTABLE_WITH_EXCLUSION" && toset([for filter in aws_ecr_repository.test.image_tag_mutability_exclusion_filter : filter.filter]) == toset(["sha256-*.sig", "sha256-*.att"])
    error_message = "Only Cosign signature/attestation artifact tags may be mutable; application tags remain immutable."
  }
}

run "explicit_automation_keeps_dry_run" {
  command = plan
  variables {
    enable_self_healing                = true
    create_config_recorder             = true
    enable_inspector_response          = true
    enable_github_deploy               = true
    existing_github_oidc_provider_arn  = "arn:aws:iam::123456789012:oidc-provider/token.actions.githubusercontent.com"
    remediation_codebuild_project_name = "team4-reviewed-worker"
    remediation_source_revision        = "1234567890123456789012345678901234567890"
  }
  assert {
    condition     = aws_lambda_function.healing[0].environment[0].variables.DRY_RUN == "true" && aws_lambda_function.inspector[0].environment[0].variables.DRY_RUN == "true"
    error_message = "Creating automation must never implicitly enable security-group or workload mutation."
  }
  assert {
    condition     = aws_lambda_function.healing[0].reserved_concurrent_executions == 1 && aws_lambda_function.inspector[0].reserved_concurrent_executions == 1
    error_message = "Demo remediation concurrency must remain bounded."
  }
  assert {
    condition     = aws_s3_bucket.evidence[0].force_destroy == false && aws_ecr_repository.test.force_delete == false
    error_message = "Evidence and stored images require explicit cleanup before deletion."
  }
  assert {
    condition     = length(aws_cloudwatch_metric_alarm.failures[0].alarm_actions) == 0
    error_message = "Failure notifications require an explicitly supplied approved topic."
  }
  assert {
    condition     = jsondecode(aws_iam_role.github_deploy[0].assume_role_policy).Statement[0].Condition.StringEquals["token.actions.githubusercontent.com:sub"] == "repo:realthoroughbred@272421931/capstone_1@1378935906:environment:aws-demo"
    error_message = "The GitHub role must match the verified immutable subject, with no legacy fallback or wildcard."
  }
}

run "approved_failure_notifications" {
  command = plan
  variables {
    enable_self_healing           = true
    existing_config_recorder_name = "reviewed-running-recorder"
    notification_topic_arn        = "arn:aws:sns:ap-northeast-2:123456789012:approved-operator-alerts"
  }
  assert {
    condition     = aws_cloudwatch_metric_alarm.failures[0].alarm_actions == toset(["arn:aws:sns:ap-northeast-2:123456789012:approved-operator-alerts"])
    error_message = "Failure alarms must target exactly the supplied topic."
  }
}

run "reject_foreign_notification_topic" {
  command = plan
  variables { notification_topic_arn = "arn:aws:sns:us-east-1:999999999999:foreign-topic" }
  expect_failures = [var.notification_topic_arn]
}

run "reject_unreviewed_worker" {
  command = plan
  variables { enable_inspector_response = true }
  expect_failures = [aws_lambda_function.inspector]
}

run "reject_unknown_config_recorder" {
  command = plan
  variables { enable_self_healing = true }
  expect_failures = [aws_config_config_rule.restricted_ssh]
}

run "reject_public_api_wildcard" {
  command = plan
  variables { admin_public_cidrs = ["0.0.0.0/0"] }
  expect_failures = [var.admin_public_cidrs]
}

run "reject_ipv6_prefix_disguised_as_host" {
  command = plan
  variables { admin_public_cidrs = ["2001:db8::/32"] }
  expect_failures = [var.admin_public_cidrs]
}
