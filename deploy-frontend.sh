#!/bin/bash

# AWS NoSQL Workshop - Frontend Deployment Script
# This script deploys pre-built frontend artifacts to S3 and CloudFront

set -e

# Configuration
PROJECT_NAME="unicorn-ecommerce"
ENVIRONMENT="dev"
REGION=${AWS_DEFAULT_REGION:-us-east-1}

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

echo -e "${BLUE}AWS NoSQL Workshop - Frontend Deployment${NC}"
echo "=================================================="
echo "Project: $PROJECT_NAME"
echo "Environment: $ENVIRONMENT"
echo "Region: $REGION"
echo ""

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

# Get deployment parameters
get_deployment_parameters() {
    log "Retrieving deployment parameters..."
    
    # Get parameters from command line or environment variables
    S3_BUCKET_NAME=${1:-$S3_BUCKET_NAME}
    CLOUDFRONT_DISTRIBUTION_ID=${2:-$CLOUDFRONT_DISTRIBUTION_ID}
    CLOUDFRONT_DOMAIN=${3:-$CLOUDFRONT_DOMAIN}
    API_GATEWAY_URL=${4:-$API_GATEWAY_URL}
    USER_POOL_ID=${5:-$USER_POOL_ID}
    USER_POOL_CLIENT_ID=${6:-$USER_POOL_CLIENT_ID}
    
    # Validate required parameters
    if [ -z "$S3_BUCKET_NAME" ]; then
        error "S3 Bucket Name is required (parameter 1 or S3_BUCKET_NAME env var)"
        exit 1
    fi
    
    if [ -z "$API_GATEWAY_URL" ]; then
        error "API Gateway URL is required (parameter 4 or API_GATEWAY_URL env var)"
        exit 1
    fi
    
    if [ -z "$USER_POOL_ID" ]; then
        error "User Pool ID is required (parameter 5 or USER_POOL_ID env var)"
        exit 1
    fi
    
    if [ -z "$USER_POOL_CLIENT_ID" ]; then
        error "User Pool Client ID is required (parameter 6 or USER_POOL_CLIENT_ID env var)"
        exit 1
    fi
    
    # Set defaults for optional parameters
    CLOUDFRONT_DISTRIBUTION_ID=${CLOUDFRONT_DISTRIBUTION_ID:-""}
    CLOUDFRONT_DOMAIN=${CLOUDFRONT_DOMAIN:-""}
    
    success "Deployment parameters retrieved successfully"
    log "S3 Bucket: $S3_BUCKET_NAME"
    log "CloudFront Distribution: $CLOUDFRONT_DISTRIBUTION_ID"
    log "CloudFront Domain: $CLOUDFRONT_DOMAIN"
    log "API Gateway URL: $API_GATEWAY_URL"
    log "User Pool ID: $USER_POOL_ID"
    log "User Pool Client ID: $USER_POOL_CLIENT_ID"
}

# Update environment variables in build
update_environment_variables() {
    log "Updating environment variables in build artifacts..."
    
    # Create deployment-ready build directory
    rm -rf build-deployment
    cp -r build-artifacts/build build-deployment
    
    # Update environment variables in JavaScript files
    log "Updating JavaScript files with environment variables..."
    
    find build-deployment -name "*.js" -type f | while read file; do
        # Replace placeholders with actual values
        sed -i.bak \
            -e "s|__API_GATEWAY_URL__|$API_GATEWAY_URL|g" \
            -e "s|__USER_POOL_ID__|$USER_POOL_ID|g" \
            -e "s|__USER_POOL_CLIENT_ID__|$USER_POOL_CLIENT_ID|g" \
            -e "s|__CLOUDFRONT_DOMAIN__|$CLOUDFRONT_DOMAIN|g" \
            "$file"
        
        # Remove backup file
        rm -f "$file.bak"
    done
    
    # Update environment variables in HTML files
    log "Updating HTML files with environment variables..."
    
    find build-deployment -name "*.html" -type f | while read file; do
        # Replace placeholders with actual values
        sed -i.bak \
            -e "s|__API_GATEWAY_URL__|$API_GATEWAY_URL|g" \
            -e "s|__USER_POOL_ID__|$USER_POOL_ID|g" \
            -e "s|__USER_POOL_CLIENT_ID__|$USER_POOL_CLIENT_ID|g" \
            -e "s|__CLOUDFRONT_DOMAIN__|$CLOUDFRONT_DOMAIN|g" \
            "$file"
        
        # Remove backup file
        rm -f "$file.bak"
    done
    
    # Re-compress updated files if gzip is available
    if command -v gzip &> /dev/null; then
        log "Re-compressing updated files..."
        find build-deployment -name "*.js" -o -name "*.css" -o -name "*.html" | while read file; do
            gzip -c "$file" > "$file.gz"
        done
    fi
    
    success "Environment variables updated successfully"
}

