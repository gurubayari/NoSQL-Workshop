#!/bin/bash

# AWS NoSQL Workshop - API Gateway Setup Script
# This script creates API Gateway integrations and configures CORS
# Now with complete cleanup before setup

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

echo -e "${BLUE}AWS NoSQL Workshop - API Gateway Setup${NC}"
echo "============================================="
echo "Project: $PROJECT_NAME"
echo "Environment: $ENVIRONMENT"
echo "Region: $REGION"
echo ""

# Check for help flag
if [[ "$1" == "--help" ]] || [[ "$1" == "-h" ]]; then
    echo "Usage: $0 <api_gateway_id> [cloudfront_domain]"
    echo ""
    echo "Parameters:"
    echo "  api_gateway_id     - API Gateway REST API ID"
    echo "  cloudfront_domain  - (Optional) CloudFront domain for CORS origin"
    echo ""
    echo "This script will:"
    echo "  1. Clean up existing API Gateway methods and integrations"
    echo "  2. Create fresh API Gateway integrations for all endpoints"
    echo "  3. Configure CORS for cross-origin requests"
    echo "  4. Deploy API Gateway with new configuration"
    echo ""
    exit 0
fi

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

# Get parameters from command line or environment
API_GATEWAY_ID=${1:-$API_GATEWAY_ID}
CLOUDFRONT_DOMAIN=${2:-$CLOUDFRONT_DOMAIN}

# Validate required parameters
if [ -z "$API_GATEWAY_ID" ]; then
    print_error "API Gateway ID is required (parameter 1 or API_GATEWAY_ID env var)"
    print_info "Usage: $0 <api_gateway_id> [cloudfront_domain]"
    exit 1
fi

print_info "API Gateway ID: $API_GATEWAY_ID"

# Set CORS origin
if [ -z "$CLOUDFRONT_DOMAIN" ]; then
    print_warning "CloudFront domain not provided. Using wildcard (*) for CORS origin."
    CORS_ORIGIN="*"
else
    CORS_ORIGIN="https://$CLOUDFRONT_DOMAIN"
    print_info "CORS Origin: $CORS_ORIGIN"
fi

# Function to delete existing methods and integrations
delete_existing_methods() {
    local resource_id=$1
    local resource_path=$2
    
    print_info "Cleaning existing methods for $resource_path"
    
    # Delete each possible method
    for method in GET POST PUT DELETE OPTIONS; do
        if aws apigateway get-method \
            --rest-api-id "$API_GATEWAY_ID" \
            --resource-id "$resource_id" \
            --http-method "$method" \
            --region "$REGION" > /dev/null 2>&1; then
            
            print_info "Deleting method $method for $resource_path"
            aws apigateway delete-method \
                --rest-api-id "$API_GATEWAY_ID" \
                --resource-id "$resource_id" \
                --http-method "$method" \
                --region "$REGION" > /dev/null 2>&1
            
            if [ $? -eq 0 ]; then
                print_status "Deleted method $method for $resource_path"
            else
                print_warning "Failed to delete method $method for $resource_path"
            fi
        fi
    done
}

# Function to clean up Lambda permissions
cleanup_lambda_permissions() {
    local function_name=$1
    
    print_info "Cleaning up existing Lambda permissions for $function_name"
    
    # Get existing policy
    local policy=$(aws lambda get-policy \
        --function-name "$function_name" \
        --region "$REGION" \
        --query 'Policy' \
        --output text 2>/dev/null || echo "")
    
    if [ -n "$policy" ] && [ "$policy" != "None" ]; then
        # Extract statement IDs that contain "apigateway-invoke"
        local statement_ids=$(echo "$policy" | jq -r '.Statement[]? | select(.Sid | contains("apigateway-invoke")) | .Sid' 2>/dev/null || echo "")
        
        if [ -n "$statement_ids" ]; then
            while IFS= read -r statement_id; do
                if [ -n "$statement_id" ]; then
                    print_info "Removing permission: $statement_id"
                    aws lambda remove-permission \
                        --function-name "$function_name" \
                        --statement-id "$statement_id" \
                        --region "$REGION" > /dev/null 2>&1
                fi
            done <<< "$statement_ids"
        fi
    fi
}

