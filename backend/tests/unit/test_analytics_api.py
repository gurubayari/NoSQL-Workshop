"""
Unit tests for Analytics API Lambda function
Tests semantic review search, sentiment analysis, and AI-powered insights
"""
import pytest
import json
import unittest.mock as mock
from unittest.mock import MagicMock, patch, Mock
from datetime import datetime, timezone
import sys
import os
from collections import defaultdict, Counter

# Add the functions directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'functions'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'shared'))

# Mock the shared modules before importing
with patch.dict('sys.modules', {
    'shared.config': MagicMock(),
    'shared.database': MagicMock(),
    'shared.embeddings': MagicMock(),
    'shared.vector_search': MagicMock(),
    'config': MagicMock(),
    'database': MagicMock(),
    'embeddings': MagicMock(),
    'vector_search': MagicMock()
}):
    from analytics_api import AnalyticsService, lambda_handler

class TestAnalyticsService:
    """Test cases for AnalyticsService class"""
    
    def setup_method(self):
        """Set up test fixtures"""
        self.mock_bedrock_client = MagicMock()
        self.mock_reviews_collection = MagicMock()
        self.mock_products_collection = MagicMock()
        self.mock_knowledge_base_collection = MagicMock()
        self.mock_embedding_generator = MagicMock()
        self.mock_vector_search_manager = MagicMock()
        
        with patch('analytics_api.boto3.client') as mock_boto3_client, \
             patch('analytics_api.get_documentdb_collection') as mock_get_collection, \
             patch('analytics_api.embedding_generator') as mock_embedding, \
             patch('analytics_api.vector_search_manager') as mock_vector_search:
            
            mock_boto3_client.return_value = self.mock_bedrock_client
            mock_get_collection.side_effect = lambda name: {
                'reviews': self.mock_reviews_collection,
                'products': self.mock_products_collection,
                'knowledge_base': self.mock_knowledge_base_collection
            }[name]
            mock_embedding.return_value = self.mock_embedding_generator
            mock_vector_search.return_value = self.mock_vector_search_manager
            
            self.service = AnalyticsService()
    
    def test_semantic_review_search_success(self):
        """Test successful semantic review search"""
        query = "phones with good audio quality"
        filters = {'limit': 10, 'min_score': 0.7}
        
        # Mock embedding generation
        mock_embedding_result = MagicMock()
        mock_embedding_result.success = True
        mock_embedding_result.embedding = [0.1, 0.2, 0.3]
        
        # Mock vector search results
        mock_search_results = [
            {
                'review_id': 'review_1',
                'product_id': 'prod_123',
                'title': 'Great audio quality',
                'content': 'The sound quality is amazing',
                'rating': 5,
                'user_name': 'John Doe',
                'created_at': datetime.now(timezone.utc),
                'helpful_count': 10,
                'sentiment': {'score': 0.8, 'label': 'positive'},
                'similarity_score': 0.9
            }
        ]
        
        with patch('analytics_api.embedding_generator') as mock_embedding, \
             patch('analytics_api.vector_search_manager') as mock_vector_search, \
             patch.object(self.service, '_enhance_search_results') as mock_enhance, \
             patch.object(self.service, '_generate_search_insights') as mock_insights, \
             patch('analytics_api.cache_get', return_value=None), \
             patch('analytics_api.cache_set'):
            
            mock_embedding.generate_embedding.return_value = mock_embedding_result
            mock_vector_search.vector_search_reviews.return_value = mock_search_results
            mock_enhance.return_value = mock_search_results
            mock_insights.return_value = {
                'summary': 'Found reviews about audio quality',
                'key_findings': ['Positive sentiment about audio']
            }
            
            result = self.service.semantic_review_search(query, filters)
            
            assert result['success'] is True
            assert result['query'] == query
            assert result['total_results'] == 1
            assert len(result['results']) == 1
            assert 'insights' in result
    
    def test_semantic_review_search_empty_query(self):
        """Test semantic review search with empty query"""
        result = self.service.semantic_review_search("")
        
        assert result['success'] is False
        assert 'Query cannot be empty' in result['error']
        assert result['results'] == []
    
    def test_semantic_review_search_embedding_failure(self):
        """Test semantic review search when embedding generation fails"""
        query = "test query"
        
        # Mock embedding failure
        mock_embedding_result = MagicMock()
        mock_embedding_result.success = False
        
        with patch('analytics_api.embedding_generator') as mock_embedding, \
             patch('analytics_api.cache_get', return_value=None):
            
            mock_embedding.generate_embedding.return_value = mock_embedding_result
            
            result = self.service.semantic_review_search(query)
            
            assert result['success'] is False
            assert 'Failed to process search query' in result['error']
    
    def test_semantic_review_search_cached_result(self):
        """Test returning cached semantic search results"""
        query = "test query"
        cached_result = {
            'success': True,
            'query': query,
            'results': []
        }
        
        with patch('analytics_api.cache_get', return_value=json.dumps(cached_result)):
            result = self.service.semantic_review_search(query)
            
            assert result == cached_result
    
    def test_get_review_sentiment_analysis_success(self):
        """Test successful review sentiment analysis"""
        product_id = 'prod_123'
        
        mock_reviews = [
            {
                'product_id': product_id,
                'rating': 5,
                'title': 'Great product',
                'content': 'I love this product, excellent quality',
                'sentiment': {
                    'score': 0.8,
                    'label': 'positive',
                    'aspects': {
                        'quality': 0.9,
                        'value': 0.7,
                        'comfort': 0.8
                    }
                },
                'created_at': datetime.now(timezone.utc)
            },
            {
                'product_id': product_id,
                'rating': 4,
                'title': 'Good value',
                'content': 'Good product for the price',
                'sentiment': {
                    'score': 0.6,
                    'label': 'positive',
                    'aspects': {
                        'quality': 0.7,
                        'value': 0.8,
                        'comfort': 0.6
                    }
                },
                'created_at': datetime.now(timezone.utc)
            }
        ]
        
        mock_cursor = MagicMock()
        mock_cursor.__iter__ = Mock(return_value=iter(mock_reviews))
        self.mock_reviews_collection.find.return_value.sort.return_value = mock_cursor
        
        with patch.object(self.service, '_analyze_review_sentiments') as mock_analyze, \
             patch.object(self.service, '_generate_aspect_insights') as mock_aspects, \
             patch.object(self.service, '_analyze_sentiment_trends') as mock_trends, \
             patch.object(self.service, '_generate_sentiment_summary') as mock_summary, \
             patch('analytics_api.cache_get', return_value=None), \
             patch('analytics_api.cache_set'):
            
            mock_analyze.return_value = {
                'overall_sentiment': {
                    'average_score': 0.7,
                    'distribution': {'positive': 2, 'neutral': 0, 'negative': 0}
                }
            }
            mock_aspects.return_value = {
                'quality': {'average_score': 0.8, 'mention_count': 2}
            }
            mock_trends.return_value = {
                'monthly_trends': [],
                'trend_direction': 'stable'
            }
            mock_summary.return_value = 'Overall positive sentiment'
            
            result = self.service.get_review_sentiment_analysis(product_id)
            
            assert result['success'] is True
            assert result['product_id'] == product_id
            assert result['total_reviews'] == 2
            assert 'sentiment_analysis' in result
            assert 'aspect_insights' in result
            assert 'sentiment_trends' in result
            assert 'ai_summary' in result
    
    def test_get_review_sentiment_analysis_no_reviews(self):
        """Test sentiment analysis when no reviews exist"""
        product_id = 'prod_123'
        
        self.mock_reviews_collection.find.return_value.sort.return_value = []
        
        with patch('analytics_api.cache_get', return_value=None):
            result = self.service.get_review_sentiment_analysis(product_id)
            
            assert result['success'] is False
            assert 'No reviews found' in result['error']
            assert result['product_id'] == product_id
    
    def test_get_product_recommendations_by_reviews_success(self):
        """Test successful product recommendations based on reviews"""
        query = "phones with good battery life"
        user_preferences = {'price_range': [100, 500]}
        
        # Mock review search results
        mock_review_search = {
            'success': True,
            'results': [
                {
                    'product_id': 'prod_123',
                    'review_content': 'Great battery life',
                    'rating': 5,
                    'similarity_score': 0.9
                }
            ]
        }
        
        # Mock products
        mock_products = [
            {
                'product_id': 'prod_123',
                'title': 'Smartphone Pro',
                'price': 299.99,
                'category': 'Electronics',
                'rating': 4.5
            }
        ]
        
        with patch.object(self.service, 'semantic_review_search', return_value=mock_review_search), \
             patch.object(self.service, '_generate_review_based_recommendations') as mock_generate, \
             patch.object(self.service, '_generate_recommendation_explanation') as mock_explain, \
             patch('analytics_api.cache_get', return_value=None), \
             patch('analytics_api.cache_set'):
            
            self.mock_products_collection.find.return_value = mock_products
            mock_generate.return_value = [
                {
                    'product_id': 'prod_123',
                    'title': 'Smartphone Pro',
                    'recommendation_score': 0.9,
                    'reasons': ['Excellent battery life mentioned in reviews']
                }
            ]
            mock_explain.return_value = 'Recommended based on positive battery life reviews'
            
            result = self.service.get_product_recommendations_by_reviews(query, user_preferences)
            
            assert result['success'] is True
            assert result['query'] == query
            assert len(result['recommendations']) == 1
            assert 'explanation' in result
    
    def test_get_product_recommendations_no_relevant_reviews(self):
        """Test product recommendations when no relevant reviews found"""
        query = "nonexistent feature"
        
        # Mock empty review search
        mock_review_search = {
            'success': False,
            'results': []
        }
        
        with patch.object(self.service, 'semantic_review_search', return_value=mock_review_search):
            result = self.service.get_product_recommendations_by_reviews(query)
            
            assert result['success'] is False
            assert 'No relevant reviews found' in result['error']
    
    def test_get_review_insights_by_aspect_success(self):
        """Test successful aspect-based review insights"""
        aspect = "audio quality"
        category = "Electronics"
        
        # Mock aspect search results
        mock_aspect_search = {
            'success': True,
            'results': [
                {
                    'product_id': 'prod_123',
                    'review_content': 'Amazing audio quality',
                    'rating': 5,
                    'similarity_score': 0.9
                },
                {
                    'product_id': 'prod_123',
                    'review_content': 'Good sound quality',
                    'rating': 4,
                    'similarity_score': 0.8
                }
            ]
        }
        
        with patch.object(self.service, 'semantic_review_search', return_value=mock_aspect_search), \
             patch.object(self.service, '_analyze_product_aspect') as mock_analyze, \
             patch.object(self.service, '_generate_aspect_overview') as mock_overview, \
             patch('analytics_api.cache_get', return_value=None), \
             patch('analytics_api.cache_set'):
            
            mock_analyze.return_value = {
                'product_id': 'prod_123',
                'product_title': 'Headphones Pro',
                'aspect_score': 4.5,
                'review_count': 2,
                'positive_mentions': 2,
                'negative_mentions': 0
            }
            mock_overview.return_value = {
                'average_aspect_score': 4.5,
                'top_performing_products': ['Headphones Pro'],
                'common_themes': ['excellent sound', 'clear audio']
            }
            
            result = self.service.get_review_insights_by_aspect(aspect, category)
            
            assert result['success'] is True
            assert result['aspect'] == aspect
            assert result['category'] == category
            assert len(result['product_insights']) == 1
            assert 'overall_insights' in result
    
    def test_get_review_insights_by_aspect_no_reviews(self):
        """Test aspect insights when no relevant reviews found"""
        aspect = "nonexistent aspect"
        
        # Mock empty search results
        mock_aspect_search = {
            'success': False,
            'results': []
        }
        
        with patch.object(self.service, 'semantic_review_search', return_value=mock_aspect_search):
            result = self.service.get_review_insights_by_aspect(aspect)
            
            assert result['success'] is False
            assert f'No reviews found discussing {aspect}' in result['error']
    
    def test_enhance_search_results(self):
        """Test enhancing search results with product information"""
        search_results = [
            {
                'review_id': 'review_1',
                'product_id': 'prod_123',
                'title': 'Great product',
                'content': 'Love it',
                'rating': 5,
                'similarity_score': 0.9
            }
        ]
        
        mock_products = [
            {
                'product_id': 'prod_123',
                'title': 'Smartphone Pro',
                'category': 'Electronics',
                'price': 299.99,
                'rating': 4.5,
                'image_url': 'image.jpg',
                'review_count': 100
            }
        ]
        
        self.mock_products_collection.find.return_value = mock_products
        
        result = self.service._enhance_search_results(search_results)
        
        assert len(result) == 1
        enhanced_result = result[0]
        assert enhanced_result['product_title'] == 'Smartphone Pro'
        assert enhanced_result['product_category'] == 'Electronics'
        assert enhanced_result['product_price'] == 299.99
        assert enhanced_result['review_title'] == 'Great product'
        assert enhanced_result['similarity_score'] == 0.9
    
    def test_enhance_search_results_empty(self):
        """Test enhancing empty search results"""
        result = self.service._enhance_search_results([])
        assert result == []
    
    def test_generate_search_insights(self):
        """Test generating AI-powered search insights"""
        query = "wireless headphones"
        results = [
            {
                'review_rating': 5,
                'sentiment': {'score': 0.8},
                'product_title': 'Headphones Pro'
            },
            {
                'review_rating': 4,
                'sentiment': {'score': 0.6},
                'product_title': 'Headphones Pro'
            }
        ]
        
        with patch.object(self.service, '_generate_ai_search_summary') as mock_ai_summary, \
             patch.object(self.service, '_extract_key_findings') as mock_findings:
            
            mock_ai_summary.return_value = 'Positive reviews about wireless headphones'
            mock_findings.return_value = ['High ratings', 'Positive sentiment']
            
            insights = self.service._generate_search_insights(query, results)
            
            assert 'summary' in insights
            assert 'statistics' in insights
            assert insights['statistics']['total_results'] == 2
            assert insights['statistics']['average_rating'] == 4.5
            assert 'top_products' in insights
    
    def test_generate_search_insights_no_results(self):
        """Test generating insights with no results"""
        query = "test query"
        results = []
        
        insights = self.service._generate_search_insights(query, results)
        
        assert f'No reviews found matching "{query}"' in insights['summary']
        assert insights['key_findings'] == []
        assert insights['sentiment_overview'] == 'neutral'
    
    def test_generate_ai_search_summary(self):
        """Test generating AI summary using Bedrock"""
        query = "wireless headphones"
        results = [
            {
                'review_content': 'Great sound quality',
                'review_rating': 5,
                'similarity_score': 0.9
            }
        ]
        avg_rating = 4.5
        avg_sentiment = 0.7
        
        # Mock Bedrock response
        mock_response = {
            'body': MagicMock()
        }
        mock_response['body'].read.return_value = json.dumps({
            'content': [{
                'text': 'Customers are very satisfied with the wireless headphones, praising their sound quality and comfort.'
            }]
        }).encode()
        
        self.mock_bedrock_client.invoke_model.return_value = mock_response
        
        result = self.service._generate_ai_search_summary(query, results, avg_rating, avg_sentiment)
        
        assert 'satisfied' in result
        assert 'sound quality' in result
    
    def test_generate_ai_search_summary_bedrock_failure(self):
        """Test AI summary generation when Bedrock fails"""
        query = "test query"
        results = []
        avg_rating = 4.0
        avg_sentiment = 0.5
        
        # Mock Bedrock failure
        self.mock_bedrock_client.invoke_model.side_effect = Exception("Bedrock error")
        
        result = self.service._generate_ai_search_summary(query, results, avg_rating, avg_sentiment)
        
        # Should return fallback summary
        assert f'Found {len(results)} customer reviews' in result
        assert f'Average rating: {avg_rating:.1f}/5' in result
    
    def test_analyze_review_sentiments(self):
        """Test analyzing review sentiment distribution"""
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
                    'aspects': {'quality': -0.1, 'value': -0.3}
                }
            },
            {
                'sentiment': {
                    'score': 0.1,
                    'aspects': {'quality': 0.2, 'value': 0.0}
                }
            }
        ]
        
        result = self.service._analyze_review_sentiments(reviews)
        
        assert 'overall_sentiment' in result
        assert result['overall_sentiment']['distribution']['positive'] == 1
        assert result['overall_sentiment']['distribution']['negative'] == 1
        assert result['overall_sentiment']['distribution']['neutral'] == 1
        assert 'aspect_sentiments' in result
        assert 'quality' in result['aspect_sentiments']
        assert 'value' in result['aspect_sentiments']
    
    def test_generate_aspect_insights(self):
        """Test generating aspect-specific insights"""
        reviews = [
            {
                'content': 'Great quality and excellent comfort',
                'sentiment': {
                    'aspects': {'quality': 0.9, 'comfort': 0.8, 'value': 0.6}
                }
            },
            {
                'content': 'Good quality but poor value',
                'sentiment': {
                    'aspects': {'quality': 0.7, 'comfort': 0.5, 'value': -0.2}
                }
            }
        ]
        
        result = self.service._generate_aspect_insights(reviews)
        
        assert 'quality' in result
        assert 'comfort' in result
        assert 'value' in result
        assert result['quality']['mention_count'] == 2
        assert result['quality']['average_score'] > 0
    
    def test_analyze_sentiment_trends(self):
        """Test analyzing sentiment trends over time"""
        reviews = [
            {
                'created_at': datetime(2024, 1, 15),
                'sentiment': {'score': 0.8}
            },
            {
                'created_at': datetime(2024, 1, 20),
                'sentiment': {'score': 0.6}
            },
            {
                'created_at': datetime(2024, 2, 10),
                'sentiment': {'score': 0.9}
            }
        ]
        
        result = self.service._analyze_sentiment_trends(reviews)
        
        assert 'monthly_trends' in result
        assert 'trend_direction' in result
        assert len(result['monthly_trends']) >= 1
        assert result['trend_direction'] in ['improving', 'declining', 'stable', 'insufficient_data']


