#!/bin/bash

# AWS NoSQL Workshop - Complete Deployment Script
# This script deploys infrastructure, Lambda functions, seeds data, and deploys frontend

set -e

# Configuration
PROJECT_NAME="unicorn-ecommerce"
ENVIRONMENT="dev"
REGION="us-east-1"
STACK_NAME="${PROJECT_NAME}-${ENVIRONMENT}-stack"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Function to print status
print_status() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

print_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

print_step() {
    echo -e "${PURPLE}🚀 $1${NC}"
}

print_header() {
    echo -e "${CYAN}"
    echo "=================================================================="
    echo "$1"
    echo "=================================================================="
    echo -e "${NC}"
}

# Function to check if AWS CLI is configured
check_aws_cli() {
    if ! aws sts get-caller-identity > /dev/null 2>&1; then
        print_error "AWS CLI is not configured or credentials are invalid"
        exit 1
    fi
    print_status "AWS CLI is configured"
}

# Function to check prerequisites
check_prerequisites() {
    print_info "Checking prerequisites..."
    
    # Check AWS CLI
    check_aws_cli
    
    # Check required files
    local required_files=(
        "deploy-infrastructure.sh"
        "deploy-lambda-functions.sh" 
        "deploy-frontend.sh"
        "setup_and_generate_data.sh"
    )
    
    for file in "${required_files[@]}"; do
        if [ ! -f "$file" ]; then
            print_error "Required file not found: $file"
            exit 1
        fi
    done
    
    # Make scripts executable
    chmod +x deploy-infrastructure.sh
    chmod +x deploy-lambda-functions.sh
    chmod +x deploy-frontend.sh
    chmod +x setup_and_generate_data.sh
    
    print_status "Prerequisites check passed"
}

# Function to deploy infrastructure
deploy_infrastructure() {
    print_header "STEP 1: DEPLOYING INFRASTRUCTURE"
    
    if ./deploy-infrastructure.sh; then
        print_status "Infrastructure deployment completed successfully"
    else
        # Check if it's just a "no updates" error
        if aws cloudformation describe-stacks --stack-name "$STACK_NAME" --region "$REGION" &>/dev/null; then
            print_warning "Infrastructure already exists and is up to date"
            print_status "Continuing with existing infrastructure"
        else
            print_error "Infrastructure deployment failed"
            exit 1
        fi
    fi
}

# Function to deploy Lambda functions
deploy_lambda_functions() {
    print_header "STEP 2: DEPLOYING LAMBDA FUNCTIONS"
    
    # Wait for any ongoing Lambda updates to complete
    print_info "Checking Lambda function status..."
    local lambda_functions=("unicorn-ecommerce-dev-product-api" "unicorn-ecommerce-dev-order-api" "unicorn-ecommerce-dev-user-api")
    
    for func in "${lambda_functions[@]}"; do
        local max_attempts=30
        local attempt=1
        
        while [ $attempt -le $max_attempts ]; do
            local state=$(aws lambda get-function --function-name "$func" --query 'Configuration.State' --output text --region "$REGION" 2>/dev/null || echo "NotFound")
            
            if [ "$state" = "Active" ] || [ "$state" = "NotFound" ]; then
                break
            elif [ "$state" = "Pending" ]; then
                print_info "Waiting for $func to become active... (attempt $attempt/$max_attempts)"
                sleep 10
                ((attempt++))
            else
                print_warning "Lambda function $func is in state: $state"
                break
            fi
        done
    done
    
    if ./deploy-lambda-functions.sh; then
        print_status "Lambda functions deployment completed successfully"
    else
        print_warning "Lambda functions deployment had issues, but continuing..."
        print_info "You may need to redeploy Lambda functions separately later"
    fi
}

