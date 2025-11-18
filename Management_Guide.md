# EC2 Management Agent - Usage Guide

## 🎯 What It Does

AI-powered EC2 and EBS management through natural language commands.

## 📋 Supported Operations

### EC2 Instance Operations

| Operation | Command Examples |
|-----------|-----------------|
| **List Instances** | "Show me all my EC2 instances"<br>"List running instances" |
| **Launch Instance** | "Launch a t3.micro instance with ami-12345"<br>"Create a new EC2 instance" |
| **Start Instance** | "Start instance i-1234567890"<br>"Power on my instance" |
| **Stop Instance** | "Stop instance i-1234567890"<br>"Shut down instance i-abc123" |
| **Terminate Instance** | "Terminate instance i-1234567890"<br>"Delete instance i-abc123" |
| **Change Type** | "Change i-1234567890 to t3.large"<br>"Resize instance to m5.xlarge" |

### EBS Volume Operations

| Operation | Command Examples |
|-----------|-----------------|
| **List Volumes** | "Show me all volumes"<br>"List EBS volumes for i-1234567890" |
| **Create Volume** | "Create a 100GB gp3 volume"<br>"Create new EBS volume" |
| **Attach Volume** | "Attach vol-123 to i-456 as /dev/sdf"<br>"Connect volume to instance" |
| **Detach Volume** | "Detach vol-123"<br>"Disconnect volume from instance" |
| **Delete Volume** | "Delete vol-123"<br>"Remove volume vol-abc" |

## 🔧 Example Queries

### Information Queries (Read-Only)

```
"What EC2 instances are currently running?"
"Show me all stopped instances"
"List volumes attached to instance i-1234567890"
"How many instances do I have?"
"What's the status of instance i-abc123?"
```

### Action Queries (Write Operations)

```
"Launch a t3.micro instance in us-east-1a"
"Stop instance i-1234567890"
"Change instance i-abc123 to t3.large"
"Create a 50GB gp3 volume"
"Delete volume vol-xyz789"
```

## 📖 Detailed Examples

### Example 1: Launch New Instance

**Query:**
```
"Launch a t3.small instance with AMI ami-0abcdef1234567890"
```

**What happens:**
1. AI parses: action=launch_instance, ami_id=ami-0abcdef, instance_type=t3.small
2. Calls `launch_ec2_instance()`
3. Creates instance with tags
4. Returns instance ID and status
5. AI explains the result

**Response:**
```
✅ Successfully launched EC2 instance!

Instance Details:
- Instance ID: i-0abc123def456789
- Type: t3.small
- State: pending → running
- AMI: ami-0abcdef1234567890
- Private IP: Will be assigned when running
- Tags: ManagedBy=AI-Assistant

The instance is now starting up. It should be ready in 1-2 minutes.
You can connect to it once the state shows "running".
```

### Example 2: Stop Instance

**Query:**
```
"Stop instance i-0abc123def456789"
```

**Response:**
```
✅ Instance stop initiated successfully!

Instance i-0abc123def456789:
- Current State: stopping
- Previous State: running
- This will take 30-60 seconds to complete

⚠️ Note: While stopped, you'll still be charged for:
- EBS volumes attached to this instance
- Elastic IPs associated with it

You won't be charged for instance hours while stopped.
```

### Example 3: Change Instance Type

**Query:**
```
"Change instance i-0abc123def456789 from t3.small to t3.large"
```

**Response:**
```
⚠️ Instance type change requires the instance to be stopped.

Current Status:
- Instance ID: i-0abc123def456789
- Current Type: t3.small
- Current State: running

To proceed:
1. Stop the instance first
2. Then I can change it to t3.large
3. Start it again

Would you like me to stop it now?
```

**Follow-up Query:**
```
"Yes, stop it first"
```

**After stopping, query again:**
```
"Now change i-0abc123def456789 to t3.large"
```

**Response:**
```
✅ Instance type changed successfully!

Details:
- Instance ID: i-0abc123def456789
- Old Type: t3.small (2 vCPU, 2GB RAM)
- New Type: t3.large (2 vCPU, 8GB RAM)
- State: stopped

You can now start the instance with the new type.
The instance will boot with 4x more memory.

Cost Impact:
- t3.small: ~$0.0208/hour
- t3.large: ~$0.0832/hour (4x more expensive)
```

### Example 4: Create and Attach Volume

**Query:**
```
"Create a 100GB gp3 volume and attach it to instance i-0abc123def456789"
```

