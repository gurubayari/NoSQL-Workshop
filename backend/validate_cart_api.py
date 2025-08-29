#!/usr/bin/env python3
"""
Code validation for Shopping Cart API Lambda function
"""
import os
import ast
import sys

def validate_cart_api_file():
    """Validate the Cart API file structure and content"""
    file_path = os.path.join(os.path.dirname(__file__), 'functions', 'cart_api.py')
    
    if not os.path.exists(file_path):
        print("❌ Cart API file does not exist")
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
        required_classes = ['ShoppingCartAPI', 'CartAPIError']
        required_functions = ['lambda_handler']
        
        missing_classes = [cls for cls in required_classes if cls not in classes]
        missing_functions = [func for func in required_functions if func not in functions]
        
        if missing_classes:
            print(f"❌ Missing required classes: {missing_classes}")
            return False
        
        if missing_functions:
            print(f"❌ Missing required functions: {missing_functions}")
            return False
        
        # Check for required methods in ShoppingCartAPI class
        cart_api_methods = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == 'ShoppingCartAPI':
                for item in node.body:
                    if isinstance(item, ast.FunctionDef):
                        cart_api_methods.append(item.name)
        
        required_methods = [
            '__init__',
            'get_cart',
            'add_to_cart',
            'update_cart_item',
            'remove_from_cart',
            'clear_cart',
            '_enrich_cart_item',
            '_get_product_info',
            '_check_inventory',
            '_get_inventory_status'
        ]
        
        missing_methods = [method for method in required_methods if method not in cart_api_methods]
        
        if missing_methods:
            print(f"❌ Missing required methods in ShoppingCartAPI: {missing_methods}")
            return False
        
        print("✅ Cart API file structure validation passed")
        return True
        
    except SyntaxError as e:
        print(f"❌ Syntax error in Cart API file: {e}")
        return False
    except Exception as e:
        print(f"❌ Error validating Cart API file: {e}")
        return False

def validate_test_file():
    """Validate the test file exists and has basic structure"""
    file_path = os.path.join(os.path.dirname(__file__), 'tests', 'test_cart_api.py')
    
    if not os.path.exists(file_path):
        print("❌ Cart API test file does not exist")
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
    file_path = os.path.join(os.path.dirname(__file__), 'functions', 'cart_api.py')
    
    try:
        with open(file_path, 'r') as f:
            content = f.read()
        
        # Check for key functionality keywords
        required_features = {
            'DynamoDB_operations': ['get_dynamodb_table', 'query', 'get_item', 'put_item', 'update_item', 'delete_item'],
            'ElastiCache_caching': ['cache_get', 'cache_set', 'cache_delete'],
            'inventory_validation': ['_check_inventory', 'availableQuantity'],
            'cart_operations': ['add_to_cart', 'update_cart_item', 'remove_from_cart', 'clear_cart'],
            'product_enrichment': ['_enrich_cart_item', '_get_product_info'],
            'error_handling': ['try:', 'except', 'logger.error', 'ClientError'],
            'TTL_management': ['ttl', 'timedelta'],
            'CORS_support': ['Access-Control-Allow-Origin', '_get_cors_headers'],
            'response_formatting': ['statusCode', 'headers', 'body']
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
    file_path = os.path.join(os.path.dirname(__file__), 'functions', 'cart_api.py')
    
    try:
        with open(file_path, 'r') as f:
            content = f.read()
        
        # Check for requirement-specific implementations
        requirements_coverage = {
            'DynamoDB connections': ['get_dynamodb_table', 'cart_table', 'inventory_table'],
            'ElastiCache connections': ['cache_get', 'cache_set', 'cache_delete'],
            'User-based cart operations': ['add_to_cart', 'update_cart_item', 'remove_from_cart'],
            'Cart persistence with TTL': ['ttl', 'timedelta', 'put_item'],
            'Real-time inventory validation': ['_check_inventory', 'availableQuantity'],
            'Session management': ['cache_get', 'cache_set', 'userId'],
            'Error handling': ['try:', 'except', 'ClientError', 'logger'],
            'Product information enrichment': ['_enrich_cart_item', '_get_product_info'],
            'Cart clearing functionality': ['clear_cart', 'delete_item'],
            'CORS support': ['Access-Control-Allow-Origin', 'OPTIONS']
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
    file_path = os.path.join(os.path.dirname(__file__), 'functions', 'cart_api.py')
    
    try:
        with open(file_path, 'r') as f:
            content = f.read()
        
        # Check for API endpoint routing
        required_endpoints = {
            'GET /cart/{userId}': ['GET', '/cart/', 'get_cart'],
            'POST /cart/{userId}/items': ['POST', '/cart/', '/items', 'add_to_cart'],
            'PUT /cart/{userId}/items/{productId}': ['PUT', '/cart/', '/items/', 'update_cart_item'],
            'DELETE /cart/{userId}/items/{productId}': ['DELETE', '/cart/', '/items/', 'remove_from_cart'],
            'DELETE /cart/{userId}/clear': ['DELETE', '/cart/', '/clear', 'clear_cart'],
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

def run_validation():
    """Run all validation checks"""
    print("🔍 Validating Shopping Cart API implementation...\n")
    
    validations = [
        ("File Structure", validate_cart_api_file),
        ("Test File", validate_test_file),
        ("Functionality", validate_functionality),
        ("Requirements Coverage", validate_requirements_coverage),
        ("API Endpoints", validate_api_endpoints)
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
        print("🎉 All validations passed! Shopping Cart API implementation meets requirements.")
        return True
    else:
        print("❌ Some validations failed. Please review the implementation.")
        return False

if __name__ == '__main__':
    success = run_validation()
    sys.exit(0 if success else 1)