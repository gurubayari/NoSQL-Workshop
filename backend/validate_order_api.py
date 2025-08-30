#!/usr/bin/env python3
"""
Code validation for Order Management API Lambda function
"""
import os
import ast
import sys

def validate_order_api_file():
    """Validate the Order API file structure and content"""
    file_path = os.path.join(os.path.dirname(__file__), 'functions', 'order_api.py')
    
    if not os.path.exists(file_path):
        print("❌ Order API file does not exist")
        return False
    
    try:
        with open(file_path, 'r') as f:
            content = f.read()
        
        # Parse the AST to validate structure
        tree = ast.parse(content)
        
        # Check for required classes and functions
        classes = []
        functions = []
        
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                classes.append(node.name)
            elif isinstance(node, ast.FunctionDef):
                functions.append(node.name)
        
        # Validate required components
        required_classes = ['OrderManagementAPI', 'OrderAPIError']
        required_functions = ['lambda_handler']
        
        missing_classes = [cls for cls in required_classes if cls not in classes]
        missing_functions = [func for func in required_functions if func not in functions]
        
        if missing_classes:
            print(f"❌ Missing required classes: {missing_classes}")
            return False
        
        if missing_functions:
            print(f"❌ Missing required functions: {missing_functions}")
            return False
        
        # Check for required methods in OrderManagementAPI class
        order_api_methods = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == 'OrderManagementAPI':
                for item in node.body:
                    if isinstance(item, ast.FunctionDef):
                        order_api_methods.append(item.name)
        
        required_methods = [
            '__init__',
            'create_order',
            'get_order',
            'get_user_orders',
            'update_order_status',
            '_validate_and_enrich_items',
            '_execute_order_transaction',
            '_get_product_info',
            '_check_inventory',
            '_calculate_tax',
            '_calculate_shipping',
            '_process_payment',
            '_clear_user_cart'
        ]
        
        missing_methods = [method for method in required_methods if method not in order_api_methods]
        
        if missing_methods:
            print(f"❌ Missing required methods in OrderManagementAPI: {missing_methods}")
            return False
        
        print("✅ Order API file structure validation passed")
        return True
        
    except SyntaxError as e:
        print(f"❌ Syntax error in Order API file: {e}")
        return False
    except Exception as e:
        print(f"❌ Error validating Order API file: {e}")
        return False

def validate_test_file():
    """Validate the test file exists and has basic structure"""
    file_path = os.path.join(os.path.dirname(__file__), 'tests', 'test_order_api.py')
    
    if not os.path.exists(file_path):
        print("❌ Order API test file does not exist")
        return False
    
    try:
        with open(file_path, 'r') as f:
            content = f.read()
        
        # Check for test classes and methods
        tree = ast.parse(content)
        
        test_classes = []
        test_methods = []
        
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name.startswith('Test'):
                test_classes.append(node.name)
                for item in node.body:
                    if isinstance(item, ast.FunctionDef) and item.name.startswith('test_'):
                        test_methods.append(item.name)
        
        if not test_classes:
            print("❌ No test classes found")
            return False
        
        if not test_methods:
            print("❌ No test methods found")
            return False
        
        print(f"✅ Test file validation passed - Found {len(test_classes)} test classes with {len(test_methods)} test methods")
        return True
        
    except Exception as e:
        print(f"❌ Error validating test file: {e}")
        return False

def validate_functionality():
    """Validate key functionality is implemented"""
    file_path = os.path.join(os.path.dirname(__file__), 'functions', 'order_api.py')
    
    try:
        with open(file_path, 'r') as f:
            content = f.read()
        
        # Check for key functionality keywords
        required_features = {
            'DynamoDB_transactions': ['transact_write_items', 'TransactItems', 'ConditionExpression'],
            'inventory_deduction': ['availableQuantity', 'quantity', 'ConditionalCheckFailedException'],
            'order_creation': ['create_order', 'orderId', 'uuid'],
            'order_retrieval': ['get_order', 'get_user_orders', 'query'],
            'status_management': ['update_order_status', 'status', 'tracking'],
            'payment_processing': ['_process_payment', 'paymentMethod', 'paymentId'],
            'tax_calculation': ['_calculate_tax', 'tax_rates', 'taxAmount'],
            'shipping_calculation': ['_calculate_shipping', 'shippingAmount'],
            'cart_clearing': ['_clear_user_cart', 'delete_item'],
            'error_handling': ['try:', 'except', 'logger.error', 'ClientError'],
            'caching': ['cache_get', 'cache_set', 'cache_delete'],
            'CORS_support': ['Access-Control-Allow-Origin', '_get_cors_headers'],
            'pagination': ['page', 'limit', 'pagination']
        }
        
        missing_features = []
        
        for feature, keywords in required_features.items():
            if not any(keyword in content for keyword in keywords):
                missing_features.append(feature)
        
        if missing_features:
            print(f"❌ Missing key functionality: {missing_features}")
            return False
        
        print("✅ Functionality validation passed - All key features implemented")
        return True
        
    except Exception as e:
        print(f"❌ Error validating functionality: {e}")
        return False

