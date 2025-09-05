#!/bin/bash

# AWS NoSQL Workshop - Lambda Functions Redeployment Script
# This script redeploys Lambda zip files to existing functions with LIVE aliases

set -e

# Configuration - Accept command line arguments with defaults
PROJECT_NAME="${1:-unicorn-ecommerce}"
ENVIRONMENT="${2:-dev}"
REGION="${3:-${AWS_DEFAULT_REGION:-us-east-1}}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}AWS NoSQL Workshop - Lambda Functions Redeployment${NC}"
echo "======================================================="
echo "Project: $PROJECT_NAME"
echo "Environment: $ENVIRONMENT"
echo "Region: $REGION"
echo ""
echo "This script assumes Lambda functions already exist."
echo "It will only update the function code to the \$LATEST version."
echo ""

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
    echo "This script will:"
    echo "  1. Update existing Lambda function code from packages"
    echo "  2. Deploy to \$LATEST version (no aliases used)"
    echo ""
    echo "Prerequisites:"
    echo "  - Lambda functions must already exist (created via CloudFormation)"
    echo "  - packages/ directory must contain the Lambda zip files"
    echo ""
    echo "The script will automatically detect existing functions and update them."
    echo ""
    exit 0
fi

# Function to print status
print_status() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

print_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

# Check if AWS CLI is configured
if ! aws sts get-caller-identity > /dev/null 2>&1; then
    print_error "AWS CLI is not configured or credentials are invalid"
    exit 1
fi

print_status "AWS CLI is configured"

# Cleanup function for partial deployments
cleanup_partial_deployment() {
    local function_name=$1
    print_warning "Cleaning up partial deployment of $function_name..."
    
    # Delete the function if it exists but is in a failed state
    if aws lambda get-function --function-name "$function_name" --region "$REGION" > /dev/null 2>&1; then
        local state=$(aws lambda get-function \
            --function-name "$function_name" \
            --region "$REGION" \
            --query 'Configuration.State' \
            --output text 2>/dev/null || echo "Unknown")
        
        if [ "$state" = "Failed" ] || [ "$state" = "Inactive" ]; then
            print_info "Deleting failed function $function_name..."
            aws lambda delete-function \
                --function-name "$function_name" \
                --region "$REGION" > /dev/null 2>&1 || true
            print_status "Cleaned up $function_name"
        fi
    fi
}

# Check if packages directory exists
if [ ! -d "packages" ]; then
    print_error "Packages directory not found. Please run ./package-lambda-functions.sh first"
    exit 1
fi

# Check if deployment manifest exists
if [ ! -f "packages/deployment-manifest.json" ]; then
    print_error "Deployment manifest not found. Please run ./package-lambda-functions.sh first"
    exit 1
fi

# Wait for function update to complete
wait_for_function_update() {
    local function_name=$1
    
    print_info "Waiting for function update to complete..."
    local max_attempts=30
    local attempt=0
    
    while [ $attempt -lt $max_attempts ]; do
        local last_update_status=$(aws lambda get-function \
            --function-name "$function_name" \
            --region "$REGION" \
            --query 'Configuration.LastUpdateStatus' \
            --output text 2>/dev/null || echo "InProgress")
        
        if [ "$last_update_status" = "Successful" ]; then
            print_status "Function update completed successfully"
            return 0
        elif [ "$last_update_status" = "Failed" ]; then
            print_error "Function update failed"
            return 1
        else
            attempt=$((attempt + 1))
            sleep 2
        fi
    done
    
    print_warning "Timeout waiting for function update to complete"
    return 1
}

