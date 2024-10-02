import boto3
import os
import zipfile
import time

# AWS Configuration
REGION = 'ap-northeast-2'
BUCKET_NAME = 'monitorbeluga'
LAUNCH_CONFIG_NAME = 'EagleEyeLaunchConfig'
ASG_NAME = 'EagleEyeASG'
LOAD_BALANCER_NAME = 'EagleEyeELB'
TARGET_GROUP_NAME = 'EagleEyeTG'
SNS_TOPICS = {
    'health_issues': 'EagleEyeHealthIssues',
    'scaling_events': 'EagleEyeScalingEvents',
    'high_traffic': 'EagleEyeHighTraffic'
}
LAMBDA_NOTIFICATION_NAME = 'EagleEyeNotificationHandler'
LAMBDA_FILE_MOVER_NAME = 'EagleEyeFileMover'
IAM_ROLE_ARN = 'arn:aws:iam::123456789012:role/YourLambdaExecutionRole'
KEY_NAME = 'Gani_reborne'

# Initialize clients
s3 = boto3.client('s3', region_name=REGION)
ec2 = boto3.resource('ec2', region_name=REGION)
asg = boto3.client('autoscaling', region_name=REGION)
elbv2 = boto3.client('elbv2', region_name=REGION)
sns = boto3.client('sns', region_name=REGION)
lambda_client = boto3.client('lambda', region_name=REGION)

# Utility function to write and zip lambda function code
def write_and_zip_lambda(name, code):
    with open(f'{name}.py', 'w') as f:
        f.write(code)
    with zipfile.ZipFile(f'{name}.zip', 'w') as z:
        z.write(f'{name}.py')
    os.remove(f'{name}.py')

# Function to create an S3 bucket
def create_bucket(bucket_name):
    try:
        res = s3.create_bucket(
            Bucket=bucket_name,
            CreateBucketConfiguration={'LocationConstraint': REGION}
        )
        print("Bucket created:", res)
        return res
    except Exception as e:
        print("Error creating bucket:", e)

# Function to upload files to S3 bucket
def upload_folders(bucket_name, folder_path):
    for root, dirs, files in os.walk(folder_path):
        for file in files:
            s3.upload_file(os.path.join(root, file), bucket_name, file)
            print("Uploaded:", file)

# Function to create an EC2 instance
def create_ec2_instance():
    instance = ec2.create_instances(
        ImageId='ami-062cf18d655c0b1e8',
        MinCount=1,
        MaxCount=1,
        InstanceType='t2.micro',
        KeyName=KEY_NAME,
        TagSpecifications=[
            {'ResourceType': 'instance', 'Tags': [{'Key': 'Name', 'Value': 'EagleEye'}]}
        ],
        UserData='''#!/bin/bash
                    sudo apt update -y
                    sudo apt install nginx -y
                    service nginx start
                    mkdir -p /var/www/uploads
                    crontab -l | { cat; echo "* * * * * aws s3 sync /var/www/uploads s3://monitorbeluga/uploads"; } | crontab -
                    aws s3 cp s3://monitorbeluga /var/www/html --recursive
'''
    )
    instance[0].wait_until_running()
    instance[0].reload()
    print("EC2 Instance created:", instance[0].id)
    return instance[0]

# Function to create a launch configuration
def create_launch_configuration():
    try:
        response = asg.create_launch_configuration(
            LaunchConfigurationName=LAUNCH_CONFIG_NAME,
            ImageId='ami-062cf18d655c0b1e8',
            InstanceType='t2.micro',
            KeyName=KEY_NAME,
            SecurityGroups=['default']
        )
        print("Launch Configuration created:", response)
        return response
    except asg.exceptions.AlreadyExistsFault:
        print(f"Launch Configuration {LAUNCH_CONFIG_NAME} already exists.")
        return None

# Function to create an Auto Scaling Group (ASG)
def create_auto_scaling_group():
    create_launch_configuration()
    try:
        response = asg.create_auto_scaling_group(
            AutoScalingGroupName=ASG_NAME,
            LaunchConfigurationName=LAUNCH_CONFIG_NAME,
            MinSize=1,
            MaxSize=3,
            DesiredCapacity=1,
            DefaultCooldown=300,
            AvailabilityZones=['ap-northeast-2a', 'ap-northeast-2b'],
            Tags=[{'Key': 'Name', 'Value': 'EagleEye', 'PropagateAtLaunch': True}]
        )
        print("Auto Scaling Group created:", response)
        sns_topic_arn = create_sns_topic(SNS_TOPICS['scaling_events'])
        asg.put_notification_configuration(
            AutoScalingGroupName=ASG_NAME,
            TopicARN=sns_topic_arn,
            NotificationTypes=['autoscaling:EC2_INSTANCE_LAUNCH', 'autoscaling:EC2_INSTANCE_TERMINATE']
        )
        print("Notification configuration added.")
        return response
    except Exception as e:
        print("Error creating Auto Scaling Group:", e)

