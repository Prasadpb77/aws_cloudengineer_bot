import json
import os
import boto3
import hashlib
import time
import uuid
from datetime import datetime, timedelta
from botocore.exceptions import ClientError

# Initialize AWS clients
ec2_client = boto3.client('ec2')
cloudwatch_client = boto3.client('cloudwatch')
sns_client = boto3.client('sns')
dynamodb = boto3.resource('dynamodb')
bedrock_runtime = boto3.client('bedrock-runtime', region_name=os.environ.get('BEDROCK_REGION', 'us-east-1'))

MODEL_ID = os.environ.get('BEDROCK_MODEL_ID', 'anthropic.claude-3-5-sonnet-20241022-v2:0')
APPROVAL_SNS_TOPIC = os.environ.get('APPROVAL_SNS_TOPIC', '')
MAX_INSTANCE_COST_PER_HOUR = float(os.environ.get('MAX_INSTANCE_COST_PER_HOUR', '1.0'))
ACTION_LOG_TABLE = os.environ.get('ACTION_LOG_TABLE', 'ec2-management-actions')
CONFIRMATION_TABLE = os.environ.get('CONFIRMATION_TABLE', 'ec2-confirmation-tokens')

# DynamoDB tables
action_log_table = dynamodb.Table(ACTION_LOG_TABLE)
confirmation_table = dynamodb.Table(CONFIRMATION_TABLE)

# Instance type pricing (approximate hourly rates in USD)
INSTANCE_PRICING = {
    't3.nano': 0.0052, 't3.micro': 0.0104, 't3.small': 0.0208,
    't3.medium': 0.0416, 't3.large': 0.0832, 't3.xlarge': 0.1664,
    't3.2xlarge': 0.3328, 't2.micro': 0.0116, 't2.small': 0.023,
    't2.medium': 0.0464, 't2.large': 0.0928, 'm5.large': 0.096,
    'm5.xlarge': 0.192, 'm5.2xlarge': 0.384, 'm5.4xlarge': 0.768,
    'c5.large': 0.085, 'c5.xlarge': 0.17, 'c5.2xlarge': 0.34,
    'r5.large': 0.126, 'r5.xlarge': 0.252, 'r5.2xlarge': 0.504
}

# =====================================================
# DYNAMODB LOGGING
# =====================================================

def log_action(action, parameters, status, result=None, error=None, user_query=None, user_email=None):
    """Log all actions to DynamoDB with user email"""
    try:
        log_id = str(uuid.uuid4())
        timestamp = datetime.now().isoformat()
        
        item = {
            'log_id': log_id,
            'timestamp': timestamp,
            'action': action,
            'parameters': json.dumps(parameters),
            'status': status,  # 'pending', 'success', 'failed', 'requires_confirmation'
            'user_query': user_query or '',
            'user_email': user_email or 'anonymous',
            'ttl': int(time.time()) + (90 * 24 * 60 * 60)  # 90 days retention
        }
        
        if result:
            item['result'] = json.dumps(result)
        if error:
            item['error'] = str(error)
        
        action_log_table.put_item(Item=item)
        
        return {'logged': True, 'log_id': log_id}
    
    except Exception as e:
        print(f"Error logging action: {e}")
        return {'logged': False, 'error': str(e)}

def get_action_logs(limit=50, action_filter=None):
    """Retrieve recent action logs"""
    try:
        params = {
            'Limit': limit,
            'ScanIndexForward': False  # Sort by timestamp descending
        }
        
        if action_filter:
            params['FilterExpression'] = 'action = :action'
            params['ExpressionAttributeValues'] = {':action': action_filter}
        
        response = action_log_table.scan(**params)
        
        items = response.get('Items', [])
        
        # Sort by timestamp
        items.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
        
        return {
            'success': True,
            'logs': items[:limit],
            'count': len(items)
        }
    
    except Exception as e:
        return {'success': False, 'error': str(e)}

# =====================================================
# CONFIRMATION SYSTEM (DynamoDB)
# =====================================================

def generate_confirmation_token(action, parameters):
    """Generate unique confirmation token stored in DynamoDB"""
    data = f"{action}:{json.dumps(parameters)}:{time.time()}"
    token = hashlib.sha256(data.encode()).hexdigest()[:12].upper()
    
    try:
        confirmation_table.put_item(
            Item={
                'token': token,
                'action': action,
                'parameters': json.dumps(parameters),
                'created_at': datetime.now().isoformat(),
                'expires_at': int(time.time() + 300),  # 5 minutes
                'ttl': int(time.time() + 300)
            }
        )
        
        return token
    
    except Exception as e:
        print(f"Error creating confirmation token: {e}")
        return None