def validate_requirements_coverage():
    """Validate that the implementation covers the specified requirements"""
    file_path = os.path.join(os.path.dirname(__file__), 'functions', 'order_api.py')
    
    try:
        with open(file_path, 'r') as f:
            content = f.read()
        
        # Check for requirement-specific implementations
        requirements_coverage = {
            'DynamoDB transaction support': ['transact_write_items', 'TransactItems'],
            'Atomic inventory deduction': ['availableQuantity', 'ConditionalCheckFailedException'],
            'Order creation': ['create_order', 'orderId', 'POST'],
            'Order history retrieval': ['get_user_orders', 'query', 'pagination'],
            'Order status tracking': ['update_order_status', 'status', 'trackingNumber'],
            'Error handling for conflicts': ['ConditionalCheckFailedException', 'Inventory conflict'],
            'Payment processing': ['_process_payment', 'paymentMethod'],
            'Comprehensive error handling': ['try:', 'except', 'logger', 'traceback'],
            'Cart clearing after order': ['_clear_user_cart', 'delete_item'],
            'Product validation': ['_get_product_info', '_check_inventory'],
            'Tax and shipping calculation': ['_calculate_tax', '_calculate_shipping']
        }
        
        covered_requirements = []
        missing_requirements = []
        
        for requirement, keywords in requirements_coverage.items():
            if any(keyword.lower() in content.lower() for keyword in keywords):
                covered_requirements.append(requirement)
            else:
                missing_requirements.append(requirement)
        
        if missing_requirements:
            print(f"❌ Missing requirement coverage: {missing_requirements}")
            return False
        
        print(f"✅ Requirements coverage validation passed - {len(covered_requirements)}/{len(requirements_coverage)} requirements covered")
        return True
        
    except Exception as e:
        print(f"❌ Error validating requirements coverage: {e}")
        return False

def validate_api_endpoints():
    """Validate that all required API endpoints are implemented"""
    file_path = os.path.join(os.path.dirname(__file__), 'functions', 'order_api.py')
    
    try:
        with open(file_path, 'r') as f:
            content = f.read()
        
        # Check for API endpoint routing
        required_endpoints = {
            'POST /orders': ['POST', '/orders', 'create_order'],
            'GET /orders/{orderId}': ['GET', '/orders/', 'get_order'],
            'GET /users/{userId}/orders': ['GET', '/users/', '/orders', 'get_user_orders'],
            'PUT /orders/{orderId}': ['PUT', '/orders/', 'update_order_status'],
            'OPTIONS (CORS)': ['OPTIONS', 'Access-Control-Allow']
        }
        
        missing_endpoints = []
        
        for endpoint, keywords in required_endpoints.items():
            if not all(keyword in content for keyword in keywords):
                missing_endpoints.append(endpoint)
        
        if missing_endpoints:
            print(f"❌ Missing API endpoints: {missing_endpoints}")
            return False
        
        print(f"✅ API endpoints validation passed - All {len(required_endpoints)} endpoints implemented")
        return True
        
    except Exception as e:
        print(f"❌ Error validating API endpoints: {e}")
        return False

def validate_transaction_logic():
    """Validate DynamoDB transaction implementation"""
    file_path = os.path.join(os.path.dirname(__file__), 'functions', 'order_api.py')
    
    try:
        with open(file_path, 'r') as f:
            content = f.read()
        
        # Check for transaction-specific implementation
        transaction_features = {
            'Transaction execution': ['transact_write_items', '_execute_order_transaction'],
            'Order creation in transaction': ['Put', 'TableName', 'orders_table'],
            'Inventory update in transaction': ['Update', 'availableQuantity', 'inventory_table'],
            'Conditional checks': ['ConditionExpression', 'attribute_not_exists', 'minQuantity'],
            'Transaction error handling': ['ConditionalCheckFailedException', 'Inventory conflict'],
            'Atomic operations': ['TransactItems', 'transact_items']
        }
        
        missing_features = []
        
        for feature, keywords in transaction_features.items():
            if not any(keyword in content for keyword in keywords):
                missing_features.append(feature)
        
        if missing_features:
            print(f"❌ Missing transaction features: {missing_features}")
            return False
        
        print(f"✅ Transaction logic validation passed - All {len(transaction_features)} features implemented")
        return True
        
    except Exception as e:
        print(f"❌ Error validating transaction logic: {e}")
        return False

def run_validation():
    """Run all validation checks"""
    print("🔍 Validating Order Management API implementation...\n")
    
    validations = [
        ("File Structure", validate_order_api_file),
        ("Test File", validate_test_file),
        ("Functionality", validate_functionality),
        ("Requirements Coverage", validate_requirements_coverage),
        ("API Endpoints", validate_api_endpoints),
        ("Transaction Logic", validate_transaction_logic)
    ]
    
    passed = 0
    total = len(validations)
    
    for name, validation_func in validations:
        print(f"Checking {name}...")
        if validation_func():
            passed += 1
        print()
    
    print(f"📊 Validation Results: {passed}/{total} checks passed")
    
    if passed == total:
        print("🎉 All validations passed! Order Management API implementation meets requirements.")
        return True
    else:
        print("❌ Some validations failed. Please review the implementation.")
        return False

if __name__ == '__main__':
    success = run_validation()
    sys.exit(0 if success else 1)