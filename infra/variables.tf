variable "region" {
  type    = string
  default = "ap-northeast-2"
}
variable "availability_zones" {
  description = "Pin two reviewed zone names so new regional AZs cannot silently change subnet placement."
  type        = list(string)
  default     = ["ap-northeast-2a", "ap-northeast-2c"]
  validation {
    condition     = length(var.availability_zones) == 2 && length(distinct(var.availability_zones)) == 2 && alltrue([for zone in var.availability_zones : startswith(zone, var.region)])
    error_message = "Provide exactly two distinct reviewed Availability Zone names within the target region."
  }
}
variable "aws_account_id" {
  type = string
  validation {
    condition     = can(regex("^[0-9]{12}$", var.aws_account_id))
    error_message = "Use the intended 12-digit AWS account ID."
  }
}
variable "iam_permissions_boundary_arn" {
  description = "Admin-managed runtime boundary for every project role. The supplied team4 operator provisioning policy requires this boundary."
  type        = string
  default     = null
  nullable    = true
  validation {
    condition     = var.iam_permissions_boundary_arn == null ? true : can(regex("^arn:aws:iam::[0-9]{12}:policy/.+$", var.iam_permissions_boundary_arn))
    error_message = "Use a pre-existing administrator-managed IAM policy ARN as the role boundary."
  }
}
variable "project" {
  type    = string
  default = "team4"
  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{2,19}$", var.project))
    error_message = "Use a 3-20 character lowercase project slug for AWS resource names."
  }
}
variable "cluster_name" {
  type    = string
  default = "team4-eks"
}
variable "kubernetes_version" {
  type    = string
  default = "1.35"
}
variable "node_instance_type" {
  description = "t3.large gives 8 GiB and up to 35 standard VPC-CNI Pods for ESO, Kyverno, Argo CD and demo workloads."
  type        = string
  default     = "t3.large"
  validation {
    condition     = contains(["t3.medium", "t3.large", "t3.xlarge"], var.node_instance_type)
    error_message = "Choose a reviewed x86_64 t3.medium, t3.large or t3.xlarge instance size."
  }
}
variable "node_min_size" {
  type    = number
  default = 1
  validation {
    condition     = var.node_min_size >= 1 && floor(var.node_min_size) == var.node_min_size
    error_message = "At least one integer worker node is required for this lab."
  }
}
variable "node_desired_size" {
  type    = number
  default = 1
  validation {
    condition     = var.node_desired_size >= var.node_min_size && var.node_desired_size <= var.node_max_size && floor(var.node_desired_size) == var.node_desired_size
    error_message = "Desired workers must be an integer between node_min_size and node_max_size."
  }
}
variable "node_max_size" {
  type    = number
  default = 2
  validation {
    condition     = var.node_max_size >= 1 && floor(var.node_max_size) == var.node_max_size
    error_message = "Maximum worker count must be a positive integer."
  }
}
variable "admin_public_cidrs" {
  type = list(string)
  validation {
    condition     = length(var.admin_public_cidrs) > 0 && alltrue([for c in var.admin_public_cidrs : can(cidrhost(c, 0)) && can(regex("^([0-9]{1,3}\\.){3}[0-9]{1,3}/32$", c))])
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

variable "enable_self_healing" {
  description = "Create billed Config, Lambda, event and evidence resources only after approval."
  type        = bool
  default     = false
}
variable "healing_dry_run" {
  description = "Keep true until the unattached demo SG experiment is explicitly approved."
  type        = bool
  default     = true
}
variable "create_config_recorder" {
  description = "False when an existing regional recorder already records EC2 SecurityGroup. Never replace an organization recorder."
  type        = bool
  default     = false
}
variable "existing_config_recorder_name" {
  description = "Existing, running regional Config recorder; required if self healing is enabled without creating a recorder."
  type        = string
  default     = ""
}
variable "enable_github_deploy" {
  type    = bool
  default = false
}
variable "github_repository" {
  type    = string
  default = "realthoroughbred/capstone_1"
  validation {
    condition     = can(regex("^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$", var.github_repository))
    error_message = "Use the GitHub owner/repository slug."
  }
}
variable "github_environment" {
  description = "Protect this GitHub environment with required reviewers and main-branch deployment restrictions."
  type        = string
  default     = "aws-demo"
  validation {
    condition     = can(regex("^[A-Za-z0-9_-]+$", var.github_environment))
    error_message = "Use an environment name with letters, numbers, underscores and hyphens for an unambiguous exact OIDC subject."
  }
}
variable "github_subject_prefix" {
  description = "Exact immutable OIDC sub_claim_prefix obtained from the repository OIDC customization API. Do not use a wildcard or assume the legacy subject."
  type        = string
  default     = "repo:realthoroughbred@272421931/capstone_1@1378935906"
  validation {
    condition     = can(regex("^repo:[A-Za-z0-9_.-]+@[0-9]+/[A-Za-z0-9_.-]+@[0-9]+$", var.github_subject_prefix)) && replace(var.github_subject_prefix, "/@[0-9]+/", "") == "repo:${var.github_repository}"
    error_message = "Provide the verified immutable owner/repository prefix matching github_repository."
  }
}
variable "existing_github_oidc_provider_arn" {
  description = "Reuse an existing token.actions.githubusercontent.com provider to avoid duplicate account-wide resources."
  type        = string
  default     = ""
}
variable "enable_inspector_response" {
  description = "Enable billed enhanced ECR scanning and CodeBuild response. Changes regional registry scanning configuration."
  type        = bool
  default     = false
}
variable "inspector_dry_run" {
  type    = bool
  default = true
}
variable "remediation_source_revision" {
  description = "Reviewed immutable 40-character Git commit containing automation/buildspec-remediate.yml. Required for Inspector response."
  type        = string
  default     = ""
  validation {
    condition     = var.remediation_source_revision == "" || can(regex("^[0-9a-f]{40}$", var.remediation_source_revision))
    error_message = "Pin CodeBuild to a reviewed full Git commit SHA."
  }
}
variable "remediation_codebuild_project_name" {
  description = "Existing dedicated CodeBuild project with approved network access to EKS and Internet, configured using remediation_codebuild_contract output. No NAT is provisioned by this stack."
  type        = string
  default     = ""
  validation {
    condition     = var.remediation_codebuild_project_name == "" || can(regex("^[A-Za-z0-9][A-Za-z0-9_-]{1,149}$", var.remediation_codebuild_project_name))
    error_message = "Use an existing dedicated CodeBuild project name."
  }
}
variable "approved_image_parameter_name" {
  description = "Existing protected SSM String parameter with approved image JSON; never written by automation roles."
  type        = string
  default     = "/team4/security/approved-image"
}
variable "signing_workflow" {
  description = "Workflow filename whose keyless certificate identity is trusted for image replacement."
  type        = string
  default     = "deploy.yml"
}
