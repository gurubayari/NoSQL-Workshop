"""
Unit tests for Order Management API Lambda function
"""
import pytest
import json
from unittest.mock import Mock, patch, MagicMock
from decimal import Decimal
from datetime import datetime
import sys
import os
from botocore.exceptions import ClientError

# Add the functions directory to the path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'functions'))
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'shared'))

from order_api import OrderManagementAPI, lambda_handler

class TestOrderManagementAPI:
    """Test cases for OrderManagementAPI class"""
    
    @pytest.fixture
    def order_api(self):
        """Create OrderManagementAPI instance with mocked dependencies"""
        with patch('order_api.get_dynamodb_table') as mock_table:
            with patch('order_api.get_documentdb_collection') as mock_collection:
                with patch('order_api.db') as mock_db:
                    api = OrderManagementAPI()
                    api.orders_table = Mock()
                    api.cart_table = Mock()
                    api.inventory_table = Mock()
                    api.users_table = Mock()
                    api.products_collection = Mock()
                    api.dynamodb = Mock()
                    return api
    
    @pytest.fixture
    def sample_order_request(self):
        """Sample order creation request"""
        return {
            'httpMethod': 'POST',
            'path': '/api/orders',
            'body': json.dumps({
                'userId': 'user123',
                'items': [
                    {'productId': 'prod456', 'quantity': 2},
                    {'productId': 'prod789', 'quantity': 1}
                ],
                'paymentMethod': {
                    'type': 'credit_card',
                    'cardNumber': '1234567890123456',
                    'expiryMonth': '12',
                    'expiryYear': '2025',
                    'cvv': '123'
                },
                'shippingAddress': {
                    'name': 'John Doe',
                    'street': '123 Main St',
                    'city': 'Seattle',
                    'state': 'WA',
                    'zipCode': '98101',
                    'country': 'US'
                },
                'billingAddress': {
                    'name': 'John Doe',
                    'street': '123 Main St',
                    'city': 'Seattle',
                    'state': 'WA',
                    'zipCode': '98101',
                    'country': 'US'
                }
            })
        }
    
    @pytest.fixture
    def sample_order(self):
        """Sample order data"""
        return {
            'orderId': 'ORD-12345678',
            'userId': 'user123',
            'status': 'confirmed',
            'items': [
                {
                    'productId': 'prod456',
                    'title': 'Wireless Headphones',
                    'price': 99.99,
                    'quantity': 2,
                    'subtotal': 199.98
                }
            ],
            'subtotal': 199.98,
            'taxAmount': 12.00,
            'shippingAmount': 0.00,
            'totalAmount': 211.98,
            'orderDate': '2024-01-01T10:00:00Z',
            'createdAt': '2024-01-01T10:00:00Z',
            'updatedAt': '2024-01-01T10:00:00Z'
        }
    
    @pytest.fixture
    def sample_product(self):
        """Sample product data"""
        return {
            '_id': 'prod456',
            'title': 'Wireless Headphones',
            'price': 99.99,
            'image_url': 'https://example.com/image.jpg',
            'category': 'Electronics',
            'in_stock': True
        }
    
    @patch('order_api.uuid.uuid4')
    def test_create_order_success(self, mock_uuid, order_api, sample_order_request, sample_product):
        """Test successful order creation"""
        # Mock UUID generation
        mock_uuid.return_value.hex = '12345678abcdef'
        
        # Mock product info
        with patch.object(order_api, '_get_product_info') as mock_product:
            mock_product.return_value = sample_product
            
            # Mock inventory check
            with patch.object(order_api, '_check_inventory') as mock_inventory:
                mock_inventory.return_value = 10
                
                # Mock payment processing
                with patch.object(order_api, '_process_payment') as mock_payment:
                    mock_payment.return_value = {
                        'success': True,
                        'paymentId': 'PAY-123456789',
                        'message': 'Payment processed'
                    }
                    
                    # Mock transaction execution
                    with patch.object(order_api, '_execute_order_transaction') as mock_transaction:
                        mock_transaction.return_value = None
                        
                        # Mock cart clearing
                        with patch.object(order_api, '_clear_user_cart') as mock_clear_cart:
                            mock_clear_cart.return_value = None
                            
                            # Mock cache invalidation
                            with patch.object(order_api, '_invalidate_caches') as mock_invalidate:
                                mock_invalidate.return_value = None
                                
                                # Call the method
                                response = order_api.create_order(sample_order_request)
        
        # Assertions
        assert response['statusCode'] == 201
        body = json.loads(response['body'])
        assert 'orderId' in body
        assert body['status'] == 'confirmed'
        assert 'totalAmount' in body
        assert 'trackingNumber' in body
        
        # Verify methods were called
        mock_transaction.assert_called_once()
        mock_clear_cart.assert_called_once_with('user123')
        mock_invalidate.assert_called_once_with('user123')
    
    def test_create_order_missing_user_id(self, order_api):
        """Test order creation without user ID"""
        event = {
            'httpMethod': 'POST',
            'path': '/api/orders',
            'body': json.dumps({
                'items': [{'productId': 'prod456', 'quantity': 1}]
            })
        }
        
        response = order_api.create_order(event)
        
        assert response['statusCode'] == 400
        body = json.loads(response['body'])
        assert 'Missing user ID' in body['error']
    
    def test_create_order_missing_items(self, order_api):
        """Test order creation without items"""
        event = {
            'httpMethod': 'POST',
            'path': '/api/orders',
            'body': json.dumps({
                'userId': 'user123',
                'paymentMethod': {'type': 'credit_card'},
                'shippingAddress': {'street': '123 Main St'}
            })
        }
        
        response = order_api.create_order(event)
        
        assert response['statusCode'] == 400
        body = json.loads(response['body'])
        assert 'Missing items' in body['error']
    
    def test_create_order_payment_failure(self, order_api, sample_order_request, sample_product):
        """Test order creation with payment failure"""
        # Mock product info and inventory
        with patch.object(order_api, '_get_product_info') as mock_product:
            mock_product.return_value = sample_product
            
            with patch.object(order_api, '_check_inventory') as mock_inventory:
                mock_inventory.return_value = 10
                
                # Mock payment processing failure
                with patch.object(order_api, '_process_payment') as mock_payment:
                    mock_payment.return_value = {
                        'success': False,
                        'message': 'Invalid card number'
                    }
                    
                    response = order_api.create_order(sample_order_request)
        
        assert response['statusCode'] == 400
        body = json.loads(response['body'])
        assert 'Payment failed' in body['error']
    
    def test_create_order_inventory_conflict(self, order_api, sample_order_request, sample_product):
        """Test order creation with inventory conflict during transaction"""
        # Mock product info and inventory
        with patch.object(order_api, '_get_product_info') as mock_product:
            mock_product.return_value = sample_product
            
            with patch.object(order_api, '_check_inventory') as mock_inventory:
                mock_inventory.return_value = 10
                
                # Mock payment processing
                with patch.object(order_api, '_process_payment') as mock_payment:
                    mock_payment.return_value = {
                        'success': True,
                        'paymentId': 'PAY-123456789'
                    }
                    
                    # Mock transaction failure
                    with patch.object(order_api, '_execute_order_transaction') as mock_transaction:
                        error = ClientError(
                            {'Error': {'Code': 'ConditionalCheckFailedException'}},
                            'TransactWriteItems'
                        )
                        mock_transaction.side_effect = error
                        
                        response = order_api.create_order(sample_order_request)
        
        assert response['statusCode'] == 409
        body = json.loads(response['body'])
        assert 'Inventory conflict' in body['error']
    
    @patch('order_api.cache_get')
    @patch('order_api.cache_set')
    def test_get_order_success(self, mock_cache_set, mock_cache_get, order_api, sample_order):
        """Test successful order retrieval"""
        # Mock cache miss
        mock_cache_get.return_value = None
        
        # Mock DynamoDB response
        order_api.orders_table.get_item.return_value = {'Item': sample_order}
        
        # Mock order enrichment
        with patch.object(order_api, '_enrich_order_with_product_info') as mock_enrich:
            mock_enrich.return_value = sample_order
            
            event = {
                'httpMethod': 'GET',
                'path': '/api/orders/ORD-12345678',
                'pathParameters': {'orderId': 'ORD-12345678'}
            }
            
            response = order_api.get_order(event)
        
        # Assertions
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['orderId'] == 'ORD-12345678'
        assert body['status'] == 'confirmed'
        
        # Verify database query
        order_api.orders_table.get_item.assert_called_once()
        
        # Verify caching
        mock_cache_set.assert_called_once()
    
    @patch('order_api.cache_get')
    def test_get_order_cached_response(self, mock_cache_get, order_api):
        """Test cached response for order retrieval"""
        # Mock cache hit
        cached_response = json.dumps({'orderId': 'ORD-12345678', 'status': 'confirmed'})
        mock_cache_get.return_value = cached_response
        
        event = {
            'httpMethod': 'GET',
            'path': '/api/orders/ORD-12345678',
            'pathParameters': {'orderId': 'ORD-12345678'}
        }
        
        response = order_api.get_order(event)
        
        # Assertions
        assert response['statusCode'] == 200
        assert response['body'] == cached_response
        
        # Verify database was not called
        order_api.orders_table.get_item.assert_not_called()
    
    def test_get_order_not_found(self, order_api):
        """Test order retrieval for non-existent order"""
        # Mock DynamoDB response (not found)
        order_api.orders_table.get_item.return_value = {}
        
        event = {
            'httpMethod': 'GET',
            'path': '/api/orders/nonexistent',
            'pathParameters': {'orderId': 'nonexistent'}
        }
        
        response = order_api.get_order(event)
        
        assert response['statusCode'] == 404
        body = json.loads(response['body'])
        assert 'Order not found' in body['error']
    
    def test_get_order_missing_id(self, order_api):
        """Test order retrieval without order ID"""
        event = {
            'httpMethod': 'GET',
            'path': '/api/orders/',
            'pathParameters': {}
        }
        
        response = order_api.get_order(event)
        
        assert response['statusCode'] == 400
        body = json.loads(response['body'])
        assert 'Missing order ID' in body['error']
    
    @patch('order_api.cache_get')
    @patch('order_api.cache_set')
    def test_get_user_orders_success(self, mock_cache_set, mock_cache_get, order_api, sample_order):
        """Test successful user orders retrieval"""
        # Mock cache miss
        mock_cache_get.return_value = None
        
        # Mock DynamoDB response
        order_api.orders_table.query.return_value = {'Items': [sample_order]}
        
        event = {
            'httpMethod': 'GET',
            'path': '/api/users/user123/orders',
            'pathParameters': {'userId': 'user123'},
            'queryStringParameters': {'page': '1', 'limit': '10'}
        }
        
        response = order_api.get_user_orders(event)
        
        # Assertions
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert 'orders' in body
        assert 'pagination' in body
        assert len(body['orders']) == 1
        
        # Verify database query
        order_api.orders_table.query.assert_called_once()
        
        # Verify caching
        mock_cache_set.assert_called_once()
    
    def test_get_user_orders_with_filters(self, order_api, sample_order):
        """Test user orders retrieval with status filter"""
        # Mock DynamoDB response
        order_api.orders_table.query.return_value = {'Items': [sample_order]}
        
        event = {
            'httpMethod': 'GET',
            'path': '/api/users/user123/orders',
            'pathParameters': {'userId': 'user123'},
            'queryStringParameters': {
                'status': 'confirmed',
                'startDate': '2024-01-01',
                'endDate': '2024-01-31'
            }
        }
        
        response = order_api.get_user_orders(event)
        
        # Assertions
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['filters_applied']['status'] == 'confirmed'
        assert body['filters_applied']['start_date'] == '2024-01-01'
        assert body['filters_applied']['end_date'] == '2024-01-31'
    
    @patch('order_api.cache_delete')
    def test_update_order_status_success(self, mock_cache_delete, order_api, sample_order):
        """Test successful order status update"""
        # Mock DynamoDB response
        updated_order = sample_order.copy()
        updated_order['status'] = 'shipped'
        updated_order['trackingNumber'] = 'TRK123456789'
        
        order_api.orders_table.update_item.return_value = {'Attributes': updated_order}
        
        event = {
            'httpMethod': 'PUT',
            'path': '/api/orders/ORD-12345678',
            'pathParameters': {'orderId': 'ORD-12345678'},
            'body': json.dumps({
                'status': 'shipped',
                'trackingNumber': 'TRK123456789'
            })
        }
        
        response = order_api.update_order_status(event)
        
        # Assertions
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['status'] == 'shipped'
        assert body['trackingNumber'] == 'TRK123456789'
        
        # Verify database update
        order_api.orders_table.update_item.assert_called_once()
        
        # Verify cache invalidation
        mock_cache_delete.assert_called_once()
    
    def test_update_order_status_invalid_status(self, order_api):
        """Test order status update with invalid status"""
        event = {
            'httpMethod': 'PUT',
            'path': '/api/orders/ORD-12345678',
            'pathParameters': {'orderId': 'ORD-12345678'},
            'body': json.dumps({'status': 'invalid_status'})
        }
        
        response = order_api.update_order_status(event)
        
        assert response['statusCode'] == 400
        body = json.loads(response['body'])
        assert 'Invalid status' in body['error']
    
    def test_update_order_status_not_found(self, order_api):
        """Test updating non-existent order status"""
        # Mock DynamoDB error
        error = ClientError(
            {'Error': {'Code': 'ConditionalCheckFailedException'}},
            'UpdateItem'
        )
        order_api.orders_table.update_item.side_effect = error
        
        event = {
            'httpMethod': 'PUT',
            'path': '/api/orders/nonexistent',
            'pathParameters': {'orderId': 'nonexistent'},
            'body': json.dumps({'status': 'shipped'})
        }
        
        response = order_api.update_order_status(event)
        
        assert response['statusCode'] == 404
        body = json.loads(response['body'])
        assert 'Order not found' in body['error']
    
    def test_validate_and_enrich_items_success(self, order_api, sample_product):
        """Test successful item validation and enrichment"""
        items = [
            {'productId': 'prod456', 'quantity': 2},
            {'productId': 'prod789', 'quantity': 1}
        ]
        
        # Mock product info
        with patch.object(order_api, '_get_product_info') as mock_product:
            mock_product.return_value = sample_product
            
            # Mock inventory check
            with patch.object(order_api, '_check_inventory') as mock_inventory:
                mock_inventory.return_value = 10
                
                validated_items, total_amount = order_api._validate_and_enrich_items(items)
        
        # Assertions
        assert len(validated_items) == 2
        assert total_amount == Decimal('299.97')  # 2 * 99.99 + 1 * 99.99
        assert validated_items[0]['productId'] == 'prod456'
        assert validated_items[0]['quantity'] == 2
        assert validated_items[0]['subtotal'] == 199.98
    
    def test_validate_and_enrich_items_insufficient_inventory(self, order_api, sample_product):
        """Test item validation with insufficient inventory"""
        items = [{'productId': 'prod456', 'quantity': 10}]
        
        # Mock product info
        with patch.object(order_api, '_get_product_info') as mock_product:
            mock_product.return_value = sample_product
            
            # Mock inventory check (insufficient)
            with patch.object(order_api, '_check_inventory') as mock_inventory:
                mock_inventory.return_value = 5  # Less than requested
                
                validated_items, total_amount = order_api._validate_and_enrich_items(items)
        
        # Assertions
        assert len(validated_items) == 0  # Item should be skipped
        assert total_amount == Decimal('0')
    
    def test_validate_and_enrich_items_product_not_found(self, order_api):
        """Test item validation with non-existent product"""
        items = [{'productId': 'nonexistent', 'quantity': 1}]
        
        # Mock product info (not found)
        with patch.object(order_api, '_get_product_info') as mock_product:
            mock_product.return_value = None
            
            validated_items, total_amount = order_api._validate_and_enrich_items(items)
        
        # Assertions
        assert len(validated_items) == 0  # Item should be skipped
        assert total_amount == Decimal('0')
    
    def test_execute_order_transaction(self, order_api, sample_order):
        """Test order transaction execution"""
        items = [{'productId': 'prod456', 'quantity': 2}]
        
        # Mock DynamoDB client
        order_api.dynamodb.meta.client.transact_write_items.return_value = {}
        
        # Should not raise exception
        order_api._execute_order_transaction(sample_order, items, 'user123')
        
        # Verify transaction was called
        order_api.dynamodb.meta.client.transact_write_items.assert_called_once()
    
    def test_calculate_tax(self, order_api):
        """Test tax calculation"""
        subtotal = Decimal('100.00')
        
        # Test California tax
        tax = order_api._calculate_tax(subtotal, 'CA')
        assert tax == Decimal('8.75')
        
        # Test default tax
        tax = order_api._calculate_tax(subtotal, 'Unknown')
        assert tax == Decimal('5.00')
    
    def test_calculate_shipping(self, order_api):
        """Test shipping calculation"""
        # Free shipping over $50
        shipping = order_api._calculate_shipping(Decimal('60.00'), {})
        assert shipping == Decimal('0')
        
        # Standard shipping under $50
        shipping = order_api._calculate_shipping(Decimal('30.00'), {})
        assert shipping == Decimal('9.99')
    
    def test_process_payment_success(self, order_api):
        """Test successful payment processing"""
        payment_method = {
            'type': 'credit_card',
            'cardNumber': '1234567890123456'
        }
        
        result = order_api._process_payment(payment_method, Decimal('100.00'))
        
        assert result['success'] is True
        assert 'paymentId' in result
        assert result['paymentId'].startswith('PAY-')
    
    def test_process_payment_invalid_card(self, order_api):
        """Test payment processing with invalid card"""
        payment_method = {
            'type': 'credit_card',
            'cardNumber': '123'  # Too short
        }
        
        result = order_api._process_payment(payment_method, Decimal('100.00'))
        
        assert result['success'] is False
        assert 'Invalid card number' in result['message']
    
    def test_clear_user_cart(self, order_api):
        """Test user cart clearing"""
        # Mock cart items
        cart_items = [
            {'userId': 'user123', 'productId': 'prod456'},
            {'userId': 'user123', 'productId': 'prod789'}
        ]
        
        order_api.cart_table.query.return_value = {'Items': cart_items}
        order_api.cart_table.delete_item.return_value = {}
        
        # Should not raise exception
        order_api._clear_user_cart('user123')
        
        # Verify deletions
        assert order_api.cart_table.delete_item.call_count == 2
    
    def test_enrich_order_with_product_info(self, order_api, sample_order, sample_product):
        """Test order enrichment with product info"""
        # Mock product info
        with patch.object(order_api, '_get_product_info') as mock_product:
            mock_product.return_value = sample_product
            
            enriched_order = order_api._enrich_order_with_product_info(sample_order)
        
        # Assertions
        assert 'items' in enriched_order
        item = enriched_order['items'][0]
        assert 'currentPrice' in item
        assert 'priceChanged' in item
        assert 'stillAvailable' in item

