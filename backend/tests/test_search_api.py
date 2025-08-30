"""
Unit tests for Search API Lambda function
"""
import unittest
from unittest.mock import Mock, patch, MagicMock
import json
import sys
import os

# Add the parent directory to the path to import modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from functions.search_api import SearchAPI, lambda_handler

class TestSearchAPI(unittest.TestCase):
    """Test cases for SearchAPI class"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.mock_products_collection = Mock()
        self.mock_search_analytics_table = Mock()
        
        with patch('functions.search_api.get_documentdb_collection') as mock_get_collection, \
             patch('functions.search_api.get_dynamodb_table') as mock_get_table:
            
            mock_get_collection.return_value = self.mock_products_collection
            mock_get_table.return_value = self.mock_search_analytics_table
            
            self.search_api = SearchAPI()
    
    @patch('functions.search_api.cache_get')
    @patch('functions.search_api.cache_set')
    def test_get_auto_complete_suggestions_cached(self, mock_cache_set, mock_cache_get):
        """Test auto-complete suggestions from cache"""
        # Mock cached suggestions
        cached_suggestions = [
            {'text': 'wireless headphones', 'type': 'popular', 'popularity': 100},
            {'text': 'wireless mouse', 'type': 'popular', 'popularity': 80}
        ]
        mock_cache_get.return_value = json.dumps(cached_suggestions)
        
        result = self.search_api.get_auto_complete_suggestions('wireless', 5)
        
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]['text'], 'wireless headphones')
        self.assertEqual(result[0]['type'], 'popular')
        mock_cache_get.assert_called_once()
        mock_cache_set.assert_not_called()
    
    @patch('functions.search_api.cache_get')
    @patch('functions.search_api.cache_set')
    def test_get_auto_complete_suggestions_not_cached(self, mock_cache_set, mock_cache_get):
        """Test auto-complete suggestions when not cached"""
        mock_cache_get.return_value = None
        
        # Mock popular terms
        with patch.object(self.search_api, '_get_popular_search_terms') as mock_popular, \
             patch.object(self.search_api, '_get_product_suggestions') as mock_products, \
             patch.object(self.search_api, '_get_category_suggestions') as mock_categories:
            
            mock_popular.return_value = [
                {'text': 'wireless headphones', 'type': 'popular', 'popularity': 100}
            ]
            mock_products.return_value = [
                {'text': 'Wireless Bluetooth Speaker', 'type': 'product', 'popularity': 50}
            ]
            mock_categories.return_value = [
                {'text': 'Electronics', 'type': 'category', 'popularity': 30}
            ]
            
            result = self.search_api.get_auto_complete_suggestions('wireless', 5)
            
            self.assertEqual(len(result), 3)
            self.assertTrue(any(s['text'] == 'wireless headphones' for s in result))
            mock_cache_set.assert_called_once()
    
    def test_get_auto_complete_suggestions_empty_query(self):
        """Test auto-complete with empty query"""
        result = self.search_api.get_auto_complete_suggestions('', 5)
        self.assertEqual(result, [])
        
        result = self.search_api.get_auto_complete_suggestions('a', 5)  # Too short
        self.assertEqual(result, [])
    
    @patch('functions.search_api.cache_get')
    def test_get_popular_search_terms(self, mock_cache_get):
        """Test getting popular search terms"""
        popular_terms = [
            {'term': 'wireless headphones', 'count': 100},
            {'term': 'wireless mouse', 'count': 80},
            {'term': 'bluetooth speaker', 'count': 60}
        ]
        mock_cache_get.return_value = json.dumps(popular_terms)
        
        result = self.search_api._get_popular_search_terms('wireless', 5)
        
        self.assertEqual(len(result), 2)  # Only wireless terms
        self.assertEqual(result[0]['text'], 'wireless headphones')
        self.assertEqual(result[0]['popularity'], 100)
    
    def test_get_product_suggestions(self):
        """Test getting product suggestions"""
        mock_products = [
            {'title': 'Wireless Bluetooth Headphones', 'category': 'Electronics', 'rating': 4.5, 'reviewCount': 100},
            {'title': 'Wireless Gaming Mouse', 'category': 'Electronics', 'rating': 4.3, 'reviewCount': 80}
        ]
        
        self.mock_products_collection.aggregate.return_value = mock_products
        
        result = self.search_api._get_product_suggestions('wireless', 5)
        
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]['text'], 'Wireless Bluetooth Headphones')
        self.assertEqual(result[0]['type'], 'product')
        self.assertEqual(result[0]['popularity'], 100)
    
    def test_get_category_suggestions(self):
        """Test getting category suggestions"""
        mock_categories = [
            {'_id': 'Electronics', 'count': 50, 'avgRating': 4.2},
            {'_id': 'Home Electronics', 'count': 30, 'avgRating': 4.0}
        ]
        
        self.mock_products_collection.aggregate.return_value = mock_categories
        
        result = self.search_api._get_category_suggestions('electronics', 5)
        
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]['text'], 'Electronics')
        self.assertEqual(result[0]['type'], 'category')
        self.assertEqual(result[0]['popularity'], 50)
    
    @patch('functions.search_api.cache_set')
    def test_search_products_basic(self, mock_cache_set):
        """Test basic product search"""
        mock_products = [
            {
                '_id': '1',
                'title': 'Wireless Headphones',
                'description': 'High-quality wireless headphones',
                'price': 199.99,
                'rating': 4.5,
                'reviewCount': 100,
                'category': 'Electronics'
            }
        ]
        
        mock_count_result = [{'total': 1}]
        
        # Mock the aggregation calls
        self.mock_products_collection.aggregate.side_effect = [mock_products, mock_count_result]
        
        with patch.object(self.search_api, '_track_search_analytics') as mock_track:
            result = self.search_api.search_products('wireless headphones', page=1, page_size=20)
            
            self.assertEqual(result['total'], 1)
            self.assertEqual(len(result['products']), 1)
            self.assertEqual(result['products'][0]['title'], 'Wireless Headphones')
            self.assertEqual(result['page'], 1)
            self.assertEqual(result['totalPages'], 1)
            mock_track.assert_called_once()
    
    def test_search_products_with_filters(self):
        """Test product search with filters"""
        filters = {
            'category': ['Electronics'],
            'minPrice': '100',
            'maxPrice': '300',
            'minRating': '4.0',
            'inStock': True
        }
        
        mock_products = []
        mock_count_result = [{'total': 0}]
        
        self.mock_products_collection.aggregate.side_effect = [mock_products, mock_count_result]
        
        with patch.object(self.search_api, '_track_search_analytics'), \
             patch.object(self.search_api, '_get_alternative_suggestions') as mock_alternatives:
            
            mock_alternatives.return_value = ['headphones', 'speakers']
            
            result = self.search_api.search_products('wireless', filters=filters)
            
            self.assertEqual(result['total'], 0)
            self.assertEqual(len(result['alternatives']), 2)
    
    def test_build_filter_conditions(self):
        """Test building filter conditions"""
        filters = {
            'category': ['Electronics', 'Audio'],
            'minPrice': '50',
            'maxPrice': '200',
            'minRating': '4.0',
            'inStock': True,
            'tags': ['wireless', 'bluetooth']
        }
        
        conditions = self.search_api._build_filter_conditions(filters)
        
        self.assertIn('category', conditions)
        self.assertEqual(conditions['category']['$in'], ['Electronics', 'Audio'])
        self.assertIn('price', conditions)
        self.assertEqual(conditions['price']['$gte'], 50.0)
        self.assertEqual(conditions['price']['$lte'], 200.0)
        self.assertEqual(conditions['rating']['$gte'], 4.0)
        self.assertTrue(conditions['inStock'])
        self.assertEqual(conditions['tags']['$in'], ['wireless', 'bluetooth'])
    
    def test_build_sort_stage(self):
        """Test building sort stage"""
        # Test relevance sort (default)
        sort_stage = self.search_api._build_sort_stage('relevance')
        self.assertIn('relevanceScore', sort_stage)
        self.assertEqual(sort_stage['relevanceScore'], -1)
        
        # Test price sort
        sort_stage = self.search_api._build_sort_stage('price_low')
        self.assertIn('price', sort_stage)
        self.assertEqual(sort_stage['price'], 1)
        
        sort_stage = self.search_api._build_sort_stage('price_high')
        self.assertEqual(sort_stage['price'], -1)
        
        # Test rating sort
        sort_stage = self.search_api._build_sort_stage('rating')
        self.assertIn('rating', sort_stage)
        self.assertEqual(sort_stage['rating'], -1)
    
    def test_highlight_search_terms(self):
        """Test highlighting search terms in results"""
        products = [
            {
                'title': 'Wireless Bluetooth Headphones',
                'description': 'High-quality wireless audio device with bluetooth connectivity'
            }
        ]
        
        result = self.search_api._highlight_search_terms(products, 'wireless bluetooth')
        
        self.assertIn('<mark>Wireless</mark>', result[0]['highlightedTitle'])
        self.assertIn('<mark>Bluetooth</mark>', result[0]['highlightedTitle'])
        self.assertIn('<mark>wireless</mark>', result[0]['highlightedDescription'])
        self.assertIn('<mark>bluetooth</mark>', result[0]['highlightedDescription'])
    
    def test_get_alternative_suggestions(self):
        """Test getting alternative suggestions"""
        # Mock categories
        self.mock_products_collection.distinct.return_value = [
            'Electronics', 'Audio Equipment', 'Gaming'
        ]
        
        with patch('functions.search_api.cache_get') as mock_cache_get:
            popular_terms = [
                {'term': 'headphones', 'count': 100},
                {'term': 'speakers', 'count': 80}
            ]
            mock_cache_get.return_value = json.dumps(popular_terms)
            
            result = self.search_api._get_alternative_suggestions('audio')
            
            self.assertIn('Audio Equipment', result)
            self.assertTrue(len(result) <= 5)
    
    @patch('functions.search_api.cache_set')
    @patch('functions.search_api.cache_get')
    def test_track_search_analytics(self, mock_cache_get, mock_cache_set):
        """Test tracking search analytics"""
        mock_cache_get.return_value = '5'  # Current count
        
        with patch.object(self.search_api, '_update_popular_terms') as mock_update_popular:
            self.search_api._track_search_analytics('wireless headphones', {'category': ['Electronics']})
            
            # Verify DynamoDB put_item was called
            self.mock_search_analytics_table.put_item.assert_called_once()
            
            # Verify cache operations
            mock_cache_set.assert_called()
            mock_update_popular.assert_called_once()
    
    @patch('functions.search_api.cache_get')
    @patch('functions.search_api.cache_set')
    def test_update_popular_terms(self, mock_cache_set, mock_cache_get):
        """Test updating popular terms"""
        existing_terms = [
            {'term': 'headphones', 'count': 50},
            {'term': 'speakers', 'count': 30}
        ]
        mock_cache_get.return_value = json.dumps(existing_terms)
        
        self.search_api._update_popular_terms('wireless', 25)
        
        # Verify cache_set was called with updated terms
        mock_cache_set.assert_called()
        call_args = mock_cache_set.call_args[0]
        updated_terms = json.loads(call_args[1])
        
        # Should have 3 terms now, sorted by count
        self.assertEqual(len(updated_terms), 3)
        self.assertEqual(updated_terms[0]['term'], 'headphones')  # Highest count
        self.assertEqual(updated_terms[0]['count'], 50)

class TestSearchAPILambdaHandler(unittest.TestCase):
    """Test cases for lambda_handler function"""
    
    @patch('functions.search_api.SearchAPI')
    def test_lambda_handler_suggestions(self, mock_search_api_class):
        """Test lambda handler for auto-complete suggestions"""
        mock_search_api = Mock()
        mock_search_api_class.return_value = mock_search_api
        mock_search_api.get_auto_complete_suggestions.return_value = [
            {'text': 'wireless headphones', 'type': 'popular', 'popularity': 100}
        ]
        
        event = {
            'httpMethod': 'GET',
            'path': '/api/search/suggestions',
            'queryStringParameters': {'q': 'wireless', 'limit': '5'}
        }
        
        result = lambda_handler(event, None)
        
        self.assertEqual(result['statusCode'], 200)
        body = json.loads(result['body'])
        self.assertIn('suggestions', body)
        self.assertEqual(len(body['suggestions']), 1)
        self.assertEqual(body['query'], 'wireless')
    
    @patch('functions.search_api.SearchAPI')
    def test_lambda_handler_search_get(self, mock_search_api_class):
        """Test lambda handler for product search (GET)"""
        mock_search_api = Mock()
        mock_search_api_class.return_value = mock_search_api
        mock_search_api.search_products.return_value = {
            'products': [{'title': 'Test Product'}],
            'total': 1,
            'page': 1,
            'totalPages': 1
        }
        
        event = {
            'httpMethod': 'GET',
            'path': '/api/search/products',
            'queryStringParameters': {
                'q': 'wireless',
                'category': 'Electronics,Audio',
                'minPrice': '50',
                'maxPrice': '200',
                'sort': 'price_low',
                'page': '1',
                'pageSize': '10'
            }
        }
        
        result = lambda_handler(event, None)
        
        self.assertEqual(result['statusCode'], 200)
        body = json.loads(result['body'])
        self.assertIn('products', body)
        self.assertEqual(body['total'], 1)
        
        # Verify search_products was called with correct parameters
        mock_search_api.search_products.assert_called_once()
        call_args = mock_search_api.search_products.call_args
        self.assertEqual(call_args[0][0], 'wireless')  # query
        self.assertIn('category', call_args[0][1])  # filters
        self.assertEqual(call_args[0][2], 'price_low')  # sort_by
        self.assertEqual(call_args[0][3], 1)  # page
        self.assertEqual(call_args[0][4], 10)  # page_size
    
    @patch('functions.search_api.SearchAPI')
    def test_lambda_handler_search_post(self, mock_search_api_class):
        """Test lambda handler for product search (POST)"""
        mock_search_api = Mock()
        mock_search_api_class.return_value = mock_search_api
        mock_search_api.search_products.return_value = {
            'products': [],
            'total': 0,
            'page': 1,
            'totalPages': 0
        }
        
        event = {
            'httpMethod': 'POST',
            'path': '/api/search/products',
            'body': json.dumps({
                'query': 'wireless headphones',
                'filters': {'category': ['Electronics']},
                'sortBy': 'rating',
                'page': 2,
                'pageSize': 15
            })
        }
        
        result = lambda_handler(event, None)
        
        self.assertEqual(result['statusCode'], 200)
        body = json.loads(result['body'])
        self.assertEqual(body['total'], 0)
        
        # Verify search_products was called with POST body parameters
        mock_search_api.search_products.assert_called_once()
        call_args = mock_search_api.search_products.call_args
        self.assertEqual(call_args[0][0], 'wireless headphones')
        self.assertEqual(call_args[0][1], {'category': ['Electronics']})
        self.assertEqual(call_args[0][2], 'rating')
        self.assertEqual(call_args[0][3], 2)
        self.assertEqual(call_args[0][4], 15)
    
    def test_lambda_handler_invalid_path(self):
        """Test lambda handler with invalid path"""
        event = {
            'httpMethod': 'GET',
            'path': '/api/search/invalid',
            'queryStringParameters': {}
        }
        
        result = lambda_handler(event, None)
        
        self.assertEqual(result['statusCode'], 404)
        body = json.loads(result['body'])
        self.assertIn('error', body)
    
    @patch('functions.search_api.SearchAPI')
    def test_lambda_handler_error(self, mock_search_api_class):
        """Test lambda handler error handling"""
        mock_search_api_class.side_effect = Exception('Database connection failed')
        
        event = {
            'httpMethod': 'GET',
            'path': '/api/search/suggestions',
            'queryStringParameters': {'q': 'test'}
        }
        
        result = lambda_handler(event, None)
        
        self.assertEqual(result['statusCode'], 500)
        body = json.loads(result['body'])
        self.assertIn('error', body)
        self.assertIn('Internal server error', body['error'])
    
    def test_lambda_handler_cors_headers(self):
        """Test that CORS headers are included in responses"""
        event = {
            'httpMethod': 'GET',
            'path': '/api/search/invalid',
            'queryStringParameters': {}
        }
        
        result = lambda_handler(event, None)
        
        headers = result['headers']
        self.assertIn('Access-Control-Allow-Origin', headers)
        self.assertEqual(headers['Access-Control-Allow-Origin'], '*')

if __name__ == '__main__':
    unittest.main()