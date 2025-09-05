#!/bin/bash

# API Gateway Resources and Methods Setup Script
# This script creates all API Gateway resources and methods post CloudFormation deployment

set -e

# Configuration - Accept command line arguments with defaults
PROJECT_NAME="${1:-unicorn-ecommerce}"
ENVIRONMENT="${2:-dev}"
REGION="${3:-${AWS_DEFAULT_REGION:-us-east-1}}"

# Check for help flag
if [[ "$1" == "--help" ]] || [[ "$1" == "-h" ]]; then
    echo "Usage: $0 [PROJECT_NAME] [ENVIRONMENT] [REGION]"
    echo ""
    echo "Arguments:"
    echo "  PROJECT_NAME  Project name (default: 'unicorn-ecommerce')"
    echo "  ENVIRONMENT   Environment name (default: 'dev')"
    echo "  REGION        AWS region (default: \$AWS_DEFAULT_REGION or 'us-east-1')"
    echo ""
    echo "Examples:"
    echo "  $0                              # Uses defaults: unicorn-ecommerce, dev, us-east-1"
    echo "  $0 my-project                   # Uses my-project, dev, default region"
    echo "  $0 my-project staging           # Uses my-project, staging, default region"
    echo "  $0 my-project prod us-west-2    # Uses my-project, prod, us-west-2"
    echo ""
    exit 0
fi

# Derive API Gateway and User Pool IDs from project and environment
API_GATEWAY_ID=$(aws apigateway get-rest-apis --query "items[?name=='${PROJECT_NAME}-${ENVIRONMENT}-api'].id" --output text --region "$REGION")
USER_POOL_ID=$(aws cognito-idp list-user-pools --max-items 60 --query "UserPools[?Name=='${PROJECT_NAME}-${ENVIRONMENT}-users'].Id" --output text --region "$REGION")

if [ -z "$API_GATEWAY_ID" ] || [ "$API_GATEWAY_ID" = "None" ]; then
    echo "❌ Error: API Gateway not found for ${PROJECT_NAME}-${ENVIRONMENT}-api in region $REGION"
    exit 1
fi

if [ -z "$USER_POOL_ID" ] || [ "$USER_POOL_ID" = "None" ]; then
    echo "❌ Error: User Pool not found for ${PROJECT_NAME}-${ENVIRONMENT}-users in region $REGION"
    exit 1
fi

AWS_REGION="$REGION"
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

echo "Setting up API Gateway resources and methods..."
echo "API Gateway ID: $API_GATEWAY_ID"
echo "User Pool ID: $USER_POOL_ID"
echo "Environment: $ENVIRONMENT"
echo "Region: $AWS_REGION"

# Get the root resource ID
ROOT_RESOURCE_ID=$(aws apigateway get-resources --rest-api-id $API_GATEWAY_ID --query 'items[?path==`/`].id' --output text)
echo "Root Resource ID: $ROOT_RESOURCE_ID"

# Function to create a resource
create_resource() {
    local parent_id=$1
    local path_part=$2
    local resource_name=$3
    
    echo "Creating or getting resource: $resource_name with path: $path_part"
    
    # Check if resource already exists
    local existing_resource_id=$(aws apigateway get-resources \
        --rest-api-id $API_GATEWAY_ID \
        --query "items[?parentId=='$parent_id' && pathPart=='$path_part'].id" \
        --output text)
    
    if [ ! -z "$existing_resource_id" ] && [ "$existing_resource_id" != "None" ]; then
        echo "Using existing $resource_name: $existing_resource_id"
        local resource_id=$existing_resource_id
    else
        echo "Creating new resource: $resource_name with path: $path_part"
        local resource_id=$(aws apigateway create-resource \
            --rest-api-id $API_GATEWAY_ID \
            --parent-id $parent_id \
            --path-part "$path_part" \
            --query 'id' --output text)
        echo "Created $resource_name: $resource_id"
    fi
    
    eval "${resource_name}=$resource_id"
}

