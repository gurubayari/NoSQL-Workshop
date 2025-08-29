"""
Unit tests for Review API Lambda function
"""
import unittest
from unittest.mock import Mock, patch, MagicMock
import json
import sys
import os
from datetime import datetime, timezone

# Add the functions directory to the path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'functions'))
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'shared'))

from review_api import ReviewAPI, lambda_handler

class TestReviewAPI(unittest.TestCase):
    """Test cases for ReviewAPI class"""
    
    def setUp(self):
        """Set up test fixtures"""
        # Mock database connections
        self.mock_reviews_collection = Mock()
        self.mock_users_table = Mock()
        self.mock_orders_table = Mock()
        
        # Patch database connections
        self.db_patcher = patch('review_api.get_documentdb_collection')
        self.dynamodb_patcher = patch('review_api.get_dynamodb_table')
        self.cache_get_patcher = patch('review_api.cache_get')
        self.cache_set_patcher = patch('review_api.cache_set')
        self.cache_delete_patcher = patch('review_api.cache_delete')
        self.bedrock_patcher = patch('review_api.bedrock_client')
        
        self.mock_get_collection = self.db_patcher.start()
        self.mock_get_table = self.dynamodb_patcher.start()
        self.mock_cache_get = self.cache_get_patcher.start()
        self.mock_cache_set = self.cache_set_patcher.start()
        self.mock_cache_delete = self.cache_delete_patcher.start()
        self.mock_bedrock = self.bedrock_patcher.start()
        
        # Configure mocks
        self.mock_get_collection.return_value = self.mock_reviews_collection
        self.mock_get_table.side_effect = lambda table_name: {
            'unicorn-ecommerce-dev-users': self.mock_users_table,
            'unicorn-ecommerce-dev-orders': self.mock_orders_table
        }.get(table_name, Mock())
        
        self.mock_cache_get.return_value = None
        self.mock_cache_set.return_value = True
        self.mock_cache_delete.return_value = True
        
        # Initialize API
        self.api = ReviewAPI()
    
    def tearDown(self):
        """Clean up test fixtures"""
        self.db_patcher.stop()
        self.dynamodb_patcher.stop()
        self.cache_get_patcher.stop()
        self.cache_set_patcher.stop()
        self.cache_delete_patcher.stop()
        self.bedrock_patcher.stop()
    
    def test_create_review_success(self):
        """Test successful review creation"""
        # Mock successful insertion
        mock_result = Mock()
        mock_result.inserted_id = 'mock_object_id'
        self.mock_reviews_collection.find_one.return_value = None  # No existing review
        self.mock_reviews_collection.insert_one.return_value = mock_result
        
        # Mock verified purchase check
        self.mock_orders_table.scan.return_value = {
            'Items': [{
                'userId': 'user123',
                'items': [{'productId': 'product123'}]
            }]
        }
        
        # Mock Bedrock sentiment analysis
        self.mock_bedrock.invoke_model.return_value = {
            'body': Mock(read=lambda: json.dumps({
                'content': [{
                    'text': json.dumps({
                        'score': 0.8,
                        'label': 'positive',
                        'confidence': 0.9,
                        'aspects': {
                            'quality': 0.8,
                            'value': 0.7,
                            'comfort': 0.6,
                            'design': 0.5,
                            'durability': 0.4
                        }
                    })
                }]
            }).encode())
        }
        
        # Test data
        review_data = {
            'userId': 'user123',
            'productId': 'product123',
            'rating': 5,
            'title': 'Great product!',
            'content': 'This is an excellent product with great quality and value.',
            'aspectRatings': {
                'quality': 5,
                'value': 4
            }
        }
        
        # Execute
        result = self.api.create_review(review_data)
        
        # Verify
        self.assertEqual(result['statusCode'], 201)
        response_body = json.loads(result['body'])
        self.assertEqual(response_body['message'], 'Review created successfully')
        self.assertIn('reviewId', response_body)
        self.assertTrue(response_body['isVerifiedPurchase'])
        
        # Verify database calls
        self.mock_reviews_collection.find_one.assert_called_once()
        self.mock_reviews_collection.insert_one.assert_called_once()
        self.mock_cache_delete.assert_called()
    
    def test_create_review_missing_fields(self):
        """Test review creation with missing required fields"""
        review_data = {
            'userId': 'user123',
            # Missing productId and rating
            'title': 'Great product!',
            'content': 'This is an excellent product.'
        }
        
        result = self.api.create_review(review_data)
        
        self.assertEqual(result['statusCode'], 400)
        response_body = json.loads(result['body'])
        self.assertIn('Missing required fields', response_body['error'])
    
    def test_create_review_invalid_rating(self):
        """Test review creation with invalid rating"""
        review_data = {
            'userId': 'user123',
            'productId': 'product123',
            'rating': 6,  # Invalid rating
            'title': 'Great product!',
            'content': 'This is an excellent product.'
        }
        
        result = self.api.create_review(review_data)
        
        self.assertEqual(result['statusCode'], 400)
        response_body = json.loads(result['body'])
        self.assertIn('Rating must be between 1 and 5', response_body['error'])
    
    def test_create_review_duplicate(self):
        """Test review creation when user has already reviewed the product"""
        # Mock existing review
        self.mock_reviews_collection.find_one.return_value = {
            'reviewId': 'existing123',
            'userId': 'user123',
            'productId': 'product123'
        }
        
        review_data = {
            'userId': 'user123',
            'productId': 'product123',
            'rating': 5,
            'title': 'Great product!',
            'content': 'This is an excellent product.'
        }
        
        result = self.api.create_review(review_data)
        
        self.assertEqual(result['statusCode'], 409)
        response_body = json.loads(result['body'])
        self.assertIn('already reviewed', response_body['error'])
    
    def test_create_review_content_moderation_fail(self):
        """Test review creation with inappropriate content"""
        self.mock_reviews_collection.find_one.return_value = None
        
        review_data = {
            'userId': 'user123',
            'productId': 'product123',
            'rating': 1,
            'title': 'Terrible product',
            'content': 'This is spam spam spam spam spam spam spam spam spam spam'
        }
        
        result = self.api.create_review(review_data)
        
        self.assertEqual(result['statusCode'], 400)
        response_body = json.loads(result['body'])
        self.assertIn('community guidelines', response_body['error'])
    
    def test_get_reviews_success(self):
        """Test successful review retrieval"""
        # Mock review data
        mock_reviews = [
            {
                'reviewId': 'review123',
                'userId': 'user123',
                'productId': 'product123',
                'rating': 5,
                'title': 'Great product!',
                'content': 'Excellent quality',
                'images': [],
                'aspectRatings': {},
                'isVerifiedPurchase': True,
                'helpfulCount': 5,
                'notHelpfulCount': 1,
                'sentiment': {'score': 0.8, 'label': 'positive'},
                'createdAt': datetime.now(timezone.utc),
                'updatedAt': datetime.now(timezone.utc)
            }
        ]
        
        # Mock cursor
        mock_cursor = Mock()
        mock_cursor.sort.return_value = mock_cursor
        mock_cursor.skip.return_value = mock_cursor
        mock_cursor.limit.return_value = mock_cursor
        mock_cursor.__iter__ = lambda self: iter(mock_reviews)
        
        self.mock_reviews_collection.find.return_value = mock_cursor
        self.mock_reviews_collection.count_documents.return_value = 1
        
        query_params = {
            'productId': 'product123',
            'page': '1',
            'limit': '20'
        }
        
        result = self.api.get_reviews(query_params)
        
        self.assertEqual(result['statusCode'], 200)
        response_body = json.loads(result['body'])
        self.assertEqual(len(response_body['reviews']), 1)
        self.assertEqual(response_body['reviews'][0]['reviewId'], 'review123')
        self.assertIn('pagination', response_body)
    
    def test_get_reviews_with_filters(self):
        """Test review retrieval with filters"""
        mock_cursor = Mock()
        mock_cursor.sort.return_value = mock_cursor
        mock_cursor.skip.return_value = mock_cursor
        mock_cursor.limit.return_value = mock_cursor
        mock_cursor.__iter__ = lambda self: iter([])
        
        self.mock_reviews_collection.find.return_value = mock_cursor
        self.mock_reviews_collection.count_documents.return_value = 0
        
        query_params = {
            'productId': 'product123',
            'rating': '4',
            'verifiedOnly': 'true',
            'sortBy': 'helpful',
            'sortOrder': 'desc'
        }
        
        result = self.api.get_reviews(query_params)
        
        self.assertEqual(result['statusCode'], 200)
        
        # Verify filter was applied
        call_args = self.mock_reviews_collection.find.call_args[0][0]
        self.assertEqual(call_args['productId'], 'product123')
        self.assertEqual(call_args['rating']['$gte'], 4.0)
        self.assertTrue(call_args['isVerifiedPurchase'])
        self.assertTrue(call_args['isApproved'])
    
    def test_vote_helpful_success(self):
        """Test successful helpful vote"""
        # Mock existing review
        mock_review = {
            'reviewId': 'review123',
            'productId': 'product123',
            'helpfulVotes': [],
            'notHelpfulVotes': []
        }
        
        self.mock_reviews_collection.find_one.return_value = mock_review
        
        mock_update_result = Mock()
        mock_update_result.modified_count = 1
        self.mock_reviews_collection.update_one.return_value = mock_update_result
        
        vote_data = {
            'reviewId': 'review123',
            'userId': 'user456',
            'isHelpful': True
        }
        
        result = self.api.vote_helpful(vote_data)
        
        self.assertEqual(result['statusCode'], 200)
        response_body = json.loads(result['body'])
        self.assertEqual(response_body['message'], 'Vote recorded successfully')
        self.assertEqual(response_body['helpfulCount'], 1)
        self.assertEqual(response_body['notHelpfulCount'], 0)
    
    def test_vote_helpful_review_not_found(self):
        """Test voting on non-existent review"""
        self.mock_reviews_collection.find_one.return_value = None
        
        vote_data = {
            'reviewId': 'nonexistent',
            'userId': 'user456',
            'isHelpful': True
        }
        
        result = self.api.vote_helpful(vote_data)
        
        self.assertEqual(result['statusCode'], 404)
        response_body = json.loads(result['body'])
        self.assertIn('Review not found', response_body['error'])
    
    def test_vote_helpful_change_vote(self):
        """Test changing vote from helpful to not helpful"""
        # Mock existing review with user's previous vote
        mock_review = {
            'reviewId': 'review123',
            'productId': 'product123',
            'helpfulVotes': ['user456'],
            'notHelpfulVotes': []
        }
        
        self.mock_reviews_collection.find_one.return_value = mock_review
        
        mock_update_result = Mock()
        mock_update_result.modified_count = 1
        self.mock_reviews_collection.update_one.return_value = mock_update_result
        
        vote_data = {
            'reviewId': 'review123',
            'userId': 'user456',
            'isHelpful': False
        }
        
        result = self.api.vote_helpful(vote_data)
        
        self.assertEqual(result['statusCode'], 200)
        response_body = json.loads(result['body'])
        self.assertEqual(response_body['helpfulCount'], 0)
        self.assertEqual(response_body['notHelpfulCount'], 1)
    
    def test_check_verified_purchase_true(self):
        """Test verified purchase check returns True"""
        self.mock_orders_table.scan.return_value = {
            'Items': [{
                'userId': 'user123',
                'items': [
                    {'productId': 'product123'},
                    {'productId': 'product456'}
                ]
            }]
        }
        
        result = self.api._check_verified_purchase('user123', 'product123')
        self.assertTrue(result)
    
    def test_check_verified_purchase_false(self):
        """Test verified purchase check returns False"""
        self.mock_orders_table.scan.return_value = {
            'Items': [{
                'userId': 'user123',
                'items': [
                    {'productId': 'product456'},
                    {'productId': 'product789'}
                ]
            }]
        }
        
        result = self.api._check_verified_purchase('user123', 'product123')
        self.assertFalse(result)
    
    def test_moderate_content_approved(self):
        """Test content moderation approves good content"""
        content = "This is a great product with excellent quality and good value for money."
        result = self.api._moderate_content(content)
        
        self.assertTrue(result['approved'])
        self.assertIsNone(result['reason'])
    
    def test_moderate_content_rejected_keyword(self):
        """Test content moderation rejects inappropriate content"""
        content = "This product is spam and terrible quality."
        result = self.api._moderate_content(content)
        
        self.assertFalse(result['approved'])
        self.assertIn('inappropriate language', result['reason'])
    
    def test_moderate_content_rejected_too_short(self):
        """Test content moderation rejects too short content"""
        content = "Bad"
        result = self.api._moderate_content(content)
        
        self.assertFalse(result['approved'])
        self.assertIn('too short', result['reason'])
    
    def test_moderate_content_rejected_spam(self):
        """Test content moderation rejects spam content"""
        content = "great great great great great great great great great great"
        result = self.api._moderate_content(content)
        
        self.assertFalse(result['approved'])
        self.assertIn('spam', result['reason'])
    
    def test_basic_sentiment_analysis_positive(self):
        """Test basic sentiment analysis for positive content"""
        content = "This product is great and excellent with amazing quality."
        result = self.api._basic_sentiment_analysis(content)
        
        self.assertGreater(result['score'], 0)
        self.assertEqual(result['label'], 'positive')
        self.assertIn('aspects', result)
    
    def test_basic_sentiment_analysis_negative(self):
        """Test basic sentiment analysis for negative content"""
        content = "This product is terrible and awful with bad quality."
        result = self.api._basic_sentiment_analysis(content)
        
        self.assertLess(result['score'], 0)
        self.assertEqual(result['label'], 'negative')
        self.assertIn('aspects', result)
    
    def test_basic_sentiment_analysis_neutral(self):
        """Test basic sentiment analysis for neutral content"""
        content = "This product has standard features and normal quality."
        result = self.api._basic_sentiment_analysis(content)
        
        self.assertEqual(result['score'], 0.0)
        self.assertEqual(result['label'], 'neutral')
        self.assertIn('aspects', result)

