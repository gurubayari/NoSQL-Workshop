"""
Unit tests for Product API Lambda function
"""
import pytest
import json
from unittest.mock import Mock, patch, MagicMock
from bson import ObjectId
from datetime import datetime
import sys
import os

# Add the functions directory to the path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'functions'))
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'shared'))

from product_api import ProductAPI, lambda_handler

class TestProductAPI:
    """Test cases for ProductAPI class"""
    
    @pytest.fixture
    def product_api(self):
        """Create ProductAPI instance with mocked dependencies"""
        with patch('product_api.get_documentdb_collection') as mock_collection:
            api = ProductAPI()
            api.products_collection = Mock()
            api.reviews_collection = Mock()
            return api
    
    @pytest.fixture
    def sample_product(self):
        """Sample product data for testing"""
        return {
            '_id': ObjectId('507f1f77bcf86cd799439011'),
            'title': 'Wireless Bluetooth Headphones',
            'description': 'High-quality wireless headphones with noise cancellation',
            'price': 199.99,
            'category': 'Electronics',
            'tags': ['wireless', 'bluetooth', 'headphones', 'audio'],
            'average_rating': 4.5,
            'review_count': 234,
            'in_stock': True,
            'stock_quantity': 150,
            'created_at': datetime(2024, 1, 1),
            'updated_at': datetime(2024, 1, 15)
        }
    
    @pytest.fixture
    def sample_event_list_products(self):
        """Sample event for listing products"""
        return {
            'httpMethod': 'GET',
            'path': '/api/products',
            'queryStringParameters': {
                'page': '1',
                'limit': '20',
                'category': 'Electronics',
                'sort_by': 'price',
                'sort_order': 'asc'
            }
        }
    
    @pytest.fixture
    def sample_event_get_product(self):
        """Sample event for getting product detail"""
        return {
            'httpMethod': 'GET',
            'path': '/api/products/507f1f77bcf86cd799439011',
            'pathParameters': {
                'id': '507f1f77bcf86cd799439011'
            }
        }
    
    @pytest.fixture
    def sample_event_search_products(self):
        """Sample event for searching products"""
        return {
            'httpMethod': 'POST',
            'path': '/api/products/search',
            'body': json.dumps({
                'q': 'wireless headphones',
                'category': 'Electronics',
                'min_price': '100',
                'max_price': '300',
                'page': '1',
                'limit': '10'
            })
        }
    
    @patch('product_api.cache_get')
    @patch('product_api.cache_set')
    def test_list_products_success(self, mock_cache_set, mock_cache_get, product_api, sample_product, sample_event_list_products):
        """Test successful product listing"""
        # Mock cache miss
        mock_cache_get.return_value = None
        
        # Mock database response
        mock_cursor = Mock()
        mock_cursor.__iter__ = Mock(return_value=iter([sample_product]))
        product_api.products_collection.find.return_value.sort.return_value.skip.return_value.limit.return_value = mock_cursor
        product_api.products_collection.count_documents.return_value = 1
        
        # Call the method
        response = product_api.list_products(sample_event_list_products)
        
        # Assertions
        assert response['statusCode'] == 200
        assert 'application/json' in response['headers']['Content-Type']
        
        body = json.loads(response['body'])
        assert 'products' in body
        assert 'pagination' in body
        assert body['pagination']['total_items'] == 1
        assert body['pagination']['current_page'] == 1
        
        # Verify database query was called
        product_api.products_collection.find.assert_called_once()
        product_api.products_collection.count_documents.assert_called_once()
        
        # Verify caching
        mock_cache_set.assert_called_once()
    
    @patch('product_api.cache_get')
    def test_list_products_cached_response(self, mock_cache_get, product_api, sample_event_list_products):
        """Test cached response for product listing"""
        # Mock cache hit
        cached_response = json.dumps({
            'products': [],
            'pagination': {'total_items': 0}
        })
        mock_cache_get.return_value = cached_response
        
        # Call the method
        response = product_api.list_products(sample_event_list_products)
        
        # Assertions
        assert response['statusCode'] == 200
        assert response['body'] == cached_response
        
        # Verify database was not called
        product_api.products_collection.find.assert_not_called()
    
    def test_list_products_invalid_parameters(self, product_api):
        """Test product listing with invalid parameters"""
        event = {
            'httpMethod': 'GET',
            'path': '/api/products',
            'queryStringParameters': {
                'page': 'invalid',
                'limit': '20'
            }
        }
        
        response = product_api.list_products(event)
        
        assert response['statusCode'] == 400
        body = json.loads(response['body'])
        assert 'error' in body
        assert 'Invalid parameters' in body['error']
    
    @patch('product_api.cache_get')
    @patch('product_api.cache_set')
    def test_get_product_detail_success(self, mock_cache_set, mock_cache_get, product_api, sample_product, sample_event_get_product):
        """Test successful product detail retrieval"""
        # Mock cache miss
        mock_cache_get.return_value = None
        
        # Mock database response
        product_api.products_collection.find_one.return_value = sample_product
        
        # Mock reviews summary
        with patch.object(product_api, '_get_reviews_summary') as mock_reviews:
            mock_reviews.return_value = {
                'total_reviews': 10,
                'average_rating': 4.5,
                'rating_distribution': {1: 0, 2: 1, 3: 2, 4: 3, 5: 4}
            }
            
            # Mock related products
            with patch.object(product_api, '_get_related_products') as mock_related:
                mock_related.return_value = []
                
                # Call the method
                response = product_api.get_product_detail(sample_event_get_product)
        
        # Assertions
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert 'product' in body
        assert 'reviews_summary' in body
        assert 'related_products' in body
        assert body['product']['title'] == 'Wireless Bluetooth Headphones'
        
        # Verify database query
        product_api.products_collection.find_one.assert_called_once()
        
        # Verify caching
        mock_cache_set.assert_called_once()
    
    def test_get_product_detail_not_found(self, product_api):
        """Test product detail retrieval for non-existent product"""
        event = {
            'httpMethod': 'GET',
            'path': '/api/products/nonexistent',
            'pathParameters': {
                'id': 'nonexistent'
            }
        }
        
        # Mock database response
        product_api.products_collection.find_one.return_value = None
        
        response = product_api.get_product_detail(event)
        
        assert response['statusCode'] == 404
        body = json.loads(response['body'])
        assert 'error' in body
        assert 'Product not found' in body['error']
    
    def test_get_product_detail_missing_id(self, product_api):
        """Test product detail retrieval without product ID"""
        event = {
            'httpMethod': 'GET',
            'path': '/api/products/',
            'pathParameters': {}
        }
        
        response = product_api.get_product_detail(event)
        
        assert response['statusCode'] == 400
        body = json.loads(response['body'])
        assert 'error' in body
        assert 'Missing product ID' in body['error']
    
    @patch('product_api.cache_get')
    @patch('product_api.cache_set')
    def test_search_products_success(self, mock_cache_set, mock_cache_get, product_api, sample_product, sample_event_search_products):
        """Test successful product search"""
        # Mock cache miss
        mock_cache_get.return_value = None
        
        # Mock database response
        mock_cursor = Mock()
        mock_cursor.__iter__ = Mock(return_value=iter([sample_product]))
        product_api.products_collection.find.return_value.sort.return_value.skip.return_value.limit.return_value = mock_cursor
        product_api.products_collection.count_documents.return_value = 1
        
        # Mock search suggestions
        with patch.object(product_api, '_get_search_suggestions') as mock_suggestions:
            mock_suggestions.return_value = ['wireless headphones', 'bluetooth headphones']
            
            # Call the method
            response = product_api.search_products(sample_event_search_products)
        
        # Assertions
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert 'products' in body
        assert 'suggestions' in body
        assert 'pagination' in body
        assert body['query'] == 'wireless headphones'
        assert len(body['suggestions']) == 2
        
        # Verify database query
        product_api.products_collection.find.assert_called_once()
        product_api.products_collection.count_documents.assert_called_once()
        
        # Verify caching
        mock_cache_set.assert_called_once()
    
    def test_search_products_missing_query(self, product_api):
        """Test product search without query parameter"""
        event = {
            'httpMethod': 'POST',
            'path': '/api/products/search',
            'body': json.dumps({})
        }
        
        response = product_api.search_products(event)
        
        assert response['statusCode'] == 400
        body = json.loads(response['body'])
        assert 'error' in body
        assert 'Missing search query' in body['error']
    
    def test_get_reviews_summary_success(self, product_api):
        """Test reviews summary calculation"""
        # Mock aggregation result
        mock_result = [{
            'total_reviews': 10,
            'average_rating': 4.2,
            'rating_distribution': [5, 4, 4, 3, 3, 2, 2, 1, 1, 1]
        }]
        product_api.reviews_collection.aggregate.return_value = mock_result
        
        result = product_api._get_reviews_summary('test_product_id')
        
        assert result['total_reviews'] == 10
        assert result['average_rating'] == 4.2
        assert isinstance(result['rating_distribution'], dict)
        assert sum(result['rating_distribution'].values()) == 10
    
    def test_get_reviews_summary_no_reviews(self, product_api):
        """Test reviews summary with no reviews"""
        # Mock empty aggregation result
        product_api.reviews_collection.aggregate.return_value = []
        
        result = product_api._get_reviews_summary('test_product_id')
        
        assert result['total_reviews'] == 0
        assert result['average_rating'] == 0
        assert result['rating_distribution'] == {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
    
    def test_get_related_products_success(self, product_api, sample_product):
        """Test related products retrieval"""
        # Mock database response
        mock_cursor = Mock()
        mock_cursor.__iter__ = Mock(return_value=iter([sample_product]))
        product_api.products_collection.find.return_value.sort.return_value.limit.return_value = mock_cursor
        
        result = product_api._get_related_products('Electronics', 'test_id')
        
        assert len(result) == 1
        assert result[0]['title'] == 'Wireless Bluetooth Headphones'
        
        # Verify database query
        product_api.products_collection.find.assert_called_once()
    
    def test_get_search_suggestions_success(self, product_api, sample_product):
        """Test search suggestions generation"""
        # Mock database response
        mock_cursor = Mock()
        mock_cursor.__iter__ = Mock(return_value=iter([{'title': 'Wireless Headphones'}]))
        product_api.products_collection.find.return_value.limit.return_value = mock_cursor
        
        result = product_api._get_search_suggestions('wireless')
        
        assert len(result) == 1
        assert result[0] == 'Wireless Headphones'

class TestLambdaHandler:
    """Test cases for lambda_handler function"""
    
    @patch('product_api.ProductAPI')
    def test_lambda_handler_get_products(self, mock_api_class):
        """Test lambda handler for GET /products"""
        mock_api = Mock()
        mock_api_class.return_value = mock_api
        mock_api.list_products.return_value = {'statusCode': 200, 'body': '{}'}
        
        event = {
            'httpMethod': 'GET',
            'path': '/api/products'
        }
        
        response = lambda_handler(event, {})
        
        assert response['statusCode'] == 200
        mock_api.list_products.assert_called_once_with(event)
    
    @patch('product_api.ProductAPI')
    def test_lambda_handler_get_product_detail(self, mock_api_class):
        """Test lambda handler for GET /products/{id}"""
        mock_api = Mock()
        mock_api_class.return_value = mock_api
        mock_api.get_product_detail.return_value = {'statusCode': 200, 'body': '{}'}
        
        event = {
            'httpMethod': 'GET',
            'path': '/api/products/123'
        }
        
        response = lambda_handler(event, {})
        
        assert response['statusCode'] == 200
        mock_api.get_product_detail.assert_called_once_with(event)
    
    @patch('product_api.ProductAPI')
    def test_lambda_handler_search_products(self, mock_api_class):
        """Test lambda handler for POST /products/search"""
        mock_api = Mock()
        mock_api_class.return_value = mock_api
        mock_api.search_products.return_value = {'statusCode': 200, 'body': '{}'}
        
        event = {
            'httpMethod': 'POST',
            'path': '/api/products/search'
        }
        
        response = lambda_handler(event, {})
        
        assert response['statusCode'] == 200
        mock_api.search_products.assert_called_once_with(event)
    
    def test_lambda_handler_method_not_allowed(self):
        """Test lambda handler for unsupported HTTP method"""
        event = {
            'httpMethod': 'DELETE',
            'path': '/api/products'
        }
        
        response = lambda_handler(event, {})
        
        assert response['statusCode'] == 405
        body = json.loads(response['body'])
        assert 'Method not allowed' in body['error']
    
    @patch('product_api.ProductAPI')
    def test_lambda_handler_exception(self, mock_api_class):
        """Test lambda handler with unhandled exception"""
        mock_api_class.side_effect = Exception('Test exception')
        
        event = {
            'httpMethod': 'GET',
            'path': '/api/products'
        }
        
        response = lambda_handler(event, {})
        
        assert response['statusCode'] == 500
        body = json.loads(response['body'])
        assert 'Internal server error' in body['error']

if __name__ == '__main__':
    pytest.main([__file__])