**Step 1 Response (Volume Creation):**
```
✅ EBS volume created successfully!

Volume Details:
- Volume ID: vol-0xyz789abc123def
- Size: 100 GB
- Type: gp3 (3000 IOPS, 125 MB/s)
- State: creating → available
- Availability Zone: us-east-1a

Now attaching to instance i-0abc123def456789...
```

**Step 2 Response (Volume Attachment):**
```
✅ Volume attached successfully!

Attachment Details:
- Volume: vol-0xyz789abc123def
- Instance: i-0abc123def456789
- Device: /dev/sdf
- State: attaching → attached

Next Steps:
1. SSH into your instance
2. Check if volume appears: lsblk
3. Format if new: sudo mkfs -t ext4 /dev/sdf
4. Mount: sudo mount /dev/sdf /mnt/data
5. Add to fstab for persistence
```

### Example 5: List All Resources

**Query:**
```
"Show me all my EC2 instances and volumes"
```

**Response:**
```
📊 Your AWS EC2 Resources Overview

=== EC2 INSTANCES (3 total) ===

1. i-0abc123def456789
   - Type: t3.large
   - State: running
   - Private IP: 10.0.1.45
   - Public IP: 54.123.45.67
   - Launch Time: 2025-01-10T14:30:00
   - Tags: Name=WebServer, Env=Production

2. i-0def456abc789012
   - Type: t3.micro
   - State: stopped
   - Private IP: 10.0.1.67
   - Launch Time: 2025-01-08T09:15:00
   - Tags: Name=DevServer

3. i-0ghi789jkl012345
   - Type: t2.small
   - State: running
   - Private IP: 10.0.2.23
   - Public IP: 34.56.78.90
   - Tags: Name=TestServer

=== EBS VOLUMES (5 total) ===

1. vol-0xyz789abc123def
   - Size: 100 GB
   - Type: gp3
   - State: in-use
   - Attached: i-0abc123def456789 (/dev/sdf)

2. vol-0abc123def456789
   - Size: 30 GB
   - Type: gp3
   - State: in-use
   - Attached: i-0abc123def456789 (/dev/sda1) [Root]

3. vol-0def456ghi789012
   - Size: 20 GB
   - Type: gp2
   - State: available (Not attached)

4. vol-0jkl345mno678901
   - Size: 50 GB
   - Type: gp3
   - State: in-use
   - Attached: i-0ghi789jkl012345 (/dev/sdf)

5. vol-0pqr678stu901234
   - Size: 10 GB
   - Type: gp3
   - State: in-use
   - Attached: i-0def456abc789012 (/dev/sda1) [Root]

💰 Monthly Cost Estimate:
- Running instances: ~$150/month
- Stopped instances (storage only): ~$3/month
- EBS volumes: ~$21/month
- Total: ~$174/month
```

## ⚠️ Safety Features

### Destructive Operation Warnings

**Terminate Instance:**
```
⚠️ DESTRUCTIVE ACTION WARNING ⚠️

You're about to TERMINATE instance i-0abc123def456789

This action:
✗ Cannot be undone
✗ Will permanently delete the instance
✗ Will delete the root EBS volume (if not configured otherwise)
✗ Will release the public IP address
✓ Will stop all charges for this instance

Instance Details:
- Name: ProductionWebServer
- Type: t3.large
- Uptime: 45 days
- Has attached volumes: 2 (vol-123, vol-456)

⚠️ Attached volumes will be preserved but detached.

Are you absolutely sure? Type 'CONFIRM TERMINATE' to proceed.
```

**Delete Volume:**
```
⚠️ VOLUME DELETION WARNING ⚠️

You're about to DELETE volume vol-0xyz789abc123def

This action:
✗ Cannot be undone
✗ Will permanently delete all data on this volume
✗ There is no backup/snapshot

Volume Details:
- Size: 100 GB
- Type: gp3
- State: available
- Last Snapshot: None found
- Data: Will be lost forever

💡 Recommendation: Create a snapshot first:
   "Create snapshot of vol-0xyz789abc123def"

Type 'CONFIRM DELETE' to proceed, or 'CANCEL' to abort.
```

## 🔐 Security Best Practices

### 1. Use Tags for Management
```python
tags = {
    'Name': 'WebServer-Prod',
    'Environment': 'Production',
    'Owner': 'DevOps',
    'CostCenter': 'Engineering',
    'ManagedBy': 'AI-Assistant'
}
```

