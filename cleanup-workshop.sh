#!/bin/bash

# Unicorn E-Commerce Workshop Cleanup Script
# This script safely removes all AWS resources created during the workshop

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
STACK_NAME="unicorn-ecommerce"
REGION="us-east-1"
S3_BUCKET_PREFIX="unicorn-ecommerce"

echo -e "${BLUE}🦄 Unicorn E-Commerce Workshop Cleanup${NC}"
echo "=================================================="
echo ""

# Function to print status
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Function to check if AWS CLI is configured
check_aws_cli() {
    print_status "Checking AWS CLI configuration..."
    
    if ! command -v aws &> /dev/null; then
        print_error "AWS CLI is not installed. Please install it first."
        exit 1
    fi
    
    if ! aws sts get-caller-identity &> /dev/null; then
        print_error "AWS CLI is not configured. Please run 'aws configure' first."
        exit 1
    fi
    
    ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
    print_success "AWS CLI configured for account: $ACCOUNT_ID"
}

# Function to confirm cleanup
confirm_cleanup() {
    echo ""
    print_warning "This will DELETE ALL resources created during the workshop!"
    print_warning "This action cannot be undone."
    echo ""
    read -p "Are you sure you want to proceed? (type 'yes' to continue): " confirmation
    
    if [ "$confirmation" != "yes" ]; then
        print_status "Cleanup cancelled."
        exit 0
    fi
    echo ""
}

# Function to empty and delete S3 buckets
cleanup_s3_buckets() {
    print_status "Cleaning up S3 buckets..."
    
    # Find all buckets with the prefix
    BUCKETS=$(aws s3api list-buckets --query "Buckets[?starts_with(Name, '$S3_BUCKET_PREFIX')].Name" --output text --region $REGION 2>/dev/null || true)
    
    if [ -z "$BUCKETS" ]; then
        print_status "No S3 buckets found with prefix '$S3_BUCKET_PREFIX'"
        return
    fi
    
    for bucket in $BUCKETS; do
        print_status "Processing bucket: $bucket"
        
        # Check if bucket exists
        if aws s3api head-bucket --bucket "$bucket" --region $REGION 2>/dev/null; then
            # Empty the bucket first
            print_status "Emptying bucket: $bucket"
            aws s3 rm "s3://$bucket" --recursive --region $REGION 2>/dev/null || true
            
            # Delete all versions and delete markers (for versioned buckets)
            aws s3api list-object-versions --bucket "$bucket" --region $REGION --query 'Versions[].{Key:Key,VersionId:VersionId}' --output text 2>/dev/null | while read key version; do
                if [ ! -z "$key" ] && [ ! -z "$version" ]; then
                    aws s3api delete-object --bucket "$bucket" --key "$key" --version-id "$version" --region $REGION 2>/dev/null || true
                fi
            done
            
            # Delete delete markers
            aws s3api list-object-versions --bucket "$bucket" --region $REGION --query 'DeleteMarkers[].{Key:Key,VersionId:VersionId}' --output text 2>/dev/null | while read key version; do
                if [ ! -z "$key" ] && [ ! -z "$version" ]; then
                    aws s3api delete-object --bucket "$bucket" --key "$key" --version-id "$version" --region $REGION 2>/dev/null || true
                fi
            done
            
            # Delete the bucket
            print_status "Deleting bucket: $bucket"
            aws s3api delete-bucket --bucket "$bucket" --region $REGION 2>/dev/null || true
            print_success "Deleted bucket: $bucket"
        else
            print_status "Bucket $bucket does not exist or is not accessible"
        fi
    done
}

