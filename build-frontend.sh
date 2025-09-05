#!/bin/bash

# AWS NoSQL Workshop - Frontend Build Script
# This script builds the Unicorn E-Commerce React application for deployment

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

echo -e "${BLUE}AWS NoSQL Workshop - Frontend Build${NC}"
echo "=================================================="
echo "Project: $PROJECT_NAME"
echo "Environment: $ENVIRONMENT"
echo "Region: $REGION"
echo ""

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
    
    # Check if package.json exists
    if [ ! -f "package.json" ]; then
        error "package.json not found. Please run this script from the project root."
        exit 1
    fi
    
    success "Prerequisites check passed"
}

# Create environment configuration template
create_env_template() {
    log "Creating environment configuration template..."
    
    # Create .env.production.template file for build-time environment variables
    cat > .env.production.template << EOF
# AWS NoSQL Workshop - Production Environment Configuration Template
# This file will be used to generate .env.production during deployment
GENERATE_SOURCEMAP=false
REACT_APP_AWS_REGION=$REGION
REACT_APP_API_GATEWAY_URL=__API_GATEWAY_URL__
REACT_APP_USER_POOL_ID=__USER_POOL_ID__
REACT_APP_USER_POOL_CLIENT_ID=__USER_POOL_CLIENT_ID__
REACT_APP_CLOUDFRONT_DOMAIN=__CLOUDFRONT_DOMAIN__
REACT_APP_ENVIRONMENT=$ENVIRONMENT
REACT_APP_PROJECT_NAME=$PROJECT_NAME
REACT_APP_VERSION=1.0.0
EOF
    
    success "Environment configuration template created"
}

# Install dependencies with webpack fix
install_dependencies() {
    log "Installing npm dependencies..."
    
    # Complete clean install to fix webpack issues
    if [ -d "node_modules" ]; then
        log "Removing existing node_modules..."
        # Use more robust removal method
        if ! rm -rf node_modules 2>/dev/null; then
            log "Standard removal failed, trying alternative method..."
            find node_modules -delete 2>/dev/null || true
            rmdir node_modules 2>/dev/null || true
        fi
        
        # If still exists, skip clean install
        if [ -d "node_modules" ]; then
            warning "Could not remove node_modules, skipping clean install"
            success "Dependencies already installed"
            return
        fi
    fi
    
    if [ -f "package-lock.json" ]; then
        log "Removing package-lock.json to force fresh install..."
        rm -f package-lock.json
    fi
    
    # Clear npm cache completely
    npm cache clean --force
    
    # Fresh install
    log "Performing fresh npm install..."
    npm install
    
    # Verify critical webpack dependencies
    if [ ! -d "node_modules/html-webpack-plugin" ]; then
        warning "html-webpack-plugin not found, installing explicitly..."
        npm install html-webpack-plugin --save-dev
    fi
    
    if [ ! -d "node_modules/webpack" ]; then
        warning "webpack not found, installing via react-scripts..."
        npm install react-scripts --save
    fi
    
    success "Dependencies installed successfully"
}



# Force clean build for cache busting
force_clean_build() {
    log "Performing force clean build to avoid cache issues..."
    
    # Remove all build artifacts
    log "Removing build directories..."
    rm -rf build/ 2>/dev/null || true
    rm -rf build-artifacts/ 2>/dev/null || true
    rm -rf build-deployment/ 2>/dev/null || true
    
    # Clear node_modules cache more safely
    log "Clearing node_modules cache..."
    if [ -d "node_modules/.cache" ]; then
        find node_modules/.cache -type f -delete 2>/dev/null || true
        find node_modules/.cache -type d -empty -delete 2>/dev/null || true
        rm -rf node_modules/.cache/ 2>/dev/null || true
    fi
    
    # Clear npm cache
    log "Clearing npm cache..."
    npm cache clean --force 2>/dev/null || {
        warning "npm cache clean failed, continuing anyway"
    }
    
    success "Clean build preparation completed"
}

# Build application with webpack error handling
build_application() {
    log "Building React application for production..."
    
    # Add build timestamp for cache busting
    BUILD_TIMESTAMP=$(date +%s)
    export REACT_APP_BUILD_TIMESTAMP=$BUILD_TIMESTAMP
    
    # Create temporary .env.production with placeholders and timestamp
    cat > .env.production << EOF
GENERATE_SOURCEMAP=false
REACT_APP_AWS_REGION=$REGION
REACT_APP_API_GATEWAY_URL=__API_GATEWAY_URL__
REACT_APP_USER_POOL_ID=__USER_POOL_ID__
REACT_APP_USER_POOL_CLIENT_ID=__USER_POOL_CLIENT_ID__
REACT_APP_CLOUDFRONT_DOMAIN=__CLOUDFRONT_DOMAIN__
REACT_APP_ENVIRONMENT=$ENVIRONMENT
REACT_APP_PROJECT_NAME=$PROJECT_NAME
REACT_APP_VERSION=1.0.0
REACT_APP_BUILD_TIMESTAMP=$BUILD_TIMESTAMP
EOF
    
    # Set NODE_ENV for production build
    export NODE_ENV=production
    
    # Try basic build first to avoid optimize-build.js issues
    log "Attempting basic React build..."
    if ! npm run build:basic; then
        error "Basic React build failed. Trying to fix webpack issues..."
        
        # Try to fix webpack issues
        log "Reinstalling react-scripts..."
        npm install react-scripts@latest
        
        log "Retrying basic build..."
        if ! npm run build:basic; then
            error "Build failed even after webpack fix attempts"
            exit 1
        fi
    fi
    
    # Run optimization separately if basic build succeeded
    if [ -f "optimize-build.js" ] && [ -d "build" ]; then
        log "Running build optimization..."
        if ! node optimize-build.js; then
            warning "Build optimization failed, but basic build succeeded"
        fi
    fi
    
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
    success "Application built successfully (Size: $BUILD_SIZE, Timestamp: $BUILD_TIMESTAMP)"
}

