"""
Unit tests for Review Analytics Lambda function
"""
import unittest
from unittest.mock import Mock, patch, MagicMock
import json
import sys
import os
from datetime import datetime, timezone, timedelta

# Add the functions directory to the path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'functions'))
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'shared'))

from review_analytics import ReviewAnalytics, lambda_handler

class TestReviewAnalytics(unittest.TestCase):
    """Test cases for ReviewAnalytics class"""
    
    def setUp(self):
        """Set up test fixtures"""
        # Mock database connections
        self.mock_reviews_collection = Mock()
        self.mock_products_collection = Mock()
        self.mock_users_table = Mock()
        
        # Patch database connections
        self.db_patcher = patch('review_analytics.get_documentdb_collection')
        self.dynamodb_patcher = patch('review_analytics.get_dynamodb_table')
        self.cache_get_patcher = patch('review_analytics.cache_get')
        self.cache_set_patcher = patch('review_analytics.cache_set')
        self.cache_delete_patcher = patch('review_analytics.cache_delete')
        self.bedrock_patcher = patch('review_analytics.bedrock_client')
        
        self.mock_get_collection = self.db_patcher.start()
        self.mock_get_table = self.dynamodb_patcher.start()
        self.mock_cache_get = self.cache_get_patcher.start()
        self.mock_cache_set = self.cache_set_patcher.start()
        self.mock_cache_delete = self.cache_delete_patcher.start()
        self.mock_bedrock = self.bedrock_patcher.start()
        
        # Configure mocks
        def mock_get_collection_side_effect(collection_name):
            if collection_name == 'reviews':
                return self.mock_reviews_collection
            elif collection_name == 'products':
                return self.mock_products_collection
            return Mock()
        
        self.mock_get_collection.side_effect = mock_get_collection_side_effect
        self.mock_get_table.return_value = self.mock_users_table
        
        self.mock_cache_get.return_value = None
        self.mock_cache_set.return_value = True
        self.mock_cache_delete.return_value = True
        
        # Initialize analytics
        self.analytics = ReviewAnalytics()
    
    def tearDown(self):
        """Clean up test fixtures"""
        self.db_patcher.stop()
        self.dynamodb_patcher.stop()
        self.cache_get_patcher.stop()
        self.cache_set_patcher.stop()
        self.cache_delete_patcher.stop()
        self.bedrock_patcher.stop()
    
    def test_get_product_review_insights_success(self):
        """Test successful product review insights generation"""
        # Mock review data
        mock_reviews = [
            {
                'reviewId': 'review1',
                'productId': 'product123',
                'rating': 5,
                'content': 'Great product with excellent quality',
                'sentiment': {
                    'score': 0.8,
                    'aspects': {
                        'quality': 0.9,
                        'value': 0.7
                    }
                },
                'helpfulCount': 10,
                'isVerifiedPurchase': True,
                'createdAt': datetime.now(timezone.utc)
            },
            {
                'reviewId': 'review2',
                'productId': 'product123',
                'rating': 4,
                'content': 'Good product, decent value',
                'sentiment': {
                    'score': 0.6,
                    'aspects': {
                        'quality': 0.7,
                        'value': 0.8
                    }
                },
                'helpfulCount': 5,
                'isVerifiedPurchase': False,
                'createdAt': datetime.now(timezone.utc) - timedelta(days=5)
            }
        ]
        
        self.mock_reviews_collection.find.return_value = mock_reviews
        
        # Mock Bedrock response for themes
        self.mock_bedrock.invoke_model.return_value = {
            'body': Mock(read=lambda: json.dumps({
                'content': [{
                    'text': json.dumps([
                        {'theme': 'Quality', 'description': 'Product quality', 'sentiment': 'positive'},
                        {'theme': 'Value', 'description': 'Price value', 'sentiment': 'positive'}
                    ])
                }]
            }).encode())
        }
        
        query_params = {'productId': 'product123'}
        result = self.analytics.get_product_review_insights(query_params)
        
        self.assertEqual(result['statusCode'], 200)
        response_body = json.loads(result['body'])
        
        self.assertEqual(response_body['productId'], 'product123')
        self.assertEqual(response_body['summary']['totalReviews'], 2)
        self.assertEqual(response_body['summary']['averageRating'], 4.5)
        self.assertIn('aspectScores', response_body)
        self.assertIn('commonThemes', response_body)
        self.assertIn('mostHelpfulReviews', response_body)
    
    def test_get_product_review_insights_no_product_id(self):
        """Test insights request without product ID"""
        query_params = {}
        result = self.analytics.get_product_review_insights(query_params)
        
        self.assertEqual(result['statusCode'], 400)
        response_body = json.loads(result['body'])
        self.assertIn('Missing required parameter', response_body['error'])
    
    def test_get_product_review_insights_no_reviews(self):
        """Test insights for product with no reviews"""
        self.mock_reviews_collection.find.return_value = []
        
        query_params = {'productId': 'product123'}
        result = self.analytics.get_product_review_insights(query_params)
        
        self.assertEqual(result['statusCode'], 404)
        response_body = json.loads(result['body'])
        self.assertIn('No reviews found', response_body['error'])
    
    def test_get_product_review_insights_cached(self):
        """Test cached insights response"""
        cached_data = json.dumps({'productId': 'product123', 'cached': True})
        self.mock_cache_get.return_value = cached_data
        
        query_params = {'productId': 'product123'}
        result = self.analytics.get_product_review_insights(query_params)
        
        self.assertEqual(result['statusCode'], 200)
        self.assertEqual(result['body'], cached_data)
        
        # Verify cache was checked but collection was not queried
        self.mock_cache_get.assert_called_once()
        self.mock_reviews_collection.find.assert_not_called()
    
    def test_search_reviews_semantic_success(self):
        """Test successful semantic review search"""
        # Mock embedding generation
        mock_embedding = [0.1, 0.2, 0.3, 0.4, 0.5]
        self.mock_bedrock.invoke_model.side_effect = [
            # First call for embedding
            {
                'body': Mock(read=lambda: json.dumps({
                    'embedding': mock_embedding
                }).encode())
            },
            # Second call for search summary
            {
                'body': Mock(read=lambda: json.dumps({
                    'content': [{
                        'text': 'Customers are very satisfied with the audio quality of these products.'
                    }]
                }).encode())
            }
        ]
        
        # Mock vector search results
        mock_search_results = [
            {
                'reviewId': 'review1',
                'userId': 'user1',
                'productId': 'product123',
                'rating': 5,
                'title': 'Great audio',
                'content': 'Amazing sound quality',
                'isVerifiedPurchase': True,
                'helpfulCount': 10,
                'sentiment': {'score': 0.8},
                'createdAt': datetime.now(timezone.utc),
                'score': 0.95
            }
        ]
        
        self.mock_reviews_collection.aggregate.return_value = mock_search_results
        
        search_body = {
            'query': 'audio quality',
            'minRating': 4,
            'maxResults': 10
        }
        
        result = self.analytics.search_reviews_semantic(search_body)
        
        self.assertEqual(result['statusCode'], 200)
        response_body = json.loads(result['body'])
        
        self.assertEqual(response_body['query'], 'audio quality')
        self.assertEqual(response_body['totalResults'], 1)
        self.assertEqual(len(response_body['results']), 1)
        self.assertIn('summary', response_body)
        
        # Verify vector search was called with correct parameters
        self.mock_reviews_collection.aggregate.assert_called_once()
        pipeline = self.mock_reviews_collection.aggregate.call_args[0][0]
        self.assertIn('$vectorSearch', pipeline[0])
    
    def test_search_reviews_semantic_no_query(self):
        """Test semantic search without query"""
        search_body = {}
        result = self.analytics.search_reviews_semantic(search_body)
        
        self.assertEqual(result['statusCode'], 400)
        response_body = json.loads(result['body'])
        self.assertIn('Missing required field: query', response_body['error'])
    
    def test_search_reviews_semantic_embedding_failure(self):
        """Test semantic search when embedding generation fails"""
        # Mock embedding failure
        self.mock_bedrock.invoke_model.side_effect = Exception("Bedrock error")
        
        search_body = {'query': 'audio quality'}
        result = self.analytics.search_reviews_semantic(search_body)
        
        self.assertEqual(result['statusCode'], 500)
        response_body = json.loads(result['body'])
        self.assertIn('Failed to generate query embedding', response_body['error'])
    
    def test_get_product_recommendations_success(self):
        """Test successful product recommendations"""
        # Mock review aggregation data
        mock_aggregation = [
            {
                '_id': 'product123',
                'avgRating': 4.5,
                'reviewCount': 25,
                'positiveReviews': 20,
                'recentReviews': [
                    {'content': 'Great product', 'rating': 5, 'sentiment': {'score': 0.8}}
                ]
            }
        ]
        
        self.mock_reviews_collection.aggregate.return_value = mock_aggregation
        
        # Mock product data
        mock_products = [
            {
                'productId': 'product123',
                'title': 'Wireless Headphones',
                'category': 'Electronics',
                'price': 199.99,
                'imageUrl': 'http://example.com/image.jpg'
            }
        ]
        
        self.mock_products_collection.find.return_value = mock_products
        
        query_params = {
            'userId': 'user123',
            'category': 'Electronics',
            'minRating': '4.0',
            'maxResults': '5'
        }
        
        result = self.analytics.get_product_recommendations(query_params)
        
        self.assertEqual(result['statusCode'], 200)
        response_body = json.loads(result['body'])
        
        self.assertIn('recommendations', response_body)
        self.assertEqual(len(response_body['recommendations']), 1)
        
        recommendation = response_body['recommendations'][0]
        self.assertEqual(recommendation['productId'], 'product123')
        self.assertEqual(recommendation['title'], 'Wireless Headphones')
        self.assertIn('recommendationScore', recommendation)
        self.assertIn('reasonForRecommendation', recommendation)
    
    def test_get_product_recommendations_no_products(self):
        """Test recommendations when no products match criteria"""
        self.mock_reviews_collection.aggregate.return_value = []
        
        query_params = {'minRating': '4.5'}
        result = self.analytics.get_product_recommendations(query_params)
        
        self.assertEqual(result['statusCode'], 200)
        response_body = json.loads(result['body'])
        
        self.assertEqual(len(response_body['recommendations']), 0)
        self.assertIn('No products found', response_body['message'])
    
    def test_get_product_recommendations_cached(self):
        """Test cached recommendations response"""
        cached_data = json.dumps({'recommendations': [], 'cached': True})
        self.mock_cache_get.return_value = cached_data
        
        query_params = {'minRating': '4.0'}
        result = self.analytics.get_product_recommendations(query_params)
        
        self.assertEqual(result['statusCode'], 200)
        self.assertEqual(result['body'], cached_data)
        
        # Verify cache was used
        self.mock_cache_get.assert_called_once()
        self.mock_reviews_collection.aggregate.assert_not_called()
    
    def test_analyze_review_trends_success(self):
        """Test successful review trends analysis"""
        # Mock trend data
        mock_trend_data = [
            {
                '_id': {'date': '2024-01-01', 'rating': 5},
                'count': 10,
                'avgSentiment': 0.8
            },
            {
                '_id': {'date': '2024-01-01', 'rating': 4},
                'count': 5,
                'avgSentiment': 0.6
            },
            {
                '_id': {'date': '2024-01-02', 'rating': 5},
                'count': 8,
                'avgSentiment': 0.7
            }
        ]
        
        # Mock overall stats
        mock_overall_stats = [
            {
                '_id': None,
                'totalReviews': 23,
                'avgRating': 4.6,
                'avgSentiment': 0.7,
                'ratingDistribution': [5, 5, 5, 4, 4, 4, 4, 4]
            }
        ]
        
        self.mock_reviews_collection.aggregate.side_effect = [
            mock_trend_data,
            mock_overall_stats
        ]
        
        query_params = {
            'productId': 'product123',
            'days': '7'
        }
        
        result = self.analytics.analyze_review_trends(query_params)
        
        self.assertEqual(result['statusCode'], 200)
        response_body = json.loads(result['body'])
        
        self.assertIn('trends', response_body)
        self.assertIn('statistics', response_body)
        self.assertIn('period', response_body)
        
        # Verify trends data structure
        trends = response_body['trends']
        self.assertIn('daily', trends)
        self.assertIn('summary', trends)
        
        # Verify daily trends
        daily_trends = trends['daily']
        self.assertEqual(len(daily_trends), 2)  # 2 unique dates
        
        # Verify first day data
        first_day = daily_trends[0]
        self.assertEqual(first_day['date'], '2024-01-01')
        self.assertEqual(first_day['totalReviews'], 15)  # 10 + 5
        self.assertAlmostEqual(first_day['averageRating'], 4.67, places=1)  # (5*10 + 4*5) / 15
    
    def test_analyze_review_trends_with_category(self):
        """Test trends analysis with category filter"""
        # Mock products in category
        mock_products = [
            {'productId': 'product1'},
            {'productId': 'product2'}
        ]
        
        self.mock_products_collection.find.return_value = mock_products
        self.mock_reviews_collection.aggregate.return_value = []
        
        query_params = {
            'category': 'Electronics',
            'days': '30'
        }
        
        result = self.analytics.analyze_review_trends(query_params)
        
        self.assertEqual(result['statusCode'], 200)
        
        # Verify products collection was queried for category
        self.mock_products_collection.find.assert_called_once_with({'category': 'Electronics'})
    
    def test_generate_embedding_success(self):
        """Test successful embedding generation"""
        mock_embedding = [0.1, 0.2, 0.3, 0.4, 0.5]
        self.mock_bedrock.invoke_model.return_value = {
            'body': Mock(read=lambda: json.dumps({
                'embedding': mock_embedding
            }).encode())
        }
        
        result = self.analytics._generate_embedding('test text')
        
        self.assertEqual(result, mock_embedding)
        self.mock_bedrock.invoke_model.assert_called_once()
    
    def test_generate_embedding_failure(self):
        """Test embedding generation failure"""
        self.mock_bedrock.invoke_model.side_effect = Exception("Bedrock error")
        
        result = self.analytics._generate_embedding('test text')
        
        self.assertIsNone(result)
    
    def test_analyze_user_preferences_success(self):
        """Test user preferences analysis"""
        user_reviews = [
            {
                'rating': 5,
                'productCategory': 'Electronics',
                'sentiment': {
                    'score': 0.8,
                    'aspects': {
                        'quality': 0.9,
                        'value': 0.7
                    }
                }
            },
            {
                'rating': 4,
                'productCategory': 'Electronics',
                'sentiment': {
                    'score': 0.6,
                    'aspects': {
                        'quality': 0.8,
                        'value': 0.5
                    }
                }
            }
        ]
        
        preferences = self.analytics._analyze_user_preferences(user_reviews)
        
        self.assertIn('preferred_categories', preferences)
        self.assertIn('Electronics', preferences['preferred_categories'])
        self.assertEqual(preferences['rating_tendency'], 4.5)
        self.assertEqual(preferences['sentiment_tendency'], 0.7)
        self.assertIn('aspect_preferences', preferences)
        self.assertAlmostEqual(preferences['aspect_preferences']['quality'], 0.85)
    
    def test_analyze_user_preferences_empty(self):
        """Test user preferences analysis with no reviews"""
        preferences = self.analytics._analyze_user_preferences([])
        
        self.assertEqual(preferences, {})
    
    def test_calculate_personalization_boost(self):
        """Test personalization boost calculation"""
        product = {'category': 'Electronics'}
        review_data = {
            'avgRating': 4.5,
            'recentReviews': [
                {'sentiment': {'score': 0.8}, 'rating': 5}
            ]
        }
        user_preferences = {
            'preferred_categories': ['Electronics'],
            'rating_tendency': 4.3,
            'sentiment_tendency': 0.7
        }
        
        boost = self.analytics._calculate_personalization_boost(
            product, review_data, user_preferences
        )
        
        self.assertGreater(boost, 0)  # Should get some boost for category match
        self.assertLessEqual(boost, 0.5)  # Should not exceed reasonable bounds
    
    def test_get_review_highlights(self):
        """Test review highlights extraction"""
        recent_reviews = [
            {'content': 'This is an excellent product with great quality.', 'rating': 5},
            {'content': 'Good value for money and fast shipping.', 'rating': 4},
            {'content': 'Poor quality', 'rating': 2}  # Should be filtered out
        ]
        
        highlights = self.analytics._get_review_highlights(recent_reviews)
        
        self.assertEqual(len(highlights), 2)  # Only positive reviews
        self.assertIn('excellent product', highlights[0])
        self.assertIn('Good value', highlights[1])
    
    def test_generate_recommendation_reason(self):
        """Test recommendation reason generation"""
        product = {'category': 'Electronics'}
        review_data = {'avgRating': 4.7, 'reviewCount': 25}
        user_preferences = {'preferred_categories': ['Electronics']}
        
        reason = self.analytics._generate_recommendation_reason(
            product, review_data, user_preferences
        )
        
        self.assertIn('Highly rated', reason)
        self.assertIn('Popular choice', reason)

