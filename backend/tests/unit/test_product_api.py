"""
Unit tests for Product API Lambda function
Tests all business logic including error handling and edge cases
"""
import pytest
import json
import unittest.mock as mock
from unittest.mock import MagicMock, patch, Mock
from datetime import datetime
from bson import ObjectId
import sys
import os

# Add the functions directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'functions'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'shared'))

# Mock the shared modules before importing
with patch.dict('sys.modules', {
    'database': MagicMock(),
    'config': MagicMock(),
    'monitoring': MagicMock(),
    'error_handling': MagicMock()
}):
    from product_api import ProductAPI, lambda_handler

class TestProductAPI:
    """Test cases for ProductAPI class"""
    
    def setup_method(self):
        """Set up test fixtures"""
        self.mock_products_collection = MagicMock()
        self.mock_reviews_collection = MagicMock()
        
        with patch('product_api.get_documentdb_collection') as mock_get_collection:
            mock_get_collection.side_effect = lambda name: {
                'products': self.mock_products_collection,
                'reviews': self.mock_reviews_collection
            }[name]
            
            self.api = ProductAPI()
    
    def test_list_products_success(self):
        """Test successful product listing with pagination"""
        # Mock data
        mock_products = [
            {
                '_id': ObjectId(),
                'title': 'Test Product 1',
                'price': 99.99,
                'category': 'Electronics',
                'rating': 4.5,
                'created_at': datetime.utcnow(),
                'updated_at': datetime.utcnow()
            },
            {
                '_id': ObjectId(),
                'title': 'Test Product 2',
                'price': 149.99,
                'category': 'Electronics',
                'rating': 4.2,
                'created_at': datetime.utcnow(),
                'updated_at': datetime.utcnow()
            }
        ]
        
        # Mock collection methods
        mock_cursor = MagicMock()
        mock_cursor.__iter__ = Mock(return_value=iter(mock_products))
        self.mock_products_collection.find.return_value.sort.return_value.skip.return_value.limit.return_value = mock_cursor
        self.mock_products_collection.count_documents.return_value = 2
        
        # Mock cache
        with patch('product_api.cache_get', return_value=None), \
             patch('product_api.cache_set') as mock_cache_set:
            
            # Test event
            event = {
                'queryStringParameters': {
                    'page': '1',
                    'limit': '20',
                    'category': 'Electronics'
                }
            }
            
            result = self.api.list_products(event)
            
            # Assertions
            assert result['statusCode'] == 200
            response_body = json.loads(result['body'])
            assert 'products' in response_body
            assert 'pagination' in response_body
            assert len(response_body['products']) == 2
            assert response_body['pagination']['current_page'] == 1
            assert response_body['pagination']['total_items'] == 2
            
            # Verify cache was called
            mock_cache_set.assert_called_once()
    
    def test_list_products_with_filters(self):
        """Test product listing with various filters"""
        # Mock empty result for filtered query
        mock_cursor = MagicMock()
        mock_cursor.__iter__ = Mock(return_value=iter([]))
        self.mock_products_collection.find.return_value.sort.return_value.skip.return_value.limit.return_value = mock_cursor
        self.mock_products_collection.count_documents.return_value = 0
        
        with patch('product_api.cache_get', return_value=None), \
             patch('product_api.cache_set'):
            
            event = {
                'queryStringParameters': {
                    'page': '1',
                    'limit': '10',
                    'category': 'Electronics',
                    'min_price': '50',
                    'max_price': '200',
                    'min_rating': '4.0',
                    'sort_by': 'price',
                    'sort_order': 'asc',
                    'search': 'wireless'
                }
            }
            
            result = self.api.list_products(event)
            
            # Verify the query was built correctly
            call_args = self.mock_products_collection.find.call_args[0][0]
            assert 'category' in call_args
            assert 'price' in call_args
            assert 'average_rating' in call_args
            assert '$or' in call_args  # Search term
            
            assert result['statusCode'] == 200
    
    def test_list_products_invalid_sort_field(self):
        """Test product listing with invalid sort field"""
        with patch('product_api.ValidationError') as mock_validation_error:
            mock_validation_error.side_effect = Exception("Invalid sort field")
            
            event = {
                'queryStringParameters': {
                    'sort_by': 'invalid_field'
                }
            }
            
            # Should raise validation error
            with pytest.raises(Exception):
                self.api.list_products(event)
    
    def test_list_products_cached_result(self):
        """Test returning cached product list"""
        cached_data = json.dumps({
            'products': [],
            'pagination': {'current_page': 1, 'total_items': 0}
        })
        
        with patch('product_api.cache_get', return_value=cached_data):
            event = {'queryStringParameters': {'page': '1'}}
            result = self.api.list_products(event)
            
            assert result['statusCode'] == 200
            # Should not call database
            self.mock_products_collection.find.assert_not_called()
    
    def test_get_product_detail_success(self):
        """Test successful product detail retrieval"""
        product_id = str(ObjectId())
        mock_product = {
            '_id': ObjectId(product_id),
            'title': 'Test Product',
            'description': 'Test Description',
            'price': 99.99,
            'category': 'Electronics',
            'rating': 4.5,
            'created_at': datetime.utcnow(),
            'updated_at': datetime.utcnow()
        }
        
        self.mock_products_collection.find_one.return_value = mock_product
        
        # Mock reviews summary
        with patch.object(self.api, '_get_reviews_summary', return_value={'total_reviews': 5}), \
             patch.object(self.api, '_get_related_products', return_value=[]), \
             patch('product_api.cache_get', return_value=None), \
             patch('product_api.cache_set'):
            
            event = {
                'pathParameters': {'id': product_id}
            }
            
            result = self.api.get_product_detail(event)
            
            assert result['statusCode'] == 200
            response_body = json.loads(result['body'])
            assert 'product' in response_body
            assert 'reviews_summary' in response_body
            assert 'related_products' in response_body
            assert response_body['product']['title'] == 'Test Product'
    
    def test_get_product_detail_not_found(self):
        """Test product detail when product doesn't exist"""
        self.mock_products_collection.find_one.return_value = None
        
        with patch('product_api.cache_get', return_value=None):
            event = {
                'pathParameters': {'id': 'nonexistent_id'}
            }
            
            result = self.api.get_product_detail(event)
            
            assert result['statusCode'] == 404
            response_body = json.loads(result['body'])
            assert 'error' in response_body
            assert 'Product not found' in response_body['error']
    
    def test_get_product_detail_missing_id(self):
        """Test product detail with missing product ID"""
        event = {'pathParameters': {}}
        
        result = self.api.get_product_detail(event)
        
        assert result['statusCode'] == 400
        response_body = json.loads(result['body'])
        assert 'Missing product ID' in response_body['error']
    
    def test_search_products_success(self):
        """Test successful product search"""
        mock_products = [
            {
                '_id': ObjectId(),
                'title': 'Wireless Headphones',
                'description': 'Great sound quality',
                'price': 99.99,
                'category': 'Electronics',
                'rating': 4.5,
                'created_at': datetime.utcnow()
            }
        ]
        
        mock_cursor = MagicMock()
        mock_cursor.__iter__ = Mock(return_value=iter(mock_products))
        self.mock_products_collection.find.return_value.sort.return_value.skip.return_value.limit.return_value = mock_cursor
        self.mock_products_collection.count_documents.return_value = 1
        
        with patch.object(self.api, '_get_search_suggestions', return_value=['wireless earbuds']), \
             patch('product_api.cache_get', return_value=None), \
             patch('product_api.cache_set'):
            
            event = {
                'httpMethod': 'GET',
                'queryStringParameters': {
                    'q': 'wireless headphones',
                    'page': '1',
                    'limit': '20'
                }
            }
            
            result = self.api.search_products(event)
            
            assert result['statusCode'] == 200
            response_body = json.loads(result['body'])
            assert 'products' in response_body
            assert 'suggestions' in response_body
            assert response_body['query'] == 'wireless headphones'
            assert len(response_body['products']) == 1
    
    def test_search_products_empty_query(self):
        """Test product search with empty query"""
        event = {
            'httpMethod': 'GET',
            'queryStringParameters': {'q': ''}
        }
        
        result = self.api.search_products(event)
        
        assert result['statusCode'] == 400
        response_body = json.loads(result['body'])
        assert 'Missing search query' in response_body['error']
    
    def test_search_products_post_method(self):
        """Test product search via POST method"""
        mock_products = []
        mock_cursor = MagicMock()
        mock_cursor.__iter__ = Mock(return_value=iter(mock_products))
        self.mock_products_collection.find.return_value.sort.return_value.skip.return_value.limit.return_value = mock_cursor
        self.mock_products_collection.count_documents.return_value = 0
        
        with patch.object(self.api, '_get_search_suggestions', return_value=[]), \
             patch('product_api.cache_get', return_value=None), \
             patch('product_api.cache_set'):
            
            event = {
                'httpMethod': 'POST',
                'body': json.dumps({
                    'q': 'test query',
                    'category': 'Electronics',
                    'min_price': '50',
                    'max_price': '200'
                })
            }
            
            result = self.api.search_products(event)
            
            assert result['statusCode'] == 200
            response_body = json.loads(result['body'])
            assert response_body['query'] == 'test query'
    
    def test_get_reviews_summary(self):
        """Test reviews summary aggregation"""
        mock_aggregation_result = [
            {
                '_id': None,
                'total_reviews': 10,
                'average_rating': 4.2,
                'rating_distribution': [5, 4, 4, 3, 5, 5, 4, 3, 4, 5]
            }
        ]
        
        self.mock_reviews_collection.aggregate.return_value = mock_aggregation_result
        
        result = self.api._get_reviews_summary('test_product_id')
        
        assert result['total_reviews'] == 10
        assert result['average_rating'] == 4.2
        assert isinstance(result['rating_distribution'], dict)
        assert result['rating_distribution'][5] == 4  # Count of 5-star ratings
    
    def test_get_reviews_summary_no_reviews(self):
        """Test reviews summary when no reviews exist"""
        self.mock_reviews_collection.aggregate.return_value = []
        
        result = self.api._get_reviews_summary('test_product_id')
        
        assert result['total_reviews'] == 0
        assert result['average_rating'] == 0
        assert all(count == 0 for count in result['rating_distribution'].values())
    
    def test_get_related_products(self):
        """Test related products retrieval"""
        mock_related = [
            {
                '_id': ObjectId(),
                'title': 'Related Product',
                'category': 'Electronics',
                'rating': 4.0,
                'created_at': datetime.utcnow()
            }
        ]
        
        mock_cursor = MagicMock()
        mock_cursor.__iter__ = Mock(return_value=iter(mock_related))
        self.mock_products_collection.find.return_value.sort.return_value.limit.return_value = mock_cursor
        
        result = self.api._get_related_products('Electronics', 'exclude_id')
        
        assert len(result) == 1
        assert result[0]['title'] == 'Related Product'
        
        # Verify exclusion query
        call_args = self.mock_products_collection.find.call_args[0][0]
        assert 'category' in call_args
        assert '_id' in call_args
        assert call_args['_id']['$ne'] == 'exclude_id'
    
    def test_get_search_suggestions(self):
        """Test search suggestions generation"""
        mock_products = [
            {'title': 'Wireless Headphones Premium'},
            {'title': 'Wireless Earbuds Pro'}
        ]
        
        mock_cursor = MagicMock()
        mock_cursor.__iter__ = Mock(return_value=iter(mock_products))
        self.mock_products_collection.find.return_value.limit.return_value = mock_cursor
        
        result = self.api._get_search_suggestions('wireless')
        
        assert len(result) == 2
        assert 'Wireless Headphones Premium' in result
        assert 'Wireless Earbuds Pro' in result


