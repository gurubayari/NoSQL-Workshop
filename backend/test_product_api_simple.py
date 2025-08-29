#!/usr/bin/env python3
"""
Simple test script for Product API Lambda function
"""
import json
import sys
import os
from unittest.mock import Mock, patch
from datetime import datetime

# Add the functions directory to the path
sys.path.append(os.path.join(os.path.dirname(__file__), 'functions'))
sys.path.append(os.path.join(os.path.dirname(__file__), 'shared'))

# Mock ObjectId for testing
class MockObjectId:
    def __init__(self, oid_string):
        self.oid_string = oid_string
    
    def __str__(self):
        return self.oid_string
    
    @staticmethod
    def is_valid(oid):
        return True

def test_product_api_imports():
    """Test that all imports work correctly"""
    try:
        from product_api import ProductAPI, lambda_handler
        print("✅ Product API imports successful")
        return True
    except Exception as e:
        print(f"❌ Import error: {e}")
        return False

def test_product_api_initialization():
    """Test ProductAPI class initialization"""
    try:
        with patch('product_api.get_documentdb_collection') as mock_collection:
            mock_collection.return_value = Mock()
            from product_api import ProductAPI
            
            api = ProductAPI()
            assert hasattr(api, 'products_collection')
            assert hasattr(api, 'reviews_collection')
            print("✅ ProductAPI initialization successful")
            return True
    except Exception as e:
        print(f"❌ Initialization error: {e}")
        return False

def test_lambda_handler_routing():
    """Test lambda handler routing logic"""
    try:
        with patch('product_api.ProductAPI') as mock_api_class:
            mock_api = Mock()
            mock_api_class.return_value = mock_api
            mock_api.list_products.return_value = {
                'statusCode': 200,
                'headers': {'Content-Type': 'application/json'},
                'body': json.dumps({'products': []})
            }
            
            from product_api import lambda_handler
            
            # Test GET /products
            event = {
                'httpMethod': 'GET',
                'path': '/api/products',
                'queryStringParameters': {}
            }
            
            response = lambda_handler(event, {})
            assert response['statusCode'] == 200
            mock_api.list_products.assert_called_once()
            
            print("✅ Lambda handler routing successful")
            return True
    except Exception as e:
        print(f"❌ Lambda handler error: {e}")
        return False

def test_product_list_logic():
    """Test product listing logic"""
    try:
        with patch('product_api.get_documentdb_collection') as mock_collection:
            with patch('product_api.cache_get') as mock_cache_get:
                with patch('product_api.cache_set') as mock_cache_set:
                    mock_collection.return_value = Mock()
                    mock_cache_get.return_value = None  # Cache miss
                    
                    from product_api import ProductAPI
                    
                    api = ProductAPI()
                    
                    # Mock database response
                    sample_product = {
                        '_id': ObjectId('507f1f77bcf86cd799439011'),
                        'title': 'Test Product',
                        'price': 99.99,
                        'category': 'Electronics',
                        'created_at': datetime.now(),
                        'updated_at': datetime.now()
                    }
                    
                    mock_cursor = Mock()
                    mock_cursor.__iter__ = Mock(return_value=iter([sample_product]))
                    api.products_collection.find.return_value.sort.return_value.skip.return_value.limit.return_value = mock_cursor
                    api.products_collection.count_documents.return_value = 1
                    
                    # Test event
                    event = {
                        'queryStringParameters': {
                            'page': '1',
                            'limit': '20'
                        }
                    }
                    
                    response = api.list_products(event)
                    assert response['statusCode'] == 200
                    
                    body = json.loads(response['body'])
                    assert 'products' in body
                    assert 'pagination' in body
                    
                    print("✅ Product listing logic successful")
                    return True
    except Exception as e:
        print(f"❌ Product listing error: {e}")
        return False

def test_product_detail_logic():
    """Test product detail retrieval logic"""
    try:
        with patch('product_api.get_documentdb_collection') as mock_collection:
            with patch('product_api.cache_get') as mock_cache_get:
                with patch('product_api.cache_set') as mock_cache_set:
                    mock_collection.return_value = Mock()
                    mock_cache_get.return_value = None  # Cache miss
                    
                    from product_api import ProductAPI
                    
                    api = ProductAPI()
                    
                    # Mock database response
                    sample_product = {
                        '_id': ObjectId('507f1f77bcf86cd799439011'),
                        'title': 'Test Product',
                        'price': 99.99,
                        'category': 'Electronics',
                        'created_at': datetime.now(),
                        'updated_at': datetime.now()
                    }
                    
                    api.products_collection.find_one.return_value = sample_product
                    api.reviews_collection.aggregate.return_value = []
                    
                    # Test event
                    event = {
                        'pathParameters': {
                            'id': '507f1f77bcf86cd799439011'
                        }
                    }
                    
                    response = api.get_product_detail(event)
                    assert response['statusCode'] == 200
                    
                    body = json.loads(response['body'])
                    assert 'product' in body
                    assert 'reviews_summary' in body
                    assert 'related_products' in body
                    
                    print("✅ Product detail logic successful")
                    return True
    except Exception as e:
        print(f"❌ Product detail error: {e}")
        return False

def test_search_logic():
    """Test product search logic"""
    try:
        with patch('product_api.get_documentdb_collection') as mock_collection:
            with patch('product_api.cache_get') as mock_cache_get:
                with patch('product_api.cache_set') as mock_cache_set:
                    mock_collection.return_value = Mock()
                    mock_cache_get.return_value = None  # Cache miss
                    
                    from product_api import ProductAPI
                    
                    api = ProductAPI()
                    
                    # Mock database response
                    sample_product = {
                        '_id': ObjectId('507f1f77bcf86cd799439011'),
                        'title': 'Wireless Headphones',
                        'price': 199.99,
                        'category': 'Electronics',
                        'created_at': datetime.now(),
                        'updated_at': datetime.now()
                    }
                    
                    mock_cursor = Mock()
                    mock_cursor.__iter__ = Mock(return_value=iter([sample_product]))
                    api.products_collection.find.return_value.sort.return_value.skip.return_value.limit.return_value = mock_cursor
                    api.products_collection.count_documents.return_value = 1
                    
                    # Test event
                    event = {
                        'httpMethod': 'POST',
                        'body': json.dumps({
                            'q': 'wireless',
                            'page': '1',
                            'limit': '10'
                        })
                    }
                    
                    response = api.search_products(event)
                    assert response['statusCode'] == 200
                    
                    body = json.loads(response['body'])
                    assert 'products' in body
                    assert 'query' in body
                    assert 'suggestions' in body
                    assert body['query'] == 'wireless'
                    
                    print("✅ Product search logic successful")
                    return True
    except Exception as e:
        print(f"❌ Product search error: {e}")
        return False

def run_all_tests():
    """Run all tests"""
    print("🧪 Running Product API tests...\n")
    
    tests = [
        test_product_api_imports,
        test_product_api_initialization,
        test_lambda_handler_routing,
        test_product_list_logic,
        test_product_detail_logic,
        test_search_logic
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        if test():
            passed += 1
        print()
    
    print(f"📊 Test Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed! Product API implementation is working correctly.")
        return True
    else:
        print("❌ Some tests failed. Please check the implementation.")
        return False

if __name__ == '__main__':
    success = run_all_tests()
    sys.exit(0 if success else 1)