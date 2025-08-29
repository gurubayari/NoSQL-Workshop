"""
Advanced caching decorators for AWS NoSQL Workshop
Provides specialized decorators for different caching patterns and strategies
"""
import json
import hashlib
import logging
from typing import Any, Dict, List, Optional, Callable, Union
from functools import wraps
from datetime import datetime, timedelta

try:
    from .cache_manager import cache_manager, CacheInvalidation
    from .config import config
except ImportError:
    from cache_manager import cache_manager, CacheInvalidation
    from config import config

logger = logging.getLogger(__name__)

def cache_api_response(cache_type: str, ttl: Optional[int] = None, 
                      key_params: Optional[List[str]] = None,
                      invalidate_on_error: bool = False):
    """
    Decorator for caching API responses with automatic key generation
    
    Args:
        cache_type: Type of cache (product_search, product_listing, etc.)
        ttl: Time to live in seconds
        key_params: Specific parameters to include in cache key
        invalidate_on_error: Whether to invalidate cache on function error
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Generate cache key based on function parameters
            if key_params:
                key_data = {param: kwargs.get(param) for param in key_params if param in kwargs}
            else:
                key_data = kwargs.copy()
                # Remove sensitive data from cache key
                key_data.pop('auth_token', None)
                key_data.pop('password', None)
            
            cache_key = cache_manager._generate_cache_key(cache_type, *args, **key_data)
            
            # Try to get from cache
            cached_result = cache_manager.get(cache_key)
            if cached_result is not None:
                logger.debug(f"API cache hit for {func.__name__}: {cache_key}")
                return cached_result
            
            try:
                # Execute function
                result = func(*args, **kwargs)
                
                # Cache successful results
                if result is not None:
                    cache_ttl = ttl or cache_manager.cache_ttls.get(cache_type, cache_manager.default_ttl)
                    cache_manager.set(cache_key, result, cache_ttl)
                    logger.debug(f"Cached API response for {func.__name__}: {cache_key}")
                
                return result
                
            except Exception as e:
                if invalidate_on_error:
                    cache_manager.delete(cache_key)
                    logger.debug(f"Invalidated cache on error for {func.__name__}: {cache_key}")
                raise e
                
        return wrapper
    return decorator

def cache_bedrock_response(model_id: Optional[str] = None, ttl: Optional[int] = None,
                          include_parameters: bool = True):
    """
    Decorator for caching Bedrock AI responses with prompt-based keys
    
    Args:
        model_id: Bedrock model ID (if not provided, extracted from kwargs)
        ttl: Time to live in seconds
        include_parameters: Whether to include model parameters in cache key
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Extract prompt and model information
            prompt = kwargs.get('prompt') or (args[0] if args else '')
            used_model_id = model_id or kwargs.get('model_id', config.BEDROCK_MODEL_ID)
            parameters = kwargs.get('parameters', {}) if include_parameters else {}
            
            # Generate prompt hash for cache key
            prompt_data = {
                'prompt': str(prompt),
                'model_id': used_model_id,
                'parameters': parameters
            }
            prompt_string = json.dumps(prompt_data, sort_keys=True)
            prompt_hash = hashlib.sha256(prompt_string.encode()).hexdigest()[:16]
            
            cache_key = cache_manager._generate_cache_key('bedrock_prompt', prompt_hash)
            
            # Check cache
            cached_response = cache_manager.get(cache_key)
            if cached_response is not None:
                logger.debug(f"Bedrock cache hit for {func.__name__}: {prompt_hash}")
                return cached_response.get('response', cached_response)
            
            # Execute function
            result = func(*args, **kwargs)
            
            # Cache response with metadata
            if result is not None:
                cache_ttl = ttl or cache_manager.cache_ttls['bedrock_prompt']
                cached_data = {
                    'response': result,
                    'cached_at': datetime.utcnow().isoformat(),
                    'model_id': used_model_id,
                    'parameters': parameters,
                    'prompt_hash': prompt_hash
                }
                cache_manager.set(cache_key, cached_data, cache_ttl)
                logger.debug(f"Cached Bedrock response for {func.__name__}: {prompt_hash}")
            
            return result
            
        return wrapper
    return decorator