def verify_confirmation_token(token):
    """Verify and consume confirmation token from DynamoDB"""
    try:
        response = confirmation_table.get_item(Key={'token': token})
        
        if 'Item' not in response:
            return {'valid': False, 'error': 'Invalid confirmation token'}
        
        token_data = response['Item']
        
        # Check expiration
        if int(time.time()) > int(token_data['expires_at']):
            confirmation_table.delete_item(Key={'token': token})
            return {'valid': False, 'error': 'Token expired (5 min limit)'}
        
        # Get action data
        action = token_data['action']
        parameters = json.loads(token_data['parameters'])
        
        # Delete token (one-time use)
        confirmation_table.delete_item(Key={'token': token})
        
        return {'valid': True, 'action': action, 'parameters': parameters}
    
    except Exception as e:
        return {'valid': False, 'error': str(e)}

def check_budget_limits(instance_type):
    """Check if instance type is within budget limits"""
    hourly_cost = INSTANCE_PRICING.get(instance_type, 0)
    
    if hourly_cost > MAX_INSTANCE_COST_PER_HOUR:
        return {
            'allowed': False,
            'reason': f'Instance type exceeds budget limit',
            'hourly_cost': hourly_cost,
            'limit': MAX_INSTANCE_COST_PER_HOUR,
            'monthly_cost': hourly_cost * 730
        }
    
    return {
        'allowed': True,
        'hourly_cost': hourly_cost,
        'monthly_cost': hourly_cost * 730
    }

# =====================================================
# AMI BACKUP OPERATIONS
# =====================================================

def list_instance_amis(instance_id):
    """List all AMIs created from an instance"""
    try:
        response = ec2_client.describe_images(
            Filters=[
                {'Name': 'tag:SourceInstanceId', 'Values': [instance_id]}
            ],
            Owners=['self']
        )
        
        amis = []
        for image in response['Images']:
            ami_info = {
                'ImageId': image['ImageId'],
                'Name': image.get('Name', 'N/A'),
                'State': image['State'],
                'CreationDate': image['CreationDate'],
                'Description': image.get('Description', ''),
                'Tags': {tag['Key']: tag['Value'] for tag in image.get('Tags', [])}
            }
            amis.append(ami_info)
        
        # Sort by creation date (newest first)
        amis.sort(key=lambda x: x['CreationDate'], reverse=True)
        
        return {'success': True, 'amis': amis, 'count': len(amis)}
    
    except ClientError as e:
        return {'success': False, 'error': str(e)}

def create_ami_backup(instance_id, ami_name=None, description=None, no_reboot=True):
    """Create AMI backup of an instance"""
    try:
        # Get instance details
        instance_response = ec2_client.describe_instances(InstanceIds=[instance_id])
        instance = instance_response['Reservations'][0]['Instances'][0]
        
        instance_name = 'Unknown'
        for tag in instance.get('Tags', []):
            if tag['Key'] == 'Name':
                instance_name = tag['Value']
                break
        
        # Generate AMI name
        timestamp = datetime.now().strftime('%Y-%m-%d-%H%M%S')
        if not ami_name:
            ami_name = f"{instance_name}-backup-{timestamp}"
        
        if not description:
            description = f"AMI backup of {instance_name} ({instance_id}) created on {timestamp}"
        
        # Create AMI
        response = ec2_client.create_image(
            InstanceId=instance_id,
            Name=ami_name,
            Description=description,
            NoReboot=no_reboot,
            TagSpecifications=[
                {
                    'ResourceType': 'image',
                    'Tags': [
                        {'Key': 'Name', 'Value': ami_name},
                        {'Key': 'SourceInstanceId', 'Value': instance_id},
                        {'Key': 'SourceInstanceName', 'Value': instance_name},
                        {'Key': 'BackupType', 'Value': 'AMI'},
                        {'Key': 'CreatedBy', 'Value': 'AI-Assistant'},
                        {'Key': 'CreatedAt', 'Value': timestamp}
                    ]
                }
            ]
        )
        
        ami_id = response['ImageId']
        
        # Log the action
        log_action('create_ami_backup', {'instance_id': instance_id}, 'success', 
                  {'ami_id': ami_id, 'ami_name': ami_name})
        
        return {
            'success': True,
            'ami_id': ami_id,
            'ami_name': ami_name,
            'instance_id': instance_id,
            'instance_name': instance_name,
            'no_reboot': no_reboot,
            'message': f'AMI backup {ami_id} created successfully'
        }
    
    except ClientError as e:
        log_action('create_ami_backup', {'instance_id': instance_id}, 'failed', error=str(e))
        return {'success': False, 'error': str(e)}

