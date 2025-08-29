#!/bin/bash

# AWS NoSQL Workshop - Lambda Functions Deployment Script
# This script deploys all Lambda functions for the Unicorn E-Commerce platform

set -e

# Configuration
PROJECT_NAME="unicorn-ecommerce"
ENVIRONMENT="dev"
REGION="us-east-1"
STACK_NAME=$1

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}AWS NoSQL Workshop - Lambda Functions Deployment${NC}"
echo "=================================================="
echo "Project: $PROJECT_NAME"
echo "Environment: $ENVIRONMENT"
echo "Region: $REGION"
echo "Stack: $STACK_NAME"
echo ""

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

# Check if AWS CLI is configured
if ! aws sts get-caller-identity > /dev/null 2>&1; then
    print_error "AWS CLI is not configured or credentials are invalid"
    exit 1
fi

print_status "AWS CLI is configured"

# Get stack outputs
print_info "Retrieving stack outputs..."
STACK_OUTPUTS=$(aws cloudformation describe-stacks \
    --stack-name "$STACK_NAME" \
    --region "$REGION" \
    --query 'Stacks[0].Outputs' \
    --output json)

if [ $? -ne 0 ]; then
    print_error "Failed to retrieve stack outputs. Make sure the infrastructure is deployed."
    exit 1
fi

# Extract required values from stack outputs
LAMBDA_EXECUTION_ROLE_ARN=$(echo "$STACK_OUTPUTS" | jq -r '.[] | select(.OutputKey=="LambdaExecutionRoleArn") | .OutputValue')
LAMBDA_SECURITY_GROUP_ID=$(echo "$STACK_OUTPUTS" | jq -r '.[] | select(.OutputKey=="LambdaSecurityGroupId") | .OutputValue')
PRIVATE_SUBNET_1_ID=$(echo "$STACK_OUTPUTS" | jq -r '.[] | select(.OutputKey=="PrivateSubnet1Id") | .OutputValue')
PRIVATE_SUBNET_2_ID=$(echo "$STACK_OUTPUTS" | jq -r '.[] | select(.OutputKey=="PrivateSubnet2Id") | .OutputValue')
API_GATEWAY_ID=$(echo "$STACK_OUTPUTS" | jq -r '.[] | select(.OutputKey=="ApiGatewayId") | .OutputValue')

print_info "Lambda Execution Role ARN: $LAMBDA_EXECUTION_ROLE_ARN"
print_info "Lambda Security Group ID: $LAMBDA_SECURITY_GROUP_ID"
print_info "Private Subnet 1 ID: $PRIVATE_SUBNET_1_ID"
print_info "Private Subnet 2 ID: $PRIVATE_SUBNET_2_ID"
print_info "API Gateway ID: $API_GATEWAY_ID"