# Function to cleanup existing API Gateway setup
cleanup_api_gateway() {
    print_info "Starting cleanup of existing API Gateway setup..."
    
    # Get current resources (excluding root)
    resources=$(aws apigateway get-resources \
        --rest-api-id "$API_GATEWAY_ID" \
        --region "$REGION" \
        --query 'items[].[path,id]' \
        --output text)
    
    if [ -n "$resources" ]; then
        print_info "Cleaning up existing methods and integrations..."
        while IFS=$'\t' read -r path id; do
            if [ -n "$path" ] && [ -n "$id" ] && [ "$path" != "/" ]; then
                delete_existing_methods "$id" "$path"
            fi
        done <<< "$resources"
    fi
    
    # Clean up Lambda permissions for all functions
    print_info "Cleaning up Lambda permissions..."
    lambda_functions=(
        "${PROJECT_NAME}-${ENVIRONMENT}-product-api"
        "${PROJECT_NAME}-${ENVIRONMENT}-cart-api"
        "${PROJECT_NAME}-${ENVIRONMENT}-order-api"
        "${PROJECT_NAME}-${ENVIRONMENT}-auth-api"
        "${PROJECT_NAME}-${ENVIRONMENT}-review-api"
        "${PROJECT_NAME}-${ENVIRONMENT}-search-api"
        "${PROJECT_NAME}-${ENVIRONMENT}-chat-api"
        "${PROJECT_NAME}-${ENVIRONMENT}-analytics-api"
    )
    
    for function_name in "${lambda_functions[@]}"; do
        # Check if function exists before cleaning permissions
        if aws lambda get-function --function-name "$function_name" --region "$REGION" > /dev/null 2>&1; then
            cleanup_lambda_permissions "$function_name"
        fi
    done
    
    print_status "Cleanup completed successfully"
}

# Function to create nested resources in API Gateway
create_nested_resource() {
    local full_path=$1
    
    # Remove leading slash and split path into parts
    local path_without_slash="${full_path#/}"
    IFS='/' read -ra path_parts <<< "$path_without_slash"
    
    # Start with root resource
    local current_parent_id=$(aws apigateway get-resources \
        --rest-api-id "$API_GATEWAY_ID" \
        --region "$REGION" \
        --query 'items[?path==`/`].id' \
        --output text)
    
    local current_path="/"
    
    # Create each path segment
    for path_part in "${path_parts[@]}"; do
        if [ -n "$path_part" ]; then
            current_path="${current_path%/}/${path_part}"
            
            # Check if resource already exists first
            local existing_resource_id=$(aws apigateway get-resources \
                --rest-api-id "$API_GATEWAY_ID" \
                --region "$REGION" \
                --query "items[?path=='$current_path'].id" \
                --output text 2>/dev/null)
            
            if [ -n "$existing_resource_id" ] && [ "$existing_resource_id" != "None" ]; then
                print_info "Resource $current_path already exists with ID: $existing_resource_id"
                current_parent_id="$existing_resource_id"
            else
                # Create new resource
                print_info "Creating resource: $current_path (parent: $current_parent_id, path-part: $path_part)"
                local new_resource_id=$(aws apigateway create-resource \
                    --rest-api-id "$API_GATEWAY_ID" \
                    --parent-id "$current_parent_id" \
                    --path-part "$path_part" \
                    --region "$REGION" \
                    --query 'id' \
                    --output text 2>/dev/null)
                
                if [ -n "$new_resource_id" ] && [ "$new_resource_id" != "None" ]; then
                    print_status "Created resource $current_path with ID: $new_resource_id"
                    current_parent_id="$new_resource_id"
                else
                    print_error "Failed to create resource $current_path"
                    return 1
                fi
            fi
        fi
    done
    
    echo "$current_parent_id"
}