def check_ami_backup_status(instance_id):
    """Check if instance has recent AMI backups"""
    try:
        amis_result = list_instance_amis(instance_id)
        
        if not amis_result['success']:
            return amis_result
        
        amis = amis_result['amis']
        
        if not amis:
            return {
                'success': True,
                'has_backup': False,
                'message': 'No AMI backups found for this instance',
                'recommendation': 'Create an AMI backup before proceeding'
            }
        
        # Check for recent backups (within last 7 days)
        recent_amis = []
        cutoff_date = datetime.now() - timedelta(days=7)
        
        for ami in amis:
            ami_date = datetime.fromisoformat(ami['CreationDate'].replace('Z', '+00:00'))
            if ami_date.replace(tzinfo=None) > cutoff_date:
                recent_amis.append(ami)
        
        if recent_amis:
            latest = recent_amis[0]
            return {
                'success': True,
                'has_backup': True,
                'has_recent_backup': True,
                'latest_ami': latest,
                'recent_amis_count': len(recent_amis),
                'total_amis_count': len(amis),
                'message': f'Latest AMI backup: {latest["ImageId"]} from {latest["CreationDate"]}'
            }
        else:
            latest = amis[0]
            return {
                'success': True,
                'has_backup': True,
                'has_recent_backup': False,
                'latest_ami': latest,
                'total_amis_count': len(amis),
                'message': f'Latest AMI backup is older than 7 days: {latest["CreationDate"]}',
                'recommendation': 'Consider creating a fresh AMI backup'
            }
    
    except ClientError as e:
        return {'success': False, 'error': str(e)}

# =====================================================
# CLOUDWATCH ALARMS
# =====================================================

def create_cpu_alarm(instance_id, threshold=80, alarm_name=None, sns_topic_arn=None):
    """Create CPU utilization alarm for instance"""
    try:
        if not alarm_name:
            alarm_name = f"{instance_id}-high-cpu"
        
        alarm_actions = [sns_topic_arn] if sns_topic_arn else []
        
        cloudwatch_client.put_metric_alarm(
            AlarmName=alarm_name,
            ComparisonOperator='GreaterThanThreshold',
            EvaluationPeriods=2,
            MetricName='CPUUtilization',
            Namespace='AWS/EC2',
            Period=300,
            Statistic='Average',
            Threshold=threshold,
            ActionsEnabled=True,
            AlarmActions=alarm_actions,
            AlarmDescription=f'Alert when CPU exceeds {threshold}% for {instance_id}',
            Dimensions=[
                {
                    'Name': 'InstanceId',
                    'Value': instance_id
                }
            ],
            Tags=[
                {'Key': 'InstanceId', 'Value': instance_id},
                {'Key': 'CreatedBy', 'Value': 'AI-Assistant'}
            ]
        )
        
        log_action('create_cpu_alarm', {'instance_id': instance_id, 'threshold': threshold}, 
                  'success', {'alarm_name': alarm_name})
        
        return {
            'success': True,
            'alarm_name': alarm_name,
            'threshold': threshold,
            'instance_id': instance_id,
            'message': f'CPU alarm created: {alarm_name}'
        }
    
    except ClientError as e:
        log_action('create_cpu_alarm', {'instance_id': instance_id}, 'failed', error=str(e))
        return {'success': False, 'error': str(e)}

def create_status_check_alarm(instance_id, alarm_name=None, sns_topic_arn=None):
    """Create status check alarm for instance"""
    try:
        if not alarm_name:
            alarm_name = f"{instance_id}-status-check-failed"
        
        alarm_actions = [sns_topic_arn] if sns_topic_arn else []
        
        cloudwatch_client.put_metric_alarm(
            AlarmName=alarm_name,
            ComparisonOperator='GreaterThanThreshold',
            EvaluationPeriods=2,
            MetricName='StatusCheckFailed',
            Namespace='AWS/EC2',
            Period=60,
            Statistic='Maximum',
            Threshold=0,
            ActionsEnabled=True,
            AlarmActions=alarm_actions,
            AlarmDescription=f'Alert when status check fails for {instance_id}',
            Dimensions=[
                {
                    'Name': 'InstanceId',
                    'Value': instance_id
                }
            ],
            Tags=[
                {'Key': 'InstanceId', 'Value': instance_id},
                {'Key': 'CreatedBy', 'Value': 'AI-Assistant'}
            ]
        )
        
        log_action('create_status_alarm', {'instance_id': instance_id}, 'success', 
                  {'alarm_name': alarm_name})
        
        return {
            'success': True,
            'alarm_name': alarm_name,
            'instance_id': instance_id,
            'message': f'Status check alarm created: {alarm_name}'
        }
    
    except ClientError as e:
        log_action('create_status_alarm', {'instance_id': instance_id}, 'failed', error=str(e))
        return {'success': False, 'error': str(e)}

