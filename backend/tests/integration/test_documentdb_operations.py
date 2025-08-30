"""
Integration tests for DocumentDB operations
Tests CRUD operations, vector search, and aggregation pipelines
"""
import pytest
import pymongo
from pymongo import MongoClient
import json
import time
from datetime import datetime, timezone
from bson import ObjectId
import numpy as np
import sys
import os
from unittest.mock import patch, MagicMock

# Add the shared directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'shared'))

class TestDocumentDBOperations:
    """Integration tests for DocumentDB operations"""
    
    def setup_method(self):
        """Set up test DocumentDB connection and collections"""
        # Use MongoDB for testing (compatible with DocumentDB)
        try:
            self.client = MongoClient('mongodb://localhost:27017/', serverSelectionTimeoutMS=1000)
            # Test connection
            self.client.server_info()
            self.db = self.client['test_nosql_workshop']
        except Exception:
            # If MongoDB is not available, use mock
            pytest.skip("MongoDB not available for integration tests")
        
        # Get collection references
        self.products_collection = self.db['products']
        self.reviews_collection = self.db['reviews']
        self.knowledge_base_collection = self.db['knowledge_base']
        
        # Clean up collections before each test
        self.products_collection.delete_many({})
        self.reviews_collection.delete_many({})
        self.knowledge_base_collection.delete_many({})
    
    def teardown_method(self):
        """Clean up after each test"""
        if hasattr(self, 'client'):
            self.client.close()
    
    def test_product_crud_operations(self):
        """Test product CRUD operations"""
        # Create product
        product = {
            'product_id': 'prod_123',
            'title': 'Wireless Bluetooth Headphones',
            'description': 'High-quality wireless headphones with noise cancellation',
            'price': 199.99,
            'category': 'Electronics',
            'tags': ['wireless', 'bluetooth', 'headphones', 'audio'],
            'rating': 4.5,
            'review_count': 150,
            'in_stock': True,
            'image_url': 'https://example.com/headphones.jpg',
            'specifications': {
                'battery_life': '30 hours',
                'connectivity': 'Bluetooth 5.0',
                'weight': '250g'
            },
            'created_at': datetime.now(timezone.utc),
            'updated_at': datetime.now(timezone.utc)
        }
        
        # Test CREATE
        result = self.products_collection.insert_one(product)
        assert result.inserted_id is not None
        
        # Test READ
        found_product = self.products_collection.find_one({'product_id': 'prod_123'})
        assert found_product is not None
        assert found_product['title'] == 'Wireless Bluetooth Headphones'
        assert found_product['price'] == 199.99
        assert found_product['category'] == 'Electronics'
        
        # Test UPDATE
        update_result = self.products_collection.update_one(
            {'product_id': 'prod_123'},
            {
                '$set': {
                    'price': 179.99,
                    'rating': 4.6,
                    'updated_at': datetime.now(timezone.utc)
                },
                '$inc': {'review_count': 1}
            }
        )
        assert update_result.modified_count == 1
        
        # Verify update
        updated_product = self.products_collection.find_one({'product_id': 'prod_123'})
        assert updated_product['price'] == 179.99
        assert updated_product['rating'] == 4.6
        assert updated_product['review_count'] == 151
        
        # Test DELETE
        delete_result = self.products_collection.delete_one({'product_id': 'prod_123'})
        assert delete_result.deleted_count == 1
        
        # Verify deletion
        deleted_product = self.products_collection.find_one({'product_id': 'prod_123'})
        assert deleted_product is None
    
    def test_product_search_operations(self):
        """Test product search and filtering operations"""
        # Insert test products
        products = [
            {
                'product_id': 'prod_1',
                'title': 'Wireless Bluetooth Headphones',
                'description': 'Premium wireless headphones',
                'price': 199.99,
                'category': 'Electronics',
                'tags': ['wireless', 'bluetooth', 'headphones'],
                'rating': 4.5,
                'in_stock': True
            },
            {
                'product_id': 'prod_2',
                'title': 'Wired Gaming Headphones',
                'description': 'Professional gaming headphones',
                'price': 149.99,
                'category': 'Electronics',
                'tags': ['wired', 'gaming', 'headphones'],
                'rating': 4.2,
                'in_stock': True
            },
            {
                'product_id': 'prod_3',
                'title': 'Bluetooth Speaker',
                'description': 'Portable bluetooth speaker',
                'price': 79.99,
                'category': 'Electronics',
                'tags': ['bluetooth', 'speaker', 'portable'],
                'rating': 4.0,
                'in_stock': False
            },
            {
                'product_id': 'prod_4',
                'title': 'Wireless Mouse',
                'description': 'Ergonomic wireless mouse',
                'price': 29.99,
                'category': 'Electronics',
                'tags': ['wireless', 'mouse', 'ergonomic'],
                'rating': 4.3,
                'in_stock': True
            }
        ]
        
        self.products_collection.insert_many(products)
        
        # Test text search
        text_search_results = list(self.products_collection.find({
            '$or': [
                {'title': {'$regex': 'wireless', '$options': 'i'}},
                {'description': {'$regex': 'wireless', '$options': 'i'}},
                {'tags': {'$in': ['wireless']}}
            ]
        }))
        assert len(text_search_results) == 2  # Wireless headphones and mouse
        
        # Test category filter
        electronics_products = list(self.products_collection.find({
            'category': 'Electronics'
        }))
        assert len(electronics_products) == 4
        
        # Test price range filter
        price_range_products = list(self.products_collection.find({
            'price': {'$gte': 50, '$lte': 200}
        }))
        assert len(price_range_products) == 3  # Excludes the $29.99 mouse
        
        # Test rating filter
        high_rated_products = list(self.products_collection.find({
            'rating': {'$gte': 4.2}
        }))
        assert len(high_rated_products) == 3
        
        # Test stock filter
        in_stock_products = list(self.products_collection.find({
            'in_stock': True
        }))
        assert len(in_stock_products) == 3
        
        # Test complex query with multiple filters
        complex_query_results = list(self.products_collection.find({
            '$and': [
                {'category': 'Electronics'},
                {'price': {'$lte': 150}},
                {'rating': {'$gte': 4.0}},
                {'in_stock': True}
            ]
        }))
        assert len(complex_query_results) == 2  # Gaming headphones and mouse
    
    def test_product_aggregation_operations(self):
        """Test product aggregation pipelines"""
        # Insert test products with various categories and prices
        products = [
            {'product_id': 'p1', 'category': 'Electronics', 'price': 100, 'rating': 4.5, 'review_count': 50},
            {'product_id': 'p2', 'category': 'Electronics', 'price': 200, 'rating': 4.2, 'review_count': 30},
            {'product_id': 'p3', 'category': 'Electronics', 'price': 150, 'rating': 4.8, 'review_count': 80},
            {'product_id': 'p4', 'category': 'Clothing', 'price': 50, 'rating': 4.0, 'review_count': 20},
            {'product_id': 'p5', 'category': 'Clothing', 'price': 75, 'rating': 4.3, 'review_count': 40},
            {'product_id': 'p6', 'category': 'Home', 'price': 300, 'rating': 4.6, 'review_count': 60}
        ]
        
        self.products_collection.insert_many(products)
        
        # Test category aggregation
        category_stats = list(self.products_collection.aggregate([
            {
                '$group': {
                    '_id': '$category',
                    'count': {'$sum': 1},
                    'avg_price': {'$avg': '$price'},
                    'avg_rating': {'$avg': '$rating'},
                    'total_reviews': {'$sum': '$review_count'}
                }
            },
            {'$sort': {'count': -1}}
        ]))
        
        assert len(category_stats) == 3
        electronics_stats = next(stat for stat in category_stats if stat['_id'] == 'Electronics')
        assert electronics_stats['count'] == 3
        assert electronics_stats['avg_price'] == 150.0  # (100 + 200 + 150) / 3
        
        # Test price range aggregation
        price_ranges = list(self.products_collection.aggregate([
            {
                '$bucket': {
                    'groupBy': '$price',
                    'boundaries': [0, 100, 200, 400],
                    'default': 'Other',
                    'output': {
                        'count': {'$sum': 1},
                        'products': {'$push': '$product_id'}
                    }
                }
            }
        ]))
        
        assert len(price_ranges) >= 2
        
        # Test top-rated products
        top_rated = list(self.products_collection.aggregate([
            {'$match': {'rating': {'$gte': 4.5}}},
            {'$sort': {'rating': -1, 'review_count': -1}},
            {'$limit': 3},
            {'$project': {'product_id': 1, 'rating': 1, 'review_count': 1}}
        ]))
        
        assert len(top_rated) == 3
        assert top_rated[0]['rating'] >= 4.5
    
    def test_review_crud_operations(self):
        """Test review CRUD operations"""
        # Create review
        review = {
            'review_id': 'review_123',
            'product_id': 'prod_456',
            'user_id': 'user_789',
            'user_name': 'John Doe',
            'rating': 5,
            'title': 'Excellent product!',
            'content': 'I absolutely love this product. The quality is outstanding and it works perfectly.',
            'is_verified_purchase': True,
            'helpful_count': 15,
            'not_helpful_count': 2,
            'helpful_votes': ['user_1', 'user_2', 'user_3'],
            'not_helpful_votes': ['user_4'],
            'images': ['image1.jpg', 'image2.jpg'],
            'aspect_ratings': {
                'quality': 5,
                'value': 4,
                'comfort': 5,
                'design': 4
            },
            'sentiment': {
                'score': 0.8,
                'label': 'positive',
                'confidence': 0.9,
                'aspects': {
                    'quality': 0.9,
                    'value': 0.7,
                    'comfort': 0.8,
                    'design': 0.6
                }
            },
            'created_at': datetime.now(timezone.utc),
            'updated_at': datetime.now(timezone.utc)
        }
        
        # Test CREATE
        result = self.reviews_collection.insert_one(review)
        assert result.inserted_id is not None
        
        # Test READ
        found_review = self.reviews_collection.find_one({'review_id': 'review_123'})
        assert found_review is not None
        assert found_review['rating'] == 5
        assert found_review['title'] == 'Excellent product!'
        assert found_review['is_verified_purchase'] is True
        
        # Test UPDATE (helpful vote)
        update_result = self.reviews_collection.update_one(
            {'review_id': 'review_123'},
            {
                '$inc': {'helpful_count': 1},
                '$push': {'helpful_votes': 'user_5'},
                '$set': {'updated_at': datetime.now(timezone.utc)}
            }
        )
        assert update_result.modified_count == 1
        
        # Verify update
        updated_review = self.reviews_collection.find_one({'review_id': 'review_123'})
        assert updated_review['helpful_count'] == 16
        assert 'user_5' in updated_review['helpful_votes']
        
        # Test DELETE
        delete_result = self.reviews_collection.delete_one({'review_id': 'review_123'})
        assert delete_result.deleted_count == 1
    
    def test_review_aggregation_operations(self):
        """Test review aggregation for product insights"""
        product_id = 'prod_test'
        
        # Insert test reviews
        reviews = [
            {
                'review_id': 'r1',
                'product_id': product_id,
                'rating': 5,
                'sentiment': {'score': 0.8, 'aspects': {'quality': 0.9, 'value': 0.7}},
                'created_at': datetime(2024, 1, 15)
            },
            {
                'review_id': 'r2',
                'product_id': product_id,
                'rating': 4,
                'sentiment': {'score': 0.6, 'aspects': {'quality': 0.7, 'value': 0.8}},
                'created_at': datetime(2024, 1, 20)
            },
            {
                'review_id': 'r3',
                'product_id': product_id,
                'rating': 5,
                'sentiment': {'score': 0.9, 'aspects': {'quality': 0.8, 'value': 0.9}},
                'created_at': datetime(2024, 2, 10)
            },
            {
                'review_id': 'r4',
                'product_id': product_id,
                'rating': 3,
                'sentiment': {'score': 0.2, 'aspects': {'quality': 0.3, 'value': 0.4}},
                'created_at': datetime(2024, 2, 15)
            }
        ]
        
        self.reviews_collection.insert_many(reviews)
        
        # Test review summary aggregation
        summary = list(self.reviews_collection.aggregate([
            {'$match': {'product_id': product_id}},
            {
                '$group': {
                    '_id': None,
                    'total_reviews': {'$sum': 1},
                    'average_rating': {'$avg': '$rating'},
                    'rating_distribution': {'$push': '$rating'},
                    'avg_sentiment': {'$avg': '$sentiment.score'}
                }
            }
        ]))
        
        assert len(summary) == 1
        assert summary[0]['total_reviews'] == 4
        assert summary[0]['average_rating'] == 4.25  # (5+4+5+3)/4
        
        # Test rating distribution
        rating_dist = list(self.reviews_collection.aggregate([
            {'$match': {'product_id': product_id}},
            {
                '$group': {
                    '_id': '$rating',
                    'count': {'$sum': 1}
                }
            },
            {'$sort': {'_id': -1}}
        ]))
        
        rating_counts = {item['_id']: item['count'] for item in rating_dist}
        assert rating_counts[5] == 2
        assert rating_counts[4] == 1
        assert rating_counts[3] == 1
        
        # Test monthly sentiment trends
        monthly_trends = list(self.reviews_collection.aggregate([
            {'$match': {'product_id': product_id}},
            {
                '$group': {
                    '_id': {
                        'year': {'$year': '$created_at'},
                        'month': {'$month': '$created_at'}
                    },
                    'avg_sentiment': {'$avg': '$sentiment.score'},
                    'review_count': {'$sum': 1}
                }
            },
            {'$sort': {'_id.year': 1, '_id.month': 1}}
        ]))
        
        assert len(monthly_trends) == 2  # January and February 2024
    
    def test_vector_search_simulation(self):
        """Test vector search simulation (DocumentDB vector search)"""
        # Insert products with simulated embeddings
        products_with_embeddings = [
            {
                'product_id': 'p1',
                'title': 'Wireless Bluetooth Headphones',
                'description': 'High-quality audio with noise cancellation',
                'category': 'Electronics',
                'embedding': [0.1, 0.2, 0.3, 0.4, 0.5]  # Simulated embedding
            },
            {
                'product_id': 'p2',
                'title': 'Gaming Headset',
                'description': 'Professional gaming headset with microphone',
                'category': 'Electronics',
                'embedding': [0.15, 0.25, 0.35, 0.45, 0.55]  # Similar to p1
            },
            {
                'product_id': 'p3',
                'title': 'Bluetooth Speaker',
                'description': 'Portable wireless speaker',
                'category': 'Electronics',
                'embedding': [0.8, 0.7, 0.6, 0.5, 0.4]  # Different from headphones
            }
        ]
        
        self.products_collection.insert_many(products_with_embeddings)
        
        # Simulate vector search by calculating cosine similarity
        query_embedding = [0.12, 0.22, 0.32, 0.42, 0.52]  # Similar to headphones
        
        # In real DocumentDB, this would use vector search index
        # For testing, we'll simulate with a simple similarity calculation
        products = list(self.products_collection.find({}))
        
        def cosine_similarity(a, b):
            """Calculate cosine similarity between two vectors"""
            dot_product = sum(x * y for x, y in zip(a, b))
            magnitude_a = sum(x * x for x in a) ** 0.5
            magnitude_b = sum(x * x for x in b) ** 0.5
            return dot_product / (magnitude_a * magnitude_b)
        
        # Calculate similarities
        for product in products:
            similarity = cosine_similarity(query_embedding, product['embedding'])
            product['similarity_score'] = similarity
        
        # Sort by similarity
        products.sort(key=lambda x: x['similarity_score'], reverse=True)
        
        # Verify results
        assert products[0]['product_id'] in ['p1', 'p2']  # Should be headphones
        assert products[0]['similarity_score'] > products[2]['similarity_score']
    
    def test_knowledge_base_operations(self):
        """Test knowledge base CRUD and search operations"""
        # Insert knowledge base articles
        articles = [
            {
                'article_id': 'kb_1',
                'title': 'Return Policy',
                'content': 'You can return items within 30 days of purchase. Items must be in original condition.',
                'category': 'policies',
                'tags': ['return', 'policy', 'refund'],
                'created_at': datetime.now(timezone.utc),
                'updated_at': datetime.now(timezone.utc)
            },
            {
                'article_id': 'kb_2',
                'title': 'Shipping Information',
                'content': 'We offer free shipping on orders over $50. Standard shipping takes 3-5 business days.',
                'category': 'shipping',
                'tags': ['shipping', 'delivery', 'free'],
                'created_at': datetime.now(timezone.utc),
                'updated_at': datetime.now(timezone.utc)
            },
            {
                'article_id': 'kb_3',
                'title': 'Product Warranty',
                'content': 'All electronics come with a 1-year manufacturer warranty. Extended warranties available.',
                'category': 'warranty',
                'tags': ['warranty', 'electronics', 'protection'],
                'created_at': datetime.now(timezone.utc),
                'updated_at': datetime.now(timezone.utc)
            }
        ]
        
        self.knowledge_base_collection.insert_many(articles)
        
        # Test search by category
        policy_articles = list(self.knowledge_base_collection.find({
            'category': 'policies'
        }))
        assert len(policy_articles) == 1
        assert policy_articles[0]['title'] == 'Return Policy'
        
        # Test text search
        shipping_articles = list(self.knowledge_base_collection.find({
            '$or': [
                {'title': {'$regex': 'shipping', '$options': 'i'}},
                {'content': {'$regex': 'shipping', '$options': 'i'}},
                {'tags': {'$in': ['shipping']}}
            ]
        }))
        assert len(shipping_articles) == 1
        
        # Test tag search
        electronics_articles = list(self.knowledge_base_collection.find({
            'tags': {'$in': ['electronics']}
        }))
        assert len(electronics_articles) == 1
        assert electronics_articles[0]['title'] == 'Product Warranty'
    
    def test_index_operations(self):
        """Test index creation and usage"""
        # Create indexes for better query performance
        
        # Product indexes
        self.products_collection.create_index([('product_id', 1)], unique=True)
        self.products_collection.create_index([('category', 1)])
        self.products_collection.create_index([('price', 1)])
        self.products_collection.create_index([('rating', -1)])
        self.products_collection.create_index([('tags', 1)])
        
        # Compound index for common queries
        self.products_collection.create_index([
            ('category', 1),
            ('price', 1),
            ('rating', -1)
        ])
        
        # Text index for search
        self.products_collection.create_index([
            ('title', 'text'),
            ('description', 'text'),
            ('tags', 'text')
        ])
        
        # Review indexes
        self.reviews_collection.create_index([('review_id', 1)], unique=True)
        self.reviews_collection.create_index([('product_id', 1)])
        self.reviews_collection.create_index([('user_id', 1)])
        self.reviews_collection.create_index([('created_at', -1)])
        self.reviews_collection.create_index([('rating', -1)])
        
        # Compound index for product reviews
        self.reviews_collection.create_index([
            ('product_id', 1),
            ('created_at', -1)
        ])
        
        # Verify indexes were created
        product_indexes = list(self.products_collection.list_indexes())
        review_indexes = list(self.reviews_collection.list_indexes())
        
        # Should have more than just the default _id index
        assert len(product_indexes) > 1
        assert len(review_indexes) > 1
        
        # Test that queries use indexes (explain would show this in real MongoDB)
        # For testing, we just verify the indexes exist
        index_names = [idx['name'] for idx in product_indexes]
        assert any('product_id' in name for name in index_names)
        assert any('category' in name for name in index_names)
    
    def test_bulk_operations(self):
        """Test bulk insert, update, and delete operations"""
        # Bulk insert
        bulk_products = []
        for i in range(100):
            bulk_products.append({
                'product_id': f'bulk_prod_{i}',
                'title': f'Product {i}',
                'price': 10.0 + i,
                'category': 'Electronics' if i % 2 == 0 else 'Clothing',
                'rating': 3.0 + (i % 3),
                'created_at': datetime.now(timezone.utc)
            })
        
        # Bulk insert
        bulk_result = self.products_collection.insert_many(bulk_products)
        assert len(bulk_result.inserted_ids) == 100
        
        # Bulk update
        bulk_update_result = self.products_collection.update_many(
            {'category': 'Electronics'},
            {'$set': {'updated_at': datetime.now(timezone.utc)}}
        )
        assert bulk_update_result.modified_count == 50  # Half are Electronics
        
        # Bulk delete
        bulk_delete_result = self.products_collection.delete_many(
            {'price': {'$lt': 50}}
        )
        assert bulk_delete_result.deleted_count == 40  # Products 0-39 have price < 50
        
        # Verify remaining count
        remaining_count = self.products_collection.count_documents({})
        assert remaining_count == 60
    
    def test_transaction_operations(self):
        """Test multi-document transactions"""
        # Note: Transactions require MongoDB 4.0+ and replica set
        # For testing purposes, we'll simulate transaction-like behavior
        
        product_id = 'prod_transaction'
        review_id = 'review_transaction'
        
        # Simulate atomic operation: insert product and review together
        try:
            # In a real transaction, these would be wrapped in a session
            product = {
                'product_id': product_id,
                'title': 'Transaction Test Product',
                'rating': 0,
                'review_count': 0
            }
            
            review = {
                'review_id': review_id,
                'product_id': product_id,
                'rating': 5,
                'content': 'Great product!'
            }
            
            # Insert product
            product_result = self.products_collection.insert_one(product)
            
            # Insert review
            review_result = self.reviews_collection.insert_one(review)
            
            # Update product with review stats
            self.products_collection.update_one(
                {'product_id': product_id},
                {
                    '$set': {'rating': 5},
                    '$inc': {'review_count': 1}
                }
            )
            
            # Verify all operations succeeded
            assert product_result.inserted_id is not None
            assert review_result.inserted_id is not None
            
            updated_product = self.products_collection.find_one({'product_id': product_id})
            assert updated_product['rating'] == 5
            assert updated_product['review_count'] == 1
            
        except Exception as e:
            # In a real transaction, this would trigger rollback
            pytest.fail(f"Transaction simulation failed: {e}")


if __name__ == '__main__':
    pytest.main([__file__])