# Function to create API Gateway integration with nested resource support
create_api_integration() {
    local resource_path=$1
    local http_method=$2
    local function_name=$3
    
    print_info "Processing $http_method $resource_path"
    
    # Get resource ID
    local resource_id=$(aws apigateway get-resources \
        --rest-api-id "$API_GATEWAY_ID" \
        --region "$REGION" \
        --query "items[?path=='$resource_path'].id" \
        --output text)
    
    # If resource doesn't exist, create it
    if [ -z "$resource_id" ] || [ "$resource_id" = "None" ]; then
        print_info "Creating nested resource path: $resource_path"
        resource_id=$(create_nested_resource "$resource_path")
        
        if [ -z "$resource_id" ]; then
            print_error "Failed to create resource path $resource_path"
            return 1
        fi
    fi
    
    print_info "Resource ID for $resource_path: $resource_id"
    
    # Get function ARN
    local function_arn=$(aws lambda get-function \
        --function-name "$function_name" \
        --region "$REGION" \
        --query 'Configuration.FunctionArn' \
        --output text)
    
    if [ -z "$function_arn" ]; then
        print_error "Failed to get function ARN for $function_name"
        return 1
    fi
    
    print_info "Creating method $http_method for $resource_path"
    
    # Create method (no checking since we cleaned up)
    aws apigateway put-method \
        --rest-api-id "$API_GATEWAY_ID" \
        --resource-id "$resource_id" \
        --http-method "$http_method" \
        --authorization-type "NONE" \
        --region "$REGION" > /dev/null 2>&1
    
    if [ $? -eq 0 ]; then
        print_status "Method $http_method created for $resource_path"
    else
        print_error "Failed to create method $http_method for $resource_path"
        return 1
    fi
    
    # Create integration
    print_info "Creating integration for $http_method $resource_path"
    aws apigateway put-integration \
        --rest-api-id "$API_GATEWAY_ID" \
        --resource-id "$resource_id" \
        --http-method "$http_method" \
        --type "AWS_PROXY" \
        --integration-http-method "POST" \
        --uri "arn:aws:apigateway:$REGION:lambda:path/2015-03-31/functions/$function_arn/invocations" \
        --region "$REGION" > /dev/null 2>&1
    
    if [ $? -eq 0 ]; then
        print_status "Integration created for $http_method $resource_path"
    else
        print_error "Failed to create integration for $http_method $resource_path"
        return 1
    fi
    
    # Add Lambda permission with unique statement ID
    local statement_id="apigateway-invoke-${function_name}-$(echo "$resource_path" | tr '/' '-')-${http_method}-$(date +%s)"
    print_info "Adding Lambda permission"
    aws lambda add-permission \
        --function-name "$function_name" \
        --statement-id "$statement_id" \
        --action "lambda:InvokeFunction" \
        --principal "apigateway.amazonaws.com" \
        --source-arn "arn:aws:execute-api:$REGION:$(aws sts get-caller-identity --query Account --output text):$API_GATEWAY_ID/*/*" \
        --region "$REGION" > /dev/null 2>&1
    
    print_status "Successfully configured $http_method $resource_path"
}

