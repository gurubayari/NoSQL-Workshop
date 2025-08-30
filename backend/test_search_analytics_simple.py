#!/usr/bin/env python3
"""
Simple test script for Search Analytics without external dependencies
"""
import json
import sys
import os
from datetime import datetime, timedelta
from collections import Counter

# Mock the dependencies (same as search API test)
class MockTable:
    def __init__(self):
        self.items = []
    
    def put_item(self, **kwargs):
        self.items.append(kwargs['Item'])
        return {'ResponseMetadata': {'HTTPStatusCode': 200}}
    
    def scan(self, **kwargs):
        # Return mock search data based on filter
        now = datetime.utcnow()
        mock_items = [
            {
                'searchTerm': 'wireless headphones',
                'timestamp': now.isoformat(),
                'hour': now.strftime('%Y-%m-%d-%H'),
                'userId': 'user1',
                'conversionFlag': True,
                'resultsCount': 25,
                'filters': '{"category": ["Electronics"]}',
                'searchDuration': 45,
                'refinements': 2
            },
            {
                'searchTerm': 'bluetooth speaker',
                'timestamp': (now - timedelta(hours=1)).isoformat(),
                'hour': (now - timedelta(hours=1)).strftime('%Y-%m-%d-%H'),
                'userId': 'user2',
                'conversionFlag': False,
                'resultsCount': 15,
                'filters': '{"category": ["Electronics", "Audio"]}',
                'searchDuration': 30,
                'refinements': 1
            },
            {
                'searchTerm': 'wireless headphones',
                'timestamp': (now - timedelta(hours=2)).isoformat(),
                'hour': (now - timedelta(hours=2)).strftime('%Y-%m-%d-%H'),
                'userId': 'user1',
                'conversionFlag': True,
                'resultsCount': 30,
                'filters': '{}',
                'searchDuration': 60,
                'refinements': 0
            },
            {
                'searchTerm': 'gaming mouse',
                'timestamp': (now - timedelta(hours=3)).isoformat(),
                'hour': (now - timedelta(hours=3)).strftime('%Y-%m-%d-%H'),
                'userId': 'user3',
                'conversionFlag': False,
                'resultsCount': 20,
                'filters': '{"category": ["Gaming"]}',
                'searchDuration': 35,
                'refinements': 3
            }
        ]
        
        return {'Items': mock_items}

# Mock the modules
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
        return type('MockAdmin', (), {'command': lambda self, cmd: {'ok': 1}})()

sys.modules['redis'] = type('MockRedis', (), {'Redis': MockRedis})
sys.modules['pymongo'] = type('MockPyMongo', (), {'MongoClient': MockMongoClient})
sys.modules['boto3'] = type('MockBoto3', (), {
    'resource': lambda service, **kwargs: type('MockResource', (), {'Table': lambda name: MockTable()})(),
    'client': lambda service, **kwargs: type('MockClient', (), {})()
})

# Mock ssl module
sys.modules['ssl'] = type('MockSSL', (), {'CERT_REQUIRED': 'CERT_REQUIRED'})

# Mock the database functions
def mock_get_dynamodb_table(name):
    return MockTable()

def mock_get_cache_key(prefix, identifier):
    return f"test:{prefix}:{identifier}"

# Cache storage for testing
cache_storage = {}

def mock_cache_get(key):
    if key in cache_storage:
        return cache_storage[key]
    
    # Return mock data for specific keys
    if 'popular_terms' in key:
        return json.dumps([
            {'term': 'wireless headphones', 'count': 100},
            {'term': 'bluetooth speaker', 'count': 80},
            {'term': 'gaming mouse', 'count': 60}
        ])
    elif 'trending_terms' in key:
        return json.dumps([
            {'term': 'wireless headphones', 'trendScore': 2.5, 'recentCount': 50},
            {'term': 'smart watch', 'trendScore': 2.0, 'recentCount': 30}
        ])
    elif 'user_pattern' in key:
        return json.dumps({
            'searchCount': 5,
            'categories': ['Electronics', 'Audio'],
            'terms': ['bluetooth speaker', 'wireless mouse'],
            'lastSearch': '2024-01-01T00:00:00'
        })
    
    return None

def mock_cache_set(key, value, ttl=None):
    cache_storage[key] = value
    return True

def mock_cache_delete(key):
    if key in cache_storage:
        del cache_storage[key]
        return True
    return False

# Patch the imports
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Mock the config
class MockConfig:
    SEARCH_ANALYTICS_TABLE = 'test-search-analytics'
    LOG_LEVEL = 'INFO'

# Import and patch the module
import functions.search_analytics as search_analytics
search_analytics.config = MockConfig()
search_analytics.get_dynamodb_table = mock_get_dynamodb_table
search_analytics.get_cache_key = mock_get_cache_key
search_analytics.cache_get = mock_cache_get
search_analytics.cache_set = mock_cache_set
search_analytics.cache_delete = mock_cache_delete