class TestAnalyticsAPILambdaHandler:
    """Test cases for lambda_handler function"""
    
    def test_lambda_handler_semantic_search(self):
        """Test lambda handler for semantic review search"""
        with patch('analytics_api.AnalyticsService') as mock_service_class:
            mock_service = MagicMock()
            mock_service_class.return_value = mock_service
            mock_service.semantic_review_search.return_value = {
                'success': True,
                'results': []
            }
            
            event = {
                'httpMethod': 'POST',
                'path': '/analytics/reviews/search',
                'body': json.dumps({
                    'query': 'phones with good audio',
                    'filters': {'limit': 10}
                })
            }
            context = MagicMock()
            
            result = lambda_handler(event, context)
            
            assert result['statusCode'] == 200
            mock_service.semantic_review_search.assert_called_once()
    
    def test_lambda_handler_sentiment_analysis(self):
        """Test lambda handler for sentiment analysis"""
        with patch('analytics_api.AnalyticsService') as mock_service_class:
            mock_service = MagicMock()
            mock_service_class.return_value = mock_service
            mock_service.get_review_sentiment_analysis.return_value = {
                'success': True,
                'sentiment_analysis': {}
            }
            
            event = {
                'httpMethod': 'GET',
                'path': '/analytics/sentiment/prod_123',
                'pathParameters': {'productId': 'prod_123'}
            }
            context = MagicMock()
            
            result = lambda_handler(event, context)
            
            assert result['statusCode'] == 200
            mock_service.get_review_sentiment_analysis.assert_called_once_with('prod_123')
    
    def test_lambda_handler_product_recommendations(self):
        """Test lambda handler for product recommendations"""
        with patch('analytics_api.AnalyticsService') as mock_service_class:
            mock_service = MagicMock()
            mock_service_class.return_value = mock_service
            mock_service.get_product_recommendations_by_reviews.return_value = {
                'success': True,
                'recommendations': []
            }
            
            event = {
                'httpMethod': 'POST',
                'path': '/analytics/recommendations',
                'body': json.dumps({
                    'query': 'phones with good battery',
                    'user_preferences': {'price_range': [100, 500]}
                })
            }
            context = MagicMock()
            
            result = lambda_handler(event, context)
            
            assert result['statusCode'] == 200
            mock_service.get_product_recommendations_by_reviews.assert_called_once()
    
    def test_lambda_handler_aspect_insights(self):
        """Test lambda handler for aspect insights"""
        with patch('analytics_api.AnalyticsService') as mock_service_class:
            mock_service = MagicMock()
            mock_service_class.return_value = mock_service
            mock_service.get_review_insights_by_aspect.return_value = {
                'success': True,
                'product_insights': []
            }
            
            event = {
                'httpMethod': 'GET',
                'path': '/analytics/aspects/audio-quality',
                'pathParameters': {'aspect': 'audio-quality'},
                'queryStringParameters': {'category': 'Electronics'}
            }
            context = MagicMock()
            
            result = lambda_handler(event, context)
            
            assert result['statusCode'] == 200
            mock_service.get_review_insights_by_aspect.assert_called_once_with('audio-quality', 'Electronics')
    
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
        with patch('analytics_api.AnalyticsService') as mock_service_class:
            mock_service_class.side_effect = Exception("Service initialization error")
            
            event = {
                'httpMethod': 'POST',
                'path': '/analytics/reviews/search',
                'body': json.dumps({'query': 'test'})
            }
            context = MagicMock()
            
            result = lambda_handler(event, context)
            
            assert result['statusCode'] == 500
            response_body = json.loads(result['body'])
            assert 'Internal server error' in response_body['error']


if __name__ == '__main__':
    pytest.main([__file__])