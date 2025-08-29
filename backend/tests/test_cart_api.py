"""
Unit tests for Shopping Cart API Lambda function
"""
import pytest
import json
from unittest.mock import Mock, patch, MagicMock, AsyncMock
from decimal import Decimal
from datetime import datetime
import sys
import os
from botocore.exceptions import ClientError

# Add the functions directory to the path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'functions'))
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'shared'))

from cart_api import ShoppingCartAPI, lambda_handler

class TestShoppingCartAPI:
    """Test cases for ShoppingCartAPI class"""
    
    @pytest.fixture
    def cart_api(self):
        """Create ShoppingCartAPI instance with mocked dependencies"""
        with patch('cart_api.get_dynamodb_table') as mock_table:
            with patch('cart_api.get_documentdb_collection') as mock_collection:
                api = ShoppingCartAPI()
                api.cart_table = Mock()
                api.inventory_table = Mock()
                api.products_collection = Mock()
                return api
    
    @pytest.fixture
    def sample_cart_item(self):
        """Sample cart item data for testing"""
        return {
            'userId': 'user123',
            'productId': 'prod456',
            'quantity': 2,
            'price': Decimal('99.99'),
            'addedAt': '2024-01-01T10:00:00Z',
            'updatedAt': '2024-01-01T10:00:00Z',
            'ttl': 1735689600
        }
    
    @pytest.fixture
    def sample_product(self):
        """Sample product data for testing"""
        return {
            '_id': 'prod456',
            'title': 'Wireless Headphones',
            'price': 99.99,
            'image_url': 'https://example.com/image.jpg',
            'category': 'Electronics',
            'in_stock': True
        }
    
    @pytest.fixture
    def sample_event_get_cart(self):
        """Sample event for getting cart"""
        return {
            'httpMethod': 'GET',
            'path': '/api/cart/user123',
            'pathParameters': {
                'userId': 'user123'
            }
        }
    
    @pytest.fixture
    def sample_event_add_to_cart(self):
        """Sample event for adding to cart"""
        return {
            'httpMethod': 'POST',
            'path': '/api/cart/user123/items',
            'pathParameters': {
                'userId': 'user123'
            },
            'body': json.dumps({
                'productId': 'prod456',
                'quantity': 2
            })
        }
    
    @pytest.fixture
    def sample_event_update_cart(self):
        """Sample event for updating cart item"""
        return {
            'httpMethod': 'PUT',
            'path': '/api/cart/user123/items/prod456',
            'pathParameters': {
                'userId': 'user123',
                'productId': 'prod456'
            },
            'body': json.dumps({
                'quantity': 3
            })
        }
    
    @pytest.fixture
    def sample_event_remove_from_cart(self):
        """Sample event for removing from cart"""
        return {
            'httpMethod': 'DELETE',
            'path': '/api/cart/user123/items/prod456',
            'pathParameters': {
                'userId': 'user123',
                'productId': 'prod456'
            }
        }
    
    @patch('cart_api.cache_get')
    @patch('cart_api.cache_set')
    def test_get_cart_success(self, mock_cache_set, mock_cache_get, cart_api, sample_cart_item, sample_event_get_cart):
        """Test successful cart retrieval"""
        # Mock cache miss
        mock_cache_get.return_value = None
        
        # Mock DynamoDB response
        cart_api.cart_table.query.return_value = {
            'Items': [sample_cart_item]
        }
        
        # Mock product info
        with patch.object(cart_api, '_get_product_info') as mock_product:
            mock_product.return_value = {
                'title': 'Wireless Headphones',
                'price': 99.99,
                'image_url': 'https://example.com/image.jpg',
                'category': 'Electronics'
            }
            
            # Mock inventory check
            with patch.object(cart_api, '_check_inventory') as mock_inventory:
                mock_inventory.return_value = 10
                
                # Mock enrich_cart_item
                with patch.object(cart_api, '_enrich_cart_item') as mock_enrich:
                    mock_enrich.return_value = {
                        'productId': 'prod456',
                        'title': 'Wireless Headphones',
                        'price': 99.99,
                        'quantity': 2,
                        'subtotal': 199.98,
                        'inStock': True
                    }
                    
                    # Call the method
                    response = cart_api.get_cart(sample_event_get_cart)
        
        # Assertions
        assert response['statusCode'] == 200
        assert 'application/json' in response['headers']['Content-Type']
        
        body = json.loads(response['body'])
        assert 'items' in body
        assert 'totalAmount' in body
        assert body['userId'] == 'user123'
        assert body['itemCount'] == 1
        
        # Verify database query was called
        cart_api.cart_table.query.assert_called_once()
        
        # Verify caching
        mock_cache_set.assert_called_once()
    
    @patch('cart_api.cache_get')
    def test_get_cart_cached_response(self, mock_cache_get, cart_api, sample_event_get_cart):
        """Test cached response for cart retrieval"""
        # Mock cache hit
        cached_response = json.dumps({
            'userId': 'user123',
            'items': [],
            'itemCount': 0,
            'totalAmount': 0
        })
        mock_cache_get.return_value = cached_response
        
        # Call the method
        response = cart_api.get_cart(sample_event_get_cart)
        
        # Assertions
        assert response['statusCode'] == 200
        assert response['body'] == cached_response
        
        # Verify database was not called
        cart_api.cart_table.query.assert_not_called()
    
    def test_get_cart_missing_user_id(self, cart_api):
        """Test cart retrieval without user ID"""
        event = {
            'httpMethod': 'GET',
            'path': '/api/cart/',
            'pathParameters': {}
        }
        
        response = cart_api.get_cart(event)
        
        assert response['statusCode'] == 400
        body = json.loads(response['body'])
        assert 'error' in body
        assert 'Missing user ID' in body['error']
    
    @patch('cart_api.cache_delete')
    def test_add_to_cart_success(self, mock_cache_delete, cart_api, sample_event_add_to_cart, sample_product):
        """Test successful item addition to cart"""
        # Mock product info
        with patch.object(cart_api, '_get_product_info') as mock_product:
            mock_product.return_value = sample_product
            
            # Mock inventory check
            with patch.object(cart_api, '_check_inventory') as mock_inventory:
                mock_inventory.return_value = 10
                
                # Mock DynamoDB get_item (item doesn't exist)
                cart_api.cart_table.get_item.return_value = {}
                
                # Mock DynamoDB put_item
                cart_api.cart_table.put_item.return_value = {}
                
                # Call the method
                response = cart_api.add_to_cart(sample_event_add_to_cart)
        
        # Assertions
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert 'message' in body
        assert body['productId'] == 'prod456'
        assert body['quantity'] == 2
        
        # Verify database operations
        cart_api.cart_table.get_item.assert_called_once()
        cart_api.cart_table.put_item.assert_called_once()
        
        # Verify cache invalidation
        mock_cache_delete.assert_called_once()
    
    def test_add_to_cart_update_existing(self, cart_api, sample_event_add_to_cart, sample_product, sample_cart_item):
        """Test updating existing item in cart"""
        # Mock product info
        with patch.object(cart_api, '_get_product_info') as mock_product:
            mock_product.return_value = sample_product
            
            # Mock inventory check
            with patch.object(cart_api, '_check_inventory') as mock_inventory:
                mock_inventory.return_value = 10
                
                # Mock DynamoDB get_item (item exists)
                cart_api.cart_table.get_item.return_value = {'Item': sample_cart_item}
                
                # Mock DynamoDB update_item
                cart_api.cart_table.update_item.return_value = {}
                
                # Call the method
                response = cart_api.add_to_cart(sample_event_add_to_cart)
        
        # Assertions
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['quantity'] == 4  # 2 existing + 2 new
        
        # Verify database operations
        cart_api.cart_table.get_item.assert_called_once()
        cart_api.cart_table.update_item.assert_called_once()
    
    def test_add_to_cart_insufficient_inventory(self, cart_api, sample_event_add_to_cart, sample_product):
        """Test adding to cart with insufficient inventory"""
        # Mock product info
        with patch.object(cart_api, '_get_product_info') as mock_product:
            mock_product.return_value = sample_product
            
            # Mock inventory check (insufficient)
            with patch.object(cart_api, '_check_inventory') as mock_inventory:
                mock_inventory.return_value = 1  # Less than requested quantity of 2
                
                # Call the method
                response = cart_api.add_to_cart(sample_event_add_to_cart)
        
        # Assertions
        assert response['statusCode'] == 400
        body = json.loads(response['body'])
        assert 'Insufficient inventory' in body['error']
    
    def test_add_to_cart_product_not_found(self, cart_api, sample_event_add_to_cart):
        """Test adding non-existent product to cart"""
        # Mock product info (not found)
        with patch.object(cart_api, '_get_product_info') as mock_product:
            mock_product.return_value = None
            
            # Call the method
            response = cart_api.add_to_cart(sample_event_add_to_cart)
        
        # Assertions
        assert response['statusCode'] == 404
        body = json.loads(response['body'])
        assert 'Product not found' in body['error']
    
    def test_add_to_cart_invalid_quantity(self, cart_api):
        """Test adding to cart with invalid quantity"""
        event = {
            'httpMethod': 'POST',
            'path': '/api/cart/user123/items',
            'pathParameters': {'userId': 'user123'},
            'body': json.dumps({
                'productId': 'prod456',
                'quantity': -1  # Invalid quantity
            })
        }
        
        response = cart_api.add_to_cart(event)
        
        assert response['statusCode'] == 400
        body = json.loads(response['body'])
        assert 'Invalid quantity' in body['error']
    
    @patch('cart_api.cache_delete')
    def test_update_cart_item_success(self, mock_cache_delete, cart_api, sample_event_update_cart, sample_product):
        """Test successful cart item update"""
        # Mock product info
        with patch.object(cart_api, '_get_product_info') as mock_product:
            mock_product.return_value = sample_product
            
            # Mock inventory check
            with patch.object(cart_api, '_check_inventory') as mock_inventory:
                mock_inventory.return_value = 10
                
                # Mock DynamoDB update_item
                cart_api.cart_table.update_item.return_value = {
                    'Attributes': {
                        'userId': 'user123',
                        'productId': 'prod456',
                        'quantity': 3,
                        'price': Decimal('99.99')
                    }
                }
                
                # Call the method
                response = cart_api.update_cart_item(sample_event_update_cart)
        
        # Assertions
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['quantity'] == 3
        assert body['productId'] == 'prod456'
        
        # Verify database operations
        cart_api.cart_table.update_item.assert_called_once()
        
        # Verify cache invalidation
        mock_cache_delete.assert_called_once()
    
    def test_update_cart_item_zero_quantity(self, cart_api):
        """Test updating cart item with zero quantity (should remove)"""
        event = {
            'httpMethod': 'PUT',
            'path': '/api/cart/user123/items/prod456',
            'pathParameters': {
                'userId': 'user123',
                'productId': 'prod456'
            },
            'body': json.dumps({'quantity': 0})
        }
        
        # Mock the remove_from_cart method
        with patch.object(cart_api, 'remove_from_cart') as mock_remove:
            mock_remove.return_value = {
                'statusCode': 200,
                'headers': cart_api._get_cors_headers(),
                'body': json.dumps({'message': 'Item removed'})
            }
            
            response = cart_api.update_cart_item(event)
            
            # Should call remove_from_cart
            mock_remove.assert_called_once_with(event)
    
    def test_update_cart_item_not_found(self, cart_api, sample_event_update_cart, sample_product):
        """Test updating non-existent cart item"""
        # Mock product info
        with patch.object(cart_api, '_get_product_info') as mock_product:
            mock_product.return_value = sample_product
            
            # Mock inventory check
            with patch.object(cart_api, '_check_inventory') as mock_inventory:
                mock_inventory.return_value = 10
                
                # Mock DynamoDB update_item (item not found)
                error = ClientError(
                    {'Error': {'Code': 'ConditionalCheckFailedException'}},
                    'UpdateItem'
                )
                cart_api.cart_table.update_item.side_effect = error
                
                # Call the method
                response = cart_api.update_cart_item(sample_event_update_cart)
        
        # Assertions
        assert response['statusCode'] == 404
        body = json.loads(response['body'])
        assert 'Item not found' in body['error']
    
    @patch('cart_api.cache_delete')
    def test_remove_from_cart_success(self, mock_cache_delete, cart_api, sample_event_remove_from_cart):
        """Test successful item removal from cart"""
        # Mock DynamoDB delete_item
        cart_api.cart_table.delete_item.return_value = {}
        
        # Call the method
        response = cart_api.remove_from_cart(sample_event_remove_from_cart)
        
        # Assertions
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert 'removed' in body['message']
        assert body['productId'] == 'prod456'
        
        # Verify database operations
        cart_api.cart_table.delete_item.assert_called_once()
        
        # Verify cache invalidation
        mock_cache_delete.assert_called_once()
    
    def test_remove_from_cart_not_found(self, cart_api, sample_event_remove_from_cart):
        """Test removing non-existent cart item"""
        # Mock DynamoDB delete_item (item not found)
        error = ClientError(
            {'Error': {'Code': 'ConditionalCheckFailedException'}},
            'DeleteItem'
        )
        cart_api.cart_table.delete_item.side_effect = error
        
        # Call the method
        response = cart_api.remove_from_cart(sample_event_remove_from_cart)
        
        # Assertions
        assert response['statusCode'] == 404
        body = json.loads(response['body'])
        assert 'Item not found' in body['error']
    
    @patch('cart_api.cache_delete')
    def test_clear_cart_success(self, mock_cache_delete, cart_api, sample_cart_item):
        """Test successful cart clearing"""
        event = {
            'httpMethod': 'DELETE',
            'path': '/api/cart/user123/clear',
            'pathParameters': {'userId': 'user123'}
        }
        
        # Mock DynamoDB query
        cart_api.cart_table.query.return_value = {
            'Items': [sample_cart_item, sample_cart_item]
        }
        
        # Mock DynamoDB delete_item
        cart_api.cart_table.delete_item.return_value = {}
        
        # Call the method
        response = cart_api.clear_cart(event)
        
        # Assertions
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert 'cleared' in body['message']
        assert body['itemsRemoved'] == 2
        
        # Verify database operations
        cart_api.cart_table.query.assert_called_once()
        assert cart_api.cart_table.delete_item.call_count == 2
        
        # Verify cache invalidation
        mock_cache_delete.assert_called_once()
    
    def test_get_product_info_success(self, cart_api, sample_product):
        """Test successful product info retrieval"""
        # Mock DocumentDB response
        cart_api.products_collection.find_one.return_value = sample_product
        
        result = cart_api._get_product_info('prod456')
        
        assert result is not None
        assert result['title'] == 'Wireless Headphones'
        assert result['price'] == 99.99
    
    def test_get_product_info_not_found(self, cart_api):
        """Test product info retrieval for non-existent product"""
        # Mock DocumentDB response (not found)
        cart_api.products_collection.find_one.return_value = None
        
        result = cart_api._get_product_info('nonexistent')
        
        assert result is None
    
    def test_check_inventory_success(self, cart_api):
        """Test successful inventory check"""
        # Mock DynamoDB response
        cart_api.inventory_table.get_item.return_value = {
            'Item': {'productId': 'prod456', 'availableQuantity': 10}
        }
        
        result = cart_api._check_inventory('prod456')
        
        assert result == 10
    
    def test_check_inventory_not_found(self, cart_api):
        """Test inventory check for non-existent product"""
        # Mock DynamoDB response (not found)
        cart_api.inventory_table.get_item.return_value = {}
        
        result = cart_api._check_inventory('nonexistent')
        
        assert result == 0
    
    def test_get_inventory_status(self, cart_api):
        """Test inventory status calculation"""
        assert cart_api._get_inventory_status(0, 1) == 'out_of_stock'
        assert cart_api._get_inventory_status(5, 10) == 'insufficient_stock'
        assert cart_api._get_inventory_status(3, 2) == 'low_stock'
        assert cart_api._get_inventory_status(10, 2) == 'in_stock'
    
    def test_decimal_serializer(self, cart_api):
        """Test Decimal serialization"""
        result = cart_api._decimal_serializer(Decimal('99.99'))
        assert result == 99.99
        assert isinstance(result, float)
        
        with pytest.raises(TypeError):
            cart_api._decimal_serializer(object())

