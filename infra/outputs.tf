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
