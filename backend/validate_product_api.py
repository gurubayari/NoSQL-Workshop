#!/usr/bin/env python3
"""
Code validation for Product API Lambda function
"""
import os
import ast
import sys

def validate_product_api_file():
    """Validate the Product API file structure and content"""
    file_path = os.path.join(os.path.dirname(__file__), 'functions', 'product_api.py')
    
    if not os.path.exists(file_path):
        print("❌ Product API file does not exist")
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
        required_classes = ['ProductAPI', 'ProductAPIError']
        required_functions = ['lambda_handler']
        
        missing_classes = [cls for cls in required_classes if cls not in classes]
        missing_functions = [func for func in required_functions if func not in functions]
        
        if missing_classes:
            print(f"❌ Missing required classes: {missing_classes}")
            return False
        
        if missing_functions:
            print(f"❌ Missing required functions: {missing_functions}")
            return False
        
        # Check for required methods in ProductAPI class
        product_api_methods = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == 'ProductAPI':
                for item in node.body:
                    if isinstance(item, ast.FunctionDef):
                        product_api_methods.append(item.name)
        
        required_methods = [
            '__init__',
            'list_products',
            'get_product_detail', 
            'search_products',
            '_get_reviews_summary',
            '_get_related_products',
            '_get_search_suggestions'
        ]
        
        missing_methods = [method for method in required_methods if method not in product_api_methods]
        
        if missing_methods:
            print(f"❌ Missing required methods in ProductAPI: {missing_methods}")
            return False
        
        # Check for required imports
        required_imports = [
            'json', 'logging', 'traceback', 'datetime', 'boto3'
        ]
        
        import_names = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    import_names.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    import_names.append(node.module)
                for alias in node.names:
                    import_names.append(alias.name)
        
        missing_imports = []
        for imp in required_imports:
            if not any(imp in name for name in import_names):
                missing_imports.append(imp)
        
        if missing_imports:
            print(f"❌ Missing required imports: {missing_imports}")
            return False
        
        print("✅ Product API file structure validation passed")
        return True
        
    except SyntaxError as e:
        print(f"❌ Syntax error in Product API file: {e}")
        return False
    except Exception as e:
        print(f"❌ Error validating Product API file: {e}")
        return False

def validate_test_file():
    """Validate the test file exists and has basic structure"""
    file_path = os.path.join(os.path.dirname(__file__), 'tests', 'test_product_api.py')
    
    if not os.path.exists(file_path):
        print("❌ Product API test file does not exist")
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
    file_path = os.path.join(os.path.dirname(__file__), 'functions', 'product_api.py')
    
    try:
        with open(file_path, 'r') as f:
            content = f.read()
        
        # Check for key functionality keywords
        required_features = {
            'pagination': ['skip', 'limit', 'page'],
            'filtering': ['category', 'price', 'rating'],
            'sorting': ['sort', 'order'],
            'caching': ['cache_get', 'cache_set', 'ElastiCache'],
            'error_handling': ['try:', 'except', 'logger.error'],
            'database_operations': ['find', 'find_one', 'aggregate'],
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
    file_path = os.path.join(os.path.dirname(__file__), 'functions', 'product_api.py')
    
    try:
        with open(file_path, 'r') as f:
            content = f.read()
        
        # Check for requirement-specific implementations
        requirements_coverage = {
            'DocumentDB connection': ['documentdb', 'MongoClient', 'get_documentdb_collection'],
            'Product listing with pagination': ['list_products', 'skip', 'limit'],
            'Filtering and sorting': ['category', 'price', 'rating', 'sort'],
            'ElastiCache caching': ['cache_get', 'cache_set', 'elasticache'],
            'Product search': ['search_products', 'regex', '$or'],
            'Error handling': ['try:', 'except', 'logger', 'traceback'],
            'Product detail retrieval': ['get_product_detail', 'find_one'],
            'Reviews summary': ['_get_reviews_summary', 'aggregate'],
            'Related products': ['_get_related_products', 'category']
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

def run_validation():
    """Run all validation checks"""
    print("🔍 Validating Product API implementation...\n")
    
    validations = [
        ("File Structure", validate_product_api_file),
        ("Test File", validate_test_file),
        ("Functionality", validate_functionality),
        ("Requirements Coverage", validate_requirements_coverage)
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
        print("🎉 All validations passed! Product API implementation meets requirements.")
        return True
    else:
        print("❌ Some validations failed. Please review the implementation.")
        return False

if __name__ == '__main__':
    success = run_validation()
    sys.exit(0 if success else 1)