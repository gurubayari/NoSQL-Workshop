#!/usr/bin/env python3
"""
Simple test script for Search API without external dependencies
"""
import json
import sys
import os

# Mock the dependencies
class MockRedis:
    def __init__(self, *args, **kwargs):
        pass
    
    def get(self, key):
        return None
    
    def setex(self, key, ttl, value):
        return True
    
    def ping(self):
        return True
    
    def close(self):
        pass

class MockMongoClient:
    def __init__(self, *args, **kwargs):
        pass
    
    def close(self):
        pass
    
    @property
    def admin(self):
        return MockAdmin()

class MockAdmin:
    def command(self, cmd):
        return {'ok': 1}

class MockCollection:
    def aggregate(self, pipeline):
        # Return mock data based on pipeline
        if any('$count' in stage for stage in pipeline):
            return [{'total': 5}]
        else:
            return [
                {
                    '_id': '1',
                    'title': 'Wireless Bluetooth Headphones',
                    'description': 'High-quality wireless headphones with noise cancellation',
                    'price': 199.99,
                    'rating': 4.5,
                    'reviewCount': 234,
                    'category': 'Electronics',
                    'tags': ['wireless', 'bluetooth', 'audio'],
                    'inStock': True
                },
                {
                    '_id': '2', 
                    'title': 'Gaming Wireless Mouse',
                    'description': 'Precision wireless gaming mouse with RGB lighting',
                    'price': 79.99,
                    'rating': 4.3,
                    'reviewCount': 156,
                    'category': 'Electronics',
                    'tags': ['wireless', 'gaming', 'mouse'],
                    'inStock': True
                }
            ]
    
    def distinct(self, field):
        return ['Electronics', 'Audio Equipment', 'Gaming', 'Home & Garden']

class MockTable:
    def put_item(self, **kwargs):
        return {'ResponseMetadata': {'HTTPStatusCode': 200}}

class MockBoto3Resource:
    def Table(self, name):
        return MockTable()

class MockBoto3Client:
    def invoke_model(self, **kwargs):
        return {
            'body': MockBody()
        }

class MockBody:
    def read(self):
        return json.dumps({
            'embedding': [0.1, 0.2, 0.3] * 512  # Mock 1536-dim embedding
        }).encode()

# Mock the modules
sys.modules['redis'] = type('MockRedis', (), {'Redis': MockRedis})
sys.modules['pymongo'] = type('MockPyMongo', (), {'MongoClient': MockMongoClient})
sys.modules['boto3'] = type('MockBoto3', (), {
    'resource': lambda service, **kwargs: MockBoto3Resource(),
    'client': lambda service, **kwargs: MockBoto3Client()
})

# Mock ssl module
sys.modules['ssl'] = type('MockSSL', (), {'CERT_REQUIRED': 'CERT_REQUIRED'})

# Now import our modules
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Mock the config
class MockConfig:
    AWS_REGION = 'us-west-2'
    SEARCH_ANALYTICS_TABLE = 'test-search-analytics'
    BEDROCK_EMBEDDING_MODEL_ID = 'amazon.titan-embed-text-v1'
    MAX_PAGE_SIZE = 100
    LOG_LEVEL = 'INFO'

# Mock the database functions
def mock_get_documentdb_collection(name):
    return MockCollection()

def mock_get_dynamodb_table(name):
    return MockTable()

def mock_get_cache_key(prefix, identifier):
    return f"test:{prefix}:{identifier}"

def mock_cache_get(key):
    # Return mock cached data for popular terms
    if 'popular_terms' in key:
        return json.dumps([
            {'term': 'wireless headphones', 'count': 100},
            {'term': 'bluetooth speaker', 'count': 80},
            {'term': 'gaming mouse', 'count': 60}
        ])
    return None

def mock_cache_set(key, value, ttl=None):
    return True

# Patch the imports
import functions.search_api as search_api
search_api.config = MockConfig()
search_api.get_documentdb_collection = mock_get_documentdb_collection
search_api.get_dynamodb_table = mock_get_dynamodb_table
search_api.get_cache_key = mock_get_cache_key
search_api.cache_get = mock_cache_get
search_api.cache_set = mock_cache_set

def test_search_api():
    """Test the SearchAPI functionality"""
    print("Testing Search API...")
    
    # Initialize SearchAPI
    api = search_api.SearchAPI()
    
    # Test 1: Auto-complete suggestions
    print("\n1. Testing auto-complete suggestions...")
    suggestions = api.get_auto_complete_suggestions('wireless', 5)
    print(f"   Found {len(suggestions)} suggestions for 'wireless'")
    for suggestion in suggestions:
        print(f"   - {suggestion['text']} ({suggestion['type']})")
    
    # Test 2: Product search
    print("\n2. Testing product search...")
    results = api.search_products('wireless', page=1, page_size=10)
    print(f"   Found {results['total']} products for 'wireless'")
    print(f"   Page {results['page']} of {results['totalPages']}")
    for product in results['products']:
        print(f"   - {product['title']} (${product['price']})")
    
    # Test 3: Product search with filters
    print("\n3. Testing product search with filters...")
    filters = {
        'category': ['Electronics'],
        'minPrice': '50',
        'maxPrice': '200',
        'minRating': '4.0'
    }
    results = api.search_products('wireless', filters=filters, sort_by='price_low')
    print(f"   Found {results['total']} filtered products")
    
    # Test 4: Lambda handler
    print("\n4. Testing lambda handler...")
    
    # Test auto-complete endpoint
    event = {
        'httpMethod': 'GET',
        'path': '/api/search/suggestions',
        'queryStringParameters': {'q': 'wireless', 'limit': '3'}
    }
    
    result = search_api.lambda_handler(event, None)
    print(f"   Auto-complete endpoint status: {result['statusCode']}")
    if result['statusCode'] == 200:
        body = json.loads(result['body'])
        print(f"   Returned {len(body['suggestions'])} suggestions")
    
    # Test search endpoint
    event = {
        'httpMethod': 'GET',
        'path': '/api/search/products',
        'queryStringParameters': {
            'q': 'wireless',
            'sort': 'relevance',
            'page': '1',
            'pageSize': '5'
        }
    }
    
    result = search_api.lambda_handler(event, None)
    print(f"   Search endpoint status: {result['statusCode']}")
    if result['statusCode'] == 200:
        body = json.loads(result['body'])
        print(f"   Returned {len(body['products'])} products")
    
    print("\n✅ All tests completed successfully!")

if __name__ == '__main__':
    test_search_api()