# Deploy to S3
deploy_to_s3() {
    log "Deploying to S3 bucket: $S3_BUCKET_NAME"
    
    # Sync build directory to S3 with optimized settings
    log "Uploading static assets (JS, CSS, images)..."
    aws s3 sync build-deployment/ s3://$S3_BUCKET_NAME \
        --region $REGION \
        --delete \
        --cache-control "public, max-age=31536000" \
        --exclude "*.html" \
        --exclude "service-worker.js" \
        --exclude "manifest.json" \
        --exclude "*.gz"
    
    # Upload HTML files with shorter cache control
    log "Uploading HTML files and service worker..."
    aws s3 sync build-deployment/ s3://$S3_BUCKET_NAME \
        --region $REGION \
        --cache-control "public, max-age=0, must-revalidate" \
        --include "*.html" \
        --include "service-worker.js" \
        --include "manifest.json" \
        --exclude "*"
    
    # Upload compressed files with proper encoding
    if command -v gzip &> /dev/null; then
        log "Uploading compressed files..."
        find build-deployment -name "*.gz" | while read file; do
            original_file=${file%.gz}
            relative_path=${original_file#build-deployment/}
            content_type=""
            
            case "$original_file" in
                *.js) content_type="application/javascript" ;;
                *.css) content_type="text/css" ;;
                *.html) content_type="text/html" ;;
            esac
            
            if [ -n "$content_type" ]; then
                aws s3 cp "$file" "s3://$S3_BUCKET_NAME/$relative_path" \
                    --region $REGION \
                    --content-encoding gzip \
                    --content-type "$content_type" \
                    --cache-control "public, max-age=31536000"
            fi
        done
    fi
    
    success "Deployment to S3 completed successfully"
}

# Invalidate CloudFront cache
invalidate_cloudfront() {
    if [ -n "$CLOUDFRONT_DISTRIBUTION_ID" ] && [ "$CLOUDFRONT_DISTRIBUTION_ID" != "None" ] && [ "$CLOUDFRONT_DISTRIBUTION_ID" != "" ]; then
        log "Invalidating CloudFront cache..."
        
        INVALIDATION_ID=$(aws cloudfront create-invalidation \
            --distribution-id $CLOUDFRONT_DISTRIBUTION_ID \
            --paths "/*" \
            --query 'Invalidation.Id' \
            --output text)
        
        log "CloudFront invalidation created: $INVALIDATION_ID"
        log "Waiting for invalidation to complete..."
        
        aws cloudfront wait invalidation-completed \
            --distribution-id $CLOUDFRONT_DISTRIBUTION_ID \
            --id $INVALIDATION_ID
        
        success "CloudFront cache invalidated successfully"
    else
        warning "CloudFront distribution ID not provided, skipping cache invalidation"
    fi
}

# Test deployment
test_deployment() {
    log "Testing deployment..."
    
    # Test S3 website endpoint
    if [ -n "$S3_BUCKET_NAME" ]; then
        S3_WEBSITE_URL="http://$S3_BUCKET_NAME.s3-website-$REGION.amazonaws.com"
        log "Testing S3 website endpoint: $S3_WEBSITE_URL"
        
        if curl -s -o /dev/null -w "%{http_code}" "$S3_WEBSITE_URL" | grep -q "200"; then
            success "S3 website endpoint is accessible"
        else
            warning "S3 website endpoint may not be accessible"
        fi
    fi
    
    # Test CloudFront distribution
    if [ -n "$CLOUDFRONT_DOMAIN" ] && [ "$CLOUDFRONT_DOMAIN" != "None" ] && [ "$CLOUDFRONT_DOMAIN" != "" ]; then
        CLOUDFRONT_URL="https://$CLOUDFRONT_DOMAIN"
        log "Testing CloudFront distribution: $CLOUDFRONT_URL"
        
        # Wait a bit for CloudFront to propagate
        sleep 10
        
        if curl -s -o /dev/null -w "%{http_code}" "$CLOUDFRONT_URL" | grep -q "200"; then
            success "CloudFront distribution is accessible"
        else
            warning "CloudFront distribution may still be propagating"
        fi
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
    echo "2. Run end-to-end tests"
    echo "3. Monitor CloudWatch logs"
    echo "4. Set up monitoring and alerts"
    echo ""
}

# Main execution
main() {
    log "Starting Unicorn E-Commerce frontend deployment..."
    
    check_prerequisites
    get_deployment_parameters "$@"
    update_environment_variables
    deploy_to_s3
    invalidate_cloudfront
    # test_deployment
    generate_deployment_report
    cleanup_deployment_files
    generate_deployment_summary
    
    success "Frontend deployment completed successfully!"
    
    if [ -n "$CLOUDFRONT_DOMAIN" ] && [ "$CLOUDFRONT_DOMAIN" != "None" ] && [ "$CLOUDFRONT_DOMAIN" != "" ]; then
        echo ""
        echo "🎉 Your Unicorn E-Commerce application is now live at:"
        echo "   https://$CLOUDFRONT_DOMAIN"
    else
        echo ""
        echo "🎉 Your Unicorn E-Commerce application is now live at:"
        echo "   http://$S3_BUCKET_NAME.s3-website-$REGION.amazonaws.com"
    fi
}

# Handle script interruption
trap cleanup_deployment_files EXIT

# Run main function
main "$@"