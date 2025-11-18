# aws_cloudengineer_bot# AWS EC2 Management Agent - Complete Solution

AI-powered EC2 management with user email tracking, AMI backups, CloudWatch alarms, CloudFront HTTPS, and comprehensive DynamoDB logging.

## ✨ Features

- 🖥️ **EC2 Management**: Launch, stop, start, terminate, resize
- 💾 **AMI Backups**: Server-level backups (not snapshots)
- 🔔 **CloudWatch Alarms**: CPU and status check monitoring
- 📧 **Email Tracking**: All actions logged with user email
- 📊 **DynamoDB Logging**: Complete audit trail with timestamps
- 🔐 **HTTPS via CloudFront**: Secure access with SSL
- 🌐 **Custom Domain**: Route53 integration
- 🛡️ **Safety Features**: Confirmations, budget limits, backup checks
- 💬 **Chat Interface**: User-friendly web UI

## 📋 Prerequisites

1. **Terraform** >= 1.0
2. **AWS CLI** configured
3. **Bedrock access** (Claude 3.5 Sonnet)
4. **Route53 domain** (optional)

## 🚀 Quick Deploy (5 Minutes)

### Step 1: Create Structure

```bash
mkdir ec2-manager
cd ec2-manager
mkdir lambda-ec2 frontend-ec2
```

### Step 2: Copy Files

From the artifacts above, copy:
- `lambda-ec2/lambda_ec2_manager.py`
- `frontend-ec2/index.html`
- `ec2-main.tf`
- `ec2-variables.tf`
- `ec2-outputs.tf`
- `ec2-s3-hosting.tf`
- `terraform.tfvars` (provided)

### Step 3: Configure `terraform.tfvars`

```hcl
aws_region                = "us-east-1"
project_name              = "ec2-manager"
bedrock_model_id          = "anthropic.claude-3-5-sonnet-20241022-v2:0"
max_instance_cost_per_hour = "1.0"

# CloudFront (HTTPS)
enable_cloudfront = true

# Custom Domain (Optional)
domain_name      = ""  # Leave empty to use CloudFront URL
route53_zone_id  = ""

# Security
enable_api_key = false
```

### Step 4: Deploy

```bash
terraform init
terraform apply
# Type: yes
```

### Step 5: Access

```bash
terraform output frontend_url
# Opens: https://xxxxx.cloudfront.net (or your custom domain)
```

## 📧 User Email Field

### Why Email is Required

Every action is logged in DynamoDB with the user's email:

```json
{
  "log_id": "uuid-1234",
  "timestamp": "2025-01-15T14:30:00",
  "action": "terminate_instance",
  "parameters": "{\"instance_id\": \"i-abc123\"}",
  "status": "success",
  "user_email": "john@example.com",
  "user_query": "Terminate instance i-abc123"
}
```

### Email Usage

1. **Action Logging**: Track who performed each action
2. **Notifications**: Receive emails for important actions
3. **Audit Trail**: Complete accountability
4. **SNS Alerts**: Get notified about your actions

### Frontend Flow

1. User opens frontend
2. Enters email address (required)
3. Email saved in localStorage
4. Sent with every API request
5. Logged in DynamoDB

## 🌐 CloudFront + Route53 Setup

### Option A: CloudFront Only (No Custom Domain)

```hcl
# terraform.tfvars
enable_cloudfront = true
domain_name       = ""
```

**Result**: `https://d1234abcd.cloudfront.net`

### Option B: CloudFront + Custom Domain

```hcl
# terraform.tfvars
enable_cloudfront = true
domain_name       = "ec2-manager.yourdomain.com"
route53_zone_id   = "Z1234567890ABC"
```

**Result**: `https://ec2-manager.yourdomain.com`

### Find Zone ID

```bash
aws route53 list-hosted-zones --query 'HostedZones[*].[Name,Id]' --output table
```

### Option C: Create New Hosted Zone

```hcl
# terraform.tfvars
enable_cloudfront  = true
create_hosted_zone = true
domain_name        = "ec2-manager.yourdomain.com"
```