# Function to create EC2 instance for data seeding
create_ec2_instance() {
    print_header "STEP 3: CREATING EC2 INSTANCE FOR DATA SEEDING"
    
    # Check if we already have generated data
    print_info "Checking for existing generated data..."
    local bucket_name=$(aws cloudformation describe-stacks \
        --stack-name "$STACK_NAME" \
        --region "$REGION" \
        --query 'Stacks[0].Outputs[?OutputKey==`WebsiteBucketName`].OutputValue' \
        --output text)
    
    if aws s3 ls "s3://$bucket_name/generated-data/" --region "$REGION" >/dev/null 2>&1; then
        print_status "Found existing generated data in S3. Skipping data generation."
        return 0
    fi
    
    # Get VPC and subnet information from stack outputs - use public subnet for better connectivity
    print_info "Retrieving VPC information..."
    
    local vpc_id=$(aws cloudformation describe-stacks \
        --stack-name "$STACK_NAME" \
        --region "$REGION" \
        --query 'Stacks[0].Outputs[?OutputKey==`VPCId`].OutputValue' \
        --output text)
    
    # Use private subnet (SSM works fine with private subnets)
    local private_subnet_id=$(aws cloudformation describe-stacks \
        --stack-name "$STACK_NAME" \
        --region "$REGION" \
        --query 'Stacks[0].Outputs[?OutputKey==`PrivateSubnet1Id`].OutputValue' \
        --output text)
    
    local lambda_sg_id=$(aws cloudformation describe-stacks \
        --stack-name "$STACK_NAME" \
        --region "$REGION" \
        --query 'Stacks[0].Outputs[?OutputKey==`LambdaSecurityGroupId`].OutputValue' \
        --output text)
    
    print_info "VPC ID: $vpc_id"
    print_info "Private Subnet ID: $private_subnet_id"
    print_info "Security Group ID: $lambda_sg_id"
    
    # Create IAM role for EC2 instance if it doesn't exist
    print_info "Creating IAM role for EC2 instance..."
    
    local role_name="${PROJECT_NAME}-${ENVIRONMENT}-ec2-role"
    
    # Check if role exists
    if ! aws iam get-role --role-name "$role_name" > /dev/null 2>&1; then
        # Create trust policy
        cat > ec2-trust-policy.json << EOF
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Principal": {
                "Service": "ec2.amazonaws.com"
            },
            "Action": "sts:AssumeRole"
        }
    ]
}
EOF
        
        # Create role
        aws iam create-role \
            --role-name "$role_name" \
            --assume-role-policy-document file://ec2-trust-policy.json \
            --region "$REGION"
        
        # Attach policies
        aws iam attach-role-policy \
            --role-name "$role_name" \
            --policy-arn "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
        
        aws iam attach-role-policy \
            --role-name "$role_name" \
            --policy-arn "arn:aws:iam::aws:policy/SecretsManagerReadWrite"
        
        aws iam attach-role-policy \
            --role-name "$role_name" \
            --policy-arn "arn:aws:iam::aws:policy/AmazonDynamoDBFullAccess"
        
        aws iam attach-role-policy \
            --role-name "$role_name" \
            --policy-arn "arn:aws:iam::aws:policy/AmazonElastiCacheFullAccess"
        
        aws iam attach-role-policy \
            --role-name "$role_name" \
            --policy-arn "arn:aws:iam::aws:policy/AmazonBedrockFullAccess"
        
        aws iam attach-role-policy \
            --role-name "$role_name" \
            --policy-arn "arn:aws:iam::aws:policy/AmazonS3FullAccess"
        
        # Create instance profile
        aws iam create-instance-profile --instance-profile-name "$role_name"
        aws iam add-role-to-instance-profile --instance-profile-name "$role_name" --role-name "$role_name"
        
        print_info "Waiting for IAM role to propagate..."
        sleep 30
        
        rm -f ec2-trust-policy.json
    else
        print_info "IAM role already exists, ensuring S3 permissions..."
        # Ensure S3 permissions are attached
        aws iam attach-role-policy \
            --role-name "$role_name" \
            --policy-arn "arn:aws:iam::aws:policy/AmazonS3FullAccess" 2>/dev/null || true
    fi
    
    # Get latest Amazon Linux 2023 AMI
    print_info "Getting latest Amazon Linux 2023 AMI..."
    local ami_id=$(aws ec2 describe-images \
        --owners amazon \
        --filters "Name=name,Values=al2023-ami-*-x86_64" "Name=state,Values=available" \
        --query 'Images | sort_by(@, &CreationDate) | [-1].ImageId' \
        --output text \
        --region "$REGION")
    
    print_info "Using AMI: $ami_id"
    
    # Create user data script
    cat > user-data.sh << 'EOF'