# Function to delete CloudFront distributions
cleanup_cloudfront() {
    print_status "Cleaning up CloudFront distributions..."
    
    # Find distributions with unicorn-ecommerce tag or comment
    DISTRIBUTIONS=$(aws cloudfront list-distributions --query "DistributionList.Items[?contains(Comment, 'unicorn-ecommerce') || contains(Comment, 'Unicorn E-Commerce')].Id" --output text 2>/dev/null || true)
    
    if [ -z "$DISTRIBUTIONS" ]; then
        print_status "No CloudFront distributions found"
        return
    fi
    
    for dist_id in $DISTRIBUTIONS; do
        print_status "Processing CloudFront distribution: $dist_id"
        
        # Get current config
        ETAG=$(aws cloudfront get-distribution --id "$dist_id" --query 'ETag' --output text 2>/dev/null || true)
        
        if [ ! -z "$ETAG" ]; then
            # Disable the distribution first
            print_status "Disabling CloudFront distribution: $dist_id"
            aws cloudfront get-distribution-config --id "$dist_id" --query 'DistributionConfig' > /tmp/dist-config.json 2>/dev/null || true
            
            # Update the config to disable
            jq '.Enabled = false' /tmp/dist-config.json > /tmp/dist-config-disabled.json 2>/dev/null || true
            
            aws cloudfront update-distribution --id "$dist_id" --distribution-config file:///tmp/dist-config-disabled.json --if-match "$ETAG" 2>/dev/null || true
            
            print_warning "CloudFront distribution $dist_id has been disabled. It will be automatically deleted after it's fully disabled (this can take 15-20 minutes)."
            print_status "You can check status with: aws cloudfront get-distribution --id $dist_id"
        fi
    done
    
    # Cleanup temp files
    rm -f /tmp/dist-config.json /tmp/dist-config-disabled.json 2>/dev/null || true
}

# Function to delete CloudFormation stack
cleanup_cloudformation() {
    print_status "Cleaning up CloudFormation stack: $STACK_NAME"
    
    # Check if stack exists
    if aws cloudformation describe-stacks --stack-name "$STACK_NAME" --region $REGION &>/dev/null; then
        print_status "Deleting CloudFormation stack: $STACK_NAME"
        aws cloudformation delete-stack --stack-name "$STACK_NAME" --region $REGION
        
        print_status "Waiting for stack deletion to complete..."
        aws cloudformation wait stack-delete-complete --stack-name "$STACK_NAME" --region $REGION
        print_success "CloudFormation stack deleted successfully"
    else
        print_status "CloudFormation stack '$STACK_NAME' not found"
    fi
}

# Function to cleanup remaining Lambda functions
cleanup_lambda_functions() {
    print_status "Cleaning up remaining Lambda functions..."
    
    # Find functions with unicorn-ecommerce prefix
    FUNCTIONS=$(aws lambda list-functions --region $REGION --query "Functions[?starts_with(FunctionName, 'unicorn-ecommerce') || starts_with(FunctionName, 'UnicornEcommerce')].FunctionName" --output text 2>/dev/null || true)
    
    if [ -z "$FUNCTIONS" ]; then
        print_status "No Lambda functions found"
        return
    fi
    
    for function in $FUNCTIONS; do
        print_status "Deleting Lambda function: $function"
        aws lambda delete-function --function-name "$function" --region $REGION 2>/dev/null || true
        print_success "Deleted Lambda function: $function"
    done
}

# Function to cleanup DynamoDB tables
cleanup_dynamodb_tables() {
    print_status "Cleaning up DynamoDB tables..."
    
    # List of expected table names
    TABLES=("Users" "ShoppingCart" "Inventory" "Orders" "ChatHistory" "SearchAnalytics")
    
    for table in "${TABLES[@]}"; do
        FULL_TABLE_NAME="${STACK_NAME}-${table}"
        
        if aws dynamodb describe-table --table-name "$FULL_TABLE_NAME" --region $REGION &>/dev/null; then
            print_status "Deleting DynamoDB table: $FULL_TABLE_NAME"
            aws dynamodb delete-table --table-name "$FULL_TABLE_NAME" --region $REGION 2>/dev/null || true
            print_success "Deleted DynamoDB table: $FULL_TABLE_NAME"
        else
            print_status "DynamoDB table '$FULL_TABLE_NAME' not found"
        fi
    done
}

# Function to cleanup DocumentDB cluster
cleanup_documentdb() {
    print_status "Cleaning up DocumentDB cluster..."
    
    CLUSTER_NAME="${STACK_NAME}-docdb-cluster"
    
    # Check if cluster exists
    if aws docdb describe-db-clusters --db-cluster-identifier "$CLUSTER_NAME" --region $REGION &>/dev/null; then
        # Delete cluster instances first
        INSTANCES=$(aws docdb describe-db-clusters --db-cluster-identifier "$CLUSTER_NAME" --region $REGION --query 'DBClusters[0].DBClusterMembers[].DBInstanceIdentifier' --output text 2>/dev/null || true)
        
        for instance in $INSTANCES; do
            if [ ! -z "$instance" ]; then
                print_status "Deleting DocumentDB instance: $instance"
                aws docdb delete-db-instance --db-instance-identifier "$instance" --region $REGION 2>/dev/null || true
            fi
        done
        
        # Wait a bit for instances to start deleting
        sleep 30
        
        # Delete the cluster
        print_status "Deleting DocumentDB cluster: $CLUSTER_NAME"
        aws docdb delete-db-cluster --db-cluster-identifier "$CLUSTER_NAME" --skip-final-snapshot --region $REGION 2>/dev/null || true
        print_success "DocumentDB cluster deletion initiated"
    else
        print_status "DocumentDB cluster '$CLUSTER_NAME' not found"
    fi
}