# Create deployment package function
create_deployment_package() {
    local function_name=$1
    local function_file=$2
    
    print_info "Creating deployment package for $function_name..." >&2
    
    # Check if function file exists
    if [ ! -f "backend/functions/$function_file" ]; then
        print_error "Function file backend/functions/$function_file not found" >&2
        return 1
    fi
    
    # Create temporary directory
    local temp_dir=$(mktemp -d)
    print_info "Using temporary directory: $temp_dir" >&2
    
    # Copy function code
    if ! cp "backend/functions/$function_file" "$temp_dir/lambda_function.py"; then
        print_error "Failed to copy function file: backend/functions/$function_file" >&2
        rm -rf "$temp_dir"
        return 1
    fi
    
    # Copy shared modules
    if [ -d "backend/shared" ]; then
        if ! cp -r backend/shared/* "$temp_dir/"; then
            print_error "Failed to copy shared modules" >&2
            rm -rf "$temp_dir"
            return 1
        fi
    fi
    
    # Skip pip installation for now - Lambda runtime has boto3 built-in
    # We'll create a minimal package with just our code
    print_info "Creating minimal deployment package (using Lambda runtime dependencies)..." >&2
    
    # Create a simple __init__.py if it doesn't exist
    touch "$temp_dir/__init__.py"
    
    # Create zip file
    local zip_file="${function_name}.zip"
    local current_dir=$(pwd)
    if (cd "$temp_dir" && zip -r "$current_dir/$zip_file" . > /dev/null 2>&1); then
        print_status "Created deployment package: $zip_file" >&2
    else
        print_error "Failed to create zip file for $function_name" >&2
        rm -rf "$temp_dir"
        return 1
    fi
    
    # Cleanup
    rm -rf "$temp_dir"
    
    echo "$zip_file"
}

# Deploy Lambda function
deploy_lambda_function() {
    local function_name=$1
    local function_file=$2
    local description=$3
    local timeout=${4:-30}
    local memory=${5:-256}
    
    print_info "Deploying Lambda function: $function_name"
    
    # Create deployment package
    local zip_file
    zip_file=$(create_deployment_package "$function_name" "$function_file")
    if [ $? -ne 0 ] || [ -z "$zip_file" ]; then
        print_error "Failed to create deployment package for $function_name"
        return 1
    fi
    
    if [ ! -f "$zip_file" ]; then
        print_error "Deployment package file $zip_file not found for $function_name"
        return 1
    fi
    
    # Check if function exists
    if aws lambda get-function --function-name "$function_name" --region "$REGION" > /dev/null 2>&1; then
        print_info "Function $function_name exists, updating..."
        
        # Update function code
        aws lambda update-function-code \
            --function-name "$function_name" \
            --zip-file "fileb://$zip_file" \
            --region "$REGION" > /dev/null
        
        # Update function configuration
        aws lambda update-function-configuration \
            --function-name "$function_name" \
            --timeout "$timeout" \
            --memory-size "$memory" \
            --region "$REGION" > /dev/null
            
    else
        print_info "Creating new function $function_name..."
        
        # Create function
        aws lambda create-function \
            --function-name "$function_name" \
            --runtime python3.9 \
            --role "$LAMBDA_EXECUTION_ROLE_ARN" \
            --handler lambda_function.lambda_handler \
            --zip-file "fileb://$zip_file" \
            --description "$description" \
            --timeout "$timeout" \
            --memory-size "$memory" \
            --vpc-config SubnetIds="$PRIVATE_SUBNET_1_ID,$PRIVATE_SUBNET_2_ID",SecurityGroupIds="$LAMBDA_SECURITY_GROUP_ID" \
            --environment Variables="{PROJECT_NAME=$PROJECT_NAME,ENVIRONMENT=$ENVIRONMENT,REGION=$REGION}" \
            --region "$REGION" > /dev/null
    fi
    
    # Wait for function to be active
    print_info "Waiting for function $function_name to be active..."
    aws lambda wait function-active --function-name "$function_name" --region "$REGION"
    
    # Cleanup zip file
    rm -f "$zip_file"
    
    print_status "Successfully deployed $function_name"
}

# Deploy all Lambda functions
print_info "Starting Lambda function deployment..."

# Core API functions
deploy_lambda_function "${PROJECT_NAME}-${ENVIRONMENT}-product-api" "product_api.py" "Product API for Unicorn E-Commerce" 30 512
deploy_lambda_function "${PROJECT_NAME}-${ENVIRONMENT}-cart-api" "cart_api.py" "Shopping Cart API for Unicorn E-Commerce" 30 256
deploy_lambda_function "${PROJECT_NAME}-${ENVIRONMENT}-order-api" "order_api.py" "Order Management API for Unicorn E-Commerce" 30 256
deploy_lambda_function "${PROJECT_NAME}-${ENVIRONMENT}-auth-api" "auth_api.py" "Authentication API for Unicorn E-Commerce" 30 256

# Review and Search functions
deploy_lambda_function "${PROJECT_NAME}-${ENVIRONMENT}-review-api" "review_api.py" "Review API for Unicorn E-Commerce" 30 512
deploy_lambda_function "${PROJECT_NAME}-${ENVIRONMENT}-review-analytics" "review_analytics.py" "Review Analytics API for Unicorn E-Commerce" 60 1024
deploy_lambda_function "${PROJECT_NAME}-${ENVIRONMENT}-search-api" "search_api.py" "Search API for Unicorn E-Commerce" 30 512
deploy_lambda_function "${PROJECT_NAME}-${ENVIRONMENT}-search-analytics" "search_analytics.py" "Search Analytics API for Unicorn E-Commerce" 30 256

# AI and Analytics functions
deploy_lambda_function "${PROJECT_NAME}-${ENVIRONMENT}-chat-api" "chat_api.py" "AI Chat API for Unicorn E-Commerce" 60 1024
deploy_lambda_function "${PROJECT_NAME}-${ENVIRONMENT}-analytics-api" "analytics_api.py" "Analytics API for Unicorn E-Commerce" 60 1024

print_status "All Lambda functions deployed successfully!"

# Create API Gateway integrations
print_info "Setting up API Gateway integrations..."

# Function to create API Gateway integration
create_api_integration() {
    local resource_path=$1
    local http_method=$2
    local function_name=$3
    
    print_info "Creating integration for $http_method $resource_path -> $function_name"
    
    # Get function ARN
    local function_arn=$(aws lambda get-function \
        --function-name "$function_name" \
        --region "$REGION" \
        --query 'Configuration.FunctionArn' \
        --output text)
    
    # Create resource if it doesn't exist
    local parent_id=$(aws apigateway get-resources \
        --rest-api-id "$API_GATEWAY_ID" \
        --region "$REGION" \
        --query 'items[?path==`/`].id' \
        --output text)
    
    # Create resource path
    local resource_id=$(aws apigateway create-resource \
        --rest-api-id "$API_GATEWAY_ID" \
        --parent-id "$parent_id" \
        --path-part "${resource_path#/}" \
        --region "$REGION" \
        --query 'id' \
        --output text 2>/dev/null || \
        aws apigateway get-resources \
        --rest-api-id "$API_GATEWAY_ID" \
        --region "$REGION" \
        --query "items[?path=='$resource_path'].id" \
        --output text)
    
    # Create method
    aws apigateway put-method \
        --rest-api-id "$API_GATEWAY_ID" \
        --resource-id "$resource_id" \
        --http-method "$http_method" \
        --authorization-type "NONE" \
        --region "$REGION" > /dev/null 2>&1 || true
    
    # Create integration
    aws apigateway put-integration \
        --rest-api-id "$API_GATEWAY_ID" \
        --resource-id "$resource_id" \
        --http-method "$http_method" \
        --type "AWS_PROXY" \
        --integration-http-method "POST" \
        --uri "arn:aws:apigateway:$REGION:lambda:path/2015-03-31/functions/$function_arn/invocations" \
        --region "$REGION" > /dev/null 2>&1 || true
    
    # Add Lambda permission
    aws lambda add-permission \
        --function-name "$function_name" \
        --statement-id "apigateway-invoke-$(date +%s)" \
        --action "lambda:InvokeFunction" \
        --principal "apigateway.amazonaws.com" \
        --source-arn "arn:aws:execute-api:$REGION:$(aws sts get-caller-identity --query Account --output text):$API_GATEWAY_ID/*/*" \
        --region "$REGION" > /dev/null 2>&1 || true
}

