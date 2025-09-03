#!/bin/bash

# AWS NoSQL Workshop - Infrastructure Deployment Script
# This script deploys the complete CloudFormation stack and validates all resources

set -e

# Configuration
PROJECT_NAME="unicorn-ecommerce"
ENVIRONMENT="dev"
STACK_NAME="${PROJECT_NAME}-${ENVIRONMENT}-stack"
TEMPLATE_FILE="infrastructure/cloudformation-template-basic.yaml"
REGION=${AWS_DEFAULT_REGION:-us-east-1}
S3_BUCKET_PREFIX="${PROJECT_NAME}-${ENVIRONMENT}-templates"
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text 2>/dev/null || echo "unknown")

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging function
log() {
    echo -e "${BLUE}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1"
}

success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check prerequisites
check_prerequisites() {
    log "Checking prerequisites..."
    
    # Check AWS CLI
    if ! command -v aws &> /dev/null; then
        error "AWS CLI is not installed. Please install it first."
        exit 1
    fi
    
    # Check AWS credentials
    if ! aws sts get-caller-identity &> /dev/null; then
        error "AWS credentials not configured. Please run 'aws configure' first."
        exit 1
    fi
    
    # Check CloudFormation template exists
    if [ ! -f "$TEMPLATE_FILE" ]; then
        error "CloudFormation template not found at $TEMPLATE_FILE"
        exit 1
    fi
    
    success "Prerequisites check passed"
}

# Create S3 bucket for templates
create_template_bucket() {
    local bucket_name="${S3_BUCKET_PREFIX}-${ACCOUNT_ID}"
    
    echo "Creating S3 bucket for CloudFormation templates: $bucket_name"
    
    # Check if bucket exists
    if aws s3api head-bucket --bucket $bucket_name --region $REGION 2>/dev/null; then
        echo "S3 bucket $bucket_name already exists"
    else
        # Create bucket
        if [ "$REGION" = "us-east-1" ]; then
            aws s3api create-bucket --bucket $bucket_name --region $REGION
        else
            aws s3api create-bucket --bucket $bucket_name --region $REGION --create-bucket-configuration LocationConstraint=$REGION
        fi
        echo "S3 bucket $bucket_name created"
    fi
    
    # Enable versioning
    aws s3api put-bucket-versioning --bucket $bucket_name --versioning-configuration Status=Enabled
    
    echo $bucket_name
}

# Upload nested templates to S3
upload_templates() {
    local bucket_name=$1
    
    echo "Uploading nested templates to S3..."
    
    # Upload infrastructure template
    aws s3 cp infrastructure/infrastructure-template.yaml s3://$bucket_name/infrastructure-template.yaml --region $REGION
    echo "Uploaded infrastructure-template.yaml"
    
    # Upload EC2 host template
    aws s3 cp infrastructure/ec2host-template.yaml s3://$bucket_name/ec2host-template.yaml --region $REGION
    echo "Uploaded ec2host-template.yaml"
    
    # Create modified main template with S3 URLs
    local temp_main_template="/tmp/main-template-modified.yaml"
    sed "s|TemplateURL: ./infrastructure-template.yaml|TemplateURL: https://s3.amazonaws.com/$bucket_name/infrastructure-template.yaml|g" $TEMPLATE_FILE > $temp_main_template
    sed -i '' "s|TemplateURL: ./ec2host-template.yaml|TemplateURL: https://s3.amazonaws.com/$bucket_name/ec2host-template.yaml|g" $temp_main_template
    
    # Upload modified main template
    aws s3 cp $temp_main_template s3://$bucket_name/main-template.yaml --region $REGION
    echo "Uploaded modified main-template.yaml"
    
    echo $temp_main_template
}

# Validate CloudFormation template
validate_template() {
    log "Validating CloudFormation template..."
    
    if aws cloudformation validate-template --template-body file://$TEMPLATE_FILE --region $REGION > /dev/null; then
        success "CloudFormation template is valid"
    else
        error "CloudFormation template validation failed"
        exit 1
    fi
}

