"""
Integration tests for ElastiCache operations
Tests caching patterns, cache consistency, and invalidation strategies
"""
import pytest
import redis
import json
import time
from datetime import datetime, timedelta
import sys
import os
from unittest.mock import patch, MagicMock

# Add the shared directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'shared'))

from database import cache_get, cache_set, cache_delete, get_cache_key

class TestElastiCacheOperations:
    """Integration tests for ElastiCache operations"""
    
    def setup_method(self):
        """Set up test Redis connection"""
        try:
            # Try to connect to local Redis for testing
            self.redis_client = redis.Redis(host='localhost', port=6379, db=1, decode_responses=True)
            # Test connection
            self.redis_client.ping()
        except Exception:
            # If Redis is not available, use fakeredis for testing
            try:
                import fakeredis
                self.redis_client = fakeredis.FakeRedis(decode_responses=True)
            except ImportError:
                pytest.skip("Redis not available and fakeredis not installed")
        
        # Clear test database
        self.redis_client.flushdb()
    
    def teardown_method(self):
        """Clean up after each test"""
        if hasattr(self, 'redis_client'):
            self.redis_client.flushdb()
    
    def test_basic_cache_operations(self):
        """Test basic cache set, get, and delete operations"""
        key = 'test_key'
        value = 'test_value'
        
        # Test SET
        result = self.redis_client.set(key, value)
        assert result is True
        
        # Test GET
        retrieved_value = self.redis_client.get(key)
        assert retrieved_value == value
        
        # Test DELETE
        delete_result = self.redis_client.delete(key)
        assert delete_result == 1
        
        # Verify deletion
        deleted_value = self.redis_client.get(key)
        assert deleted_value is None
    
    def test_cache_with_ttl(self):
        """Test cache operations with TTL (Time To Live)"""
        key = 'ttl_test_key'
        value = 'ttl_test_value'
        ttl_seconds = 2
        
        # Set with TTL
        self.redis_client.setex(key, ttl_seconds, value)
        
        # Verify value exists
        assert self.redis_client.get(key) == value
        
        # Check TTL
        ttl = self.redis_client.ttl(key)
        assert 0 < ttl <= ttl_seconds
        
        # Wait for expiration (in real tests, we'd mock time)
        time.sleep(ttl_seconds + 0.1)
        
        # Verify expiration
        expired_value = self.redis_client.get(key)
        assert expired_value is None
    
    def test_json_cache_operations(self):
        """Test caching JSON data"""
        key = 'json_test_key'
        data = {
            'product_id': 'prod_123',
            'title': 'Test Product',
            'price': 99.99,
            'tags': ['electronics', 'gadget'],
            'metadata': {
                'created_at': '2024-01-01T00:00:00Z',
                'updated_at': '2024-01-02T00:00:00Z'
            }
        }
        
        # Cache JSON data
        json_value = json.dumps(data)
        self.redis_client.set(key, json_value)
        
        # Retrieve and parse JSON
        retrieved_json = self.redis_client.get(key)
        retrieved_data = json.loads(retrieved_json)
        
        assert retrieved_data == data
        assert retrieved_data['product_id'] == 'prod_123'
        assert retrieved_data['price'] == 99.99
        assert len(retrieved_data['tags']) == 2
    
    def test_product_cache_operations(self):
        """Test product-specific caching patterns"""
        product_id = 'prod_123'
        
        # Cache product details
        product_data = {
            'product_id': product_id,
            'title': 'Wireless Headphones',
            'price': 199.99,
            'rating': 4.5,
            'review_count': 150,
            'in_stock': True
        }
        
        product_key = f'product:{product_id}'
        self.redis_client.setex(product_key, 3600, json.dumps(product_data))  # 1 hour TTL
        
        # Cache product reviews summary
        reviews_summary = {
            'total_reviews': 150,
            'average_rating': 4.5,
            'rating_distribution': {1: 2, 2: 5, 3: 15, 4: 50, 5: 78}
        }
        
        reviews_key = f'product_reviews:{product_id}'
        self.redis_client.setex(reviews_key, 1800, json.dumps(reviews_summary))  # 30 minutes TTL
        
        # Verify cached data
        cached_product = json.loads(self.redis_client.get(product_key))
        cached_reviews = json.loads(self.redis_client.get(reviews_key))
        
        assert cached_product['title'] == 'Wireless Headphones'
        assert cached_reviews['total_reviews'] == 150
        assert cached_reviews['rating_distribution']['5'] == 78
    
    def test_search_cache_operations(self):
        """Test search result caching patterns"""
        query = 'wireless headphones'
        filters = {'category': 'Electronics', 'min_price': 50}
        
        # Create cache key for search
        search_key = f'search:{hash(query + str(sorted(filters.items())))}'
        
        # Cache search results
        search_results = {
            'query': query,
            'filters': filters,
            'total_results': 25,
            'products': [
                {'product_id': 'prod_1', 'title': 'Headphones A', 'price': 99.99},
                {'product_id': 'prod_2', 'title': 'Headphones B', 'price': 149.99}
            ],
            'cached_at': datetime.utcnow().isoformat()
        }
        
        self.redis_client.setex(search_key, 600, json.dumps(search_results))  # 10 minutes TTL
        
        # Verify cached search results
        cached_results = json.loads(self.redis_client.get(search_key))
        assert cached_results['query'] == query
        assert cached_results['total_results'] == 25
        assert len(cached_results['products']) == 2
    
    def test_auto_complete_cache_operations(self):
        """Test auto-complete suggestions caching"""
        # Cache popular search terms
        popular_terms = [
            {'term': 'wireless headphones', 'count': 1500},
            {'term': 'wireless mouse', 'count': 1200},
            {'term': 'wireless keyboard', 'count': 800},
            {'term': 'wireless speaker', 'count': 600}
        ]
        
        popular_key = 'popular_terms:all'
        self.redis_client.setex(popular_key, 3600, json.dumps(popular_terms))
        
        # Cache auto-complete suggestions for specific query
        query = 'wireless'
        suggestions = [
            {'text': 'wireless headphones', 'type': 'popular', 'count': 1500},
            {'text': 'wireless mouse', 'type': 'popular', 'count': 1200},
            {'text': 'Wireless Bluetooth Headphones', 'type': 'product', 'rating': 4.5}
        ]
        
        autocomplete_key = f'autocomplete:{query.lower()}'
        self.redis_client.setex(autocomplete_key, 300, json.dumps(suggestions))  # 5 minutes TTL
        
        # Verify cached suggestions
        cached_popular = json.loads(self.redis_client.get(popular_key))
        cached_suggestions = json.loads(self.redis_client.get(autocomplete_key))
        
        assert len(cached_popular) == 4
        assert cached_popular[0]['term'] == 'wireless headphones'
        assert len(cached_suggestions) == 3
        assert cached_suggestions[0]['type'] == 'popular'
    
    def test_cart_session_cache_operations(self):
        """Test shopping cart session caching"""
        user_id = 'user_123'
        session_id = 'session_456'
        
        # Cache cart data
        cart_data = {
            'user_id': user_id,
            'session_id': session_id,
            'items': [
                {
                    'product_id': 'prod_1',
                    'quantity': 2,
                    'price': 99.99,
                    'subtotal': 199.98
                },
                {
                    'product_id': 'prod_2',
                    'quantity': 1,
                    'price': 49.99,
                    'subtotal': 49.99
                }
            ],
            'total_amount': 249.97,
            'last_updated': datetime.utcnow().isoformat()
        }
        
        cart_key = f'cart:{user_id}'
        self.redis_client.setex(cart_key, 1800, json.dumps(cart_data))  # 30 minutes TTL
        
        # Cache session info
        session_data = {
            'session_id': session_id,
            'user_id': user_id,
            'created_at': datetime.utcnow().isoformat(),
            'last_activity': datetime.utcnow().isoformat()
        }
        
        session_key = f'session:{session_id}'
        self.redis_client.setex(session_key, 3600, json.dumps(session_data))  # 1 hour TTL
        
        # Verify cached data
        cached_cart = json.loads(self.redis_client.get(cart_key))
        cached_session = json.loads(self.redis_client.get(session_key))
        
        assert cached_cart['total_amount'] == 249.97
        assert len(cached_cart['items']) == 2
        assert cached_session['user_id'] == user_id
    
    def test_chat_memory_cache_operations(self):
        """Test chat memory caching patterns"""
        user_id = 'user_123'
        
        # Cache recent chat messages
        recent_messages = [
            {
                'message_id': 'msg_1',
                'role': 'user',
                'content': 'What are the best wireless headphones?',
                'timestamp': datetime.utcnow().isoformat()
            },
            {
                'message_id': 'msg_2',
                'role': 'assistant',
                'content': 'Based on customer reviews, I recommend...',
                'timestamp': datetime.utcnow().isoformat()
            }
        ]
        
        chat_key = f'chat_recent:{user_id}'
        self.redis_client.setex(chat_key, 600, json.dumps(recent_messages))  # 10 minutes TTL
        
        # Cache AI response for common queries
        common_query = 'return policy'
        ai_response = {
            'query': common_query,
            'response': 'You can return items within 30 days of purchase...',
            'sources': ['Knowledge Base: Return Policy'],
            'cached_at': datetime.utcnow().isoformat()
        }
        
        ai_cache_key = f'ai_response:{hash(common_query)}'
        self.redis_client.setex(ai_cache_key, 3600, json.dumps(ai_response))  # 1 hour TTL
        
        # Verify cached data
        cached_messages = json.loads(self.redis_client.get(chat_key))
        cached_ai_response = json.loads(self.redis_client.get(ai_cache_key))
        
        assert len(cached_messages) == 2
        assert cached_messages[0]['role'] == 'user'
        assert cached_ai_response['query'] == common_query
    
    def test_cache_invalidation_patterns(self):
        """Test cache invalidation strategies"""
        product_id = 'prod_123'
        
        # Set up related cache entries
        product_key = f'product:{product_id}'
        reviews_key = f'product_reviews:{product_id}'
        search_key = f'search:electronics_headphones'
        
        # Cache data
        self.redis_client.setex(product_key, 3600, json.dumps({'title': 'Headphones'}))
        self.redis_client.setex(reviews_key, 1800, json.dumps({'total_reviews': 100}))
        self.redis_client.setex(search_key, 600, json.dumps({'results': ['prod_123']}))
        
        # Verify data exists
        assert self.redis_client.get(product_key) is not None
        assert self.redis_client.get(reviews_key) is not None
        assert self.redis_client.get(search_key) is not None
        
        # Simulate product update - invalidate related caches
        keys_to_invalidate = [
            f'product:{product_id}',
            f'product_reviews:{product_id}',
            f'search:*'  # Pattern for search results
        ]
        
        # Delete specific keys
        for key in keys_to_invalidate[:-1]:  # Exclude pattern
            self.redis_client.delete(key)
        
        # For pattern deletion, we'd use SCAN in production
        # Here we'll simulate by deleting the search key
        self.redis_client.delete(search_key)
        
        # Verify invalidation
        assert self.redis_client.get(product_key) is None
        assert self.redis_client.get(reviews_key) is None
        assert self.redis_client.get(search_key) is None
    
    def test_cache_consistency_operations(self):
        """Test cache consistency patterns"""
        product_id = 'prod_123'
        
        # Simulate cache-aside pattern
        def get_product_with_cache(product_id):
            cache_key = f'product:{product_id}'
            
            # Try cache first
            cached_data = self.redis_client.get(cache_key)
            if cached_data:
                return json.loads(cached_data)
            
            # Simulate database fetch
            db_data = {
                'product_id': product_id,
                'title': 'Database Product',
                'price': 99.99,
                'version': 1
            }
            
            # Cache the result
            self.redis_client.setex(cache_key, 3600, json.dumps(db_data))
            return db_data
        
        # First call - should fetch from "database" and cache
        product1 = get_product_with_cache(product_id)
        assert product1['title'] == 'Database Product'
        
        # Second call - should return from cache
        product2 = get_product_with_cache(product_id)
        assert product2['title'] == 'Database Product'
        
        # Verify cache hit
        cached_product = json.loads(self.redis_client.get(f'product:{product_id}'))
        assert cached_product['title'] == 'Database Product'
    
    def test_cache_performance_patterns(self):
        """Test cache performance optimization patterns"""
        # Test batch operations
        products = {}
        for i in range(10):
            product_id = f'prod_{i}'
            product_data = {
                'product_id': product_id,
                'title': f'Product {i}',
                'price': 10.0 + i
            }
            products[f'product:{product_id}'] = json.dumps(product_data)
        
        # Batch set using pipeline
        pipe = self.redis_client.pipeline()
        for key, value in products.items():
            pipe.setex(key, 3600, value)
        pipe.execute()
        
        # Batch get using pipeline
        pipe = self.redis_client.pipeline()
        for key in products.keys():
            pipe.get(key)
        results = pipe.execute()
        
        # Verify batch operations
        assert len(results) == 10
        for result in results:
            assert result is not None
            product_data = json.loads(result)
            assert 'product_id' in product_data
    
    def test_cache_memory_management(self):
        """Test cache memory management and eviction"""
        # Fill cache with data
        for i in range(100):
            key = f'test_key_{i}'
            value = f'test_value_{i}' * 100  # Make values larger
            self.redis_client.setex(key, 3600, value)
        
        # Check memory usage (in real Redis)
        info = self.redis_client.info('memory')
        
        # Verify data was stored
        sample_key = 'test_key_50'
        assert self.redis_client.get(sample_key) is not None
        
        # Test key expiration
        short_ttl_key = 'short_ttl_key'
        self.redis_client.setex(short_ttl_key, 1, 'short_value')
        
        # Verify key exists
        assert self.redis_client.get(short_ttl_key) == 'short_value'
        
        # Wait for expiration
        time.sleep(1.1)
        
        # Verify expiration
        assert self.redis_client.get(short_ttl_key) is None
    
    def test_cache_key_patterns(self):
        """Test cache key naming patterns and organization"""
        # Test hierarchical key patterns
        keys_data = {
            'product:123': {'type': 'product', 'id': '123'},
            'product:123:reviews': {'type': 'reviews', 'product_id': '123'},
            'product:123:inventory': {'type': 'inventory', 'product_id': '123'},
            'user:456': {'type': 'user', 'id': '456'},
            'user:456:cart': {'type': 'cart', 'user_id': '456'},
            'user:456:preferences': {'type': 'preferences', 'user_id': '456'},
            'search:electronics:page:1': {'type': 'search', 'category': 'electronics'},
            'autocomplete:wireless': {'type': 'autocomplete', 'query': 'wireless'}
        }
        
        # Store data with different key patterns
        for key, data in keys_data.items():
            self.redis_client.setex(key, 3600, json.dumps(data))
        
        # Test pattern-based retrieval
        product_keys = []
        for key in self.redis_client.scan_iter(match='product:*'):
            product_keys.append(key)
        
        user_keys = []
        for key in self.redis_client.scan_iter(match='user:*'):
            user_keys.append(key)
        
        # Verify pattern matching
        assert len(product_keys) == 3  # product:123, product:123:reviews, product:123:inventory
        assert len(user_keys) == 3     # user:456, user:456:cart, user:456:preferences
        
        # Test specific key retrieval
        product_data = json.loads(self.redis_client.get('product:123'))
        assert product_data['type'] == 'product'
        assert product_data['id'] == '123'
    
    def test_cache_monitoring_operations(self):
        """Test cache monitoring and statistics"""
        # Store various types of data
        test_data = {
            'string_key': 'simple_string',
            'json_key': json.dumps({'complex': 'object', 'with': ['nested', 'data']}),
            'large_key': 'x' * 1000  # Large string
        }
        
        for key, value in test_data.items():
            self.redis_client.setex(key, 3600, value)
        
        # Get Redis info
        info = self.redis_client.info()
        
        # Check basic stats
        assert 'redis_version' in info or 'server' in str(info)  # Different for fakeredis
        
        # Test key existence
        assert self.redis_client.exists('string_key') == 1
        assert self.redis_client.exists('nonexistent_key') == 0
        
        # Test key TTL
        ttl = self.redis_client.ttl('string_key')
        assert ttl > 0  # Should have TTL set
        
        # Test key type
        key_type = self.redis_client.type('string_key')
        assert key_type == 'string'


if __name__ == '__main__':
    pytest.main([__file__])