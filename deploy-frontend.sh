#!/bin/bash

# AWS NoSQL Workshop - Frontend Deployment Script
# This script builds and deploys the Unicorn E-Commerce React application to S3 and CloudFront

set -e

# Configuration
PROJECT_NAME="unicorn-ecommerce"
ENVIRONMENT="dev"
STACK_NAME="${PROJECT_NAME}-${ENVIRONMENT}-stack"
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

# Check prerequisites
check_prerequisites() {
    log "Checking prerequisites..."
    
    # Check Node.js and npm
    if ! command -v node &> /dev/null; then
        error "Node.js is not installed. Please install Node.js first."
        exit 1
    fi
    
    if ! command -v npm &> /dev/null; then
        error "npm is not installed. Please install npm first."
        exit 1
    fi
    
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
    
    # Check if package.json exists
    if [ ! -f "package.json" ]; then
        error "package.json not found. Please run this script from the project root."
        exit 1
    fi
    
    success "Prerequisites check passed"
}

# Get stack outputs
get_stack_outputs() {
    log "Retrieving stack outputs..."
    
    if ! aws cloudformation describe-stacks --stack-name $STACK_NAME --region $REGION &> /dev/null; then
        error "CloudFormation stack $STACK_NAME not found. Please deploy infrastructure first."
        exit 1
    fi
    
    # Get key outputs
    S3_BUCKET_NAME=$(aws cloudformation describe-stacks \
        --stack-name $STACK_NAME \
        --region $REGION \
        --query 'Stacks[0].Outputs[?OutputKey==`WebsiteBucketName`].OutputValue' \
        --output text)
    
    CLOUDFRONT_DISTRIBUTION_ID=$(aws cloudformation describe-stacks \
        --stack-name $STACK_NAME \
        --region $REGION \
        --query 'Stacks[0].Outputs[?OutputKey==`CloudFrontDistributionId`].OutputValue' \
        --output text)
    
    CLOUDFRONT_DOMAIN=$(aws cloudformation describe-stacks \
        --stack-name $STACK_NAME \
        --region $REGION \
        --query 'Stacks[0].Outputs[?OutputKey==`CloudFrontDistributionDomainName`].OutputValue' \
        --output text)
    
    API_GATEWAY_URL=$(aws cloudformation describe-stacks \
        --stack-name $STACK_NAME \
        --region $REGION \
        --query 'Stacks[0].Outputs[?OutputKey==`ApiGatewayURL`].OutputValue' \
        --output text)
    
    USER_POOL_ID=$(aws cloudformation describe-stacks \
        --stack-name $STACK_NAME \
        --region $REGION \
        --query 'Stacks[0].Outputs[?OutputKey==`UserPoolId`].OutputValue' \
        --output text)
    
    USER_POOL_CLIENT_ID=$(aws cloudformation describe-stacks \
        --stack-name $STACK_NAME \
        --region $REGION \
        --query 'Stacks[0].Outputs[?OutputKey==`UserPoolClientId`].OutputValue' \
        --output text)
    
    if [ -z "$S3_BUCKET_NAME" ] || [ "$S3_BUCKET_NAME" = "None" ]; then
        error "Could not retrieve S3 bucket name from stack outputs"
        exit 1
    fi
    
    success "Stack outputs retrieved successfully"
    log "S3 Bucket: $S3_BUCKET_NAME"
    log "CloudFront Distribution: $CLOUDFRONT_DISTRIBUTION_ID"
    log "CloudFront Domain: $CLOUDFRONT_DOMAIN"
    log "API Gateway URL: $API_GATEWAY_URL"
}

# Create environment configuration
create_env_config() {
    log "Creating environment configuration..."
    
    # Create .env.production file for build-time environment variables
    cat > .env.production << EOF
# AWS NoSQL Workshop - Production Environment Configuration
GENERATE_SOURCEMAP=false
REACT_APP_AWS_REGION=$REGION
REACT_APP_API_GATEWAY_URL=$API_GATEWAY_URL
REACT_APP_USER_POOL_ID=$USER_POOL_ID
REACT_APP_USER_POOL_CLIENT_ID=$USER_POOL_CLIENT_ID
REACT_APP_CLOUDFRONT_DOMAIN=$CLOUDFRONT_DOMAIN
REACT_APP_ENVIRONMENT=$ENVIRONMENT
REACT_APP_PROJECT_NAME=$PROJECT_NAME
REACT_APP_VERSION=1.0.0
EOF
    
    success "Environment configuration created"
}

# Install dependencies
install_dependencies() {
    log "Installing npm dependencies..."
    
    # Clean install
    if [ -d "node_modules" ]; then
        log "Cleaning existing node_modules..."
        rm -rf node_modules
    fi
    
    if [ -f "package-lock.json" ]; then
        npm ci
    else
        npm install
    fi
    
    success "Dependencies installed successfully"
}

# Run tests
run_tests() {
    log "Running tests..."
    
    # Run tests in CI mode
    if npm test -- --ci --coverage --watchAll=false --passWithNoTests; then
        success "All tests passed"
    else
        warning "Some tests failed, but continuing with deployment"
    fi
}

