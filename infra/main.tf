data "aws_availability_zones" "available" {
  state = "available"
}

resource "aws_vpc" "demo" {
  cidr_block           = "10.40.0.0/16"
  enable_dns_support   = true
  enable_dns_hostnames = true
  tags                 = { Name = "${var.project}-vpc" }
}
resource "aws_internet_gateway" "demo" {
  vpc_id = aws_vpc.demo.id
}
resource "aws_subnet" "public" {
  count                   = 2
  vpc_id                  = aws_vpc.demo.id
  cidr_block              = cidrsubnet(aws_vpc.demo.cidr_block, 8, count.index + 1)
  availability_zone       = data.aws_availability_zones.available.names[count.index]
  map_public_ip_on_launch = true
  tags                    = { Name = "${var.project}-public-${count.index + 1}" }
}
resource "aws_route_table" "public" {
  vpc_id = aws_vpc.demo.id
  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.demo.id
  }
}
resource "aws_route_table_association" "public" {
  count          = 2
  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}

resource "aws_iam_role" "cluster" {
  name = "${var.project}-eks-cluster"
  assume_role_policy = jsonencode({
    Version   = "2012-10-17"
    Statement = [{ Effect = "Allow", Principal = { Service = "eks.amazonaws.com" }, Action = "sts:AssumeRole" }]
  })
}
resource "aws_iam_role_policy_attachment" "cluster" {
  role       = aws_iam_role.cluster.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKSClusterPolicy"
}
resource "aws_cloudwatch_log_group" "cluster" {
  name              = "/aws/eks/${var.cluster_name}/cluster"
  retention_in_days = 7
}
resource "aws_eks_cluster" "demo" {
  name     = var.cluster_name
  role_arn = aws_iam_role.cluster.arn
  version  = var.kubernetes_version
  access_config {
    authentication_mode                         = "API"
    bootstrap_cluster_creator_admin_permissions = false
  }
  vpc_config {
    subnet_ids              = aws_subnet.public[*].id
    endpoint_private_access = true
    endpoint_public_access  = true
    public_access_cidrs     = var.admin_public_cidrs
  }
  enabled_cluster_log_types = ["api", "audit", "authenticator"]
  depends_on = [
    aws_iam_role_policy_attachment.cluster,
    aws_cloudwatch_log_group.cluster,
    aws_route_table_association.public
  ]
}
resource "aws_eks_access_entry" "operators" {
  for_each      = var.operator_principal_arns
  cluster_name  = aws_eks_cluster.demo.name
  principal_arn = each.value
  type          = "STANDARD"
}
resource "aws_eks_access_policy_association" "operators" {
  for_each      = var.operator_principal_arns
  cluster_name  = aws_eks_cluster.demo.name
  principal_arn = aws_eks_access_entry.operators[each.key].principal_arn
  policy_arn    = "arn:aws:eks::aws:cluster-access-policy/AmazonEKSClusterAdminPolicy"
  access_scope {
    type = "cluster"
  }
}

resource "aws_iam_role" "node" {
  name = "${var.project}-eks-node"
  assume_role_policy = jsonencode({
    Version   = "2012-10-17"
    Statement = [{ Effect = "Allow", Principal = { Service = "ec2.amazonaws.com" }, Action = "sts:AssumeRole" }]
  })
}
resource "aws_iam_role_policy_attachment" "node" {
  for_each = toset([
    "AmazonEKSWorkerNodePolicy",
    "AmazonEC2ContainerRegistryPullOnly",
    "AmazonEKS_CNI_Policy"
  ])
  role       = aws_iam_role.node.name
  policy_arn = "arn:aws:iam::aws:policy/${each.value}"
}
resource "aws_launch_template" "node" {
  name_prefix = "${var.project}-node-"
  metadata_options {
    http_endpoint               = "enabled"
    http_tokens                 = "required"
    http_put_response_hop_limit = 1
    instance_metadata_tags      = "disabled"
  }
  block_device_mappings {
    device_name = "/dev/xvda"
    ebs {
      volume_size           = 20
      volume_type           = "gp3"
      encrypted             = true
      delete_on_termination = true
    }
  }
  tag_specifications {
    resource_type = "instance"
    tags = {
      Name      = "${var.project}-worker"
      Project   = var.project
      ManagedBy = "Terraform"
    }
  }
}
resource "aws_eks_node_group" "demo" {
  cluster_name    = aws_eks_cluster.demo.name
  node_group_name = "demo-workers"
  node_role_arn   = aws_iam_role.node.arn
  subnet_ids      = aws_subnet.public[*].id
  version         = var.kubernetes_version
  ami_type        = "AL2023_x86_64_STANDARD"
  instance_types  = ["t3.medium"]
  capacity_type   = "ON_DEMAND"
  launch_template {
    id      = aws_launch_template.node.id
    version = tostring(aws_launch_template.node.latest_version)
  }
  scaling_config {
    min_size     = 1
    desired_size = 1
    max_size     = 2
  }
  update_config {
    max_unavailable = 1
  }
  depends_on = [aws_iam_role_policy_attachment.node, aws_route_table_association.public]
}
resource "aws_eks_addon" "network" {
  for_each                    = toset(["vpc-cni", "kube-proxy"])
  cluster_name                = aws_eks_cluster.demo.name
  addon_name                  = each.value
  addon_version               = var.addon_versions[each.value]
  resolve_conflicts_on_create = "OVERWRITE"
  resolve_conflicts_on_update = "PRESERVE"
  configuration_values        = each.value == "vpc-cni" ? jsonencode({ enableNetworkPolicy = "true" }) : null
  depends_on                  = [aws_eks_node_group.demo]
}
resource "aws_eks_addon" "dns" {
  cluster_name                = aws_eks_cluster.demo.name
  addon_name                  = "coredns"
  addon_version               = var.addon_versions.coredns
  resolve_conflicts_on_create = "OVERWRITE"
  resolve_conflicts_on_update = "PRESERVE"
  depends_on                  = [aws_eks_addon.network]
}

resource "aws_ecr_repository" "test" {
  name                 = "${var.project}-test"
  image_tag_mutability = "IMMUTABLE"
  force_delete         = false
  image_scanning_configuration {
    scan_on_push = true
  }
  encryption_configuration {
    encryption_type = "AES256"
  }
}
resource "aws_security_group" "healing_demo" {
  name        = "${var.project}-healing-demo"
  description = "Unattached security group for later configuration remediation tests"
  vpc_id      = aws_vpc.demo.id
  ingress     = []
  egress      = []
  tags = {
    Name     = "${var.project}-healing-demo"
    DemoOnly = "true"
  }
}