# Function to create all API integrations
create_all_api_integrations() {
    print_info "Creating fresh API Gateway integrations..."
    
    # Product API endpoints
    print_info "Creating Product API endpoints..."
    create_api_integration "/products" "GET" "${PROJECT_NAME}-${ENVIRONMENT}-product-api"
    create_api_integration "/products" "POST" "${PROJECT_NAME}-${ENVIRONMENT}-product-api"
    create_api_integration "/products/{id}" "GET" "${PROJECT_NAME}-${ENVIRONMENT}-product-api"
    create_api_integration "/products/{id}" "PUT" "${PROJECT_NAME}-${ENVIRONMENT}-product-api"
    create_api_integration "/products/{id}" "DELETE" "${PROJECT_NAME}-${ENVIRONMENT}-product-api"
    create_api_integration "/products/{id}/reviews" "GET" "${PROJECT_NAME}-${ENVIRONMENT}-product-api"
    create_api_integration "/products/categories" "GET" "${PROJECT_NAME}-${ENVIRONMENT}-product-api"
    create_api_integration "/products/featured" "GET" "${PROJECT_NAME}-${ENVIRONMENT}-product-api"
    
    # Cart API endpoints
    print_info "Creating Cart API endpoints..."
    create_api_integration "/cart" "GET" "${PROJECT_NAME}-${ENVIRONMENT}-cart-api"
    create_api_integration "/cart" "POST" "${PROJECT_NAME}-${ENVIRONMENT}-cart-api"
    create_api_integration "/cart" "DELETE" "${PROJECT_NAME}-${ENVIRONMENT}-cart-api"
    create_api_integration "/cart/{userId}" "GET" "${PROJECT_NAME}-${ENVIRONMENT}-cart-api"
    create_api_integration "/cart/{userId}/items" "POST" "${PROJECT_NAME}-${ENVIRONMENT}-cart-api"
    create_api_integration "/cart/{userId}/items/{itemId}" "PUT" "${PROJECT_NAME}-${ENVIRONMENT}-cart-api"
    create_api_integration "/cart/{userId}/items/{itemId}" "DELETE" "${PROJECT_NAME}-${ENVIRONMENT}-cart-api"
    
    # Order API endpoints
    print_info "Creating Order API endpoints..."
    create_api_integration "/orders" "GET" "${PROJECT_NAME}-${ENVIRONMENT}-order-api"
    create_api_integration "/orders" "POST" "${PROJECT_NAME}-${ENVIRONMENT}-order-api"
    create_api_integration "/orders/{orderId}" "GET" "${PROJECT_NAME}-${ENVIRONMENT}-order-api"
    create_api_integration "/orders/{orderId}" "PUT" "${PROJECT_NAME}-${ENVIRONMENT}-order-api"
    create_api_integration "/orders/{orderId}/cancel" "POST" "${PROJECT_NAME}-${ENVIRONMENT}-order-api"
    create_api_integration "/orders/user/{userId}" "GET" "${PROJECT_NAME}-${ENVIRONMENT}-order-api"
    
    # Authentication API endpoints - these require nested resource creation
    print_info "Creating Authentication API endpoints with nested resources..."
    create_api_integration "/auth/register" "POST" "${PROJECT_NAME}-${ENVIRONMENT}-auth-api"
    create_api_integration "/auth/login" "POST" "${PROJECT_NAME}-${ENVIRONMENT}-auth-api"
    create_api_integration "/auth/logout" "POST" "${PROJECT_NAME}-${ENVIRONMENT}-auth-api"
    create_api_integration "/auth/profile" "GET" "${PROJECT_NAME}-${ENVIRONMENT}-auth-api"
    create_api_integration "/auth/profile" "PUT" "${PROJECT_NAME}-${ENVIRONMENT}-auth-api"
    create_api_integration "/auth/refresh" "POST" "${PROJECT_NAME}-${ENVIRONMENT}-auth-api"
    create_api_integration "/auth/verify" "POST" "${PROJECT_NAME}-${ENVIRONMENT}-auth-api"
    create_api_integration "/auth/forgot-password" "POST" "${PROJECT_NAME}-${ENVIRONMENT}-auth-api"
    create_api_integration "/auth/reset-password" "POST" "${PROJECT_NAME}-${ENVIRONMENT}-auth-api"
    
    # Review API endpoints
    print_info "Creating Review API endpoints..."
    create_api_integration "/reviews" "GET" "${PROJECT_NAME}-${ENVIRONMENT}-review-api"
    create_api_integration "/reviews" "POST" "${PROJECT_NAME}-${ENVIRONMENT}-review-api"
    create_api_integration "/reviews/{reviewId}" "GET" "${PROJECT_NAME}-${ENVIRONMENT}-review-api"
    create_api_integration "/reviews/{reviewId}" "PUT" "${PROJECT_NAME}-${ENVIRONMENT}-review-api"
    create_api_integration "/reviews/{reviewId}" "DELETE" "${PROJECT_NAME}-${ENVIRONMENT}-review-api"
    create_api_integration "/reviews/{reviewId}/helpful" "POST" "${PROJECT_NAME}-${ENVIRONMENT}-review-api"
    create_api_integration "/reviews/product/{productId}" "GET" "${PROJECT_NAME}-${ENVIRONMENT}-review-api"
    
    # Search API endpoints - these require nested resource creation
    print_info "Creating Search API endpoints with nested resources..."
    create_api_integration "/search/products" "GET" "${PROJECT_NAME}-${ENVIRONMENT}-search-api"
    create_api_integration "/search/products" "POST" "${PROJECT_NAME}-${ENVIRONMENT}-search-api"
    create_api_integration "/search/suggestions" "GET" "${PROJECT_NAME}-${ENVIRONMENT}-search-api"
    create_api_integration "/search/autocomplete" "GET" "${PROJECT_NAME}-${ENVIRONMENT}-search-api"
    create_api_integration "/search/filters" "GET" "${PROJECT_NAME}-${ENVIRONMENT}-search-api"
    
    # Chat API endpoints
    print_info "Creating Chat API endpoints..."
    create_api_integration "/chat" "POST" "${PROJECT_NAME}-${ENVIRONMENT}-chat-api"
    create_api_integration "/chat/sessions" "GET" "${PROJECT_NAME}-${ENVIRONMENT}-chat-api"
    create_api_integration "/chat/sessions/{sessionId}" "GET" "${PROJECT_NAME}-${ENVIRONMENT}-chat-api"
    create_api_integration "/chat/sessions/{sessionId}/messages" "POST" "${PROJECT_NAME}-${ENVIRONMENT}-chat-api"
    
    # Analytics API endpoints
    print_info "Creating Analytics API endpoints..."
    create_api_integration "/analytics" "GET" "${PROJECT_NAME}-${ENVIRONMENT}-analytics-api"
    create_api_integration "/analytics/events" "POST" "${PROJECT_NAME}-${ENVIRONMENT}-analytics-api"
    create_api_integration "/analytics/dashboard" "GET" "${PROJECT_NAME}-${ENVIRONMENT}-analytics-api"
    create_api_integration "/analytics/reports" "GET" "${PROJECT_NAME}-${ENVIRONMENT}-analytics-api"
    
    print_status "All API Gateway integrations created successfully"
}