class TestProductAPILambdaHandler:
    """Test cases for lambda_handler function"""
    
    def test_lambda_handler_get_products(self):
        """Test lambda handler for GET /products"""
        with patch('product_api.product_api') as mock_api:
            mock_api.list_products.return_value = {
                'statusCode': 200,
                'body': json.dumps({'products': []})
            }
            
            event = {
                'httpMethod': 'GET',
                'path': '/products',
                'queryStringParameters': {}
            }
            context = MagicMock()
            context.aws_request_id = 'test-request-id'
            
            with patch('product_api.lambda_monitor'), \
                 patch('product_api.log_api_call'), \
                 patch('product_api.performance_monitor'):
                
                result = lambda_handler(event, context)
                
                assert result['statusCode'] == 200
                mock_api.list_products.assert_called_once_with(event)
    
    def test_lambda_handler_get_product_detail(self):
        """Test lambda handler for GET /products/{id}"""
        with patch('product_api.product_api') as mock_api:
            mock_api.get_product_detail.return_value = {
                'statusCode': 200,
                'body': json.dumps({'product': {}})
            }
            
            event = {
                'httpMethod': 'GET',
                'path': '/products/123',
                'pathParameters': {'id': '123'}
            }
            context = MagicMock()
            context.aws_request_id = 'test-request-id'
            
            with patch('product_api.lambda_monitor'), \
                 patch('product_api.log_api_call'), \
                 patch('product_api.performance_monitor'):
                
                result = lambda_handler(event, context)
                
                assert result['statusCode'] == 200
                mock_api.get_product_detail.assert_called_once_with(event)
    
    def test_lambda_handler_search_products(self):
        """Test lambda handler for product search"""
        with patch('product_api.product_api') as mock_api:
            mock_api.search_products.return_value = {
                'statusCode': 200,
                'body': json.dumps({'products': [], 'query': 'test'})
            }
            
            event = {
                'httpMethod': 'POST',
                'path': '/products/search',
                'body': json.dumps({'q': 'test'})
            }
            context = MagicMock()
            context.aws_request_id = 'test-request-id'
            
            with patch('product_api.lambda_monitor'), \
                 patch('product_api.log_api_call'), \
                 patch('product_api.performance_monitor'):
                
                result = lambda_handler(event, context)
                
                assert result['statusCode'] == 200
                mock_api.search_products.assert_called_once_with(event)
    
    def test_lambda_handler_unsupported_method(self):
        """Test lambda handler with unsupported HTTP method"""
        event = {
            'httpMethod': 'DELETE',
            'path': '/products'
        }
        context = MagicMock()
        context.aws_request_id = 'test-request-id'
        
        with patch('product_api.lambda_monitor'), \
             patch('product_api.ValidationError') as mock_error, \
             patch('product_api.create_error_response') as mock_create_error:
            
            mock_error.side_effect = Exception("Method not supported")
            mock_create_error.return_value = {
                'statusCode': 405,
                'body': json.dumps({'error': 'Method not allowed'})
            }
            
            result = lambda_handler(event, context)
            
            assert result['statusCode'] == 405
    
    def test_lambda_handler_exception_handling(self):
        """Test lambda handler exception handling"""
        with patch('product_api.product_api') as mock_api:
            mock_api.list_products.side_effect = Exception("Database error")
            
            event = {
                'httpMethod': 'GET',
                'path': '/products'
            }
            context = MagicMock()
            context.aws_request_id = 'test-request-id'
            
            with patch('product_api.lambda_monitor'), \
                 patch('product_api.create_error_response') as mock_create_error, \
                 patch('product_api.security_monitor'):
                
                mock_create_error.return_value = {
                    'statusCode': 500,
                    'body': json.dumps({'error': 'Internal server error'})
                }
                
                result = lambda_handler(event, context)
                
                assert result['statusCode'] == 500