def list_instance_alarms(instance_id):
    """List all alarms for an instance"""
    try:
        response = cloudwatch_client.describe_alarms(
            AlarmNamePrefix=instance_id
        )
        
        alarms = []
        for alarm in response['MetricAlarms']:
            alarm_info = {
                'AlarmName': alarm['AlarmName'],
                'MetricName': alarm['MetricName'],
                'Threshold': alarm['Threshold'],
                'State': alarm['StateValue'],
                'ActionsEnabled': alarm['ActionsEnabled'],
                'AlarmDescription': alarm.get('AlarmDescription', '')
            }
            alarms.append(alarm_info)
        
        return {'success': True, 'alarms': alarms, 'count': len(alarms)}
    
    except ClientError as e:
        return {'success': False, 'error': str(e)}

def delete_alarm(alarm_name):
    """Delete a CloudWatch alarm"""
    try:
        cloudwatch_client.delete_alarms(AlarmNames=[alarm_name])
        
        log_action('delete_alarm', {'alarm_name': alarm_name}, 'success')
        
        return {
            'success': True,
            'alarm_name': alarm_name,
            'message': f'Alarm {alarm_name} deleted'
        }
    
    except ClientError as e:
        log_action('delete_alarm', {'alarm_name': alarm_name}, 'failed', error=str(e))
        return {'success': False, 'error': str(e)}

# =====================================================
# EC2 INSTANCE OPERATIONS
# =====================================================

def list_ec2_instances(filters=None):
    """List all EC2 instances"""
    try:
        params = {}
        if filters:
            params['Filters'] = filters
        
        response = ec2_client.describe_instances(**params)
        
        instances = []
        for reservation in response['Reservations']:
            for instance in reservation['Instances']:
                launch_time = instance['LaunchTime'].replace(tzinfo=None)
                uptime_days = (datetime.now() - launch_time).days
                
                instance_info = {
                    'InstanceId': instance['InstanceId'],
                    'InstanceType': instance['InstanceType'],
                    'State': instance['State']['Name'],
                    'LaunchTime': instance['LaunchTime'].isoformat(),
                    'UptimeDays': uptime_days,
                    'PrivateIpAddress': instance.get('PrivateIpAddress', 'N/A'),
                    'PublicIpAddress': instance.get('PublicIpAddress', 'N/A'),
                    'AvailabilityZone': instance['Placement']['AvailabilityZone'],
                    'Tags': {tag['Key']: tag['Value'] for tag in instance.get('Tags', [])},
                    'HourlyCost': INSTANCE_PRICING.get(instance['InstanceType'], 0),
                    'MonthlyCost': INSTANCE_PRICING.get(instance['InstanceType'], 0) * 730
                }
                instances.append(instance_info)
        
        return {'success': True, 'instances': instances, 'count': len(instances)}
    
    except ClientError as e:
        return {'success': False, 'error': str(e)}

def launch_ec2_instance(ami_id, instance_type, key_name=None, subnet_id=None, security_group_ids=None, tags=None, dry_run=False):
    """Launch a new EC2 instance"""
    try:
        user_email = os.environ.get('CURRENT_USER_EMAIL', 'anonymous')
        budget_check = check_budget_limits(instance_type)
        if not budget_check['allowed']:
            log_action('launch_instance', {'instance_type': instance_type}, 'failed', 
                      error=budget_check['reason'], user_email=user_email)
            return {'success': False, 'error': budget_check['reason'], 'details': budget_check}
        
        if dry_run:
            return {
                'success': True,
                'dry_run': True,
                'message': 'Dry run successful',
                'estimated_cost': budget_check
            }
        
        params = {
            'ImageId': ami_id,
            'InstanceType': instance_type,
            'MinCount': 1,
            'MaxCount': 1,
            'TagSpecifications': [
                {
                    'ResourceType': 'instance',
                    'Tags': [
                        {'Key': 'ManagedBy', 'Value': 'AI-Assistant'},
                        {'Key': 'LaunchedBy', 'Value': user_email},
                        {'Key': 'LaunchedAt', 'Value': datetime.now().isoformat()}
                    ]
                }
            ]
        }
        
        if key_name:
            params['KeyName'] = key_name
        if subnet_id:
            params['SubnetId'] = subnet_id
        if security_group_ids:
            params['SecurityGroupIds'] = security_group_ids
        if tags:
            params['TagSpecifications'][0]['Tags'].extend([{'Key': k, 'Value': v} for k, v in tags.items()])
        
        response = ec2_client.run_instances(**params)
        instance = response['Instances'][0]
        
        log_action('launch_instance', params, 'success', {'instance_id': instance['InstanceId']}, user_email=user_email)
        
        return {
            'success': True,
            'instance_id': instance['InstanceId'],
            'instance_type': instance['InstanceType'],
            'state': instance['State']['Name'],
            'cost_estimate': budget_check,
            'message': f"Instance {instance['InstanceId']} launched successfully"
        }
    
    except ClientError as e:
        log_action('launch_instance', {'ami_id': ami_id, 'instance_type': instance_type}, 
                  'failed', error=str(e), user_email=os.environ.get('CURRENT_USER_EMAIL', 'anonymous'))
        return {'success': False, 'error': str(e)}

