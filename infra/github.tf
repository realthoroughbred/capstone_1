resource "aws_iam_openid_connect_provider" "github" {
  count          = var.enable_github_deploy && var.existing_github_oidc_provider_arn == "" ? 1 : 0
  url            = "https://token.actions.githubusercontent.com"
  client_id_list = ["sts.amazonaws.com"]
}
resource "aws_iam_role" "github_deploy" {
  permissions_boundary = var.iam_permissions_boundary_arn
  count                = var.enable_github_deploy ? 1 : 0
  name                 = "${var.project}-github-deploy"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{ Effect = "Allow", Action = "sts:AssumeRoleWithWebIdentity",
      Principal = { Federated = var.existing_github_oidc_provider_arn != "" ? var.existing_github_oidc_provider_arn : aws_iam_openid_connect_provider.github[0].arn },
      Condition = { StringEquals = {
        "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com",
        "token.actions.githubusercontent.com:sub" = "${var.github_subject_prefix}:environment:${var.github_environment}"
      } }
    }]
  })
}
resource "aws_iam_role_policy" "github_deploy" {
  #checkov:skip=CKV_AWS_355:GetAuthorizationToken has no resource-level permission; all image operations are scoped to the demo repository.
  count = var.enable_github_deploy ? 1 : 0
  role  = aws_iam_role.github_deploy[0].id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      { Effect = "Allow", Action = ["ecr:GetAuthorizationToken"], Resource = "*" },
      { Effect = "Allow", Action = ["ecr:BatchCheckLayerAvailability", "ecr:InitiateLayerUpload", "ecr:UploadLayerPart", "ecr:CompleteLayerUpload", "ecr:PutImage", "ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer", "ecr:DescribeImages"], Resource = aws_ecr_repository.test.arn },
      { Effect = "Allow", Action = ["eks:DescribeCluster"], Resource = aws_eks_cluster.demo.arn }
    ]
  })
}
resource "aws_eks_access_entry" "github_deploy" {
  count             = var.enable_github_deploy ? 1 : 0
  cluster_name      = aws_eks_cluster.demo.name
  principal_arn     = aws_iam_role.github_deploy[0].arn
  kubernetes_groups = ["team4:deploy"]
  type              = "STANDARD"
}
