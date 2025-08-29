"""
Unit tests for Analytics API Lambda function
Tests semantic review search, sentiment analysis, and AI-powered insights
"""
import pytest
import json
import uuid
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta
import sys
import os

# Add the functions directory to the path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'functions'))
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'shared'))

# Mock AWS services before importing
with patch('boto3.client'), patch('boto3.resource'):
    from analytics_api import AnalyticsService, lambda_handler

class TestAnalyticsService:
    """Test cases for AnalyticsService class"""
    
    @pytest.fixture
    def mock_dependencies(self):
        """Mock all external dependencies"""
        with patch('analytics_api.get_documentdb_collection') as mock_collection, \
             patch('analytics_api.cache_get') as mock_cache_get, \
             patch('analytics_api.cache_set') as mock_cache_set, \
             patch('analytics_api.embedding_generator') as mock_embedding, \
             patch('analytics_api.vector_search_manager') as mock_vector_search, \
             patch('boto3.client') as mock_boto_client:
            
            # Setup mocks
            mock_bedrock = Mock()
            mock_boto_client.return_value = mock_bedrock
            
            mock_reviews_collection = Mock()
            mock_products_collection = Mock()
            mock_kb_collection = Mock()
            
            def collection_side_effect(name):
                if name == 'reviews':
                    return mock_reviews_collection
                elif name == 'products':
                    return mock_products_collection
                elif name == 'knowledge_base':
                    return mock_kb_collection
                return Mock()
            
            mock_collection.side_effect = collection_side_effect
            
            yield {
                'bedrock': mock_bedrock,
                'reviews_collection': mock_reviews_collection,
                'products_collection': mock_products_collection,
                'kb_collection': mock_kb_collection,
                'cache_get': mock_cache_get,
                'cache_set': mock_cache_set,
                'embedding_generator': mock_embedding,
                'vector_search_manager': mock_vector_search
            }
    
    @pytest.fixture
    def analytics_service(self, mock_dependencies):
        """Create AnalyticsService instance with mocked dependencies"""
        return AnalyticsService()
    
    def test_semantic_review_search_success(self, analytics_service, mock_dependencies):
        """Test successful semantic review search"""
        # Setup
        query = "wireless headphones audio quality"
        filters = {'limit': 10, 'min_score': 0.7}
        
        # Mock embedding generation
        mock_embedding_result = Mock()
        mock_embedding_result.success = True
        mock_embedding_result.embedding = [0.1] * 1536
        mock_dependencies['embedding_generator'].generate_embedding.return_value = mock_embedding_result
        
        # Mock vector search results
        vector_search_results = [
            {
                'review_id': 'review_123',
                'product_id': 'prod_456',
                'title': 'Great audio quality',
                'content': 'These headphones have amazing sound quality...',
                'rating': 5,
                'user_name': 'John Doe',
                'created_at': datetime.utcnow(),
                'helpful_count': 10,
                'sentiment': {'score': 0.8},
                'similarity_score': 0.9
            }
        ]
        mock_dependencies['vector_search_manager'].vector_search_reviews.return_value = vector_search_results
        
        # Mock product information
        mock_dependencies['products_collection'].find.return_value = [
            {
                'product_id': 'prod_456',
                'title': 'Wireless Bluetooth Headphones',
                'category': 'Electronics',
                'price': 199.99,
                'rating': 4.5,
                'image_url': 'http://example.com/image.jpg'
            }
        ]
        
        # Mock cache
        mock_dependencies['cache_get'].return_value = None
        mock_dependencies['cache_set'].return_value = True
        
        # Mock AI summary generation
        with patch.object(analytics_service, '_generate_ai_search_summary') as mock_ai_summary:
            mock_ai_summary.return_value = "Customers are very satisfied with the audio quality of wireless headphones."
            
            # Execute
            result = analytics_service.semantic_review_search(query, filters)
        
        # Assert
        assert result['success'] is True
        assert result['query'] == query
        assert result['total_results'] == 1
        assert len(result['results']) == 1
        assert result['results'][0]['product_title'] == 'Wireless Bluetooth Headphones'
        assert result['results'][0]['similarity_score'] == 0.9
        assert 'insights' in result
        
        # Verify embedding generation was called
        mock_dependencies['embedding_generator'].generate_embedding.assert_called_once_with(query)
        
        # Verify vector search was called
        mock_dependencies['vector_search_manager'].vector_search_reviews.assert_called_once()
    
    def test_semantic_review_search_empty_query(self, analytics_service, mock_dependencies):
        """Test semantic review search with empty query"""
        # Execute
        result = analytics_service.semantic_review_search("")
        
        # Assert
        assert result['success'] is False
        assert 'empty' in result['error'].lower()
        assert result['results'] == []
    
    def test_semantic_review_search_embedding_failure(self, analytics_service, mock_dependencies):
        """Test semantic review search when embedding generation fails"""
        # Setup
        query = "test query"
        
        mock_embedding_result = Mock()
        mock_embedding_result.success = False
        mock_dependencies['embedding_generator'].generate_embedding.return_value = mock_embedding_result
        
        # Execute
        result = analytics_service.semantic_review_search(query)
        
        # Assert
        assert result['success'] is False
        assert 'process search query' in result['error']
        assert result['results'] == []
    
    def test_semantic_review_search_with_filters(self, analytics_service, mock_dependencies):
        """Test semantic review search with various filters"""
        # Setup
        query = "battery life"
        filters = {
            'product_ids': ['prod_123', 'prod_456'],
            'min_rating': 4,
            'categories': ['Electronics'],
            'limit': 5
        }
        
        # Mock embedding generation
        mock_embedding_result = Mock()
        mock_embedding_result.success = True
        mock_embedding_result.embedding = [0.1] * 1536
        mock_dependencies['embedding_generator'].generate_embedding.return_value = mock_embedding_result
        
        # Mock vector search results with mixed ratings
        vector_search_results = [
            {
                'review_id': 'review_1',
                'product_id': 'prod_123',
                'rating': 5,
                'similarity_score': 0.9
            },
            {
                'review_id': 'review_2',
                'product_id': 'prod_789',  # Not in filter
                'rating': 5,
                'similarity_score': 0.8
            },
            {
                'review_id': 'review_3',
                'product_id': 'prod_456',
                'rating': 3,  # Below min_rating
                'similarity_score': 0.85
            }
        ]
        mock_dependencies['vector_search_manager'].vector_search_reviews.return_value = vector_search_results
        
        # Mock product information
        mock_dependencies['products_collection'].find.return_value = [
            {
                'product_id': 'prod_123',
                'category': 'Electronics',
                'title': 'Product 1'
            },
            {
                'product_id': 'prod_456',
                'category': 'Electronics',
                'title': 'Product 2'
            }
        ]
        
        mock_dependencies['cache_get'].return_value = None
        
        with patch.object(analytics_service, '_generate_ai_search_summary') as mock_ai_summary:
            mock_ai_summary.return_value = "Test summary"
            
            # Execute
            result = analytics_service.semantic_review_search(query, filters)
        
        # Assert
        assert result['success'] is True
        # Should only include prod_123 (in product_ids, rating >= 4, Electronics category)
        assert len(result['results']) == 1
        assert result['results'][0]['product_id'] == 'prod_123'
    
    def test_get_review_sentiment_analysis_success(self, analytics_service, mock_dependencies):
        """Test successful sentiment analysis"""
        # Setup
        product_id = "prod_123"
        
        # Mock reviews data
        mock_reviews = [
            {
                'product_id': product_id,
                'content': 'Great product, love it!',
                'rating': 5,
                'sentiment': {
                    'score': 0.8,
                    'aspects': {
                        'quality': 0.9,
                        'value': 0.7
                    }
                },
                'created_at': datetime.utcnow()
            },
            {
                'product_id': product_id,
                'content': 'Good but could be better',
                'rating': 4,
                'sentiment': {
                    'score': 0.2,
                    'aspects': {
                        'quality': 0.6,
                        'value': 0.8
                    }
                },
                'created_at': datetime.utcnow() - timedelta(days=1)
            }
        ]
        
        mock_dependencies['reviews_collection'].find.return_value.sort.return_value = mock_reviews
        mock_dependencies['cache_get'].return_value = None
        mock_dependencies['cache_set'].return_value = True
        
        # Mock AI summary generation
        with patch.object(analytics_service, '_generate_sentiment_summary') as mock_summary:
            mock_summary.return_value = "Overall positive sentiment with good quality ratings."
            
            # Execute
            result = analytics_service.get_review_sentiment_analysis(product_id)
        
        # Assert
        assert result['success'] is True
        assert result['product_id'] == product_id
        assert result['total_reviews'] == 2
        assert 'sentiment_analysis' in result
        assert 'aspect_insights' in result
        assert 'sentiment_trends' in result
        assert 'ai_summary' in result
        
        # Check sentiment analysis structure
        sentiment_analysis = result['sentiment_analysis']
        assert 'overall_sentiment' in sentiment_analysis
        assert 'aspect_sentiments' in sentiment_analysis
        
        # Check aspect insights
        aspect_insights = result['aspect_insights']
        assert 'quality' in aspect_insights
        assert 'value' in aspect_insights
    
    def test_get_review_sentiment_analysis_no_reviews(self, analytics_service, mock_dependencies):
        """Test sentiment analysis with no reviews"""
        # Setup
        product_id = "prod_nonexistent"
        
        mock_dependencies['reviews_collection'].find.return_value.sort.return_value = []
        
        # Execute
        result = analytics_service.get_review_sentiment_analysis(product_id)
        
        # Assert
        assert result['success'] is False
        assert 'No reviews found' in result['error']
        assert result['product_id'] == product_id
    
    def test_get_product_recommendations_by_reviews_success(self, analytics_service, mock_dependencies):
        """Test successful product recommendations based on reviews"""
        # Setup
        query = "phones with good camera"
        user_preferences = {
            'preferred_categories': ['Electronics'],
            'max_price': 800
        }
        
        # Mock semantic search results
        with patch.object(analytics_service, 'semantic_review_search') as mock_search:
            mock_search.return_value = {
                'success': True,
                'results': [
                    {
                        'product_id': 'phone_123',
                        'review_rating': 5,
                        'similarity_score': 0.9,
                        'review_content': 'Amazing camera quality!'
                    },
                    {
                        'product_id': 'phone_456',
                        'review_rating': 4,
                        'similarity_score': 0.8,
                        'review_content': 'Good camera for the price'
                    }
                ]
            }
            
            # Mock product data
            mock_dependencies['products_collection'].find.return_value = [
                {
                    'product_id': 'phone_123',
                    'title': 'Premium Smartphone',
                    'category': 'Electronics',
                    'price': 699,
                    'rating': 4.5,
                    'image_url': 'http://example.com/phone1.jpg'
                },
                {
                    'product_id': 'phone_456',
                    'title': 'Budget Smartphone',
                    'category': 'Electronics',
                    'price': 299,
                    'rating': 4.0,
                    'image_url': 'http://example.com/phone2.jpg'
                }
            ]
            
            mock_dependencies['cache_get'].return_value = None
            mock_dependencies['cache_set'].return_value = True
            
            # Mock AI explanation
            with patch.object(analytics_service, '_generate_recommendation_explanation') as mock_explanation:
                mock_explanation.return_value = "These phones are recommended based on positive camera reviews."
                
                # Execute
                result = analytics_service.get_product_recommendations_by_reviews(query, user_preferences)
        
        # Assert
        assert result['success'] is True
        assert result['query'] == query
        assert result['total_recommendations'] == 2
        assert len(result['recommendations']) == 2
        assert 'explanation' in result
        
        # Check recommendation structure
        rec = result['recommendations'][0]
        assert 'product_id' in rec
        assert 'title' in rec
        assert 'recommendation_score' in rec
        assert 'highlights' in rec
        assert 'why_recommended' in rec
    
    def test_get_product_recommendations_no_reviews(self, analytics_service, mock_dependencies):
        """Test product recommendations when no relevant reviews found"""
        # Setup
        query = "nonexistent product"
        
        with patch.object(analytics_service, 'semantic_review_search') as mock_search:
            mock_search.return_value = {
                'success': False,
                'results': []
            }
            
            # Execute
            result = analytics_service.get_product_recommendations_by_reviews(query)
        
        # Assert
        assert result['success'] is False
        assert 'No relevant reviews found' in result['error']
        assert result['recommendations'] == []
    
    def test_get_review_insights_by_aspect_success(self, analytics_service, mock_dependencies):
        """Test successful aspect insights analysis"""
        # Setup
        aspect = "audio quality"
        category = "Electronics"
        
        # Mock semantic search for aspect
        with patch.object(analytics_service, 'semantic_review_search') as mock_search:
            mock_search.return_value = {
                'success': True,
                'results': [
                    {
                        'product_id': 'prod_123',
                        'review_content': 'The audio quality is excellent',
                        'sentiment': {'aspects': {'audio_quality': 0.9}},
                        'similarity_score': 0.9
                    },
                    {
                        'product_id': 'prod_123',
                        'review_content': 'Sound quality could be better',
                        'sentiment': {'aspects': {'audio_quality': 0.3}},
                        'similarity_score': 0.7
                    },
                    {
                        'product_id': 'prod_456',
                        'review_content': 'Amazing sound for the price',
                        'sentiment': {'aspects': {'audio_quality': 0.8}},
                        'similarity_score': 0.8
                    }
                ]
            }
            
            # Mock product data
            mock_dependencies['products_collection'].find_one.side_effect = [
                {
                    'product_id': 'prod_123',
                    'title': 'Headphones A',
                    'category': 'Electronics',
                    'price': 199,
                    'rating': 4.2
                },
                {
                    'product_id': 'prod_456',
                    'title': 'Headphones B',
                    'category': 'Electronics',
                    'price': 149,
                    'rating': 4.0
                }
            ]
            
            mock_dependencies['cache_get'].return_value = None
            mock_dependencies['cache_set'].return_value = True
            
            # Execute
            result = analytics_service.get_review_insights_by_aspect(aspect, category)
        
        # Assert
        assert result['success'] is True
        assert result['aspect'] == aspect
        assert result['category'] == category
        assert result['total_products_analyzed'] == 2
        assert len(result['product_insights']) == 2
        assert 'overall_insights' in result
        
        # Check product insights structure
        product_insight = result['product_insights'][0]
        assert 'product_id' in product_insight
        assert 'aspect_score' in product_insight
        assert 'sentiment_label' in product_insight
    
    def test_get_review_insights_by_aspect_no_data(self, analytics_service, mock_dependencies):
        """Test aspect insights when no relevant data found"""
        # Setup
        aspect = "nonexistent aspect"
        
        with patch.object(analytics_service, 'semantic_review_search') as mock_search:
            mock_search.return_value = {
                'success': False,
                'results': []
            }
            
            # Execute
            result = analytics_service.get_review_insights_by_aspect(aspect)
        
        # Assert
        assert result['success'] is False
        assert f'No reviews found discussing {aspect}' in result['error']
    
    def test_enhance_search_results(self, analytics_service, mock_dependencies):
        """Test enhancement of search results with product information"""
        # Setup
        search_results = [
            {
                'review_id': 'review_123',
                'product_id': 'prod_456',
                'title': 'Great product',
                'content': 'Love this product!',
                'rating': 5,
                'similarity_score': 0.9
            }
        ]
        
        mock_dependencies['products_collection'].find.return_value = [
            {
                'product_id': 'prod_456',
                'title': 'Amazing Product',
                'category': 'Electronics',
                'price': 99.99,
                'rating': 4.5,
                'image_url': 'http://example.com/product.jpg'
            }
        ]
        
        # Execute
        result = analytics_service._enhance_search_results(search_results)
        
        # Assert
        assert len(result) == 1
        enhanced_result = result[0]
        assert enhanced_result['product_title'] == 'Amazing Product'
        assert enhanced_result['product_category'] == 'Electronics'
        assert enhanced_result['product_price'] == 99.99
        assert enhanced_result['review_rating'] == 5
        assert enhanced_result['similarity_score'] == 0.9
    
    def test_analyze_review_sentiments(self, analytics_service, mock_dependencies):
        """Test sentiment analysis of reviews"""
        # Setup
        reviews = [
            {
                'sentiment': {
                    'score': 0.8,
                    'aspects': {'quality': 0.9, 'value': 0.7}
                }
            },
            {
                'sentiment': {
                    'score': -0.2,
                    'aspects': {'quality': 0.3, 'value': 0.8}
                }
            },
            {
                'sentiment': {
                    'score': 0.1,
                    'aspects': {'quality': 0.6, 'value': 0.5}
                }
            }
        ]
        
        # Execute
        result = analytics_service._analyze_review_sentiments(reviews)
        
        # Assert
        assert 'overall_sentiment' in result
        assert 'aspect_sentiments' in result
        
        overall = result['overall_sentiment']
        assert 'average_score' in overall
        assert 'distribution' in overall
        
        distribution = overall['distribution']
        assert distribution['positive'] == 2  # scores > 0.1
        assert distribution['negative'] == 1  # scores < -0.1
        assert distribution['neutral'] == 0   # scores between -0.1 and 0.1
        
        # Check aspect sentiments
        aspects = result['aspect_sentiments']
        assert 'quality' in aspects
        assert 'value' in aspects
    
    def test_get_sentiment_label(self, analytics_service, mock_dependencies):
        """Test sentiment score to label conversion"""
        # Test cases
        test_cases = [
            (0.5, 'very_positive'),
            (0.2, 'positive'),
            (0.05, 'neutral'),
            (-0.05, 'neutral'),
            (-0.2, 'negative'),
            (-0.5, 'very_negative')
        ]
        
        for score, expected_label in test_cases:
            result = analytics_service._get_sentiment_label(score)
            assert result == expected_label, f"Score {score} should be {expected_label}, got {result}"