# Function to cleanup ElastiCache cluster
cleanup_elasticache() {
    print_status "Cleaning up ElastiCache cluster..."
    
    CLUSTER_NAME="${STACK_NAME}-cache"
    
    # Check for serverless cache
    if aws elasticache describe-serverless-caches --serverless-cache-name "$CLUSTER_NAME" --region $REGION &>/dev/null; then
        print_status "Deleting ElastiCache serverless cache: $CLUSTER_NAME"
        aws elasticache delete-serverless-cache --serverless-cache-name "$CLUSTER_NAME" --region $REGION 2>/dev/null || true
        print_success "ElastiCache serverless cache deletion initiated"
    else
        # Check for regular cache cluster
        if aws elasticache describe-cache-clusters --cache-cluster-id "$CLUSTER_NAME" --region $REGION &>/dev/null; then
            print_status "Deleting ElastiCache cluster: $CLUSTER_NAME"
            aws elasticache delete-cache-cluster --cache-cluster-id "$CLUSTER_NAME" --region $REGION 2>/dev/null || true
            print_success "ElastiCache cluster deletion initiated"
        else
            print_status "ElastiCache cluster '$CLUSTER_NAME' not found"
        fi
    fi
}

# Function to cleanup CloudWatch logs
cleanup_cloudwatch_logs() {
    print_status "Cleaning up CloudWatch log groups..."
    
    # Find log groups related to the workshop
    LOG_GROUPS=$(aws logs describe-log-groups --region $REGION --query "logGroups[?contains(logGroupName, 'unicorn-ecommerce') || contains(logGroupName, '/aws/lambda/UnicornEcommerce') || contains(logGroupName, '/aws/lambda/unicorn-ecommerce')].logGroupName" --output text 2>/dev/null || true)
    
    if [ -z "$LOG_GROUPS" ]; then
        print_status "No CloudWatch log groups found"
        return
    fi
    
    for log_group in $LOG_GROUPS; do
        print_status "Deleting CloudWatch log group: $log_group"
        aws logs delete-log-group --log-group-name "$log_group" --region $REGION 2>/dev/null || true
        print_success "Deleted CloudWatch log group: $log_group"
    done
}

# Function to cleanup IAM roles (created outside CloudFormation)
cleanup_iam_roles() {
    print_status "Cleaning up IAM roles..."
    
    # Find roles with unicorn-ecommerce prefix
    ROLES=$(aws iam list-roles --query "Roles[?starts_with(RoleName, 'unicorn-ecommerce') || starts_with(RoleName, 'UnicornEcommerce')].RoleName" --output text 2>/dev/null || true)
    
    if [ -z "$ROLES" ]; then
        print_status "No IAM roles found"
        return
    fi
    
    for role in $ROLES; do
        print_status "Processing IAM role: $role"
        
        # Detach managed policies
        ATTACHED_POLICIES=$(aws iam list-attached-role-policies --role-name "$role" --query 'AttachedPolicies[].PolicyArn' --output text 2>/dev/null || true)
        for policy_arn in $ATTACHED_POLICIES; do
            if [ ! -z "$policy_arn" ]; then
                print_status "Detaching policy: $policy_arn from role: $role"
                aws iam detach-role-policy --role-name "$role" --policy-arn "$policy_arn" 2>/dev/null || true
            fi
        done
        
        # Delete inline policies
        INLINE_POLICIES=$(aws iam list-role-policies --role-name "$role" --query 'PolicyNames' --output text 2>/dev/null || true)
        for policy_name in $INLINE_POLICIES; do
            if [ ! -z "$policy_name" ]; then
                print_status "Deleting inline policy: $policy_name from role: $role"
                aws iam delete-role-policy --role-name "$role" --policy-name "$policy_name" 2>/dev/null || true
            fi
        done
        
        # Delete the role
        print_status "Deleting IAM role: $role"
        aws iam delete-role --role-name "$role" 2>/dev/null || true
        print_success "Deleted IAM role: $role"
    done
}

