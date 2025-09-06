#!/bin/bash

# Database Seeding Script for Unicorn E-Commerce
# This script seeds pre-generated data to respective databases

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_status() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

print_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

usage() {
    echo "Usage: $0 <PROJECT_NAME> <ENVIRONMENT> <REGION> <SECRET_ARN> <DOCDB_ENDPOINT> <ELASTICACHE_ENDPOINT>"
    echo ""
    echo "Parameters:"
    echo "  PROJECT_NAME        - Project name (e.g., unicorn-ecommerce)"
    echo "  ENVIRONMENT         - Environment (e.g., dev, staging, prod)"
    echo "  REGION              - AWS region (e.g., us-east-1)"
    echo "  SECRET_ARN          - ARN of the database credentials secret"
    echo "  DOCDB_ENDPOINT      - DocumentDB cluster endpoint"
    echo "  ELASTICACHE_ENDPOINT - ElastiCache cluster endpoint"
    echo ""
    echo "Example:"
    echo "  $0 unicorn-ecommerce dev us-east-1 arn:aws:secretsmanager:us-east-1:123456789012:secret:unicorn-ecommerce-dev-database-credentials-AbCdEf docdb-cluster.cluster-xyz.us-east-1.docdb.amazonaws.com cache-cluster.xyz.cache.amazonaws.com"
    exit 1
}

