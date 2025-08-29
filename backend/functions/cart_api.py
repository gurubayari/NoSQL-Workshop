"""
Shopping Cart API Lambda function for Unicorn E-Commerce
Handles cart operations with DynamoDB persistence and ElastiCache caching
"""
import json
import logging
import traceback
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

class CartAPIError(Exception):
    """Custom exception for Cart API errors"""
    pass

class ShoppingCartAPI:
    """Shopping Cart API handler class"""
    
    def __init__(self):
        self.cart_table = get_dynamodb_table(config.SHOPPING_CART_TABLE)
        self.inventory_table = get_dynamodb_table(config.INVENTORY_TABLE)
        self.products_collection = get_documentdb_collection('products')
    
    def get_cart(self, event: Dict) -> Dict:
        """
        Get cart contents for a user
        Returns cart items with current product information and inventory status
        """
        try:
            # Extract user ID from path parameters
            path_params = event.get('pathParameters') or {}
            user_id = path_params.get('userId')
            
            if not user_id:
                return self._error_response(400, 'Missing user ID', 'User ID is required')
            
            # Check cache first
            cache_key = get_cache_key('cart', user_id)
            cached_cart = cache_get(cache_key)
            if cached_cart:
                logger.info(f"Returning cached cart for user: {user_id}")
                return {
                    'statusCode': 200,
                    'headers': self._get_cors_headers(),
                    'body': cached_cart
                }
            
            # Get cart items from DynamoDB
            try:
                response = self.cart_table.query(
                    KeyConditionExpression='userId = :userId',
                    ExpressionAttributeValues={':userId': user_id}
                )
                cart_items = response.get('Items', [])
            except ClientError as e:
                logger.error(f"DynamoDB error getting cart: {e}")
                return self._error_response(500, 'Database error', 'Failed to retrieve cart')
            
            # Enrich cart items with current product information
            enriched_items = []
            total_amount = Decimal('0')
            
            for item in cart_items:
                enriched_item = self._enrich_cart_item(item)
                if enriched_item:
                    enriched_items.append(enriched_item)
                    total_amount += Decimal(str(enriched_item['subtotal']))
            
            # Prepare cart response
            cart_data = {
                'userId': user_id,
                'items': enriched_items,
                'itemCount': len(enriched_items),
                'totalAmount': float(total_amount),
                'lastUpdated': datetime.utcnow().isoformat(),
                'currency': 'USD'
            }
            
            response_body = json.dumps(cart_data, default=self._decimal_serializer)
            
            # Cache the result
            cache_set(cache_key, response_body, ttl=300)  # 5 minutes cache
            
            return {
                'statusCode': 200,
                'headers': self._get_cors_headers(),
                'body': response_body
            }
            
        except Exception as e:
            logger.error(f"Error in get_cart: {e}")
            logger.error(traceback.format_exc())
            return self._error_response(500, 'Internal server error', 'Failed to retrieve cart')
    
    def add_to_cart(self, event: Dict) -> Dict:
        """
        Add item to cart or update quantity if item already exists
        Validates inventory availability before adding
        """
        try:
            # Extract user ID from path parameters
            path_params = event.get('pathParameters') or {}
            user_id = path_params.get('userId')
            
            if not user_id:
                return self._error_response(400, 'Missing user ID', 'User ID is required')
            
            # Parse request body
            try:
                body = json.loads(event.get('body', '{}'))
            except json.JSONDecodeError:
                return self._error_response(400, 'Invalid JSON', 'Request body must be valid JSON')
            
            product_id = body.get('productId')
            quantity = body.get('quantity', 1)
            
            if not product_id:
                return self._error_response(400, 'Missing product ID', 'Product ID is required')
            
            if not isinstance(quantity, int) or quantity <= 0:
                return self._error_response(400, 'Invalid quantity', 'Quantity must be a positive integer')
            
            # Validate product exists and get current price
            product = self._get_product_info(product_id)
            if not product:
                return self._error_response(404, 'Product not found', f'Product {product_id} does not exist')
            
            # Check inventory availability
            available_quantity = self._check_inventory(product_id)
            if available_quantity < quantity:
                return self._error_response(400, 'Insufficient inventory', 
                    f'Only {available_quantity} items available, requested {quantity}')
            
            # Check if item already exists in cart
            try:
                existing_item = self.cart_table.get_item(
                    Key={'userId': user_id, 'productId': product_id}
                )
                
                if 'Item' in existing_item:
                    # Update existing item
                    new_quantity = existing_item['Item']['quantity'] + quantity
                    
                    # Check total quantity against inventory
                    if available_quantity < new_quantity:
                        return self._error_response(400, 'Insufficient inventory', 
                            f'Only {available_quantity} items available, cart would have {new_quantity}')
                    
                    # Update item in DynamoDB
                    self.cart_table.update_item(
                        Key={'userId': user_id, 'productId': product_id},
                        UpdateExpression='SET quantity = :quantity, updatedAt = :updatedAt, price = :price',
                        ExpressionAttributeValues={
                            ':quantity': new_quantity,
                            ':updatedAt': datetime.utcnow().isoformat(),
                            ':price': product['price']
                        }
                    )
                    
                    response_quantity = new_quantity
                else:
                    # Add new item to cart
                    cart_item = {
                        'userId': user_id,
                        'productId': product_id,
                        'quantity': quantity,
                        'price': product['price'],
                        'addedAt': datetime.utcnow().isoformat(),
                        'updatedAt': datetime.utcnow().isoformat(),
                        'ttl': int((datetime.utcnow() + timedelta(days=30)).timestamp())  # 30 days TTL
                    }
                    
                    self.cart_table.put_item(Item=cart_item)
                    response_quantity = quantity
                
            except ClientError as e:
                logger.error(f"DynamoDB error adding to cart: {e}")
                return self._error_response(500, 'Database error', 'Failed to add item to cart')
            
            # Invalidate cart cache
            cache_key = get_cache_key('cart', user_id)
            cache_delete(cache_key)
            
            # Prepare response
            response_data = {
                'message': 'Item added to cart successfully',
                'productId': product_id,
                'quantity': response_quantity,
                'price': float(product['price']),
                'subtotal': float(Decimal(str(product['price'])) * response_quantity)
            }
            
            return {
                'statusCode': 200,
                'headers': self._get_cors_headers(),
                'body': json.dumps(response_data, default=self._decimal_serializer)
            }
            
        except Exception as e:
            logger.error(f"Error in add_to_cart: {e}")
            logger.error(traceback.format_exc())
            return self._error_response(500, 'Internal server error', 'Failed to add item to cart')
    
    def update_cart_item(self, event: Dict) -> Dict:
        """
        Update quantity of an item in the cart
        """
        try:
            # Extract parameters
            path_params = event.get('pathParameters') or {}
            user_id = path_params.get('userId')
            product_id = path_params.get('productId')
            
            if not user_id or not product_id:
                return self._error_response(400, 'Missing parameters', 'User ID and Product ID are required')
            
            # Parse request body
            try:
                body = json.loads(event.get('body', '{}'))
            except json.JSONDecodeError:
                return self._error_response(400, 'Invalid JSON', 'Request body must be valid JSON')
            
            quantity = body.get('quantity')
            
            if quantity is None or not isinstance(quantity, int) or quantity < 0:
                return self._error_response(400, 'Invalid quantity', 'Quantity must be a non-negative integer')
            
            # If quantity is 0, remove the item
            if quantity == 0:
                return self.remove_from_cart(event)
            
            # Check inventory availability
            available_quantity = self._check_inventory(product_id)
            if available_quantity < quantity:
                return self._error_response(400, 'Insufficient inventory', 
                    f'Only {available_quantity} items available, requested {quantity}')
            
            # Get current product price
            product = self._get_product_info(product_id)
            if not product:
                return self._error_response(404, 'Product not found', f'Product {product_id} does not exist')
            
            # Update item in DynamoDB
            try:
                response = self.cart_table.update_item(
                    Key={'userId': user_id, 'productId': product_id},
                    UpdateExpression='SET quantity = :quantity, updatedAt = :updatedAt, price = :price',
                    ExpressionAttributeValues={
                        ':quantity': quantity,
                        ':updatedAt': datetime.utcnow().isoformat(),
                        ':price': product['price']
                    },
                    ConditionExpression='attribute_exists(userId)',
                    ReturnValues='ALL_NEW'
                )
                
                updated_item = response['Attributes']
                
            except ClientError as e:
                if e.response['Error']['Code'] == 'ConditionalCheckFailedException':
                    return self._error_response(404, 'Item not found', 'Item not found in cart')
                logger.error(f"DynamoDB error updating cart item: {e}")
                return self._error_response(500, 'Database error', 'Failed to update cart item')
            
            # Invalidate cart cache
            cache_key = get_cache_key('cart', user_id)
            cache_delete(cache_key)
            
            # Prepare response
            response_data = {
                'message': 'Cart item updated successfully',
                'productId': product_id,
                'quantity': updated_item['quantity'],
                'price': float(updated_item['price']),
                'subtotal': float(Decimal(str(updated_item['price'])) * updated_item['quantity'])
            }
            
            return {
                'statusCode': 200,
                'headers': self._get_cors_headers(),
                'body': json.dumps(response_data, default=self._decimal_serializer)
            }
            
        except Exception as e:
            logger.error(f"Error in update_cart_item: {e}")
            logger.error(traceback.format_exc())
            return self._error_response(500, 'Internal server error', 'Failed to update cart item')
    
    def remove_from_cart(self, event: Dict) -> Dict:
        """
        Remove item from cart
        """
        try:
            # Extract parameters
            path_params = event.get('pathParameters') or {}
            user_id = path_params.get('userId')
            product_id = path_params.get('productId')
            
            if not user_id or not product_id:
                return self._error_response(400, 'Missing parameters', 'User ID and Product ID are required')
            
            # Remove item from DynamoDB
            try:
                self.cart_table.delete_item(
                    Key={'userId': user_id, 'productId': product_id},
                    ConditionExpression='attribute_exists(userId)'
                )
            except ClientError as e:
                if e.response['Error']['Code'] == 'ConditionalCheckFailedException':
                    return self._error_response(404, 'Item not found', 'Item not found in cart')
                logger.error(f"DynamoDB error removing cart item: {e}")
                return self._error_response(500, 'Database error', 'Failed to remove cart item')
            
            # Invalidate cart cache
            cache_key = get_cache_key('cart', user_id)
            cache_delete(cache_key)
            
            response_data = {
                'message': 'Item removed from cart successfully',
                'productId': product_id
            }
            
            return {
                'statusCode': 200,
                'headers': self._get_cors_headers(),
                'body': json.dumps(response_data)
            }
            
        except Exception as e:
            logger.error(f"Error in remove_from_cart: {e}")
            logger.error(traceback.format_exc())
            return self._error_response(500, 'Internal server error', 'Failed to remove cart item')
    
    def clear_cart(self, event: Dict) -> Dict:
        """
        Clear all items from user's cart
        """
        try:
            # Extract user ID from path parameters
            path_params = event.get('pathParameters') or {}
            user_id = path_params.get('userId')
            
            if not user_id:
                return self._error_response(400, 'Missing user ID', 'User ID is required')
            
            # Get all cart items for the user
            try:
                response = self.cart_table.query(
                    KeyConditionExpression='userId = :userId',
                    ExpressionAttributeValues={':userId': user_id}
                )
                cart_items = response.get('Items', [])
            except ClientError as e:
                logger.error(f"DynamoDB error getting cart items: {e}")
                return self._error_response(500, 'Database error', 'Failed to retrieve cart items')
            
            # Delete all items
            deleted_count = 0
            for item in cart_items:
                try:
                    self.cart_table.delete_item(
                        Key={'userId': item['userId'], 'productId': item['productId']}
                    )
                    deleted_count += 1
                except ClientError as e:
                    logger.error(f"Error deleting cart item {item['productId']}: {e}")
            
            # Invalidate cart cache
            cache_key = get_cache_key('cart', user_id)
            cache_delete(cache_key)
            
            response_data = {
                'message': 'Cart cleared successfully',
                'itemsRemoved': deleted_count
            }
            
            return {
                'statusCode': 200,
                'headers': self._get_cors_headers(),
                'body': json.dumps(response_data)
            }
            
        except Exception as e:
            logger.error(f"Error in clear_cart: {e}")
            logger.error(traceback.format_exc())
            return self._error_response(500, 'Internal server error', 'Failed to clear cart')
    
    def _enrich_cart_item(self, cart_item: Dict) -> Optional[Dict]:
        """
        Enrich cart item with current product information and inventory status
        """
        try:
            product_id = cart_item['productId']
            
            # Get current product information
            product = self._get_product_info(product_id)
            if not product:
                logger.warning(f"Product {product_id} not found, removing from cart")
                return None
            
            # Check current inventory
            available_quantity = self._check_inventory(product_id)
            
            # Calculate subtotal
            quantity = cart_item['quantity']
            current_price = product['price']
            subtotal = Decimal(str(current_price)) * quantity
            
            # Check if price has changed
            cart_price = cart_item.get('price', current_price)
            price_changed = abs(float(cart_price) - float(current_price)) > 0.01
            
            enriched_item = {
                'productId': product_id,
                'title': product['title'],
                'price': float(current_price),
                'originalPrice': float(cart_price),
                'priceChanged': price_changed,
                'quantity': quantity,
                'subtotal': float(subtotal),
                'imageUrl': product.get('image_url', ''),
                'category': product.get('category', ''),
                'inStock': available_quantity > 0,
                'availableQuantity': available_quantity,
                'inventoryStatus': self._get_inventory_status(available_quantity, quantity),
                'addedAt': cart_item.get('addedAt'),
                'updatedAt': cart_item.get('updatedAt')
            }
            
            return enriched_item
            
        except Exception as e:
            logger.error(f"Error enriching cart item {cart_item.get('productId')}: {e}")
            return None
    
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
    
    def _get_inventory_status(self, available: int, requested: int) -> str:
        """Get inventory status message"""
        if available == 0:
            return 'out_of_stock'
        elif available < requested:
            return 'insufficient_stock'
        elif available <= 5:
            return 'low_stock'
        else:
            return 'in_stock'
    
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
cart_api = ShoppingCartAPI()

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
        if http_method == 'GET' and '/cart/' in path:
            return cart_api.get_cart(event)
        elif http_method == 'POST' and '/cart/' in path and path.endswith('/items'):
            return cart_api.add_to_cart(event)
        elif http_method == 'PUT' and '/cart/' in path and '/items/' in path:
            return cart_api.update_cart_item(event)
        elif http_method == 'DELETE' and '/cart/' in path and '/items/' in path:
            return cart_api.remove_from_cart(event)
        elif http_method == 'DELETE' and '/cart/' in path and path.endswith('/clear'):
            return cart_api.clear_cart(event)
        else:
            return {
                'statusCode': 405,
                'headers': cart_api._get_cors_headers(),
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