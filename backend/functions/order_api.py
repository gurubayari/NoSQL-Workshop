"""
Order Management API Lambda function for Unicorn E-Commerce
Handles order creation, retrieval, and status management with DynamoDB transactions
"""
import json
import logging
import traceback
import uuid
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from decimal import Decimal
import boto3
from botocore.exceptions import ClientError

# Import shared utilities
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'shared'))

from database import (
    get_dynamodb_table,
    get_documentdb_collection,
    cache_get,
    cache_set,
    cache_delete,
    get_cache_key,
    db
)
from config import config

# Configure logging
logger = logging.getLogger()
logger.setLevel(getattr(logging, config.LOG_LEVEL))

class OrderAPIError(Exception):
    """Custom exception for Order API errors"""
    pass

class OrderManagementAPI:
    """Order Management API handler class"""
    
    def __init__(self):
        self.orders_table = get_dynamodb_table(config.ORDERS_TABLE)
        self.cart_table = get_dynamodb_table(config.SHOPPING_CART_TABLE)
        self.inventory_table = get_dynamodb_table(config.INVENTORY_TABLE)
        self.users_table = get_dynamodb_table(config.USERS_TABLE)
        self.products_collection = get_documentdb_collection('products')
        self.dynamodb = db.dynamodb
    
    def create_order(self, event: Dict) -> Dict:
        """
        Create a new order with atomic inventory deduction using DynamoDB transactions
        Validates inventory, processes payment, and creates order record
        """
        try:
            # Parse request body
            try:
                body = json.loads(event.get('body', '{}'))
            except json.JSONDecodeError:
                return self._error_response(400, 'Invalid JSON', 'Request body must be valid JSON')
            
            user_id = body.get('userId')
            payment_method = body.get('paymentMethod', {})
            shipping_address = body.get('shippingAddress', {})
            billing_address = body.get('billingAddress', {})
            items = body.get('items', [])
            
            if not user_id:
                return self._error_response(400, 'Missing user ID', 'User ID is required')
            
            if not items:
                return self._error_response(400, 'Missing items', 'Order items are required')
            
            if not payment_method:
                return self._error_response(400, 'Missing payment method', 'Payment method is required')
            
            if not shipping_address:
                return self._error_response(400, 'Missing shipping address', 'Shipping address is required')
            
            # Validate and enrich order items
            validated_items, total_amount = self._validate_and_enrich_items(items)
            if not validated_items:
                return self._error_response(400, 'Invalid items', 'No valid items found in order')
            
            # Generate order ID
            order_id = f"ORD-{uuid.uuid4().hex[:8].upper()}"
            
            # Calculate taxes and shipping
            tax_amount = self._calculate_tax(total_amount, shipping_address.get('state'))
            shipping_amount = self._calculate_shipping(total_amount, shipping_address)
            final_amount = total_amount + tax_amount + shipping_amount
            
            # Process payment (mock implementation)
            payment_result = self._process_payment(payment_method, final_amount)
            if not payment_result['success']:
                return self._error_response(400, 'Payment failed', payment_result['message'])
            
            # Create order record
            order_data = {
                'orderId': order_id,
                'userId': user_id,
                'status': 'confirmed',
                'items': validated_items,
                'subtotal': float(total_amount),
                'taxAmount': float(tax_amount),
                'shippingAmount': float(shipping_amount),
                'totalAmount': float(final_amount),
                'currency': 'USD',
                'paymentMethod': payment_method,
                'paymentId': payment_result['paymentId'],
                'shippingAddress': shipping_address,
                'billingAddress': billing_address or shipping_address,
                'orderDate': datetime.utcnow().isoformat(),
                'estimatedDelivery': (datetime.utcnow() + timedelta(days=3)).isoformat(),
                'trackingNumber': f"TRK{uuid.uuid4().hex[:10].upper()}",
                'createdAt': datetime.utcnow().isoformat(),
                'updatedAt': datetime.utcnow().isoformat(),
                'ttl': int((datetime.utcnow() + timedelta(days=365)).timestamp())  # 1 year TTL
            }
            
            # Execute atomic transaction
            try:
                self._execute_order_transaction(order_data, validated_items, user_id)
            except ClientError as e:
                logger.error(f"Transaction failed: {e}")
                if 'ConditionalCheckFailedException' in str(e):
                    return self._error_response(409, 'Inventory conflict', 'One or more items are no longer available')
                return self._error_response(500, 'Transaction failed', 'Failed to process order')
            
            # Clear user's cart after successful order
            self._clear_user_cart(user_id)
            
            # Invalidate relevant caches
            self._invalidate_caches(user_id)
            
            # Prepare response
            response_data = {
                'orderId': order_id,
                'status': 'confirmed',
                'totalAmount': float(final_amount),
                'estimatedDelivery': order_data['estimatedDelivery'],
                'trackingNumber': order_data['trackingNumber'],
                'message': 'Order created successfully'
            }
            
            return {
                'statusCode': 201,
                'headers': self._get_cors_headers(),
                'body': json.dumps(response_data, default=self._decimal_serializer)
            }
            
        except Exception as e:
            logger.error(f"Error in create_order: {e}")
            logger.error(traceback.format_exc())
            return self._error_response(500, 'Internal server error', 'Failed to create order')
    
    def get_order(self, event: Dict) -> Dict:
        """
        Get order details by order ID
        """
        try:
            # Extract order ID from path parameters
            path_params = event.get('pathParameters') or {}
            order_id = path_params.get('orderId')
            
            if not order_id:
                return self._error_response(400, 'Missing order ID', 'Order ID is required')
            
            # Check cache first
            cache_key = get_cache_key('order', order_id)
            cached_order = cache_get(cache_key)
            if cached_order:
                logger.info(f"Returning cached order: {order_id}")
                return {
                    'statusCode': 200,
                    'headers': self._get_cors_headers(),
                    'body': cached_order
                }
            
            # Get order from DynamoDB
            try:
                response = self.orders_table.get_item(
                    Key={'orderId': order_id}
                )
                
                if 'Item' not in response:
                    return self._error_response(404, 'Order not found', f'Order {order_id} does not exist')
                
                order = response['Item']
                
            except ClientError as e:
                logger.error(f"DynamoDB error getting order: {e}")
                return self._error_response(500, 'Database error', 'Failed to retrieve order')
            
            # Enrich order with current product information
            enriched_order = self._enrich_order_with_product_info(order)
            
            response_body = json.dumps(enriched_order, default=self._decimal_serializer)
            
            # Cache the result
            cache_set(cache_key, response_body, ttl=1800)  # 30 minutes cache
            
            return {
                'statusCode': 200,
                'headers': self._get_cors_headers(),
                'body': response_body
            }
            
        except Exception as e:
            logger.error(f"Error in get_order: {e}")
            logger.error(traceback.format_exc())
            return self._error_response(500, 'Internal server error', 'Failed to retrieve order')
    
    def get_user_orders(self, event: Dict) -> Dict:
        """
        Get order history for a user with pagination and filtering
        """
        try:
            # Extract user ID from path parameters
            path_params = event.get('pathParameters') or {}
            user_id = path_params.get('userId')
            
            if not user_id:
                return self._error_response(400, 'Missing user ID', 'User ID is required')
            
            # Parse query parameters
            query_params = event.get('queryStringParameters') or {}
            page = int(query_params.get('page', 1))
            limit = min(int(query_params.get('limit', config.DEFAULT_PAGE_SIZE)), config.MAX_PAGE_SIZE)
            status_filter = query_params.get('status')
            start_date = query_params.get('startDate')
            end_date = query_params.get('endDate')
            
            # Build cache key
            cache_key = get_cache_key('user_orders', 
                f"{user_id}_{page}_{limit}_{status_filter}_{start_date}_{end_date}")
            
            # Check cache first
            cached_orders = cache_get(cache_key)
            if cached_orders:
                logger.info(f"Returning cached user orders for: {user_id}")
                return {
                    'statusCode': 200,
                    'headers': self._get_cors_headers(),
                    'body': cached_orders
                }
            
            # Build query parameters
            key_condition = 'userId = :userId'
            expression_values = {':userId': user_id}
            filter_expression = None
            filter_values = {}
            
            # Add status filter
            if status_filter:
                filter_expression = '#status = :status'
                filter_values[':status'] = status_filter
                
            # Add date range filter
            if start_date or end_date:
                date_conditions = []
                if start_date:
                    date_conditions.append('orderDate >= :startDate')
                    filter_values[':startDate'] = start_date
                if end_date:
                    date_conditions.append('orderDate <= :endDate')
                    filter_values[':endDate'] = end_date
                
                date_filter = ' AND '.join(date_conditions)
                if filter_expression:
                    filter_expression += f' AND {date_filter}'
                else:
                    filter_expression = date_filter
            
            expression_values.update(filter_values)
            
            # Execute query
            try:
                query_params = {
                    'IndexName': 'UserOrdersIndex',  # Assuming GSI exists
                    'KeyConditionExpression': key_condition,
                    'ExpressionAttributeValues': expression_values,
                    'ScanIndexForward': False,  # Most recent first
                    'Limit': limit
                }
                
                if filter_expression:
                    query_params['FilterExpression'] = filter_expression
                    query_params['ExpressionAttributeNames'] = {'#status': 'status'}
                
                # Handle pagination
                if page > 1:
                    # For simplicity, we'll use scan with pagination
                    # In production, you'd want to use LastEvaluatedKey
                    query_params['ExclusiveStartKey'] = None  # Implement proper pagination
                
                response = self.orders_table.query(**query_params)
                orders = response.get('Items', [])
                
            except ClientError as e:
                logger.error(f"DynamoDB error getting user orders: {e}")
                return self._error_response(500, 'Database error', 'Failed to retrieve orders')
            
            # Calculate pagination info
            total_count = len(orders)  # Simplified - in production, use separate count query
            total_pages = (total_count + limit - 1) // limit if total_count > 0 else 1
            
            # Prepare response
            response_data = {
                'orders': orders,
                'pagination': {
                    'current_page': page,
                    'total_pages': total_pages,
                    'total_items': total_count,
                    'items_per_page': limit,
                    'has_next': page < total_pages,
                    'has_previous': page > 1
                },
                'filters_applied': {
                    'status': status_filter,
                    'start_date': start_date,
                    'end_date': end_date
                }
            }
            
            response_body = json.dumps(response_data, default=self._decimal_serializer)
            
            # Cache the result
            cache_set(cache_key, response_body, ttl=600)  # 10 minutes cache
            
            return {
                'statusCode': 200,
                'headers': self._get_cors_headers(),
                'body': response_body
            }
            
        except ValueError as e:
            logger.error(f"Invalid parameter in get_user_orders: {e}")
            return self._error_response(400, 'Invalid parameters', str(e))
        except Exception as e:
            logger.error(f"Error in get_user_orders: {e}")
            logger.error(traceback.format_exc())
            return self._error_response(500, 'Internal server error', 'Failed to retrieve user orders')
    
    def update_order_status(self, event: Dict) -> Dict:
        """
        Update order status and tracking information
        """
        try:
            # Extract order ID from path parameters
            path_params = event.get('pathParameters') or {}
            order_id = path_params.get('orderId')
            
            if not order_id:
                return self._error_response(400, 'Missing order ID', 'Order ID is required')
            
            # Parse request body
            try:
                body = json.loads(event.get('body', '{}'))
            except json.JSONDecodeError:
                return self._error_response(400, 'Invalid JSON', 'Request body must be valid JSON')
            
            new_status = body.get('status')
            tracking_number = body.get('trackingNumber')
            delivery_date = body.get('deliveryDate')
            notes = body.get('notes')
            
            if not new_status:
                return self._error_response(400, 'Missing status', 'New status is required')
            
            # Validate status
            valid_statuses = ['confirmed', 'processing', 'shipped', 'delivered', 'cancelled', 'returned']
            if new_status not in valid_statuses:
                return self._error_response(400, 'Invalid status', f'Status must be one of: {valid_statuses}')
            
            # Update order in DynamoDB
            try:
                update_expression = 'SET #status = :status, updatedAt = :updatedAt'
                expression_values = {
                    ':status': new_status,
                    ':updatedAt': datetime.utcnow().isoformat()
                }
                expression_names = {'#status': 'status'}
                
                if tracking_number:
                    update_expression += ', trackingNumber = :trackingNumber'
                    expression_values[':trackingNumber'] = tracking_number
                
                if delivery_date:
                    update_expression += ', deliveryDate = :deliveryDate'
                    expression_values[':deliveryDate'] = delivery_date
                
                if notes:
                    update_expression += ', notes = :notes'
                    expression_values[':notes'] = notes
                
                response = self.orders_table.update_item(
                    Key={'orderId': order_id},
                    UpdateExpression=update_expression,
                    ExpressionAttributeValues=expression_values,
                    ExpressionAttributeNames=expression_names,
                    ConditionExpression='attribute_exists(orderId)',
                    ReturnValues='ALL_NEW'
                )
                
                updated_order = response['Attributes']
                
            except ClientError as e:
                if e.response['Error']['Code'] == 'ConditionalCheckFailedException':
                    return self._error_response(404, 'Order not found', f'Order {order_id} does not exist')
                logger.error(f"DynamoDB error updating order: {e}")
                return self._error_response(500, 'Database error', 'Failed to update order')
            
            # Invalidate cache
            cache_key = get_cache_key('order', order_id)
            cache_delete(cache_key)
            
            # Also invalidate user orders cache
            user_id = updated_order.get('userId')
            if user_id:
                user_cache_pattern = get_cache_key('user_orders', f"{user_id}_*")
                # In production, you'd implement cache pattern deletion
            
            response_data = {
                'orderId': order_id,
                'status': new_status,
                'updatedAt': updated_order['updatedAt'],
                'message': 'Order status updated successfully'
            }
            
            if tracking_number:
                response_data['trackingNumber'] = tracking_number
            if delivery_date:
                response_data['deliveryDate'] = delivery_date
            
            return {
                'statusCode': 200,
                'headers': self._get_cors_headers(),
                'body': json.dumps(response_data, default=self._decimal_serializer)
            }
            
        except Exception as e:
            logger.error(f"Error in update_order_status: {e}")
            logger.error(traceback.format_exc())
            return self._error_response(500, 'Internal server error', 'Failed to update order status')
    
    def _validate_and_enrich_items(self, items: List[Dict]) -> tuple[List[Dict], Decimal]:
        """
        Validate order items and enrich with current product information
        Returns (validated_items, total_amount)
        """
        validated_items = []
        total_amount = Decimal('0')
        
        for item in items:
            product_id = item.get('productId')
            quantity = item.get('quantity', 1)
            
            if not product_id or quantity <= 0:
                continue
            
            # Get current product information
            product = self._get_product_info(product_id)
            if not product:
                logger.warning(f"Product {product_id} not found, skipping")
                continue
            
            # Check inventory
            available_quantity = self._check_inventory(product_id)
            if available_quantity < quantity:
                logger.warning(f"Insufficient inventory for {product_id}: {available_quantity} < {quantity}")
                continue
            
            # Calculate item total
            item_price = Decimal(str(product['price']))
            item_total = item_price * quantity
            
            validated_item = {
                'productId': product_id,
                'title': product['title'],
                'price': float(item_price),
                'quantity': quantity,
                'subtotal': float(item_total),
                'imageUrl': product.get('image_url', ''),
                'category': product.get('category', '')
            }
            
            validated_items.append(validated_item)
            total_amount += item_total
        
        return validated_items, total_amount
    
    def _execute_order_transaction(self, order_data: Dict, items: List[Dict], user_id: str):
        """
        Execute atomic transaction to create order and update inventory
        """
        transact_items = []
        
        # 1. Create order record
        transact_items.append({
            'Put': {
                'TableName': self.orders_table.name,
                'Item': order_data,
                'ConditionExpression': 'attribute_not_exists(orderId)'
            }
        })
        
        # 2. Update inventory for each item
        for item in items:
            product_id = item['productId']
            quantity = item['quantity']
            
            transact_items.append({
                'Update': {
                    'TableName': self.inventory_table.name,
                    'Key': {'productId': product_id},
                    'UpdateExpression': 'SET availableQuantity = availableQuantity - :quantity, updatedAt = :updatedAt',
                    'ExpressionAttributeValues': {
                        ':quantity': quantity,
                        ':updatedAt': datetime.utcnow().isoformat(),
                        ':minQuantity': quantity
                    },
                    'ConditionExpression': 'availableQuantity >= :minQuantity'
                }
            })
        
        # Execute transaction
        self.dynamodb.meta.client.transact_write_items(
            TransactItems=transact_items
        )
    
    def _get_product_info(self, product_id: str) -> Optional[Dict]:
        """Get product information from DocumentDB"""
        try:
            from bson import ObjectId
            
            # Try to find by ObjectId first, then by string ID
            try:
                product = self.products_collection.find_one({'_id': ObjectId(product_id)})
            except:
                product = self.products_collection.find_one({'_id': product_id})
            
            if product:
                return {
                    'title': product.get('title', ''),
                    'price': product.get('price', 0),
                    'image_url': product.get('image_url', ''),
                    'category': product.get('category', ''),
                    'in_stock': product.get('in_stock', True)
                }
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting product info for {product_id}: {e}")
            return None
    
    def _check_inventory(self, product_id: str) -> int:
        """Check available inventory for a product"""
        try:
            response = self.inventory_table.get_item(
                Key={'productId': product_id}
            )
            
            if 'Item' in response:
                return response['Item'].get('availableQuantity', 0)
            
            return 0
            
        except ClientError as e:
            logger.error(f"Error checking inventory for {product_id}: {e}")
            return 0
    
    def _calculate_tax(self, subtotal: Decimal, state: str) -> Decimal:
        """Calculate tax amount based on subtotal and state"""
        # Simplified tax calculation - in production, use proper tax service
        tax_rates = {
            'CA': Decimal('0.0875'),  # California
            'NY': Decimal('0.08'),    # New York
            'TX': Decimal('0.0625'),  # Texas
            'FL': Decimal('0.06'),    # Florida
            'WA': Decimal('0.065'),   # Washington
        }
        
        tax_rate = tax_rates.get(state, Decimal('0.05'))  # Default 5%
        return subtotal * tax_rate
    
    def _calculate_shipping(self, subtotal: Decimal, shipping_address: Dict) -> Decimal:
        """Calculate shipping cost"""
        # Free shipping over $50
        if subtotal >= Decimal('50'):
            return Decimal('0')
        
        # Standard shipping rates
        return Decimal('9.99')
    
    def _process_payment(self, payment_method: Dict, amount: Decimal) -> Dict:
        """Process payment (mock implementation)"""
        # Mock payment processing
        payment_type = payment_method.get('type', 'credit_card')
        
        if payment_type == 'credit_card':
            card_number = payment_method.get('cardNumber', '')
            if not card_number or len(card_number) < 16:
                return {'success': False, 'message': 'Invalid card number'}
        
        # Simulate payment processing
        payment_id = f"PAY-{uuid.uuid4().hex[:12].upper()}"
        
        return {
            'success': True,
            'paymentId': payment_id,
            'message': 'Payment processed successfully'
        }
    
    def _clear_user_cart(self, user_id: str):
        """Clear user's cart after successful order"""
        try:
            # Get all cart items
            response = self.cart_table.query(
                KeyConditionExpression='userId = :userId',
                ExpressionAttributeValues={':userId': user_id}
            )
            
            # Delete all items
            for item in response.get('Items', []):
                self.cart_table.delete_item(
                    Key={'userId': item['userId'], 'productId': item['productId']}
                )
            
            logger.info(f"Cleared cart for user: {user_id}")
            
        except Exception as e:
            logger.error(f"Error clearing cart for user {user_id}: {e}")
    
    def _enrich_order_with_product_info(self, order: Dict) -> Dict:
        """Enrich order with current product information"""
        try:
            enriched_items = []
            
            for item in order.get('items', []):
                product_id = item.get('productId')
                current_product = self._get_product_info(product_id)
                
                enriched_item = item.copy()
                if current_product:
                    enriched_item['currentPrice'] = current_product['price']
                    enriched_item['priceChanged'] = abs(float(item.get('price', 0)) - float(current_product['price'])) > 0.01
                    enriched_item['stillAvailable'] = current_product['in_stock']
                
                enriched_items.append(enriched_item)
            
            order['items'] = enriched_items
            return order
            
        except Exception as e:
            logger.error(f"Error enriching order: {e}")
            return order
    
    def _invalidate_caches(self, user_id: str):
        """Invalidate relevant caches"""
        try:
            # Invalidate user cart cache
            cart_cache_key = get_cache_key('cart', user_id)
            cache_delete(cart_cache_key)
            
            # In production, you'd implement pattern-based cache invalidation
            # for user orders cache
            
        except Exception as e:
            logger.error(f"Error invalidating caches: {e}")
    
    def _get_cors_headers(self) -> Dict[str, str]:
        """Get CORS headers for responses"""
        return {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
            'Access-Control-Allow-Headers': 'Content-Type, Authorization'
        }
    
    def _error_response(self, status_code: int, error: str, message: str) -> Dict:
        """Generate standardized error response"""
        return {
            'statusCode': status_code,
            'headers': self._get_cors_headers(),
            'body': json.dumps({
                'error': error,
                'message': message
            })
        }
    
    def _decimal_serializer(self, obj):
        """JSON serializer for Decimal objects"""
        if isinstance(obj, Decimal):
            return float(obj)
        raise TypeError(f"Object of type {type(obj)} is not JSON serializable")