# Function to create a target group
def create_target_group(vpc_id):
    response = elbv2.create_target_group(
        Name=TARGET_GROUP_NAME,
        Protocol='HTTP',
        Port=80,
        VpcId=vpc_id,
        HealthCheckProtocol='HTTP',
        HealthCheckPort='80',
        HealthCheckEnabled=True,
        HealthCheckPath='/',
        HealthCheckIntervalSeconds=30,
        HealthCheckTimeoutSeconds=5,
        HealthyThresholdCount=5,
        UnhealthyThresholdCount=2,
        TargetType='instance'
    )
    target_group_arn = response['TargetGroups'][0]['TargetGroupArn']
    print("Target Group created:", target_group_arn)
    return target_group_arn

# Function to create a load balancer and attach it to the target group
def attach_load_balancer(target_group_arn):
    client = boto3.client('ec2', region_name=REGION)

    # Fetch subnets in the specified availability zones
    specified_subnets = client.describe_subnets(
        Filters=[
            {'Name': 'availability-zone', 'Values': ['ap-northeast-2a', 'ap-northeast-2b']}
        ]
    )['Subnets']

    if len(specified_subnets) < 2:
        raise ValueError("At least two subnets are required in the specified availability zones.")

    subnets = [subnet['SubnetId'] for subnet in specified_subnets[:2]]

    response = elbv2.create_load_balancer(
        Name=LOAD_BALANCER_NAME,
        Scheme='internet-facing',
        Subnets=subnets,
        Tags=[{'Key': 'Name', 'Value': 'EagleEye'}]
    )
    load_balancer_arn = response['LoadBalancers'][0]['LoadBalancerArn']
    listener = elbv2.create_listener(
        LoadBalancerArn=load_balancer_arn,
        Protocol='HTTP',
        Port=80,
        DefaultActions=[{'Type': 'forward', 'TargetGroupArn': target_group_arn}]
    )
    print("Load Balancer created and listener attached:", load_balancer_arn)
    return load_balancer_arn

# Function to register targets to the target group
def register_targets(target_group_arn, instance_id):
    response = elbv2.register_targets(
        TargetGroupArn=target_group_arn,
        Targets=[{'Id': instance_id, 'Port': 80}]
    )
    print("Instance registered to Target Group:", response)
    return response

# Function to create an SNS topic
def create_sns_topic(name):
    response = sns.create_topic(Name=name)
    print("SNS Topic created:", response['TopicArn'])
    return response['TopicArn']

# Function to create a Lambda function
def create_lambda_function(name, zip_file, handler):
    try:
        with open(zip_file, 'rb') as f:
            code = f.read()
        response = lambda_client.create_function(
            FunctionName=name,
            Runtime='python3.8',
            Role=IAM_ROLE_ARN,
            Handler=handler,
            Code={'ZipFile': code},
            Description=f'Lambda function for {name}',
            Timeout=60,
            MemorySize=128,
            Publish=True
        )
        print("Lambda Function created:", response['FunctionArn'])
        return response['FunctionArn']
    except Exception as e:
        print(f"Error creating Lambda function {name}:", e)

# Function to subscribe Lambda to SNS topic
def subscribe_lambda_to_sns(topic_arn, lambda_arn):
    response = sns.subscribe(
        TopicArn=topic_arn,
        Protocol='lambda',
        Endpoint=lambda_arn
    )
    print("Lambda subscribed to SNS Topic:", response)
    return response

# Lambda function code for handling notifications
lambda_notification_code = '''
import json
import boto3

def lambda_handler(event, context):
    sns_message = event['Records'][0]['Sns']['Message']
    print("Received SNS message:", sns_message)
    
    # Initialize the SNS client
    sns_client = boto3.client('sns')
    
    # Define the recipient's phone number
    recipient_phone_number = '<RecipientPhoneNumber>'  # Replace with actual phone number
    
    # Logic to handle different types of notifications
    if 'health issue' in sns_message:
        # Handle health issue notification
        sns_client.publish(
            PhoneNumber=recipient_phone_number,
            Message=f"Health Issue Alert: {sns_message}"
        )
    elif 'scaling event' in sns_message:
        # Handle scaling event notification
        sns_client.publish(
            PhoneNumber=recipient_phone_number,
            Message=f"Scaling Event Alert: {sns_message}"
        )
    elif 'high traffic' in sns_message:
        # Handle high traffic notification
        sns_client.publish(
            PhoneNumber=recipient_phone_number,
            Message=f"High Traffic Alert: {sns_message}"
        )
    else:
        # Handle general notifications
        sns_client.publish(
            PhoneNumber=recipient_phone_number,
            Message=f"General Alert: {sns_message}"
        )
'''