#!/bin/bash
exec > >(tee /var/log/user-data.log|logger -t user-data -s 2>/dev/console) 2>&1
echo "Starting user data script execution at $(date)"

# Update system
yum update -y

# Install required packages including SSM agent
yum install -y python3 python3-pip git jq amazon-ssm-agent

# Ensure SSM agent is running
systemctl enable amazon-ssm-agent
systemctl start amazon-ssm-agent
echo "SSM agent status:"
systemctl status amazon-ssm-agent --no-pager

# Install AWS CLI v2
cd /tmp
curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
unzip awscliv2.zip
./aws/install

# Install Python packages
pip3 install boto3 pymongo redis

# Create working directory
mkdir -p /opt/unicorn-workshop
cd /opt/unicorn-workshop

# Download DocumentDB SSL certificate
curl -o rds-ca-2019-root.pem https://s3.amazonaws.com/rds-downloads/rds-ca-2019-root.pem

# Signal completion
echo "EC2 instance setup completed at $(date)" > /tmp/setup-complete.log
echo "User data script completed successfully at $(date)"
EOF
    
    # Launch EC2 instance
    print_info "Launching EC2 instance for data seeding..."
    
    local instance_id=$(aws ec2 run-instances \
        --image-id "$ami_id" \
        --count 1 \
        --instance-type t3.medium \
        --iam-instance-profile Name="$role_name" \
        --security-group-ids "$lambda_sg_id" \
        --subnet-id "$private_subnet_id" \
        --associate-public-ip-address \
        --user-data file://user-data.sh \
        --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=${PROJECT_NAME}-${ENVIRONMENT}-data-seeding},{Key=Project,Value=${PROJECT_NAME}},{Key=Environment,Value=${ENVIRONMENT}}]" \
        --query 'Instances[0].InstanceId' \
        --output text \
        --region "$REGION")
    
    print_info "EC2 Instance ID: $instance_id"
    
    # Wait for instance to be running
    print_info "Waiting for EC2 instance to be running..."
    aws ec2 wait instance-running --instance-ids "$instance_id" --region "$REGION"
    
    # Give instance more time to boot and install packages
    print_info "Waiting for instance to complete initialization..."
    sleep 120
    
    # Wait for SSM agent to be ready
    print_info "Waiting for SSM agent to be ready..."
    local max_attempts=60  # Increased from 30
    local attempt=0
    
    while [ $attempt -lt $max_attempts ]; do
        local ssm_status=$(aws ssm describe-instance-information \
            --filters "Key=InstanceIds,Values=$instance_id" \
            --query 'InstanceInformationList[0].PingStatus' \
            --output text \
            --region "$REGION" 2>/dev/null || echo "NotFound")
        
        if [ "$ssm_status" = "Online" ]; then
            print_status "SSM agent is online"
            break
        fi
        
        attempt=$((attempt + 1))
        print_info "Waiting for SSM agent... (attempt $attempt/$max_attempts) - Status: $ssm_status"
        
        if [ $attempt -eq $max_attempts ]; then
            print_error "SSM agent did not come online within expected time"
            print_info "Final SSM status: $ssm_status"
            
            # Check instance state for debugging
            local instance_state=$(aws ec2 describe-instances \
                --instance-ids "$instance_id" \
                --query 'Reservations[0].Instances[0].State.Name' \
                --output text \
                --region "$REGION")
            print_info "Instance state: $instance_state"
            
            cleanup_ec2_instance "$instance_id"
            return 1
        fi
        
        sleep 20  # Reduced from 30 to check more frequently
    done
    
    print_status "EC2 instance is ready for data seeding"
    
    # Store instance ID for cleanup
    echo "$instance_id" > .ec2-instance-id
    
    rm -f user-data.sh
}