# Initialize API handler
order_api = OrderManagementAPI()

def lambda_handler(event, context):
    """
    Main Lambda handler function
    Routes requests based on HTTP method and path
    """
    try:
        logger.info(f"Received event: {json.dumps(event)}")
        
        http_method = event.get('httpMethod')
        path = event.get('path', '')
        
        # Handle OPTIONS requests for CORS
        if http_method == 'OPTIONS':
            return {
                'statusCode': 200,
                'headers': {
                    'Access-Control-Allow-Origin': '*',
                    'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
                    'Access-Control-Allow-Headers': 'Content-Type, Authorization'
                },
                'body': ''
            }
        
        # Route requests
        if http_method == 'POST' and path.endswith('/orders'):
            return order_api.create_order(event)
        elif http_method == 'GET' and '/orders/' in path and not '/users/' in path:
            return order_api.get_order(event)
        elif http_method == 'GET' and '/users/' in path and '/orders' in path:
            return order_api.get_user_orders(event)
        elif http_method == 'PUT' and '/orders/' in path:
            return order_api.update_order_status(event)
        else:
            return {
                'statusCode': 405,
                'headers': order_api._get_cors_headers(),
                'body': json.dumps({
                    'error': 'Method not allowed',
                    'message': f'HTTP method {http_method} not supported for path {path}'
                })
            }
    
    except Exception as e:
        logger.error(f"Unhandled error in lambda_handler: {e}")
        logger.error(traceback.format_exc())
        return {
            'statusCode': 500,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({
                'error': 'Internal server error',
                'message': 'An unexpected error occurred'
            })
        }