"""
Search Analytics Lambda function for Unicorn E-Commerce
Tracks and analyzes search behavior, manages popular terms and user patterns
"""
import json
import logging
import boto3
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
from collections import defaultdict, Counter
import re

try:
    from shared.database import (
        db, get_dynamodb_table, get_cache_key, cache_get, cache_set, cache_delete
    )
    from shared.config import config
except ImportError:
    import sys
    import os
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from shared.database import (
        db, get_dynamodb_table, get_cache_key, cache_get, cache_set, cache_delete
    )
    from shared.config import config

# Configure logging
logging.basicConfig(level=getattr(logging, config.LOG_LEVEL))
logger = logging.getLogger(__name__)

class SearchAnalytics:
    """Search analytics handler for tracking and analyzing search behavior"""
    
    def __init__(self):
        self.search_analytics_table = get_dynamodb_table(config.SEARCH_ANALYTICS_TABLE)
        
    def track_search_event(self, search_data: Dict[str, Any]) -> Dict[str, Any]:
        """Track a search event with detailed analytics"""
        try:
            timestamp = datetime.utcnow()
            search_term = search_data.get('searchTerm', '').lower().strip()
            
            if not search_term:
                return {'success': False, 'error': 'Search term is required'}
            
            # Prepare search event data
            event_data = {
                'searchTerm': search_term,
                'timestamp': timestamp.isoformat(),
                'date': timestamp.strftime('%Y-%m-%d'),
                'hour': timestamp.strftime('%Y-%m-%d-%H'),
                'userId': search_data.get('userId', 'anonymous'),
                'sessionId': search_data.get('sessionId', ''),
                'filters': json.dumps(search_data.get('filters', {})),
                'sortBy': search_data.get('sortBy', 'relevance'),
                'resultsCount': search_data.get('resultsCount', 0),
                'clickedResults': json.dumps(search_data.get('clickedResults', [])),
                'userAgent': search_data.get('userAgent', ''),
                'ipAddress': search_data.get('ipAddress', ''),
                'conversionFlag': search_data.get('conversionFlag', False),  # Did user purchase?
                'searchDuration': search_data.get('searchDuration', 0),  # Time spent on search
                'refinements': search_data.get('refinements', 0),  # Number of filter changes
                'pageViews': search_data.get('pageViews', 1)  # Pages of results viewed
            }
            
            # Store in DynamoDB
            self.search_analytics_table.put_item(Item=event_data)
            
            # Update real-time analytics
            self._update_search_frequency(search_term)
            self._update_popular_terms()
            self._update_user_search_patterns(search_data)
            
            logger.info(f"Tracked search event for term: {search_term}")
            return {'success': True, 'eventId': f"{search_term}_{timestamp.isoformat()}"}
            
        except Exception as e:
            logger.error(f"Error tracking search event: {e}")
            return {'success': False, 'error': str(e)}
    
    def get_search_analytics(self, time_range: str = '24h', 
                           metrics: List[str] = None) -> Dict[str, Any]:
        """Get comprehensive search analytics"""
        try:
            if metrics is None:
                metrics = ['popular_terms', 'search_volume', 'conversion_rate', 'user_patterns']
            
            analytics = {}
            
            # Calculate time range
            end_time = datetime.utcnow()
            if time_range == '1h':
                start_time = end_time - timedelta(hours=1)
            elif time_range == '24h':
                start_time = end_time - timedelta(hours=24)
            elif time_range == '7d':
                start_time = end_time - timedelta(days=7)
            elif time_range == '30d':
                start_time = end_time - timedelta(days=30)
            else:
                start_time = end_time - timedelta(hours=24)
            
            # Get analytics for each requested metric
            if 'popular_terms' in metrics:
                analytics['popularTerms'] = self._get_popular_terms_analytics(start_time, end_time)
            
            if 'search_volume' in metrics:
                analytics['searchVolume'] = self._get_search_volume_analytics(start_time, end_time)
            
            if 'conversion_rate' in metrics:
                analytics['conversionRate'] = self._get_conversion_analytics(start_time, end_time)
            
            if 'user_patterns' in metrics:
                analytics['userPatterns'] = self._get_user_pattern_analytics(start_time, end_time)
            
            if 'trending_terms' in metrics:
                analytics['trendingTerms'] = self._get_trending_terms(start_time, end_time)
            
            if 'search_performance' in metrics:
                analytics['searchPerformance'] = self._get_search_performance_metrics(start_time, end_time)
            
            analytics['timeRange'] = time_range
            analytics['generatedAt'] = datetime.utcnow().isoformat()
            
            # Cache the results
            cache_key = get_cache_key('analytics', f"{time_range}_{hash(str(metrics))}")
            cache_set(cache_key, json.dumps(analytics, default=str), ttl=300)  # 5 minutes
            
            logger.info(f"Generated search analytics for {time_range} with {len(metrics)} metrics")
            return analytics
            
        except Exception as e:
            logger.error(f"Error getting search analytics: {e}")
            return {'error': str(e)}
    
    def get_user_search_insights(self, user_id: str, limit: int = 50) -> Dict[str, Any]:
        """Get personalized search insights for a user"""
        try:
            # Query user's search history
            response = self.search_analytics_table.scan(
                FilterExpression='userId = :userId',
                ExpressionAttributeValues={':userId': user_id},
                Limit=limit
            )
            
            user_searches = response.get('Items', [])
            
            if not user_searches:
                return {
                    'userId': user_id,
                    'totalSearches': 0,
                    'insights': 'No search history available'
                }
            
            # Analyze user patterns
            search_terms = [item['searchTerm'] for item in user_searches]
            search_categories = []
            conversion_events = 0
            total_results_viewed = 0
            
            for search in user_searches:
                filters = json.loads(search.get('filters', '{}'))
                if 'category' in filters:
                    search_categories.extend(filters['category'])
                
                if search.get('conversionFlag', False):
                    conversion_events += 1
                
                total_results_viewed += search.get('resultsCount', 0)
            
            # Generate insights
            insights = {
                'userId': user_id,
                'totalSearches': len(user_searches),
                'uniqueTerms': len(set(search_terms)),
                'topSearchTerms': [term for term, count in Counter(search_terms).most_common(10)],
                'preferredCategories': [cat for cat, count in Counter(search_categories).most_common(5)],
                'conversionRate': (conversion_events / len(user_searches)) * 100 if user_searches else 0,
                'avgResultsPerSearch': total_results_viewed / len(user_searches) if user_searches else 0,
                'searchFrequency': self._calculate_search_frequency(user_searches),
                'recommendations': self._generate_user_recommendations(search_terms, search_categories)
            }
            
            logger.info(f"Generated search insights for user: {user_id}")
            return insights
            
        except Exception as e:
            logger.error(f"Error getting user search insights: {e}")
            return {'error': str(e)}
    
    def update_trending_terms(self) -> Dict[str, Any]:
        """Update trending search terms in cache"""
        try:
            # Get recent search data (last 24 hours)
            end_time = datetime.utcnow()
            start_time = end_time - timedelta(hours=24)
            
            # Query recent searches
            response = self.search_analytics_table.scan(
                FilterExpression='#ts BETWEEN :start_time AND :end_time',
                ExpressionAttributeNames={'#ts': 'timestamp'},
                ExpressionAttributeValues={
                    ':start_time': start_time.isoformat(),
                    ':end_time': end_time.isoformat()
                }
            )
            
            recent_searches = response.get('Items', [])
            
            # Count search term frequencies
            term_counts = Counter()
            hourly_counts = defaultdict(lambda: defaultdict(int))
            
            for search in recent_searches:
                term = search['searchTerm']
                hour = search['hour']
                term_counts[term] += 1
                hourly_counts[hour][term] += 1
            
            # Calculate trending score (recent frequency vs historical average)
            trending_terms = []
            for term, recent_count in term_counts.most_common(100):
                # Get historical average (simplified - in production, use more sophisticated trending algorithm)
                historical_avg = self._get_historical_average(term)
                trend_score = recent_count / max(historical_avg, 1)
                
                trending_terms.append({
                    'term': term,
                    'recentCount': recent_count,
                    'trendScore': trend_score,
                    'isRising': trend_score > 1.5,
                    'hourlyData': dict(hourly_counts.get(term, {}))
                })
            
            # Sort by trend score
            trending_terms.sort(key=lambda x: x['trendScore'], reverse=True)
            
            # Update cache
            trending_key = get_cache_key('trending_terms', 'current')
            cache_set(trending_key, json.dumps(trending_terms[:50]), ttl=1800)  # 30 minutes
            
            # Update popular terms for auto-complete
            popular_terms = [
                {'term': term['term'], 'count': term['recentCount']}
                for term in trending_terms[:100]
            ]
            
            popular_key = get_cache_key('popular_terms', 'all')
            cache_set(popular_key, json.dumps(popular_terms), ttl=3600)  # 1 hour
            
            logger.info(f"Updated {len(trending_terms)} trending terms")
            return {
                'success': True,
                'trendingTermsCount': len(trending_terms),
                'topTrending': trending_terms[:10]
            }
            
        except Exception as e:
            logger.error(f"Error updating trending terms: {e}")
            return {'success': False, 'error': str(e)}
    
    def get_search_suggestions_data(self) -> Dict[str, Any]:
        """Get data for search suggestions and auto-complete"""
        try:
            # Get popular terms from cache
            popular_key = get_cache_key('popular_terms', 'all')
            popular_terms_json = cache_get(popular_key)
            
            if popular_terms_json:
                popular_terms = json.loads(popular_terms_json)
            else:
                # Fallback: generate from recent data
                popular_terms = self._generate_popular_terms_fallback()
            
            # Get trending terms
            trending_key = get_cache_key('trending_terms', 'current')
            trending_terms_json = cache_get(trending_key)
            
            if trending_terms_json:
                trending_terms = json.loads(trending_terms_json)
            else:
                trending_terms = []
            
            # Combine and format for suggestions
            suggestions_data = {
                'popularTerms': popular_terms[:50],
                'trendingTerms': [
                    {'term': t['term'], 'trendScore': t['trendScore']}
                    for t in trending_terms[:20]
                ],
                'lastUpdated': datetime.utcnow().isoformat()
            }
            
            return suggestions_data
            
        except Exception as e:
            logger.error(f"Error getting search suggestions data: {e}")
            return {'error': str(e)}
    
    def _update_search_frequency(self, search_term: str):
        """Update search term frequency in cache"""
        try:
            freq_key = get_cache_key('search_freq', search_term)
            current_count = cache_get(freq_key) or '0'
            new_count = int(current_count) + 1
            cache_set(freq_key, str(new_count), ttl=86400)  # 24 hours
            
        except Exception as e:
            logger.error(f"Error updating search frequency: {e}")
    
    def _update_popular_terms(self):
        """Update popular terms list in cache"""
        try:
            # This is called frequently, so we'll update incrementally
            # Full update happens in update_trending_terms()
            pass
            
        except Exception as e:
            logger.error(f"Error updating popular terms: {e}")
    
    def _update_user_search_patterns(self, search_data: Dict[str, Any]):
        """Update user search patterns for personalization"""
        try:
            user_id = search_data.get('userId')
            if not user_id or user_id == 'anonymous':
                return
            
            # Update user's search pattern in cache
            pattern_key = get_cache_key('user_pattern', user_id)
            pattern_data = cache_get(pattern_key)
            
            if pattern_data:
                pattern = json.loads(pattern_data)
            else:
                pattern = {
                    'searchCount': 0,
                    'categories': [],
                    'terms': [],
                    'lastSearch': None
                }
            
            # Update pattern
            pattern['searchCount'] += 1
            pattern['terms'].append(search_data.get('searchTerm', ''))
            pattern['lastSearch'] = datetime.utcnow().isoformat()
            
            filters = search_data.get('filters', {})
            if 'category' in filters:
                pattern['categories'].extend(filters['category'])
            
            # Keep only recent data (last 100 searches)
            pattern['terms'] = pattern['terms'][-100:]
            pattern['categories'] = pattern['categories'][-100:]
            
            # Cache updated pattern
            cache_set(pattern_key, json.dumps(pattern), ttl=86400 * 7)  # 7 days
            
        except Exception as e:
            logger.error(f"Error updating user search patterns: {e}")
    
    def _get_popular_terms_analytics(self, start_time: datetime, end_time: datetime) -> List[Dict[str, Any]]:
        """Get popular terms analytics for time range"""
        try:
            response = self.search_analytics_table.scan(
                FilterExpression='#ts BETWEEN :start_time AND :end_time',
                ExpressionAttributeNames={'#ts': 'timestamp'},
                ExpressionAttributeValues={
                    ':start_time': start_time.isoformat(),
                    ':end_time': end_time.isoformat()
                }
            )
            
            searches = response.get('Items', [])
            term_counts = Counter(search['searchTerm'] for search in searches)
            
            return [
                {'term': term, 'count': count, 'percentage': (count / len(searches)) * 100}
                for term, count in term_counts.most_common(20)
            ]
            
        except Exception as e:
            logger.error(f"Error getting popular terms analytics: {e}")
            return []
    
    def _get_search_volume_analytics(self, start_time: datetime, end_time: datetime) -> Dict[str, Any]:
        """Get search volume analytics"""
        try:
            response = self.search_analytics_table.scan(
                FilterExpression='#ts BETWEEN :start_time AND :end_time',
                ExpressionAttributeNames={'#ts': 'timestamp'},
                ExpressionAttributeValues={
                    ':start_time': start_time.isoformat(),
                    ':end_time': end_time.isoformat()
                }
            )
            
            searches = response.get('Items', [])
            
            # Group by hour
            hourly_counts = defaultdict(int)
            for search in searches:
                hour = search['hour']
                hourly_counts[hour] += 1
            
            return {
                'totalSearches': len(searches),
                'hourlyBreakdown': dict(hourly_counts),
                'averagePerHour': len(searches) / max(len(hourly_counts), 1),
                'peakHour': max(hourly_counts.items(), key=lambda x: x[1])[0] if hourly_counts else None
            }
            
        except Exception as e:
            logger.error(f"Error getting search volume analytics: {e}")
            return {}
    
    def _get_conversion_analytics(self, start_time: datetime, end_time: datetime) -> Dict[str, Any]:
        """Get conversion rate analytics"""
        try:
            response = self.search_analytics_table.scan(
                FilterExpression='#ts BETWEEN :start_time AND :end_time',
                ExpressionAttributeNames={'#ts': 'timestamp'},
                ExpressionAttributeValues={
                    ':start_time': start_time.isoformat(),
                    ':end_time': end_time.isoformat()
                }
            )
            
            searches = response.get('Items', [])
            
            total_searches = len(searches)
            conversions = sum(1 for search in searches if search.get('conversionFlag', False))
            
            # Conversion by search term
            term_conversions = defaultdict(lambda: {'searches': 0, 'conversions': 0})
            for search in searches:
                term = search['searchTerm']
                term_conversions[term]['searches'] += 1
                if search.get('conversionFlag', False):
                    term_conversions[term]['conversions'] += 1
            
            # Calculate conversion rates
            term_rates = {}
            for term, data in term_conversions.items():
                if data['searches'] > 0:
                    term_rates[term] = (data['conversions'] / data['searches']) * 100
            
            return {
                'overallConversionRate': (conversions / total_searches) * 100 if total_searches > 0 else 0,
                'totalConversions': conversions,
                'topConvertingTerms': sorted(term_rates.items(), key=lambda x: x[1], reverse=True)[:10]
            }
            
        except Exception as e:
            logger.error(f"Error getting conversion analytics: {e}")
            return {}
    
    def _get_user_pattern_analytics(self, start_time: datetime, end_time: datetime) -> Dict[str, Any]:
        """Get user pattern analytics"""
        try:
            response = self.search_analytics_table.scan(
                FilterExpression='#ts BETWEEN :start_time AND :end_time',
                ExpressionAttributeNames={'#ts': 'timestamp'},
                ExpressionAttributeValues={
                    ':start_time': start_time.isoformat(),
                    ':end_time': end_time.isoformat()
                }
            )
            
            searches = response.get('Items', [])
            
            # Analyze user patterns
            unique_users = set(search['userId'] for search in searches if search['userId'] != 'anonymous')
            user_search_counts = Counter(search['userId'] for search in searches)
            
            # Session analysis
            session_lengths = defaultdict(int)
            for search in searches:
                session_id = search.get('sessionId', '')
                if session_id:
                    session_lengths[session_id] += 1
            
            return {
                'uniqueUsers': len(unique_users),
                'anonymousSearches': user_search_counts.get('anonymous', 0),
                'averageSearchesPerUser': sum(user_search_counts.values()) / max(len(unique_users), 1),
                'averageSessionLength': sum(session_lengths.values()) / max(len(session_lengths), 1),
                'topActiveUsers': user_search_counts.most_common(10)
            }
            
        except Exception as e:
            logger.error(f"Error getting user pattern analytics: {e}")
            return {}
    
    def _get_trending_terms(self, start_time: datetime, end_time: datetime) -> List[Dict[str, Any]]:
        """Get trending terms for the time period"""
        try:
            trending_key = get_cache_key('trending_terms', 'current')
            trending_terms_json = cache_get(trending_key)
            
            if trending_terms_json:
                return json.loads(trending_terms_json)[:20]
            else:
                return []
                
        except Exception as e:
            logger.error(f"Error getting trending terms: {e}")
            return []
    
    def _get_search_performance_metrics(self, start_time: datetime, end_time: datetime) -> Dict[str, Any]:
        """Get search performance metrics"""
        try:
            response = self.search_analytics_table.scan(
                FilterExpression='#ts BETWEEN :start_time AND :end_time',
                ExpressionAttributeNames={'#ts': 'timestamp'},
                ExpressionAttributeValues={
                    ':start_time': start_time.isoformat(),
                    ':end_time': end_time.isoformat()
                }
            )
            
            searches = response.get('Items', [])
            
            if not searches:
                return {}
            
            # Calculate performance metrics
            total_results = sum(search.get('resultsCount', 0) for search in searches)
            zero_result_searches = sum(1 for search in searches if search.get('resultsCount', 0) == 0)
            total_duration = sum(search.get('searchDuration', 0) for search in searches)
            total_refinements = sum(search.get('refinements', 0) for search in searches)
            
            return {
                'averageResultsPerSearch': total_results / len(searches),
                'zeroResultRate': (zero_result_searches / len(searches)) * 100,
                'averageSearchDuration': total_duration / len(searches),
                'averageRefinements': total_refinements / len(searches),
                'searchSuccessRate': ((len(searches) - zero_result_searches) / len(searches)) * 100
            }
            
        except Exception as e:
            logger.error(f"Error getting search performance metrics: {e}")
            return {}
    
    def _get_historical_average(self, term: str) -> float:
        """Get historical average for a search term (simplified)"""
        try:
            # In a real implementation, this would query historical data
            # For now, return a simple estimate based on cached frequency
            freq_key = get_cache_key('search_freq', term)
            freq = cache_get(freq_key) or '1'
            return float(freq) / 24  # Rough daily average
            
        except Exception as e:
            logger.error(f"Error getting historical average: {e}")
            return 1.0
    
    def _calculate_search_frequency(self, user_searches: List[Dict[str, Any]]) -> str:
        """Calculate user's search frequency pattern"""
        if len(user_searches) < 2:
            return 'insufficient_data'
        
        # Calculate time between searches
        timestamps = [datetime.fromisoformat(search['timestamp']) for search in user_searches]
        timestamps.sort()
        
        intervals = []
        for i in range(1, len(timestamps)):
            interval = (timestamps[i] - timestamps[i-1]).total_seconds() / 3600  # hours
            intervals.append(interval)
        
        avg_interval = sum(intervals) / len(intervals)
        
        if avg_interval < 1:
            return 'very_frequent'  # Multiple searches per hour
        elif avg_interval < 24:
            return 'frequent'  # Multiple searches per day
        elif avg_interval < 168:
            return 'regular'  # Weekly searches
        else:
            return 'occasional'  # Less than weekly
    
    def _generate_user_recommendations(self, search_terms: List[str], 
                                     categories: List[str]) -> List[str]:
        """Generate personalized recommendations for user"""
        recommendations = []
        
        # Analyze search patterns
        term_counter = Counter(search_terms)
        category_counter = Counter(categories)
        
        # Recommend related terms
        for term, count in term_counter.most_common(3):
            if 'wireless' in term:
                recommendations.append('bluetooth speakers')
            elif 'gaming' in term:
                recommendations.append('gaming accessories')
            elif 'phone' in term:
                recommendations.append('phone accessories')
        
        # Recommend based on categories
        for category, count in category_counter.most_common(2):
            if category == 'Electronics':
                recommendations.append('latest electronics')
            elif category == 'Audio':
                recommendations.append('premium audio equipment')
        
        return list(set(recommendations))[:5]  # Remove duplicates and limit
    
    def _generate_popular_terms_fallback(self) -> List[Dict[str, Any]]:
        """Generate popular terms fallback when cache is empty"""
        try:
            # Get recent searches to build popular terms
            end_time = datetime.utcnow()
            start_time = end_time - timedelta(days=7)
            
            response = self.search_analytics_table.scan(
                FilterExpression='#ts BETWEEN :start_time AND :end_time',
                ExpressionAttributeNames={'#ts': 'timestamp'},
                ExpressionAttributeValues={
                    ':start_time': start_time.isoformat(),
                    ':end_time': end_time.isoformat()
                }
            )
            
            searches = response.get('Items', [])
            term_counts = Counter(search['searchTerm'] for search in searches)
            
            return [
                {'term': term, 'count': count}
                for term, count in term_counts.most_common(100)
            ]
            
        except Exception as e:
            logger.error(f"Error generating popular terms fallback: {e}")
            return []