class TestLambdaHandler(unittest.TestCase):
    """Test cases for lambda_handler function"""
    
    @patch('review_api.ReviewAPI')
    def test_lambda_handler_create_review(self, mock_api_class):
        """Test lambda handler for creating review"""
        mock_api = Mock()
        mock_api_class.return_value = mock_api
        mock_api.create_review.return_value = {
            'statusCode': 201,
            'body': json.dumps({'message': 'Review created successfully'})
        }
        
        event = {
            'httpMethod': 'POST',
            'path': '/reviews',
            'body': json.dumps({
                'userId': 'user123',
                'productId': 'product123',
                'rating': 5,
                'title': 'Great!',
                'content': 'Excellent product'
            })
        }
        
        result = lambda_handler(event, {})
        
        self.assertEqual(result['statusCode'], 201)
        self.assertIn('Access-Control-Allow-Origin', result['headers'])
        mock_api.create_review.assert_called_once()
    
    @patch('review_api.ReviewAPI')
    def test_lambda_handler_get_reviews(self, mock_api_class):
        """Test lambda handler for getting reviews"""
        mock_api = Mock()
        mock_api_class.return_value = mock_api
        mock_api.get_reviews.return_value = {
            'statusCode': 200,
            'body': json.dumps({'reviews': []})
        }
        
        event = {
            'httpMethod': 'GET',
            'path': '/reviews',
            'queryStringParameters': {'productId': 'product123'}
        }
        
        result = lambda_handler(event, {})
        
        self.assertEqual(result['statusCode'], 200)
        self.assertIn('Access-Control-Allow-Origin', result['headers'])
        mock_api.get_reviews.assert_called_once()
    
    @patch('review_api.ReviewAPI')
    def test_lambda_handler_vote_helpful(self, mock_api_class):
        """Test lambda handler for voting helpful"""
        mock_api = Mock()
        mock_api_class.return_value = mock_api
        mock_api.vote_helpful.return_value = {
            'statusCode': 200,
            'body': json.dumps({'message': 'Vote recorded'})
        }
        
        event = {
            'httpMethod': 'POST',
            'path': '/reviews/review123/helpful',
            'body': json.dumps({
                'reviewId': 'review123',
                'userId': 'user456',
                'isHelpful': True
            })
        }
        
        result = lambda_handler(event, {})
        
        self.assertEqual(result['statusCode'], 200)
        mock_api.vote_helpful.assert_called_once()
    
    def test_lambda_handler_invalid_json(self):
        """Test lambda handler with invalid JSON"""
        event = {
            'httpMethod': 'POST',
            'path': '/reviews',
            'body': 'invalid json'
        }
        
        result = lambda_handler(event, {})
        
        self.assertEqual(result['statusCode'], 400)
        response_body = json.loads(result['body'])
        self.assertIn('Invalid JSON', response_body['error'])
    
    def test_lambda_handler_not_found(self):
        """Test lambda handler for non-existent endpoint"""
        event = {
            'httpMethod': 'GET',
            'path': '/nonexistent'
        }
        
        result = lambda_handler(event, {})
        
        self.assertEqual(result['statusCode'], 404)
        response_body = json.loads(result['body'])
        self.assertIn('Endpoint not found', response_body['error'])

if __name__ == '__main__':
    unittest.main()