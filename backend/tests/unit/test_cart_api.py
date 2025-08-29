"""
Unit tests for Shopping Cart API Lambda function
Tests cart operations, inventory validation, and error handling
"""
import pytest
import json
import unittest.mock as mock
from unittest.mock import MagicMock, patch, Mock
from datetime import datetime, timedelta
from decimal import Decimal
import sys
import os
from botocore.exceptions import ClientError

# Add the functions directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'functions'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'shared'))

# Mock the shared modules before importing
with patch.dict('sys.modules', {
    'database': MagicMock(),
    'config': MagicMock()
}):
    from cart_api import ShoppingCartAPI, lambda_handler

class TestShoppingCartAPI:
    """Test cases for ShoppingCartAPI class"""
    
    def setup_method(self):
        """Set up test fixtures"""
        self.mock_cart_table = MagicMock()
        self.mock_inventory_table = MagicMock()
        self.mock_products_collection = MagicMock()
        
        with patch('cart_api.get_dynamodb_table') as mock_get_table, \
             patch('cart_api.get_documentdb_collection') as mock_get_collection:
            
            mock_get_table.side_effect = lambda name: {
                'shopping_cart': self.mock_cart_table,
                'inventory': self.mock_inventory_table
            }.get(name, MagicMock())
            
            mock_get_collection.return_value = self.mock_products_collection
            
            self.api = ShoppingCartAPI()
    
    def test_get_cart_success(self):
        """Test successful cart retrieval"""
        user_id = 'test_user_123'
        mock_cart_items = [
            {
                'userId': user_id,
                'productId': 'prod_1',
                'quantity': 2,
                'price': Decimal('99.99'),
                'addedAt': datetime.utcnow().isoformat(),
                'updatedAt': datetime.utcnow().isoformat()
            },
            {
                'userId': user_id,
                'productId': 'prod_2',
                'quantity': 1,
                'price': Decimal('49.99'),
                'addedAt': datetime.utcnow().isoformat(),
                'updatedAt': datetime.utcnow().isoformat()
            }
        ]
        
        # Mock DynamoDB response
        self.mock_cart_table.query.return_value = {'Items': mock_cart_items}
        
        # Mock product enrichment
        with patch.object(self.api, '_enrich_cart_item') as mock_enrich:
            mock_enrich.side_effect = [
                {
                    'productId': 'prod_1',
                    'title': 'Product 1',
                    'quantity': 2,
                    'price': 99.99,
                    'subtotal': 199.98
                },
                {
                    'productId': 'prod_2',
                    'title': 'Product 2',
                    'quantity': 1,
                    'price': 49.99,
                    'subtotal': 49.99
                }
            ]
            
            with patch('cart_api.cache_get', return_value=None), \
                 patch('cart_api.cache_set'):
                
                event = {'pathParameters': {'userId': user_id}}
                result = self.api.get_cart(event)
                
                assert result['statusCode'] == 200
                response_body = json.loads(result['body'])
                assert response_body['userId'] == user_id
                assert len(response_body['items']) == 2
                assert response_body['itemCount'] == 2
                assert response_body['totalAmount'] == 249.97
    
    def test_get_cart_cached_result(self):
        """Test returning cached cart"""
        user_id = 'test_user_123'
        cached_data = json.dumps({
            'userId': user_id,
            'items': [],
            'itemCount': 0,
            'totalAmount': 0.0
        })
        
        with patch('cart_api.cache_get', return_value=cached_data):
            event = {'pathParameters': {'userId': user_id}}
            result = self.api.get_cart(event)
            
            assert result['statusCode'] == 200
            # Should not call DynamoDB
            self.mock_cart_table.query.assert_not_called()
    
    def test_get_cart_missing_user_id(self):
        """Test cart retrieval with missing user ID"""
        event = {'pathParameters': {}}
        result = self.api.get_cart(event)
        
        assert result['statusCode'] == 400
        response_body = json.loads(result['body'])
        assert 'Missing user ID' in response_body['error']
    
    def test_get_cart_database_error(self):
        """Test cart retrieval with database error"""
        user_id = 'test_user_123'
        self.mock_cart_table.query.side_effect = ClientError(
            {'Error': {'Code': 'ServiceUnavailable'}}, 'Query'
        )
        
        with patch('cart_api.cache_get', return_value=None):
            event = {'pathParameters': {'userId': user_id}}
            result = self.api.get_cart(event)
            
            assert result['statusCode'] == 500
            response_body = json.loads(result['body'])
            assert 'Database error' in response_body['error']
    
    def test_add_to_cart_success(self):
        """Test successful item addition to cart"""
        user_id = 'test_user_123'
        product_id = 'prod_1'
        
        # Mock product info
        with patch.object(self.api, '_get_product_info') as mock_get_product:
            mock_get_product.return_value = {
                'title': 'Test Product',
                'price': 99.99,
                'image_url': 'test.jpg',
                'category': 'Electronics'
            }
            
            # Mock inventory check
            with patch.object(self.api, '_check_inventory', return_value=10):
                # Mock existing item check (no existing item)
                self.mock_cart_table.get_item.return_value = {}
                
                with patch('cart_api.cache_delete'):
                    event = {
                        'pathParameters': {'userId': user_id},
                        'body': json.dumps({
                            'productId': product_id,
                            'quantity': 2
                        })
                    }
                    
                    result = self.api.add_to_cart(event)
                    
                    assert result['statusCode'] == 200
                    response_body = json.loads(result['body'])
                    assert response_body['productId'] == product_id
                    assert response_body['quantity'] == 2
                    assert response_body['price'] == 99.99
                    assert response_body['subtotal'] == 199.98
                    
                    # Verify DynamoDB put_item was called
                    self.mock_cart_table.put_item.assert_called_once()
    
    def test_add_to_cart_update_existing(self):
        """Test adding to cart when item already exists"""
        user_id = 'test_user_123'
        product_id = 'prod_1'
        
        # Mock existing item
        existing_item = {
            'Item': {
                'userId': user_id,
                'productId': product_id,
                'quantity': 1,
                'price': Decimal('99.99')
            }
        }
        self.mock_cart_table.get_item.return_value = existing_item
        
        with patch.object(self.api, '_get_product_info') as mock_get_product, \
             patch.object(self.api, '_check_inventory', return_value=10), \
             patch('cart_api.cache_delete'):
            
            mock_get_product.return_value = {
                'title': 'Test Product',
                'price': 99.99
            }
            
            event = {
                'pathParameters': {'userId': user_id},
                'body': json.dumps({
                    'productId': product_id,
                    'quantity': 2
                })
            }
            
            result = self.api.add_to_cart(event)
            
            assert result['statusCode'] == 200
            response_body = json.loads(result['body'])
            assert response_body['quantity'] == 3  # 1 existing + 2 new
            
            # Verify DynamoDB update_item was called
            self.mock_cart_table.update_item.assert_called_once()
    
    def test_add_to_cart_insufficient_inventory(self):
        """Test adding to cart with insufficient inventory"""
        user_id = 'test_user_123'
        product_id = 'prod_1'
        
        with patch.object(self.api, '_get_product_info') as mock_get_product, \
             patch.object(self.api, '_check_inventory', return_value=1):  # Only 1 available
            
            mock_get_product.return_value = {'title': 'Test Product', 'price': 99.99}
            
            event = {
                'pathParameters': {'userId': user_id},
                'body': json.dumps({
                    'productId': product_id,
                    'quantity': 5  # Requesting more than available
                })
            }
            
            result = self.api.add_to_cart(event)
            
            assert result['statusCode'] == 400
            response_body = json.loads(result['body'])
            assert 'Insufficient inventory' in response_body['error']
    
    def test_add_to_cart_product_not_found(self):
        """Test adding non-existent product to cart"""
        user_id = 'test_user_123'
        product_id = 'nonexistent_prod'
        
        with patch.object(self.api, '_get_product_info', return_value=None):
            event = {
                'pathParameters': {'userId': user_id},
                'body': json.dumps({
                    'productId': product_id,
                    'quantity': 1
                })
            }
            
            result = self.api.add_to_cart(event)
            
            assert result['statusCode'] == 404
            response_body = json.loads(result['body'])
            assert 'Product not found' in response_body['error']
    
    def test_add_to_cart_invalid_quantity(self):
        """Test adding to cart with invalid quantity"""
        user_id = 'test_user_123'
        
        event = {
            'pathParameters': {'userId': user_id},
            'body': json.dumps({
                'productId': 'prod_1',
                'quantity': -1  # Invalid quantity
            })
        }
        
        result = self.api.add_to_cart(event)
        
        assert result['statusCode'] == 400
        response_body = json.loads(result['body'])
        assert 'Invalid quantity' in response_body['error']
    
    def test_add_to_cart_invalid_json(self):
        """Test adding to cart with invalid JSON"""
        user_id = 'test_user_123'
        
        event = {
            'pathParameters': {'userId': user_id},
            'body': 'invalid json'
        }
        
        result = self.api.add_to_cart(event)
        
        assert result['statusCode'] == 400
        response_body = json.loads(result['body'])
        assert 'Invalid JSON' in response_body['error']
    
    def test_update_cart_item_success(self):
        """Test successful cart item update"""
        user_id = 'test_user_123'
        product_id = 'prod_1'
        
        with patch.object(self.api, '_check_inventory', return_value=10), \
             patch.object(self.api, '_get_product_info') as mock_get_product, \
             patch('cart_api.cache_delete'):
            
            mock_get_product.return_value = {'title': 'Test Product', 'price': 99.99}
            
            # Mock successful update
            self.mock_cart_table.update_item.return_value = {
                'Attributes': {
                    'userId': user_id,
                    'productId': product_id,
                    'quantity': 3,
                    'price': Decimal('99.99')
                }
            }
            
            event = {
                'pathParameters': {'userId': user_id, 'productId': product_id},
                'body': json.dumps({'quantity': 3})
            }
            
            result = self.api.update_cart_item(event)
            
            assert result['statusCode'] == 200
            response_body = json.loads(result['body'])
            assert response_body['quantity'] == 3
            assert response_body['subtotal'] == 299.97
    
    def test_update_cart_item_zero_quantity(self):
        """Test updating cart item with zero quantity (should remove)"""
        user_id = 'test_user_123'
        product_id = 'prod_1'
        
        with patch.object(self.api, 'remove_from_cart') as mock_remove:
            mock_remove.return_value = {
                'statusCode': 200,
                'body': json.dumps({'message': 'Item removed'})
            }
            
            event = {
                'pathParameters': {'userId': user_id, 'productId': product_id},
                'body': json.dumps({'quantity': 0})
            }
            
            result = self.api.update_cart_item(event)
            
            assert result['statusCode'] == 200
            mock_remove.assert_called_once_with(event)
    
    def test_update_cart_item_not_found(self):
        """Test updating non-existent cart item"""
        user_id = 'test_user_123'
        product_id = 'prod_1'
        
        # Mock conditional check failure
        self.mock_cart_table.update_item.side_effect = ClientError(
            {'Error': {'Code': 'ConditionalCheckFailedException'}}, 'UpdateItem'
        )
        
        with patch.object(self.api, '_check_inventory', return_value=10), \
             patch.object(self.api, '_get_product_info', return_value={'price': 99.99}):
            
            event = {
                'pathParameters': {'userId': user_id, 'productId': product_id},
                'body': json.dumps({'quantity': 2})
            }
            
            result = self.api.update_cart_item(event)
            
            assert result['statusCode'] == 404
            response_body = json.loads(result['body'])
            assert 'Item not found' in response_body['error']
    
    def test_remove_from_cart_success(self):
        """Test successful item removal from cart"""
        user_id = 'test_user_123'
        product_id = 'prod_1'
        
        with patch('cart_api.cache_delete'):
            event = {
                'pathParameters': {'userId': user_id, 'productId': product_id}
            }
            
            result = self.api.remove_from_cart(event)
            
            assert result['statusCode'] == 200
            response_body = json.loads(result['body'])
            assert 'Item removed from cart successfully' in response_body['message']
            assert response_body['productId'] == product_id
            
            # Verify DynamoDB delete_item was called
            self.mock_cart_table.delete_item.assert_called_once()
    
    def test_remove_from_cart_item_not_found(self):
        """Test removing non-existent cart item"""
        user_id = 'test_user_123'
        product_id = 'prod_1'
        
        # Mock conditional check failure
        self.mock_cart_table.delete_item.side_effect = ClientError(
            {'Error': {'Code': 'ConditionalCheckFailedException'}}, 'DeleteItem'
        )
        
        event = {
            'pathParameters': {'userId': user_id, 'productId': product_id}
        }
        
        result = self.api.remove_from_cart(event)
        
        assert result['statusCode'] == 404
        response_body = json.loads(result['body'])
        assert 'Item not found' in response_body['error']
    
    def test_clear_cart_success(self):
        """Test successful cart clearing"""
        user_id = 'test_user_123'
        mock_cart_items = [
            {'userId': user_id, 'productId': 'prod_1'},
            {'userId': user_id, 'productId': 'prod_2'}
        ]
        
        self.mock_cart_table.query.return_value = {'Items': mock_cart_items}
        
        with patch('cart_api.cache_delete'):
            event = {'pathParameters': {'userId': user_id}}
            result = self.api.clear_cart(event)
            
            assert result['statusCode'] == 200
            response_body = json.loads(result['body'])
            assert 'Cart cleared successfully' in response_body['message']
            assert response_body['itemsRemoved'] == 2
            
            # Verify delete_item was called for each item
            assert self.mock_cart_table.delete_item.call_count == 2
    
    def test_enrich_cart_item_success(self):
        """Test successful cart item enrichment"""
        cart_item = {
            'productId': 'prod_1',
            'quantity': 2,
            'price': Decimal('99.99'),
            'addedAt': datetime.utcnow().isoformat(),
            'updatedAt': datetime.utcnow().isoformat()
        }
        
        with patch.object(self.api, '_get_product_info') as mock_get_product, \
             patch.object(self.api, '_check_inventory', return_value=5):
            
            mock_get_product.return_value = {
                'title': 'Test Product',
                'price': 99.99,
                'image_url': 'test.jpg',
                'category': 'Electronics'
            }
            
            result = self.api._enrich_cart_item(cart_item)
            
            assert result is not None
            assert result['productId'] == 'prod_1'
            assert result['title'] == 'Test Product'
            assert result['quantity'] == 2
            assert result['subtotal'] == 199.98
            assert result['inStock'] is True
            assert result['availableQuantity'] == 5
            assert result['inventoryStatus'] == 'in_stock'
    
    def test_enrich_cart_item_product_not_found(self):
        """Test cart item enrichment when product doesn't exist"""
        cart_item = {
            'productId': 'nonexistent_prod',
            'quantity': 1,
            'price': Decimal('99.99')
        }
        
        with patch.object(self.api, '_get_product_info', return_value=None):
            result = self.api._enrich_cart_item(cart_item)
            
            assert result is None
    
    def test_enrich_cart_item_price_changed(self):
        """Test cart item enrichment with price change"""
        cart_item = {
            'productId': 'prod_1',
            'quantity': 1,
            'price': Decimal('99.99')  # Original price
        }
        
        with patch.object(self.api, '_get_product_info') as mock_get_product, \
             patch.object(self.api, '_check_inventory', return_value=10):
            
            mock_get_product.return_value = {
                'title': 'Test Product',
                'price': 89.99,  # New lower price
                'image_url': 'test.jpg',
                'category': 'Electronics'
            }
            
            result = self.api._enrich_cart_item(cart_item)
            
            assert result['price'] == 89.99
            assert result['originalPrice'] == 99.99
            assert result['priceChanged'] is True
    
    def test_get_product_info_success(self):
        """Test successful product info retrieval"""
        product_id = 'prod_1'
        mock_product = {
            'title': 'Test Product',
            'price': 99.99,
            'image_url': 'test.jpg',
            'category': 'Electronics',
            'in_stock': True
        }
        
        self.mock_products_collection.find_one.return_value = mock_product
        
        result = self.api._get_product_info(product_id)
        
        assert result is not None
        assert result['title'] == 'Test Product'
        assert result['price'] == 99.99
    
    def test_get_product_info_not_found(self):
        """Test product info retrieval when product doesn't exist"""
        self.mock_products_collection.find_one.return_value = None
        
        result = self.api._get_product_info('nonexistent_prod')
        
        assert result is None
    
    def test_check_inventory_success(self):
        """Test successful inventory check"""
        product_id = 'prod_1'
        self.mock_inventory_table.get_item.return_value = {
            'Item': {'productId': product_id, 'availableQuantity': 10}
        }
        
        result = self.api._check_inventory(product_id)
        
        assert result == 10
    
    def test_check_inventory_not_found(self):
        """Test inventory check when product not found"""
        self.mock_inventory_table.get_item.return_value = {}
        
        result = self.api._check_inventory('nonexistent_prod')
        
        assert result == 0
    
    def test_get_inventory_status(self):
        """Test inventory status determination"""
        assert self.api._get_inventory_status(0, 1) == 'out_of_stock'
        assert self.api._get_inventory_status(2, 5) == 'insufficient_stock'
        assert self.api._get_inventory_status(3, 2) == 'low_stock'
        assert self.api._get_inventory_status(10, 2) == 'in_stock'


