# AWS Configuration
aws_region     = "us-east-1"
bedrock_region = "us-east-1"

# Project Configuration
project_name = "ec2-manager"
environment  = "prod"

# Bedrock Model Configuration
bedrock_model_id = "us.anthropic.claude-3-5-sonnet-20241022-v2:0"

# Budget Configuration
max_instance_cost_per_hour = "1.0"  # Maximum $1/hour per instance

# Custom Domain Configuration (Optional)
# Option 1: Create NEW hosted zone
# create_hosted_zone = true
# domain_name        = "ec2-manager.yourdomain.com"
# route53_zone_id    = ""

# Option 2: Use EXISTING hosted zone
# create_hosted_zone = false
# domain_name        = "ec2-manager.yourdomain.com"
# route53_zone_id    = "Z1234567890ABC"

# Option 3: No custom domain (use CloudFront URL)
create_hosted_zone = true
domain_name        = "awsengineerbot.run.place"
route53_zone_id    = ""

# CloudFront Configuration
enable_cloudfront = true  # Always use CloudFront for HTTPS

# API Gateway Configuration
api_stage_name = "prod"

# Security Configuration
enable_api_key = false  # Set to true for production

# SNS Alerts Configuration (Optional)
enable_sns_alerts = false
alert_email       = ""  # Add your email if enabling alerts

# Logging Configuration
log_retention_days = 7

# Additional Tags
tags = {
  Owner       = "DevOps Team"
  CostCenter  = "Engineering"
  Application = "EC2 Management"
  ManagedBy   = "Terraform"
}

# To find your Route53 Zone ID:
# aws route53 list-hosted-zones --query 'HostedZones[*].[Name,Id]' --output table