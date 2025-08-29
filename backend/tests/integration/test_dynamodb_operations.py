"""
Integration tests for DynamoDB operations
Tests CRUD operations, transactions, and cache consistency
"""
import pytest
import boto3
import json
import time
from datetime import datetime, timedelta
from decimal import Decimal
from moto import mock_dynamodb
import sys
import os

# Add the shared directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'shared'))

from database import get_dynamodb_table, cache_get, cache_set, cache_delete, get_cache_key

@mock_dynamodb
class TestDynamoDBOperations:
    """Integration tests for DynamoDB operations"""
    
    def setup_method(self):
        """Set up test DynamoDB tables"""
        self.dynamodb = boto3.resource('dynamodb', region_name='us-west-2')
        
        # Create test tables
        self.create_test_tables()
        
        # Get table references
        self.cart_table = self.dynamodb.Table('test-shopping-cart')
        self.orders_table = self.dynamodb.Table('test-orders')
        self.inventory_table = self.dynamodb.Table('test-inventory')
        self.users_table = self.dynamodb.Table('test-users')
        self.search_analytics_table = self.dynamodb.Table('test-search-analytics')
    
    def create_test_tables(self):
        """Create test DynamoDB tables"""
        
        # Shopping Cart Table
        self.dynamodb.create_table(
            TableName='test-shopping-cart',
            KeySchema=[
                {'AttributeName': 'userId', 'KeyType': 'HASH'},
                {'AttributeName': 'productId', 'KeyType': 'RANGE'}
            ],
            AttributeDefinitions=[
                {'AttributeName': 'userId', 'AttributeType': 'S'},
                {'AttributeName': 'productId', 'AttributeType': 'S'}
            ],
            BillingMode='PAY_PER_REQUEST'
        )
        
        # Orders Table
        self.dynamodb.create_table(
            TableName='test-orders',
            KeySchema=[
                {'AttributeName': 'orderId', 'KeyType': 'HASH'}
            ],
            AttributeDefinitions=[
                {'AttributeName': 'orderId', 'AttributeType': 'S'},
                {'AttributeName': 'userId', 'AttributeType': 'S'}
            ],
            GlobalSecondaryIndexes=[
                {
                    'IndexName': 'UserOrdersIndex',
                    'KeySchema': [
                        {'AttributeName': 'userId', 'KeyType': 'HASH'}
                    ],
                    'Projection': {'ProjectionType': 'ALL'}
                }
            ],
            BillingMode='PAY_PER_REQUEST'
        )
        
        # Inventory Table
        self.dynamodb.create_table(
            TableName='test-inventory',
            KeySchema=[
                {'AttributeName': 'productId', 'KeyType': 'HASH'}
            ],
            AttributeDefinitions=[
                {'AttributeName': 'productId', 'AttributeType': 'S'}
            ],
            BillingMode='PAY_PER_REQUEST'
        )
        
        # Users Table
        self.dynamodb.create_table(
            TableName='test-users',
            KeySchema=[
                {'AttributeName': 'userId', 'KeyType': 'HASH'}
            ],
            AttributeDefinitions=[
                {'AttributeName': 'userId', 'AttributeType': 'S'},
                {'AttributeName': 'email', 'AttributeType': 'S'}
            ],
            GlobalSecondaryIndexes=[
                {
                    'IndexName': 'EmailIndex',
                    'KeySchema': [
                        {'AttributeName': 'email', 'KeyType': 'HASH'}
                    ],
                    'Projection': {'ProjectionType': 'ALL'}
                }
            ],
            BillingMode='PAY_PER_REQUEST'
        )
        
        # Search Analytics Table
        self.dynamodb.create_table(
            TableName='test-search-analytics',
            KeySchema=[
                {'AttributeName': 'searchTerm', 'KeyType': 'HASH'},
                {'AttributeName': 'timestamp', 'KeyType': 'RANGE'}
            ],
            AttributeDefinitions=[
                {'AttributeName': 'searchTerm', 'AttributeType': 'S'},
                {'AttributeName': 'timestamp', 'AttributeType': 'S'}
            ],
            BillingMode='PAY_PER_REQUEST'
        )
    
    def test_cart_crud_operations(self):
        """Test shopping cart CRUD operations"""
        user_id = 'test_user_123'
        product_id = 'prod_456'
        
        # Create cart item
        cart_item = {
            'userId': user_id,
            'productId': product_id,
            'quantity': 2,
            'price': Decimal('99.99'),
            'addedAt': datetime.utcnow().isoformat(),
            'updatedAt': datetime.utcnow().isoformat(),
            'ttl': int((datetime.utcnow() + timedelta(days=30)).timestamp())
        }
        
        # Test CREATE
        self.cart_table.put_item(Item=cart_item)
        
        # Test READ
        response = self.cart_table.get_item(
            Key={'userId': user_id, 'productId': product_id}
        )
        assert 'Item' in response
        assert response['Item']['quantity'] == 2
        assert response['Item']['price'] == Decimal('99.99')
        
        # Test UPDATE
        self.cart_table.update_item(
            Key={'userId': user_id, 'productId': product_id},
            UpdateExpression='SET quantity = :quantity, updatedAt = :updatedAt',
            ExpressionAttributeValues={
                ':quantity': 3,
                ':updatedAt': datetime.utcnow().isoformat()
            }
        )
        
        # Verify update
        response = self.cart_table.get_item(
            Key={'userId': user_id, 'productId': product_id}
        )
        assert response['Item']['quantity'] == 3
        
        # Test DELETE
        self.cart_table.delete_item(
            Key={'userId': user_id, 'productId': product_id}
        )
        
        # Verify deletion
        response = self.cart_table.get_item(
            Key={'userId': user_id, 'productId': product_id}
        )
        assert 'Item' not in response
    
    def test_cart_query_operations(self):
        """Test cart query operations for user"""
        user_id = 'test_user_123'
        
        # Add multiple items to cart
        items = [
            {
                'userId': user_id,
                'productId': 'prod_1',
                'quantity': 1,
                'price': Decimal('50.00')
            },
            {
                'userId': user_id,
                'productId': 'prod_2',
                'quantity': 2,
                'price': Decimal('75.00')
            },
            {
                'userId': user_id,
                'productId': 'prod_3',
                'quantity': 1,
                'price': Decimal('100.00')
            }
        ]
        
        for item in items:
            self.cart_table.put_item(Item=item)
        
        # Query all items for user
        response = self.cart_table.query(
            KeyConditionExpression='userId = :userId',
            ExpressionAttributeValues={':userId': user_id}
        )
        
        assert len(response['Items']) == 3
        
        # Calculate total
        total = sum(item['price'] * item['quantity'] for item in response['Items'])
        assert total == Decimal('300.00')  # 50 + 150 + 100
    
    def test_inventory_operations(self):
        """Test inventory management operations"""
        product_id = 'prod_123'
        
        # Create inventory record
        inventory_item = {
            'productId': product_id,
            'availableQuantity': 100,
            'reservedQuantity': 0,
            'warehouseLocation': 'WH-001',
            'lastUpdated': datetime.utcnow().isoformat()
        }
        
        self.inventory_table.put_item(Item=inventory_item)
        
        # Test inventory check
        response = self.inventory_table.get_item(
            Key={'productId': product_id}
        )
        assert response['Item']['availableQuantity'] == 100
        
        # Test inventory deduction (atomic update)
        quantity_to_deduct = 5
        self.inventory_table.update_item(
            Key={'productId': product_id},
            UpdateExpression='SET availableQuantity = availableQuantity - :quantity, lastUpdated = :updated',
            ExpressionAttributeValues={
                ':quantity': quantity_to_deduct,
                ':updated': datetime.utcnow().isoformat(),
                ':minQuantity': quantity_to_deduct
            },
            ConditionExpression='availableQuantity >= :minQuantity'
        )
        
        # Verify deduction
        response = self.inventory_table.get_item(
            Key={'productId': product_id}
        )
        assert response['Item']['availableQuantity'] == 95
    
    def test_inventory_insufficient_stock(self):
        """Test inventory operations with insufficient stock"""
        product_id = 'prod_low_stock'
        
        # Create low stock item
        inventory_item = {
            'productId': product_id,
            'availableQuantity': 2,
            'reservedQuantity': 0
        }
        
        self.inventory_table.put_item(Item=inventory_item)
        
        # Try to deduct more than available
        quantity_to_deduct = 5
        
        with pytest.raises(Exception):  # Should raise ConditionalCheckFailedException
            self.inventory_table.update_item(
                Key={'productId': product_id},
                UpdateExpression='SET availableQuantity = availableQuantity - :quantity',
                ExpressionAttributeValues={
                    ':quantity': quantity_to_deduct,
                    ':minQuantity': quantity_to_deduct
                },
                ConditionExpression='availableQuantity >= :minQuantity'
            )
    
    def test_order_operations(self):
        """Test order management operations"""
        order_id = 'ORD-12345678'
        user_id = 'user_123'
        
        # Create order
        order = {
            'orderId': order_id,
            'userId': user_id,
            'status': 'confirmed',
            'items': [
                {
                    'productId': 'prod_1',
                    'quantity': 2,
                    'price': 99.99,
                    'subtotal': 199.98
                }
            ],
            'totalAmount': Decimal('199.98'),
            'orderDate': datetime.utcnow().isoformat(),
            'createdAt': datetime.utcnow().isoformat()
        }
        
        self.orders_table.put_item(Item=order)
        
        # Test order retrieval
        response = self.orders_table.get_item(
            Key={'orderId': order_id}
        )
        assert 'Item' in response
        assert response['Item']['userId'] == user_id
        assert response['Item']['status'] == 'confirmed'
        
        # Test order status update
        self.orders_table.update_item(
            Key={'orderId': order_id},
            UpdateExpression='SET #status = :status, updatedAt = :updated',
            ExpressionAttributeNames={'#status': 'status'},
            ExpressionAttributeValues={
                ':status': 'shipped',
                ':updated': datetime.utcnow().isoformat()
            }
        )
        
        # Verify status update
        response = self.orders_table.get_item(
            Key={'orderId': order_id}
        )
        assert response['Item']['status'] == 'shipped'
    
    def test_user_orders_query(self):
        """Test querying orders by user using GSI"""
        user_id = 'user_123'
        
        # Create multiple orders for user
        orders = [
            {
                'orderId': 'ORD-001',
                'userId': user_id,
                'status': 'delivered',
                'totalAmount': Decimal('100.00'),
                'orderDate': (datetime.utcnow() - timedelta(days=5)).isoformat()
            },
            {
                'orderId': 'ORD-002',
                'userId': user_id,
                'status': 'shipped',
                'totalAmount': Decimal('200.00'),
                'orderDate': (datetime.utcnow() - timedelta(days=2)).isoformat()
            },
            {
                'orderId': 'ORD-003',
                'userId': user_id,
                'status': 'confirmed',
                'totalAmount': Decimal('150.00'),
                'orderDate': datetime.utcnow().isoformat()
            }
        ]
        
        for order in orders:
            self.orders_table.put_item(Item=order)
        
        # Query orders by user
        response = self.orders_table.query(
            IndexName='UserOrdersIndex',
            KeyConditionExpression='userId = :userId',
            ExpressionAttributeValues={':userId': user_id},
            ScanIndexForward=False  # Most recent first
        )
        
        assert len(response['Items']) == 3
        
        # Verify order (should be sorted by most recent first)
        order_dates = [order['orderDate'] for order in response['Items']]
        assert order_dates == sorted(order_dates, reverse=True)
    
    def test_search_analytics_operations(self):
        """Test search analytics data operations"""
        search_term = 'wireless headphones'
        timestamp = datetime.utcnow().isoformat()
        
        # Record search event
        search_event = {
            'searchTerm': search_term.lower(),
            'timestamp': timestamp,
            'filters': json.dumps({'category': 'Electronics'}),
            'date': datetime.utcnow().strftime('%Y-%m-%d'),
            'hour': datetime.utcnow().strftime('%Y-%m-%d-%H'),
            'userId': 'user_123',
            'sessionId': 'session_456'
        }
        
        self.search_analytics_table.put_item(Item=search_event)
        
        # Query search events for term
        response = self.search_analytics_table.query(
            KeyConditionExpression='searchTerm = :term',
            ExpressionAttributeValues={':term': search_term.lower()}
        )
        
        assert len(response['Items']) == 1
        assert response['Items'][0]['searchTerm'] == search_term.lower()
        
        # Test batch insert for analytics
        batch_events = []
        for i in range(5):
            event_time = (datetime.utcnow() - timedelta(minutes=i)).isoformat()
            batch_events.append({
                'searchTerm': search_term.lower(),
                'timestamp': event_time,
                'filters': json.dumps({}),
                'date': datetime.utcnow().strftime('%Y-%m-%d'),
                'hour': datetime.utcnow().strftime('%Y-%m-%d-%H')
            })
        
        # Batch write
        with self.search_analytics_table.batch_writer() as batch:
            for event in batch_events:
                batch.put_item(Item=event)
        
        # Verify batch insert
        response = self.search_analytics_table.query(
            KeyConditionExpression='searchTerm = :term',
            ExpressionAttributeValues={':term': search_term.lower()}
        )
        
        assert len(response['Items']) == 6  # 1 original + 5 batch
    
    def test_transaction_operations(self):
        """Test DynamoDB transaction operations"""
        user_id = 'user_123'
        order_id = 'ORD-TRANSACTION-TEST'
        product_id = 'prod_transaction'
        quantity_ordered = 3
        
        # Set up initial inventory
        inventory_item = {
            'productId': product_id,
            'availableQuantity': 10,
            'reservedQuantity': 0
        }
        self.inventory_table.put_item(Item=inventory_item)
        
        # Create order with transaction (order creation + inventory deduction)
        order = {
            'orderId': order_id,
            'userId': user_id,
            'status': 'confirmed',
            'items': [
                {
                    'productId': product_id,
                    'quantity': quantity_ordered,
                    'price': 50.00
                }
            ],
            'totalAmount': Decimal('150.00'),
            'orderDate': datetime.utcnow().isoformat()
        }
        
        # Execute transaction
        dynamodb_client = boto3.client('dynamodb', region_name='us-west-2')
        
        try:
            dynamodb_client.transact_write_items(
                TransactItems=[
                    {
                        'Put': {
                            'TableName': 'test-orders',
                            'Item': {
                                'orderId': {'S': order_id},
                                'userId': {'S': user_id},
                                'status': {'S': 'confirmed'},
                                'totalAmount': {'N': '150.00'},
                                'orderDate': {'S': datetime.utcnow().isoformat()}
                            },
                            'ConditionExpression': 'attribute_not_exists(orderId)'
                        }
                    },
                    {
                        'Update': {
                            'TableName': 'test-inventory',
                            'Key': {'productId': {'S': product_id}},
                            'UpdateExpression': 'SET availableQuantity = availableQuantity - :quantity',
                            'ExpressionAttributeValues': {
                                ':quantity': {'N': str(quantity_ordered)},
                                ':minQuantity': {'N': str(quantity_ordered)}
                            },
                            'ConditionExpression': 'availableQuantity >= :minQuantity'
                        }
                    }
                ]
            )
            
            # Verify transaction success
            # Check order was created
            order_response = self.orders_table.get_item(
                Key={'orderId': order_id}
            )
            assert 'Item' in order_response
            
            # Check inventory was deducted
            inventory_response = self.inventory_table.get_item(
                Key={'productId': product_id}
            )
            assert inventory_response['Item']['availableQuantity'] == 7  # 10 - 3
            
        except Exception as e:
            pytest.fail(f"Transaction failed: {e}")
    
    def test_transaction_rollback(self):
        """Test transaction rollback on failure"""
        user_id = 'user_123'
        order_id = 'ORD-ROLLBACK-TEST'
        product_id = 'prod_rollback'
        quantity_ordered = 15  # More than available
        
        # Set up initial inventory (insufficient stock)
        inventory_item = {
            'productId': product_id,
            'availableQuantity': 5,  # Less than ordered quantity
            'reservedQuantity': 0
        }
        self.inventory_table.put_item(Item=inventory_item)
        
        # Attempt transaction that should fail
        dynamodb_client = boto3.client('dynamodb', region_name='us-west-2')
        
        with pytest.raises(Exception):  # Should raise TransactionCanceledException
            dynamodb_client.transact_write_items(
                TransactItems=[
                    {
                        'Put': {
                            'TableName': 'test-orders',
                            'Item': {
                                'orderId': {'S': order_id},
                                'userId': {'S': user_id},
                                'status': {'S': 'confirmed'},
                                'totalAmount': {'N': '750.00'}
                            },
                            'ConditionExpression': 'attribute_not_exists(orderId)'
                        }
                    },
                    {
                        'Update': {
                            'TableName': 'test-inventory',
                            'Key': {'productId': {'S': product_id}},
                            'UpdateExpression': 'SET availableQuantity = availableQuantity - :quantity',
                            'ExpressionAttributeValues': {
                                ':quantity': {'N': str(quantity_ordered)},
                                ':minQuantity': {'N': str(quantity_ordered)}
                            },
                            'ConditionExpression': 'availableQuantity >= :minQuantity'
                        }
                    }
                ]
            )
        
        # Verify rollback - order should not exist
        order_response = self.orders_table.get_item(
            Key={'orderId': order_id}
        )
        assert 'Item' not in order_response
        
        # Verify rollback - inventory should be unchanged
        inventory_response = self.inventory_table.get_item(
            Key={'productId': product_id}
        )
        assert inventory_response['Item']['availableQuantity'] == 5  # Unchanged
    
    def test_conditional_updates(self):
        """Test conditional update operations"""
        user_id = 'user_conditional'
        product_id = 'prod_conditional'
        
        # Create initial cart item
        cart_item = {
            'userId': user_id,
            'productId': product_id,
            'quantity': 1,
            'price': Decimal('99.99'),
            'version': 1
        }
        self.cart_table.put_item(Item=cart_item)
        
        # Test successful conditional update
        self.cart_table.update_item(
            Key={'userId': user_id, 'productId': product_id},
            UpdateExpression='SET quantity = :quantity, version = version + :inc',
            ExpressionAttributeValues={
                ':quantity': 2,
                ':inc': 1,
                ':expectedVersion': 1
            },
            ConditionExpression='version = :expectedVersion'
        )
        
        # Verify update
        response = self.cart_table.get_item(
            Key={'userId': user_id, 'productId': product_id}
        )
        assert response['Item']['quantity'] == 2
        assert response['Item']['version'] == 2
        
        # Test failed conditional update (wrong version)
        with pytest.raises(Exception):  # Should raise ConditionalCheckFailedException
            self.cart_table.update_item(
                Key={'userId': user_id, 'productId': product_id},
                UpdateExpression='SET quantity = :quantity',
                ExpressionAttributeValues={
                    ':quantity': 3,
                    ':expectedVersion': 1  # Wrong version
                },
                ConditionExpression='version = :expectedVersion'
            )
    
    def test_ttl_operations(self):
        """Test TTL (Time To Live) operations"""
        user_id = 'user_ttl'
        product_id = 'prod_ttl'
        
        # Create cart item with TTL
        ttl_timestamp = int((datetime.utcnow() + timedelta(seconds=5)).timestamp())
        cart_item = {
            'userId': user_id,
            'productId': product_id,
            'quantity': 1,
            'price': Decimal('99.99'),
            'ttl': ttl_timestamp
        }
        
        self.cart_table.put_item(Item=cart_item)
        
        # Verify item exists
        response = self.cart_table.get_item(
            Key={'userId': user_id, 'productId': product_id}
        )
        assert 'Item' in response
        assert response['Item']['ttl'] == ttl_timestamp
        
        # Note: In real DynamoDB, TTL deletion happens automatically
        # In moto, we need to simulate this behavior
        # For testing purposes, we verify the TTL attribute is set correctly
    
    def test_batch_operations(self):
        """Test batch read and write operations"""
        user_id = 'user_batch'
        
        # Batch write multiple cart items
        items_to_write = []
        for i in range(5):
            items_to_write.append({
                'userId': user_id,
                'productId': f'prod_{i}',
                'quantity': i + 1,
                'price': Decimal(f'{(i + 1) * 10}.99')
            })
        
        # Batch write
        with self.cart_table.batch_writer() as batch:
            for item in items_to_write:
                batch.put_item(Item=item)
        
        # Verify batch write
        response = self.cart_table.query(
            KeyConditionExpression='userId = :userId',
            ExpressionAttributeValues={':userId': user_id}
        )
        assert len(response['Items']) == 5
        
        # Test batch read
        keys_to_read = [
            {'userId': user_id, 'productId': 'prod_0'},
            {'userId': user_id, 'productId': 'prod_2'},
            {'userId': user_id, 'productId': 'prod_4'}
        ]
        
        dynamodb_client = boto3.client('dynamodb', region_name='us-west-2')
        batch_response = dynamodb_client.batch_get_item(
            RequestItems={
                'test-shopping-cart': {
                    'Keys': [
                        {
                            'userId': {'S': user_id},
                            'productId': {'S': 'prod_0'}
                        },
                        {
                            'userId': {'S': user_id},
                            'productId': {'S': 'prod_2'}
                        },
                        {
                            'userId': {'S': user_id},
                            'productId': {'S': 'prod_4'}
                        }
                    ]
                }
            }
        )
        
        assert len(batch_response['Responses']['test-shopping-cart']) == 3


if __name__ == '__main__':
    pytest.main([__file__])