After deployment:
```bash
terraform output route53_nameservers
# Update your domain registrar with these nameservers
```

## 📖 Usage Examples

### List Instances
```
User Email: john@example.com
Query: "Show me all EC2 instances"
```

### Create AMI Backup
```
"Create AMI backup for i-abc123"
→ AMI created with user email tag
→ Logged in DynamoDB
```

### Create Alarm
```
"Create CPU alarm for i-abc123 threshold 80%"
→ Alarm created
→ Action logged with user email
```

### Terminate (with confirmation)
```
"Terminate i-abc123"
→ Returns token: A7B3C9
→ Email notification sent

"Confirm with A7B3C9"
→ Instance terminated
→ Logged with user email
```

### View Your Actions
```
"Show my action logs"
→ Returns recent actions by your email
```

## 🗄️ DynamoDB Tables

### Action Logs Table Schema

| Field | Type | Description |
|-------|------|-------------|
| log_id | String (PK) | Unique action ID |
| timestamp | String (GSI) | When action occurred |
| action | String | Action type |
| parameters | String (JSON) | Action parameters |
| status | String | success/failed/pending |
| result | String (JSON) | Action result |
| user_email | String | Who performed action |
| user_query | String | Original query |
| error | String | Error message (if failed) |
| ttl | Number | Auto-delete after 90 days |

### Query Logs by Email

```bash
aws dynamodb scan \
  --table-name ec2-manager-action-logs \
  --filter-expression "user_email = :email" \
  --expression-attribute-values '{":email":{"S":"john@example.com"}}'
```

### Confirmation Tokens Table

| Field | Type | Description |
|-------|------|-------------|
| token | String (PK) | Unique token |
| action | String | Pending action |
| parameters | String (JSON) | Action parameters |
| created_at | String | Creation time |
| expires_at | Number | Expiration timestamp |
| ttl | Number | Auto-delete after 5 min |

## 🔐 Security Features

### 1. Email Validation
- Frontend validates email format
- Required for all actions
- Stored in localStorage

### 2. Confirmation Tokens
- Destructive actions require tokens
- Tokens expire in 5 minutes
- One-time use only

### 3. Budget Limits
- Prevents expensive instance launches
- Configurable per-hour limit
- Cost estimates provided

### 4. AMI Backup Checks
- Checks for backups before termination
- Recommends backup if none found
- Auto-backup before resize

### 5. Action Logging
- Everything logged to DynamoDB
- Complete audit trail
- 90-day retention

## 💰 Cost Estimate

| Component | Monthly Cost |
|-----------|--------------|
| Lambda (1K invocations) | $0.20 |
| API Gateway (1K requests) | $3.50 |
| DynamoDB (pay-per-request) | $1.25 |
| S3 Hosting | $0.05 |
| CloudFront (10GB) | $1.00 |
| Route53 (hosted zone) | $0.50 |
| Bedrock (100K tokens) | $0.30 |
| **Total** | **~$6.80/month** |

## 🎯 Example Workflows

### Complete Termination Flow

```
1. User: john@example.com
   Query: "Check AMI backup for i-abc123"
   → Shows: Last backup 10 days ago

2. "Create AMI backup for i-abc123"
   → Creates ami-xyz789
   → Logs: user_email=john@example.com

3. "Terminate i-abc123"
   → Backup verified
   → Returns token: A7B3C9
   → Email sent to john@example.com

4. "Confirm with A7B3C9"
   → Instance terminated
   → Logged with user email
   → Email notification sent
```

### Launch with Budget Check

```
User: jane@example.com
Query: "Launch m5.4xlarge instance"

Response: ❌ Budget exceeded
- Cost: $0.768/hour ($560/month)
- Your limit: $1.00/hour
- Logged with user email: jane@example.com
```

## 📊 View Action Logs

### Via DynamoDB Console
1. AWS Console → DynamoDB
2. Tables → ec2-manager-action-logs
3. Explore items
4. Filter by user_email