### 2. Limit Actions with IAM
```json
{
  "Effect": "Allow",
  "Action": ["ec2:StopInstances"],
  "Resource": "*",
  "Condition": {
    "StringEquals": {
      "ec2:ResourceTag/Environment": "Development"
    }
  }
}
```

### 3. Enable Termination Protection
```
"Enable termination protection for instance i-0abc123def456789"
```

## 💰 Cost Optimization Tips

### Stop vs Terminate
```
STOP Instance:
✓ Preserves instance configuration
✓ Keeps EBS volumes
✓ Can restart anytime
✓ Still charges for EBS storage (~$0.10/GB/month)
✗ Charges for Elastic IP if attached

TERMINATE Instance:
✓ No more instance charges
✓ Releases resources
✗ Cannot restart
✗ Loses instance configuration
✗ Deletes root volume (unless configured otherwise)
```

### Instance Type Costs
```
t3.nano:   $0.0052/hour  (~$3.74/month)
t3.micro:  $0.0104/hour  (~$7.49/month)
t3.small:  $0.0208/hour  (~$15/month)
t3.medium: $0.0416/hour  (~$30/month)
t3.large:  $0.0832/hour  (~$60/month)
t3.xlarge: $0.1664/hour  (~$120/month)
```

### Volume Type Costs (per GB/month)
```
gp3: $0.08/GB  (3000 IOPS, 125 MB/s baseline)
gp2: $0.10/GB  (3 IOPS/GB)
io2: $0.125/GB (Higher performance)
st1: $0.045/GB (Throughput optimized)
sc1: $0.015/GB (Cold storage)
```

## 🚨 Common Errors & Solutions

### Error 1: "Instance must be stopped to change type"
**Solution:**
```
1. "Stop instance i-xyz"
2. Wait 30-60 seconds
3. "Change instance i-xyz to t3.large"
4. "Start instance i-xyz"
```

### Error 2: "Volume is attached, cannot delete"
**Solution:**
```
1. "Detach volume vol-xyz"
2. Wait for state=available
3. "Delete volume vol-xyz"
```

### Error 3: "Instance not found"
**Solution:**
```
- Verify instance ID: "List all instances"
- Check if already terminated
- Ensure correct region
```

### Error 4: "Insufficient permissions"
**Solution:**
- Update IAM policy with required permissions
- Check ec2-iam-policy.json for required actions
- Contact AWS administrator

## 📊 Query Response Examples

### Informational Response
```
Query: "What instances are running?"

Response: You have 2 running instances:

1. i-0abc123 (t3.large) - WebServer-Prod
   - Running for 15 days
   - Public IP: 54.123.45.67
   - Cost: ~$2/day

2. i-0def456 (t3.micro) - TestServer
   - Running for 3 days
   - Public IP: 34.56.78.90
   - Cost: ~$0.25/day

Total running cost: ~$2.25/day (~$68/month)
```

### Action Confirmation Response
```
Query: "Stop instance i-0abc123"

Response: ✅ Instance stopped successfully!

Action Summary:
- Instance: i-0abc123 (WebServer-Prod)
- Previous State: running
- Current State: stopped
- Time: 45 seconds

Cost Impact:
- Before: $0.0832/hour (running)
- After: $0.00/hour (stopped) + $3/month (storage)
- Savings: ~$60/month while stopped

You can restart anytime with: "Start instance i-0abc123"
```

## 🔄 Workflow Examples

### Complete Instance Lifecycle
```
1. "Launch t3.micro with ami-12345"
   → Creates instance i-abc123

2. "Create 50GB gp3 volume in us-east-1a"
   → Creates vol-xyz789

3. "Attach vol-xyz789 to i-abc123"
   → Attaches volume

4. "Stop instance i-abc123"
   → Stops instance

5. "Change i-abc123 to t3.small"
   → Upgrades instance type

6. "Start instance i-abc123"
   → Starts with new type

7. "Detach vol-xyz789"
   → Detaches volume

8. "Delete vol-xyz789"
   → Deletes volume

9. "Terminate i-abc123"
   → Terminates instance
```

## 🎯 Best Practices

1. **Always tag your resources**
2. **Stop instances when not in use**
3. **Use appropriate instance types**
4. **Regular volume cleanup**
5. **Create snapshots before changes**
6. **Monitor costs regularly**
7. **Use termination protection for critical instances**
8. **Document instance purposes**

---

**Ready to manage your EC2 infrastructure with AI!** 🚀