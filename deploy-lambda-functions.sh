#!/bin/bash

# AWS NoSQL Workshop - Lambda Functions Deployment Script
# This script deploys pre-packaged Lambda functions to AWS

set -e

# Configuration
PROJECT_NAME="unicorn-ecommerce"
ENVIRONMENT="dev"
REGION="us-east-1"

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

# Cleanup function for partial deployments
cleanup_partial_deployment() {
    local function_name=$1
    print_warning "Cleaning up partial deployment of $function_name..."
    
    # Delete the function if it exists but is in a failed state
    if aws lambda get-function --function-name "$function_name" --region "$REGION" > /dev/null 2>&1; then
        local state=$(aws lambda get-function \
            --function-name "$function_name" \
            --region "$REGION" \
            --query 'Configuration.State' \
            --output text 2>/dev/null || echo "Unknown")
        
        if [ "$state" = "Failed" ] || [ "$state" = "Inactive" ]; then
            print_info "Deleting failed function $function_name..."
            aws lambda delete-function \
                --function-name "$function_name" \
                --region "$REGION" > /dev/null 2>&1 || true
            print_status "Cleaned up $function_name"
        fi
    fi
}

# Check if packages directory exists
if [ ! -d "packages" ]; then
    print_error "Packages directory not found. Please run ./package-lambda-functions.sh first"
    exit 1
fi

# Check if deployment manifest exists
if [ ! -f "packages/deployment-manifest.json" ]; then
    print_error "Deployment manifest not found. Please run ./package-lambda-functions.sh first"
    exit 1
fi

# Get parameters from command line or environment
LAMBDA_EXECUTION_ROLE_ARN=${1:-$LAMBDA_EXECUTION_ROLE_ARN}
LAMBDA_SECURITY_GROUP_ID=${2:-$LAMBDA_SECURITY_GROUP_ID}
PRIVATE_SUBNET_1_ID=${3:-$PRIVATE_SUBNET_1_ID}
PRIVATE_SUBNET_2_ID=${4:-$PRIVATE_SUBNET_2_ID}
API_GATEWAY_ID=${5:-$API_GATEWAY_ID}

# Validate required parameters
if [ -z "$LAMBDA_EXECUTION_ROLE_ARN" ]; then
    print_error "Lambda Execution Role ARN is required (parameter 1 or LAMBDA_EXECUTION_ROLE_ARN env var)"
    exit 1
fi

if [ -z "$LAMBDA_SECURITY_GROUP_ID" ]; then
    print_error "Lambda Security Group ID is required (parameter 2 or LAMBDA_SECURITY_GROUP_ID env var)"
    exit 1
fi

if [ -z "$PRIVATE_SUBNET_1_ID" ]; then
    print_error "Private Subnet 1 ID is required (parameter 3 or PRIVATE_SUBNET_1_ID env var)"
    exit 1
fi

if [ -z "$PRIVATE_SUBNET_2_ID" ]; then
    print_error "Private Subnet 2 ID is required (parameter 4 or PRIVATE_SUBNET_2_ID env var)"
    exit 1
fi

if [ -z "$API_GATEWAY_ID" ]; then
    print_error "API Gateway ID is required (parameter 5 or API_GATEWAY_ID env var)"
    exit 1
fi

print_info "Lambda Execution Role ARN: $LAMBDA_EXECUTION_ROLE_ARN"
print_info "Lambda Security Group ID: $LAMBDA_SECURITY_GROUP_ID"
print_info "Private Subnet 1 ID: $PRIVATE_SUBNET_1_ID"
print_info "Private Subnet 2 ID: $PRIVATE_SUBNET_2_ID"
print_info "API Gateway ID: $API_GATEWAY_ID"