def lambda_handler(event, context):
    """Lambda handler for search analytics"""
    try:
        # Parse request
        http_method = event.get('httpMethod', 'POST')
        path = event.get('path', '')
        query_params = event.get('queryStringParameters') or {}
        body = event.get('body')
        
        if body:
            try:
                body = json.loads(body)
            except json.JSONDecodeError:
                body = {}
        else:
            body = {}
        
        # Initialize search analytics
        analytics = SearchAnalytics()
        
        # Route requests
        if path.endswith('/track') and http_method == 'POST':
            # Track search event
            result = analytics.track_search_event(body)
            
            return {
                'statusCode': 200 if result.get('success') else 400,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*',
                    'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token',
                    'Access-Control-Allow-Methods': 'POST,OPTIONS'
                },
                'body': json.dumps(result)
            }
        
        elif path.endswith('/analytics') and http_method == 'GET':
            # Get search analytics
            time_range = query_params.get('timeRange', '24h')
            metrics = query_params.get('metrics', '').split(',') if query_params.get('metrics') else None
            
            result = analytics.get_search_analytics(time_range, metrics)
            
            return {
                'statusCode': 200,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*',
                    'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token',
                    'Access-Control-Allow-Methods': 'GET,OPTIONS'
                },
                'body': json.dumps(result, default=str)
            }
        
        elif path.endswith('/user-insights') and http_method == 'GET':
            # Get user search insights
            user_id = query_params.get('userId')
            limit = int(query_params.get('limit', '50'))
            
            if not user_id:
                return {
                    'statusCode': 400,
                    'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
                    'body': json.dumps({'error': 'userId parameter is required'})
                }
            
            result = analytics.get_user_search_insights(user_id, limit)
            
            return {
                'statusCode': 200,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*',
                    'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token',
                    'Access-Control-Allow-Methods': 'GET,OPTIONS'
                },
                'body': json.dumps(result, default=str)
            }
        
        elif path.endswith('/trending') and http_method == 'POST':
            # Update trending terms
            result = analytics.update_trending_terms()
            
            return {
                'statusCode': 200,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*',
                    'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token',
                    'Access-Control-Allow-Methods': 'POST,OPTIONS'
                },
                'body': json.dumps(result)
            }
        
        elif path.endswith('/suggestions-data') and http_method == 'GET':
            # Get suggestions data
            result = analytics.get_search_suggestions_data()
            
            return {
                'statusCode': 200,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*',
                    'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token',
                    'Access-Control-Allow-Methods': 'GET,OPTIONS'
                },
                'body': json.dumps(result, default=str)
            }
        
        else:
            return {
                'statusCode': 404,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps({'error': 'Endpoint not found'})
            }
    
    except Exception as e:
        logger.error(f"Lambda handler error: {e}")
        return {
            'statusCode': 500,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({'error': 'Internal server error', 'message': str(e)})
        }

# For local testing
if __name__ == '__main__':
    # Test search analytics
    analytics = SearchAnalytics()
    
    # Test tracking search event
    test_search_data = {
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
    
    result = analytics.track_search_event(test_search_data)
    print("Track search event result:")
    print(json.dumps(result, indent=2))
    
    # Test getting analytics
    analytics_result = analytics.get_search_analytics('24h', ['popular_terms', 'search_volume'])
    print("\nSearch analytics result:")
    print(json.dumps(analytics_result, indent=2, default=str))
    
    # Test lambda handler
    test_event = {
        'httpMethod': 'POST',
        'path': '/api/search-analytics/track',
        'body': json.dumps(test_search_data)
    }
    
    result = lambda_handler(test_event, None)
    print("\nLambda handler test result:")
    print(json.dumps(json.loads(result['body']), indent=2))