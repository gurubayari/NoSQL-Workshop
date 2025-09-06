#!/bin/bash

# AWS NoSQL Workshop - Frontend Deployment Script
# This script deploys pre-built frontend artifacts to S3 and CloudFront
# Usage: ./deploy-frontend.sh <s3-bucket> <api-gateway-url> <user-pool-id> <user-pool-client-id> [cloudfront-dist-id] [cloudfront-domain] [user-pool-region]

set -e

# Configuration - Accept command line inputs or use defaults
PROJECT_NAME="${1:-unicorn-ecommerce}"
ENVIRONMENT="${2:-dev}"
REGION="${3:-${AWS_DEFAULT_REGION:-us-east-1}}"

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

# Show usage information
show_usage() {
    echo -e "${BLUE}AWS NoSQL Workshop - Frontend Deployment${NC}"
    echo "=================================================="
    echo ""
    echo "Usage: $0 [project-name] [environment] [region] <s3-bucket> <api-gateway-url> <user-pool-id> <user-pool-client-id> [cloudfront-dist-id] [cloudfront-domain] [user-pool-region]"
    echo ""
    echo "Optional Configuration Parameters (first 3):"
    echo "  project-name        Project name (defaults to 'unicorn-ecommerce')"
    echo "  environment         Environment name (defaults to 'dev')"
    echo "  region              AWS region (defaults to current AWS region)"
    echo ""
    echo "Required Parameters:"
    echo "  s3-bucket           S3 bucket name for hosting the website"
    echo "  api-gateway-url     API Gateway base URL (e.g., https://abc123.execute-api.us-east-1.amazonaws.com/dev)"
    echo "  user-pool-id        Cognito User Pool ID"
    echo "  user-pool-client-id Cognito User Pool Client ID"
    echo ""
    echo "Optional Parameters:"
    echo "  cloudfront-dist-id  CloudFront Distribution ID (for cache invalidation)"
    echo "  cloudfront-domain   CloudFront domain name (e.g., d1234567890.cloudfront.net)"
    echo "  user-pool-region    Cognito User Pool region (defaults to current AWS region)"
    echo ""
    echo "Examples:"
    echo "  # Basic deployment with defaults"
    echo "  $0 my-website-bucket https://api123.execute-api.us-east-1.amazonaws.com/dev us-east-1_ABC123 1234567890abcdef"
    echo ""
    echo "  # Custom project configuration"
    echo "  $0 my-project prod us-west-2 my-website-bucket https://api123.execute-api.us-west-2.amazonaws.com/prod us-west-2_ABC123 1234567890abcdef"
    echo ""
    echo "  # Full deployment with CloudFront"
    echo "  $0 unicorn-ecommerce dev us-east-1 my-website-bucket https://api123.execute-api.us-east-1.amazonaws.com/dev us-east-1_ABC123 1234567890abcdef E1234567890ABC d1234567890.cloudfront.net"
    echo ""
    echo "Current Configuration:"
    echo "  Project: $PROJECT_NAME"
    echo "  Environment: $ENVIRONMENT"
    echo "  Region: $REGION"
    echo ""
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
    
    # Check if build artifacts exist
    if [ ! -d "build-artifacts" ]; then
        error "Build artifacts directory not found. Please run ./build-frontend.sh first."
        exit 1
    fi
    
    if [ ! -f "build-artifacts/build-manifest.json" ]; then
        error "Build manifest not found. Please run ./build-frontend.sh first."
        exit 1
    fi
    
    if [ ! -d "build-artifacts/build" ]; then
        error "Build directory not found in artifacts. Please run ./build-frontend.sh first."
        exit 1
    fi
    
    success "Prerequisites check passed"
}