def terminate_ec2_instance(instance_id, confirmation_token=None, skip_backup=False):
    """Terminate instance with AMI backup check"""
    try:
        response = ec2_client.describe_instances(InstanceIds=[instance_id])
        if not response['Reservations']:
            return {'success': False, 'error': f"Instance {instance_id} not found"}
        
        instance = response['Reservations'][0]['Instances'][0]
        instance_name = next((tag['Value'] for tag in instance.get('Tags', []) if tag['Key'] == 'Name'), 'Unknown')
        
        # Check AMI backup
        if not skip_backup:
            backup_status = check_ami_backup_status(instance_id)
            
            if backup_status['success'] and not backup_status.get('has_recent_backup', False):
                log_action('terminate_instance', {'instance_id': instance_id}, 
                          'requires_confirmation', {'reason': 'no_recent_backup'})
                return {
                    'success': False,
                    'requires_confirmation': True,
                    'backup_status': backup_status,
                    'message': 'No recent AMI backup. Create AMI first or confirm to proceed.',
                    'recommendation': f"Run: 'Create AMI backup for {instance_id}'"
                }
        
        # Require confirmation
        if not confirmation_token:
            token = generate_confirmation_token('terminate_instance', {'instance_id': instance_id})
            log_action('terminate_instance', {'instance_id': instance_id}, 'requires_confirmation')
            
            return {
                'success': False,
                'requires_confirmation': True,
                'confirmation_token': token,
                'instance_details': {
                    'instance_id': instance_id,
                    'name': instance_name,
                    'type': instance['InstanceType'],
                    'state': instance['State']['Name']
                },
                'message': f"⚠️ DESTRUCTIVE: Terminating {instance_name}. Token: {token}"
            }
        
        # Verify token
        token_verify = verify_confirmation_token(confirmation_token)
        if not token_verify['valid']:
            return {'success': False, 'error': token_verify['error']}
        
        # Terminate
        response = ec2_client.terminate_instances(InstanceIds=[instance_id])
        current_state = response['TerminatingInstances'][0]['CurrentState']['Name']
        
        log_action('terminate_instance', {'instance_id': instance_id}, 'success')
        
        return {
            'success': True,
            'instance_id': instance_id,
            'instance_name': instance_name,
            'state': current_state,
            'message': f"Instance {instance_id} termination initiated"
        }
    
    except ClientError as e:
        log_action('terminate_instance', {'instance_id': instance_id}, 'failed', error=str(e))
        return {'success': False, 'error': str(e)}

def stop_ec2_instance(instance_id):
    """Stop instance"""
    try:
        response = ec2_client.stop_instances(InstanceIds=[instance_id])
        current_state = response['StoppingInstances'][0]['CurrentState']['Name']
        
        log_action('stop_instance', {'instance_id': instance_id}, 'success')
        
        return {
            'success': True,
            'instance_id': instance_id,
            'state': current_state,
            'message': f"Instance {instance_id} stopping"
        }
    
    except ClientError as e:
        log_action('stop_instance', {'instance_id': instance_id}, 'failed', error=str(e))
        return {'success': False, 'error': str(e)}

def start_ec2_instance(instance_id):
    """Start instance"""
    try:
        response = ec2_client.start_instances(InstanceIds=[instance_id])
        current_state = response['StartingInstances'][0]['CurrentState']['Name']
        
        log_action('start_instance', {'instance_id': instance_id}, 'success')
        
        return {
            'success': True,
            'instance_id': instance_id,
            'state': current_state,
            'message': f"Instance {instance_id} starting"
        }
    
    except ClientError as e:
        log_action('start_instance', {'instance_id': instance_id}, 'failed', error=str(e))
        return {'success': False, 'error': str(e)}