# Deploy CloudFormation stack
deploy_stack() {
    local template_file=$1
    
    log "Deploying CloudFormation stack: $STACK_NAME"
    
    # Check if stack exists
    if aws cloudformation describe-stacks --stack-name $STACK_NAME --region $REGION &> /dev/null; then
        log "Stack exists, updating..."
        OPERATION="update-stack"
    else
        log "Stack doesn't exist, creating..."
        OPERATION="create-stack"
    fi
    
    # Deploy stack
    aws cloudformation $OPERATION \
        --stack-name $STACK_NAME \
        --template-body file://$template_file \
        --parameters \
            ParameterKey=ProjectName,ParameterValue=$PROJECT_NAME \
            ParameterKey=Environment,ParameterValue=$ENVIRONMENT \
        --capabilities CAPABILITY_NAMED_IAM CAPABILITY_AUTO_EXPAND \
        --region $REGION \
        --tags \
            Key=Project,Value=$PROJECT_NAME \
            Key=Environment,Value=$ENVIRONMENT \
            Key=ManagedBy,Value=CloudFormation
    
    log "Waiting for stack deployment to complete..."
    
    if [ "$OPERATION" = "create-stack" ]; then
        aws cloudformation wait stack-create-complete --stack-name $STACK_NAME --region $REGION
    else
        aws cloudformation wait stack-update-complete --stack-name $STACK_NAME --region $REGION
    fi
    
    success "Stack deployment completed successfully"
}

# Get stack outputs
get_stack_outputs() {
    log "Retrieving stack outputs..."
    
    aws cloudformation describe-stacks \
        --stack-name $STACK_NAME \
        --region $REGION \
        --query 'Stacks[0].Outputs' \
        --output table
}

# Validate DynamoDB tables
validate_dynamodb() {
    log "Validating DynamoDB tables..."
    
    local tables=(
        "${PROJECT_NAME}-${ENVIRONMENT}-users"
        "${PROJECT_NAME}-${ENVIRONMENT}-shopping-cart"
        "${PROJECT_NAME}-${ENVIRONMENT}-inventory"
        "${PROJECT_NAME}-${ENVIRONMENT}-orders"
        "${PROJECT_NAME}-${ENVIRONMENT}-chat-history"
        "${PROJECT_NAME}-${ENVIRONMENT}-search-analytics"
    )
    
    for table in "${tables[@]}"; do
        if aws dynamodb describe-table --table-name $table --region $REGION &> /dev/null; then
            local status=$(aws dynamodb describe-table --table-name $table --region $REGION --query 'Table.TableStatus' --output text)
            if [ "$status" = "ACTIVE" ]; then
                success "DynamoDB table $table is active"
            else
                warning "DynamoDB table $table status: $status"
            fi
        else
            error "DynamoDB table $table not found"
        fi
    done
}

# Validate DocumentDB cluster
validate_documentdb() {
    log "Validating DocumentDB cluster..."
    
    local cluster_id="${PROJECT_NAME}-${ENVIRONMENT}-docdb-cluster"
    
    if aws docdb describe-db-clusters --db-cluster-identifier $cluster_id --region $REGION &> /dev/null; then
        local status=$(aws docdb describe-db-clusters --db-cluster-identifier $cluster_id --region $REGION --query 'DBClusters[0].Status' --output text)
        if [ "$status" = "available" ]; then
            success "DocumentDB cluster $cluster_id is available"
        else
            warning "DocumentDB cluster $cluster_id status: $status"
        fi
    else
        error "DocumentDB cluster $cluster_id not found"
    fi
}

# Validate ElastiCache
validate_elasticache() {
    log "Validating ElastiCache serverless cache..."
    
    local cache_name="${PROJECT_NAME}-${ENVIRONMENT}-cache"
    
    if aws elasticache describe-serverless-caches --serverless-cache-name $cache_name --region $REGION &> /dev/null; then
        local status=$(aws elasticache describe-serverless-caches --serverless-cache-name $cache_name --region $REGION --query 'ServerlessCaches[0].Status' --output text)
        if [ "$status" = "available" ]; then
            success "ElastiCache serverless cache $cache_name is available"
        else
            warning "ElastiCache serverless cache $cache_name status: $status"
        fi
    else
        error "ElastiCache serverless cache $cache_name not found"
    fi
}

# Validate Cognito User Pool
validate_cognito() {
    log "Validating Cognito User Pool..."
    
    local user_pool_name="${PROJECT_NAME}-${ENVIRONMENT}-users"
    
    local user_pool_id=$(aws cognito-idp list-user-pools --max-items 50 --region $REGION --query "UserPools[?Name=='$user_pool_name'].Id" --output text)
    
    if [ -n "$user_pool_id" ] && [ "$user_pool_id" != "None" ]; then
        success "Cognito User Pool $user_pool_name found with ID: $user_pool_id"
    else
        error "Cognito User Pool $user_pool_name not found"
    fi
}

# Validate S3 bucket
validate_s3() {
    log "Validating S3 bucket..."
    
    local bucket_name="${PROJECT_NAME}-${ENVIRONMENT}-website-$(aws sts get-caller-identity --query Account --output text)"
    
    if aws s3api head-bucket --bucket $bucket_name --region $REGION 2>/dev/null; then
        success "S3 bucket $bucket_name exists and is accessible"
    else
        error "S3 bucket $bucket_name not found or not accessible"
    fi
}

