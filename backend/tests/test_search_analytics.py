"""
Unit tests for Search Analytics Lambda function
"""
import unittest
from unittest.mock import Mock, patch, MagicMock
import json
import sys
import os
from datetime import datetime, timedelta

# Add the parent directory to the path to import modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from functions.search_analytics import SearchAnalytics, lambda_handler

class TestSearchAnalytics(unittest.TestCase):
    """Test cases for SearchAnalytics class"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.mock_search_analytics_table = Mock()
        
        with patch('functions.search_analytics.get_dynamodb_table') as mock_get_table:
            mock_get_table.return_value = self.mock_search_analytics_table
            self.analytics = SearchAnalytics()
    
    def test_track_search_event_success(self):
        """Test successful search event tracking"""
        search_data = {
            'searchTerm': 'wireless headphones',
            'userId': 'test-user-123',
            'sessionId': 'session-456',
            'filters': {'category': ['Electronics']},
            'sortBy': 'relevance',
            'resultsCount': 25,
            'clickedResults': ['product-1', 'product-2'],
            'conversionFlag': True,
            'searchDuration': 45,
            'refinements': 2,
            'pageViews': 3
        }
        
        self.mock_search_analytics_table.put_item.return_value = {
            'ResponseMetadata': {'HTTPStatusCode': 200}
        }
        
        with patch.object(self.analytics, '_update_search_frequency') as mock_freq, \
             patch.object(self.analytics, '_update_popular_terms') as mock_popular, \
             patch.object(self.analytics, '_update_user_search_patterns') as mock_patterns:
            
            result = self.analytics.track_search_event(search_data)
            
            self.assertTrue(result['success'])
            self.assertIn('eventId', result)
            self.mock_search_analytics_table.put_item.assert_called_once()
            mock_freq.assert_called_once_with('wireless headphones')
            mock_popular.assert_called_once()
            mock_patterns.assert_called_once_with(search_data)
    
    def test_track_search_event_empty_term(self):
        """Test tracking search event with empty search term"""
        search_data = {'searchTerm': ''}
        
        result = self.analytics.track_search_event(search_data)
        
        self.assertFalse(result['success'])
        self.assertIn('error', result)
        self.mock_search_analytics_table.put_item.assert_not_called()
    
    def test_track_search_event_minimal_data(self):
        """Test tracking search event with minimal required data"""
        search_data = {'searchTerm': 'test query'}
        
        self.mock_search_analytics_table.put_item.return_value = {
            'ResponseMetadata': {'HTTPStatusCode': 200}
        }
        
        with patch.object(self.analytics, '_update_search_frequency'), \
             patch.object(self.analytics, '_update_popular_terms'), \
             patch.object(self.analytics, '_update_user_search_patterns'):
            
            result = self.analytics.track_search_event(search_data)
            
            self.assertTrue(result['success'])
            
            # Verify the put_item call had default values
            call_args = self.mock_search_analytics_table.put_item.call_args
            item = call_args[1]['Item']
            self.assertEqual(item['searchTerm'], 'test query')
            self.assertEqual(item['userId'], 'anonymous')
            self.assertEqual(item['resultsCount'], 0)
            self.assertFalse(item['conversionFlag'])
    
    @patch('functions.search_analytics.cache_set')
    def test_get_search_analytics_24h(self, mock_cache_set):
        """Test getting 24h search analytics"""
        # Mock DynamoDB response
        mock_searches = [
            {
                'searchTerm': 'wireless headphones',
                'timestamp': datetime.utcnow().isoformat(),
                'hour': datetime.utcnow().strftime('%Y-%m-%d-%H'),
                'conversionFlag': True,
                'resultsCount': 25,
                'userId': 'user1'
            },
            {
                'searchTerm': 'bluetooth speaker',
                'timestamp': datetime.utcnow().isoformat(),
                'hour': datetime.utcnow().strftime('%Y-%m-%d-%H'),
                'conversionFlag': False,
                'resultsCount': 15,
                'userId': 'user2'
            }
        ]
        
        self.mock_search_analytics_table.scan.return_value = {
            'Items': mock_searches
        }
        
        result = self.analytics.get_search_analytics('24h', ['popular_terms', 'search_volume'])
        
        self.assertIn('popularTerms', result)
        self.assertIn('searchVolume', result)
        self.assertEqual(result['timeRange'], '24h')
        self.assertIn('generatedAt', result)
        
        # Verify popular terms
        self.assertEqual(len(result['popularTerms']), 2)
        self.assertEqual(result['popularTerms'][0]['term'], 'wireless headphones')
        
        # Verify search volume
        self.assertEqual(result['searchVolume']['totalSearches'], 2)
        mock_cache_set.assert_called_once()
    
    def test_get_search_analytics_different_time_ranges(self):
        """Test getting analytics for different time ranges"""
        self.mock_search_analytics_table.scan.return_value = {'Items': []}
        
        # Test different time ranges
        for time_range in ['1h', '7d', '30d', 'invalid']:
            result = self.analytics.get_search_analytics(time_range, ['popular_terms'])
            self.assertEqual(result['timeRange'], time_range)
    
    def test_get_user_search_insights_with_data(self):
        """Test getting user search insights with data"""
        user_id = 'test-user-123'
        mock_searches = [
            {
                'searchTerm': 'wireless headphones',
                'filters': '{"category": ["Electronics"]}',
                'conversionFlag': True,
                'resultsCount': 25
            },
            {
                'searchTerm': 'bluetooth speaker',
                'filters': '{"category": ["Electronics", "Audio"]}',
                'conversionFlag': False,
                'resultsCount': 15
            },
            {
                'searchTerm': 'wireless headphones',  # Duplicate term
                'filters': '{}',
                'conversionFlag': True,
                'resultsCount': 30
            }
        ]
        
        self.mock_search_analytics_table.scan.return_value = {
            'Items': mock_searches
        }
        
        with patch.object(self.analytics, '_calculate_search_frequency') as mock_freq, \
             patch.object(self.analytics, '_generate_user_recommendations') as mock_recs:
            
            mock_freq.return_value = 'frequent'
            mock_recs.return_value = ['gaming headphones', 'audio accessories']
            
            result = self.analytics.get_user_search_insights(user_id, 50)
            
            self.assertEqual(result['userId'], user_id)
            self.assertEqual(result['totalSearches'], 3)
            self.assertEqual(result['uniqueTerms'], 2)  # wireless headphones, bluetooth speaker
            self.assertEqual(result['conversionRate'], (2/3) * 100)  # 2 conversions out of 3 searches
            self.assertIn('Electronics', result['preferredCategories'])
            self.assertEqual(result['searchFrequency'], 'frequent')
            self.assertEqual(len(result['recommendations']), 2)
    
    def test_get_user_search_insights_no_data(self):
        """Test getting user search insights with no data"""
        user_id = 'nonexistent-user'
        self.mock_search_analytics_table.scan.return_value = {'Items': []}
        
        result = self.analytics.get_user_search_insights(user_id, 50)
        
        self.assertEqual(result['userId'], user_id)
        self.assertEqual(result['totalSearches'], 0)
        self.assertIn('No search history available', result['insights'])
    
    @patch('functions.search_analytics.cache_set')
    def test_update_trending_terms(self, mock_cache_set):
        """Test updating trending terms"""
        # Mock recent searches
        now = datetime.utcnow()
        mock_searches = [
            {
                'searchTerm': 'wireless headphones',
                'timestamp': now.isoformat(),
                'hour': now.strftime('%Y-%m-%d-%H')
            },
            {
                'searchTerm': 'wireless headphones',
                'timestamp': now.isoformat(),
                'hour': now.strftime('%Y-%m-%d-%H')
            },
            {
                'searchTerm': 'bluetooth speaker',
                'timestamp': now.isoformat(),
                'hour': now.strftime('%Y-%m-%d-%H')
            }
        ]
        
        self.mock_search_analytics_table.scan.return_value = {
            'Items': mock_searches
        }
        
        with patch.object(self.analytics, '_get_historical_average') as mock_historical:
            mock_historical.return_value = 1.0  # Historical average
            
            result = self.analytics.update_trending_terms()
            
            self.assertTrue(result['success'])
            self.assertEqual(result['trendingTermsCount'], 2)
            self.assertEqual(len(result['topTrending']), 2)
            
            # Verify cache was updated twice (trending and popular terms)
            self.assertEqual(mock_cache_set.call_count, 2)
    
    @patch('functions.search_analytics.cache_get')
    def test_get_search_suggestions_data_with_cache(self, mock_cache_get):
        """Test getting search suggestions data from cache"""
        popular_terms = [
            {'term': 'wireless headphones', 'count': 100},
            {'term': 'bluetooth speaker', 'count': 80}
        ]
        
        trending_terms = [
            {'term': 'gaming mouse', 'trendScore': 2.5},
            {'term': 'smart watch', 'trendScore': 2.0}
        ]
        
        def cache_get_side_effect(key):
            if 'popular_terms' in key:
                return json.dumps(popular_terms)
            elif 'trending_terms' in key:
                return json.dumps(trending_terms)
            return None
        
        mock_cache_get.side_effect = cache_get_side_effect
        
        result = self.analytics.get_search_suggestions_data()
        
        self.assertIn('popularTerms', result)
        self.assertIn('trendingTerms', result)
        self.assertEqual(len(result['popularTerms']), 2)
        self.assertEqual(len(result['trendingTerms']), 2)
        self.assertIn('lastUpdated', result)
    
    @patch('functions.search_analytics.cache_get')
    def test_get_search_suggestions_data_no_cache(self, mock_cache_get):
        """Test getting search suggestions data when cache is empty"""
        mock_cache_get.return_value = None
        
        with patch.object(self.analytics, '_generate_popular_terms_fallback') as mock_fallback:
            mock_fallback.return_value = [
                {'term': 'fallback term', 'count': 10}
            ]
            
            result = self.analytics.get_search_suggestions_data()
            
            self.assertIn('popularTerms', result)
            self.assertEqual(len(result['popularTerms']), 1)
            self.assertEqual(result['popularTerms'][0]['term'], 'fallback term')
            self.assertEqual(len(result['trendingTerms']), 0)  # No trending data
    
    @patch('functions.search_analytics.cache_get')
    @patch('functions.search_analytics.cache_set')
    def test_update_user_search_patterns(self, mock_cache_set, mock_cache_get):
        """Test updating user search patterns"""
        search_data = {
            'userId': 'test-user',
            'searchTerm': 'wireless headphones',
            'filters': {'category': ['Electronics']}
        }
        
        # Mock existing pattern
        existing_pattern = {
            'searchCount': 5,
            'categories': ['Audio'],
            'terms': ['bluetooth speaker'],
            'lastSearch': '2024-01-01T00:00:00'
        }
        
        mock_cache_get.return_value = json.dumps(existing_pattern)
        
        self.analytics._update_user_search_patterns(search_data)
        
        # Verify cache_set was called with updated pattern
        mock_cache_set.assert_called_once()
        call_args = mock_cache_set.call_args[0]
        updated_pattern = json.loads(call_args[1])
        
        self.assertEqual(updated_pattern['searchCount'], 6)  # Incremented
        self.assertIn('wireless headphones', updated_pattern['terms'])
        self.assertIn('Electronics', updated_pattern['categories'])
    
    def test_update_user_search_patterns_anonymous(self):
        """Test updating search patterns for anonymous user"""
        search_data = {
            'userId': 'anonymous',
            'searchTerm': 'test query'
        }
        
        # Should not update patterns for anonymous users
        with patch('functions.search_analytics.cache_get') as mock_cache_get:
            self.analytics._update_user_search_patterns(search_data)
            mock_cache_get.assert_not_called()
    
    def test_calculate_search_frequency(self):
        """Test calculating search frequency patterns"""
        now = datetime.utcnow()
        
        # Test very frequent (multiple per hour)
        frequent_searches = [
            {'timestamp': now.isoformat()},
            {'timestamp': (now - timedelta(minutes=30)).isoformat()}
        ]
        result = self.analytics._calculate_search_frequency(frequent_searches)
        self.assertEqual(result, 'very_frequent')
        
        # Test frequent (multiple per day)
        daily_searches = [
            {'timestamp': now.isoformat()},
            {'timestamp': (now - timedelta(hours=12)).isoformat()}
        ]
        result = self.analytics._calculate_search_frequency(daily_searches)
        self.assertEqual(result, 'frequent')
        
        # Test regular (weekly)
        weekly_searches = [
            {'timestamp': now.isoformat()},
            {'timestamp': (now - timedelta(days=3)).isoformat()}
        ]
        result = self.analytics._calculate_search_frequency(weekly_searches)
        self.assertEqual(result, 'regular')
        
        # Test occasional (less than weekly)
        occasional_searches = [
            {'timestamp': now.isoformat()},
            {'timestamp': (now - timedelta(days=10)).isoformat()}
        ]
        result = self.analytics._calculate_search_frequency(occasional_searches)
        self.assertEqual(result, 'occasional')
        
        # Test insufficient data
        single_search = [{'timestamp': now.isoformat()}]
        result = self.analytics._calculate_search_frequency(single_search)
        self.assertEqual(result, 'insufficient_data')
    
    def test_generate_user_recommendations(self):
        """Test generating user recommendations"""
        search_terms = ['wireless headphones', 'gaming mouse', 'phone case']
        categories = ['Electronics', 'Audio', 'Electronics']
        
        recommendations = self.analytics._generate_user_recommendations(search_terms, categories)
        
        self.assertIsInstance(recommendations, list)
        self.assertTrue(len(recommendations) <= 5)
        
        # Should include recommendations based on search patterns
        self.assertTrue(any('bluetooth' in rec or 'gaming' in rec or 'phone' in rec or 'electronics' in rec 
                          for rec in recommendations))
    
    def test_generate_popular_terms_fallback(self):
        """Test generating popular terms fallback"""
        mock_searches = [
            {'searchTerm': 'wireless headphones'},
            {'searchTerm': 'wireless headphones'},
            {'searchTerm': 'bluetooth speaker'}
        ]
        
        self.mock_search_analytics_table.scan.return_value = {
            'Items': mock_searches
        }
        
        result = self.analytics._generate_popular_terms_fallback()
        
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]['term'], 'wireless headphones')
        self.assertEqual(result[0]['count'], 2)
        self.assertEqual(result[1]['term'], 'bluetooth speaker')
        self.assertEqual(result[1]['count'], 1)

class TestSearchAnalyticsLambdaHandler(unittest.TestCase):
    """Test cases for lambda_handler function"""
    
    @patch('functions.search_analytics.SearchAnalytics')
    def test_lambda_handler_track_event(self, mock_analytics_class):
        """Test lambda handler for tracking search event"""
        mock_analytics = Mock()
        mock_analytics_class.return_value = mock_analytics
        mock_analytics.track_search_event.return_value = {
            'success': True,
            'eventId': 'test-event-123'
        }
        
        event = {
            'httpMethod': 'POST',
            'path': '/api/search-analytics/track',
            'body': json.dumps({
                'searchTerm': 'wireless headphones',
                'userId': 'test-user'
            })
        }
        
        result = lambda_handler(event, None)
        
        self.assertEqual(result['statusCode'], 200)
        body = json.loads(result['body'])
        self.assertTrue(body['success'])
        self.assertEqual(body['eventId'], 'test-event-123')
    
    @patch('functions.search_analytics.SearchAnalytics')
    def test_lambda_handler_get_analytics(self, mock_analytics_class):
        """Test lambda handler for getting analytics"""
        mock_analytics = Mock()
        mock_analytics_class.return_value = mock_analytics
        mock_analytics.get_search_analytics.return_value = {
            'popularTerms': [{'term': 'test', 'count': 10}],
            'timeRange': '24h'
        }
        
        event = {
            'httpMethod': 'GET',
            'path': '/api/search-analytics/analytics',
            'queryStringParameters': {
                'timeRange': '24h',
                'metrics': 'popular_terms,search_volume'
            }
        }
        
        result = lambda_handler(event, None)
        
        self.assertEqual(result['statusCode'], 200)
        body = json.loads(result['body'])
        self.assertIn('popularTerms', body)
        self.assertEqual(body['timeRange'], '24h')
        
        # Verify method was called with correct parameters
        mock_analytics.get_search_analytics.assert_called_once_with(
            '24h', ['popular_terms', 'search_volume']
        )
    
    @patch('functions.search_analytics.SearchAnalytics')
    def test_lambda_handler_user_insights(self, mock_analytics_class):
        """Test lambda handler for user insights"""
        mock_analytics = Mock()
        mock_analytics_class.return_value = mock_analytics
        mock_analytics.get_user_search_insights.return_value = {
            'userId': 'test-user',
            'totalSearches': 10
        }
        
        event = {
            'httpMethod': 'GET',
            'path': '/api/search-analytics/user-insights',
            'queryStringParameters': {
                'userId': 'test-user',
                'limit': '25'
            }
        }
        
        result = lambda_handler(event, None)
        
        self.assertEqual(result['statusCode'], 200)
        body = json.loads(result['body'])
        self.assertEqual(body['userId'], 'test-user')
        
        # Verify method was called with correct parameters
        mock_analytics.get_user_search_insights.assert_called_once_with('test-user', 25)
    
    def test_lambda_handler_user_insights_missing_user_id(self):
        """Test lambda handler for user insights without userId"""
        event = {
            'httpMethod': 'GET',
            'path': '/api/search-analytics/user-insights',
            'queryStringParameters': {}
        }
        
        result = lambda_handler(event, None)
        
        self.assertEqual(result['statusCode'], 400)
        body = json.loads(result['body'])
        self.assertIn('error', body)
        self.assertIn('userId parameter is required', body['error'])
    
    @patch('functions.search_analytics.SearchAnalytics')
    def test_lambda_handler_update_trending(self, mock_analytics_class):
        """Test lambda handler for updating trending terms"""
        mock_analytics = Mock()
        mock_analytics_class.return_value = mock_analytics
        mock_analytics.update_trending_terms.return_value = {
            'success': True,
            'trendingTermsCount': 25
        }
        
        event = {
            'httpMethod': 'POST',
            'path': '/api/search-analytics/trending'
        }
        
        result = lambda_handler(event, None)
        
        self.assertEqual(result['statusCode'], 200)
        body = json.loads(result['body'])
        self.assertTrue(body['success'])
        self.assertEqual(body['trendingTermsCount'], 25)
    
    @patch('functions.search_analytics.SearchAnalytics')
    def test_lambda_handler_suggestions_data(self, mock_analytics_class):
        """Test lambda handler for getting suggestions data"""
        mock_analytics = Mock()
        mock_analytics_class.return_value = mock_analytics
        mock_analytics.get_search_suggestions_data.return_value = {
            'popularTerms': [{'term': 'test', 'count': 10}],
            'trendingTerms': []
        }
        
        event = {
            'httpMethod': 'GET',
            'path': '/api/search-analytics/suggestions-data'
        }
        
        result = lambda_handler(event, None)
        
        self.assertEqual(result['statusCode'], 200)
        body = json.loads(result['body'])
        self.assertIn('popularTerms', body)
        self.assertIn('trendingTerms', body)
    
    def test_lambda_handler_invalid_path(self):
        """Test lambda handler with invalid path"""
        event = {
            'httpMethod': 'GET',
            'path': '/api/search-analytics/invalid'
        }
        
        result = lambda_handler(event, None)
        
        self.assertEqual(result['statusCode'], 404)
        body = json.loads(result['body'])
        self.assertIn('error', body)
    
    @patch('functions.search_analytics.SearchAnalytics')
    def test_lambda_handler_error(self, mock_analytics_class):
        """Test lambda handler error handling"""
        mock_analytics_class.side_effect = Exception('Database connection failed')
        
        event = {
            'httpMethod': 'GET',
            'path': '/api/search-analytics/analytics'
        }
        
        result = lambda_handler(event, None)
        
        self.assertEqual(result['statusCode'], 500)
        body = json.loads(result['body'])
        self.assertIn('error', body)
        self.assertIn('Internal server error', body['error'])
    
    def test_lambda_handler_cors_headers(self):
        """Test that CORS headers are included in responses"""
        event = {
            'httpMethod': 'GET',
            'path': '/api/search-analytics/invalid'
        }
        
        result = lambda_handler(event, None)
        
        headers = result['headers']
        self.assertIn('Access-Control-Allow-Origin', headers)
        self.assertEqual(headers['Access-Control-Allow-Origin'], '*')

if __name__ == '__main__':
    unittest.main()