class TestLambdaHandler:
    """Test cases for lambda_handler function"""
    
    @patch('order_api.OrderManagementAPI')
    def test_lambda_handler_create_order(self, mock_api_class):
        """Test lambda handler for POST /orders"""
        mock_api = Mock()
        mock_api_class.return_value = mock_api
        mock_api.create_order.return_value = {'statusCode': 201, 'body': '{}'}
        
        event = {
            'httpMethod': 'POST',
            'path': '/api/orders'
        }
        
        response = lambda_handler(event, {})
        
        assert response['statusCode'] == 201
        mock_api.create_order.assert_called_once_with(event)
    
    @patch('order_api.OrderManagementAPI')
    def test_lambda_handler_get_order(self, mock_api_class):
        """Test lambda handler for GET /orders/{orderId}"""
        mock_api = Mock()
        mock_api_class.return_value = mock_api
        mock_api.get_order.return_value = {'statusCode': 200, 'body': '{}'}
        
        event = {
            'httpMethod': 'GET',
            'path': '/api/orders/ORD-12345678'
        }
        
        response = lambda_handler(event, {})
        
        assert response['statusCode'] == 200
        mock_api.get_order.assert_called_once_with(event)
    
    @patch('order_api.OrderManagementAPI')
    def test_lambda_handler_get_user_orders(self, mock_api_class):
        """Test lambda handler for GET /users/{userId}/orders"""
        mock_api = Mock()
        mock_api_class.return_value = mock_api
        mock_api.get_user_orders.return_value = {'statusCode': 200, 'body': '{}'}
        
        event = {
            'httpMethod': 'GET',
            'path': '/api/users/user123/orders'
        }
        
        response = lambda_handler(event, {})
        
        assert response['statusCode'] == 200
        mock_api.get_user_orders.assert_called_once_with(event)
    
    @patch('order_api.OrderManagementAPI')
    def test_lambda_handler_update_order_status(self, mock_api_class):
        """Test lambda handler for PUT /orders/{orderId}"""
        mock_api = Mock()
        mock_api_class.return_value = mock_api
        mock_api.update_order_status.return_value = {'statusCode': 200, 'body': '{}'}
        
        event = {
            'httpMethod': 'PUT',
            'path': '/api/orders/ORD-12345678'
        }
        
        response = lambda_handler(event, {})
        
        assert response['statusCode'] == 200
        mock_api.update_order_status.assert_called_once_with(event)
    
    def test_lambda_handler_options_request(self):
        """Test lambda handler for OPTIONS request (CORS)"""
        event = {
            'httpMethod': 'OPTIONS',
            'path': '/api/orders'
        }
        
        response = lambda_handler(event, {})
        
        assert response['statusCode'] == 200
        assert 'Access-Control-Allow-Origin' in response['headers']
        assert 'Access-Control-Allow-Methods' in response['headers']
    
    def test_lambda_handler_method_not_allowed(self):
        """Test lambda handler for unsupported HTTP method"""
        event = {
            'httpMethod': 'PATCH',
            'path': '/api/orders'
        }
        
        response = lambda_handler(event, {})
        
        assert response['statusCode'] == 405
        body = json.loads(response['body'])
        assert 'Method not allowed' in body['error']
    
    @patch('order_api.OrderManagementAPI')
    def test_lambda_handler_exception(self, mock_api_class):
        """Test lambda handler with unhandled exception"""
        mock_api_class.side_effect = Exception('Test exception')
        
        event = {
            'httpMethod': 'POST',
            'path': '/api/orders'
        }
        
        response = lambda_handler(event, {})
        
        assert response['statusCode'] == 500
        body = json.loads(response['body'])
        assert 'Internal server error' in body['error']

if __name__ == '__main__':
    pytest.main([__file__])