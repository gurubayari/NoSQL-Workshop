"""
Unit tests for Search API Lambda function
Tests auto-complete suggestions, semantic search, and search analytics
"""
import pytest
import json
import unittest.mock as mock
from unittest.mock import MagicMock, patch, Mock
from datetime import datetime, timedelta
import sys
import os

# Add the functions directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'functions'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'shared'))

# Mock the shared modules before importing
with patch.dict('sys.modules', {
    'shared.database': MagicMock(),
    'shared.config': MagicMock(),
    'database': MagicMock(),
    'config': MagicMock()
}):
    from search_api import SearchAPI, lambda_handler

class TestSearchAPI:
    """Test cases for SearchAPI class"""
    
    def setup_method(self):
        """Set up test fixtures"""
        self.mock_products_collection = MagicMock()
        self.mock_search_analytics_table = MagicMock()
        self.mock_bedrock_client = MagicMock()
        
        with patch('search_api.get_documentdb_collection') as mock_get_collection, \
             patch('search_api.get_dynamodb_table') as mock_get_table, \
             patch('search_api.boto3.client') as mock_boto3_client:
            
            mock_get_collection.return_value = self.mock_products_collection
            mock_get_table.return_value = self.mock_search_analytics_table
            mock_boto3_client.return_value = self.mock_bedrock_client
            
            self.api = SearchAPI()
    
    def test_get_auto_complete_suggestions_success(self):
        """Test successful auto-complete suggestions"""
        query = "wireless"
        
        # Mock popular terms from cache
        popular_terms = [
            {'term': 'wireless headphones', 'count': 100},
            {'term': 'wireless mouse', 'count': 80}
        ]
        
        # Mock product suggestions
        mock_products = [
            {
                'title': 'Wireless Bluetooth Headphones',
                'category': 'Electronics',
                'rating': 4.5,
                'reviewCount': 200
            },
            {
                'title': 'Wireless Gaming Mouse',
                'category': 'Electronics',
                'rating': 4.2,
                'reviewCount': 150
            }
        ]
        
        with patch.object(self.api, '_get_popular_search_terms') as mock_popular, \
             patch.object(self.api, '_get_product_suggestions') as mock_products_suggestions, \
             patch.object(self.api, '_get_category_suggestions') as mock_category, \
             patch('search_api.cache_get', return_value=None), \
             patch('search_api.cache_set'):
            
            mock_popular.return_value = [
                {'text': 'wireless headphones', 'type': 'popular', 'popularity': 100, 'count': 100},
                {'text': 'wireless mouse', 'type': 'popular', 'popularity': 80, 'count': 80}
            ]
            
            mock_products_suggestions.return_value = [
                {'text': 'Wireless Bluetooth Headphones', 'type': 'product', 'popularity': 200, 'rating': 4.5},
                {'text': 'Wireless Gaming Mouse', 'type': 'product', 'popularity': 150, 'rating': 4.2}
            ]
            
            mock_category.return_value = [
                {'text': 'Electronics', 'type': 'category', 'popularity': 500, 'count': 500}
            ]
            
            result = self.api.get_auto_complete_suggestions(query, limit=10)
            
            assert len(result) > 0
            assert any(suggestion['text'] == 'wireless headphones' for suggestion in result)
            assert any(suggestion['type'] == 'popular' for suggestion in result)
            assert any(suggestion['type'] == 'product' for suggestion in result)
    
    def test_get_auto_complete_suggestions_cached(self):
        """Test returning cached auto-complete suggestions"""
        query = "wireless"
        cached_suggestions = [
            {'text': 'wireless headphones', 'type': 'popular', 'popularity': 100}
        ]
        
        with patch('search_api.cache_get', return_value=json.dumps(cached_suggestions)):
            result = self.api.get_auto_complete_suggestions(query)
            
            assert result == cached_suggestions
    
    def test_get_auto_complete_suggestions_empty_query(self):
        """Test auto-complete with empty or short query"""
        result = self.api.get_auto_complete_suggestions("")
        assert result == []
        
        result = self.api.get_auto_complete_suggestions("a")
        assert result == []
    
    def test_get_popular_search_terms(self):
        """Test getting popular search terms from cache"""
        query = "wireless"
        popular_terms = [
            {'term': 'wireless headphones', 'count': 100},
            {'term': 'wireless mouse', 'count': 80},
            {'term': 'wired keyboard', 'count': 60}  # Should not match
        ]
        
        with patch('search_api.cache_get', return_value=json.dumps(popular_terms)):
            result = self.api._get_popular_search_terms(query, limit=5)
            
            # Should only return terms that start with query
            assert len(result) == 2
            assert all(term['text'].startswith(query) for term in result)
            assert result[0]['popularity'] == 100  # Should be sorted by popularity
    
    def test_get_product_suggestions(self):
        """Test getting product suggestions from DocumentDB"""
        query = "wireless"
        mock_products = [
            {
                'title': 'Wireless Headphones Premium',
                'category': 'Electronics',
                'rating': 4.5,
                'reviewCount': 200
            },
            {
                'title': 'Wireless Mouse Pro',
                'category': 'Electronics',
                'rating': 4.2,
                'reviewCount': 150
            }
        ]
        
        self.mock_products_collection.aggregate.return_value = mock_products
        
        result = self.api._get_product_suggestions(query, limit=5)
        
        assert len(result) == 2
        assert result[0]['text'] == 'Wireless Headphones Premium'
        assert result[0]['type'] == 'product'
        assert result[0]['popularity'] == 200  # reviewCount
    
    def test_get_category_suggestions(self):
        """Test getting category suggestions from DocumentDB"""
        query = "elect"
        mock_categories = [
            {'_id': 'Electronics', 'count': 500, 'avgRating': 4.3},
            {'_id': 'Electrical', 'count': 100, 'avgRating': 4.1}
        ]
        
        self.mock_products_collection.aggregate.return_value = mock_categories
        
        result = self.api._get_category_suggestions(query, limit=5)
        
        assert len(result) == 2
        assert result[0]['text'] == 'Electronics'
        assert result[0]['type'] == 'category'
        assert result[0]['popularity'] == 500
    
    def test_search_products_success(self):
        """Test successful product search"""
        query = "wireless headphones"
        filters = {'category': ['Electronics'], 'min_price': '50', 'max_price': '200'}
        
        mock_products = [
            {
                'title': 'Wireless Bluetooth Headphones',
                'description': 'High-quality wireless headphones',
                'price': 99.99,
                'category': 'Electronics',
                'rating': 4.5,
                'reviewCount': 200,
                'created_at': datetime.utcnow()
            }
        ]
        
        mock_count_result = [{'total': 1}]
        
        with patch.object(self.api, '_build_search_pipeline') as mock_build_pipeline, \
             patch.object(self.api, '_build_count_pipeline') as mock_build_count, \
             patch.object(self.api, '_highlight_search_terms') as mock_highlight, \
             patch.object(self.api, '_get_alternative_suggestions') as mock_alternatives, \
             patch.object(self.api, '_track_search_analytics'), \
             patch('search_api.cache_get', return_value=None), \
             patch('search_api.cache_set'):
            
            self.mock_products_collection.aggregate.side_effect = [mock_products, mock_count_result]
            mock_highlight.return_value = mock_products
            mock_alternatives.return_value = []
            
            result = self.api.search_products(query, filters, sort_by='relevance', page=1, page_size=20)
            
            assert result['total'] == 1
            assert len(result['products']) == 1
            assert result['query'] == query
            assert result['page'] == 1
            assert result['totalPages'] == 1
    
    def test_search_products_no_results(self):
        """Test product search with no results"""
        query = "nonexistent product"
        
        with patch.object(self.api, '_build_search_pipeline'), \
             patch.object(self.api, '_build_count_pipeline'), \
             patch.object(self.api, '_get_alternative_suggestions') as mock_alternatives, \
             patch.object(self.api, '_track_search_analytics'), \
             patch('search_api.cache_get', return_value=None), \
             patch('search_api.cache_set'):
            
            self.mock_products_collection.aggregate.side_effect = [[], [{'total': 0}]]
            mock_alternatives.return_value = ['similar product', 'alternative item']
            
            result = self.api.search_products(query)
            
            assert result['total'] == 0
            assert len(result['products']) == 0
            assert len(result['alternatives']) == 2
    
    def test_search_products_empty_query(self):
        """Test product search with empty query"""
        result = self.api.search_products("")
        
        assert result['products'] == []
        assert result['total'] == 0
    
    def test_build_search_pipeline(self):
        """Test building MongoDB aggregation pipeline for search"""
        query = "wireless headphones"
        filters = {'category': ['Electronics'], 'min_price': '50', 'max_price': '200'}
        
        with patch.object(self.api, '_get_vector_search_conditions', return_value=[]), \
             patch.object(self.api, '_build_filter_conditions') as mock_build_filters, \
             patch.object(self.api, '_build_sort_stage') as mock_build_sort:
            
            mock_build_filters.return_value = {'category': {'$in': ['Electronics']}}
            mock_build_sort.return_value = {'relevanceScore': -1}
            
            pipeline = self.api._build_search_pipeline(query, filters, 'relevance', 1, 20)
            
            # Should have match, addFields, sort, skip, and limit stages
            assert len(pipeline) >= 4
            assert '$match' in pipeline[0]
            assert '$addFields' in pipeline[1]
            assert '$sort' in pipeline[2]
            assert '$skip' in pipeline[3]
            assert '$limit' in pipeline[4]
    
    def test_build_filter_conditions(self):
        """Test building filter conditions"""
        filters = {
            'category': ['Electronics', 'Computers'],
            'min_price': '50',
            'max_price': '200',
            'min_rating': '4.0',
            'in_stock': True,
            'tags': ['wireless', 'bluetooth']
        }
        
        conditions = self.api._build_filter_conditions(filters)
        
        assert 'category' in conditions
        assert conditions['category']['$in'] == ['Electronics', 'Computers']
        assert 'price' in conditions
        assert conditions['price']['$gte'] == 50.0
        assert conditions['price']['$lte'] == 200.0
        assert 'rating' in conditions
        assert conditions['rating']['$gte'] == 4.0
        assert 'inStock' in conditions
        assert conditions['inStock'] is True
        assert 'tags' in conditions
        assert conditions['tags']['$in'] == ['wireless', 'bluetooth']
    
    def test_build_sort_stage(self):
        """Test building sort stage for different sort options"""
        # Test relevance sort
        sort_stage = self.api._build_sort_stage('relevance')
        assert 'relevanceScore' in sort_stage
        assert sort_stage['relevanceScore'] == -1
        
        # Test price low to high
        sort_stage = self.api._build_sort_stage('price_low')
        assert 'price' in sort_stage
        assert sort_stage['price'] == 1
        
        # Test price high to low
        sort_stage = self.api._build_sort_stage('price_high')
        assert 'price' in sort_stage
        assert sort_stage['price'] == -1
        
        # Test rating sort
        sort_stage = self.api._build_sort_stage('rating')
        assert 'rating' in sort_stage
        assert sort_stage['rating'] == -1
        
        # Test invalid sort (should default to relevance)
        sort_stage = self.api._build_sort_stage('invalid_sort')
        assert 'relevanceScore' in sort_stage
    
    def test_highlight_search_terms(self):
        """Test highlighting search terms in results"""
        query = "wireless headphones"
        products = [
            {
                'title': 'Wireless Bluetooth Headphones',
                'description': 'Premium wireless headphones with great sound quality'
            },
            {
                'title': 'Gaming Mouse',
                'description': 'High-precision gaming mouse'
            }
        ]
        
        result = self.api._highlight_search_terms(products, query)
        
        # First product should have highlighted terms
        assert '<mark>Wireless</mark>' in result[0]['highlightedTitle']
        assert '<mark>Headphones</mark>' in result[0]['highlightedTitle']
        assert '<mark>wireless</mark>' in result[0]['highlightedDescription']
        assert '<mark>headphones</mark>' in result[0]['highlightedDescription']
        
        # Second product should not have highlights (no matching terms)
        assert result[1]['highlightedTitle'] == 'Gaming Mouse'
    
    def test_get_alternative_suggestions(self):
        """Test getting alternative suggestions when no results found"""
        query = "nonexistent product"
        
        # Mock categories
        self.mock_products_collection.distinct.return_value = [
            'Electronics', 'Clothing', 'Home & Garden'
        ]
        
        # Mock popular terms
        popular_terms = [
            {'term': 'wireless headphones', 'count': 100},
            {'term': 'bluetooth speaker', 'count': 80}
        ]
        
        with patch('search_api.cache_get', return_value=json.dumps(popular_terms)):
            result = self.api._get_alternative_suggestions(query)
            
            assert len(result) <= 5
            assert isinstance(result, list)
    
    def test_track_search_analytics(self):
        """Test tracking search analytics"""
        query = "wireless headphones"
        filters = {'category': ['Electronics']}
        
        with patch.object(self.api, '_update_search_frequency'):
            self.api._track_search_analytics(query, filters)
            
            # Should have called DynamoDB put_item
            self.mock_search_analytics_table.put_item.assert_called_once()
            
            # Verify the item structure
            call_args = self.mock_search_analytics_table.put_item.call_args[1]['Item']
            assert call_args['searchTerm'] == query.lower()
            assert 'timestamp' in call_args
            assert 'filters' in call_args
            assert 'date' in call_args
            assert 'hour' in call_args
    
    def test_update_search_frequency(self):
        """Test updating search term frequency in cache"""
        query = "wireless headphones"
        
        with patch('search_api.cache_get', return_value='5'), \
             patch('search_api.cache_set') as mock_cache_set, \
             patch.object(self.api, '_update_popular_terms'):
            
            self.api._update_search_frequency(query)
            
            # Should increment count and cache it
            mock_cache_set.assert_called()
            # First call should be for frequency, second for popular terms update
            assert mock_cache_set.call_count >= 1
    
    def test_update_popular_terms(self):
        """Test updating popular terms list"""
        query = "wireless headphones"
        count = 10
        
        existing_terms = [
            {'term': 'bluetooth speaker', 'count': 15},
            {'term': 'gaming mouse', 'count': 8}
        ]
        
        with patch('search_api.cache_get', return_value=json.dumps(existing_terms)), \
             patch('search_api.cache_set') as mock_cache_set:
            
            self.api._update_popular_terms(query, count)
            
            # Should update cache with new term added
            mock_cache_set.assert_called_once()
            
            # Verify the updated list
            call_args = mock_cache_set.call_args[0]
            updated_terms = json.loads(call_args[1])
            
            # Should have 3 terms now, sorted by count
            assert len(updated_terms) == 3
            assert updated_terms[0]['count'] == 15  # bluetooth speaker (highest)
            assert any(term['term'] == query for term in updated_terms)