class TestLambdaHandler:
    """Test cases for Lambda handler function"""
    
    def test_semantic_search_endpoint(self):
        """Test POST /analytics/search/reviews endpoint"""
        # Setup
        event = {
            'httpMethod': 'POST',
            'path': '/analytics/search/reviews',
            'body': json.dumps({
                'query': 'wireless headphones',
                'filters': {'limit': 10}
            })
        }
        
        with patch('analytics_api.analytics_service') as mock_service:
            mock_service.semantic_review_search.return_value = {
                'success': True,
                'query': 'wireless headphones',
                'total_results': 5,
                'results': []
            }
            
            # Execute
            response = lambda_handler(event, {})
        
        # Assert
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['success'] is True
        assert body['query'] == 'wireless headphones'
        
        # Verify CORS headers
        assert response['headers']['Access-Control-Allow-Origin'] == '*'
    
    def test_semantic_search_missing_query(self):
        """Test semantic search endpoint with missing query"""
        # Setup
        event = {
            'httpMethod': 'POST',
            'path': '/analytics/search/reviews',
            'body': json.dumps({
                'filters': {'limit': 10}
            })
        }
        
        # Execute
        response = lambda_handler(event, {})
        
        # Assert
        assert response['statusCode'] == 400
        body = json.loads(response['body'])
        assert body['success'] is False
        assert 'required' in body['error']
    
    def test_sentiment_analysis_endpoint(self):
        """Test GET /analytics/sentiment/{product_id} endpoint"""
        # Setup
        event = {
            'httpMethod': 'GET',
            'path': '/analytics/sentiment/prod_123',
            'pathParameters': {'product_id': 'prod_123'}
        }
        
        with patch('analytics_api.analytics_service') as mock_service:
            mock_service.get_review_sentiment_analysis.return_value = {
                'success': True,
                'product_id': 'prod_123',
                'sentiment_analysis': {}
            }
            
            # Execute
            response = lambda_handler(event, {})
        
        # Assert
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['success'] is True
        assert body['product_id'] == 'prod_123'
    
    def test_recommendations_endpoint(self):
        """Test POST /analytics/recommendations endpoint"""
        # Setup
        event = {
            'httpMethod': 'POST',
            'path': '/analytics/recommendations',
            'body': json.dumps({
                'query': 'gaming laptops',
                'user_preferences': {'max_price': 1500}
            })
        }
        
        with patch('analytics_api.analytics_service') as mock_service:
            mock_service.get_product_recommendations_by_reviews.return_value = {
                'success': True,
                'recommendations': []
            }
            
            # Execute
            response = lambda_handler(event, {})
        
        # Assert
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['success'] is True
    
    def test_aspect_insights_endpoint(self):
        """Test GET /analytics/aspects/{aspect} endpoint"""
        # Setup
        event = {
            'httpMethod': 'GET',
            'path': '/analytics/aspects/battery_life',
            'pathParameters': {'aspect': 'battery_life'},
            'queryStringParameters': {'category': 'Electronics'}
        }
        
        with patch('analytics_api.analytics_service') as mock_service:
            mock_service.get_review_insights_by_aspect.return_value = {
                'success': True,
                'aspect': 'battery_life',
                'product_insights': []
            }
            
            # Execute
            response = lambda_handler(event, {})
        
        # Assert
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['success'] is True
        assert body['aspect'] == 'battery_life'
    
    def test_options_request(self):
        """Test OPTIONS request for CORS preflight"""
        # Setup
        event = {
            'httpMethod': 'OPTIONS',
            'path': '/analytics/search/reviews'
        }
        
        # Execute
        response = lambda_handler(event, {})
        
        # Assert
        assert response['statusCode'] == 200
        assert response['headers']['Access-Control-Allow-Origin'] == '*'
        assert 'GET,POST,PUT,DELETE,OPTIONS' in response['headers']['Access-Control-Allow-Methods']
    
    def test_invalid_endpoint(self):
        """Test request to invalid endpoint"""
        # Setup
        event = {
            'httpMethod': 'GET',
            'path': '/analytics/invalid'
        }
        
        # Execute
        response = lambda_handler(event, {})
        
        # Assert
        assert response['statusCode'] == 404
        body = json.loads(response['body'])
        assert body['success'] is False
        assert 'not found' in body['error'].lower()
    
    def test_invalid_json_body(self):
        """Test request with invalid JSON body"""
        # Setup
        event = {
            'httpMethod': 'POST',
            'path': '/analytics/search/reviews',
            'body': 'invalid json'
        }
        
        # Execute
        response = lambda_handler(event, {})
        
        # Assert
        assert response['statusCode'] == 400
        body = json.loads(response['body'])
        assert body['success'] is False
        assert 'Invalid JSON' in body['error']
    
    def test_lambda_handler_exception(self):
        """Test lambda handler with unexpected exception"""
        # Setup
        event = {
            'httpMethod': 'POST',
            'path': '/analytics/search/reviews',
            'body': json.dumps({'query': 'test'})
        }
        
        with patch('analytics_api.analytics_service') as mock_service:
            mock_service.semantic_review_search.side_effect = Exception("Unexpected error")
            
            # Execute
            response = lambda_handler(event, {})
        
        # Assert
        assert response['statusCode'] == 500
        body = json.loads(response['body'])
        assert body['success'] is False
        assert 'Internal server error' in body['error']

if __name__ == '__main__':
    pytest.main([__file__])