class TestLambdaHandler(unittest.TestCase):
    """Test cases for lambda_handler function"""
    
    @patch('review_analytics.ReviewAnalytics')
    def test_lambda_handler_get_insights(self, mock_analytics_class):
        """Test lambda handler for getting product insights"""
        mock_analytics = Mock()
        mock_analytics_class.return_value = mock_analytics
        mock_analytics.get_product_review_insights.return_value = {
            'statusCode': 200,
            'body': json.dumps({'insights': 'test'})
        }
        
        event = {
            'httpMethod': 'GET',
            'path': '/analytics/reviews/insights',
            'queryStringParameters': {'productId': 'product123'}
        }
        
        result = lambda_handler(event, {})
        
        self.assertEqual(result['statusCode'], 200)
        self.assertIn('Access-Control-Allow-Origin', result['headers'])
        mock_analytics.get_product_review_insights.assert_called_once()
    
    @patch('review_analytics.ReviewAnalytics')
    def test_lambda_handler_semantic_search(self, mock_analytics_class):
        """Test lambda handler for semantic search"""
        mock_analytics = Mock()
        mock_analytics_class.return_value = mock_analytics
        mock_analytics.search_reviews_semantic.return_value = {
            'statusCode': 200,
            'body': json.dumps({'results': []})
        }
        
        event = {
            'httpMethod': 'POST',
            'path': '/analytics/reviews/search',
            'body': json.dumps({'query': 'audio quality'})
        }
        
        result = lambda_handler(event, {})
        
        self.assertEqual(result['statusCode'], 200)
        mock_analytics.search_reviews_semantic.assert_called_once()
    
    @patch('review_analytics.ReviewAnalytics')
    def test_lambda_handler_get_recommendations(self, mock_analytics_class):
        """Test lambda handler for getting recommendations"""
        mock_analytics = Mock()
        mock_analytics_class.return_value = mock_analytics
        mock_analytics.get_product_recommendations.return_value = {
            'statusCode': 200,
            'body': json.dumps({'recommendations': []})
        }
        
        event = {
            'httpMethod': 'GET',
            'path': '/analytics/products/recommendations',
            'queryStringParameters': {'userId': 'user123'}
        }
        
        result = lambda_handler(event, {})
        
        self.assertEqual(result['statusCode'], 200)
        mock_analytics.get_product_recommendations.assert_called_once()
    
    @patch('review_analytics.ReviewAnalytics')
    def test_lambda_handler_analyze_trends(self, mock_analytics_class):
        """Test lambda handler for analyzing trends"""
        mock_analytics = Mock()
        mock_analytics_class.return_value = mock_analytics
        mock_analytics.analyze_review_trends.return_value = {
            'statusCode': 200,
            'body': json.dumps({'trends': {}})
        }
        
        event = {
            'httpMethod': 'GET',
            'path': '/analytics/reviews/trends',
            'queryStringParameters': {'productId': 'product123'}
        }
        
        result = lambda_handler(event, {})
        
        self.assertEqual(result['statusCode'], 200)
        mock_analytics.analyze_review_trends.assert_called_once()
    
    def test_lambda_handler_invalid_json(self):
        """Test lambda handler with invalid JSON"""
        event = {
            'httpMethod': 'POST',
            'path': '/analytics/reviews/search',
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