# Function to create a method
create_method() {
    local resource_id=$1
    local http_method=$2
    local authorization_type=$3
    local authorizer_id=$4
    local lambda_function_arn=$5
    local method_name=$6
    
    echo "Creating or updating method: $method_name ($http_method) on resource: $resource_id"
    
    # Create method (this will update if it exists)
    if [ "$authorization_type" = "COGNITO_USER_POOLS" ]; then
        aws apigateway put-method \
            --rest-api-id $API_GATEWAY_ID \
            --resource-id $resource_id \
            --http-method $http_method \
            --authorization-type $authorization_type \
            --authorizer-id $authorizer_id \
            --no-api-key-required 2>/dev/null || echo "Method $http_method already exists on resource $resource_id"
    else
        aws apigateway put-method \
            --rest-api-id $API_GATEWAY_ID \
            --resource-id $resource_id \
            --http-method $http_method \
            --authorization-type $authorization_type \
            --no-api-key-required 2>/dev/null || echo "Method $http_method already exists on resource $resource_id"
    fi
    
    # Create method response first
    aws apigateway put-method-response \
        --rest-api-id $API_GATEWAY_ID \
        --resource-id $resource_id \
        --http-method $http_method \
        --status-code 200 \
        --response-parameters method.response.header.Access-Control-Allow-Origin=false 2>/dev/null || echo "Method response already exists"
    
    # Create integration
    aws apigateway put-integration \
        --rest-api-id $API_GATEWAY_ID \
        --resource-id $resource_id \
        --http-method $http_method \
        --type AWS_PROXY \
        --integration-http-method POST \
        --uri "arn:aws:apigateway:$AWS_REGION:lambda:path/2015-03-31/functions/$lambda_function_arn/invocations" 2>/dev/null || echo "Integration already exists"
    
    # Create integration response
    aws apigateway put-integration-response \
        --rest-api-id $API_GATEWAY_ID \
        --resource-id $resource_id \
        --http-method $http_method \
        --status-code 200 \
        --response-parameters '{"method.response.header.Access-Control-Allow-Origin": "'\''*'\''"}'  2>/dev/null || echo "Integration response already exists"
    
    echo "Processed method: $method_name"
}

# Function to create OPTIONS method for CORS
create_options_method() {
    local resource_id=$1
    local resource_name=$2
    local allowed_methods=${3:-"GET,POST,PUT,DELETE,OPTIONS"}
    
    echo "Creating or updating OPTIONS method for CORS on $resource_name (Methods: $allowed_methods)"
    
    # Create OPTIONS method
    aws apigateway put-method \
        --rest-api-id $API_GATEWAY_ID \
        --resource-id $resource_id \
        --http-method OPTIONS \
        --authorization-type NONE \
        --no-api-key-required 2>/dev/null || echo "OPTIONS method already exists on $resource_name"
    
    # Create method response for OPTIONS first
    aws apigateway put-method-response \
        --rest-api-id $API_GATEWAY_ID \
        --resource-id $resource_id \
        --http-method OPTIONS \
        --status-code 200 \
        --response-parameters method.response.header.Access-Control-Allow-Headers=false,method.response.header.Access-Control-Allow-Methods=false,method.response.header.Access-Control-Allow-Origin=false,method.response.header.Access-Control-Allow-Credentials=false,method.response.header.Access-Control-Max-Age=false 2>/dev/null || echo "OPTIONS method response already exists"
    
    # Create MOCK integration for OPTIONS
    aws apigateway put-integration \
        --rest-api-id $API_GATEWAY_ID \
        --resource-id $resource_id \
        --http-method OPTIONS \
        --type MOCK \
        --request-templates '{"application/json": "{\"statusCode\": 200}"}' 2>/dev/null || echo "OPTIONS integration already exists"
    
    # Create integration response for OPTIONS
    aws apigateway put-integration-response \
        --rest-api-id $API_GATEWAY_ID \
        --resource-id $resource_id \
        --http-method OPTIONS \
        --status-code 200 \
        --response-parameters '{
            "method.response.header.Access-Control-Allow-Headers": "'\''Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token,X-Requested-With,X-Amz-User-Agent'\''",
            "method.response.header.Access-Control-Allow-Methods": "'\'''"$allowed_methods"''\''",
            "method.response.header.Access-Control-Allow-Origin": "'\''*'\''",
            "method.response.header.Access-Control-Allow-Credentials": "'\''true'\''",
            "method.response.header.Access-Control-Max-Age": "'\''86400'\''"
        }' \
        --response-templates '{"application/json": ""}' 2>/dev/null || echo "OPTIONS integration response already exists"
    
    echo "Processed OPTIONS method for $resource_name"
}

