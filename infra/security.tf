locals {
  account_root       = "arn:aws:iam::${var.aws_account_id}:root"
  oidc_issuer        = replace(aws_eks_cluster.demo.identity[0].oidc[0].issuer, "https://", "")
  automation_enabled = var.enable_self_healing || var.enable_inspector_response
}

# One customer-managed key bounds cost while protecting this dedicated lab's data.
resource "aws_kms_key" "project" {
  description             = "${var.project} EKS, ECR, secrets and evidence encryption"
  enable_key_rotation     = true
  deletion_window_in_days = 30
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      { Sid = "EnableAccountIAM", Effect = "Allow", Principal = { AWS = local.account_root }, Action = "kms:*", Resource = "*" },
      {
        Sid       = "CloudWatchLogs", Effect = "Allow", Principal = { Service = "logs.${var.region}.amazonaws.com" }
        Action    = ["kms:Encrypt", "kms:Decrypt", "kms:ReEncrypt*", "kms:GenerateDataKey*", "kms:DescribeKey"], Resource = "*"
        Condition = { ArnLike = { "kms:EncryptionContext:aws:logs:arn" = ["arn:aws:logs:${var.region}:${var.aws_account_id}:log-group:*${var.project}*", "arn:aws:logs:${var.region}:${var.aws_account_id}:log-group:/aws/eks/${var.cluster_name}/cluster"] } }
      },
      {
        Sid       = "ConfigEvidence", Effect = "Allow", Principal = { Service = "config.amazonaws.com" }
        Action    = ["kms:GenerateDataKey", "kms:Decrypt"], Resource = "*"
        Condition = { StringEquals = { "AWS:SourceAccount" = var.aws_account_id } }
      }
    ]
  })
}
resource "aws_kms_alias" "project" {
  name          = "alias/${var.project}-security"
  target_key_id = aws_kms_key.project.key_id
}

resource "aws_default_security_group" "closed" {
  vpc_id  = aws_vpc.demo.id
  ingress = []
  egress  = []
  tags    = { Name = "${var.project}-default-deny" }
}

resource "aws_cloudwatch_log_group" "flow" {
  name              = "/aws/vpc/${var.project}/flow"
  retention_in_days = 365
  kms_key_id        = aws_kms_key.project.arn
}
resource "aws_iam_role" "flow" {
  permissions_boundary = var.iam_permissions_boundary_arn
  name = "${var.project}-flow-logs"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{ Effect = "Allow", Action = "sts:AssumeRole", Principal = { Service = "vpc-flow-logs.amazonaws.com" },
      Condition = { StringEquals = { "aws:SourceAccount" = var.aws_account_id }, ArnLike = { "aws:SourceArn" = "arn:aws:ec2:${var.region}:${var.aws_account_id}:vpc-flow-log/*" } }
    }]
  })
}
resource "aws_iam_role_policy" "flow" {
  role = aws_iam_role.flow.id
  policy = jsonencode({
    Version   = "2012-10-17"
    Statement = [{ Effect = "Allow", Action = ["logs:CreateLogStream", "logs:PutLogEvents", "logs:DescribeLogStreams"], Resource = "${aws_cloudwatch_log_group.flow.arn}:*" }]
  })
}
resource "aws_flow_log" "demo" {
  iam_role_arn    = aws_iam_role.flow.arn
  log_destination = aws_cloudwatch_log_group.flow.arn
  traffic_type    = "ALL"
  vpc_id          = aws_vpc.demo.id
}

resource "aws_iam_openid_connect_provider" "cluster" {
  url            = aws_eks_cluster.demo.identity[0].oidc[0].issuer
  client_id_list = ["sts.amazonaws.com"]
}
resource "aws_iam_role" "cni" {
  permissions_boundary = var.iam_permissions_boundary_arn
  name = "${var.project}-vpc-cni"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{ Effect = "Allow", Action = "sts:AssumeRoleWithWebIdentity", Principal = { Federated = aws_iam_openid_connect_provider.cluster.arn },
      Condition = { StringEquals = { "${local.oidc_issuer}:aud" = "sts.amazonaws.com", "${local.oidc_issuer}:sub" = "system:serviceaccount:kube-system:aws-node" } }
    }]
  })
}
resource "aws_iam_role_policy_attachment" "cni" {
  role       = aws_iam_role.cni.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKS_CNI_Policy"
}

# Intentionally no secret_version resource: test values are written outside Terraform state.
resource "aws_secretsmanager_secret" "demo" {
  #checkov:skip=CKV2_AWS_57:Demo token rotation is manually verified through ESO; no production credential or rotation Lambda is created.
  name                    = "${var.project}/demo/token"
  description             = "Non-production test token consumed by ESO"
  kms_key_id              = aws_kms_key.project.arn
  recovery_window_in_days = 7
}
resource "aws_iam_role" "eso" {
  permissions_boundary = var.iam_permissions_boundary_arn
  name = "${var.project}-eso-reader"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{ Effect = "Allow", Action = "sts:AssumeRoleWithWebIdentity", Principal = { Federated = aws_iam_openid_connect_provider.cluster.arn },
      Condition = { StringEquals = { "${local.oidc_issuer}:aud" = "sts.amazonaws.com", "${local.oidc_issuer}:sub" = "system:serviceaccount:demo:eso-secrets-reader" } }
    }]
  })
}
resource "aws_iam_role_policy" "eso" {
  role = aws_iam_role.eso.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      { Effect = "Allow", Action = ["secretsmanager:GetSecretValue", "secretsmanager:DescribeSecret"], Resource = aws_secretsmanager_secret.demo.arn },
      { Effect    = "Allow", Action = ["kms:Decrypt"], Resource = aws_kms_key.project.arn,
        Condition = { StringEquals = { "kms:ViaService" = "secretsmanager.${var.region}.amazonaws.com", "kms:EncryptionContext:SecretARN" = aws_secretsmanager_secret.demo.arn } }
      }
    ]
  })
}
resource "aws_iam_role" "kyverno" {
  permissions_boundary = var.iam_permissions_boundary_arn
  name = "${var.project}-kyverno-ecr-reader"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{ Effect = "Allow", Action = "sts:AssumeRoleWithWebIdentity", Principal = { Federated = aws_iam_openid_connect_provider.cluster.arn },
      Condition = { StringEquals = { "${local.oidc_issuer}:aud" = "sts.amazonaws.com", "${local.oidc_issuer}:sub" = "system:serviceaccount:kyverno:kyverno-admission-controller" } }
    }]
  })
}
resource "aws_iam_role_policy" "kyverno" {
  #checkov:skip=CKV_AWS_355:ECR GetAuthorizationToken does not support resource-level permissions; image reads are scoped to one repository.
  role = aws_iam_role.kyverno.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      { Effect = "Allow", Action = ["ecr:GetAuthorizationToken"], Resource = "*" },
      { Effect = "Allow", Action = ["ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer", "ecr:BatchCheckLayerAvailability"], Resource = aws_ecr_repository.test.arn }
    ]
  })
}
resource "aws_ecr_lifecycle_policy" "test" {
  repository = aws_ecr_repository.test.name
  policy     = jsonencode({ rules = [{ rulePriority = 1, description = "Remove untagged temporary images after 30 days", selection = { tagStatus = "untagged", countType = "sinceImagePushed", countUnit = "days", countNumber = 30 }, action = { type = "expire" } }] })
}
