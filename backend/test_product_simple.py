#!/usr/bin/env python3
"""
Simple validation test for Product API Lambda function
"""
import json
import sys
import os

# Add the functions directory to the path
sys.path.append(os.path.join(os.path.dirname(__file__), 'functions'))
sys.path.append(os.path.join(os.path.dirname(__file__), 'shared'))

def test_imports():
    """Test that the Product API can be imported"""
    try:
        # Mock the dependencies that might not be available
        import types
        
        # Create mock modules
        bson_module = types.ModuleType('bson')
        pymongo_module = types.ModuleType('pymongo')
        pymongo_errors_module = types.ModuleType('pymongo.errors')
        redis_module = types.ModuleType('redis')
        boto3_module = types.ModuleType('boto3')
        
        sys.modules['bson'] = bson_module
        sys.modules['pymongo'] = pymongo_module
        sys.modules['pymongo.errors'] = pymongo_errors_module
        sys.modules['redis'] = redis_module
        sys.modules['boto3'] = boto3_module
        
        # Mock ObjectId
        class MockObjectId:
            def __init__(self, oid_string='507f1f77bcf86cd799439011'):
                self.oid_string = oid_string
            def __str__(self):
                return self.oid_string
            @staticmethod
            def is_valid(oid):
                return True
        
        bson_module.ObjectId = MockObjectId
        
        # Mock MongoClient
        class MockMongoClient:
            def __init__(self, *args, **kwargs):
                pass
        
        pymongo_module.MongoClient = MockMongoClient
        
        # Mock PyMongoError
        class MockPyMongoError(Exception):
            pass
        
        pymongo_errors_module.PyMongoError = MockPyMongoError
        
        # Now try to import
        from product_api import ProductAPI, lambda_handler
        print("✅ Product API imports successful")
        return True
    except Exception as e:
        print(f"❌ Import error: {e}")
        return False

def test_lambda_handler_structure():
    """Test that lambda handler has correct structure"""
    try:
        from product_api import lambda_handler
        
        # Test with unsupported method
        event = {
            'httpMethod': 'DELETE',
            'path': '/api/products'
        }
        
        response = lambda_handler(event, {})
        
        # Should return method not allowed
        assert response['statusCode'] == 405
        assert 'headers' in response
        assert 'body' in response
        
        body = json.loads(response['body'])
        assert 'error' in body
        assert 'Method not allowed' in body['error']
        
        print("✅ Lambda handler structure test successful")
        return True
    except Exception as e:
        print(f"❌ Lambda handler structure error: {e}")
        return False

def test_response_format():
    """Test that responses have correct format"""
    try:
        from product_api import lambda_handler
        
        # Test with unsupported method to get a known response
        event = {
            'httpMethod': 'PATCH',
            'path': '/api/products'
        }
        
        response = lambda_handler(event, {})
        
        # Check response structure
        required_keys = ['statusCode', 'headers', 'body']
        for key in required_keys:
            assert key in response, f"Missing key: {key}"
        
        # Check headers
        assert 'Content-Type' in response['headers']
        assert 'Access-Control-Allow-Origin' in response['headers']
        assert response['headers']['Content-Type'] == 'application/json'
        assert response['headers']['Access-Control-Allow-Origin'] == '*'
        
        # Check body is valid JSON
        body = json.loads(response['body'])
        assert isinstance(body, dict)
        
        print("✅ Response format test successful")
        return True
    except Exception as e:
        print(f"❌ Response format error: {e}")
        return False

def test_error_handling():
    """Test error handling in lambda handler"""
    try:
        from product_api import lambda_handler
        
        # Test with malformed event
        event = {}  # Missing required fields
        
        response = lambda_handler(event, {})
        
        # Should handle gracefully
        assert 'statusCode' in response
        assert 'headers' in response
        assert 'body' in response
        
        print("✅ Error handling test successful")
        return True
    except Exception as e:
        print(f"❌ Error handling test error: {e}")
        return False

def run_tests():
    """Run all validation tests"""
    print("🧪 Running Product API validation tests...\n")
    
    tests = [
        test_imports,
        test_lambda_handler_structure,
        test_response_format,
        test_error_handling
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        try:
            if test():
                passed += 1
        except Exception as e:
            print(f"❌ Test failed with exception: {e}")
        print()
    
    print(f"📊 Test Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All validation tests passed! Product API structure is correct.")
        return True
    else:
        print("❌ Some tests failed. Please check the implementation.")
        return False

if __name__ == '__main__':
    success = run_tests()
    sys.exit(0 if success else 1)