# Function to add CORS to a resource
add_cors_to_resource() {
    local resource_path=$1
    local resource_id=$2
    
    print_info "Adding CORS to resource: $resource_path"
    
    # Add OPTIONS method
    aws apigateway put-method \
        --rest-api-id "$API_GATEWAY_ID" \
        --resource-id "$resource_id" \
        --http-method "OPTIONS" \
        --authorization-type "NONE" \
        --region "$REGION" > /dev/null 2>&1 || true
    
    # Add OPTIONS integration (mock integration for CORS)
    aws apigateway put-integration \
        --rest-api-id "$API_GATEWAY_ID" \
        --resource-id "$resource_id" \
        --http-method "OPTIONS" \
        --type "MOCK" \
        --integration-http-method "OPTIONS" \
        --request-templates '{"application/json": "{\"statusCode\": 200}"}' \
        --region "$REGION" > /dev/null 2>&1 || true
    
    # Add method response for OPTIONS
    aws apigateway put-method-response \
        --rest-api-id "$API_GATEWAY_ID" \
        --resource-id "$resource_id" \
        --http-method "OPTIONS" \
        --status-code "200" \
        --response-parameters "{
            \"method.response.header.Access-Control-Allow-Origin\": false,
            \"method.response.header.Access-Control-Allow-Methods\": false,
            \"method.response.header.Access-Control-Allow-Headers\": false,
            \"method.response.header.Access-Control-Allow-Credentials\": false,
            \"method.response.header.Access-Control-Max-Age\": false
        }" \
        --region "$REGION" > /dev/null 2>&1 || true
    
    # Add integration response for OPTIONS with CORS headers
    aws apigateway put-integration-response \
        --rest-api-id "$API_GATEWAY_ID" \
        --resource-id "$resource_id" \
        --http-method "OPTIONS" \
        --status-code "200" \
        --response-parameters "{
            \"method.response.header.Access-Control-Allow-Origin\": \"'$CORS_ORIGIN'\",
            \"method.response.header.Access-Control-Allow-Methods\": \"'GET,POST,PUT,DELETE,OPTIONS'\",
            \"method.response.header.Access-Control-Allow-Headers\": \"'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token,X-Amz-User-Agent,X-Requested-With'\",
            \"method.response.header.Access-Control-Allow-Credentials\": \"'true'\",
            \"method.response.header.Access-Control-Max-Age\": \"'86400'\"
        }" \
        --region "$REGION" > /dev/null 2>&1 || true
    
    # Update existing methods to include CORS headers in responses
    for method in GET POST PUT DELETE; do
        # Check if method exists
        if aws apigateway get-method \
            --rest-api-id "$API_GATEWAY_ID" \
            --resource-id "$resource_id" \
            --http-method "$method" \
            --region "$REGION" > /dev/null 2>&1; then
            
            # Add method response with CORS headers for 200 status
            aws apigateway put-method-response \
                --rest-api-id "$API_GATEWAY_ID" \
                --resource-id "$resource_id" \
                --http-method "$method" \
                --status-code "200" \
                --response-parameters "{
                    \"method.response.header.Access-Control-Allow-Origin\": false,
                    \"method.response.header.Access-Control-Allow-Credentials\": false
                }" \
                --region "$REGION" > /dev/null 2>&1 || true
            
            # Add method response with CORS headers for error statuses
            for status in 400 401 403 404 500; do
                aws apigateway put-method-response \
                    --rest-api-id "$API_GATEWAY_ID" \
                    --resource-id "$resource_id" \
                    --http-method "$method" \
                    --status-code "$status" \
                    --response-parameters "{
                        \"method.response.header.Access-Control-Allow-Origin\": false,
                        \"method.response.header.Access-Control-Allow-Credentials\": false
                    }" \
                    --region "$REGION" > /dev/null 2>&1 || true
            done
            
            # Add integration response with CORS headers for 200 status
            aws apigateway put-integration-response \
                --rest-api-id "$API_GATEWAY_ID" \
                --resource-id "$resource_id" \
                --http-method "$method" \
                --status-code "200" \
                --response-parameters "{
                    \"method.response.header.Access-Control-Allow-Origin\": \"'$CORS_ORIGIN'\",
                    \"method.response.header.Access-Control-Allow-Credentials\": \"'true'\"
                }" \
                --region "$REGION" > /dev/null 2>&1 || true
            
            # Add integration response with CORS headers for error statuses
            for status in 400 401 403 404 500; do
                aws apigateway put-integration-response \
                    --rest-api-id "$API_GATEWAY_ID" \
                    --resource-id "$resource_id" \
                    --http-method "$method" \
                    --status-code "$status" \
                    --response-parameters "{
                        \"method.response.header.Access-Control-Allow-Origin\": \"'$CORS_ORIGIN'\",
                        \"method.response.header.Access-Control-Allow-Credentials\": \"'true'\"
                    }" \
                    --region "$REGION" > /dev/null 2>&1 || true
            done
        fi
    done
}