# Redeploy Lambda function code to existing function
redeploy_lambda_function() {
    local function_name=$1
    
    print_info "Redeploying Lambda function: $function_name"
    
    # Check if package exists
    local zip_file="packages/${function_name}.zip"
    
    if [ ! -f "$zip_file" ]; then
        print_error "Package file $zip_file not found for $function_name"
        return 1
    fi
    
    # Check if function exists
    if ! aws lambda get-function --function-name "$function_name" --region "$REGION" > /dev/null 2>&1; then
        print_error "Function $function_name does not exist. Please create it via CloudFormation first."
        return 1
    fi
    
    print_info "Function $function_name exists, updating code..."
    
    # Update function code
    aws lambda update-function-code \
        --function-name "$function_name" \
        --zip-file "fileb://$zip_file" \
        --region "$REGION" > /dev/null
    
    if [ $? -ne 0 ]; then
        print_error "Failed to update function code for $function_name"
        return 1
    fi
    
    # Wait for update to complete
    if wait_for_function_update "$function_name"; then
        print_status "Successfully redeployed $function_name to \$LATEST"
        return 0
    else
        print_error "Failed to redeploy $function_name"
        return 1
    fi

    done
    
    if [ $attempt -eq $max_attempts ]; then
        print_error "Timeout waiting for function $function_name to become active"
        print_warning "This might be due to VPC ENI creation taking longer than expected"
        print_info "You can check the function status in the AWS Console and re-run this script"
        return 1
    fi
    
    # Additional check to ensure function is truly ready
    print_info "Verifying function $function_name is ready for invocation..."
    local invoke_test=$(aws lambda invoke \
        --function-name "$function_name" \
        --payload '{"httpMethod":"GET","path":"/health"}' \
        --region "$REGION" \
        /tmp/test-response.json 2>&1 || echo "failed")
    
    if [[ "$invoke_test" == *"failed"* ]] || [[ "$invoke_test" == *"error"* ]]; then
        print_warning "Function may not be fully ready yet, but continuing deployment..."
    else
        print_status "Function $function_name is ready for invocation"
    fi
    
    print_status "Successfully deployed $function_name"
}

# Deploy a single function in parallel (simplified for redeployment)
redeploy_function_parallel() {
    local function_name=$1
    local log_file="/tmp/redeploy_${function_name}.log"
    
    {
        echo "=== Starting redeployment of $function_name at $(date) ===" 
        
        if redeploy_lambda_function "$function_name"; then
            echo "✅ Successfully redeployed $function_name to \$LATEST"
            echo "SUCCESS:$function_name" > "/tmp/result_${function_name}.status"
        else
            echo "❌ Failed to redeploy $function_name"
            echo "FAILED:$function_name" > "/tmp/result_${function_name}.status"
        fi
        
        echo "=== Completed redeployment of $function_name at $(date) ==="
    } > "$log_file" 2>&1
}

