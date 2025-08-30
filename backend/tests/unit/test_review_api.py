"""
Unit tests for Review API Lambda function
Tests review creation, retrieval, voting, sentiment analysis, and moderation
"""
import pytest
import json
import unittest.mock as mock
from unittest.mock import MagicMock, patch, Mock
from datetime import datetime, timezone
import uuid
import sys
import os

# Add the functions directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'functions'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'shared'))

# Mock the shared modules before importing
with patch.dict('sys.modules', {
    'database': MagicMock(),
    'config': MagicMock()
}):
    from review_api import ReviewAPI, lambda_handler

class TestReviewAPI:
    """Test cases for ReviewAPI class"""
    
    def setup_method(self):
        """Set up test fixtures"""
        self.mock_reviews_collection = MagicMock()
        self.mock_users_table = MagicMock()
        self.mock_orders_table = MagicMock()
        self.mock_bedrock_client = MagicMock()
        
        with patch('review_api.get_documentdb_collection') as mock_get_collection, \
             patch('review_api.get_dynamodb_table') as mock_get_table, \
             patch('review_api.boto3.client') as mock_boto3_client:
            
            mock_get_collection.return_value = self.mock_reviews_collection
            mock_get_table.side_effect = lambda name: {
                'users': self.mock_users_table,
                'orders': self.mock_orders_table
            }.get(name, MagicMock())
            mock_boto3_client.return_value = self.mock_bedrock_client
            
            self.api = ReviewAPI()
    
    def test_create_review_success(self):
        """Test successful review creation"""
        review_data = {
            'userId': 'user_123',
            'productId': 'prod_456',
            'rating': 5,
            'title': 'Great product!',
            'content': 'I love this product. It works perfectly and exceeded my expectations.',
            'aspectRatings': {
                'quality': 5,
                'value': 4,
                'comfort': 5
            }
        }
        
        # Mock no existing review
        self.mock_reviews_collection.find_one.return_value = None
        
        # Mock verified purchase check
        with patch.object(self.api, '_check_verified_purchase', return_value=True), \
             patch.object(self.api, '_moderate_content', return_value={'approved': True}), \
             patch.object(self.api, '_analyze_sentiment') as mock_sentiment, \
             patch('review_api.cache_delete'):
            
            mock_sentiment.return_value = {
                'score': 0.8,
                'label': 'positive',
                'confidence': 0.9,
                'aspects': {'quality': 0.9, 'value': 0.7}
            }
            
            # Mock successful insert
            self.mock_reviews_collection.insert_one.return_value.inserted_id = 'review_id_123'
            
            result = self.api.create_review(review_data)
            
            assert result['statusCode'] == 201
            response_body = json.loads(result['body'])
            assert 'Review created successfully' in response_body['message']
            assert 'reviewId' in response_body
            assert response_body['isVerifiedPurchase'] is True
            assert 'sentiment' in response_body
    
    def test_create_review_missing_required_fields(self):
        """Test review creation with missing required fields"""
        incomplete_data = {
            'userId': 'user_123',
            # Missing productId and rating
            'title': 'Test review'
        }
        
        result = self.api.create_review(incomplete_data)
        
        assert result['statusCode'] == 400
        response_body = json.loads(result['body'])
        assert 'Missing required fields' in response_body['error']
    
    def test_create_review_invalid_rating(self):
        """Test review creation with invalid rating"""
        review_data = {
            'userId': 'user_123',
            'productId': 'prod_456',
            'rating': 6,  # Invalid rating (should be 1-5)
            'title': 'Test review',
            'content': 'Test content'
        }
        
        result = self.api.create_review(review_data)
        
        assert result['statusCode'] == 400
        response_body = json.loads(result['body'])
        assert 'Rating must be between 1 and 5' in response_body['error']
    
    def test_create_review_duplicate(self):
        """Test review creation when user already reviewed the product"""
        review_data = {
            'userId': 'user_123',
            'productId': 'prod_456',
            'rating': 5,
            'title': 'Test review',
            'content': 'Test content'
        }
        
        # Mock existing review
        self.mock_reviews_collection.find_one.return_value = {
            'userId': 'user_123',
            'productId': 'prod_456'
        }
        
        result = self.api.create_review(review_data)
        
        assert result['statusCode'] == 409
        response_body = json.loads(result['body'])
        assert 'already reviewed this product' in response_body['error']
    
    def test_create_review_content_moderation_failed(self):
        """Test review creation with content that fails moderation"""
        review_data = {
            'userId': 'user_123',
            'productId': 'prod_456',
            'rating': 1,
            'title': 'Terrible product',
            'content': 'This is spam spam spam'
        }
        
        self.mock_reviews_collection.find_one.return_value = None
        
        with patch.object(self.api, '_check_verified_purchase', return_value=False), \
             patch.object(self.api, '_moderate_content') as mock_moderate:
            
            mock_moderate.return_value = {
                'approved': False,
                'reason': 'Content appears to be spam'
            }
            
            result = self.api.create_review(review_data)
            
            assert result['statusCode'] == 400
            response_body = json.loads(result['body'])
            assert 'violates community guidelines' in response_body['error']
    
    def test_get_reviews_success(self):
        """Test successful review retrieval with filters"""
        mock_reviews = [
            {
                'reviewId': 'review_1',
                'userId': 'user_123',
                'productId': 'prod_456',
                'rating': 5,
                'title': 'Great product',
                'content': 'Love it!',
                'isVerifiedPurchase': True,
                'helpfulCount': 10,
                'notHelpfulCount': 1,
                'sentiment': {'score': 0.8, 'label': 'positive'},
                'createdAt': datetime.now(timezone.utc),
                'updatedAt': datetime.now(timezone.utc)
            }
        ]
        
        mock_cursor = MagicMock()
        mock_cursor.__iter__ = Mock(return_value=iter(mock_reviews))
        self.mock_reviews_collection.find.return_value.sort.return_value.skip.return_value.limit.return_value = mock_cursor
        self.mock_reviews_collection.count_documents.return_value = 1
        
        query_params = {
            'productId': 'prod_456',
            'rating': '4',
            'verifiedOnly': 'true',
            'sortBy': 'helpful',
            'page': '1',
            'limit': '20'
        }
        
        with patch('review_api.cache_get', return_value=None), \
             patch('review_api.cache_set'):
            
            result = self.api.get_reviews(query_params)
            
            assert result['statusCode'] == 200
            response_body = json.loads(result['body'])
            assert 'reviews' in response_body
            assert 'pagination' in response_body
            assert len(response_body['reviews']) == 1
            assert response_body['reviews'][0]['reviewId'] == 'review_1'
    
    def test_get_reviews_cached_result(self):
        """Test returning cached reviews"""
        cached_data = json.dumps({
            'reviews': [],
            'pagination': {'page': 1, 'totalCount': 0}
        })
        
        with patch('review_api.cache_get', return_value=cached_data):
            query_params = {'productId': 'prod_456'}
            result = self.api.get_reviews(query_params)
            
            assert result['statusCode'] == 200
            # Should not call database
            self.mock_reviews_collection.find.assert_not_called()
    
    def test_get_reviews_with_user_filter(self):
        """Test review retrieval filtered by user"""
        mock_reviews = []
        mock_cursor = MagicMock()
        mock_cursor.__iter__ = Mock(return_value=iter(mock_reviews))
        self.mock_reviews_collection.find.return_value.sort.return_value.skip.return_value.limit.return_value = mock_cursor
        self.mock_reviews_collection.count_documents.return_value = 0
        
        query_params = {
            'userId': 'user_123',
            'sortBy': 'createdAt',
            'sortOrder': 'desc'
        }
        
        result = self.api.get_reviews(query_params)
        
        # Verify the query filter included userId
        call_args = self.mock_reviews_collection.find.call_args[0][0]
        assert call_args['userId'] == 'user_123'
        assert call_args['isApproved'] is True  # Should only show approved reviews
    
    def test_vote_helpful_success(self):
        """Test successful helpful vote"""
        vote_data = {
            'reviewId': 'review_123',
            'userId': 'user_456',
            'isHelpful': True
        }
        
        # Mock existing review
        mock_review = {
            'reviewId': 'review_123',
            'helpfulVotes': ['user_789'],  # Existing vote from different user
            'notHelpfulVotes': [],
            'helpfulCount': 1,
            'notHelpfulCount': 0
        }
        self.mock_reviews_collection.find_one.return_value = mock_review
        
        # Mock successful update
        self.mock_reviews_collection.update_one.return_value.modified_count = 1
        
        with patch('review_api.cache_delete'):
            result = self.api.vote_helpful(vote_data)
            
            assert result['statusCode'] == 200
            response_body = json.loads(result['body'])
            assert 'Vote recorded successfully' in response_body['message']
            assert response_body['helpfulCount'] == 2  # Original 1 + new vote
            assert response_body['notHelpfulCount'] == 0
    
    def test_vote_helpful_change_vote(self):
        """Test changing vote from not helpful to helpful"""
        vote_data = {
            'reviewId': 'review_123',
            'userId': 'user_456',
            'isHelpful': True
        }
        
        # Mock review where user previously voted not helpful
        mock_review = {
            'reviewId': 'review_123',
            'helpfulVotes': [],
            'notHelpfulVotes': ['user_456'],  # User's previous vote
            'helpfulCount': 0,
            'notHelpfulCount': 1
        }
        self.mock_reviews_collection.find_one.return_value = mock_review
        self.mock_reviews_collection.update_one.return_value.modified_count = 1
        
        with patch('review_api.cache_delete'):
            result = self.api.vote_helpful(vote_data)
            
            assert result['statusCode'] == 200
            response_body = json.loads(result['body'])
            assert response_body['helpfulCount'] == 1  # Changed to helpful
            assert response_body['notHelpfulCount'] == 0  # Removed from not helpful
    
    def test_vote_helpful_review_not_found(self):
        """Test voting on non-existent review"""
        vote_data = {
            'reviewId': 'nonexistent_review',
            'userId': 'user_456',
            'isHelpful': True
        }
        
        self.mock_reviews_collection.find_one.return_value = None
        
        result = self.api.vote_helpful(vote_data)
        
        assert result['statusCode'] == 404
        response_body = json.loads(result['body'])
        assert 'Review not found' in response_body['error']
    
    def test_vote_helpful_missing_fields(self):
        """Test voting with missing required fields"""
        incomplete_data = {
            'reviewId': 'review_123'
            # Missing userId
        }
        
        result = self.api.vote_helpful(incomplete_data)
        
        assert result['statusCode'] == 400
        response_body = json.loads(result['body'])
        assert 'Missing required fields' in response_body['error']
    
    def test_check_verified_purchase_true(self):
        """Test verified purchase check when user has purchased product"""
        mock_orders = [
            {
                'userId': 'user_123',
                'items': [
                    {'productId': 'prod_456', 'quantity': 1},
                    {'productId': 'prod_789', 'quantity': 2}
                ]
            }
        ]
        
        self.mock_orders_table.scan.return_value = {'Items': mock_orders}
        
        result = self.api._check_verified_purchase('user_123', 'prod_456')
        
        assert result is True
    
    def test_check_verified_purchase_false(self):
        """Test verified purchase check when user hasn't purchased product"""
        mock_orders = [
            {
                'userId': 'user_123',
                'items': [
                    {'productId': 'prod_789', 'quantity': 1}  # Different product
                ]
            }
        ]
        
        self.mock_orders_table.scan.return_value = {'Items': mock_orders}
        
        result = self.api._check_verified_purchase('user_123', 'prod_456')
        
        assert result is False
    
    def test_check_verified_purchase_no_orders(self):
        """Test verified purchase check when user has no orders"""
        self.mock_orders_table.scan.return_value = {'Items': []}
        
        result = self.api._check_verified_purchase('user_123', 'prod_456')
        
        assert result is False
    
    def test_moderate_content_approved(self):
        """Test content moderation for acceptable content"""
        content = "This is a great product. I really enjoy using it and would recommend it to others."
        
        result = self.api._moderate_content(content)
        
        assert result['approved'] is True
        assert result['reason'] is None
    
    def test_moderate_content_inappropriate_language(self):
        """Test content moderation for inappropriate language"""
        content = "This product is terrible and stupid garbage."
        
        result = self.api._moderate_content(content)
        
        assert result['approved'] is False
        assert 'inappropriate language' in result['reason']
    
    def test_moderate_content_too_short(self):
        """Test content moderation for content that's too short"""
        content = "Bad"
        
        result = self.api._moderate_content(content)
        
        assert result['approved'] is False
        assert 'too short' in result['reason']
    
    def test_moderate_content_spam_detection(self):
        """Test content moderation for spam (excessive repetition)"""
        content = "buy buy buy buy buy buy this product now"
        
        result = self.api._moderate_content(content)
        
        assert result['approved'] is False
        assert 'spam' in result['reason']
    
    def test_analyze_sentiment_with_bedrock(self):
        """Test sentiment analysis using Bedrock"""
        content = "This product is absolutely amazing! Great quality and value."
        
        # Mock Bedrock response
        mock_response = {
            'body': MagicMock()
        }
        mock_response['body'].read.return_value = json.dumps({
            'content': [{
                'text': json.dumps({
                    'score': 0.8,
                    'label': 'positive',
                    'confidence': 0.9,
                    'aspects': {
                        'quality': 0.9,
                        'value': 0.8,
                        'comfort': 0.7,
                        'design': 0.6,
                        'durability': 0.7
                    }
                })
            }]
        }).encode()
        
        self.mock_bedrock_client.invoke_model.return_value = mock_response
        
        result = self.api._analyze_sentiment(content)
        
        assert result['score'] == 0.8
        assert result['label'] == 'positive'
        assert result['confidence'] == 0.9
        assert 'aspects' in result
        assert result['aspects']['quality'] == 0.9
    
    def test_analyze_sentiment_bedrock_failure(self):
        """Test sentiment analysis fallback when Bedrock fails"""
        content = "This product is great and excellent!"
        
        # Mock Bedrock failure
        self.mock_bedrock_client.invoke_model.side_effect = Exception("Bedrock error")
        
        result = self.api._analyze_sentiment(content)
        
        # Should fall back to basic sentiment analysis
        assert 'score' in result
        assert 'label' in result
        assert result['label'] == 'positive'  # Should detect positive words
    
    def test_analyze_sentiment_empty_content(self):
        """Test sentiment analysis with empty content"""
        content = ""
        
        result = self.api._analyze_sentiment(content)
        
        assert result['score'] == 0.0
        assert result['label'] == 'neutral'
        assert result['confidence'] == 0.0
    
    def test_basic_sentiment_analysis_positive(self):
        """Test basic sentiment analysis for positive content"""
        content = "This product is excellent and amazing. I love it!"
        
        result = self.api._basic_sentiment_analysis(content)
        
        assert result['score'] > 0
        assert result['label'] == 'positive'
        assert 'aspects' in result
    
    def test_basic_sentiment_analysis_negative(self):
        """Test basic sentiment analysis for negative content"""
        content = "This product is terrible and awful. I hate it!"
        
        result = self.api._basic_sentiment_analysis(content)
        
        assert result['score'] < 0
        assert result['label'] == 'negative'
        assert 'aspects' in result
    
    def test_basic_sentiment_analysis_neutral(self):
        """Test basic sentiment analysis for neutral content"""
        content = "This product exists and has features."
        
        result = self.api._basic_sentiment_analysis(content)
        
        assert result['score'] == 0.0
        assert result['label'] == 'neutral'


