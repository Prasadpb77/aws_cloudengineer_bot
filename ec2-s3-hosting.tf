# Route53 Hosted Zone (optional)
resource "aws_route53_zone" "main" {
  count = var.create_hosted_zone ? 1 : 0
  name  = var.domain_name

  tags = merge(
    {
      Name = "${var.project_name}-hosted-zone"
    },
    var.tags
  )
}

# S3 Bucket
resource "aws_s3_bucket" "ec2_frontend" {
  bucket = var.domain_name

  tags = merge(
    {
      Name = "${var.project_name}-frontend"
    },
    var.tags
  )
}

resource "aws_s3_bucket_website_configuration" "ec2_frontend" {
  bucket = aws_s3_bucket.ec2_frontend.id

  index_document {
    suffix = "index.html"
  }

  error_document {
    key = "index.html"
  }
}

resource "aws_s3_bucket_public_access_block" "ec2_frontend" {
  bucket = aws_s3_bucket.ec2_frontend.id

  block_public_acls       = false
  block_public_policy     = false
  ignore_public_acls      = false
  restrict_public_buckets = false
}

# S3 Bucket Policy (different for CloudFront vs direct access)
resource "aws_s3_bucket_policy" "ec2_frontend" {
  bucket = aws_s3_bucket.ec2_frontend.id

  policy = var.enable_cloudfront ? jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "CloudFrontReadGetObject"
        Effect = "Allow"
        Principal = {
          AWS = aws_cloudfront_origin_access_identity.ec2_frontend[0].iam_arn
        }
        Action   = "s3:GetObject"
        Resource = "${aws_s3_bucket.ec2_frontend.arn}/*"
      }
    ]
  }) : jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "PublicReadGetObject"
        Effect    = "Allow"
        Principal = "*"
        Action    = "s3:GetObject"
        Resource  = "${aws_s3_bucket.ec2_frontend.arn}/*"
      }
    ]
  })

  depends_on = [
    aws_s3_bucket_public_access_block.ec2_frontend,
    aws_cloudfront_origin_access_identity.ec2_frontend
  ]
}

# Generate and upload HTML
locals {
  index_html_template = file("${path.module}/frontend/index.html")
  
  index_html_content = replace(
    replace(
      local.index_html_template,
      "$${api_gateway_url}",
      "${aws_api_gateway_stage.ec2_manager_prod.invoke_url}/manage"
    ),
    "$${api_key_required}",
    var.enable_api_key ? "true" : "false"
  )
}

resource "aws_s3_object" "ec2_index" {
  bucket       = aws_s3_bucket.ec2_frontend.id
  key          = "index.html"
  content      = local.index_html_content
  content_type = "text/html"
  etag         = md5(local.index_html_content)

  depends_on = [aws_api_gateway_stage.ec2_manager_prod]
}

# CloudFront Origin Access Identity
resource "aws_cloudfront_origin_access_identity" "ec2_frontend" {
  count   = var.enable_cloudfront ? 1 : 0
  comment = "OAI for ${var.project_name} frontend"
}

# CloudFront Distribution
resource "aws_cloudfront_distribution" "ec2_frontend" {
  count   = var.enable_cloudfront ? 1 : 0
  enabled = true

  # Use custom domain or CloudFront domain
  aliases = var.domain_name != "" ? [var.domain_name] : []

  origin {
    domain_name = aws_s3_bucket.ec2_frontend.bucket_regional_domain_name
    origin_id   = "S3-${aws_s3_bucket.ec2_frontend.id}"

    s3_origin_config {
      origin_access_identity = aws_cloudfront_origin_access_identity.ec2_frontend[0].cloudfront_access_identity_path
    }
  }

  default_root_object = "index.html"

  default_cache_behavior {
    allowed_methods        = ["GET", "HEAD", "OPTIONS"]
    cached_methods         = ["GET", "HEAD"]
    target_origin_id       = "S3-${aws_s3_bucket.ec2_frontend.id}"
    viewer_protocol_policy = "redirect-to-https"

    forwarded_values {
      query_string = false
      cookies {
        forward = "none"
      }
    }

    min_ttl     = 0
    default_ttl = 3600
    max_ttl     = 86400
    compress    = true
  }

  custom_error_response {
    error_code         = 404
    response_code      = 200
    response_page_path = "/index.html"
  }

  custom_error_response {
    error_code         = 403
    response_code      = 200
    response_page_path = "/index.html"
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  # Use ACM certificate if custom domain, otherwise default CloudFront cert
  viewer_certificate {
    cloudfront_default_certificate = var.domain_name == ""
    acm_certificate_arn            = "arn:aws:acm:us-east-1:920013188018:certificate/4f16b957-3ca3-4498-93aa-bf200eed9fc5"
    ssl_support_method             = var.domain_name != "" ? "sni-only" : null
    minimum_protocol_version       = var.domain_name != "" ? "TLSv1.2_2021" : null
  }

  tags = merge(
    {
      Name = "${var.project_name}-cloudfront"
    },
    var.tags
  )
}

# Route53 Record (points to CloudFront or S3)
resource "aws_route53_record" "ec2_frontend" {
  count   = var.domain_name != "" ? 1 : 0
  zone_id = var.create_hosted_zone ? aws_route53_zone.main[0].zone_id : var.route53_zone_id
  name    = var.domain_name
  type    = "A"

  alias {
    name = var.enable_cloudfront ? aws_cloudfront_distribution.ec2_frontend[0].domain_name : aws_s3_bucket_website_configuration.ec2_frontend.website_domain
    zone_id = var.enable_cloudfront ? aws_cloudfront_distribution.ec2_frontend[0].hosted_zone_id : aws_s3_bucket.ec2_frontend.hosted_zone_id
    evaluate_target_health = false
  }

  depends_on = [
    aws_s3_bucket_website_configuration.ec2_frontend,
    aws_cloudfront_distribution.ec2_frontend
  ]
}

data "aws_caller_identity" "current" {}