# Monitor parallel deployment progress with timeout
monitor_parallel_deployments() {
    local functions=("$@")
    local total_functions=${#functions[@]}
    local completed=0
    local last_status_time=$(date +%s)
    local start_time=$(date +%s)
    local timeout_seconds=1800  # 30 minutes timeout for all deployments
    
    print_info "Monitoring deployment progress for $total_functions functions (timeout: ${timeout_seconds}s)..."
    
    while [ $completed -lt $total_functions ]; do
        local current_completed=0
        local current_time=$(date +%s)
        local elapsed_time=$((current_time - start_time))
        
        # Check for timeout
        if [ $elapsed_time -gt $timeout_seconds ]; then
            print_error "Deployment timeout reached (${timeout_seconds}s). Some deployments may still be in progress."
            
            # Show which functions are still incomplete
            local incomplete=()
            for function_name in "${functions[@]}"; do
                if [ ! -f "/tmp/result_${function_name}.status" ]; then
                    incomplete+=("$function_name")
                fi
            done
            
            if [ ${#incomplete[@]} -gt 0 ]; then
                print_warning "Functions that did not complete: ${incomplete[*]}"
                print_info "You can check their status in the AWS Console or re-run the script"
            fi
            
            return 1
        fi
        
        # Count completed deployments
        for function_name in "${functions[@]}"; do
            if [ -f "/tmp/result_${function_name}.status" ]; then
                current_completed=$((current_completed + 1))
            fi
        done
        
        # Update progress if changed or every 30 seconds
        if [ $current_completed -ne $completed ] || [ $((current_time - last_status_time)) -ge 30 ]; then
            completed=$current_completed
            last_status_time=$current_time
            
            local remaining=$((total_functions - completed))
            local elapsed_minutes=$((elapsed_time / 60))
            print_info "Progress: $completed/$total_functions functions completed ($remaining remaining, ${elapsed_minutes}m elapsed)"
            
            # Show which functions are still in progress
            if [ $remaining -gt 0 ]; then
                local in_progress=()
                for function_name in "${functions[@]}"; do
                    if [ ! -f "/tmp/result_${function_name}.status" ]; then
                        in_progress+=("$function_name")
                    fi
                done
                
                if [ ${#in_progress[@]} -le 5 ]; then
                    print_info "Still deploying: ${in_progress[*]}"
                else
                    print_info "Still deploying: ${in_progress[0]}, ${in_progress[1]}, ${in_progress[2]} and $((${#in_progress[@]} - 3)) others"
                fi
            fi
        fi
        
        sleep 5
    done
    
    local total_elapsed=$(($(date +%s) - start_time))
    local total_minutes=$((total_elapsed / 60))
    local total_seconds=$((total_elapsed % 60))
    print_status "All parallel deployments completed in ${total_minutes}m ${total_seconds}s!"
    return 0
}

# Main redeployment function with parallel execution
redeploy_all_lambda_functions() {
    local start_time=$(date +%s)
    
    print_info "Starting parallel Lambda function redeployment..."
    print_info "This script assumes functions already exist and will deploy to \$LATEST"
    
    # Read function list from manifest
    functions=($(jq -r '.functions[]' packages/deployment-manifest.json))
    
    print_info "Found ${#functions[@]} functions to redeploy in parallel"
    
    # Verify all functions exist before starting
    print_info "Verifying existing functions..."
    missing_functions=()
    for function_name in "${functions[@]}"; do
        if ! aws lambda get-function --function-name "$function_name" --region "$REGION" > /dev/null 2>&1; then
            missing_functions+=("$function_name")
        fi
    done
    
    if [ ${#missing_functions[@]} -gt 0 ]; then
        print_error "The following functions do not exist and need to be created via CloudFormation first:"
        for func in "${missing_functions[@]}"; do
            echo "  ❌ $func"
        done
        print_error "Please deploy the CloudFormation template first to create the functions"
        exit 1
    fi
    
    print_status "All functions exist - proceeding with redeployment"
    
    # Clean up any previous deployment artifacts
    rm -f /tmp/redeploy_*.log /tmp/result_*.status

    # Set up signal handler for cleanup
    cleanup_parallel_redeployment() {
        print_warning "Redeployment interrupted. Cleaning up background processes..."
        for pid in "${pids[@]}"; do
            if kill -0 "$pid" 2>/dev/null; then
                print_info "Terminating redeployment process $pid..."
                kill -TERM "$pid" 2>/dev/null || true
            fi
        done
        
        # Wait a moment for graceful termination
        sleep 2
        
        # Force kill any remaining processes
        for pid in "${pids[@]}"; do
            if kill -0 "$pid" 2>/dev/null; then
                print_warning "Force killing process $pid..."
                kill -KILL "$pid" 2>/dev/null || true
            fi
        done
        
        # Clean up temporary files
        rm -f /tmp/redeploy_*.log /tmp/result_*.status
        
        print_error "Redeployment interrupted and cleaned up"
        exit 1
    }
    
    trap cleanup_parallel_redeployment INT TERM
    
    # Start parallel redeployments
    print_info "Starting parallel redeployment of all functions..."
    pids=()
    
    for function_name in "${functions[@]}"; do
        print_info "Starting redeployment of $function_name in background..."
        redeploy_function_parallel "$function_name" &
        pids+=($!)
    done
    
    print_status "All ${#functions[@]} redeployments started in parallel (PIDs: ${pids[*]})"
    print_info "Press Ctrl+C to interrupt and clean up all redeployments"
    # Wait for all background processes to complete
    print_info "Waiting for all redeployment processes to finish..."
    for pid in "${pids[@]}"; do
        wait $pid
    done
    
    # Collect results
    failed_functions=()
    successful_functions=()
    
    for function_name in "${functions[@]}"; do
        if [ -f "/tmp/result_${function_name}.status" ]; then
            local status=$(cat "/tmp/result_${function_name}.status")
            case "$status" in
                "SUCCESS:$function_name")
                    successful_functions+=("$function_name")
                    ;;
                "FAILED:$function_name")
                    failed_functions+=("$function_name")
                    ;;
            esac
        else
            failed_functions+=("$function_name")
        fi
    done

    # Report redeployment results
    echo ""
    print_status "=== PARALLEL REDEPLOYMENT RESULTS ==="
    
    if [ ${#successful_functions[@]} -gt 0 ]; then
        print_status "Successfully redeployed ${#successful_functions[@]} functions:"
        for func in "${successful_functions[@]}"; do
            echo "  ✅ $func"
        done
    fi

    if [ ${#failed_functions[@]} -gt 0 ]; then
        print_error "Failed to redeploy ${#failed_functions[@]} functions:"
        for func in "${failed_functions[@]}"; do
            echo "  ❌ $func"
        done
        
        echo ""
        print_info "=== REDEPLOYMENT LOGS FOR FAILED FUNCTIONS ==="
        for func in "${failed_functions[@]}"; do
            if [ -f "/tmp/redeploy_${func}.log" ]; then
                echo ""
                print_error "Log for $func:"
                echo "----------------------------------------"
                cat "/tmp/redeploy_${func}.log"
                echo "----------------------------------------"
            fi
        done
        
        echo ""
        print_warning "Some functions failed to redeploy. You can:"
        echo "1. Check the logs above for specific error details"
        echo "2. Verify the function packages exist in the packages/ directory"
        echo "3. Check AWS Console for function status"
        echo "4. Re-run this script to retry failed redeployments"
        echo ""
    fi

    # Remove signal handler
    trap - INT TERM
    
    # Clean up temporary files
    rm -f /tmp/redeploy_*.log /tmp/result_*.status

    if [ ${#failed_functions[@]} -eq 0 ]; then
        print_status "All Lambda functions redeployed successfully!"
        print_info "All functions have been updated to \$LATEST version"
    else
        print_warning "Redeployment completed with some failures"
        print_info "You can re-run this script to retry failed redeployments"
    fi

    # Calculate and display deployment time
    local end_time=$(date +%s)
    local total_time=$((end_time - start_time))
    local minutes=$((total_time / 60))
    local seconds=$((total_time % 60))
    
    # Display redeployment summary
    echo ""
    echo -e "${GREEN}🎉 Lambda Functions Redeployment Complete!${NC}"
    echo "================================================="
    echo "Total redeployment time: ${minutes}m ${seconds}s"
    echo "Functions redeployed in parallel: ${#functions[@]}"
    echo ""
    echo "Redeployed Functions (\$LATEST version):"
    
    # Display function information
    for function_name in "${successful_functions[@]}"; do
        echo "- $function_name ✅ (\$LATEST version)"
    done
    echo ""
}

# Main execution
redeploy_all_lambda_functions

print_status "Lambda function redeployment completed!"
print_info "All functions have been updated to \$LATEST version"

# Function to create deployment report
create_deployment_report() {
    local timestamp=$(date +"%Y%m%d-%H%M%S")
    local report_file="deployment-report-${timestamp}.json"
    
    print_info "Creating deployment report: $report_file"
    
    # Start JSON structure
    cat > "$report_file" << EOF
{
  "deployment": {
    "timestamp": "$(date -u +"%Y-%m-%dT%H:%M:%SZ")",
    "project": "$PROJECT_NAME",
    "environment": "$ENVIRONMENT",
    "region": "$REGION"
  },
  "functions": [
EOF

    # Add function details
    local first=true
    for function_name in $(jq -r '.functions[]' packages/deployment-manifest.json); do
        if [ "$first" = false ]; then
            echo "," >> "$report_file"
        fi
        first=false
        
        # Get function ARN
        local function_arn=$(aws lambda get-function \
            --function-name "$function_name" \
            --region "$REGION" \
            --query 'Configuration.FunctionArn' \
            --output text 2>/dev/null || echo "")
        
        cat >> "$report_file" << EOF
    {
      "name": "$function_name",
      "functionArn": "$function_arn",
      "version": "\$LATEST"
    }
EOF
    done
    
    # Close JSON structure
    cat >> "$report_file" << EOF
  ]
}
EOF

    print_status "Deployment report created: $report_file"
    
    # Display key ARNs for API Gateway configuration
    echo ""
    print_info "Lambda ARNs (\$LATEST) for API Gateway configuration:"
    echo "===================================================="
    for function_name in $(jq -r '.functions[]' packages/deployment-manifest.json); do
        local function_arn=$(aws lambda get-function \
            --function-name "$function_name" \
            --region "$REGION" \
            --query 'Configuration.FunctionArn' \
            --output text 2>/dev/null || echo "")
        
        if [ -n "$function_arn" ]; then
            echo "$function_name: $function_arn"
        else
            echo "$function_name: ❌ Function not found"
        fi
    done
    echo ""
}

# Main execution
redeploy_all_lambda_functions

# Create deployment report
create_deployment_report