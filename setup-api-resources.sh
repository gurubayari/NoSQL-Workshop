#!/bin/bash

# API Gateway Resources and Methods Setup Script
# This script creates all API Gateway resources and methods post CloudFormation deployment

set -e

# Check if required parameters are provided
if [ $# -lt 2 ]; then
    echo "Usage: $0 <API_GATEWAY_ID> <USER_POOL_ID> [ENVIRONMENT]"
    echo "Example: $0 abc123def456 us-west-2_ABC123DEF dev"
    exit 1
fi

API_GATEWAY_ID=$1
USER_POOL_ID=$2
ENVIRONMENT=${3:-dev}
AWS_REGION=${AWS_DEFAULT_REGION:-$(aws configure get region)}
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

# Get Lambda function ARNs
get_lambda_arn() {
    local function_name=$1
    aws lambda get-function --function-name "unicorn-ecommerce-$ENVIRONMENT-$function_name" --query 'Configuration.FunctionArn' --output text
}

AUTH_LAMBDA_ARN=$(get_lambda_arn "AuthApi")
PRODUCT_LAMBDA_ARN=$(get_lambda_arn "ProductApi")
CART_LAMBDA_ARN=$(get_lambda_arn "CartApi")
ORDER_LAMBDA_ARN=$(get_lambda_arn "OrderApi")
REVIEW_LAMBDA_ARN=$(get_lambda_arn "ReviewApi")
SEARCH_LAMBDA_ARN=$(get_lambda_arn "SearchApi")
CHAT_LAMBDA_ARN=$(get_lambda_arn "ChatApi")
ANALYTICS_LAMBDA_ARN=$(get_lambda_arn "AnalyticsApi")

echo "Lambda ARNs retrieved successfully"

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

# Create main API resources
echo "Creating main API resources..."

# Products resources
create_resource $ROOT_RESOURCE_ID "products" "PRODUCTS_RESOURCE_ID"
create_resource $PRODUCTS_RESOURCE_ID "{id}" "PRODUCTS_ID_RESOURCE_ID"
create_resource $PRODUCTS_ID_RESOURCE_ID "reviews" "PRODUCTS_ID_REVIEWS_RESOURCE_ID"
create_resource $PRODUCTS_RESOURCE_ID "categories" "PRODUCTS_CATEGORIES_RESOURCE_ID"
create_resource $PRODUCTS_RESOURCE_ID "featured" "PRODUCTS_FEATURED_RESOURCE_ID"

# Cart resources
create_resource $ROOT_RESOURCE_ID "cart" "CART_RESOURCE_ID"
create_resource $CART_RESOURCE_ID "{userId}" "CART_USER_ID_RESOURCE_ID"
create_resource $CART_USER_ID_RESOURCE_ID "items" "CART_USER_ID_ITEMS_RESOURCE_ID"
create_resource $CART_USER_ID_ITEMS_RESOURCE_ID "{itemId}" "CART_USER_ID_ITEMS_ITEM_ID_RESOURCE_ID"
create_resource $CART_USER_ID_RESOURCE_ID "clear" "CART_USER_ID_CLEAR_RESOURCE_ID"

# Orders resources
create_resource $ROOT_RESOURCE_ID "orders" "ORDERS_RESOURCE_ID"
create_resource $ORDERS_RESOURCE_ID "{orderId}" "ORDERS_ORDER_ID_RESOURCE_ID"
create_resource $ORDERS_ORDER_ID_RESOURCE_ID "cancel" "ORDERS_ORDER_ID_CANCEL_RESOURCE_ID"
create_resource $ORDERS_RESOURCE_ID "user" "ORDERS_USER_RESOURCE_ID"
create_resource $ORDERS_USER_RESOURCE_ID "{userId}" "ORDERS_USER_USER_ID_RESOURCE_ID"

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
create_resource $REVIEWS_RESOURCE_ID "product" "REVIEWS_PRODUCT_RESOURCE_ID"
create_resource $REVIEWS_PRODUCT_RESOURCE_ID "{productId}" "REVIEWS_PRODUCT_PRODUCT_ID_RESOURCE_ID"

# Search resources
create_resource $ROOT_RESOURCE_ID "search" "SEARCH_RESOURCE_ID"
create_resource $SEARCH_RESOURCE_ID "products" "SEARCH_PRODUCTS_RESOURCE_ID"
create_resource $SEARCH_RESOURCE_ID "suggestions" "SEARCH_SUGGESTIONS_RESOURCE_ID"
create_resource $SEARCH_RESOURCE_ID "autocomplete" "SEARCH_AUTOCOMPLETE_RESOURCE_ID"
create_resource $SEARCH_RESOURCE_ID "filters" "SEARCH_FILTERS_RESOURCE_ID"

# Chat resources
create_resource $ROOT_RESOURCE_ID "chat" "CHAT_RESOURCE_ID"
create_resource $CHAT_RESOURCE_ID "sessions" "CHAT_SESSIONS_RESOURCE_ID"
create_resource $CHAT_SESSIONS_RESOURCE_ID "{sessionId}" "CHAT_SESSIONS_SESSION_ID_RESOURCE_ID"
create_resource $CHAT_SESSIONS_SESSION_ID_RESOURCE_ID "messages" "CHAT_SESSIONS_SESSION_ID_MESSAGES_RESOURCE_ID"

# Analytics resources
create_resource $ROOT_RESOURCE_ID "analytics" "ANALYTICS_RESOURCE_ID"
create_resource $ANALYTICS_RESOURCE_ID "events" "ANALYTICS_EVENTS_RESOURCE_ID"
create_resource $ANALYTICS_RESOURCE_ID "dashboard" "ANALYTICS_DASHBOARD_RESOURCE_ID"
create_resource $ANALYTICS_RESOURCE_ID "reports" "ANALYTICS_REPORTS_RESOURCE_ID"

echo "All resources created successfully!"

# Create methods
echo "Creating API methods..."

# Auth base resource methods
create_method $AUTH_RESOURCE_ID "GET" "NONE" "" $AUTH_LAMBDA_ARN "AuthGET"
create_method $AUTH_RESOURCE_ID "POST" "NONE" "" $AUTH_LAMBDA_ARN "AuthPOST"

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

# Product methods (no authorization required)
# Base products resource - GET for listing products, POST for creating products
create_method $PRODUCTS_RESOURCE_ID "GET" "NONE" "" $PRODUCT_LAMBDA_ARN "ProductsGET"
create_method $PRODUCTS_RESOURCE_ID "POST" "COGNITO_USER_POOLS" $COGNITO_AUTHORIZER_ID $PRODUCT_LAMBDA_ARN "ProductsPOST"

# Individual product methods
create_method $PRODUCTS_ID_RESOURCE_ID "GET" "NONE" "" $PRODUCT_LAMBDA_ARN "ProductsIdGET"
create_method $PRODUCTS_CATEGORIES_RESOURCE_ID "GET" "NONE" "" $PRODUCT_LAMBDA_ARN "ProductsCategoriesGET"
create_method $PRODUCTS_FEATURED_RESOURCE_ID "GET" "NONE" "" $PRODUCT_LAMBDA_ARN "ProductsFeaturedGET"
create_method $PRODUCTS_ID_REVIEWS_RESOURCE_ID "GET" "NONE" "" $PRODUCT_LAMBDA_ARN "ProductsIdReviewsGET"

# Cart base resource methods
create_method $CART_RESOURCE_ID "GET" "COGNITO_USER_POOLS" $COGNITO_AUTHORIZER_ID $CART_LAMBDA_ARN "CartGET"
create_method $CART_RESOURCE_ID "POST" "COGNITO_USER_POOLS" $COGNITO_AUTHORIZER_ID $CART_LAMBDA_ARN "CartPOST"

# Cart methods (Cognito authorization required)
create_method $CART_USER_ID_RESOURCE_ID "GET" "COGNITO_USER_POOLS" $COGNITO_AUTHORIZER_ID $CART_LAMBDA_ARN "CartUserIdGET"
create_method $CART_USER_ID_ITEMS_RESOURCE_ID "POST" "COGNITO_USER_POOLS" $COGNITO_AUTHORIZER_ID $CART_LAMBDA_ARN "CartUserIdItemsPOST"
create_method $CART_USER_ID_ITEMS_ITEM_ID_RESOURCE_ID "GET" "COGNITO_USER_POOLS" $COGNITO_AUTHORIZER_ID $CART_LAMBDA_ARN "CartUserIdItemsItemIdGET"
create_method $CART_USER_ID_ITEMS_ITEM_ID_RESOURCE_ID "PUT" "COGNITO_USER_POOLS" $COGNITO_AUTHORIZER_ID $CART_LAMBDA_ARN "CartUserIdItemsItemIdPUT"
create_method $CART_USER_ID_ITEMS_ITEM_ID_RESOURCE_ID "DELETE" "COGNITO_USER_POOLS" $COGNITO_AUTHORIZER_ID $CART_LAMBDA_ARN "CartUserIdItemsItemIdDELETE"
create_method $CART_USER_ID_CLEAR_RESOURCE_ID "DELETE" "COGNITO_USER_POOLS" $COGNITO_AUTHORIZER_ID $CART_LAMBDA_ARN "CartUserIdClearDELETE"

# Order methods (Cognito authorization required)
# Base orders resource - GET for listing orders, POST for creating orders
create_method $ORDERS_RESOURCE_ID "GET" "COGNITO_USER_POOLS" $COGNITO_AUTHORIZER_ID $ORDER_LAMBDA_ARN "OrdersGET"
create_method $ORDERS_RESOURCE_ID "POST" "COGNITO_USER_POOLS" $COGNITO_AUTHORIZER_ID $ORDER_LAMBDA_ARN "OrdersPOST"

# Individual order methods
create_method $ORDERS_ORDER_ID_RESOURCE_ID "GET" "COGNITO_USER_POOLS" $COGNITO_AUTHORIZER_ID $ORDER_LAMBDA_ARN "OrdersOrderIdGET"
create_method $ORDERS_ORDER_ID_RESOURCE_ID "PUT" "COGNITO_USER_POOLS" $COGNITO_AUTHORIZER_ID $ORDER_LAMBDA_ARN "OrdersOrderIdPUT"
create_method $ORDERS_ORDER_ID_CANCEL_RESOURCE_ID "POST" "COGNITO_USER_POOLS" $COGNITO_AUTHORIZER_ID $ORDER_LAMBDA_ARN "OrdersOrderIdCancelPOST"
create_method $ORDERS_USER_USER_ID_RESOURCE_ID "GET" "COGNITO_USER_POOLS" $COGNITO_AUTHORIZER_ID $ORDER_LAMBDA_ARN "OrdersUserUserIdGET"

# Review methods (mixed authorization)
create_method $REVIEWS_RESOURCE_ID "GET" "NONE" "" $REVIEW_LAMBDA_ARN "ReviewsGET"
create_method $REVIEWS_RESOURCE_ID "POST" "COGNITO_USER_POOLS" $COGNITO_AUTHORIZER_ID $REVIEW_LAMBDA_ARN "ReviewsPOST"
create_method $REVIEWS_REVIEW_ID_RESOURCE_ID "GET" "NONE" "" $REVIEW_LAMBDA_ARN "ReviewsReviewIdGET"
create_method $REVIEWS_REVIEW_ID_HELPFUL_RESOURCE_ID "POST" "COGNITO_USER_POOLS" $COGNITO_AUTHORIZER_ID $REVIEW_LAMBDA_ARN "ReviewsReviewIdHelpfulPOST"
create_method $REVIEWS_PRODUCT_PRODUCT_ID_RESOURCE_ID "GET" "NONE" "" $REVIEW_LAMBDA_ARN "ReviewsProductProductIdGET"

# Search base resource methods
create_method $SEARCH_RESOURCE_ID "GET" "NONE" "" $SEARCH_LAMBDA_ARN "SearchGET"
create_method $SEARCH_RESOURCE_ID "POST" "NONE" "" $SEARCH_LAMBDA_ARN "SearchPOST"

# Search methods (no authorization required)
create_method $SEARCH_PRODUCTS_RESOURCE_ID "GET" "NONE" "" $SEARCH_LAMBDA_ARN "SearchProductsGET"
create_method $SEARCH_PRODUCTS_RESOURCE_ID "POST" "NONE" "" $SEARCH_LAMBDA_ARN "SearchProductsPOST"
create_method $SEARCH_SUGGESTIONS_RESOURCE_ID "GET" "NONE" "" $SEARCH_LAMBDA_ARN "SearchSuggestionsGET"
create_method $SEARCH_AUTOCOMPLETE_RESOURCE_ID "GET" "NONE" "" $SEARCH_LAMBDA_ARN "SearchAutocompleteGET"
create_method $SEARCH_FILTERS_RESOURCE_ID "GET" "NONE" "" $SEARCH_LAMBDA_ARN "SearchFiltersGET"

# Analytics base resource methods
create_method $ANALYTICS_RESOURCE_ID "GET" "NONE" "" $ANALYTICS_LAMBDA_ARN "AnalyticsGET"
create_method $ANALYTICS_RESOURCE_ID "POST" "NONE" "" $ANALYTICS_LAMBDA_ARN "AnalyticsPOST"

# Analytics methods (no authorization required)
create_method $ANALYTICS_EVENTS_RESOURCE_ID "POST" "NONE" "" $ANALYTICS_LAMBDA_ARN "AnalyticsEventsPOST"
create_method $ANALYTICS_DASHBOARD_RESOURCE_ID "GET" "NONE" "" $ANALYTICS_LAMBDA_ARN "AnalyticsDashboardGET"
create_method $ANALYTICS_REPORTS_RESOURCE_ID "GET" "NONE" "" $ANALYTICS_LAMBDA_ARN "AnalyticsReportsGET"

# Chat base resource methods
create_method $CHAT_RESOURCE_ID "GET" "COGNITO_USER_POOLS" $COGNITO_AUTHORIZER_ID $CHAT_LAMBDA_ARN "ChatGET"
create_method $CHAT_RESOURCE_ID "POST" "COGNITO_USER_POOLS" $COGNITO_AUTHORIZER_ID $CHAT_LAMBDA_ARN "ChatPOST"

# Chat methods (Cognito authorization required)
create_method $CHAT_SESSIONS_RESOURCE_ID "GET" "COGNITO_USER_POOLS" $COGNITO_AUTHORIZER_ID $CHAT_LAMBDA_ARN "ChatSessionsGET"
create_method $CHAT_SESSIONS_RESOURCE_ID "POST" "COGNITO_USER_POOLS" $COGNITO_AUTHORIZER_ID $CHAT_LAMBDA_ARN "ChatSessionsPOST"
create_method $CHAT_SESSIONS_SESSION_ID_RESOURCE_ID "GET" "COGNITO_USER_POOLS" $COGNITO_AUTHORIZER_ID $CHAT_LAMBDA_ARN "ChatSessionsSessionIdGET"
create_method $CHAT_SESSIONS_SESSION_ID_RESOURCE_ID "DELETE" "COGNITO_USER_POOLS" $COGNITO_AUTHORIZER_ID $CHAT_LAMBDA_ARN "ChatSessionsSessionIdDELETE"
create_method $CHAT_SESSIONS_SESSION_ID_MESSAGES_RESOURCE_ID "GET" "COGNITO_USER_POOLS" $COGNITO_AUTHORIZER_ID $CHAT_LAMBDA_ARN "ChatSessionsSessionIdMessagesGET"
create_method $CHAT_SESSIONS_SESSION_ID_MESSAGES_RESOURCE_ID "POST" "COGNITO_USER_POOLS" $COGNITO_AUTHORIZER_ID $CHAT_LAMBDA_ARN "ChatSessionsSessionIdMessagesPOST"

echo "All methods created successfully!"

# Create OPTIONS methods for CORS support
echo "Creating OPTIONS methods for CORS support..."

# Root resource OPTIONS
create_options_method $ROOT_RESOURCE_ID "Root" "GET,OPTIONS"

# Auth resources OPTIONS
create_options_method $AUTH_RESOURCE_ID "Auth" "GET,POST,OPTIONS"
create_options_method $AUTH_REGISTER_RESOURCE_ID "AuthRegister" "POST,OPTIONS"
create_options_method $AUTH_LOGIN_RESOURCE_ID "AuthLogin" "POST,OPTIONS"
create_options_method $AUTH_LOGOUT_RESOURCE_ID "AuthLogout" "POST,OPTIONS"
create_options_method $AUTH_PROFILE_RESOURCE_ID "AuthProfile" "GET,PUT,OPTIONS"
create_options_method $AUTH_REFRESH_RESOURCE_ID "AuthRefresh" "POST,OPTIONS"
create_options_method $AUTH_VERIFY_RESOURCE_ID "AuthVerify" "GET,OPTIONS"
create_options_method $AUTH_RESET_PASSWORD_RESOURCE_ID "AuthResetPassword" "POST,OPTIONS"

# Products resources OPTIONS
create_options_method $PRODUCTS_RESOURCE_ID "Products" "GET,POST,OPTIONS"
create_options_method $PRODUCTS_ID_RESOURCE_ID "ProductsId" "GET,OPTIONS"
create_options_method $PRODUCTS_ID_REVIEWS_RESOURCE_ID "ProductsIdReviews" "GET,OPTIONS"
create_options_method $PRODUCTS_CATEGORIES_RESOURCE_ID "ProductsCategories" "GET,OPTIONS"
create_options_method $PRODUCTS_FEATURED_RESOURCE_ID "ProductsFeatured" "GET,OPTIONS"

# Cart resources OPTIONS
create_options_method $CART_RESOURCE_ID "Cart" "GET,POST,OPTIONS"
create_options_method $CART_USER_ID_RESOURCE_ID "CartUserId" "GET,OPTIONS"
create_options_method $CART_USER_ID_ITEMS_RESOURCE_ID "CartUserIdItems" "POST,OPTIONS"
create_options_method $CART_USER_ID_ITEMS_ITEM_ID_RESOURCE_ID "CartUserIdItemsItemId" "GET,PUT,DELETE,OPTIONS"
create_options_method $CART_USER_ID_CLEAR_RESOURCE_ID "CartUserIdClear" "DELETE,OPTIONS"

# Orders resources OPTIONS
create_options_method $ORDERS_RESOURCE_ID "Orders" "GET,POST,OPTIONS"
create_options_method $ORDERS_ORDER_ID_RESOURCE_ID "OrdersOrderId" "GET,PUT,OPTIONS"
create_options_method $ORDERS_ORDER_ID_CANCEL_RESOURCE_ID "OrdersOrderIdCancel" "POST,OPTIONS"
create_options_method $ORDERS_USER_RESOURCE_ID "OrdersUser" "OPTIONS"
create_options_method $ORDERS_USER_USER_ID_RESOURCE_ID "OrdersUserUserId" "GET,OPTIONS"

# Reviews resources OPTIONS
create_options_method $REVIEWS_RESOURCE_ID "Reviews" "GET,POST,OPTIONS"
create_options_method $REVIEWS_REVIEW_ID_RESOURCE_ID "ReviewsReviewId" "GET,OPTIONS"
create_options_method $REVIEWS_REVIEW_ID_HELPFUL_RESOURCE_ID "ReviewsReviewIdHelpful" "POST,OPTIONS"
create_options_method $REVIEWS_PRODUCT_RESOURCE_ID "ReviewsProduct" "OPTIONS"
create_options_method $REVIEWS_PRODUCT_PRODUCT_ID_RESOURCE_ID "ReviewsProductProductId" "GET,OPTIONS"

# Search resources OPTIONS
create_options_method $SEARCH_RESOURCE_ID "Search" "GET,POST,OPTIONS"
create_options_method $SEARCH_PRODUCTS_RESOURCE_ID "SearchProducts" "GET,POST,OPTIONS"
create_options_method $SEARCH_SUGGESTIONS_RESOURCE_ID "SearchSuggestions" "GET,OPTIONS"
create_options_method $SEARCH_AUTOCOMPLETE_RESOURCE_ID "SearchAutocomplete" "GET,OPTIONS"
create_options_method $SEARCH_FILTERS_RESOURCE_ID "SearchFilters" "GET,OPTIONS"

# Chat resources OPTIONS
create_options_method $CHAT_RESOURCE_ID "Chat" "GET,POST,OPTIONS"
create_options_method $CHAT_SESSIONS_RESOURCE_ID "ChatSessions" "GET,POST,OPTIONS"
create_options_method $CHAT_SESSIONS_SESSION_ID_RESOURCE_ID "ChatSessionsSessionId" "GET,DELETE,OPTIONS"
create_options_method $CHAT_SESSIONS_SESSION_ID_MESSAGES_RESOURCE_ID "ChatSessionsSessionIdMessages" "GET,POST,OPTIONS"

# Analytics resources OPTIONS
create_options_method $ANALYTICS_RESOURCE_ID "Analytics" "GET,POST,OPTIONS"
create_options_method $ANALYTICS_EVENTS_RESOURCE_ID "AnalyticsEvents" "POST,OPTIONS"
create_options_method $ANALYTICS_DASHBOARD_RESOURCE_ID "AnalyticsDashboard" "GET,OPTIONS"
create_options_method $ANALYTICS_REPORTS_RESOURCE_ID "AnalyticsReports" "GET,OPTIONS"

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
        --function-name "unicorn-ecommerce-$ENVIRONMENT-$function_name" \
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

# Save configuration to file
cat > api-gateway-config.json << EOF
{
  "apiGatewayId": "$API_GATEWAY_ID",
  "apiGatewayUrl": "$API_URL",
  "cognitoAuthorizerId": "$COGNITO_AUTHORIZER_ID",
  "deploymentId": "$DEPLOYMENT_ID",
  "environment": "$ENVIRONMENT",
  "region": "$AWS_REGION",
  "userPoolId": "$USER_POOL_ID"
}
EOF

echo "Configuration saved to api-gateway-config.json"

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
- Cart endpoints: GET (cart), POST (add items), GET/PUT/DELETE (manage items)
- Order endpoints: GET (view orders), PUT (update), POST (cancel)
- Review endpoints: GET (view), POST (create, mark helpful)
- Search endpoints: GET/POST (search products), GET (suggestions, autocomplete, filters)
- Chat endpoints: POST (create session), GET/DELETE (manage sessions), GET/POST (messages)
- Analytics endpoints: POST (events), GET (dashboard, reports)

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
echo "Setup completed successfully!"
echo "CORS summary saved to cors-config-summary.txt"