class TestCartAPILambdaHandler:
    """Test cases for lambda_handler function"""
    
    def test_lambda_handler_options_request(self):
        """Test lambda handler for OPTIONS request (CORS)"""
        event = {'httpMethod': 'OPTIONS'}
        context = MagicMock()
        
        result = lambda_handler(event, context)
        
        assert result['statusCode'] == 200
        assert 'Access-Control-Allow-Origin' in result['headers']
        assert 'Access-Control-Allow-Methods' in result['headers']
    
    def test_lambda_handler_get_cart(self):
        """Test lambda handler for GET cart"""
        with patch('cart_api.cart_api') as mock_api:
            mock_api.get_cart.return_value = {
                'statusCode': 200,
                'body': json.dumps({'items': []})
            }
            
            event = {
                'httpMethod': 'GET',
                'path': '/cart/user123'
            }
            context = MagicMock()
            
            result = lambda_handler(event, context)
            
            assert result['statusCode'] == 200
            mock_api.get_cart.assert_called_once_with(event)
    
    def test_lambda_handler_add_to_cart(self):
        """Test lambda handler for POST add to cart"""
        with patch('cart_api.cart_api') as mock_api:
            mock_api.add_to_cart.return_value = {
                'statusCode': 200,
                'body': json.dumps({'message': 'Item added'})
            }
            
            event = {
                'httpMethod': 'POST',
                'path': '/cart/user123/items',
                'body': json.dumps({'productId': 'prod_1', 'quantity': 1})
            }
            context = MagicMock()
            
            result = lambda_handler(event, context)
            
            assert result['statusCode'] == 200
            mock_api.add_to_cart.assert_called_once_with(event)
    
    def test_lambda_handler_update_cart_item(self):
        """Test lambda handler for PUT update cart item"""
        with patch('cart_api.cart_api') as mock_api:
            mock_api.update_cart_item.return_value = {
                'statusCode': 200,
                'body': json.dumps({'message': 'Item updated'})
            }
            
            event = {
                'httpMethod': 'PUT',
                'path': '/cart/user123/items/prod_1',
                'body': json.dumps({'quantity': 2})
            }
            context = MagicMock()
            
            result = lambda_handler(event, context)
            
            assert result['statusCode'] == 200
            mock_api.update_cart_item.assert_called_once_with(event)
    
    def test_lambda_handler_remove_cart_item(self):
        """Test lambda handler for DELETE cart item"""
        with patch('cart_api.cart_api') as mock_api:
            mock_api.remove_from_cart.return_value = {
                'statusCode': 200,
                'body': json.dumps({'message': 'Item removed'})
            }
            
            event = {
                'httpMethod': 'DELETE',
                'path': '/cart/user123/items/prod_1'
            }
            context = MagicMock()
            
            result = lambda_handler(event, context)
            
            assert result['statusCode'] == 200
            mock_api.remove_from_cart.assert_called_once_with(event)
    
    def test_lambda_handler_clear_cart(self):
        """Test lambda handler for DELETE clear cart"""
        with patch('cart_api.cart_api') as mock_api:
            mock_api.clear_cart.return_value = {
                'statusCode': 200,
                'body': json.dumps({'message': 'Cart cleared'})
            }
            
            event = {
                'httpMethod': 'DELETE',
                'path': '/cart/user123/clear'
            }
            context = MagicMock()
            
            result = lambda_handler(event, context)
            
            assert result['statusCode'] == 200
            mock_api.clear_cart.assert_called_once_with(event)
    
    def test_lambda_handler_unsupported_method(self):
        """Test lambda handler with unsupported method"""
        event = {
            'httpMethod': 'PATCH',
            'path': '/cart/user123'
        }
        context = MagicMock()
        
        result = lambda_handler(event, context)
        
        assert result['statusCode'] == 405
        response_body = json.loads(result['body'])
        assert 'Method not allowed' in response_body['error']
    
    def test_lambda_handler_exception_handling(self):
        """Test lambda handler exception handling"""
        with patch('cart_api.cart_api') as mock_api:
            mock_api.get_cart.side_effect = Exception("Database error")
            
            event = {
                'httpMethod': 'GET',
                'path': '/cart/user123'
            }
            context = MagicMock()
            
            result = lambda_handler(event, context)
            
            assert result['statusCode'] == 500
            response_body = json.loads(result['body'])
            assert 'Internal server error' in response_body['error']


if __name__ == '__main__':
    pytest.main([__file__])