# Lambda function code for moving files from EC2 to S3
lambda_file_mover_code = '''
import os
import boto3

s3 = boto3.client('s3')

def lambda_handler(event, context):
    bucket_name = 'monitorbeluga'
    source_directory = '/var/www/uploads'
    for filename in os.listdir(source_directory):
        local_path = os.path.join(source_directory, filename)
        if os.path.isfile(local_path):
            s3.upload_file(local_path, bucket_name, f'uploads/{filename}')
            os.remove(local_path)
    print("Files moved to S3")
'''

# Write and zip Lambda function code
write_and_zip_lambda('lambda_function', lambda_notification_code)
write_and_zip_lambda('file_mover', lambda_file_mover_code)

# Function to deploy the infrastructure
def deploy_infrastructure():
    create_bucket(BUCKET_NAME)
    upload_folders(BUCKET_NAME, 'C:/Users/eagleye/Desktop/FOCUS/Samplefiles')
    instance = create_ec2_instance()
    
    vpc_id = list(ec2.vpcs.all())[0].id
    target_group_arn = create_target_group(vpc_id)
    load_balancer_arn = attach_load_balancer(target_group_arn)
    register_targets(target_group_arn, instance.id)
    
    create_auto_scaling_group()
    
    # Create SNS topics and subscribe Lambda functions
    for topic_name in SNS_TOPICS.values():
        topic_arn = create_sns_topic(topic_name)
        lambda_name = LAMBDA_NOTIFICATION_NAME if 'notification' in topic_name.lower() else LAMBDA_FILE_MOVER_NAME
        lambda_arn = create_lambda_function(
            lambda_name,
            'lambda_function.zip' if 'notification' in topic_name.lower() else 'file_mover.zip',
            'lambda_function.lambda_handler' if 'notification' in topic_name.lower() else 'file_mover.lambda_handler'
        )
        subscribe_lambda_to_sns(topic_arn, lambda_arn)

# Function to update the infrastructure
def update_infrastructure():
    # Implement update logic as needed
    pass

# Function to tear down the infrastructure
def tear_down_infrastructure():
    try:
        asg.delete_auto_scaling_group(AutoScalingGroupName=ASG_NAME, ForceDelete=True)
        print("Auto Scaling Group deleted.")
    except Exception as e:
        print("Error deleting Auto Scaling Group:", e)
    
    try:
        load_balancers = elbv2.describe_load_balancers(Names=[LOAD_BALANCER_NAME])['LoadBalancers']
        if load_balancers:
            elbv2.delete_load_balancer(LoadBalancerArn=load_balancers[0]['LoadBalancerArn'])
            print("Load Balancer deleted.")
    except Exception as e:
        print("Error deleting Load Balancer:", e)
    
    try:
        target_groups = elbv2.describe_target_groups(Names=[TARGET_GROUP_NAME])['TargetGroups']
        if target_groups:
            elbv2.delete_target_group(TargetGroupArn=target_groups[0]['TargetGroupArn'])
            print("Target Group deleted.")
    except Exception as e:
        print("Error deleting Target Group:", e)
    
    try:
        s3.delete_bucket(Bucket=BUCKET_NAME)
        print("S3 Bucket deleted.")
    except Exception as e:
        print("Error deleting S3 Bucket:", e)
    
    try:
        lambda_client.delete_function(FunctionName=LAMBDA_NOTIFICATION_NAME)
        print("Lambda Notification Function deleted.")
    except Exception as e:
        print("Error deleting Lambda Notification Function:", e)
    
    try:
        lambda_client.delete_function(FunctionName=LAMBDA_FILE_MOVER_NAME)
        print("Lambda File Mover Function deleted.")
    except Exception as e:
        print("Error deleting Lambda File Mover Function:", e)
    
    for topic_name in SNS_TOPICS.values():
        try:
            topic_arn = create_sns_topic(topic_name)
            sns.delete_topic(TopicArn=topic_arn)
            print(f"SNS Topic {topic_name} deleted.")
        except Exception as e:
            print(f"Error deleting SNS Topic {topic_name}:", e)

if __name__ == "__main__":
    action = input("Enter action (deploy/update/teardown): ").strip().lower()
    if action == "deploy":
        deploy_infrastructure()
    elif action == "update":
        update_infrastructure()
    elif action == "teardown":
        tear_down_infrastructure()
    else:
        print("Invalid action. Please enter deploy, update, or teardown.")