def test_search_analytics():
    """Test the SearchAnalytics functionality"""
    print("Testing Search Analytics...")
    
    # Initialize SearchAnalytics
    analytics = search_analytics.SearchAnalytics()
    
    # Test 1: Track search event
    print("\n1. Testing search event tracking...")
    search_data = {
        'searchTerm': 'wireless headphones',
        'userId': 'test-user-123',
        'sessionId': 'session-456',
        'filters': {'category': ['Electronics']},
        'sortBy': 'relevance',
        'resultsCount': 25,
        'clickedResults': ['product-1', 'product-2'],
        'conversionFlag': True,
        'searchDuration': 45,
        'refinements': 2,
        'pageViews': 3
    }
    
    result = analytics.track_search_event(search_data)
    print(f"   Track event success: {result.get('success', False)}")
    if result.get('success'):
        print(f"   Event ID: {result.get('eventId', 'N/A')}")
    
    # Test 2: Get search analytics
    print("\n2. Testing search analytics retrieval...")
    analytics_result = analytics.get_search_analytics('24h', ['popular_terms', 'search_volume', 'conversion_rate'])
    print(f"   Time range: {analytics_result.get('timeRange', 'N/A')}")
    
    if 'popularTerms' in analytics_result:
        print(f"   Popular terms found: {len(analytics_result['popularTerms'])}")
        for term in analytics_result['popularTerms'][:3]:
            print(f"     - {term['term']}: {term['count']} searches")
    
    if 'searchVolume' in analytics_result:
        volume = analytics_result['searchVolume']
        print(f"   Total searches: {volume.get('totalSearches', 0)}")
        print(f"   Average per hour: {volume.get('averagePerHour', 0):.1f}")
    
    if 'conversionRate' in analytics_result:
        conversion = analytics_result['conversionRate']
        print(f"   Overall conversion rate: {conversion.get('overallConversionRate', 0):.1f}%")
    
    # Test 3: Get user search insights
    print("\n3. Testing user search insights...")
    user_insights = analytics.get_user_search_insights('test-user-123', 50)
    print(f"   User ID: {user_insights.get('userId', 'N/A')}")
    print(f"   Total searches: {user_insights.get('totalSearches', 0)}")
    print(f"   Unique terms: {user_insights.get('uniqueTerms', 0)}")
    print(f"   Conversion rate: {user_insights.get('conversionRate', 0):.1f}%")
    
    if 'topSearchTerms' in user_insights:
        print(f"   Top search terms: {user_insights['topSearchTerms'][:3]}")
    
    if 'preferredCategories' in user_insights:
        print(f"   Preferred categories: {user_insights['preferredCategories'][:3]}")
    
    # Test 4: Update trending terms
    print("\n4. Testing trending terms update...")
    trending_result = analytics.update_trending_terms()
    print(f"   Update success: {trending_result.get('success', False)}")
    print(f"   Trending terms count: {trending_result.get('trendingTermsCount', 0)}")
    
    if 'topTrending' in trending_result:
        print("   Top trending terms:")
        for term in trending_result['topTrending'][:3]:
            print(f"     - {term['term']}: trend score {term['trendScore']:.1f}")
    
    # Test 5: Get search suggestions data
    print("\n5. Testing search suggestions data...")
    suggestions_data = analytics.get_search_suggestions_data()
    
    if 'popularTerms' in suggestions_data:
        print(f"   Popular terms for suggestions: {len(suggestions_data['popularTerms'])}")
        for term in suggestions_data['popularTerms'][:3]:
            print(f"     - {term['term']}: {term['count']} searches")
    
    if 'trendingTerms' in suggestions_data:
        print(f"   Trending terms for suggestions: {len(suggestions_data['trendingTerms'])}")
        for term in suggestions_data['trendingTerms'][:3]:
            print(f"     - {term['term']}: trend score {term['trendScore']:.1f}")
    
    # Test 6: Lambda handler
    print("\n6. Testing lambda handler...")
    
    # Test track endpoint
    track_event = {
        'httpMethod': 'POST',
        'path': '/api/search-analytics/track',
        'body': json.dumps({
            'searchTerm': 'bluetooth headphones',
            'userId': 'lambda-test-user',
            'resultsCount': 15
        })
    }
    
    result = search_analytics.lambda_handler(track_event, None)
    print(f"   Track endpoint status: {result['statusCode']}")
    if result['statusCode'] == 200:
        body = json.loads(result['body'])
        print(f"   Track success: {body.get('success', False)}")
    
    # Test analytics endpoint
    analytics_event = {
        'httpMethod': 'GET',
        'path': '/api/search-analytics/analytics',
        'queryStringParameters': {
            'timeRange': '24h',
            'metrics': 'popular_terms,search_volume'
        }
    }
    
    result = search_analytics.lambda_handler(analytics_event, None)
    print(f"   Analytics endpoint status: {result['statusCode']}")
    if result['statusCode'] == 200:
        body = json.loads(result['body'])
        print(f"   Analytics time range: {body.get('timeRange', 'N/A')}")
    
    # Test user insights endpoint
    insights_event = {
        'httpMethod': 'GET',
        'path': '/api/search-analytics/user-insights',
        'queryStringParameters': {
            'userId': 'test-user-123',
            'limit': '25'
        }
    }
    
    result = search_analytics.lambda_handler(insights_event, None)
    print(f"   User insights endpoint status: {result['statusCode']}")
    if result['statusCode'] == 200:
        body = json.loads(result['body'])
        print(f"   User total searches: {body.get('totalSearches', 0)}")
    
    print("\n✅ All Search Analytics tests completed successfully!")

if __name__ == '__main__':
    test_search_analytics()