def change_instance_type(instance_id, new_instance_type, confirmation_token=None, create_backup=True):
    """Change instance type with AMI backup"""
    try:
        budget_check = check_budget_limits(new_instance_type)
        if not budget_check['allowed']:
            return {'success': False, 'error': budget_check['reason'], 'details': budget_check}
        
        response = ec2_client.describe_instances(InstanceIds=[instance_id])
        instance = response['Reservations'][0]['Instances'][0]
        current_state = instance['State']['Name']
        current_type = instance['InstanceType']
        
        if current_state != 'stopped':
            return {
                'success': False,
                'error': f"Instance must be stopped. Current: {current_state}"
            }
        
        # Create AMI backup
        if create_backup:
            backup_result = create_ami_backup(
                instance_id,
                description=f"Pre-resize backup: {current_type} to {new_instance_type}"
            )
            
            if not backup_result['success']:
                return {
                    'success': False,
                    'error': 'Failed to create AMI backup',
                    'backup_error': backup_result.get('error')
                }
        
        # Require confirmation
        if not confirmation_token:
            token = generate_confirmation_token('change_instance_type', 
                                               {'instance_id': instance_id, 'new_type': new_instance_type})
            
            cost_diff = budget_check['monthly_cost'] - (INSTANCE_PRICING.get(current_type, 0) * 730)
            
            return {
                'success': False,
                'requires_confirmation': True,
                'confirmation_token': token,
                'change_details': {
                    'current_type': current_type,
                    'new_type': new_instance_type,
                    'cost_impact': f"${abs(cost_diff):.2f}/month {'increase' if cost_diff > 0 else 'decrease'}"
                },
                'backup_created': create_backup,
                'message': f"Confirm resize. Token: {token}"
            }
        
        # Verify token
        token_verify = verify_confirmation_token(confirmation_token)
        if not token_verify['valid']:
            return {'success': False, 'error': token_verify['error']}
        
        # Modify
        ec2_client.modify_instance_attribute(
            InstanceId=instance_id,
            InstanceType={'Value': new_instance_type}
        )
        
        log_action('change_instance_type', 
                  {'instance_id': instance_id, 'old_type': current_type, 'new_type': new_instance_type}, 
                  'success')
        
        return {
            'success': True,
            'instance_id': instance_id,
            'old_type': current_type,
            'new_type': new_instance_type,
            'cost_estimate': budget_check,
            'message': f"Type changed: {current_type} → {new_instance_type}"
        }
    
    except ClientError as e:
        log_action('change_instance_type', {'instance_id': instance_id}, 'failed', error=str(e))
        return {'success': False, 'error': str(e)}

# =====================================================
# EBS VOLUME OPERATIONS (SIMPLIFIED)
# =====================================================

def list_ebs_volumes(instance_id=None):
    """List EBS volumes"""
    try:
        params = {}
        if instance_id:
            params['Filters'] = [{'Name': 'attachment.instance-id', 'Values': [instance_id]}]
        
        response = ec2_client.describe_volumes(**params)
        
        volumes = []
        for volume in response['Volumes']:
            volume_info = {
                'VolumeId': volume['VolumeId'],
                'Size': volume['Size'],
                'VolumeType': volume['VolumeType'],
                'State': volume['State'],
                'Attachments': [
                    {'InstanceId': att['InstanceId'], 'Device': att['Device']}
                    for att in volume.get('Attachments', [])
                ]
            }
            volumes.append(volume_info)
        
        return {'success': True, 'volumes': volumes, 'count': len(volumes)}
    
    except ClientError as e:
        return {'success': False, 'error': str(e)}

def create_ebs_volume(size, volume_type='gp3', availability_zone=None):
    """Create EBS volume"""
    try:
        if not availability_zone:
            azs = ec2_client.describe_availability_zones()
            availability_zone = azs['AvailabilityZones'][0]['ZoneName']
        
        response = ec2_client.create_volume(
            Size=size,
            VolumeType=volume_type,
            AvailabilityZone=availability_zone
        )
        
        log_action('create_volume', {'size': size, 'type': volume_type}, 'success', 
                  {'volume_id': response['VolumeId']})
        
        return {
            'success': True,
            'volume_id': response['VolumeId'],
            'size': response['Size'],
            'message': f"Volume {response['VolumeId']} created"
        }
    
    except ClientError as e:
        log_action('create_volume', {'size': size}, 'failed', error=str(e))
        return {'success': False, 'error': str(e)}

def attach_ebs_volume(volume_id, instance_id, device):
    """Attach volume"""
    try:
        response = ec2_client.attach_volume(
            VolumeId=volume_id,
            InstanceId=instance_id,
            Device=device
        )
        
        log_action('attach_volume', {'volume_id': volume_id, 'instance_id': instance_id}, 'success')
        
        return {
            'success': True,
            'volume_id': volume_id,
            'instance_id': instance_id,
            'device': device,
            'message': f"Volume attached"
        }
    
    except ClientError as e:
        log_action('attach_volume', {'volume_id': volume_id}, 'failed', error=str(e))
        return {'success': False, 'error': str(e)}

