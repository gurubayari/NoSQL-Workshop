#!/bin/bash

# AWS NoSQL Workshop - Deployment Status Check
# Quick status check for all deployed resources

set -e

# Configuration
PROJECT_NAME="unicorn-ecommerce"
ENVIRONMENT="dev"
STACK_NAME="${PROJECT_NAME}-${ENVIRONMENT}-stack"
REGION=${AWS_DEFAULT_REGION:-us-east-1}

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}AWS NoSQL Workshop - Deployment Status Check${NC}"
echo "=============================================="
echo "Project: $PROJECT_NAME"
echo "Environment: $ENVIRONMENT"
echo "Region: $REGION"
echo "Stack: $STACK_NAME"
echo ""

# Check CloudFormation Stack
echo -e "${BLUE}CloudFormation Stack:${NC}"
if aws cloudformation describe-stacks --stack-name $STACK_NAME --region $REGION &> /dev/null; then
    STATUS=$(aws cloudformation describe-stacks --stack-name $STACK_NAME --region $REGION --query 'Stacks[0].StackStatus' --output text)
    if [[ "$STATUS" == "CREATE_COMPLETE" || "$STATUS" == "UPDATE_COMPLETE" ]]; then
        echo -e "  ✅ Stack Status: ${GREEN}$STATUS${NC}"
    else
        echo -e "  ⚠️  Stack Status: ${YELLOW}$STATUS${NC}"
    fi
else
    echo -e "  ❌ Stack: ${RED}NOT FOUND${NC}"
fi

# Check DynamoDB Tables
echo -e "\n${BLUE}DynamoDB Tables:${NC}"
TABLES=(
    "${PROJECT_NAME}-${ENVIRONMENT}-users"
    "${PROJECT_NAME}-${ENVIRONMENT}-shopping-cart"
    "${PROJECT_NAME}-${ENVIRONMENT}-inventory"
    "${PROJECT_NAME}-${ENVIRONMENT}-orders"
    "${PROJECT_NAME}-${ENVIRONMENT}-chat-history"
    "${PROJECT_NAME}-${ENVIRONMENT}-search-analytics"
)

for table in "${TABLES[@]}"; do
    if aws dynamodb describe-table --table-name $table --region $REGION &> /dev/null; then
        STATUS=$(aws dynamodb describe-table --table-name $table --region $REGION --query 'Table.TableStatus' --output text)
        if [ "$STATUS" = "ACTIVE" ]; then
            echo -e "  ✅ $table: ${GREEN}$STATUS${NC}"
        else
            echo -e "  ⚠️  $table: ${YELLOW}$STATUS${NC}"
        fi
    else
        echo -e "  ❌ $table: ${RED}NOT FOUND${NC}"
    fi
done

# Check DocumentDB
echo -e "\n${BLUE}DocumentDB Cluster:${NC}"
CLUSTER_ID="${PROJECT_NAME}-${ENVIRONMENT}-docdb-cluster"
if aws docdb describe-db-clusters --db-cluster-identifier $CLUSTER_ID --region $REGION &> /dev/null; then
    STATUS=$(aws docdb describe-db-clusters --db-cluster-identifier $CLUSTER_ID --region $REGION --query 'DBClusters[0].Status' --output text)
    if [ "$STATUS" = "available" ]; then
        echo -e "  ✅ $CLUSTER_ID: ${GREEN}$STATUS${NC}"
    else
        echo -e "  ⚠️  $CLUSTER_ID: ${YELLOW}$STATUS${NC}"
    fi
else
    echo -e "  ❌ $CLUSTER_ID: ${RED}NOT FOUND${NC}"
fi

# Check ElastiCache
echo -e "\n${BLUE}ElastiCache Serverless:${NC}"
CACHE_NAME="${PROJECT_NAME}-${ENVIRONMENT}-cache"
if aws elasticache describe-serverless-caches --serverless-cache-name $CACHE_NAME --region $REGION &> /dev/null; then
    STATUS=$(aws elasticache describe-serverless-caches --serverless-cache-name $CACHE_NAME --region $REGION --query 'ServerlessCaches[0].Status' --output text)
    if [ "$STATUS" = "available" ]; then
        echo -e "  ✅ $CACHE_NAME: ${GREEN}$STATUS${NC}"
    else
        echo -e "  ⚠️  $CACHE_NAME: ${YELLOW}$STATUS${NC}"
    fi
