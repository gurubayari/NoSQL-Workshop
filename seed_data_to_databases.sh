#!/bin/bash

# Database Seeding Script for Unicorn E-Commerce
# This script seeds pre-generated data to respective databases

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

echo "🦄 Unicorn E-Commerce Database Seeding Script"
echo "=============================================="
echo "Started at: $(date)"
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


# Extract values from inputs
SECRET_ARN=$1
DOCDB_ENDPOINT=$2
ELASTICACHE_ENDPOINT=$3

print_info "DocumentDB Secret ARN: $SECRET_ARN"
print_info "DocumentDB Endpoint: $DOCDB_ENDPOINT"
print_info "ElastiCache Name: $ELASTICACHE_ENDPOINT"

# Get DocumentDB credentials from Secrets Manager
print_info "Retrieving DocumentDB credentials from Secrets Manager..."
SECRET_JSON=$(aws secretsmanager get-secret-value --secret-id "$SECRET_ARN" --region "$REGION" --query SecretString --output text)

if [ $? -ne 0 ]; then
    print_error "Failed to retrieve DocumentDB credentials"
    exit 1
fi

# Parse credentials
DOCDB_USERNAME=$(echo "$SECRET_JSON" | python3 -c "import sys, json; print(json.load(sys.stdin)['username'])")
DOCDB_PASSWORD=$(echo "$SECRET_JSON" | python3 -c "import sys, json; print(json.load(sys.stdin)['password'])")

print_status "DocumentDB credentials retrieved successfully"

# Download SSL certificate if not present
if [ ! -f "global-bundle.pem" ]; then
    print_info "Downloading DocumentDB SSL certificate..."
    curl -o global-bundle.pem https://truststore.pki.rds.amazonaws.com/global/global-bundle.pem
    
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
export DOCUMENTDB_DATABASE="unicorn_ecommerce_dev"
export DOCUMENTDB_SSL_CA_CERTS="./global-bundle.pem"
export ELASTICACHE_HOST="$ELASTICACHE_ENDPOINT"
export ELASTICACHE_PORT="6379"
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
echo "  DocumentDB Host: $DOCUMENTDB_HOST"
echo "  DocumentDB Database: $DOCUMENTDB_DATABASE"
echo "  ElastiCache Host: $ELASTICACHE_HOST"
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
if python3 data/seeders/product_seeder.py; then
    print_status "Products seeded to DocumentDB successfully"
else
    print_error "Products seeding failed"
    exit 1
fi

# Seed inventory to DynamoDB
print_info "Seeding inventory to DynamoDB..."
if python3 data/seeders/inventory_seeder.py; then
    print_status "Inventory seeded to DynamoDB successfully"
else
    print_error "Inventory seeding failed"
    exit 1
fi

# Seed reviews to DocumentDB (if available)
if [ -f "data/output/reviews.json" ]; then
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