def detach_ebs_volume(volume_id):
    """Detach volume"""
    try:
        response = ec2_client.detach_volume(VolumeId=volume_id)
        
        log_action('detach_volume', {'volume_id': volume_id}, 'success')
        
        return {
            'success': True,
            'volume_id': volume_id,
            'message': f"Volume {volume_id} detached"
        }
    
    except ClientError as e:
        log_action('detach_volume', {'volume_id': volume_id}, 'failed', error=str(e))
        return {'success': False, 'error': str(e)}

def delete_ebs_volume(volume_id, confirmation_token=None):
    """Delete volume"""
    try:
        response = ec2_client.describe_volumes(VolumeIds=[volume_id])
        volume = response['Volumes'][0]
        
        if volume['Attachments']:
            return {'success': False, 'error': f"Volume attached. Detach first."}
        
        if not confirmation_token:
            token = generate_confirmation_token('delete_volume', {'volume_id': volume_id})
            log_action('delete_volume', {'volume_id': volume_id}, 'requires_confirmation')
            
            return {
                'success': False,
                'requires_confirmation': True,
                'confirmation_token': token,
                'message': f"⚠️ Confirm deletion. Token: {token}"
            }
        
        token_verify = verify_confirmation_token(confirmation_token)
        if not token_verify['valid']:
            return {'success': False, 'error': token_verify['error']}
        
        ec2_client.delete_volume(VolumeId=volume_id)
        
        log_action('delete_volume', {'volume_id': volume_id}, 'success')
        
        return {
            'success': True,
            'volume_id': volume_id,
            'message': f"Volume {volume_id} deleted"
        }
    
    except ClientError as e:
        log_action('delete_volume', {'volume_id': volume_id}, 'failed', error=str(e))
        return {'success': False, 'error': str(e)}

# =====================================================
# AI PROCESSING
# =====================================================

def query_bedrock(user_query, context):
    """Query Bedrock AI"""
    system_prompt = """You are an AWS EC2 management assistant with safety features.

Key capabilities:
- EC2 instance management (launch, stop, start, terminate, resize)
- AMI backups (server-level, not volume snapshots)
- CloudWatch alarms creation
- EBS volume operations
- Action logging and audit trail

Safety rules:
1. Always check for AMI backups before destructive actions
2. Explain confirmation tokens clearly
3. Provide cost estimates
4. Recommend CloudWatch alarms for monitoring
5. Log all actions in DynamoDB

When suggesting actions:
- Be specific about instance IDs
- Include cost implications
- Mention backup status
- Explain confirmation process
- Suggest monitoring/alarms
"""
    
    user_message = f"""Context: {context}

User Request: {user_query}

Provide helpful guidance."""

    try:
        request_body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 2000,
            "temperature": 0.7,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_message}]
        }
        
        response = bedrock_runtime.invoke_model(
            modelId=MODEL_ID,
            body=json.dumps(request_body)
        )
        
        response_body = json.loads(response['body'].read())
        return response_body['content'][0]['text']
        
    except ClientError as e:
        return "Sorry, couldn't process request."

def process_ec2_action(action, parameters):
    """Execute actions"""
    action = action.lower()
    
    if action == 'list_instances':
        return list_ec2_instances()
    elif action == 'launch_instance':
        return launch_ec2_instance(**parameters)
    elif action == 'terminate_instance':
        return terminate_ec2_instance(**parameters)
    elif action == 'start_instance':
        return start_ec2_instance(parameters.get('instance_id'))
    elif action == 'stop_instance':
        return stop_ec2_instance(parameters.get('instance_id'))
    elif action == 'change_instance_type':
        return change_instance_type(**parameters)
    elif action == 'check_ami_backup':
        return check_ami_backup_status(parameters.get('instance_id'))
    elif action == 'create_ami_backup':
        return create_ami_backup(**parameters)
    elif action == 'list_amis':
        return list_instance_amis(parameters.get('instance_id'))
    elif action == 'create_cpu_alarm':
        return create_cpu_alarm(**parameters)
    elif action == 'create_status_alarm':
        return create_status_check_alarm(**parameters)
    elif action == 'list_alarms':
        return list_instance_alarms(parameters.get('instance_id'))
    elif action == 'delete_alarm':
        return delete_alarm(parameters.get('alarm_name'))
    elif action == 'list_volumes':
        return list_ebs_volumes(parameters.get('instance_id'))
    elif action == 'create_volume':
        return create_ebs_volume(**parameters)
    elif action == 'attach_volume':
        return attach_ebs_volume(**parameters)
    elif action == 'detach_volume':
        return detach_ebs_volume(parameters.get('volume_id'))
    elif action == 'delete_volume':
        return delete_ebs_volume(**parameters)
    elif action == 'get_action_logs':
        return get_action_logs(limit=parameters.get('limit', 50))
    else:
        return {'success': False, 'error': f'Unknown action: {action}'}

