"""
Product API Lambda function for Unicorn E-Commerce
Handles product listing, search, filtering, and detail retrieval
Enhanced with comprehensive monitoring, logging, and error handling
"""
import json
import logging
import traceback
import time
from typing import Dict, List, Optional, Any
from datetime import datetime
from bson import ObjectId
from pymongo.errors import PyMongoError
import boto3

# Import shared utilities
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'shared'))

from database import (
    get_documentdb_collection, 
    cache_get, 
    cache_set, 
    get_cache_key,
    db
)
from config import config
from monitoring import (
    lambda_monitor, 
    performance_monitor, 
    security_monitor,
    database_monitor,
    log_database_operation,
    log_api_call
)
from error_handling import (
    create_error_response,
    validate_required_fields,
    validate_pagination_params,
    handle_database_error,
    PRODUCT_NOT_FOUND_ERROR,
    ValidationError,
    BusinessLogicError,
    DatabaseError,
    ErrorDetails,
    ErrorCode
)

# Configure logging
logger = logging.getLogger()
logger.setLevel(getattr(logging, config.LOG_LEVEL))

class ProductAPIError(Exception):
    """Custom exception for Product API errors"""
    pass

class ProductAPI:
    """Product API handler class"""
    
    def __init__(self):
        self.products_collection = get_documentdb_collection('products')
        self.reviews_collection = get_documentdb_collection('reviews')
    
    @database_monitor.monitor_query('products', 'list')
    def list_products(self, event: Dict) -> Dict:
        """
        List products with pagination, filtering, and sorting
        Enhanced with comprehensive validation and monitoring
        
        Query parameters:
        - page: Page number (default: 1)
        - limit: Items per page (default: 20, max: 100)
        - category: Filter by category
        - min_price: Minimum price filter
        - max_price: Maximum price filter
        - min_rating: Minimum rating filter
        - sort_by: Sort field (price, rating, created_at, title)
        - sort_order: Sort order (asc, desc)
        - search: Search term for title/description
        """
        start_time = time.time()
        
        try:
            # Parse and validate query parameters
            query_params = event.get('queryStringParameters') or {}
            
            # Validate pagination parameters
            page = int(query_params.get('page', 1))
            limit = int(query_params.get('limit', config.DEFAULT_PAGE_SIZE))
            limit, offset = validate_pagination_params(limit, (page - 1) * limit)
            
            category = query_params.get('category')
            min_price = query_params.get('min_price')
            max_price = query_params.get('max_price')
            min_rating = query_params.get('min_rating')
            sort_by = query_params.get('sort_by', 'created_at')
            sort_order = query_params.get('sort_order', 'desc')
            search_term = query_params.get('search')
            
            # Validate sort parameters
            valid_sort_fields = ['price', 'rating', 'created_at', 'title', 'average_rating']
            if sort_by not in valid_sort_fields:
                raise ValidationError(ErrorDetails(
                    code=ErrorCode.INVALID_INPUT,
                    message=f'Invalid sort field: {sort_by}',
                    user_message='Please use a valid sort field.',
                    details={'valid_fields': valid_sort_fields}
                ))
            
            if sort_order not in ['asc', 'desc']:
                raise ValidationError(ErrorDetails(
                    code=ErrorCode.INVALID_INPUT,
                    message=f'Invalid sort order: {sort_order}',
                    user_message='Sort order must be "asc" or "desc".'
                ))
            
            # Build cache key
            cache_key = get_cache_key('products_list', 
                f"{page}_{limit}_{category}_{min_price}_{max_price}_{min_rating}_{sort_by}_{sort_order}_{search_term}")
            
            # Try to get from cache first
            cached_result = cache_get(cache_key)
            if cached_result:
                logger.info(f"Returning cached product list for key: {cache_key}")
                return {
                    'statusCode': 200,
                    'headers': {
                        'Content-Type': 'application/json',
                        'Access-Control-Allow-Origin': '*'
                    },
                    'body': cached_result
                }
            
            # Build MongoDB query
            query = {}
            
            # Category filter
            if category:
                query['category'] = {'$regex': category, '$options': 'i'}
            
            # Price filters
            if min_price or max_price:
                price_query = {}
                if min_price:
                    price_query['$gte'] = float(min_price)
                if max_price:
                    price_query['$lte'] = float(max_price)
                query['price'] = price_query
            
            # Rating filter
            if min_rating:
                query['average_rating'] = {'$gte': float(min_rating)}
            
            # Search term
            if search_term:
                query['$or'] = [
                    {'title': {'$regex': search_term, '$options': 'i'}},
                    {'description': {'$regex': search_term, '$options': 'i'}},
                    {'tags': {'$in': [search_term.lower()]}}
                ]
            
            # Build sort criteria
            sort_direction = 1 if sort_order == 'asc' else -1
            sort_criteria = [(sort_by, sort_direction)]
            
            # Calculate skip value
            skip = (page - 1) * limit
            
            # Execute query with pagination
            cursor = self.products_collection.find(query).sort(sort_criteria).skip(skip).limit(limit)
            products = list(cursor)
            
            # Get total count for pagination
            total_count = self.products_collection.count_documents(query)
            total_pages = (total_count + limit - 1) // limit
            
            # Convert ObjectId to string for JSON serialization
            for product in products:
                product['_id'] = str(product['_id'])
                if 'created_at' in product:
                    product['created_at'] = product['created_at'].isoformat()
                if 'updated_at' in product:
                    product['updated_at'] = product['updated_at'].isoformat()
            
            # Prepare response
            response_data = {
                'products': products,
                'pagination': {
                    'current_page': page,
                    'total_pages': total_pages,
                    'total_items': total_count,
                    'items_per_page': limit,
                    'has_next': page < total_pages,
                    'has_previous': page > 1
                },
                'filters_applied': {
                    'category': category,
                    'min_price': min_price,
                    'max_price': max_price,
                    'min_rating': min_rating,
                    'search': search_term
                },
                'sort': {
                    'sort_by': sort_by,
                    'sort_order': sort_order
                }
            }
            
            response_body = json.dumps(response_data, default=str)
            
            # Cache the result
            cache_set(cache_key, response_body, ttl=config.CACHE_TTL_SECONDS)
            
            return {
                'statusCode': 200,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': response_body
            }
            
        except ValueError as e:
            logger.error(f"Invalid parameter in list_products: {e}")
            return {
                'statusCode': 400,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps({
                    'error': 'Invalid parameters',
                    'message': str(e)
                })
            }
        except PyMongoError as e:
            logger.error(f"Database error in list_products: {e}")
            return {
                'statusCode': 500,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps({
                    'error': 'Database error',
                    'message': 'Failed to retrieve products'
                })
            }
        except Exception as e:
            logger.error(f"Unexpected error in list_products: {e}")
            logger.error(traceback.format_exc())
            return {
                'statusCode': 500,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps({
                    'error': 'Internal server error',
                    'message': 'An unexpected error occurred'
                })
            }
    
    def get_product_detail(self, event: Dict) -> Dict:
        """
        Get detailed product information by ID
        Includes product details, reviews summary, and related products
        """
        try:
            # Extract product ID from path parameters
            path_params = event.get('pathParameters') or {}
            product_id = path_params.get('id')
            
            if not product_id:
                return {
                    'statusCode': 400,
                    'headers': {
                        'Content-Type': 'application/json',
                        'Access-Control-Allow-Origin': '*'
                    },
                    'body': json.dumps({
                        'error': 'Missing product ID',
                        'message': 'Product ID is required'
                    })
                }
            
            # Check cache first
            cache_key = get_cache_key('product_detail', product_id)
            cached_result = cache_get(cache_key)
            if cached_result:
                logger.info(f"Returning cached product detail for ID: {product_id}")
                return {
                    'statusCode': 200,
                    'headers': {
                        'Content-Type': 'application/json',
                        'Access-Control-Allow-Origin': '*'
                    },
                    'body': cached_result
                }
            
            # Get product from DocumentDB
            try:
                product = self.products_collection.find_one({'_id': ObjectId(product_id)})
            except Exception:
                # Try finding by string ID if ObjectId conversion fails
                product = self.products_collection.find_one({'_id': product_id})
            
            if not product:
                return {
                    'statusCode': 404,
                    'headers': {
                        'Content-Type': 'application/json',
                        'Access-Control-Allow-Origin': '*'
                    },
                    'body': json.dumps({
                        'error': 'Product not found',
                        'message': f'Product with ID {product_id} does not exist'
                    })
                }
            
            # Convert ObjectId to string
            product['_id'] = str(product['_id'])
            if 'created_at' in product:
                product['created_at'] = product['created_at'].isoformat()
            if 'updated_at' in product:
                product['updated_at'] = product['updated_at'].isoformat()
            
            # Get reviews summary
            reviews_summary = self._get_reviews_summary(product_id)
            
            # Get related products (same category, excluding current product)
            related_products = self._get_related_products(product.get('category'), product_id)
            
            # Prepare response
            response_data = {
                'product': product,
                'reviews_summary': reviews_summary,
                'related_products': related_products
            }
            
            response_body = json.dumps(response_data, default=str)
            
            # Cache the result
            cache_set(cache_key, response_body, ttl=config.CACHE_TTL_SECONDS)
            
            return {
                'statusCode': 200,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': response_body
            }
            
        except Exception as e:
            logger.error(f"Error in get_product_detail: {e}")
            logger.error(traceback.format_exc())
            return {
                'statusCode': 500,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps({
                    'error': 'Internal server error',
                    'message': 'Failed to retrieve product details'
                })
            }
    
    def search_products(self, event: Dict) -> Dict:
        """
        Advanced product search with text search and filters
        Supports semantic search and auto-complete suggestions
        """
        try:
            # Parse request body for POST requests or query params for GET
            if event.get('httpMethod') == 'POST':
                body = json.loads(event.get('body', '{}'))
                search_params = body
            else:
                search_params = event.get('queryStringParameters') or {}
            
            query_text = search_params.get('q', '').strip()
            category = search_params.get('category')
            min_price = search_params.get('min_price')
            max_price = search_params.get('max_price')
            min_rating = search_params.get('min_rating')
            page = int(search_params.get('page', 1))
            limit = min(int(search_params.get('limit', config.DEFAULT_PAGE_SIZE)), config.MAX_PAGE_SIZE)
            
            if not query_text:
                return {
                    'statusCode': 400,
                    'headers': {
                        'Content-Type': 'application/json',
                        'Access-Control-Allow-Origin': '*'
                    },
                    'body': json.dumps({
                        'error': 'Missing search query',
                        'message': 'Search query (q) is required'
                    })
                }
            
            # Build cache key
            cache_key = get_cache_key('product_search', 
                f"{query_text}_{category}_{min_price}_{max_price}_{min_rating}_{page}_{limit}")
            
            # Check cache first
            cached_result = cache_get(cache_key)
            if cached_result:
                logger.info(f"Returning cached search results for query: {query_text}")
                return {
                    'statusCode': 200,
                    'headers': {
                        'Content-Type': 'application/json',
                        'Access-Control-Allow-Origin': '*'
                    },
                    'body': cached_result
                }
            
            # Build search query
            search_query = {
                '$or': [
                    {'title': {'$regex': query_text, '$options': 'i'}},
                    {'description': {'$regex': query_text, '$options': 'i'}},
                    {'tags': {'$in': [query_text.lower()]}},
                    {'category': {'$regex': query_text, '$options': 'i'}}
                ]
            }
            
            # Add filters
            if category:
                search_query['category'] = {'$regex': category, '$options': 'i'}
            
            if min_price or max_price:
                price_query = {}
                if min_price:
                    price_query['$gte'] = float(min_price)
                if max_price:
                    price_query['$lte'] = float(max_price)
                search_query['price'] = price_query
            
            if min_rating:
                search_query['average_rating'] = {'$gte': float(min_rating)}
            
            # Execute search with pagination
            skip = (page - 1) * limit
            cursor = self.products_collection.find(search_query).sort([('average_rating', -1), ('title', 1)]).skip(skip).limit(limit)
            products = list(cursor)
            
            # Get total count
            total_count = self.products_collection.count_documents(search_query)
            total_pages = (total_count + limit - 1) // limit
            
            # Convert ObjectId to string
            for product in products:
                product['_id'] = str(product['_id'])
                if 'created_at' in product:
                    product['created_at'] = product['created_at'].isoformat()
                if 'updated_at' in product:
                    product['updated_at'] = product['updated_at'].isoformat()
            
            # Get search suggestions
            suggestions = self._get_search_suggestions(query_text)
            
            response_data = {
                'query': query_text,
                'products': products,
                'suggestions': suggestions,
                'pagination': {
                    'current_page': page,
                    'total_pages': total_pages,
                    'total_items': total_count,
                    'items_per_page': limit,
                    'has_next': page < total_pages,
                    'has_previous': page > 1
                },
                'filters_applied': {
                    'category': category,
                    'min_price': min_price,
                    'max_price': max_price,
                    'min_rating': min_rating
                }
            }
            
            response_body = json.dumps(response_data, default=str)
            
            # Cache the result
            cache_set(cache_key, response_body, ttl=config.CACHE_TTL_SECONDS)
            
            return {
                'statusCode': 200,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': response_body
            }
            
        except Exception as e:
            logger.error(f"Error in search_products: {e}")
            logger.error(traceback.format_exc())
            return {
                'statusCode': 500,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps({
                    'error': 'Search error',
                    'message': 'Failed to search products'
                })
            }
    
    def _get_reviews_summary(self, product_id: str) -> Dict:
        """Get reviews summary for a product"""
        try:
            # Aggregate reviews data
            pipeline = [
                {'$match': {'product_id': product_id}},
                {'$group': {
                    '_id': None,
                    'total_reviews': {'$sum': 1},
                    'average_rating': {'$avg': '$rating'},
                    'rating_distribution': {
                        '$push': '$rating'
                    }
                }}
            ]
            
            result = list(self.reviews_collection.aggregate(pipeline))
            
            if not result:
                return {
                    'total_reviews': 0,
                    'average_rating': 0,
                    'rating_distribution': {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
                }
            
            summary = result[0]
            
            # Calculate rating distribution
            rating_dist = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
            for rating in summary['rating_distribution']:
                rating_dist[rating] = rating_dist.get(rating, 0) + 1
            
            return {
                'total_reviews': summary['total_reviews'],
                'average_rating': round(summary['average_rating'], 2) if summary['average_rating'] else 0,
                'rating_distribution': rating_dist
            }
            
        except Exception as e:
            logger.error(f"Error getting reviews summary: {e}")
            return {
                'total_reviews': 0,
                'average_rating': 0,
                'rating_distribution': {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
            }
    
    def _get_related_products(self, category: str, exclude_id: str, limit: int = 4) -> List[Dict]:
        """Get related products in the same category"""
        try:
            if not category:
                return []
            
            query = {
                'category': {'$regex': category, '$options': 'i'},
                '_id': {'$ne': ObjectId(exclude_id) if ObjectId.is_valid(exclude_id) else exclude_id}
            }
            
            cursor = self.products_collection.find(query).sort([('average_rating', -1)]).limit(limit)
            products = list(cursor)
            
            # Convert ObjectId to string
            for product in products:
                product['_id'] = str(product['_id'])
                if 'created_at' in product:
                    product['created_at'] = product['created_at'].isoformat()
                if 'updated_at' in product:
                    product['updated_at'] = product['updated_at'].isoformat()
            
            return products
            
        except Exception as e:
            logger.error(f"Error getting related products: {e}")
            return []
    
    def _get_search_suggestions(self, query_text: str, limit: int = 5) -> List[str]:
        """Get search suggestions based on query text"""
        try:
            # Simple suggestion logic - find products with similar titles
            suggestions = []
            
            # Find products with titles containing the query
            cursor = self.products_collection.find(
                {'title': {'$regex': query_text, '$options': 'i'}},
                {'title': 1}
            ).limit(limit)
            
            for product in cursor:
                suggestions.append(product['title'])
            
            return suggestions
            
        except Exception as e:
            logger.error(f"Error getting search suggestions: {e}")
            return []

# Initialize API handler
product_api = ProductAPI()

@lambda_monitor(service_name='product-api', environment=config.ENVIRONMENT)
def lambda_handler(event, context):
    """
    Main Lambda handler function with comprehensive monitoring
    Routes requests based on HTTP method and path
    """
    start_time = time.time()
    http_method = event.get('httpMethod')
    path = event.get('path', '')
    request_id = context.aws_request_id if context else 'unknown'
    
    # Extract user information for monitoring
    user_id = None
    if 'requestContext' in event and 'authorizer' in event['requestContext']:
        user_id = event['requestContext']['authorizer'].get('userId')
    
    try:
        # Route requests
        if http_method == 'GET':
            if path.endswith('/search'):
                result = product_api.search_products(event)
            elif '/products/' in path and path.split('/')[-1]:
                result = product_api.get_product_detail(event)
            else:
                result = product_api.list_products(event)
        elif http_method == 'POST' and path.endswith('/search'):
            result = product_api.search_products(event)
        else:
            raise ValidationError(ErrorDetails(
                code=ErrorCode.INVALID_INPUT,
                message=f'HTTP method {http_method} not supported for this endpoint',
                user_message='This request method is not supported.'
            ))
        
        # Log successful API call
        execution_time = (time.time() - start_time) * 1000
        status_code = result.get('statusCode', 200)
        log_api_call('product-api', path, http_method, status_code, execution_time, user_id)
        
        # Put business metrics
        if status_code == 200:
            if path.endswith('/search'):
                performance_monitor.put_business_metric('ProductSearches', 1, user_id)
            elif '/products/' in path:
                performance_monitor.put_business_metric('ProductViews', 1, user_id)
            else:
                performance_monitor.put_business_metric('ProductListings', 1, user_id)
        
        return result
        
    except (ValidationError, BusinessLogicError, DatabaseError) as e:
        # Handle known application errors
        execution_time = (time.time() - start_time) * 1000
        log_api_call('product-api', path, http_method, e.status_code, execution_time, user_id)
        return create_error_response(e, request_id)
        
    except Exception as e:
        # Handle unexpected errors
        execution_time = (time.time() - start_time) * 1000
        log_api_call('product-api', path, http_method, 500, execution_time, user_id)
        
        # Log security event for unexpected errors
        security_monitor.log_suspicious_activity(
            'unexpected_error',
            {'error_type': type(e).__name__, 'path': path, 'method': http_method},
            user_id=user_id
        )
        
        return create_error_response(e, request_id)