# Check if correct number of arguments provided
if [ $# -ne 6 ]; then
    print_error "Invalid number of arguments. Expected 6, got $#"
    usage
fi

# Parse input parameters
PROJECT_NAME="${1:-unicorn-ecommerce}"
ENVIRONMENT="${2:-dev}"
REGION="${3:-${AWS_DEFAULT_REGION:-us-east-1}}"
SECRET_ARN="$4"
DOCDB_ENDPOINT="$5"
ELASTICACHE_ENDPOINT="$6"

echo "🦄 Unicorn E-Commerce Database Seeding Script"
echo "=============================================="
echo "Started at: $(date)"
echo ""
echo "Configuration:"
echo "  Project Name: $PROJECT_NAME"
echo "  Environment: $ENVIRONMENT"
echo "  Region: $REGION"
echo "  Secret ARN: $SECRET_ARN"
echo "  DocumentDB Endpoint: $DOCDB_ENDPOINT"
echo "  ElastiCache Endpoint: $ELASTICACHE_ENDPOINT"
echo ""

# Check if data files exist
print_info "Checking for generated data files..."

required_files=(
    "data/output/products.json"
    "data/output/inventory.json"
)

for file in "${required_files[@]}"; do
    if [ ! -f "$file" ]; then
        print_error "$file not found. Please run generate_data_only.sh first."
        exit 1
    fi
done

print_status "Required data files found"


# Validate parameters
if [[ ! "$REGION" =~ ^[a-z0-9-]+$ ]]; then
    print_error "Invalid region format: $REGION"
    exit 1
fi

if [[ ! "$ENVIRONMENT" =~ ^[a-z0-9-]+$ ]]; then
    print_error "Invalid environment format: $ENVIRONMENT"
    exit 1
fi

if [[ ! "$PROJECT_NAME" =~ ^[a-z0-9-]+$ ]]; then
    print_error "Invalid project name format: $PROJECT_NAME"
    exit 1
fi

print_info "Parameters validated successfully"

# Get DocumentDB credentials from Secrets Manager
print_info "Retrieving DocumentDB credentials from Secrets Manager..."
SECRET_JSON=$(aws secretsmanager get-secret-value --secret-id "$SECRET_ARN" --region "$REGION" --query SecretString --output text)

if [ $? -ne 0 ]; then
    print_error "Failed to retrieve DocumentDB credentials"
    exit 1
fi

# Parse credentials (updated for new secret structure)
DOCDB_USERNAME=$(echo "$SECRET_JSON" | python3 -c "import sys, json; print(json.load(sys.stdin)['docdb_username'])")
DOCDB_PASSWORD=$(echo "$SECRET_JSON" | python3 -c "import sys, json; print(json.load(sys.stdin)['shared_password'])")
ELASTICACHE_USERNAME=$(echo "$SECRET_JSON" | python3 -c "import sys, json; print(json.load(sys.stdin)['elasticache_username'])")
ELASTICACHE_PASSWORD=$(echo "$SECRET_JSON" | python3 -c "import sys, json; print(json.load(sys.stdin)['shared_password'])")

print_status "Database credentials retrieved successfully"
print_info "DocumentDB Username: $DOCDB_USERNAME"
print_info "ElastiCache Username: $ELASTICACHE_USERNAME"

# Download SSL certificate if not present
if [ ! -f "./../global-bundle.pem" ]; then
    print_info "Downloading DocumentDB SSL certificate..."
    curl -o ./../global-bundle.pem https://truststore.pki.rds.amazonaws.com/global/global-bundle.pem
    
    if [ $? -ne 0 ]; then
        print_warning "Failed to download SSL certificate, proceeding without it"
    else
        print_status "SSL certificate downloaded"
    fi
fi

# Set environment variables
export DOCUMENTDB_HOST="$DOCDB_ENDPOINT"
export DOCUMENTDB_PORT="27017"
export DOCUMENTDB_USERNAME="$DOCDB_USERNAME"
export DOCUMENTDB_PASSWORD="$DOCDB_PASSWORD"
export DOCUMENTDB_DATABASE="${PROJECT_NAME}-${ENVIRONMENT}"
export DOCUMENTDB_SSL_CA_CERTS="./../global-bundle.pem"
export ELASTICACHE_HOST="$ELASTICACHE_ENDPOINT"
export ELASTICACHE_PORT="6379"
export ELASTICACHE_USERNAME="$ELASTICACHE_USERNAME"
export ELASTICACHE_AUTH_TOKEN="$ELASTICACHE_PASSWORD"
export AWS_REGION="$REGION"
export PROJECT_NAME="$PROJECT_NAME"
export ENVIRONMENT="$ENVIRONMENT"

# Set DynamoDB table names 
export USERS_TABLE="${PROJECT_NAME}-${ENVIRONMENT}-users"
export SHOPPING_CART_TABLE="${PROJECT_NAME}-${ENVIRONMENT}-shopping-cart"
export INVENTORY_TABLE="${PROJECT_NAME}-${ENVIRONMENT}-inventory"
export ORDERS_TABLE="${PROJECT_NAME}-${ENVIRONMENT}-orders"
export CHAT_HISTORY_TABLE="${PROJECT_NAME}-${ENVIRONMENT}-chat-history"
export SEARCH_ANALYTICS_TABLE="${PROJECT_NAME}-${ENVIRONMENT}-search-analytics"

print_info "Environment variables configured:"
echo "  Project: $PROJECT_NAME"
echo "  Environment: $ENVIRONMENT"
echo "  Region: $REGION"
echo "  DocumentDB Host: $DOCUMENTDB_HOST"
echo "  DocumentDB Database: $DOCUMENTDB_DATABASE"
echo "  DocumentDB Username: $DOCDB_USERNAME"
echo "  ElastiCache Host: $ELASTICACHE_HOST"
echo "  ElastiCache Username: $ELASTICACHE_USERNAME"
echo "  Users Table: $USERS_TABLE"
echo "  Inventory Table: $INVENTORY_TABLE"
echo ""



# Install Python dependencies if needed
print_info "Checking Python dependencies..."
python3 -c "import boto3, pymongo, redis" 2>/dev/null || {
    print_info "Installing Python dependencies..."
    pip3 install boto3 pymongo redis --user
    
    if [ $? -ne 0 ]; then
        print_error "Failed to install Python dependencies"
        exit 1
    fi
    
    print_status "Python dependencies installed"
}



# Set Python path
export PYTHONPATH="${PYTHONPATH}:$(pwd)"

# Seed data to databases
print_info "Starting database seeding..."

# Seed products to DocumentDB
print_info "Seeding products to DocumentDB..."
if python3 data/seeders/product_seeder.py --force; then
    print_status "Products seeded to DocumentDB successfully"
else
    print_error "Products seeding failed"
    exit 1
fi

# Seed inventory to DynamoDB
print_info "Seeding inventory to DynamoDB..."
if python3 data/seeders/inventory_seeder.py --force; then
    print_status "Inventory seeded to DynamoDB successfully"
else
    print_error "Inventory seeding failed"
    exit 1
fi

# Seed reviews to DocumentDB (if available)
if [ -f "data/output/reviews.json.zip" ]; then
    unzip data/output/reviews.json.zip -d data/output
    print_info "Seeding reviews to DocumentDB..."
    if python3 data/seeders/review_seeder.py; then
        print_status "Reviews seeded to DocumentDB successfully"
    else
        print_warning "Reviews seeding failed, continuing..."
    fi
fi

# Seed knowledge base to DocumentDB (if available)
if [ -f "data/output/knowledge_base.json" ]; then
    print_info "Seeding knowledge base to DocumentDB..."
    if python3 data/seeders/knowledge_base_seeder.py; then
        print_status "Knowledge base seeded to DocumentDB successfully"
    else
        print_warning "Knowledge base seeding failed, continuing..."
    fi
fi

# Seed search behaviors to DynamoDB (if available)
if [ -f "data/output/search_behaviors.json" ]; then
    print_info "Seeding search behaviors to DynamoDB..."
    if python3 data/seeders/search_analytics_seeder.py; then
        print_status "Search behaviors seeded to DynamoDB successfully"
    else
        print_warning "Search behaviors seeding failed, continuing..."
    fi
fi

# Seed popular search terms to ElastiCache (if available)
if [ -f "data/output/popular_search_terms.json" ]; then
    print_info "Seeding popular search terms to ElastiCache..."
    if python3 data/seeders/elasticache_seeder.py; then
        print_status "Popular search terms seeded to ElastiCache successfully"
    else
        print_warning "ElastiCache seeding failed, continuing..."
    fi
fi

print_status "Database seeding completed successfully!"
print_info "Data has been seeded to:"
echo "  • DocumentDB: Products, reviews, and knowledge base collections"
echo "  • DynamoDB: Inventory and search behaviors tables"
echo "  • ElastiCache: Popular search terms, auto-complete suggestions, and trending terms"
echo ""
print_status "Database seeding script completed at: $(date)"