class TestReviewAPILambdaHandler:
    """Test cases for lambda_handler function"""
    
    def test_lambda_handler_create_review(self):
        """Test lambda handler for POST /reviews"""
        with patch('review_api.ReviewAPI') as mock_api_class:
            mock_api = MagicMock()
            mock_api_class.return_value = mock_api
            mock_api.create_review.return_value = {
                'statusCode': 201,
                'body': json.dumps({'message': 'Review created'})
            }
            
            event = {
                'httpMethod': 'POST',
                'path': '/reviews',
                'body': json.dumps({
                    'userId': 'user_123',
                    'productId': 'prod_456',
                    'rating': 5,
                    'title': 'Great!',
                    'content': 'Love this product'
                })
            }
            context = MagicMock()
            
            result = lambda_handler(event, context)
            
            assert result['statusCode'] == 201
            assert 'Access-Control-Allow-Origin' in result['headers']
            mock_api.create_review.assert_called_once()
    
    def test_lambda_handler_get_reviews(self):
        """Test lambda handler for GET /reviews"""
        with patch('review_api.ReviewAPI') as mock_api_class:
            mock_api = MagicMock()
            mock_api_class.return_value = mock_api
            mock_api.get_reviews.return_value = {
                'statusCode': 200,
                'body': json.dumps({'reviews': []})
            }
            
            event = {
                'httpMethod': 'GET',
                'path': '/reviews',
                'queryStringParameters': {'productId': 'prod_456'}
            }
            context = MagicMock()
            
            result = lambda_handler(event, context)
            
            assert result['statusCode'] == 200
            mock_api.get_reviews.assert_called_once()
    
    def test_lambda_handler_vote_helpful(self):
        """Test lambda handler for POST /reviews/{reviewId}/helpful"""
        with patch('review_api.ReviewAPI') as mock_api_class:
            mock_api = MagicMock()
            mock_api_class.return_value = mock_api
            mock_api.vote_helpful.return_value = {
                'statusCode': 200,
                'body': json.dumps({'message': 'Vote recorded'})
            }
            
            event = {
                'httpMethod': 'POST',
                'path': '/reviews/review_123/helpful',
                'body': json.dumps({
                    'reviewId': 'review_123',
                    'userId': 'user_456',
                    'isHelpful': True
                })
            }
            context = MagicMock()
            
            result = lambda_handler(event, context)
            
            assert result['statusCode'] == 200
            mock_api.vote_helpful.assert_called_once()
    
    def test_lambda_handler_invalid_json(self):
        """Test lambda handler with invalid JSON"""
        event = {
            'httpMethod': 'POST',
            'path': '/reviews',
            'body': 'invalid json'
        }
        context = MagicMock()
        
        result = lambda_handler(event, context)
        
        assert result['statusCode'] == 400
        response_body = json.loads(result['body'])
        assert 'Invalid JSON' in response_body['error']
    
    def test_lambda_handler_endpoint_not_found(self):
        """Test lambda handler with unknown endpoint"""
        event = {
            'httpMethod': 'GET',
            'path': '/unknown'
        }
        context = MagicMock()
        
        result = lambda_handler(event, context)
        
        assert result['statusCode'] == 404
        response_body = json.loads(result['body'])
        assert 'Endpoint not found' in response_body['error']
    
    def test_lambda_handler_exception_handling(self):
        """Test lambda handler exception handling"""
        with patch('review_api.ReviewAPI') as mock_api_class:
            mock_api_class.side_effect = Exception("Initialization error")
            
            event = {
                'httpMethod': 'GET',
                'path': '/reviews'
            }
            context = MagicMock()
            
            result = lambda_handler(event, context)
            
            assert result['statusCode'] == 500
            response_body = json.loads(result['body'])
            assert 'Internal server error' in response_body['error']


if __name__ == '__main__':
    pytest.main([__file__])