# Optimize build
optimize_build() {
    log "Optimizing build for production..."
    
    # Create build-artifacts directory
    mkdir -p build-artifacts
    
    # Copy build to artifacts directory
    cp -r build build-artifacts/
    
    # Compress files if gzip is available
    if command -v gzip &> /dev/null; then
        log "Pre-compressing static files..."
        find build-artifacts/build -name "*.js" -o -name "*.css" -o -name "*.html" | while read file; do
            gzip -c "$file" > "$file.gz"
        done
        success "Files pre-compressed successfully"
    fi
    
    # Set proper file permissions
    find build-artifacts/build -type f -exec chmod 644 {} \;
    find build-artifacts/build -type d -exec chmod 755 {} \;
    
    success "Build optimization completed"
}

# Create build manifest
create_build_manifest() {
    log "Creating build manifest..."
    
    cat > build-artifacts/build-manifest.json << EOF
{
    "build_info": {
        "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
        "project": "$PROJECT_NAME",
        "environment": "$ENVIRONMENT",
        "region": "$REGION",
        "version": "1.0.0",
        "build_size": "$(du -sh build 2>/dev/null | cut -f1 || echo 'Unknown')",
        "node_version": "$(node --version)",
        "npm_version": "$(npm --version)",
        "react_version": "$(npm list react --depth=0 2>/dev/null | grep react@ | cut -d@ -f2 || echo 'Unknown')"
    },
    "environment_variables": {
        "REACT_APP_AWS_REGION": "$REGION",
        "REACT_APP_ENVIRONMENT": "$ENVIRONMENT",
        "REACT_APP_PROJECT_NAME": "$PROJECT_NAME",
        "REACT_APP_VERSION": "1.0.0"
    },
    "placeholders": [
        "REACT_APP_API_GATEWAY_URL",
        "REACT_APP_USER_POOL_ID",
        "REACT_APP_USER_POOL_CLIENT_ID",
        "REACT_APP_CLOUDFRONT_DOMAIN"
    ],
    "files": {
        "total_files": $(find build -type f | wc -l),
        "js_files": $(find build -name "*.js" | wc -l),
        "css_files": $(find build -name "*.css" | wc -l),
        "html_files": $(find build -name "*.html" | wc -l),
        "compressed_files": $(find build-artifacts/build -name "*.gz" | wc -l)
    }
}
EOF
    
    success "Build manifest created: build-artifacts/build-manifest.json"
}

# Cleanup temporary files
cleanup_temp_files() {
    log "Cleaning up temporary files..."
    
    # Remove temporary environment file
    rm -f .env.production
    
    success "Temporary files cleaned up"
}

# Generate build summary
generate_build_summary() {
    log "Generating build summary..."
    
    echo ""
    echo "=========================================="
    echo "  FRONTEND BUILD SUMMARY"
    echo "=========================================="
    echo "Project: $PROJECT_NAME"
    echo "Environment: $ENVIRONMENT"
    echo "Region: $REGION"
    echo "Timestamp: $(date)"
    echo ""
    echo "Build Information:"
    echo "  Build Size: $(du -sh build 2>/dev/null | cut -f1 || echo 'Unknown')"
    echo "  Artifacts Size: $(du -sh build-artifacts 2>/dev/null | cut -f1 || echo 'Unknown')"
    echo "  Node Version: $(node --version)"
    echo "  NPM Version: $(npm --version)"
    echo "  React Version: $(npm list react --depth=0 2>/dev/null | grep react@ | cut -d@ -f2 || echo 'Unknown')"
    echo ""
    echo "Files:"
    echo "  Total Files: $(find build -type f | wc -l)"
    echo "  JavaScript Files: $(find build -name "*.js" | wc -l)"
    echo "  CSS Files: $(find build -name "*.css" | wc -l)"
    echo "  HTML Files: $(find build -name "*.html" | wc -l)"
    if command -v gzip &> /dev/null; then
        echo "  Compressed Files: $(find build-artifacts/build -name "*.gz" | wc -l)"
    fi
    echo ""
    echo "Build Artifacts Directory: $(pwd)/build-artifacts"
    echo ""
    echo "Next Steps:"
    echo "1. Run deployment: ./deploy-frontend.sh [parameters]"
    echo "2. Or manually deploy using the build-artifacts directory"
    echo ""
}

# Main execution
main() {
    log "Starting Unicorn E-Commerce frontend build..."
    
    check_prerequisites
    create_env_template
    force_clean_build
    install_dependencies
    build_application
    optimize_build
    create_build_manifest
    cleanup_temp_files
    generate_build_summary
    
    success "Frontend build completed successfully!"
    
    echo ""
    echo "🎉 Build artifacts are ready in: $(pwd)/build-artifacts"
    echo "   Use ./deploy-frontend.sh with required parameters to deploy to AWS"
    echo ""
    echo "Example deployment command:"
    echo "./deploy-frontend.sh \\"
    echo "  your-s3-bucket \\"
    echo "  https://your-api-gateway-url \\"
    echo "  your-user-pool-id \\"
    echo "  your-user-pool-client-id \\"
    echo "  [cloudfront-distribution-id] \\"
    echo "  [cloudfront-domain]"
}

# Handle script interruption
trap cleanup_temp_files EXIT

# Run main function
main "$@"