# Parse command line arguments
parse_arguments() {
    # Check if help is requested
    if [ "$1" = "-h" ] || [ "$1" = "--help" ] || [ "$1" = "help" ]; then
        show_usage
        exit 0
    fi
    
    # Determine if first 3 args are config parameters or deployment parameters
    # If we have 7+ args, assume first 3 are config parameters
    if [ $# -ge 7 ]; then
        # First 3 are config parameters, shift them
        shift 3
        # Remaining parameters are deployment parameters
        S3_BUCKET_NAME="$1"
        API_GATEWAY_URL="$2"
        USER_POOL_ID="$3"
        USER_POOL_CLIENT_ID="$4"
        
        # Optional parameters
        CLOUDFRONT_DISTRIBUTION_ID="${5:-}"
        CLOUDFRONT_DOMAIN="${6:-}"
        USER_POOL_REGION="$REGION"
    else
        # Check minimum required arguments (old format)
        if [ $# -lt 4 ]; then
            error "Insufficient arguments provided"
            echo ""
            show_usage
            exit 1
        fi
        
        # Required parameters (old format)
        S3_BUCKET_NAME="$1"
        API_GATEWAY_URL="$2"
        USER_POOL_ID="$3"
        USER_POOL_CLIENT_ID="$4"
        
        # Optional parameters
        CLOUDFRONT_DISTRIBUTION_ID="${5:-}"
        CLOUDFRONT_DOMAIN="${6:-}"
        USER_POOL_REGION="$REGION"
    fi
    
    # Validate required parameters
    if [ -z "$S3_BUCKET_NAME" ]; then
        error "S3 bucket name cannot be empty"
        exit 1
    fi
    
    if [ -z "$API_GATEWAY_URL" ]; then
        error "API Gateway URL cannot be empty"
        exit 1
    fi
    
    if [ -z "$USER_POOL_ID" ]; then
        error "User Pool ID cannot be empty"
        exit 1
    fi
    
    if [ -z "$USER_POOL_CLIENT_ID" ]; then
        error "User Pool Client ID cannot be empty"
        exit 1
    fi
    
    # Validate URL format
    if [[ ! "$API_GATEWAY_URL" =~ ^https?:// ]]; then
        error "API Gateway URL must start with http:// or https://"
        exit 1
    fi
    
    # Validate configuration parameters
    if [ -z "$PROJECT_NAME" ]; then
        error "Project name cannot be empty"
        exit 1
    fi
    
    if [ -z "$ENVIRONMENT" ]; then
        error "Environment cannot be empty"
        exit 1
    fi
    
    if [ -z "$REGION" ]; then
        error "Region cannot be empty"
        exit 1
    fi
    
    log "Deployment parameters parsed successfully"
}

# Display deployment parameters
display_deployment_parameters() {
    log "Deployment parameters:"
    echo ""
    echo "Required Parameters:"
    echo "  S3 Bucket: $S3_BUCKET_NAME"
    echo "  API Gateway URL: $API_GATEWAY_URL"
    echo "  User Pool ID: $USER_POOL_ID"
    echo "  User Pool Client ID: $USER_POOL_CLIENT_ID"
    echo "  User Pool Region: $USER_POOL_REGION"
    echo ""
    echo "Optional Parameters:"
    echo "  CloudFront Distribution ID: ${CLOUDFRONT_DISTRIBUTION_ID:-'Not provided'}"
    echo "  CloudFront Domain: ${CLOUDFRONT_DOMAIN:-'Not provided'}"
    echo ""
    echo "Environment:"
    echo "  Project: $PROJECT_NAME"
    echo "  Environment: $ENVIRONMENT"
    echo "  AWS Region: $REGION"
    echo ""
}

# Update environment variables in build
update_environment_variables() {
    log "Updating environment variables in build artifacts..."
    
    # Create deployment-ready build directory
    rm -rf build-deployment
    cp -r build-artifacts/build build-deployment
    
    # Set default values for optional parameters
    CLOUDFRONT_DOMAIN_VALUE=${CLOUDFRONT_DOMAIN:-""}
    
    # Display environment variables being set
    log "Environment variables to be replaced:"
    echo "  __API_GATEWAY_URL__ -> $API_GATEWAY_URL"
    echo "  __USER_POOL_ID__ -> $USER_POOL_ID"
    echo "  __USER_POOL_CLIENT_ID__ -> $USER_POOL_CLIENT_ID"
    echo "  __USER_POOL_REGION__ -> $USER_POOL_REGION"
    echo "  __CLOUDFRONT_DOMAIN__ -> $CLOUDFRONT_DOMAIN_VALUE"
    echo "  __AWS_REGION__ -> $REGION"
    echo "  __PROJECT_NAME__ -> $PROJECT_NAME"
    echo "  __ENVIRONMENT__ -> $ENVIRONMENT"
    echo ""
    
    # Update environment variables in JavaScript files
    log "Updating JavaScript files with environment variables..."
    
    find build-deployment -name "*.js" -type f | while read file; do
        # Replace placeholders with actual values
        sed -i.bak \
            -e "s|__API_GATEWAY_URL__|$API_GATEWAY_URL|g" \
            -e "s|__USER_POOL_ID__|$USER_POOL_ID|g" \
            -e "s|__USER_POOL_CLIENT_ID__|$USER_POOL_CLIENT_ID|g" \
            -e "s|__USER_POOL_REGION__|$USER_POOL_REGION|g" \
            -e "s|__CLOUDFRONT_DOMAIN__|$CLOUDFRONT_DOMAIN_VALUE|g" \
            -e "s|__AWS_REGION__|$REGION|g" \
            -e "s|__PROJECT_NAME__|$PROJECT_NAME|g" \
            -e "s|__ENVIRONMENT__|$ENVIRONMENT|g" \
            "$file"
        
        # Remove backup file
        rm -f "$file.bak"
        
        # Log replacement for debugging
        log "Updated environment variables in: $file"
    done
    
    # Update environment variables in HTML files
    log "Updating HTML files with environment variables..."
    
    find build-deployment -name "*.html" -type f | while read file; do
        # Replace placeholders with actual values
        sed -i.bak \
            -e "s|__API_GATEWAY_URL__|$API_GATEWAY_URL|g" \
            -e "s|__USER_POOL_ID__|$USER_POOL_ID|g" \
            -e "s|__USER_POOL_CLIENT_ID__|$USER_POOL_CLIENT_ID|g" \
            -e "s|__USER_POOL_REGION__|$USER_POOL_REGION|g" \
            -e "s|__CLOUDFRONT_DOMAIN__|$CLOUDFRONT_DOMAIN_VALUE|g" \
            -e "s|__AWS_REGION__|$REGION|g" \
            -e "s|__PROJECT_NAME__|$PROJECT_NAME|g" \
            -e "s|__ENVIRONMENT__|$ENVIRONMENT|g" \
            "$file"
        
        # Remove backup file
        rm -f "$file.bak"
        
        # Log replacement for debugging
        log "Updated environment variables in: $file"
    done
    
    # Update environment variables in CSS files
    log "Updating CSS files with environment variables..."
    
    find build-deployment -name "*.css" -type f | while read file; do
        # Replace placeholders with actual values
        sed -i.bak \
            -e "s|__API_GATEWAY_URL__|$API_GATEWAY_URL|g" \
            -e "s|__USER_POOL_ID__|$USER_POOL_ID|g" \
            -e "s|__USER_POOL_CLIENT_ID__|$USER_POOL_CLIENT_ID|g" \
            -e "s|__USER_POOL_REGION__|$USER_POOL_REGION|g" \
            -e "s|__CLOUDFRONT_DOMAIN__|$CLOUDFRONT_DOMAIN_VALUE|g" \
            -e "s|__AWS_REGION__|$REGION|g" \
            -e "s|__PROJECT_NAME__|$PROJECT_NAME|g" \
            -e "s|__ENVIRONMENT__|$ENVIRONMENT|g" \
            "$file"
        
        # Remove backup file
        rm -f "$file.bak"
        
        # Log replacement for debugging
        log "Updated environment variables in: $file"
    done
    
    # Update environment variables in JSON files
    log "Updating JSON files with environment variables..."
    
    find build-deployment -name "*.json" -type f | while read file; do
        # Replace placeholders with actual values
        sed -i.bak \
            -e "s|__API_GATEWAY_URL__|$API_GATEWAY_URL|g" \
            -e "s|__USER_POOL_ID__|$USER_POOL_ID|g" \
            -e "s|__USER_POOL_CLIENT_ID__|$USER_POOL_CLIENT_ID|g" \
            -e "s|__USER_POOL_REGION__|$USER_POOL_REGION|g" \
            -e "s|__CLOUDFRONT_DOMAIN__|$CLOUDFRONT_DOMAIN_VALUE|g" \
            -e "s|__AWS_REGION__|$REGION|g" \
            -e "s|__PROJECT_NAME__|$PROJECT_NAME|g" \
            -e "s|__ENVIRONMENT__|$ENVIRONMENT|g" \
            "$file"
        
        # Remove backup file
        rm -f "$file.bak"
        
        # Log replacement for debugging
        log "Updated environment variables in: $file"
    done
    
    # Re-compress updated files if gzip is available
    if command -v gzip &> /dev/null; then
        log "Re-compressing updated files..."
        find build-deployment -name "*.js" -o -name "*.css" -o -name "*.html" | while read file; do
            gzip -c "$file" > "$file.gz"
        done
    fi
    
    # Verify replacements were successful
    log "Verifying environment variable replacements..."
    
    UNREPLACED_PLACEHOLDERS=$(find build-deployment -name "*.js" -o -name "*.html" -o -name "*.css" -o -name "*.json" | xargs grep -l "__.*__" 2>/dev/null || true)
    
    if [ -n "$UNREPLACED_PLACEHOLDERS" ]; then
        warning "Found unreplaced placeholders in the following files:"
        echo "$UNREPLACED_PLACEHOLDERS" | while read file; do
            echo "  - $file"
            grep -n "__.*__" "$file" | head -3 | while read line; do
                echo "    $line"
            done
        done
        warning "Some placeholders may not have been replaced correctly"
    else
        success "All placeholders replaced successfully"
    fi
    
    success "Environment variables updated successfully"
}

# Deploy to S3 with aggressive cache management
deploy_to_s3() {
    log "Deploying to S3 bucket: $S3_BUCKET_NAME"
    
    # First, upload everything with no-cache to ensure immediate updates
    log "Initial upload with no-cache headers..."
    aws s3 sync build-deployment/ s3://$S3_BUCKET_NAME \
        --region $REGION \
        --delete \
        --cache-control "no-cache, no-store, must-revalidate" \
        --metadata-directive REPLACE \
        --exclude "*.gz"
    
    # Then set proper cache headers for static assets
    log "Setting long cache headers for static assets..."
    aws s3 cp s3://$S3_BUCKET_NAME/static/ s3://$S3_BUCKET_NAME/static/ \
        --recursive \
        --metadata-directive REPLACE \
        --cache-control "public, max-age=31536000, immutable" \
        --region $REGION 2>/dev/null || true
    
    # Ensure HTML files and service worker have no-cache headers
    log "Setting no-cache headers for HTML and service worker..."
    
    # Update index.html
    aws s3 cp s3://$S3_BUCKET_NAME/index.html s3://$S3_BUCKET_NAME/index.html \
        --metadata-directive REPLACE \
        --cache-control "no-cache, no-store, must-revalidate" \
        --region $REGION 2>/dev/null || true
    
    # Update service worker if it exists
    aws s3 cp s3://$S3_BUCKET_NAME/service-worker.js s3://$S3_BUCKET_NAME/service-worker.js \
        --metadata-directive REPLACE \
        --cache-control "no-cache, no-store, must-revalidate" \
        --region $REGION 2>/dev/null || true
    
    # Update manifest.json if it exists
    aws s3 cp s3://$S3_BUCKET_NAME/manifest.json s3://$S3_BUCKET_NAME/manifest.json \
        --metadata-directive REPLACE \
        --cache-control "no-cache, no-store, must-revalidate" \
        --region $REGION 2>/dev/null || true
    
    # Upload compressed files with proper encoding
    if command -v gzip &> /dev/null; then
        log "Uploading compressed files..."
        find build-deployment -name "*.gz" | while read file; do
            original_file=${file%.gz}
            relative_path=${original_file#build-deployment/}
            content_type=""
            cache_control="public, max-age=31536000, immutable"
            
            case "$original_file" in
                *.js) content_type="application/javascript" ;;
                *.css) content_type="text/css" ;;
                *.html) 
                    content_type="text/html"
                    cache_control="no-cache, no-store, must-revalidate"
                    ;;
            esac
            
            if [ -n "$content_type" ]; then
                aws s3 cp "$file" "s3://$S3_BUCKET_NAME/$relative_path" \
                    --region $REGION \
                    --content-encoding gzip \
                    --content-type "$content_type" \
                    --cache-control "$cache_control" \
                    --metadata-directive REPLACE
            fi
        done
    fi
    
    success "Deployment to S3 completed successfully"
}

# Aggressive CloudFront cache invalidation
invalidate_cloudfront() {
    if [ -n "$CLOUDFRONT_DISTRIBUTION_ID" ] && [ "$CLOUDFRONT_DISTRIBUTION_ID" != "None" ] && [ "$CLOUDFRONT_DISTRIBUTION_ID" != "" ]; then
        log "Performing aggressive CloudFront cache invalidation..."
        
        # Create multiple invalidations for different paths to ensure complete cache clearing
        PATHS_TO_INVALIDATE=(
            "/*"
            "/index.html"
            "/static/*"
            "/service-worker.js"
            "/manifest.json"
        )
        
        INVALIDATION_IDS=()
        
        for path in "${PATHS_TO_INVALIDATE[@]}"; do
            log "Creating invalidation for path: $path"
            INVALIDATION_ID=$(aws cloudfront create-invalidation \
                --distribution-id $CLOUDFRONT_DISTRIBUTION_ID \
                --paths "$path" \
                --query 'Invalidation.Id' \
                --output text 2>/dev/null || echo "failed")
            
            if [ "$INVALIDATION_ID" != "failed" ]; then
                INVALIDATION_IDS+=("$INVALIDATION_ID")
                log "Created invalidation: $INVALIDATION_ID for path: $path"
            else
                warning "Failed to create invalidation for path: $path"
            fi
        done
        
        # Wait for the main invalidation to complete
        if [ ${#INVALIDATION_IDS[@]} -gt 0 ]; then
            MAIN_INVALIDATION_ID=${INVALIDATION_IDS[0]}
            log "Waiting for main invalidation to complete: $MAIN_INVALIDATION_ID"
            
            aws cloudfront wait invalidation-completed \
                --distribution-id $CLOUDFRONT_DISTRIBUTION_ID \
                --id $MAIN_INVALIDATION_ID
            
            success "CloudFront cache invalidated successfully"
            log "Created ${#INVALIDATION_IDS[@]} invalidations total"
        else
            error "Failed to create any CloudFront invalidations"
        fi
    else
        warning "CloudFront distribution ID not provided, skipping cache invalidation"
        log "To enable CloudFront invalidation, provide the distribution ID as the 5th parameter"
    fi
}



# Generate deployment report
generate_deployment_report() {
    log "Generating deployment report..."
    
    REPORT_FILE="deployment-report-$(date +%Y%m%d-%H%M%S).json"
    
    # Read build manifest
    BUILD_INFO=$(cat build-artifacts/build-manifest.json | jq '.build_info')
    
    cat > $REPORT_FILE << EOF
{
  "deployment": {
    "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
    "project": "$PROJECT_NAME",
    "environment": "$ENVIRONMENT",
    "region": "$REGION",
    "version": "1.0.0"
  },
  "build_info": $BUILD_INFO,
  "infrastructure": {
    "s3_bucket": "$S3_BUCKET_NAME",
    "cloudfront_distribution_id": "$CLOUDFRONT_DISTRIBUTION_ID",
    "cloudfront_domain": "$CLOUDFRONT_DOMAIN",
    "api_gateway_url": "$API_GATEWAY_URL",
    "user_pool_id": "$USER_POOL_ID",
    "user_pool_client_id": "$USER_POOL_CLIENT_ID"
  },
  "endpoints": {
    "s3_website": "http://$S3_BUCKET_NAME.s3-website-$REGION.amazonaws.com",
    "cloudfront_url": "https://$CLOUDFRONT_DOMAIN",
    "api_base_url": "$API_GATEWAY_URL"
  },
  "environment_variables": {
    "REACT_APP_AWS_REGION": "$REGION",
    "REACT_APP_API_GATEWAY_URL": "$API_GATEWAY_URL",
    "REACT_APP_USER_POOL_ID": "$USER_POOL_ID",
    "REACT_APP_USER_POOL_CLIENT_ID": "$USER_POOL_CLIENT_ID",
    "REACT_APP_CLOUDFRONT_DOMAIN": "$CLOUDFRONT_DOMAIN",
    "REACT_APP_ENVIRONMENT": "$ENVIRONMENT",
    "REACT_APP_PROJECT_NAME": "$PROJECT_NAME",
    "REACT_APP_VERSION": "1.0.0"
  }
}
EOF
    
    success "Deployment report saved to: $REPORT_FILE"
}

# Cleanup deployment files
cleanup_deployment_files() {
    log "Cleaning up deployment files..."
    
    # Remove deployment build directory
    rm -rf build-deployment
    
    success "Deployment cleanup completed"
}

# Generate deployment summary
generate_deployment_summary() {
    log "Generating deployment summary..."
    
    echo ""
    echo "=========================================="
    echo "  FRONTEND DEPLOYMENT SUMMARY"
    echo "=========================================="
    echo "Project: $PROJECT_NAME"
    echo "Environment: $ENVIRONMENT"
    echo "Region: $REGION"
    echo "Timestamp: $(date)"
    echo ""
    echo "Deployed Endpoints:"
    echo "  S3 Website: http://$S3_BUCKET_NAME.s3-website-$REGION.amazonaws.com"
    if [ -n "$CLOUDFRONT_DOMAIN" ] && [ "$CLOUDFRONT_DOMAIN" != "None" ] && [ "$CLOUDFRONT_DOMAIN" != "" ]; then
        echo "  CloudFront: https://$CLOUDFRONT_DOMAIN"
    fi
    echo "  API Gateway: $API_GATEWAY_URL"
    echo ""
    echo "Configuration:"
    echo "  User Pool ID: $USER_POOL_ID"
    echo "  User Pool Client ID: $USER_POOL_CLIENT_ID"
    echo "  Region: $REGION"
    echo ""
    echo "Build Information:"
    if [ -f "build-artifacts/build-manifest.json" ]; then
        echo "  Build Size: $(cat build-artifacts/build-manifest.json | jq -r '.build_info.build_size')"
        echo "  Node Version: $(cat build-artifacts/build-manifest.json | jq -r '.build_info.node_version')"
        echo "  React Version: $(cat build-artifacts/build-manifest.json | jq -r '.build_info.react_version')"
    fi
    echo ""
    echo "Next Steps:"
    echo "1. Test the application in your browser"
    echo "2. Monitor CloudWatch logs"
    echo "3. Set up monitoring and alerts"
    echo ""
}

# Main execution
main() {
    # Show usage if no arguments provided
    if [ $# -eq 0 ]; then
        show_usage
        exit 1
    fi
    
    log "Starting Unicorn E-Commerce frontend deployment..."
    log "Configuration: Project=$PROJECT_NAME, Environment=$ENVIRONMENT, Region=$REGION"
    
    parse_arguments "$@"
    check_prerequisites
    display_deployment_parameters
    
    update_environment_variables
    deploy_to_s3
    invalidate_cloudfront
    generate_deployment_report
    cleanup_deployment_files
    generate_deployment_summary
    
    success "Frontend deployment completed successfully!"
    
    echo ""
    echo "🎉 Your Unicorn E-Commerce application is now live!"
    echo ""
    echo "Access URLs:"
    echo "  S3 Website: http://$S3_BUCKET_NAME.s3-website-$REGION.amazonaws.com"
    if [ -n "$CLOUDFRONT_DOMAIN" ] && [ "$CLOUDFRONT_DOMAIN" != "None" ] && [ "$CLOUDFRONT_DOMAIN" != "" ]; then
        echo "  CloudFront: https://$CLOUDFRONT_DOMAIN"
        echo ""
        echo "🚀 Primary URL: https://$CLOUDFRONT_DOMAIN"
    else
        echo ""
        echo "🚀 Primary URL: http://$S3_BUCKET_NAME.s3-website-$REGION.amazonaws.com"
    fi
    echo ""
    echo "Cache Management:"
    echo "  ✅ S3 cache headers optimized"
    if [ -n "$CLOUDFRONT_DISTRIBUTION_ID" ]; then
        echo "  ✅ CloudFront cache invalidated"
    else
        echo "  ⚠️  CloudFront cache invalidation skipped (no distribution ID provided)"
    fi
    echo ""
    echo "Note: Changes may take 5-15 minutes to fully propagate"
    echo "      Try hard refresh (Ctrl+F5 or Cmd+Shift+R) if needed"
}

# Handle script interruption
trap cleanup_deployment_files EXIT

# Run main function
main "$@"