# DynamoDB table for action logging
resource "aws_dynamodb_table" "action_logs" {
  name           = "${var.project_name}-action-logs"
  billing_mode   = "PAY_PER_REQUEST"
  hash_key       = "log_id"
  
  attribute {
    name = "log_id"
    type = "S"
  }
  
  attribute {
    name = "timestamp"
    type = "S"
  }
  
  global_secondary_index {
    name            = "timestamp-index"
    hash_key        = "timestamp"
    projection_type = "ALL"
  }
  
  ttl {
    attribute_name = "ttl"
    enabled        = true
  }
  
  tags = {
    Name = "${var.project_name}-action-logs"
  }
}

# DynamoDB table for confirmation tokens
resource "aws_dynamodb_table" "confirmation_tokens" {
  name           = "${var.project_name}-confirmation-tokens"
  billing_mode   = "PAY_PER_REQUEST"
  hash_key       = "token"
  
  attribute {
    name = "token"
    type = "S"
  }
  
  ttl {
    attribute_name = "ttl"
    enabled        = true
  }
  
  tags = {
    Name = "${var.project_name}-confirmation-tokens"
  }
}

# IAM Role for Lambda
resource "aws_iam_role" "ec2_manager_lambda_role" {
  name = "${var.project_name}-ec2-manager-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })
}

# IAM Policy for Lambda
resource "aws_iam_role_policy" "ec2_manager_lambda_policy" {
  name = "${var.project_name}-ec2-manager-policy"
  role = aws_iam_role.ec2_manager_lambda_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "ec2:DescribeInstances",
          "ec2:DescribeInstanceStatus",
          "ec2:DescribeImages",
          "ec2:RunInstances",
          "ec2:TerminateInstances",
          "ec2:StartInstances",
          "ec2:StopInstances",
          "ec2:ModifyInstanceAttribute",
          "ec2:CreateImage",
          "ec2:DescribeVolumes",
          "ec2:CreateVolume",
          "ec2:DeleteVolume",
          "ec2:AttachVolume",
          "ec2:DetachVolume",
          "ec2:CreateTags",
          "ec2:DescribeAvailabilityZones"
        ]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "cloudwatch:PutMetricAlarm",
          "cloudwatch:DeleteAlarms",
          "cloudwatch:DescribeAlarms"
        ]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "dynamodb:PutItem",
          "dynamodb:GetItem",
          "dynamodb:DeleteItem",
          "dynamodb:Scan",
          "dynamodb:Query"
        ]
        Resource = [
          aws_dynamodb_table.action_logs.arn,
          "${aws_dynamodb_table.action_logs.arn}/index/*",
          aws_dynamodb_table.confirmation_tokens.arn
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "bedrock:InvokeModel"
        ]
        Resource = [
          "arn:aws:bedrock:*::foundation-model/us.anthropic.claude-3-5-sonnet-20241022-v2:0",
          "arn:aws:bedrock:us-east-1:920013188018:inference-profile/us.anthropic.claude-3-5-sonnet-20241022-v2:0",
          "arn:aws:bedrock:us-west-2::foundation-model/anthropic.claude-3-5-sonnet-20241022-v2:0",
          "arn:aws:bedrock:us-east-1::foundation-model/anthropic.claude-3-5-sonnet-20241022-v2:0"
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "arn:aws:logs:*:*:*"
      }
    ]
  })
}

# CloudWatch Log Group
resource "aws_cloudwatch_log_group" "ec2_manager_logs" {
  name              = "/aws/lambda/${var.project_name}-ec2-manager"
  retention_in_days = var.log_retention_days
}

# Archive Lambda code
data "archive_file" "ec2_manager_lambda_zip" {
  type        = "zip"
  source_dir  = "${path.module}/lambda"
  output_path = "${path.module}/ec2-manager-deployment.zip"
}

# Lambda Function
resource "aws_lambda_function" "ec2_manager" {
  filename         = data.archive_file.ec2_manager_lambda_zip.output_path
  function_name    = "${var.project_name}-ec2-manager"
  role            = aws_iam_role.ec2_manager_lambda_role.arn
  handler         = "lambda_handler.lambda_handler"
  source_code_hash = data.archive_file.ec2_manager_lambda_zip.output_base64sha256
  runtime         = "python3.11"
  timeout         = 60
  memory_size     = 512

  environment {
    variables = {
      BEDROCK_MODEL_ID           = var.bedrock_model_id
      BEDROCK_REGION             = var.bedrock_region
      MAX_INSTANCE_COST_PER_HOUR = var.max_instance_cost_per_hour
      ACTION_LOG_TABLE           = aws_dynamodb_table.action_logs.name
      CONFIRMATION_TABLE         = aws_dynamodb_table.confirmation_tokens.name
      APPROVAL_SNS_TOPIC         = var.enable_sns_alerts ? aws_sns_topic.ec2_alerts[0].arn : ""
    }
  }

  depends_on = [
    aws_cloudwatch_log_group.ec2_manager_logs,
    aws_iam_role_policy.ec2_manager_lambda_policy
  ]
}

# API Gateway
resource "aws_api_gateway_rest_api" "ec2_manager_api" {
  name        = "${var.project_name}-ec2-manager-api"
  description = "API for EC2 Management Agent"

  endpoint_configuration {
    types = ["REGIONAL"]
  }
}