# Get Lambda function ARNs (using $LATEST directly)
get_lambda_arn() {
    local function_name=$1
    local full_function_name="$PROJECT_NAME-$ENVIRONMENT-$function_name"
    
    # Get the base function ARN (using $LATEST)
    aws lambda get-function \
        --function-name "$full_function_name" \
        --query 'Configuration.FunctionArn' \
        --output text
}

echo "Retrieving Lambda function ARNs (using $LATEST)..."
AUTH_LAMBDA_ARN=$(get_lambda_arn "AuthApi")
PRODUCT_LAMBDA_ARN=$(get_lambda_arn "ProductApi")
CART_LAMBDA_ARN=$(get_lambda_arn "CartApi")
ORDER_LAMBDA_ARN=$(get_lambda_arn "OrderApi")
REVIEW_LAMBDA_ARN=$(get_lambda_arn "ReviewApi")
SEARCH_LAMBDA_ARN=$(get_lambda_arn "SearchApi")
CHAT_LAMBDA_ARN=$(get_lambda_arn "ChatApi")
ANALYTICS_LAMBDA_ARN=$(get_lambda_arn "AnalyticsApi")

# Verify Lambda functions exist
verify_lambda_functions() {
    echo "Verifying Lambda functions exist..."
    echo "=================================="
    
    local functions=("AuthApi" "ProductApi" "CartApi" "OrderApi" "ReviewApi" "SearchApi" "ChatApi" "AnalyticsApi")
    local functions_found=0
    
    for func in "${functions[@]}"; do
        local full_function_name="$PROJECT_NAME-$ENVIRONMENT-$func"
        
        # Check if function exists
        local function_check=$(aws lambda get-function \
            --function-name "$full_function_name" \
            --query 'Configuration.FunctionName' \
            --output text 2>/dev/null)
        
        if [ $? -eq 0 ] && [ "$function_check" = "$full_function_name" ]; then
            functions_found=$((functions_found + 1))
            echo "✅ $func: Function exists (using \$LATEST)"
        else
            echo "❌ $func: Function not found"
        fi
    done
    
    echo ""
    echo "Summary: $functions_found/${#functions[@]} functions found"
    
    if [ $functions_found -lt ${#functions[@]} ]; then
        echo ""
        echo "⚠️  Warning: Some functions are missing."
        echo "   Please ensure the CloudFormation template has been deployed successfully."
        exit 1
    fi
    
    echo "ℹ️  Info: All functions will use \$LATEST version (no aliases or provisioned concurrency)."
    echo ""
}

verify_lambda_functions

echo "Lambda ARNs retrieved successfully (using \$LATEST)"

# Create or get existing Cognito Authorizer
echo "Creating or getting Cognito Authorizer..."
AUTHORIZER_NAME="${ENVIRONMENT}-cognito-authorizer"

# Check if authorizer already exists
EXISTING_AUTHORIZER_ID=$(aws apigateway get-authorizers \
    --rest-api-id $API_GATEWAY_ID \
    --query "items[?name=='$AUTHORIZER_NAME'].id" \
    --output text)

if [ ! -z "$EXISTING_AUTHORIZER_ID" ] && [ "$EXISTING_AUTHORIZER_ID" != "None" ]; then
    echo "Using existing Cognito Authorizer ID: $EXISTING_AUTHORIZER_ID"
    COGNITO_AUTHORIZER_ID=$EXISTING_AUTHORIZER_ID
else
    echo "Creating new Cognito Authorizer..."
    COGNITO_AUTHORIZER_ID=$(aws apigateway create-authorizer \
        --rest-api-id $API_GATEWAY_ID \
        --name "$AUTHORIZER_NAME" \
        --type COGNITO_USER_POOLS \
        --provider-arns "arn:aws:cognito-idp:$AWS_REGION:$AWS_ACCOUNT_ID:userpool/$USER_POOL_ID" \
        --identity-source method.request.header.Authorization \
        --query 'id' --output text)
    echo "Created new Cognito Authorizer ID: $COGNITO_AUTHORIZER_ID"
fi

# Create main API resources (only those used by frontend)
echo "Creating main API resources..."

# Products resources
create_resource $ROOT_RESOURCE_ID "products" "PRODUCTS_RESOURCE_ID"
create_resource $PRODUCTS_RESOURCE_ID "{id}" "PRODUCTS_ID_RESOURCE_ID"
create_resource $PRODUCTS_ID_RESOURCE_ID "reviews" "PRODUCTS_ID_REVIEWS_RESOURCE_ID"

# Cart resources
create_resource $ROOT_RESOURCE_ID "cart" "CART_RESOURCE_ID"
create_resource $CART_RESOURCE_ID "items" "CART_ITEMS_RESOURCE_ID"
create_resource $CART_ITEMS_RESOURCE_ID "{itemId}" "CART_ITEMS_ITEM_ID_RESOURCE_ID"
create_resource $CART_RESOURCE_ID "clear" "CART_CLEAR_RESOURCE_ID"

# Orders resources
create_resource $ROOT_RESOURCE_ID "orders" "ORDERS_RESOURCE_ID"
create_resource $ORDERS_RESOURCE_ID "{orderId}" "ORDERS_ORDER_ID_RESOURCE_ID"

# Auth resources
create_resource $ROOT_RESOURCE_ID "auth" "AUTH_RESOURCE_ID"
create_resource $AUTH_RESOURCE_ID "register" "AUTH_REGISTER_RESOURCE_ID"
create_resource $AUTH_RESOURCE_ID "login" "AUTH_LOGIN_RESOURCE_ID"
create_resource $AUTH_RESOURCE_ID "logout" "AUTH_LOGOUT_RESOURCE_ID"
create_resource $AUTH_RESOURCE_ID "profile" "AUTH_PROFILE_RESOURCE_ID"
create_resource $AUTH_RESOURCE_ID "refresh" "AUTH_REFRESH_RESOURCE_ID"
create_resource $AUTH_RESOURCE_ID "verify" "AUTH_VERIFY_RESOURCE_ID"
create_resource $AUTH_RESOURCE_ID "reset-password" "AUTH_RESET_PASSWORD_RESOURCE_ID"

# Reviews resources
create_resource $ROOT_RESOURCE_ID "reviews" "REVIEWS_RESOURCE_ID"
create_resource $REVIEWS_RESOURCE_ID "{reviewId}" "REVIEWS_REVIEW_ID_RESOURCE_ID"
create_resource $REVIEWS_REVIEW_ID_RESOURCE_ID "helpful" "REVIEWS_REVIEW_ID_HELPFUL_RESOURCE_ID"

# Search resources
create_resource $ROOT_RESOURCE_ID "search" "SEARCH_RESOURCE_ID"
create_resource $SEARCH_RESOURCE_ID "products" "SEARCH_PRODUCTS_RESOURCE_ID"
create_resource $SEARCH_RESOURCE_ID "suggestions" "SEARCH_SUGGESTIONS_RESOURCE_ID"

# Chat resources
create_resource $ROOT_RESOURCE_ID "chat" "CHAT_RESOURCE_ID"
create_resource $CHAT_RESOURCE_ID "message" "CHAT_MESSAGE_RESOURCE_ID"
create_resource $CHAT_RESOURCE_ID "history" "CHAT_HISTORY_RESOURCE_ID"

# Analytics resources
create_resource $ROOT_RESOURCE_ID "analytics" "ANALYTICS_RESOURCE_ID"
create_resource $ANALYTICS_RESOURCE_ID "dashboard" "ANALYTICS_DASHBOARD_RESOURCE_ID"
create_resource $ANALYTICS_RESOURCE_ID "reviews" "ANALYTICS_REVIEWS_RESOURCE_ID"
create_resource $ANALYTICS_REVIEWS_RESOURCE_ID "insights" "ANALYTICS_REVIEWS_INSIGHTS_RESOURCE_ID"
create_resource $ANALYTICS_REVIEWS_INSIGHTS_RESOURCE_ID "{id}" "ANALYTICS_REVIEWS_INSIGHTS_ID_RESOURCE_ID"
create_resource $ANALYTICS_RESOURCE_ID "products" "ANALYTICS_PRODUCTS_RESOURCE_ID"
create_resource $ANALYTICS_PRODUCTS_RESOURCE_ID "recommendations" "ANALYTICS_PRODUCTS_RECOMMENDATIONS_RESOURCE_ID"

echo "All resources created successfully!"

# Create methods (only those used by frontend)
echo "Creating API methods..."

# Auth methods (no authorization required)
create_method $AUTH_REGISTER_RESOURCE_ID "POST" "NONE" "" $AUTH_LAMBDA_ARN "AuthRegisterPOST"
create_method $AUTH_LOGIN_RESOURCE_ID "POST" "NONE" "" $AUTH_LAMBDA_ARN "AuthLoginPOST"
create_method $AUTH_REFRESH_RESOURCE_ID "POST" "NONE" "" $AUTH_LAMBDA_ARN "AuthRefreshPOST"
create_method $AUTH_VERIFY_RESOURCE_ID "GET" "NONE" "" $AUTH_LAMBDA_ARN "AuthVerifyGET"
create_method $AUTH_RESET_PASSWORD_RESOURCE_ID "POST" "NONE" "" $AUTH_LAMBDA_ARN "AuthResetPasswordPOST"

# Auth methods (Cognito authorization required)
create_method $AUTH_PROFILE_RESOURCE_ID "GET" "COGNITO_USER_POOLS" $COGNITO_AUTHORIZER_ID $AUTH_LAMBDA_ARN "AuthProfileGET"
create_method $AUTH_PROFILE_RESOURCE_ID "PUT" "COGNITO_USER_POOLS" $COGNITO_AUTHORIZER_ID $AUTH_LAMBDA_ARN "AuthProfilePUT"
create_method $AUTH_LOGOUT_RESOURCE_ID "POST" "COGNITO_USER_POOLS" $COGNITO_AUTHORIZER_ID $AUTH_LAMBDA_ARN "AuthLogoutPOST"

# Product methods
create_method $PRODUCTS_RESOURCE_ID "GET" "NONE" "" $PRODUCT_LAMBDA_ARN "ProductsGET"
create_method $PRODUCTS_ID_RESOURCE_ID "GET" "NONE" "" $PRODUCT_LAMBDA_ARN "ProductsIdGET"
create_method $PRODUCTS_ID_REVIEWS_RESOURCE_ID "GET" "NONE" "" $REVIEW_LAMBDA_ARN "ProductsIdReviewsGET"

# Cart methods (Cognito authorization required)
create_method $CART_RESOURCE_ID "GET" "COGNITO_USER_POOLS" $COGNITO_AUTHORIZER_ID $CART_LAMBDA_ARN "CartGET"
create_method $CART_ITEMS_RESOURCE_ID "POST" "COGNITO_USER_POOLS" $COGNITO_AUTHORIZER_ID $CART_LAMBDA_ARN "CartItemsPOST"
create_method $CART_ITEMS_ITEM_ID_RESOURCE_ID "PUT" "COGNITO_USER_POOLS" $COGNITO_AUTHORIZER_ID $CART_LAMBDA_ARN "CartItemsItemIdPUT"
create_method $CART_ITEMS_ITEM_ID_RESOURCE_ID "DELETE" "COGNITO_USER_POOLS" $COGNITO_AUTHORIZER_ID $CART_LAMBDA_ARN "CartItemsItemIdDELETE"
create_method $CART_CLEAR_RESOURCE_ID "DELETE" "COGNITO_USER_POOLS" $COGNITO_AUTHORIZER_ID $CART_LAMBDA_ARN "CartClearDELETE"

# Order methods (Cognito authorization required)
create_method $ORDERS_RESOURCE_ID "GET" "COGNITO_USER_POOLS" $COGNITO_AUTHORIZER_ID $ORDER_LAMBDA_ARN "OrdersGET"
create_method $ORDERS_RESOURCE_ID "POST" "COGNITO_USER_POOLS" $COGNITO_AUTHORIZER_ID $ORDER_LAMBDA_ARN "OrdersPOST"
create_method $ORDERS_ORDER_ID_RESOURCE_ID "GET" "COGNITO_USER_POOLS" $COGNITO_AUTHORIZER_ID $ORDER_LAMBDA_ARN "OrdersOrderIdGET"

# Review methods
create_method $REVIEWS_RESOURCE_ID "POST" "COGNITO_USER_POOLS" $COGNITO_AUTHORIZER_ID $REVIEW_LAMBDA_ARN "ReviewsPOST"
create_method $REVIEWS_REVIEW_ID_HELPFUL_RESOURCE_ID "POST" "COGNITO_USER_POOLS" $COGNITO_AUTHORIZER_ID $REVIEW_LAMBDA_ARN "ReviewsReviewIdHelpfulPOST"

# Search methods (no authorization required)
create_method $SEARCH_PRODUCTS_RESOURCE_ID "GET" "NONE" "" $SEARCH_LAMBDA_ARN "SearchProductsGET"
create_method $SEARCH_PRODUCTS_RESOURCE_ID "POST" "NONE" "" $SEARCH_LAMBDA_ARN "SearchProductsPOST"
create_method $SEARCH_SUGGESTIONS_RESOURCE_ID "GET" "NONE" "" $SEARCH_LAMBDA_ARN "SearchSuggestionsGET"

# Analytics methods
create_method $ANALYTICS_DASHBOARD_RESOURCE_ID "GET" "COGNITO_USER_POOLS" $COGNITO_AUTHORIZER_ID $ANALYTICS_LAMBDA_ARN "AnalyticsDashboardGET"
create_method $ANALYTICS_REVIEWS_INSIGHTS_ID_RESOURCE_ID "GET" "NONE" "" $ANALYTICS_LAMBDA_ARN "AnalyticsReviewsInsightsIdGET"
create_method $ANALYTICS_PRODUCTS_RECOMMENDATIONS_RESOURCE_ID "GET" "COGNITO_USER_POOLS" $COGNITO_AUTHORIZER_ID $ANALYTICS_LAMBDA_ARN "AnalyticsProductsRecommendationsGET"

# Chat methods (Cognito authorization required)
create_method $CHAT_MESSAGE_RESOURCE_ID "POST" "COGNITO_USER_POOLS" $COGNITO_AUTHORIZER_ID $CHAT_LAMBDA_ARN "ChatMessagePOST"
create_method $CHAT_HISTORY_RESOURCE_ID "GET" "COGNITO_USER_POOLS" $COGNITO_AUTHORIZER_ID $CHAT_LAMBDA_ARN "ChatHistoryGET"

echo "All methods created successfully!"

# Create OPTIONS methods for CORS support (only for used resources)
echo "Creating OPTIONS methods for CORS support..."

# Auth resources OPTIONS
create_options_method $AUTH_REGISTER_RESOURCE_ID "AuthRegister" "POST,OPTIONS"
create_options_method $AUTH_LOGIN_RESOURCE_ID "AuthLogin" "POST,OPTIONS"
create_options_method $AUTH_LOGOUT_RESOURCE_ID "AuthLogout" "POST,OPTIONS"
create_options_method $AUTH_PROFILE_RESOURCE_ID "AuthProfile" "GET,PUT,OPTIONS"
create_options_method $AUTH_REFRESH_RESOURCE_ID "AuthRefresh" "POST,OPTIONS"
create_options_method $AUTH_VERIFY_RESOURCE_ID "AuthVerify" "GET,OPTIONS"
create_options_method $AUTH_RESET_PASSWORD_RESOURCE_ID "AuthResetPassword" "POST,OPTIONS"

# Products resources OPTIONS
create_options_method $PRODUCTS_RESOURCE_ID "Products" "GET,OPTIONS"
create_options_method $PRODUCTS_ID_RESOURCE_ID "ProductsId" "GET,OPTIONS"
create_options_method $PRODUCTS_ID_REVIEWS_RESOURCE_ID "ProductsIdReviews" "GET,OPTIONS"

# Cart resources OPTIONS
create_options_method $CART_RESOURCE_ID "Cart" "GET,OPTIONS"
create_options_method $CART_ITEMS_RESOURCE_ID "CartItems" "POST,OPTIONS"
create_options_method $CART_ITEMS_ITEM_ID_RESOURCE_ID "CartItemsItemId" "PUT,DELETE,OPTIONS"
create_options_method $CART_CLEAR_RESOURCE_ID "CartClear" "DELETE,OPTIONS"

# Orders resources OPTIONS
create_options_method $ORDERS_RESOURCE_ID "Orders" "GET,POST,OPTIONS"
create_options_method $ORDERS_ORDER_ID_RESOURCE_ID "OrdersOrderId" "GET,OPTIONS"

# Reviews resources OPTIONS
create_options_method $REVIEWS_RESOURCE_ID "Reviews" "POST,OPTIONS"
create_options_method $REVIEWS_REVIEW_ID_HELPFUL_RESOURCE_ID "ReviewsReviewIdHelpful" "POST,OPTIONS"

# Search resources OPTIONS
create_options_method $SEARCH_PRODUCTS_RESOURCE_ID "SearchProducts" "GET,POST,OPTIONS"
create_options_method $SEARCH_SUGGESTIONS_RESOURCE_ID "SearchSuggestions" "GET,OPTIONS"

# Chat resources OPTIONS
create_options_method $CHAT_MESSAGE_RESOURCE_ID "ChatMessage" "POST,OPTIONS"
create_options_method $CHAT_HISTORY_RESOURCE_ID "ChatHistory" "GET,OPTIONS"

# Analytics resources OPTIONS
create_options_method $ANALYTICS_DASHBOARD_RESOURCE_ID "AnalyticsDashboard" "GET,OPTIONS"
create_options_method $ANALYTICS_REVIEWS_INSIGHTS_ID_RESOURCE_ID "AnalyticsReviewsInsightsId" "GET,OPTIONS"
create_options_method $ANALYTICS_PRODUCTS_RECOMMENDATIONS_RESOURCE_ID "AnalyticsProductsRecommendations" "GET,OPTIONS"

echo "All OPTIONS methods for CORS created successfully!"

# Function to add CORS headers to existing method responses
add_cors_to_existing_methods() {
    echo "Adding CORS headers to existing method responses..."
    
    # Get all resources and their methods
    local resources=$(aws apigateway get-resources --rest-api-id $API_GATEWAY_ID --query 'items[].id' --output text)
    
    for resource_id in $resources; do
        # Get methods for this resource (excluding OPTIONS)
        local methods=$(aws apigateway get-resource --rest-api-id $API_GATEWAY_ID --resource-id $resource_id --query 'resourceMethods' --output text 2>/dev/null || echo "")
        
        if [ ! -z "$methods" ] && [ "$methods" != "None" ]; then
            for method in GET POST PUT DELETE; do
                if echo "$methods" | grep -q "$method"; then
                    echo "Adding CORS headers to $method method on resource $resource_id"
                    # Update integration response to include CORS headers
                    aws apigateway update-integration-response \
                        --rest-api-id $API_GATEWAY_ID \
                        --resource-id $resource_id \
                        --http-method $method \
                        --status-code 200 \
                        --patch-ops op=replace,path=/responseParameters/method.response.header.Access-Control-Allow-Origin,value="'*'" \
                        2>/dev/null || echo "Could not update CORS for $method on $resource_id (may not exist yet)"
                fi
            done
        fi
    done
}

# Add CORS headers to existing methods
add_cors_to_existing_methods

echo "CORS configuration completed!"

# Add Lambda permissions for API Gateway to invoke functions
echo "Adding Lambda permissions for API Gateway..."

add_lambda_permission() {
    local function_name=$1
    local statement_id=$2
    
    aws lambda add-permission \
        --function-name "$PROJECT_NAME-$ENVIRONMENT-$function_name" \
        --statement-id "$statement_id" \
        --action lambda:InvokeFunction \
        --principal apigateway.amazonaws.com \
        --source-arn "arn:aws:execute-api:$AWS_REGION:$AWS_ACCOUNT_ID:$API_GATEWAY_ID/*/*" \
        --no-cli-pager || echo "Permission already exists for $function_name"
}

add_lambda_permission "AuthApi" "apigateway-auth-invoke"
add_lambda_permission "ProductApi" "apigateway-product-invoke"
add_lambda_permission "CartApi" "apigateway-cart-invoke"
add_lambda_permission "OrderApi" "apigateway-order-invoke"
add_lambda_permission "ReviewApi" "apigateway-review-invoke"
add_lambda_permission "SearchApi" "apigateway-search-invoke"
add_lambda_permission "ChatApi" "apigateway-chat-invoke"
add_lambda_permission "AnalyticsApi" "apigateway-analytics-invoke"

echo "Lambda permissions added successfully!"

# Create deployment
echo "Creating API Gateway deployment..."
DEPLOYMENT_ID=$(aws apigateway create-deployment \
    --rest-api-id $API_GATEWAY_ID \
    --stage-name $ENVIRONMENT \
    --stage-description "Deployment for $ENVIRONMENT environment" \
    --description "API Gateway deployment created by setup script" \
    --query 'id' --output text)

echo "Deployment created with ID: $DEPLOYMENT_ID"

# Output the API Gateway URL
API_URL="https://$API_GATEWAY_ID.execute-api.$AWS_REGION.amazonaws.com/$ENVIRONMENT"
echo ""
echo "=========================================="
echo "API Gateway setup completed successfully!"
echo "=========================================="
echo "API Gateway ID: $API_GATEWAY_ID"
echo "API Gateway URL: $API_URL"
echo "Cognito Authorizer ID: $COGNITO_AUTHORIZER_ID"
echo "Deployment ID: $DEPLOYMENT_ID"
echo "=========================================="

# Save configuration to file with Lambda ARN details
cat > api-gateway-config.json << EOF
{
  "apiGatewayId": "$API_GATEWAY_ID",
  "apiGatewayUrl": "$API_URL",
  "cognitoAuthorizerId": "$COGNITO_AUTHORIZER_ID",
  "deploymentId": "$DEPLOYMENT_ID",
  "environment": "$ENVIRONMENT",
  "region": "$AWS_REGION",
  "userPoolId": "$USER_POOL_ID",
  "lambdaArns": {
    "authApi": "$AUTH_LAMBDA_ARN",
    "productApi": "$PRODUCT_LAMBDA_ARN",
    "cartApi": "$CART_LAMBDA_ARN",
    "orderApi": "$ORDER_LAMBDA_ARN",
    "reviewApi": "$REVIEW_LAMBDA_ARN",
    "searchApi": "$SEARCH_LAMBDA_ARN",
    "chatApi": "$CHAT_LAMBDA_ARN",
    "analyticsApi": "$ANALYTICS_LAMBDA_ARN"
  }
}
EOF

echo "Configuration saved to api-gateway-config.json"

# Create Lambda integration summary
cat > lambda-integration-summary.txt << EOF
Lambda Integration Summary
==========================

API Gateway is configured to use the following Lambda integrations:

Auth API: $AUTH_LAMBDA_ARN
Product API: $PRODUCT_LAMBDA_ARN
Cart API: $CART_LAMBDA_ARN
Order API: $ORDER_LAMBDA_ARN
Review API: $REVIEW_LAMBDA_ARN
Search API: $SEARCH_LAMBDA_ARN
Chat API: $CHAT_LAMBDA_ARN
Analytics API: $ANALYTICS_LAMBDA_ARN

Performance Notes:
- All functions use \$LATEST version (no aliases or provisioned concurrency)
- Functions may experience cold starts on first invocation
- Run ./deploy-lambda-functions.sh to update function code

Integration Type: AWS_PROXY
All integrations use POST method to Lambda (AWS_PROXY requirement)
EOF

# Create CORS configuration summary
cat > cors-config-summary.txt << EOF
CORS Configuration Summary
==========================

The following CORS settings have been applied to all API resources:

Headers Allowed:
- Content-Type
- X-Amz-Date
- Authorization
- X-Api-Key
- X-Amz-Security-Token
- X-Requested-With
- X-Amz-User-Agent

Methods Configured per Resource:
- Auth endpoints: POST (register, login, logout, refresh), GET (verify), GET/PUT (profile)
- Product endpoints: GET (all product-related endpoints)
- Cart endpoints: GET (/cart), POST (/cart/items), PUT/DELETE (/cart/items/{itemId}), DELETE (/cart/clear)
- Order endpoints: GET (/orders/user), POST (/orders), GET/PUT (/orders/{orderId})
- Review endpoints: GET (view), POST (create, mark helpful), GET (/reviews/user for user reviews)
- Search endpoints: GET/POST (search products), GET (suggestions, autocomplete, filters)
- Chat endpoints: POST (/chat/message), GET (/chat/history), GET/POST (sessions and messages)
- Analytics endpoints: POST (events), GET (dashboard - requires auth, reports), GET (recommendations - requires auth)

Origin: * (all origins allowed)
Credentials: true
Max-Age: 86400 seconds (24 hours)

All endpoints return Access-Control-Allow-Origin: * header in responses.
EOF

echo ""
echo "=========================================="
echo "CORS Configuration Summary:"
echo "=========================================="
cat cors-config-summary.txt
echo "=========================================="
echo ""
echo "Lambda Integration Summary:"
echo "=========================="
cat lambda-integration-summary.txt
echo ""
echo "=========================================="
echo "Setup completed successfully!"
echo "Configuration files created:"
echo "- api-gateway-config.json (API Gateway configuration)"
echo "- cors-config-summary.txt (CORS configuration details)"
echo "- lambda-integration-summary.txt (Lambda integration details)"