# Validate CloudFront distribution
validate_cloudfront() {
    log "Validating CloudFront distribution..."
    
    # Get distribution ID from stack outputs
    local distribution_id=$(aws cloudformation describe-stacks \
        --stack-name $STACK_NAME \
        --region $REGION \
        --query 'Stacks[0].Outputs[?OutputKey==`CloudFrontDistributionId`].OutputValue' \
        --output text)
    
    if [ -n "$distribution_id" ] && [ "$distribution_id" != "None" ]; then
        local status=$(aws cloudfront get-distribution --id $distribution_id --query 'Distribution.Status' --output text)
        if [ "$status" = "Deployed" ]; then
            success "CloudFront distribution $distribution_id is deployed"
        else
            warning "CloudFront distribution $distribution_id status: $status"
        fi
    else
        error "CloudFront distribution not found in stack outputs"
    fi
}

# Validate API Gateway
validate_api_gateway() {
    log "Validating API Gateway..."
    
    local api_name="${PROJECT_NAME}-${ENVIRONMENT}-api"
    
    local api_id=$(aws apigateway get-rest-apis --region $REGION --query "items[?name=='$api_name'].id" --output text)
    
    if [ -n "$api_id" ] && [ "$api_id" != "None" ]; then
        success "API Gateway $api_name found with ID: $api_id"
        
        # Test API Gateway endpoint
        local api_url="https://${api_id}.execute-api.${REGION}.amazonaws.com/${ENVIRONMENT}"
        log "API Gateway endpoint: $api_url"
    else
        error "API Gateway $api_name not found"
    fi
}

# Run connectivity tests
run_connectivity_tests() {
    log "Running connectivity tests..."
    
    # Test VPC connectivity (this would require Lambda functions to be deployed)
    warning "Connectivity tests require Lambda functions to be deployed first"
    warning "These tests will be performed after Lambda deployment"
}

# Run smoke tests
run_smoke_tests() {
    log "Running smoke tests..."
    
    # Basic AWS service connectivity tests
    log "Testing AWS service connectivity..."
    
    # Test DynamoDB connectivity
    if aws dynamodb list-tables --region $REGION &> /dev/null; then
        success "DynamoDB service connectivity: OK"
    else
        error "DynamoDB service connectivity: FAILED"
    fi
    
    # Test DocumentDB connectivity (requires VPC access)
    warning "DocumentDB connectivity test requires VPC access - skipping for now"
    
    # Test ElastiCache connectivity (requires VPC access)
    warning "ElastiCache connectivity test requires VPC access - skipping for now"
    
    # Test S3 connectivity
    if aws s3 ls --region $REGION &> /dev/null; then
        success "S3 service connectivity: OK"
    else
        error "S3 service connectivity: FAILED"
    fi
    
    # Test CloudFront connectivity
    if aws cloudfront list-distributions &> /dev/null; then
        success "CloudFront service connectivity: OK"
    else
        error "CloudFront service connectivity: FAILED"
    fi
}

# Generate deployment summary
generate_summary() {
    log "Generating deployment summary..."
    
    echo ""
    echo "=========================================="
    echo "  DEPLOYMENT SUMMARY"
    echo "=========================================="
    echo "Project: $PROJECT_NAME"
    echo "Environment: $ENVIRONMENT"
    echo "Region: $REGION"
    echo "Stack Name: $STACK_NAME"
    echo ""
    
    # Get key outputs
    local outputs=$(aws cloudformation describe-stacks \
        --stack-name $STACK_NAME \
        --region $REGION \
        --query 'Stacks[0].Outputs[?OutputKey==`WebsiteURL` || OutputKey==`ApiGatewayURL` || OutputKey==`CloudFrontDistributionDomainName`].[OutputKey,OutputValue]' \
        --output text)
    
    echo "Key Endpoints:"
    echo "$outputs" | while read key value; do
        echo "  $key: $value"
    done
    
    echo ""
    echo "Next Steps:"
    echo "1. Deploy Lambda functions"
    echo "2. Seed sample data"
    echo "3. Deploy frontend application"
    echo "4. Run end-to-end tests"
    echo ""
}

# Main execution
main() {
    log "Starting AWS NoSQL Workshop infrastructure deployment..."
    
    check_prerequisites
    validate_template
    deploy_stack $TEMPLATE_FILE
    get_stack_outputs
    
    log "Validating deployed resources..."
    validate_dynamodb
    validate_documentdb
    validate_elasticache
    validate_cognito
    validate_s3
    validate_cloudfront
    validate_api_gateway
    
    run_connectivity_tests
    run_smoke_tests
    generate_summary
    
    success "Infrastructure deployment and validation completed!"
}

# Run main function
main "$@"