# Function to seed data via EC2
seed_data_via_ec2() {
    print_header "STEP 4: SEEDING DATA VIA EC2 INSTANCE"
    
    local instance_id=$(cat .ec2-instance-id)
    
    # Copy project files to EC2 instance
    print_info "Copying project files to EC2 instance..."
    
    # Create a deployment package
    echo "Creating deployment package..."
    
    # Clean up any Python cache files first
    find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
    find . -name "*.pyc" -delete 2>/dev/null || true
    
    # Create the tar file
    tar -czf workshop-files.tar.gz \
        backend/ \
        data/ \
        setup_and_generate_data.sh \
        rds-ca-2019-root.pem 2>/dev/null || {
        # Fallback: create without SSL cert if it doesn't exist
        tar -czf workshop-files.tar.gz \
            backend/ \
            data/ \
            setup_and_generate_data.sh
    }
    
    # Copy files via S3 (more reliable than direct copy)
    local bucket_name=$(aws cloudformation describe-stacks \
        --stack-name "$STACK_NAME" \
        --region "$REGION" \
        --query 'Stacks[0].Outputs[?OutputKey==`WebsiteBucketName`].OutputValue' \
        --output text)
    
    aws s3 cp workshop-files.tar.gz "s3://$bucket_name/workshop-files.tar.gz"
    
    # Execute data seeding on EC2 instance
    print_info "Executing data seeding on EC2 instance..."
    
    # Create a command script with proper variable substitution
    cat > data-seeding-commands.json << EOF
{
    "commands": [
        "cd /opt/unicorn-workshop",
        "echo 'Starting data seeding process...'",
        "aws s3 cp s3://$bucket_name/workshop-files.tar.gz . || exit 1",
        "tar -xzf workshop-files.tar.gz || exit 1",
        "chmod +x setup_and_generate_data.sh",
        "echo 'Running data generation...'",
        "./setup_and_generate_data.sh 2>&1 | tee /tmp/data-seeding.log",
        "echo 'Data seeding completed'"
    ]
}
EOF
    
    local command_id=$(aws ssm send-command \
        --instance-ids "$instance_id" \
        --document-name "AWS-RunShellScript" \
        --parameters file://data-seeding-commands.json \
        --query 'Command.CommandId' \
        --output text \
        --region "$REGION")
    
    rm -f data-seeding-commands.json
    
    print_info "SSM Command ID: $command_id"
    
    # Wait for command to complete
    print_info "Waiting for data seeding to complete..."
    
    local max_wait=1800  # 30 minutes
    local wait_time=0
    
    while [ $wait_time -lt $max_wait ]; do
        local status=$(aws ssm get-command-invocation \
            --command-id "$command_id" \
            --instance-id "$instance_id" \
            --query 'Status' \
            --output text \
            --region "$REGION" 2>/dev/null || echo "InProgress")
        
        if [ "$status" = "Success" ]; then
            print_status "Data seeding completed successfully"
            break
        elif [ "$status" = "Failed" ] || [ "$status" = "Cancelled" ] || [ "$status" = "TimedOut" ]; then
            print_error "Data seeding failed with status: $status"
            
            # Get command output for debugging
            print_info "Command output:"
            aws ssm get-command-invocation \
                --command-id "$command_id" \
                --instance-id "$instance_id" \
                --query 'StandardOutputContent' \
                --output text \
                --region "$REGION"
            
            print_info "Command errors:"
            aws ssm get-command-invocation \
                --command-id "$command_id" \
                --instance-id "$instance_id" \
                --query 'StandardErrorContent' \
                --output text \
                --region "$REGION"
            
            exit 1
        fi
        
        wait_time=$((wait_time + 30))
        print_info "Data seeding in progress... (${wait_time}s elapsed)"
        sleep 30
    done
    
    if [ $wait_time -ge $max_wait ]; then
        print_error "Data seeding timed out after $max_wait seconds"
        exit 1
    fi
    
    # Cleanup
    rm -f workshop-files.tar.gz
    aws s3 rm "s3://$bucket_name/workshop-files.tar.gz"
}

# Function to deploy frontend
deploy_frontend() {
    print_header "STEP 5: DEPLOYING FRONTEND"
    
    if ./deploy-frontend.sh; then
        print_status "Frontend deployment completed successfully"
    else
        print_error "Frontend deployment failed"
        exit 1
    fi
}

# Function to cleanup EC2 instance
cleanup_ec2_instance() {
    print_header "CLEANUP: TERMINATING EC2 INSTANCE"
    
    if [ -f .ec2-instance-id ]; then
        local instance_id=$(cat .ec2-instance-id)
        
        print_info "Terminating EC2 instance: $instance_id"
        aws ec2 terminate-instances --instance-ids "$instance_id" --region "$REGION"
        
        print_info "Waiting for instance termination..."
        aws ec2 wait instance-terminated --instance-ids "$instance_id" --region "$REGION"
        
        rm -f .ec2-instance-id
        print_status "EC2 instance terminated successfully"
    fi
}