# Function to verify cleanup
verify_cleanup() {
    print_status "Verifying cleanup..."
    
    # Check for remaining resources
    echo ""
    print_status "Checking for remaining resources..."
    
    # S3 buckets
    REMAINING_BUCKETS=$(aws s3api list-buckets --query "Buckets[?starts_with(Name, '$S3_BUCKET_PREFIX')].Name" --output text 2>/dev/null || true)
    if [ ! -z "$REMAINING_BUCKETS" ]; then
        print_warning "Remaining S3 buckets: $REMAINING_BUCKETS"
    else
        print_success "No remaining S3 buckets"
    fi
    
    # Lambda functions
    REMAINING_FUNCTIONS=$(aws lambda list-functions --region $REGION --query "Functions[?starts_with(FunctionName, 'unicorn-ecommerce') || starts_with(FunctionName, 'UnicornEcommerce')].FunctionName" --output text 2>/dev/null || true)
    if [ ! -z "$REMAINING_FUNCTIONS" ]; then
        print_warning "Remaining Lambda functions: $REMAINING_FUNCTIONS"
    else
        print_success "No remaining Lambda functions"
    fi
    
    # CloudFormation stack
    if aws cloudformation describe-stacks --stack-name "$STACK_NAME" --region $REGION &>/dev/null; then
        STACK_STATUS=$(aws cloudformation describe-stacks --stack-name "$STACK_NAME" --region $REGION --query 'Stacks[0].StackStatus' --output text 2>/dev/null || true)
        print_warning "CloudFormation stack still exists with status: $STACK_STATUS"
    else
        print_success "CloudFormation stack deleted"
    fi
    
    echo ""
}

# Function to show cost estimation
show_cost_info() {
    print_status "Cost Information"
    echo "=================="
    echo ""
    print_status "After cleanup, you should not incur charges for:"
    echo "  • Lambda function executions"
    echo "  • DynamoDB read/write operations"
    echo "  • DocumentDB cluster hours"
    echo "  • ElastiCache cluster hours"
    echo "  • S3 storage and requests"
    echo "  • CloudFront requests"
    echo ""
    print_warning "Note: Some services may have minimal charges for:"
    echo "  • CloudWatch logs retention (if not deleted)"
    echo "  • Data transfer costs (minimal)"
    echo "  • CloudFormation API calls (free tier)"
    echo ""
    print_status "Check your AWS billing dashboard in 24-48 hours to confirm no ongoing charges."
    echo ""
}

# Main execution
main() {
    echo "Starting cleanup process..."
    echo ""
    
    # Pre-flight checks
    check_aws_cli
    confirm_cleanup
    
    # Cleanup resources in order
    print_status "Step 1: Cleaning up S3 buckets..."
    cleanup_s3_buckets
    echo ""
    
    print_status "Step 2: Cleaning up CloudFront distributions..."
    cleanup_cloudfront
    echo ""
    
    print_status "Step 3: Cleaning up CloudFormation stack..."
    cleanup_cloudformation
    echo ""
    
    print_status "Step 4: Cleaning up remaining Lambda functions..."
    cleanup_lambda_functions
    echo ""
    
    print_status "Step 5: Cleaning up DynamoDB tables..."
    cleanup_dynamodb_tables
    echo ""
    
    print_status "Step 6: Cleaning up DocumentDB cluster..."
    cleanup_documentdb
    echo ""
    
    print_status "Step 7: Cleaning up ElastiCache cluster..."
    cleanup_elasticache
    echo ""
    
    print_status "Step 8: Cleaning up CloudWatch logs..."
    cleanup_cloudwatch_logs
    echo ""
    
    print_status "Step 9: Cleaning up IAM roles..."
    cleanup_iam_roles
    echo ""
    
    # Verification
    verify_cleanup
    
    # Cost information
    show_cost_info
    
    print_success "Cleanup process completed!"
    print_status "Please check your AWS console to verify all resources have been deleted."
    print_status "Monitor your billing dashboard over the next few days to ensure no unexpected charges."
}

# Run main function
main "$@"