def cache_user_session(ttl: Optional[int] = None, auto_refresh: bool = True):
    """
    Decorator for caching user session data
    
    Args:
        ttl: Time to live in seconds
        auto_refresh: Whether to refresh TTL on cache hit
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Extract user ID from parameters
            user_id = kwargs.get('user_id') or kwargs.get('userId')
            if not user_id and args:
                user_id = args[0]
            
            if not user_id:
                # If no user ID, execute function without caching
                return func(*args, **kwargs)
            
            cache_key = cache_manager._generate_cache_key('user_session', user_id)
            
            # Check cache
            cached_session = cache_manager.get(cache_key)
            if cached_session is not None:
                if auto_refresh:
                    # Refresh TTL on access
                    session_ttl = ttl or cache_manager.cache_ttls['user_session']
                    cache_manager.expire(cache_key, session_ttl)
                
                logger.debug(f"Session cache hit for user: {user_id}")
                return cached_session
            
            # Execute function
            result = func(*args, **kwargs)
            
            # Cache session data
            if result is not None:
                session_ttl = ttl or cache_manager.cache_ttls['user_session']
                cache_manager.set(cache_key, result, session_ttl)
                logger.debug(f"Cached session for user: {user_id}")
            
            return result
            
        return wrapper
    return decorator

def cache_search_suggestions(ttl: Optional[int] = None, max_suggestions: int = 10):
    """
    Decorator for caching search auto-complete suggestions
    
    Args:
        ttl: Time to live in seconds
        max_suggestions: Maximum number of suggestions to cache
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Extract query prefix
            query_prefix = kwargs.get('query') or kwargs.get('prefix') or (args[0] if args else '')
            limit = kwargs.get('limit', max_suggestions)
            
            cache_key = cache_manager._generate_cache_key('search_suggestions', 
                                                        query_prefix.lower(), limit)
            
            # Check cache
            cached_suggestions = cache_manager.get(cache_key)
            if cached_suggestions is not None:
                logger.debug(f"Search suggestions cache hit for: {query_prefix}")
                return cached_suggestions
            
            # Execute function
            result = func(*args, **kwargs)
            
            # Cache suggestions
            if result is not None:
                suggestions_ttl = ttl or cache_manager.cache_ttls['search_suggestions']
                cache_manager.set(cache_key, result, suggestions_ttl)
                logger.debug(f"Cached search suggestions for: {query_prefix}")
            
            return result
            
        return wrapper
    return decorator

def cache_analytics_data(metric_type: str, ttl: Optional[int] = None,
                        include_timestamp: bool = True):
    """
    Decorator for caching analytics and insights data
    
    Args:
        metric_type: Type of analytics metric
        ttl: Time to live in seconds
        include_timestamp: Whether to include generation timestamp
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Generate cache key from parameters
            cache_key = cache_manager._generate_cache_key('analytics_cache', 
                                                        metric_type, *args, **kwargs)
            
            # Check cache
            cached_analytics = cache_manager.get(cache_key)
            if cached_analytics is not None:
                logger.debug(f"Analytics cache hit for {metric_type}: {cache_key}")
                return cached_analytics.get('data', cached_analytics) if include_timestamp else cached_analytics
            
            # Execute function
            result = func(*args, **kwargs)
            
            # Cache analytics data
            if result is not None:
                analytics_ttl = ttl or cache_manager.cache_ttls['analytics_cache']
                
                if include_timestamp:
                    cached_data = {
                        'data': result,
                        'generated_at': datetime.utcnow().isoformat(),
                        'metric_type': metric_type
                    }
                else:
                    cached_data = result
                
                cache_manager.set(cache_key, cached_data, analytics_ttl)
                logger.debug(f"Cached analytics data for {metric_type}: {cache_key}")
            
            return result
            
        return wrapper
    return decorator

def invalidate_cache_on_update(cache_patterns: List[str], 
                              invalidate_related: bool = True):
    """
    Decorator to invalidate specific cache patterns after function execution
    
    Args:
        cache_patterns: List of cache key patterns to invalidate
        invalidate_related: Whether to invalidate related caches automatically
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Execute function first
            result = func(*args, **kwargs)
            
            # Invalidate specified cache patterns
            for pattern in cache_patterns:
                try:
                    # Replace placeholders with actual values from kwargs
                    formatted_pattern = pattern.format(**kwargs)
                    deleted_count = cache_manager.delete_pattern(formatted_pattern)
                    logger.debug(f"Invalidated {deleted_count} cache entries for pattern: {formatted_pattern}")
                except Exception as e:
                    logger.warning(f"Failed to invalidate cache pattern {pattern}: {e}")
            
            # Invalidate related caches if requested
            if invalidate_related:
                try:
                    # Extract common identifiers for related cache invalidation
                    product_id = kwargs.get('product_id') or kwargs.get('productId')
                    user_id = kwargs.get('user_id') or kwargs.get('userId')
                    
                    if product_id:
                        CacheInvalidation.invalidate_product_related(product_id)
                    if user_id:
                        CacheInvalidation.invalidate_user_related(user_id)
                        
                except Exception as e:
                    logger.warning(f"Failed to invalidate related caches: {e}")
            
            return result
            
        return wrapper
    return decorator