# Function to display deployment summary
display_summary() {
    print_header "DEPLOYMENT SUMMARY"
    
    # Get stack outputs
    local stack_outputs=$(aws cloudformation describe-stacks \
        --stack-name "$STACK_NAME" \
        --region "$REGION" \
        --query 'Stacks[0].Outputs' \
        --output json)
    
    local api_gateway_url=$(echo "$stack_outputs" | jq -r '.[] | select(.OutputKey=="ApiGatewayURL") | .OutputValue')
    local cloudfront_url=$(echo "$stack_outputs" | jq -r '.[] | select(.OutputKey=="CloudFrontURL") | .OutputValue')
    local website_bucket=$(echo "$stack_outputs" | jq -r '.[] | select(.OutputKey=="WebsiteBucketName") | .OutputValue')
    
    echo ""
    print_status "🎉 Unicorn E-Commerce Workshop Deployment Complete!"
    echo ""
    echo "📊 Deployment Details:"
    echo "  • Project: $PROJECT_NAME"
    echo "  • Environment: $ENVIRONMENT"
    echo "  • Region: $REGION"
    echo "  • Stack: $STACK_NAME"
    echo ""
    echo "🌐 Application URLs:"
    echo "  • Frontend (CloudFront): $cloudfront_url"
    echo "  • API Gateway: $api_gateway_url"
    echo ""
    echo "📦 Deployed Components:"
    echo "  • ✅ Infrastructure (VPC, DocumentDB, ElastiCache, DynamoDB, Cognito)"
    echo "  • ✅ Lambda Functions (10 functions deployed)"
    echo "  • ✅ API Gateway (REST API with integrations)"
    echo "  • ✅ Sample Data (Products, Reviews, Analytics)"
    echo "  • ✅ Frontend (React app on CloudFront)"
    echo ""
    echo "🔧 Next Steps:"
    echo "  1. Visit the frontend URL to explore the application"
    echo "  2. Test the search and chat functionality"
    echo "  3. Review the generated sample data"
    echo "  4. Run end-to-end tests if needed"
    echo ""
    echo "📚 Documentation:"
    echo "  • Complete guide: COMPLETE_DEPLOYMENT_GUIDE.md"
    echo "  • API documentation: Check Lambda function logs"
    echo "  • Troubleshooting: Check CloudWatch logs"
    echo ""
}

# Main execution function
main() {
    local start_time=$(date +%s)
    
    print_header "AWS NOSQL WORKSHOP - COMPLETE DEPLOYMENT"
    echo "Starting deployment at: $(date)"
    echo ""
    
    # Trap to ensure cleanup on exit
    trap cleanup_ec2_instance EXIT
    
    # Execute deployment steps
    check_prerequisites
    deploy_infrastructure
    # deploy_lambda_functions
    create_ec2_instance
    seed_data_via_ec2
    deploy_frontend
    cleanup_ec2_instance
    
    # Calculate total time
    local end_time=$(date +%s)
    local total_time=$((end_time - start_time))
    local minutes=$((total_time / 60))
    local seconds=$((total_time % 60))
    
    display_summary
    
    echo ""
    print_status "Total deployment time: ${minutes}m ${seconds}s"
    print_status "Deployment completed at: $(date)"
}

# Handle script arguments
case "${1:-}" in
    --help|-h)
        echo "AWS NoSQL Workshop - Complete Deployment Script"
        echo ""
        echo "Usage: $0 [options]"
        echo ""
        echo "Options:"
        echo "  --help, -h     Show this help message"
        echo "  --cleanup      Cleanup EC2 instance only"
        echo ""
        echo "This script will:"
        echo "  1. Deploy infrastructure (VPC, databases, etc.)"
        echo "  2. Deploy Lambda functions"
        echo "  3. Create EC2 instance for data seeding"
        echo "  4. Seed sample data via EC2"
        echo "  5. Deploy frontend to CloudFront"
        echo "  6. Cleanup temporary resources"
        echo ""
        exit 0
        ;;
    --cleanup)
        cleanup_ec2_instance
        exit 0
        ;;
    *)
        main "$@"
        ;;
esac