# Function to setup CORS for all resources
setup_cors() {
    # Configure CORS for API Gateway
    print_info "Configuring CORS for API Gateway..."
    
    # Get all resources from API Gateway and add CORS
    resources=$(aws apigateway get-resources \
        --rest-api-id "$API_GATEWAY_ID" \
        --region "$REGION" \
        --query 'items[].[path,id]' \
        --output text)
    
    if [ -n "$resources" ]; then
        # Add CORS to each resource
        while IFS=$'\t' read -r path id; do
            if [ -n "$path" ] && [ -n "$id" ]; then
                add_cors_to_resource "$path" "$id"
            fi
        done <<< "$resources"
        
        print_status "CORS configuration completed"
    else
        print_warning "No resources found for CORS configuration"
    fi
    
    # Deploy API Gateway with CORS changes
    print_info "Deploying API Gateway with CORS configuration..."
    deployment_id=$(aws apigateway create-deployment \
        --rest-api-id "$API_GATEWAY_ID" \
        --stage-name "$ENVIRONMENT" \
        --description "API Gateway deployment with CORS configuration $(date)" \
        --region "$REGION" \
        --query 'id' \
        --output text)
    
    print_status "API Gateway deployed with deployment ID: $deployment_id"
    
    print_status "API Gateway integrations and CORS configuration completed successfully!"
    
    echo ""
    echo "API Endpoint:"
    echo "https://$API_GATEWAY_ID.execute-api.$REGION.amazonaws.com/$ENVIRONMENT"
    echo ""
    echo "CORS Configuration:"
    echo "- Origin: $CORS_ORIGIN"
    echo "- Methods: GET,POST,PUT,DELETE,OPTIONS"
    echo "- Headers: Content-Type,Authorization,X-Api-Key,X-Amz-Security-Token,X-Requested-With"
    echo "- Credentials: Enabled"
    echo "- Max Age: 86400 seconds (24 hours)"
    echo ""
    echo "Available Endpoints:"
    echo ""
    echo "Product API:"
    echo "- GET/POST /products"
    echo "- GET/PUT/DELETE /products/{id}"
    echo "- GET /products/{id}/reviews"
    echo "- GET /products/categories"
    echo "- GET /products/featured"
    echo ""
    echo "Cart API:"
    echo "- GET/POST/DELETE /cart"
    echo "- GET /cart/{userId}"
    echo "- POST /cart/{userId}/items"
    echo "- PUT/DELETE /cart/{userId}/items/{itemId}"
    echo ""
    echo "Order API:"
    echo "- GET/POST /orders"
    echo "- GET/PUT /orders/{orderId}"
    echo "- POST /orders/{orderId}/cancel"
    echo "- GET /orders/user/{userId}"
    echo ""
    echo "Authentication API:"
    echo "- POST /auth/register"
    echo "- POST /auth/login"
    echo "- POST /auth/logout"
    echo "- GET/PUT /auth/profile"
    echo "- POST /auth/refresh"
    echo "- POST /auth/verify"
    echo "- POST /auth/forgot-password"
    echo "- POST /auth/reset-password"
    echo ""
    echo "Review API:"
    echo "- GET/POST /reviews"
    echo "- GET/PUT/DELETE /reviews/{reviewId}"
    echo "- POST /reviews/{reviewId}/helpful"
    echo "- GET /reviews/product/{productId}"
    echo ""
    echo "Search API:"
    echo "- GET/POST /search/products"
    echo "- GET /search/suggestions"
    echo "- GET /search/autocomplete"
    echo "- GET /search/filters"
    echo ""
    echo "Chat API:"
    echo "- POST /chat"
    echo "- GET /chat/sessions"
    echo "- GET /chat/sessions/{sessionId}"
    echo "- POST /chat/sessions/{sessionId}/messages"
    echo ""
    echo "Analytics API:"
    echo "- GET /analytics"
    echo "- POST /analytics/events"
    echo "- GET /analytics/dashboard"
    echo "- GET /analytics/reports"
}

# Main execution
print_info "Starting API Gateway setup..."

# Check if Lambda functions exist
print_info "Verifying Lambda functions are deployed..."
functions_exist=$(aws lambda list-functions \
    --region "$REGION" \
    --query "Functions[?starts_with(FunctionName, '${PROJECT_NAME}-${ENVIRONMENT}-')].FunctionName" \
    --output text 2>/dev/null || echo "")

if [ -z "$functions_exist" ]; then
    print_error "No Lambda functions found with prefix '${PROJECT_NAME}-${ENVIRONMENT}-'"
    print_error "Please run deploy-lambda-functions.sh first to deploy Lambda functions"
    exit 1
fi

print_status "Lambda functions found - proceeding with API Gateway setup"

# Execute main functions
cleanup_api_gateway
create_all_api_integrations
setup_cors

echo ""
echo -e "${GREEN}🎉 API Gateway Setup Complete!${NC}"
echo "============================================="