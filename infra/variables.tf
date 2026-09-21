variable "region" {
  type    = string
  default = "ap-northeast-2"
}
variable "aws_account_id" {
  type = string
  validation {
    condition     = can(regex("^[0-9]{12}$", var.aws_account_id))
    error_message = "Use the intended 12-digit AWS account ID."
  }
}
variable "project" {
  type    = string
  default = "team4"
}
variable "cluster_name" {
  type    = string
  default = "team4-eks"
}
variable "kubernetes_version" {
  type    = string
  default = "1.35"
}
variable "admin_public_cidrs" {
  type = list(string)
  validation {
    condition     = length(var.admin_public_cidrs) > 0 && alltrue([for c in var.admin_public_cidrs : can(cidrhost(c, 0)) && endswith(c, "/32")])
    error_message = "Provide each authorized operator's public IPv4 address as x.x.x.x/32."
  }
}
variable "operator_principal_arns" {
  type = map(string)
  validation {
    condition     = length(var.operator_principal_arns) > 0 && alltrue([for arn in values(var.operator_principal_arns) : can(regex("^arn:aws:iam::[0-9]{12}:(role|user)/.+$", arn))])
    error_message = "Provide permanent IAM role/user ARNs, not STS session ARNs or root."
  }
}
variable "addon_versions" {
  type = object({
    vpc-cni    = string
    kube-proxy = string
    coredns    = string
  })
}