class TestProductAPIEdgeCases:
    """Test edge cases and error conditions"""
    
    def setup_method(self):
        """Set up test fixtures"""
        self.mock_products_collection = MagicMock()
        self.mock_reviews_collection = MagicMock()
        
        with patch('product_api.get_documentdb_collection') as mock_get_collection:
            mock_get_collection.side_effect = lambda name: {
                'products': self.mock_products_collection,
                'reviews': self.mock_reviews_collection
            }[name]
            
            self.api = ProductAPI()
    
    def test_list_products_database_error(self):
        """Test handling of database errors in list_products"""
        from pymongo.errors import PyMongoError
        
        self.mock_products_collection.find.side_effect = PyMongoError("Connection failed")
        
        with patch('product_api.cache_get', return_value=None):
            event = {'queryStringParameters': {}}
            result = self.api.list_products(event)
            
            assert result['statusCode'] == 500
            response_body = json.loads(result['body'])
            assert 'Database error' in response_body['error']
    
    def test_list_products_invalid_pagination(self):
        """Test handling of invalid pagination parameters"""
        event = {
            'queryStringParameters': {
                'page': 'invalid',
                'limit': 'invalid'
            }
        }
        
        result = self.api.list_products(event)
        
        assert result['statusCode'] == 400
        response_body = json.loads(result['body'])
        assert 'Invalid parameters' in response_body['error']
    
    def test_search_products_with_filters_and_no_results(self):
        """Test search with filters that return no results"""
        mock_cursor = MagicMock()
        mock_cursor.__iter__ = Mock(return_value=iter([]))
        self.mock_products_collection.find.return_value.sort.return_value.skip.return_value.limit.return_value = mock_cursor
        self.mock_products_collection.count_documents.return_value = 0
        
        with patch.object(self.api, '_get_search_suggestions', return_value=['alternative']), \
             patch('product_api.cache_get', return_value=None), \
             patch('product_api.cache_set'):
            
            event = {
                'httpMethod': 'GET',
                'queryStringParameters': {
                    'q': 'nonexistent product',
                    'category': 'NonexistentCategory',
                    'min_price': '1000',
                    'max_price': '2000'
                }
            }
            
            result = self.api.search_products(event)
            
            assert result['statusCode'] == 200
            response_body = json.loads(result['body'])
            assert len(response_body['products']) == 0
            assert response_body['pagination']['total_items'] == 0
            assert 'suggestions' in response_body
    
    def test_get_reviews_summary_aggregation_error(self):
        """Test handling of aggregation errors in reviews summary"""
        from pymongo.errors import PyMongoError
        
        self.mock_reviews_collection.aggregate.side_effect = PyMongoError("Aggregation failed")
        
        result = self.api._get_reviews_summary('test_product_id')
        
        # Should return default values on error
        assert result['total_reviews'] == 0
        assert result['average_rating'] == 0
        assert isinstance(result['rating_distribution'], dict)
    
    def test_get_related_products_with_invalid_object_id(self):
        """Test related products with invalid ObjectId"""
        mock_related = [{'_id': 'string_id', 'title': 'Test', 'created_at': datetime.utcnow()}]
        mock_cursor = MagicMock()
        mock_cursor.__iter__ = Mock(return_value=iter(mock_related))
        self.mock_products_collection.find.return_value.sort.return_value.limit.return_value = mock_cursor
        
        result = self.api._get_related_products('Electronics', 'invalid_object_id')
        
        assert len(result) == 1
        assert result[0]['_id'] == 'string_id'  # Should handle string IDs gracefully


if __name__ == '__main__':
    pytest.main([__file__])