### Via AWS CLI
```bash
# Recent 10 actions
aws dynamodb scan \
  --table-name ec2-manager-action-logs \
  --limit 10 \
  --scan-index-forward false

# Actions by specific user
aws dynamodb scan \
  --table-name ec2-manager-action-logs \
  --filter-expression "user_email = :email" \
  --expression-attribute-values '{":email":{"S":"john@example.com"}}'

# Failed actions
aws dynamodb scan \
  --table-name ec2-manager-action-logs \
  --filter-expression "#s = :status" \
  --expression-attribute-names '{"#s": "status"}' \
  --expression-attribute-values '{":status":{"S":"failed"}}'
```

## 🔧 Configuration

### Budget Limit
```hcl
max_instance_cost_per_hour = "2.0"
```

### Enable API Key
```hcl
enable_api_key = true
```
Get key:
```bash
terraform output -raw api_key
```

### SNS Email Alerts
```hcl
enable_sns_alerts = true
alert_email       = "ops-team@example.com"
```

## 🐛 Troubleshooting

### Email Not Required Error
- Email field is required in frontend
- Check browser console for errors
- Verify email format (must contain @)

### CloudFront Not Working
```bash
# Check distribution status
terraform output cloudfront_domain

# Wait for deployment (5-10 minutes)
```

### Custom Domain Not Working
```bash
# Verify Route53 record
aws route53 list-resource-record-sets \
  --hosted-zone-id YOUR_ZONE_ID

# Check DNS propagation
nslookup ec2-manager.yourdomain.com
```

### Actions Not Logged
```bash
# Check DynamoDB table
aws dynamodb describe-table --table-name ec2-manager-action-logs

# Check Lambda logs
aws logs tail /aws/lambda/ec2-manager-ec2-manager --follow
```

## 📁 Complete File Structure

```
ec2-manager/
├── lambda-ec2/
│   └── lambda_ec2_manager.py      # Lambda with email tracking
├── frontend-ec2/
│   └── index.html                 # UI with email field
├── ec2-main.tf                    # Lambda, API, DynamoDB
├── ec2-variables.tf               # Configuration variables
├── ec2-outputs.tf                 # Deployment outputs
├── ec2-s3-hosting.tf              # S3, CloudFront, Route53
└── terraform.tfvars               # Your settings
```

## 🔄 Updates

### Update Lambda (add user_email to more functions)
```bash
# Edit lambda-ec2/lambda_ec2_manager.py
terraform apply
```

### Update Frontend (change email field)
```bash
# Edit frontend-ec2/index.html
terraform apply
```

## 🧹 Cleanup

```bash
terraform destroy
```

**⚠️ Warning**: This will delete:
- All DynamoDB data (action logs)
- CloudFront distribution
- S3 bucket
- Lambda function

## 🎓 Best Practices

1. ✅ Always enter valid email
2. ✅ Review action logs weekly
3. ✅ Create AMI backups before changes
4. ✅ Use confirmation tokens properly
5. ✅ Set appropriate budget limits
6. ✅ Enable SNS alerts for production
7. ✅ Monitor DynamoDB costs
8. ✅ Clean old AMI backups periodically

## 📈 Monitoring

### View Recent Actions
```bash
# Last 24 hours
aws dynamodb scan \
  --table-name ec2-manager-action-logs \
  --filter-expression "timestamp > :yesterday" \
  --expression-attribute-values '{":yesterday":{"S":"2025-01-14T00:00:00"}}'
```

### Count Actions by User
```bash
aws dynamodb scan \
  --table-name ec2-manager-action-logs \
  --select COUNT \
  --filter-expression "user_email = :email" \
  --expression-attribute-values '{":email":{"S":"john@example.com"}}'
```

---

**Your EC2 infrastructure is now fully managed with complete audit trail and user accountability!** 🚀

**URLs after deployment:**
- Frontend: `https://your-cloudfront-url` or `https://your-domain.com`
- API: Check `terraform output api_gateway_url`
- DynamoDB: AWS Console → DynamoDB → ec2-manager-action-logs