class TestSearchAPILambdaHandler:
    """Test cases for lambda_handler function"""
    
    def test_lambda_handler_get_suggestions(self):
        """Test lambda handler for GET /search/suggestions"""
        with patch('search_api.SearchAPI') as mock_api_class:
            mock_api = MagicMock()
            mock_api_class.return_value = mock_api
            mock_api.get_auto_complete_suggestions.return_value = [
                {'text': 'wireless headphones', 'type': 'popular', 'popularity': 100}
            ]
            
            event = {
                'httpMethod': 'GET',
                'path': '/search/suggestions',
                'queryStringParameters': {'q': 'wireless', 'limit': '5'}
            }
            context = MagicMock()
            
            result = lambda_handler(event, context)
            
            assert result['statusCode'] == 200
            response_body = json.loads(result['body'])
            assert 'suggestions' in response_body
            assert response_body['query'] == 'wireless'
            mock_api.get_auto_complete_suggestions.assert_called_once_with('wireless', 5)
    
    def test_lambda_handler_get_search_products(self):
        """Test lambda handler for GET /search/products"""
        with patch('search_api.SearchAPI') as mock_api_class:
            mock_api = MagicMock()
            mock_api_class.return_value = mock_api
            mock_api.search_products.return_value = {
                'products': [],
                'total': 0,
                'query': 'test query'
            }
            
            event = {
                'httpMethod': 'GET',
                'path': '/search/products',
                'queryStringParameters': {
                    'q': 'test query',
                    'category': 'Electronics,Computers',
                    'minPrice': '50',
                    'maxPrice': '200',
                    'sort': 'price_low',
                    'page': '1',
                    'pageSize': '20'
                }
            }
            context = MagicMock()
            
            result = lambda_handler(event, context)
            
            assert result['statusCode'] == 200
            response_body = json.loads(result['body'])
            assert 'products' in response_body
            
            # Verify the search was called with correct parameters
            call_args = mock_api.search_products.call_args
            assert call_args[0][0] == 'test query'  # query
            assert 'category' in call_args[0][1]  # filters
            assert call_args[0][2] == 'price_low'  # sort_by
            assert call_args[0][3] == 1  # page
            assert call_args[0][4] == 20  # page_size
    
    def test_lambda_handler_post_search_products(self):
        """Test lambda handler for POST /search/products"""
        with patch('search_api.SearchAPI') as mock_api_class:
            mock_api = MagicMock()
            mock_api_class.return_value = mock_api
            mock_api.search_products.return_value = {
                'products': [],
                'total': 0,
                'query': 'test query'
            }
            
            event = {
                'httpMethod': 'POST',
                'path': '/search/products',
                'body': json.dumps({
                    'query': 'test query',
                    'filters': {'category': ['Electronics']},
                    'sortBy': 'relevance',
                    'page': 1,
                    'pageSize': 10
                })
            }
            context = MagicMock()
            
            result = lambda_handler(event, context)
            
            assert result['statusCode'] == 200
            mock_api.search_products.assert_called_once_with(
                'test query',
                {'category': ['Electronics']},
                'relevance',
                1,
                10
            )
    
    def test_lambda_handler_endpoint_not_found(self):
        """Test lambda handler with unknown endpoint"""
        event = {
            'httpMethod': 'GET',
            'path': '/unknown'
        }
        context = MagicMock()
        
        result = lambda_handler(event, context)
        
        assert result['statusCode'] == 404
        response_body = json.loads(result['body'])
        assert 'Endpoint not found' in response_body['error']
    
    def test_lambda_handler_exception_handling(self):
        """Test lambda handler exception handling"""
        with patch('search_api.SearchAPI') as mock_api_class:
            mock_api_class.side_effect = Exception("Initialization error")
            
            event = {
                'httpMethod': 'GET',
                'path': '/search/suggestions',
                'queryStringParameters': {'q': 'test'}
            }
            context = MagicMock()
            
            result = lambda_handler(event, context)
            
            assert result['statusCode'] == 500
            response_body = json.loads(result['body'])
            assert 'Internal server error' in response_body['error']
    
    def test_lambda_handler_missing_query_parameter(self):
        """Test lambda handler with missing query parameter"""
        with patch('search_api.SearchAPI') as mock_api_class:
            mock_api = MagicMock()
            mock_api_class.return_value = mock_api
            mock_api.get_auto_complete_suggestions.return_value = []
            
            event = {
                'httpMethod': 'GET',
                'path': '/search/suggestions',
                'queryStringParameters': {}  # Missing 'q' parameter
            }
            context = MagicMock()
            
            result = lambda_handler(event, context)
            
            assert result['statusCode'] == 200
            # Should call with empty string
            mock_api.get_auto_complete_suggestions.assert_called_once_with('', 10)