resource "aws_api_gateway_resource" "manage" {
  rest_api_id = aws_api_gateway_rest_api.ec2_manager_api.id
  parent_id   = aws_api_gateway_rest_api.ec2_manager_api.root_resource_id
  path_part   = "manage"
}

resource "aws_api_gateway_method" "post_manage" {
  rest_api_id   = aws_api_gateway_rest_api.ec2_manager_api.id
  resource_id   = aws_api_gateway_resource.manage.id
  http_method   = "POST"
  authorization = var.enable_api_key ? "API_KEY" : "NONE"
}

resource "aws_api_gateway_integration" "ec2_manager_integration" {
  rest_api_id             = aws_api_gateway_rest_api.ec2_manager_api.id
  resource_id             = aws_api_gateway_resource.manage.id
  http_method             = aws_api_gateway_method.post_manage.http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = aws_lambda_function.ec2_manager.invoke_arn
}

# CORS
resource "aws_api_gateway_method" "options_manage" {
  rest_api_id   = aws_api_gateway_rest_api.ec2_manager_api.id
  resource_id   = aws_api_gateway_resource.manage.id
  http_method   = "OPTIONS"
  authorization = "NONE"
}

resource "aws_api_gateway_integration" "options_manage" {
  rest_api_id = aws_api_gateway_rest_api.ec2_manager_api.id
  resource_id = aws_api_gateway_resource.manage.id
  http_method = aws_api_gateway_method.options_manage.http_method
  type        = "MOCK"

  request_templates = {
    "application/json" = "{\"statusCode\": 200}"
  }
}

resource "aws_api_gateway_method_response" "options_manage" {
  rest_api_id = aws_api_gateway_rest_api.ec2_manager_api.id
  resource_id = aws_api_gateway_resource.manage.id
  http_method = aws_api_gateway_method.options_manage.http_method
  status_code = "200"

  response_parameters = {
    "method.response.header.Access-Control-Allow-Headers" = true
    "method.response.header.Access-Control-Allow-Methods" = true
    "method.response.header.Access-Control-Allow-Origin"  = true
  }
}

resource "aws_api_gateway_integration_response" "options_manage" {
  rest_api_id = aws_api_gateway_rest_api.ec2_manager_api.id
  resource_id = aws_api_gateway_resource.manage.id
  http_method = aws_api_gateway_method.options_manage.http_method
  status_code = "200"

  response_parameters = {
    "method.response.header.Access-Control-Allow-Headers" = "'Content-Type,X-Api-Key'"
    "method.response.header.Access-Control-Allow-Methods" = "'POST,OPTIONS'"
    "method.response.header.Access-Control-Allow-Origin"  = "'*'"
  }

  depends_on = [aws_api_gateway_integration.options_manage]
}

# Lambda Permission
resource "aws_lambda_permission" "ec2_manager_api_gateway" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.ec2_manager.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_api_gateway_rest_api.ec2_manager_api.execution_arn}/*/*"
}

# API Deployment
resource "aws_api_gateway_deployment" "ec2_manager_deployment" {
  rest_api_id = aws_api_gateway_rest_api.ec2_manager_api.id

  triggers = {
    redeployment = sha1(jsonencode([
      aws_api_gateway_resource.manage.id,
      aws_api_gateway_method.post_manage.id,
      aws_api_gateway_integration.ec2_manager_integration.id,
    ]))
  }

  lifecycle {
    create_before_destroy = true
  }

  depends_on = [
    aws_api_gateway_integration.ec2_manager_integration
  ]
}

# API Stage
resource "aws_api_gateway_stage" "ec2_manager_prod" {
  deployment_id = aws_api_gateway_deployment.ec2_manager_deployment.id
  rest_api_id   = aws_api_gateway_rest_api.ec2_manager_api.id
  stage_name    = var.api_stage_name

  xray_tracing_enabled = true
}

# SNS Topic for alerts (optional)
resource "aws_sns_topic" "ec2_alerts" {
  count = var.enable_sns_alerts ? 1 : 0
  name  = "${var.project_name}-ec2-alerts"
}

resource "aws_sns_topic_subscription" "ec2_alerts_email" {
  count     = var.enable_sns_alerts && var.alert_email != "" ? 1 : 0
  topic_arn = aws_sns_topic.ec2_alerts[0].arn
  protocol  = "email"
  endpoint  = var.alert_email
}

# API Key (optional)
resource "aws_api_gateway_api_key" "ec2_manager_api_key" {
  count = var.enable_api_key ? 1 : 0
  name  = "${var.project_name}-ec2-manager-key"
}

resource "aws_api_gateway_usage_plan" "ec2_manager_usage_plan" {
  count = var.enable_api_key ? 1 : 0
  name  = "${var.project_name}-ec2-manager-plan"

  api_stages {
    api_id = aws_api_gateway_rest_api.ec2_manager_api.id
    stage  = aws_api_gateway_stage.ec2_manager_prod.stage_name
  }
}

resource "aws_api_gateway_usage_plan_key" "ec2_manager_usage_plan_key" {
  count         = var.enable_api_key ? 1 : 0
  key_id        = aws_api_gateway_api_key.ec2_manager_api_key[0].id
  key_type      = "API_KEY"
  usage_plan_id = aws_api_gateway_usage_plan.ec2_manager_usage_plan[0].id
}