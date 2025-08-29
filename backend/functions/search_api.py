"""
Search API Lambda function for Unicorn E-Commerce
Provides intelligent product search with auto-complete suggestions
"""
import json
import logging
import boto3
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
import re
import math

try:
    from shared.database import (
        db, get_documentdb_collection, get_dynamodb_table,
        get_cache_key, cache_get, cache_set
    )
    from shared.config import config
except ImportError:
    import sys
    import os
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from shared.database import (
        db, get_documentdb_collection, get_dynamodb_table,
        get_cache_key, cache_get, cache_set
    )
    from shared.config import config

# Configure logging
logging.basicConfig(level=getattr(logging, config.LOG_LEVEL))
logger = logging.getLogger(__name__)

# Initialize Bedrock client for embeddings
bedrock_client = boto3.client('bedrock-runtime', region_name=config.AWS_REGION)

class SearchAPI:
    """Search API handler with auto-complete and semantic search"""
    
    def __init__(self):
        self.products_collection = get_documentdb_collection('products')
        self.search_analytics_table = get_dynamodb_table(config.SEARCH_ANALYTICS_TABLE)
        
    def get_auto_complete_suggestions(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Get auto-complete suggestions from cache and database"""
        try:
            if not query or len(query) < 2:
                return []
            
            query_lower = query.lower().strip()
            
            # Try to get suggestions from cache first
            cache_key = get_cache_key('autocomplete', query_lower)
            cached_suggestions = cache_get(cache_key)
            
            if cached_suggestions:
                logger.info(f"Retrieved auto-complete suggestions from cache for query: {query}")
                return json.loads(cached_suggestions)
            
            suggestions = []
            
            # Get popular search terms from ElastiCache
            popular_terms = self._get_popular_search_terms(query_lower, limit // 2)
            suggestions.extend(popular_terms)
            
            # Get product-based suggestions from DocumentDB
            product_suggestions = self._get_product_suggestions(query_lower, limit - len(suggestions))
            suggestions.extend(product_suggestions)
            
            # Get category suggestions
            if len(suggestions) < limit:
                category_suggestions = self._get_category_suggestions(query_lower, limit - len(suggestions))
                suggestions.extend(category_suggestions)
            
            # Sort by relevance and popularity
            suggestions = sorted(suggestions, key=lambda x: (-x.get('popularity', 0), x['text']))
            suggestions = suggestions[:limit]
            
            # Cache the results
            cache_set(cache_key, json.dumps(suggestions), ttl=300)  # 5 minutes
            
            logger.info(f"Generated {len(suggestions)} auto-complete suggestions for query: {query}")
            return suggestions
            
        except Exception as e:
            logger.error(f"Error getting auto-complete suggestions: {e}")
            return []
    
    def _get_popular_search_terms(self, query: str, limit: int) -> List[Dict[str, Any]]:
        """Get popular search terms from ElastiCache"""
        try:
            # Get popular terms that start with the query
            popular_key = get_cache_key('popular_terms', 'all')
            popular_terms_json = cache_get(popular_key)
            
            if not popular_terms_json:
                return []
            
            popular_terms = json.loads(popular_terms_json)
            matching_terms = []
            
            for term_data in popular_terms:
                term = term_data.get('term', '').lower()
                if term.startswith(query) and term != query:
                    matching_terms.append({
                        'text': term_data.get('term', ''),
                        'type': 'popular',
                        'popularity': term_data.get('count', 0),
                        'count': term_data.get('count', 0)
                    })
            
            return sorted(matching_terms, key=lambda x: -x['popularity'])[:limit]
            
        except Exception as e:
            logger.error(f"Error getting popular search terms: {e}")
            return []
    
    def _get_product_suggestions(self, query: str, limit: int) -> List[Dict[str, Any]]:
        """Get product name suggestions from DocumentDB"""
        try:
            # Search for products with names that match the query
            regex_pattern = f".*{re.escape(query)}.*"
            
            pipeline = [
                {
                    '$match': {
                        '$or': [
                            {'title': {'$regex': regex_pattern, '$options': 'i'}},
                            {'category': {'$regex': regex_pattern, '$options': 'i'}},
                            {'tags': {'$regex': regex_pattern, '$options': 'i'}}
                        ]
                    }
                },
                {
                    '$project': {
                        'title': 1,
                        'category': 1,
                        'rating': 1,
                        'reviewCount': 1
                    }
                },
                {
                    '$sort': {'rating': -1, 'reviewCount': -1}
                },
                {
                    '$limit': limit * 2  # Get more to filter duplicates
                }
            ]
            
            products = list(self.products_collection.aggregate(pipeline))
            suggestions = []
            seen_titles = set()
            
            for product in products:
                title = product.get('title', '')
                if title.lower() not in seen_titles and len(suggestions) < limit:
                    seen_titles.add(title.lower())
                    suggestions.append({
                        'text': title,
                        'type': 'product',
                        'popularity': product.get('reviewCount', 0),
                        'rating': product.get('rating', 0)
                    })
            
            return suggestions
            
        except Exception as e:
            logger.error(f"Error getting product suggestions: {e}")
            return []
    
    def _get_category_suggestions(self, query: str, limit: int) -> List[Dict[str, Any]]:
        """Get category suggestions from DocumentDB"""
        try:
            pipeline = [
                {
                    '$match': {
                        'category': {'$regex': f".*{re.escape(query)}.*", '$options': 'i'}
                    }
                },
                {
                    '$group': {
                        '_id': '$category',
                        'count': {'$sum': 1},
                        'avgRating': {'$avg': '$rating'}
                    }
                },
                {
                    '$sort': {'count': -1, 'avgRating': -1}
                },
                {
                    '$limit': limit
                }
            ]
            
            categories = list(self.products_collection.aggregate(pipeline))
            suggestions = []
            
            for category in categories:
                suggestions.append({
                    'text': category['_id'],
                    'type': 'category',
                    'popularity': category['count'],
                    'count': category['count']
                })
            
            return suggestions
            
        except Exception as e:
            logger.error(f"Error getting category suggestions: {e}")
            return []
    
    def search_products(self, query: str, filters: Dict[str, Any] = None, 
                       sort_by: str = 'relevance', page: int = 1, 
                       page_size: int = 20) -> Dict[str, Any]:
        """Search products with semantic search and filtering"""
        try:
            if not query:
                return {'products': [], 'total': 0, 'page': page, 'totalPages': 0}
            
            # Track search analytics
            self._track_search_analytics(query, filters)
            
            # Build search pipeline
            pipeline = self._build_search_pipeline(query, filters, sort_by, page, page_size)
            
            # Execute search
            products = list(self.products_collection.aggregate(pipeline))
            
            # Get total count for pagination
            count_pipeline = self._build_count_pipeline(query, filters)
            total_results = list(self.products_collection.aggregate(count_pipeline))
            total = total_results[0]['total'] if total_results else 0
            
            # Calculate pagination info
            total_pages = math.ceil(total / page_size)
            
            # Highlight search terms in results
            highlighted_products = self._highlight_search_terms(products, query)
            
            # Get alternative suggestions if no results
            alternatives = []
            if total == 0:
                alternatives = self._get_alternative_suggestions(query)
            
            result = {
                'products': highlighted_products,
                'total': total,
                'page': page,
                'pageSize': page_size,
                'totalPages': total_pages,
                'query': query,
                'alternatives': alternatives
            }
            
            # Cache search results
            cache_key = get_cache_key('search', f"{query}_{hash(str(filters))}_{sort_by}_{page}_{page_size}")
            cache_set(cache_key, json.dumps(result, default=str), ttl=600)  # 10 minutes
            
            logger.info(f"Search completed for query '{query}': {total} results found")
            return result
            
        except Exception as e:
            logger.error(f"Error searching products: {e}")
            return {'products': [], 'total': 0, 'page': page, 'totalPages': 0, 'error': str(e)}
    
    def _build_search_pipeline(self, query: str, filters: Dict[str, Any], 
                              sort_by: str, page: int, page_size: int) -> List[Dict[str, Any]]:
        """Build MongoDB aggregation pipeline for search"""
        pipeline = []
        
        # Text search stage
        search_conditions = []
        
        # Add text search conditions
        regex_pattern = f".*{re.escape(query)}.*"
        search_conditions.extend([
            {'title': {'$regex': regex_pattern, '$options': 'i'}},
            {'description': {'$regex': regex_pattern, '$options': 'i'}},
            {'category': {'$regex': regex_pattern, '$options': 'i'}},
            {'tags': {'$regex': regex_pattern, '$options': 'i'}}
        ])
        
        # Try vector search if available
        try:
            vector_conditions = self._get_vector_search_conditions(query)
            if vector_conditions:
                search_conditions.extend(vector_conditions)
        except Exception as e:
            logger.warning(f"Vector search not available: {e}")
        
        # Match stage
        match_stage = {'$or': search_conditions}
        
        # Apply filters
        if filters:
            filter_conditions = self._build_filter_conditions(filters)
            if filter_conditions:
                match_stage = {'$and': [match_stage, filter_conditions]}
        
        pipeline.append({'$match': match_stage})
        
        # Add relevance scoring
        pipeline.append({
            '$addFields': {
                'relevanceScore': {
                    '$add': [
                        # Title match gets highest score
                        {'$cond': [
                            {'$regexMatch': {'input': '$title', 'regex': regex_pattern, 'options': 'i'}},
                            10, 0
                        ]},
                        # Category match gets medium score
                        {'$cond': [
                            {'$regexMatch': {'input': '$category', 'regex': regex_pattern, 'options': 'i'}},
                            5, 0
                        ]},
                        # Description match gets lower score
                        {'$cond': [
                            {'$regexMatch': {'input': '$description', 'regex': regex_pattern, 'options': 'i'}},
                            2, 0
                        ]},
                        # Rating boost
                        {'$multiply': ['$rating', 0.5]},
                        # Review count boost (normalized)
                        {'$multiply': [{'$log10': {'$add': ['$reviewCount', 1]}}, 0.3]}
                    ]
                }
            }
        })
        
        # Sort stage
        sort_stage = self._build_sort_stage(sort_by)
        pipeline.append({'$sort': sort_stage})
        
        # Pagination
        skip = (page - 1) * page_size
        pipeline.extend([
            {'$skip': skip},
            {'$limit': page_size}
        ])
        
        return pipeline
    
    def _build_filter_conditions(self, filters: Dict[str, Any]) -> Dict[str, Any]:
        """Build filter conditions for search"""
        conditions = {}
        
        if 'category' in filters and filters['category']:
            conditions['category'] = {'$in': filters['category']}
        
        if 'minPrice' in filters or 'maxPrice' in filters:
            price_condition = {}
            if 'minPrice' in filters:
                price_condition['$gte'] = float(filters['minPrice'])
            if 'maxPrice' in filters:
                price_condition['$lte'] = float(filters['maxPrice'])
            conditions['price'] = price_condition
        
        if 'minRating' in filters:
            conditions['rating'] = {'$gte': float(filters['minRating'])}
        
        if 'inStock' in filters and filters['inStock']:
            conditions['inStock'] = True
        
        if 'tags' in filters and filters['tags']:
            conditions['tags'] = {'$in': filters['tags']}
        
        return conditions
    
    def _build_sort_stage(self, sort_by: str) -> Dict[str, int]:
        """Build sort stage for search pipeline"""
        sort_options = {
            'relevance': {'relevanceScore': -1, 'rating': -1, 'reviewCount': -1},
            'price_low': {'price': 1, 'relevanceScore': -1},
            'price_high': {'price': -1, 'relevanceScore': -1},
            'rating': {'rating': -1, 'reviewCount': -1, 'relevanceScore': -1},
            'newest': {'createdAt': -1, 'relevanceScore': -1},
            'popular': {'reviewCount': -1, 'rating': -1, 'relevanceScore': -1}
        }
        
        return sort_options.get(sort_by, sort_options['relevance'])
    
    def _build_count_pipeline(self, query: str, filters: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Build pipeline to count total results"""
        pipeline = []
        
        # Same match conditions as search
        search_conditions = []
        regex_pattern = f".*{re.escape(query)}.*"
        search_conditions.extend([
            {'title': {'$regex': regex_pattern, '$options': 'i'}},
            {'description': {'$regex': regex_pattern, '$options': 'i'}},
            {'category': {'$regex': regex_pattern, '$options': 'i'}},
            {'tags': {'$regex': regex_pattern, '$options': 'i'}}
        ])
        
        match_stage = {'$or': search_conditions}
        
        if filters:
            filter_conditions = self._build_filter_conditions(filters)
            if filter_conditions:
                match_stage = {'$and': [match_stage, filter_conditions]}
        
        pipeline.extend([
            {'$match': match_stage},
            {'$count': 'total'}
        ])
        
        return pipeline
    
    def _get_vector_search_conditions(self, query: str) -> List[Dict[str, Any]]:
        """Get vector search conditions using embeddings"""
        try:
            # Generate embedding for the query
            embedding = self._generate_embedding(query)
            if not embedding:
                return []
            
            # Use vector search (this would require vector indexes in DocumentDB)
            # For now, return empty as vector search setup is complex
            return []
            
        except Exception as e:
            logger.warning(f"Vector search failed: {e}")
            return []
    
    def _generate_embedding(self, text: str) -> Optional[List[float]]:
        """Generate text embedding using Bedrock"""
        try:
            response = bedrock_client.invoke_model(
                modelId=config.BEDROCK_EMBEDDING_MODEL_ID,
                body=json.dumps({
                    'inputText': text
                })
            )
            
            result = json.loads(response['body'].read())
            return result.get('embedding')
            
        except Exception as e:
            logger.error(f"Error generating embedding: {e}")
            return None
    
    def _highlight_search_terms(self, products: List[Dict[str, Any]], query: str) -> List[Dict[str, Any]]:
        """Highlight search terms in product results"""
        try:
            query_terms = query.lower().split()
            highlighted_products = []
            
            for product in products:
                highlighted_product = product.copy()
                
                # Highlight in title
                title = product.get('title', '')
                for term in query_terms:
                    if term in title.lower():
                        title = re.sub(
                            f'({re.escape(term)})',
                            r'<mark>\1</mark>',
                            title,
                            flags=re.IGNORECASE
                        )
                highlighted_product['highlightedTitle'] = title
                
                # Highlight in description
                description = product.get('description', '')
                for term in query_terms:
                    if term in description.lower():
                        description = re.sub(
                            f'({re.escape(term)})',
                            r'<mark>\1</mark>',
                            description,
                            flags=re.IGNORECASE
                        )
                highlighted_product['highlightedDescription'] = description
                
                highlighted_products.append(highlighted_product)
            
            return highlighted_products
            
        except Exception as e:
            logger.error(f"Error highlighting search terms: {e}")
            return products
    
    def _get_alternative_suggestions(self, query: str) -> List[str]:
        """Get alternative search suggestions when no results found"""
        try:
            suggestions = []
            
            # Get similar categories
            categories = list(self.products_collection.distinct('category'))
            for category in categories:
                if any(word in category.lower() for word in query.lower().split()):
                    suggestions.append(category)
            
            # Get popular search terms
            popular_key = get_cache_key('popular_terms', 'all')
            popular_terms_json = cache_get(popular_key)
            
            if popular_terms_json:
                popular_terms = json.loads(popular_terms_json)
                for term_data in popular_terms[:5]:
                    term = term_data.get('term', '')
                    if term not in suggestions:
                        suggestions.append(term)
            
            return suggestions[:5]
            
        except Exception as e:
            logger.error(f"Error getting alternative suggestions: {e}")
            return []
    
    def _track_search_analytics(self, query: str, filters: Dict[str, Any] = None):
        """Track search analytics in DynamoDB"""
        try:
            timestamp = datetime.utcnow()
            
            # Store search event
            self.search_analytics_table.put_item(
                Item={
                    'searchTerm': query.lower(),
                    'timestamp': timestamp.isoformat(),
                    'filters': json.dumps(filters or {}),
                    'date': timestamp.strftime('%Y-%m-%d'),
                    'hour': timestamp.strftime('%Y-%m-%d-%H')
                }
            )
            
            # Update search term frequency in cache
            self._update_search_frequency(query.lower())
            
        except Exception as e:
            logger.error(f"Error tracking search analytics: {e}")
    
    def _update_search_frequency(self, query: str):
        """Update search term frequency in ElastiCache"""
        try:
            # Increment search count
            freq_key = get_cache_key('search_freq', query)
            current_count = cache_get(freq_key) or '0'
            new_count = int(current_count) + 1
            cache_set(freq_key, str(new_count), ttl=86400)  # 24 hours
            
            # Update popular terms list
            self._update_popular_terms(query, new_count)
            
        except Exception as e:
            logger.error(f"Error updating search frequency: {e}")
    
    def _update_popular_terms(self, query: str, count: int):
        """Update popular terms list in cache"""
        try:
            popular_key = get_cache_key('popular_terms', 'all')
            popular_terms_json = cache_get(popular_key)
            
            if popular_terms_json:
                popular_terms = json.loads(popular_terms_json)
            else:
                popular_terms = []
            
            # Update or add term
            term_found = False
            for term_data in popular_terms:
                if term_data['term'] == query:
                    term_data['count'] = count
                    term_found = True
                    break
            
            if not term_found:
                popular_terms.append({'term': query, 'count': count})
            
            # Sort by count and keep top 100
            popular_terms = sorted(popular_terms, key=lambda x: -x['count'])[:100]
            
            # Cache updated list
            cache_set(popular_key, json.dumps(popular_terms), ttl=3600)  # 1 hour
            
        except Exception as e:
            logger.error(f"Error updating popular terms: {e}")

def lambda_handler(event, context):
    """Lambda handler for search API"""
    try:
        # Parse request
        http_method = event.get('httpMethod', 'GET')
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
        
        # Initialize search API
        search_api = SearchAPI()
        
        # Route requests
        if path.endswith('/suggestions') and http_method == 'GET':
            # Auto-complete suggestions
            query = query_params.get('q', '')
            limit = int(query_params.get('limit', '10'))
            
            suggestions = search_api.get_auto_complete_suggestions(query, limit)
            
            return {
                'statusCode': 200,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*',
                    'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token',
                    'Access-Control-Allow-Methods': 'GET,POST,OPTIONS'
                },
                'body': json.dumps({
                    'suggestions': suggestions,
                    'query': query
                })
            }
        
        elif path.endswith('/products') and http_method in ['GET', 'POST']:
            # Product search
            if http_method == 'GET':
                query = query_params.get('q', '')
                filters = {}
                
                # Parse filters from query params
                if 'category' in query_params:
                    filters['category'] = query_params['category'].split(',')
                if 'minPrice' in query_params:
                    filters['minPrice'] = query_params['minPrice']
                if 'maxPrice' in query_params:
                    filters['maxPrice'] = query_params['maxPrice']
                if 'minRating' in query_params:
                    filters['minRating'] = query_params['minRating']
                if 'inStock' in query_params:
                    filters['inStock'] = query_params['inStock'].lower() == 'true'
                if 'tags' in query_params:
                    filters['tags'] = query_params['tags'].split(',')
                
                sort_by = query_params.get('sort', 'relevance')
                page = int(query_params.get('page', '1'))
                page_size = min(int(query_params.get('pageSize', '20')), config.MAX_PAGE_SIZE)
                
            else:  # POST
                query = body.get('query', '')
                filters = body.get('filters', {})
                sort_by = body.get('sortBy', 'relevance')
                page = body.get('page', 1)
                page_size = min(body.get('pageSize', 20), config.MAX_PAGE_SIZE)
            
            results = search_api.search_products(query, filters, sort_by, page, page_size)
            
            return {
                'statusCode': 200,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*',
                    'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token',
                    'Access-Control-Allow-Methods': 'GET,POST,OPTIONS'
                },
                'body': json.dumps(results, default=str)
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
    # Test auto-complete
    search_api = SearchAPI()
    
    test_event = {
        'httpMethod': 'GET',
        'path': '/api/search/suggestions',
        'queryStringParameters': {'q': 'wireless', 'limit': '5'}
    }
    
    result = lambda_handler(test_event, None)
    print("Auto-complete test result:")
    print(json.dumps(json.loads(result['body']), indent=2))
    
    # Test product search
    test_event = {
        'httpMethod': 'GET',
        'path': '/api/search/products',
        'queryStringParameters': {
            'q': 'wireless headphones',
            'sort': 'relevance',
            'page': '1',
            'pageSize': '10'
        }
    }
    
    result = lambda_handler(test_event, None)
    print("\nProduct search test result:")
    print(json.dumps(json.loads(result['body']), indent=2))