def cache_with_fallback(primary_cache_type: str, fallback_cache_type: str,
                       primary_ttl: Optional[int] = None, 
                       fallback_ttl: Optional[int] = None):
    """
    Decorator for implementing cache fallback strategies
    
    Args:
        primary_cache_type: Primary cache type to try first
        fallback_cache_type: Fallback cache type if primary fails
        primary_ttl: TTL for primary cache
        fallback_ttl: TTL for fallback cache
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Generate cache keys
            primary_key = cache_manager._generate_cache_key(primary_cache_type, *args, **kwargs)
            fallback_key = cache_manager._generate_cache_key(fallback_cache_type, *args, **kwargs)
            
            # Try primary cache first
            cached_result = cache_manager.get(primary_key)
            if cached_result is not None:
                logger.debug(f"Primary cache hit: {primary_key}")
                return cached_result
            
            # Try fallback cache
            fallback_result = cache_manager.get(fallback_key)
            if fallback_result is not None:
                logger.debug(f"Fallback cache hit: {fallback_key}")
                # Optionally restore to primary cache
                p_ttl = primary_ttl or cache_manager.cache_ttls.get(primary_cache_type, cache_manager.default_ttl)
                cache_manager.set(primary_key, fallback_result, p_ttl)
                return fallback_result
            
            # Execute function
            result = func(*args, **kwargs)
            
            # Cache in both locations
            if result is not None:
                p_ttl = primary_ttl or cache_manager.cache_ttls.get(primary_cache_type, cache_manager.default_ttl)
                f_ttl = fallback_ttl or cache_manager.cache_ttls.get(fallback_cache_type, cache_manager.default_ttl)
                
                cache_manager.set(primary_key, result, p_ttl)
                cache_manager.set(fallback_key, result, f_ttl)
                logger.debug(f"Cached result in both primary and fallback: {primary_key}, {fallback_key}")
            
            return result
            
        return wrapper
    return decorator

def cache_with_warming(cache_type: str, warming_func: Optional[Callable] = None,
                      warm_on_miss: bool = True, ttl: Optional[int] = None):
    """
    Decorator for cache warming strategies
    
    Args:
        cache_type: Type of cache
        warming_func: Function to call for cache warming
        warm_on_miss: Whether to warm cache on cache miss
        ttl: Time to live in seconds
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            cache_key = cache_manager._generate_cache_key(cache_type, *args, **kwargs)
            
            # Check cache
            cached_result = cache_manager.get(cache_key)
            if cached_result is not None:
                logger.debug(f"Cache hit with warming: {cache_key}")
                return cached_result
            
            # Cache miss - execute function
            result = func(*args, **kwargs)
            
            # Cache result
            if result is not None:
                cache_ttl = ttl or cache_manager.cache_ttls.get(cache_type, cache_manager.default_ttl)
                cache_manager.set(cache_key, result, cache_ttl)
                logger.debug(f"Cached result with warming: {cache_key}")
            
            # Warm related caches if configured
            if warm_on_miss and warming_func:
                try:
                    warming_func(*args, **kwargs)
                    logger.debug(f"Executed cache warming for: {cache_key}")
                except Exception as e:
                    logger.warning(f"Cache warming failed: {e}")
            
            return result
            
        return wrapper
    return decorator

# Utility functions for cache management
def warm_product_caches(product_ids: List[str]):
    """Warm up product-related caches"""
    from .cache_manager import ProductSearchCache
    
    for product_id in product_ids:
        try:
            # This would typically call the actual product API functions
            # to populate the cache with fresh data
            logger.debug(f"Warming cache for product: {product_id}")
        except Exception as e:
            logger.warning(f"Failed to warm cache for product {product_id}: {e}")

def warm_search_caches(popular_terms: List[str]):
    """Warm up search-related caches"""
    from .cache_manager import SearchSuggestionsCache
    
    for term in popular_terms:
        try:
            # This would typically call search functions to populate cache
            logger.debug(f"Warming search cache for term: {term}")
        except Exception as e:
            logger.warning(f"Failed to warm search cache for term {term}: {e}")

def get_cache_stats() -> Dict[str, Any]:
    """Get cache statistics and health information"""
    try:
        info = cache_manager.redis_client.info()
        return {
            'connected_clients': info.get('connected_clients', 0),
            'used_memory': info.get('used_memory', 0),
            'used_memory_human': info.get('used_memory_human', '0B'),
            'keyspace_hits': info.get('keyspace_hits', 0),
            'keyspace_misses': info.get('keyspace_misses', 0),
            'hit_rate': info.get('keyspace_hits', 0) / max(info.get('keyspace_hits', 0) + info.get('keyspace_misses', 0), 1),
            'uptime_in_seconds': info.get('uptime_in_seconds', 0)
        }
    except Exception as e:
        logger.error(f"Failed to get cache stats: {e}")
        return {}