class TestLambdaHandler:
    """Test cases for lambda_handler function"""
    
    @patch('cart_api.ShoppingCartAPI')
    def test_lambda_handler_get_cart(self, mock_api_class):
        """Test lambda handler for GET /cart/{userId}"""
        mock_api = Mock()
        mock_api_class.return_value = mock_api
        mock_api.get_cart.return_value = {'statusCode': 200, 'body': '{}'}
        
        event = {
            'httpMethod': 'GET',
            'path': '/api/cart/user123'
        }
        
        response = lambda_handler(event, {})
        
        assert response['statusCode'] == 200
        mock_api.get_cart.assert_called_once_with(event)
    
    @patch('cart_api.ShoppingCartAPI')
    def test_lambda_handler_add_to_cart(self, mock_api_class):
        """Test lambda handler for POST /cart/{userId}/items"""
        mock_api = Mock()
        mock_api_class.return_value = mock_api
        mock_api.add_to_cart.return_value = {'statusCode': 200, 'body': '{}'}
        
        event = {
            'httpMethod': 'POST',
            'path': '/api/cart/user123/items'
        }
        
        response = lambda_handler(event, {})
        
        assert response['statusCode'] == 200
        mock_api.add_to_cart.assert_called_once_with(event)
    
    @patch('cart_api.ShoppingCartAPI')
    def test_lambda_handler_update_cart_item(self, mock_api_class):
        """Test lambda handler for PUT /cart/{userId}/items/{productId}"""
        mock_api = Mock()
        mock_api_class.return_value = mock_api
        mock_api.update_cart_item.return_value = {'statusCode': 200, 'body': '{}'}
        
        event = {
            'httpMethod': 'PUT',
            'path': '/api/cart/user123/items/prod456'
        }
        
        response = lambda_handler(event, {})
        
        assert response['statusCode'] == 200
        mock_api.update_cart_item.assert_called_once_with(event)
    
    @patch('cart_api.ShoppingCartAPI')
    def test_lambda_handler_remove_from_cart(self, mock_api_class):
        """Test lambda handler for DELETE /cart/{userId}/items/{productId}"""
        mock_api = Mock()
        mock_api_class.return_value = mock_api
        mock_api.remove_from_cart.return_value = {'statusCode': 200, 'body': '{}'}
        
        event = {
            'httpMethod': 'DELETE',
            'path': '/api/cart/user123/items/prod456'
        }
        
        response = lambda_handler(event, {})
        
        assert response['statusCode'] == 200
        mock_api.remove_from_cart.assert_called_once_with(event)
    
    @patch('cart_api.ShoppingCartAPI')
    def test_lambda_handler_clear_cart(self, mock_api_class):
        """Test lambda handler for DELETE /cart/{userId}/clear"""
        mock_api = Mock()
        mock_api_class.return_value = mock_api
        mock_api.clear_cart.return_value = {'statusCode': 200, 'body': '{}'}
        
        event = {
            'httpMethod': 'DELETE',
            'path': '/api/cart/user123/clear'
        }
        
        response = lambda_handler(event, {})
        
        assert response['statusCode'] == 200
        mock_api.clear_cart.assert_called_once_with(event)
    
    def test_lambda_handler_options_request(self):
        """Test lambda handler for OPTIONS request (CORS)"""
        event = {
            'httpMethod': 'OPTIONS',
            'path': '/api/cart/user123'
        }
        
        response = lambda_handler(event, {})
        
        assert response['statusCode'] == 200
        assert 'Access-Control-Allow-Origin' in response['headers']
        assert 'Access-Control-Allow-Methods' in response['headers']
    
    def test_lambda_handler_method_not_allowed(self):
        """Test lambda handler for unsupported HTTP method"""
        event = {
            'httpMethod': 'PATCH',
            'path': '/api/cart/user123'
        }
        
        response = lambda_handler(event, {})
        
        assert response['statusCode'] == 405
        body = json.loads(response['body'])
        assert 'Method not allowed' in body['error']
    
    @patch('cart_api.ShoppingCartAPI')
    def test_lambda_handler_exception(self, mock_api_class):
        """Test lambda handler with unhandled exception"""
        mock_api_class.side_effect = Exception('Test exception')
        
        event = {
            'httpMethod': 'GET',
            'path': '/api/cart/user123'
        }
        
        response = lambda_handler(event, {})
        
        assert response['statusCode'] == 500
        body = json.loads(response['body'])
        assert 'Internal server error' in body['error']

if __name__ == '__main__':
    pytest.main([__file__])