else
    echo -e "  ❌ $CACHE_NAME: ${RED}NOT FOUND${NC}"
fi

# Check S3 Bucket
echo -e "\n${BLUE}S3 Bucket:${NC}"
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
BUCKET_NAME="${PROJECT_NAME}-${ENVIRONMENT}-website-${ACCOUNT_ID}"
if aws s3api head-bucket --bucket $BUCKET_NAME --region $REGION 2>/dev/null; then
    echo -e "  ✅ $BUCKET_NAME: ${GREEN}EXISTS${NC}"
else
    echo -e "  ❌ $BUCKET_NAME: ${RED}NOT FOUND${NC}"
fi

# Check CloudFront
echo -e "\n${BLUE}CloudFront Distribution:${NC}"
if aws cloudformation describe-stacks --stack-name $STACK_NAME --region $REGION &> /dev/null; then
    DISTRIBUTION_ID=$(aws cloudformation describe-stacks --stack-name $STACK_NAME --region $REGION --query 'Stacks[0].Outputs[?OutputKey==`CloudFrontDistributionId`].OutputValue' --output text)
    if [ -n "$DISTRIBUTION_ID" ] && [ "$DISTRIBUTION_ID" != "None" ]; then
        STATUS=$(aws cloudfront get-distribution --id $DISTRIBUTION_ID --query 'Distribution.Status' --output text)
        if [ "$STATUS" = "Deployed" ]; then
            echo -e "  ✅ $DISTRIBUTION_ID: ${GREEN}$STATUS${NC}"
        else
            echo -e "  ⚠️  $DISTRIBUTION_ID: ${YELLOW}$STATUS${NC}"
        fi
    else
        echo -e "  ❌ Distribution: ${RED}NOT FOUND${NC}"
    fi
fi

# Check API Gateway
echo -e "\n${BLUE}API Gateway:${NC}"
API_NAME="${PROJECT_NAME}-${ENVIRONMENT}-api"
API_ID=$(aws apigateway get-rest-apis --region $REGION --query "items[?name=='$API_NAME'].id" --output text)
if [ -n "$API_ID" ] && [ "$API_ID" != "None" ]; then
    echo -e "  ✅ $API_NAME: ${GREEN}FOUND${NC} (ID: $API_ID)"
    API_URL="https://${API_ID}.execute-api.${REGION}.amazonaws.com/${ENVIRONMENT}"
    echo -e "  📍 Endpoint: $API_URL"
else
    echo -e "  ❌ $API_NAME: ${RED}NOT FOUND${NC}"
fi

# Check Cognito User Pool
echo -e "\n${BLUE}Cognito User Pool:${NC}"
USER_POOL_NAME="${PROJECT_NAME}-${ENVIRONMENT}-users"
USER_POOL_ID=$(aws cognito-idp list-user-pools --max-items 50 --region $REGION --query "UserPools[?Name=='$USER_POOL_NAME'].Id" --output text)
if [ -n "$USER_POOL_ID" ] && [ "$USER_POOL_ID" != "None" ]; then
    echo -e "  ✅ $USER_POOL_NAME: ${GREEN}FOUND${NC} (ID: $USER_POOL_ID)"
else
    echo -e "  ❌ $USER_POOL_NAME: ${RED}NOT FOUND${NC}"
fi

# Summary
echo -e "\n${BLUE}Quick Actions:${NC}"
echo "  • Run validation: python3 validate-infrastructure.py"
echo "  • Run smoke tests: python3 smoke-tests.py"
echo "  • View stack outputs: aws cloudformation describe-stacks --stack-name $STACK_NAME --query 'Stacks[0].Outputs' --output table"
echo "  • Check stack events: aws cloudformation describe-stack-events --stack-name $STACK_NAME --query 'StackEvents[0:10]' --output table"

echo -e "\n${GREEN}Status check complete!${NC}"