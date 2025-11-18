output "lambda_function_name" {
  description = "Lambda function name"
  value       = aws_lambda_function.ec2_manager.function_name
}

output "api_gateway_url" {
  description = "API Gateway endpoint"
  value       = "${aws_api_gateway_stage.ec2_manager_prod.invoke_url}/manage"
}

output "api_key" {
  description = "API Key"
  value       = var.enable_api_key ? aws_api_gateway_api_key.ec2_manager_api_key[0].value : "API key not enabled"
  sensitive   = true
}

output "dynamodb_action_logs_table" {
  description = "DynamoDB action logs table"
  value       = aws_dynamodb_table.action_logs.name
}

output "dynamodb_tokens_table" {
  description = "DynamoDB tokens table"
  value       = aws_dynamodb_table.confirmation_tokens.name
}

output "frontend_url" {
  description = "Frontend URL"
  value       = var.enable_cloudfront ? (var.domain_name != "" ? "https://${var.domain_name}" : "https://${aws_cloudfront_distribution.ec2_frontend[0].domain_name}") : (var.domain_name != "" ? "http://${var.domain_name}" : "http://${aws_s3_bucket.ec2_frontend.bucket}.s3-website-${var.aws_region}.amazonaws.com")
}

output "cloudfront_domain" {
  description = "CloudFront domain name"
  value       = var.enable_cloudfront ? aws_cloudfront_distribution.ec2_frontend[0].domain_name : "CloudFront not enabled"
}

output "s3_website_endpoint" {
  description = "S3 website endpoint"
  value       = "http://${aws_s3_bucket.ec2_frontend.bucket}.s3-website-${var.aws_region}.amazonaws.com"
}

output "route53_nameservers" {
  description = "Route53 name servers (if created new zone)"
  value       = var.create_hosted_zone ? aws_route53_zone.main[0].name_servers : []
}

output "test_command" {
  description = "Test command"
  value       = <<-EOT
    curl -X POST ${aws_api_gateway_stage.ec2_manager_prod.invoke_url}/manage \
      -H "Content-Type: application/json" \
      -d '{"query": "List all my EC2 instances"}'
  EOT
}