def parse_user_intent(user_query):
    """Parse intent using AI"""
    parsing_prompt = f"""Parse this EC2 request and extract action and parameters.

Available actions:
- list_instances, launch_instance, terminate_instance, start_instance, stop_instance, change_instance_type
- check_ami_backup, create_ami_backup, list_amis
- create_cpu_alarm, create_status_alarm, list_alarms, delete_alarm
- list_volumes, create_volume, attach_volume, detach_volume, delete_volume
- get_action_logs

User Query: {user_query}

Return ONLY JSON: {{"action": "...", "parameters": {{...}}}}
"""
    
    try:
        request_body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 500,
            "temperature": 0,
            "messages": [{"role": "user", "content": parsing_prompt}]
        }
        
        response = bedrock_runtime.invoke_model(
            modelId=MODEL_ID,
            body=json.dumps(request_body)
        )
        
        response_body = json.loads(response['body'].read())
        response_text = response_body['content'][0]['text'].strip()
        
        if response_text.startswith('```json'):
            response_text = response_text[7:]
        if response_text.endswith('```'):
            response_text = response_text[:-3]
        
        return json.loads(response_text.strip())
        
    except Exception as e:
        print(f"Error parsing intent: {e}")
        return {'action': 'help', 'parameters': {}}

def process_user_query(user_query):
    """Process user query"""
    query_lower = user_query.lower()
    
    action_keywords = ['launch', 'terminate', 'stop', 'start', 'delete', 'create', 
                       'attach', 'detach', 'change', 'backup', 'alarm', 'ami', 'log']
    is_action = any(keyword in query_lower for keyword in action_keywords)
    
    if is_action:
        intent = parse_user_intent(user_query)
        action = intent.get('action', 'help')
        parameters = intent.get('parameters', {})
        
        action_result = process_ec2_action(action, parameters)
        
        if not action_result.get('success', False) and action_result.get('requires_confirmation', False):
            return json.dumps(action_result, indent=2)
        
        context = f"Action: {action}\nResult: {json.dumps(action_result, indent=2)}"
        response = query_bedrock(user_query, context)
        return response
    
    else:
        context = ""
        
        if any(word in query_lower for word in ['instance', 'instances', 'ec2']):
            instances = list_ec2_instances()
            context += f"\n=== INSTANCES ===\n{json.dumps(instances, indent=2)}"
        
        if any(word in query_lower for word in ['alarm', 'monitor']):
            instances_result = list_ec2_instances()
            if instances_result['success']:
                for inst in instances_result['instances'][:3]:
                    alarms = list_instance_alarms(inst['InstanceId'])
                    context += f"\n=== ALARMS {inst['InstanceId']} ===\n{json.dumps(alarms, indent=2)}"
        
        if any(word in query_lower for word in ['log', 'history', 'action']):
            logs = get_action_logs(limit=20)
            context += f"\n=== ACTION LOGS ===\n{json.dumps(logs, indent=2)}"
        
        if any(word in query_lower for word in ['backup', 'ami']):
            instances_result = list_ec2_instances()
            if instances_result['success']:
                for inst in instances_result['instances'][:3]:
                    amis = list_instance_amis(inst['InstanceId'])
                    context += f"\n=== AMIs {inst['InstanceId']} ===\n{json.dumps(amis, indent=2)}"
        
        if not context:
            instances = list_ec2_instances()
            context = f"=== INSTANCES ===\n{json.dumps(instances, indent=2)}"
        
        response = query_bedrock(user_query, context)
        return response

# =====================================================
# LAMBDA HANDLER
# =====================================================

def lambda_handler(event, context):
    """Lambda handler with DynamoDB logging and user email tracking"""
    print(f"Event: {json.dumps(event)}")
    
    try:
        if 'body' in event:
            body = json.loads(event['body']) if isinstance(event['body'], str) else event['body']
        else:
            body = event
        
        user_query = body.get('query', '')
        user_email = body.get('email', 'anonymous')  # Get user email from request
        
        if not user_query:
            return {
                'statusCode': 400,
                'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
                'body': json.dumps({'error': 'No query provided'})
            }
        
        print(f"Processing: {user_query} from user: {user_email}")
        
        # Store user email in context for logging
        os.environ['CURRENT_USER_EMAIL'] = user_email
        
        response_text = process_user_query(user_query)
        
        return {
            'statusCode': 200,
            'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
            'body': json.dumps({
                'query': user_query,
                'response': response_text,
                'timestamp': datetime.now().isoformat(),
                'model': MODEL_ID,
                'user_email': user_email
            })
        }
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        
        return {
            'statusCode': 500,
            'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
            'body': json.dumps({'error': str(e)})
        }