# Deploy Lambda function from package
deploy_lambda_function() {
    local function_name=$1
    
    print_info "Deploying Lambda function: $function_name"
    
    # Check if package exists
    local zip_file="packages/${function_name}.zip"
    local metadata_file="packages/${function_name}.json"
    
    if [ ! -f "$zip_file" ]; then
        print_error "Package file $zip_file not found for $function_name"
        return 1
    fi
    
    if [ ! -f "$metadata_file" ]; then
        print_error "Metadata file $metadata_file not found for $function_name"
        return 1
    fi
    
    # Read metadata
    local description=$(jq -r '.description' "$metadata_file")
    local timeout=$(jq -r '.timeout' "$metadata_file")
    local memory=$(jq -r '.memory' "$metadata_file")
    
    print_info "Description: $description"
    print_info "Timeout: ${timeout}s, Memory: ${memory}MB"
    
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
        
        # Clean up any partial deployment first
        cleanup_partial_deployment "$function_name"
        
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
    
    # Wait for function to be active with extended timeout for VPC functions
    print_info "Waiting for function $function_name to be active..."
    
    # For VPC functions, we need to wait longer for ENI creation
    local max_attempts=60  # 10 minutes (60 * 10 seconds)
    local attempt=0
    local wait_time=10
    
    while [ $attempt -lt $max_attempts ]; do
        local state=$(aws lambda get-function \
            --function-name "$function_name" \
            --region "$REGION" \
            --query 'Configuration.State' \
            --output text 2>/dev/null || echo "Pending")
        
        local last_update_status=$(aws lambda get-function \
            --function-name "$function_name" \
            --region "$REGION" \
            --query 'Configuration.LastUpdateStatus' \
            --output text 2>/dev/null || echo "InProgress")
        
        if [ "$state" = "Active" ] && [ "$last_update_status" = "Successful" ]; then
            print_status "Function $function_name is now active"
            break
        elif [ "$state" = "Failed" ] || [ "$last_update_status" = "Failed" ]; then
            print_error "Function $function_name deployment failed"
            
            # Get the failure reason
            local state_reason=$(aws lambda get-function \
                --function-name "$function_name" \
                --region "$REGION" \
                --query 'Configuration.StateReason' \
                --output text 2>/dev/null || echo "Unknown")
            
            print_error "Failure reason: $state_reason"
            return 1
        else
            attempt=$((attempt + 1))
            if [ $attempt -eq 1 ]; then
                print_warning "VPC Lambda deployment detected - this may take 5-10 minutes for ENI creation"
            fi
            
            # Progressive status updates
            if [ $((attempt % 6)) -eq 0 ]; then  # Every minute
                local elapsed=$((attempt * wait_time / 60))
                print_info "Still waiting... (${elapsed} minutes elapsed, state: $state, status: $last_update_status)"
            fi
            
            sleep $wait_time
        fi
    done
    
    if [ $attempt -eq $max_attempts ]; then
        print_error "Timeout waiting for function $function_name to become active"
        print_warning "This might be due to VPC ENI creation taking longer than expected"
        print_info "You can check the function status in the AWS Console and re-run this script"
        return 1
    fi
    
    # Additional check to ensure function is truly ready
    print_info "Verifying function $function_name is ready for invocation..."
    local invoke_test=$(aws lambda invoke \
        --function-name "$function_name" \
        --payload '{"httpMethod":"GET","path":"/health"}' \
        --region "$REGION" \
        /tmp/test-response.json 2>&1 || echo "failed")
    
    if [[ "$invoke_test" == *"failed"* ]] || [[ "$invoke_test" == *"error"* ]]; then
        print_warning "Function may not be fully ready yet, but continuing deployment..."
    else
        print_status "Function $function_name is ready for invocation"
    fi
    
    print_status "Successfully deployed $function_name"
}

# Check if this is the first VPC Lambda deployment
check_vpc_lambda_readiness() {
    print_info "Checking VPC readiness for Lambda deployments..."
    
    # Check if there are existing Lambda functions in the VPC
    local existing_vpc_functions=$(aws lambda list-functions \
        --region "$REGION" \
        --query "Functions[?VpcConfig.SubnetIds && contains(VpcConfig.SubnetIds, '$PRIVATE_SUBNET_1_ID')].FunctionName" \
        --output text 2>/dev/null || echo "")
    
    if [ -z "$existing_vpc_functions" ]; then
        print_warning "No existing VPC Lambda functions detected"
        print_warning "First VPC Lambda deployment may take 5-10 minutes for ENI creation"
        print_info "AWS needs to create Elastic Network Interfaces (ENIs) for VPC connectivity"
        
        # Ask user if they want to continue
        echo ""
        read -p "Continue with deployment? This may take longer than usual (y/N): " -n 1 -r
        echo ""
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            print_info "Deployment cancelled by user"
            exit 0
        fi
    else
        print_status "Existing VPC Lambda functions found - ENIs should already be available"
    fi
}

# Deploy all Lambda functions from manifest
print_info "Starting Lambda function deployment..."

# Check VPC readiness
check_vpc_lambda_readiness

# Read function list from manifest
functions=$(jq -r '.functions[]' packages/deployment-manifest.json)

# Deploy functions with error handling
failed_functions=()
successful_functions=()

for function_name in $functions; do
    if deploy_lambda_function "$function_name"; then
        successful_functions+=("$function_name")
    else
        failed_functions+=("$function_name")
        print_error "Failed to deploy $function_name"
    fi
done

# Report deployment results
echo ""
if [ ${#successful_functions[@]} -gt 0 ]; then
    print_status "Successfully deployed ${#successful_functions[@]} functions:"
    for func in "${successful_functions[@]}"; do
        echo "  ✅ $func"
    done
fi

if [ ${#failed_functions[@]} -gt 0 ]; then
    print_error "Failed to deploy ${#failed_functions[@]} functions:"
    for func in "${failed_functions[@]}"; do
        echo "  ❌ $func"
    done
    echo ""
    print_warning "Some functions failed to deploy. Common solutions:"
    echo "1. Wait 5-10 minutes and re-run the script (VPC ENI creation)"
    echo "2. Check AWS Console for detailed error messages"
    echo "3. Verify VPC configuration and security groups"
    echo "4. Ensure Lambda execution role has proper permissions"
    echo ""
    
    read -p "Do you want to retry failed deployments? (y/N): " -n 1 -r
    echo ""
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        print_info "Retrying failed deployments..."
        for function_name in "${failed_functions[@]}"; do
            print_info "Retrying deployment of $function_name..."
            if deploy_lambda_function "$function_name"; then
                print_status "Successfully deployed $function_name on retry"
            else
                print_error "Failed to deploy $function_name even on retry"
            fi
        done
    fi
fi

if [ ${#failed_functions[@]} -eq 0 ]; then
    print_status "All Lambda functions deployed successfully!"
else
    print_warning "Deployment completed with some failures"
    print_info "You can re-run this script to retry failed deployments"
fi

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
for function_name in $functions; do
    echo "- $function_name"
done
echo ""
echo "API Gateway Endpoint:"
echo "https://$API_GATEWAY_ID.execute-api.$REGION.amazonaws.com/$ENVIRONMENT"
echo ""
echo "Next Steps:"
echo "1. Run data seeding: python3 data/generate_all_data.py"
echo "2. Deploy frontend: ./deploy-frontend.sh"
echo "3. Run end-to-end tests"
echo ""