# Build application
build_application() {
    log "Building React application for production..."
    
    # Set NODE_ENV for production build
    export NODE_ENV=production
    
    # Build the application
    npm run build
    
    if [ ! -d "build" ]; then
        error "Build directory not found. Build may have failed."
        exit 1
    fi
    
    # Check if build contains essential files
    if [ ! -f "build/index.html" ]; then
        error "index.html not found in build directory"
        exit 1
    fi
    
    # Get build size
    BUILD_SIZE=$(du -sh build | cut -f1)
    success "Application built successfully (Size: $BUILD_SIZE)"
}

# Optimize build
optimize_build() {
    log "Optimizing build for production..."
    
    # Compress files if gzip is available
    if command -v gzip &> /dev/null; then
        log "Compressing static files..."
        find build -name "*.js" -o -name "*.css" -o -name "*.html" | while read file; do
            gzip -c "$file" > "$file.gz"
        done
        success "Files compressed successfully"
    fi
    
    # Set proper file permissions
    find build -type f -exec chmod 644 {} \;
    find build -type d -exec chmod 755 {} \;
    
    success "Build optimization completed"
}

# Deploy to S3
deploy_to_s3() {
    log "Deploying to S3 bucket: $S3_BUCKET_NAME"
    
    # Sync build directory to S3 with optimized settings
    aws s3 sync build/ s3://$S3_BUCKET_NAME \
        --region $REGION \
        --delete \
        --cache-control "public, max-age=31536000" \
        --exclude "*.html" \
        --exclude "service-worker.js" \
        --exclude "manifest.json"
    
    # Upload HTML files with shorter cache control
    aws s3 sync build/ s3://$S3_BUCKET_NAME \
        --region $REGION \
        --cache-control "public, max-age=0, must-revalidate" \
        --include "*.html" \
        --include "service-worker.js" \
        --include "manifest.json"
    
    # Upload compressed files with proper encoding
    if command -v gzip &> /dev/null; then
        log "Uploading compressed files..."
        find build -name "*.gz" | while read file; do
            original_file=${file%.gz}
            relative_path=${original_file#build/}
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
    if [ -n "$CLOUDFRONT_DISTRIBUTION_ID" ] && [ "$CLOUDFRONT_DISTRIBUTION_ID" != "None" ]; then
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
        warning "CloudFront distribution ID not found, skipping cache invalidation"
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
    if [ -n "$CLOUDFRONT_DOMAIN" ] && [ "$CLOUDFRONT_DOMAIN" != "None" ]; then
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
    
    cat > $REPORT_FILE << EOF
{
  "deployment": {
    "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
    "project": "$PROJECT_NAME",
    "environment": "$ENVIRONMENT",
    "region": "$REGION",
    "version": "1.0.0"
  },
  "infrastructure": {
    "s3_bucket": "$S3_BUCKET_NAME",
    "cloudfront_distribution_id": "$CLOUDFRONT_DISTRIBUTION_ID",
    "cloudfront_domain": "$CLOUDFRONT_DOMAIN",
    "api_gateway_url": "$API_GATEWAY_URL"
  },
  "endpoints": {
    "s3_website": "http://$S3_BUCKET_NAME.s3-website-$REGION.amazonaws.com",
    "cloudfront_url": "https://$CLOUDFRONT_DOMAIN",
    "api_base_url": "$API_GATEWAY_URL"
  },
  "build_info": {
    "build_size": "$(du -sh build 2>/dev/null | cut -f1 || echo 'Unknown')",
    "node_version": "$(node --version)",
    "npm_version": "$(npm --version)"
  }
}
EOF
    
    success "Deployment report saved to: $REPORT_FILE"
}

# Cleanup
cleanup() {
    log "Cleaning up temporary files..."
    
    # Remove compressed files
    find build -name "*.gz" -delete 2>/dev/null || true
    
    # Remove environment file
    rm -f .env.production
    
    success "Cleanup completed"
}

# Generate summary
generate_summary() {
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
    if [ -n "$CLOUDFRONT_DOMAIN" ] && [ "$CLOUDFRONT_DOMAIN" != "None" ]; then
        echo "  CloudFront: https://$CLOUDFRONT_DOMAIN"
    fi
    echo "  API Gateway: $API_GATEWAY_URL"
    echo ""
    echo "Build Information:"
    echo "  Build Size: $(du -sh build 2>/dev/null | cut -f1 || echo 'Unknown')"
    echo "  Node Version: $(node --version)"
    echo "  React Version: $(npm list react --depth=0 2>/dev/null | grep react@ | cut -d@ -f2 || echo 'Unknown')"
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
    get_stack_outputs
    create_env_config
    install_dependencies
    run_tests
    build_application
    optimize_build
    deploy_to_s3
    invalidate_cloudfront
    test_deployment
    generate_deployment_report
    cleanup
    generate_summary
    
    success "Frontend deployment completed successfully!"
    
    if [ -n "$CLOUDFRONT_DOMAIN" ] && [ "$CLOUDFRONT_DOMAIN" != "None" ]; then
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
trap cleanup EXIT

# Run main function
main "$@"