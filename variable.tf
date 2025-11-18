variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

variable "project_name" {
  description = "Project name prefix"
  type        = string
  default     = "ec2-manager"
}

variable "environment" {
  description = "Environment name"
  type        = string
  default     = "prod"
}

variable "bedrock_model_id" {
  description = "Bedrock model ID"
  type        = string
  default     = "anthropic.claude-3-5-sonnet-20241022-v2:0"
}

variable "bedrock_region" {
  description = "Bedrock region"
  type        = string
  default     = "us-east-1"
}

variable "log_retention_days" {
  description = "CloudWatch log retention"
  type        = number
  default     = 7
}

variable "api_stage_name" {
  description = "API Gateway stage"
  type        = string
  default     = "prod"
}

variable "enable_api_key" {
  description = "Enable API key"
  type        = bool
  default     = false
}

variable "max_instance_cost_per_hour" {
  description = "Max hourly instance cost"
  type        = string
  default     = "1.0"
}

variable "enable_sns_alerts" {
  description = "Enable SNS alerts"
  type        = bool
  default     = false
}

variable "alert_email" {
  description = "Email for alerts"
  type        = string
  default     = ""
}

variable "domain_name" {
  description = "Custom domain"
  type        = string
  default     = ""
}

variable "route53_zone_id" {
  description = "Route53 zone ID"
  type        = string
  default     = ""
}

variable "create_hosted_zone" {
  description = "Create new hosted zone"
  type        = bool
  default     = false
}

variable "enable_cloudfront" {
  description = "Enable CloudFront distribution"
  type        = bool
  default     = true
}

variable "tags" {
  description = "Additional tags"
  type        = map(string)
  default     = {}
}