# Create API integrations
create_api_integration "/products" "GET" "${PROJECT_NAME}-${ENVIRONMENT}-product-api"
create_api_integration "/products" "POST" "${PROJECT_NAME}-${ENVIRONMENT}-product-api"
create_api_integration "/cart" "GET" "${PROJECT_NAME}-${ENVIRONMENT}-cart-api"
create_api_integration "/cart" "POST" "${PROJECT_NAME}-${ENVIRONMENT}-cart-api"
create_api_integration "/orders" "GET" "${PROJECT_NAME}-${ENVIRONMENT}-order-api"
create_api_integration "/orders" "POST" "${PROJECT_NAME}-${ENVIRONMENT}-order-api"
create_api_integration "/auth" "POST" "${PROJECT_NAME}-${ENVIRONMENT}-auth-api"
create_api_integration "/reviews" "GET" "${PROJECT_NAME}-${ENVIRONMENT}-review-api"
create_api_integration "/reviews" "POST" "${PROJECT_NAME}-${ENVIRONMENT}-review-api"
create_api_integration "/search" "GET" "${PROJECT_NAME}-${ENVIRONMENT}-search-api"
create_api_integration "/chat" "POST" "${PROJECT_NAME}-${ENVIRONMENT}-chat-api"
create_api_integration "/analytics" "GET" "${PROJECT_NAME}-${ENVIRONMENT}-analytics-api"

# Deploy API Gateway
print_info "Deploying API Gateway..."
aws apigateway create-deployment \
    --rest-api-id "$API_GATEWAY_ID" \
    --stage-name "$ENVIRONMENT" \
    --region "$REGION" > /dev/null

print_status "API Gateway integrations created successfully!"

# Display deployment summary
echo ""
echo -e "${GREEN}🎉 Lambda Functions Deployment Complete!${NC}"
echo "=================================================="
echo ""
echo "Deployed Functions:"
echo "- ${PROJECT_NAME}-${ENVIRONMENT}-product-api"
echo "- ${PROJECT_NAME}-${ENVIRONMENT}-cart-api"
echo "- ${PROJECT_NAME}-${ENVIRONMENT}-order-api"
echo "- ${PROJECT_NAME}-${ENVIRONMENT}-auth-api"
echo "- ${PROJECT_NAME}-${ENVIRONMENT}-review-api"
echo "- ${PROJECT_NAME}-${ENVIRONMENT}-review-analytics"
echo "- ${PROJECT_NAME}-${ENVIRONMENT}-search-api"
echo "- ${PROJECT_NAME}-${ENVIRONMENT}-search-analytics"
echo "- ${PROJECT_NAME}-${ENVIRONMENT}-chat-api"
echo "- ${PROJECT_NAME}-${ENVIRONMENT}-analytics-api"
echo ""
echo "API Gateway Endpoint:"
echo "https://$API_GATEWAY_ID.execute-api.$REGION.amazonaws.com/$ENVIRONMENT"
echo ""
echo "Next Steps:"
echo "1. Run data seeding: python3 data/generate_all_data.py"
echo "2. Deploy frontend: ./deploy-frontend.sh"
echo "3. Run end-to-end tests"
echo ""