class TestSearchAPIEdgeCases:
    """Test edge cases and error conditions"""
    
    def setup_method(self):
        """Set up test fixtures"""
        self.mock_products_collection = MagicMock()
        self.mock_search_analytics_table = MagicMock()
        
        with patch('search_api.get_documentdb_collection') as mock_get_collection, \
             patch('search_api.get_dynamodb_table') as mock_get_table, \
             patch('search_api.boto3.client'):
            
            mock_get_collection.return_value = self.mock_products_collection
            mock_get_table.return_value = self.mock_search_analytics_table
            
            self.api = SearchAPI()
    
    def test_search_products_database_error(self):
        """Test search products with database error"""
        query = "test query"
        
        # Mock database error
        self.mock_products_collection.aggregate.side_effect = Exception("Database connection failed")
        
        with patch.object(self.api, '_track_search_analytics'):
            result = self.api.search_products(query)
            
            assert result['total'] == 0
            assert 'error' in result
    
    def test_get_auto_complete_suggestions_database_error(self):
        """Test auto-complete with database errors"""
        query = "wireless"
        
        with patch.object(self.api, '_get_popular_search_terms', side_effect=Exception("Cache error")), \
             patch.object(self.api, '_get_product_suggestions', side_effect=Exception("DB error")), \
             patch.object(self.api, '_get_category_suggestions', side_effect=Exception("DB error")), \
             patch('search_api.cache_get', return_value=None), \
             patch('search_api.cache_set'):
            
            result = self.api.get_auto_complete_suggestions(query)
            
            # Should return empty list on errors
            assert result == []
    
    def test_track_search_analytics_error(self):
        """Test search analytics tracking with database error"""
        query = "test query"
        
        # Mock DynamoDB error
        self.mock_search_analytics_table.put_item.side_effect = Exception("DynamoDB error")
        
        # Should not raise exception
        self.api._track_search_analytics(query, {})
    
    def test_highlight_search_terms_error(self):
        """Test search term highlighting with malformed data"""
        query = "test"
        products = [
            {'title': None, 'description': None},  # None values
            {'title': 123, 'description': 456}     # Non-string values
        ]
        
        result = self.api._highlight_search_terms(products, query)
        
        # Should handle errors gracefully and return original products
        assert len(result) == 2
    
    def test_build_filter_conditions_invalid_values(self):
        """Test building filter conditions with invalid values"""
        filters = {
            'min_price': 'invalid',
            'max_price': 'invalid',
            'min_rating': 'invalid'
        }
        
        # Should handle invalid values gracefully
        conditions = self.api._build_filter_conditions(filters)
        
        # Should not include invalid filters
        assert 'price' not in conditions
        assert 'rating' not in conditions


if __name__ == '__main__':
    pytest.main([__file__])