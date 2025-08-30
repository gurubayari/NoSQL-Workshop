"""
ElastiCache caching patterns and strategies for AWS NoSQL Workshop
Implements comprehensive caching for API responses, sessions, AI prompts, and analytics
"""
import json
import hashlib
import logging
from typing import Any, Dict, List, Optional, Union
from datetime import datetime, timedelta
from functools import wraps
import redis
try:
    from .database import db, get_cache_key
    from .config import config
except ImportError:
    from database import db, get_cache_key
    from config import config

logger = logging.getLogger(__name__)

class CacheManager:
    """Comprehensive cache management for all application caching needs"""
    
    def __init__(self):
        self.redis_client = db.elasticache
        self.default_ttl = config.CACHE_TTL_SECONDS
        
        # Cache TTL configurations for different data types
        self.cache_ttls = {
            'product_search': 1800,      # 30 minutes
            'product_listing': 900,      # 15 minutes
            'product_details': 3600,     # 1 hour
            'user_session': 86400,       # 24 hours
            'auth_token': 3600,          # 1 hour
            'bedrock_prompt': 7200,      # 2 hours
            'review_insights': 3600,     # 1 hour
            'search_suggestions': 1800,  # 30 minutes
            'analytics_cache': 1800,     # 30 minutes
            'chat_memory': 1800,         # 30 minutes
            'popular_searches': 3600,    # 1 hour
        }
    
    def _serialize_data(self, data: Any) -> str:
        """Serialize data for cache storage"""
        try:
            return json.dumps(data, default=str, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Failed to serialize data: {e}")
            return ""
    
    def _deserialize_data(self, data: str) -> Any:
        """Deserialize data from cache"""
        try:
            return json.loads(data) if data else None
        except Exception as e:
            logger.error(f"Failed to deserialize data: {e}")
            return None
    
    def _generate_cache_key(self, prefix: str, *args, **kwargs) -> str:
        """Generate consistent cache key from parameters"""
        # Create a hash of all parameters for consistent key generation
        key_parts = [str(arg) for arg in args]
        key_parts.extend([f"{k}:{v}" for k, v in sorted(kwargs.items())])
        key_string = "|".join(key_parts)
        key_hash = hashlib.md5(key_string.encode()).hexdigest()[:12]
        return get_cache_key(prefix, key_hash)
    
    def get(self, key: str) -> Any:
        """Get value from cache with deserialization"""
        try:
            cached_data = self.redis_client.get(key)
            return self._deserialize_data(cached_data) if cached_data else None
        except Exception as e:
            logger.warning(f"Cache get failed for key {key}: {e}")
            return None
    
    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """Set value in cache with serialization"""
        try:
            ttl = ttl or self.default_ttl
            serialized_value = self._serialize_data(value)
            if serialized_value:
                return self.redis_client.setex(key, ttl, serialized_value)
            return False
        except Exception as e:
            logger.warning(f"Cache set failed for key {key}: {e}")
            return False
    
    def delete(self, key: str) -> bool:
        """Delete value from cache"""
        try:
            return bool(self.redis_client.delete(key))
        except Exception as e:
            logger.warning(f"Cache delete failed for key {key}: {e}")
            return False
    
    def delete_pattern(self, pattern: str) -> int:
        """Delete all keys matching pattern"""
        try:
            keys = self.redis_client.keys(pattern)
            if keys:
                return self.redis_client.delete(*keys)
            return 0
        except Exception as e:
            logger.warning(f"Cache pattern delete failed for pattern {pattern}: {e}")
            return 0
    
    def exists(self, key: str) -> bool:
        """Check if key exists in cache"""
        try:
            return bool(self.redis_client.exists(key))
        except Exception as e:
            logger.warning(f"Cache exists check failed for key {key}: {e}")
            return False
    
    def increment(self, key: str, amount: int = 1) -> int:
        """Increment counter in cache"""
        try:
            return self.redis_client.incr(key, amount)
        except Exception as e:
            logger.warning(f"Cache increment failed for key {key}: {e}")
            return 0
    
    def expire(self, key: str, ttl: int) -> bool:
        """Set expiration time for existing key"""
        try:
            return self.redis_client.expire(key, ttl)
        except Exception as e:
            logger.warning(f"Cache expire failed for key {key}: {e}")
            return False

# Global cache manager instance
cache_manager = CacheManager()

class ProductSearchCache:
    """Caching for product search and listing operations"""
    
    @staticmethod
    def get_search_results(query: str, filters: Dict = None, page: int = 1, 
                          page_size: int = 20) -> Optional[Dict]:
        """Get cached search results"""
        cache_key = cache_manager._generate_cache_key(
            'product_search', query, filters or {}, page, page_size
        )
        return cache_manager.get(cache_key)
    
    @staticmethod
    def cache_search_results(query: str, results: Dict, filters: Dict = None, 
                           page: int = 1, page_size: int = 20) -> bool:
        """Cache search results"""
        cache_key = cache_manager._generate_cache_key(
            'product_search', query, filters or {}, page, page_size
        )
        ttl = cache_manager.cache_ttls['product_search']
        return cache_manager.set(cache_key, results, ttl)
    
    @staticmethod
    def get_product_listing(category: str = None, page: int = 1, 
                           page_size: int = 20, sort_by: str = None) -> Optional[Dict]:
        """Get cached product listing"""
        cache_key = cache_manager._generate_cache_key(
            'product_listing', category or 'all', page, page_size, sort_by or 'default'
        )
        return cache_manager.get(cache_key)
    
    @staticmethod
    def cache_product_listing(results: Dict, category: str = None, page: int = 1,
                            page_size: int = 20, sort_by: str = None) -> bool:
        """Cache product listing results"""
        cache_key = cache_manager._generate_cache_key(
            'product_listing', category or 'all', page, page_size, sort_by or 'default'
        )
        ttl = cache_manager.cache_ttls['product_listing']
        return cache_manager.set(cache_key, results, ttl)
    
    @staticmethod
    def get_product_details(product_id: str) -> Optional[Dict]:
        """Get cached product details"""
        cache_key = get_cache_key('product_details', product_id)
        return cache_manager.get(cache_key)
    
    @staticmethod
    def cache_product_details(product_id: str, product_data: Dict) -> bool:
        """Cache product details"""
        cache_key = get_cache_key('product_details', product_id)
        ttl = cache_manager.cache_ttls['product_details']
        return cache_manager.set(cache_key, product_data, ttl)
    
    @staticmethod
    def invalidate_product_cache(product_id: str = None):
        """Invalidate product-related caches"""
        if product_id:
            # Invalidate specific product
            cache_manager.delete(get_cache_key('product_details', product_id))
        
        # Invalidate all product listings and searches
        cache_manager.delete_pattern(get_cache_key('product_listing', '*'))
        cache_manager.delete_pattern(get_cache_key('product_search', '*'))

class SessionCache:
    """Caching for user sessions and authentication tokens"""
    
    @staticmethod
    def get_user_session(user_id: str) -> Optional[Dict]:
        """Get cached user session"""
        cache_key = get_cache_key('user_session', user_id)
        return cache_manager.get(cache_key)
    
    @staticmethod
    def cache_user_session(user_id: str, session_data: Dict) -> bool:
        """Cache user session data"""
        cache_key = get_cache_key('user_session', user_id)
        ttl = cache_manager.cache_ttls['user_session']
        return cache_manager.set(cache_key, session_data, ttl)
    
    @staticmethod
    def get_auth_token(token_hash: str) -> Optional[Dict]:
        """Get cached authentication token data"""
        cache_key = get_cache_key('auth_token', token_hash)
        return cache_manager.get(cache_key)
    
    @staticmethod
    def cache_auth_token(token_hash: str, token_data: Dict) -> bool:
        """Cache authentication token data"""
        cache_key = get_cache_key('auth_token', token_hash)
        ttl = cache_manager.cache_ttls['auth_token']
        return cache_manager.set(cache_key, token_data, ttl)
    
    @staticmethod
    def invalidate_user_session(user_id: str):
        """Invalidate user session cache"""
        cache_manager.delete(get_cache_key('user_session', user_id))
    
    @staticmethod
    def invalidate_auth_token(token_hash: str):
        """Invalidate authentication token cache"""
        cache_manager.delete(get_cache_key('auth_token', token_hash))

class BedrockPromptCache:
    """Caching for Bedrock AI responses and prompts"""
    
    @staticmethod
    def _generate_prompt_hash(prompt: str, model_id: str, parameters: Dict = None) -> str:
        """Generate hash for prompt caching"""
        prompt_data = {
            'prompt': prompt,
            'model_id': model_id,
            'parameters': parameters or {}
        }
        prompt_string = json.dumps(prompt_data, sort_keys=True)
        return hashlib.sha256(prompt_string.encode()).hexdigest()[:16]
    
    @staticmethod
    def get_cached_response(prompt: str, model_id: str, parameters: Dict = None) -> Optional[Dict]:
        """Get cached Bedrock response"""
        prompt_hash = BedrockPromptCache._generate_prompt_hash(prompt, model_id, parameters)
        cache_key = get_cache_key('bedrock_prompt', prompt_hash)
        return cache_manager.get(cache_key)
    
    @staticmethod
    def cache_response(prompt: str, model_id: str, response: Dict, 
                      parameters: Dict = None) -> bool:
        """Cache Bedrock response"""
        prompt_hash = BedrockPromptCache._generate_prompt_hash(prompt, model_id, parameters)
        cache_key = get_cache_key('bedrock_prompt', prompt_hash)
        ttl = cache_manager.cache_ttls['bedrock_prompt']
        
        # Add metadata to cached response
        cached_data = {
            'response': response,
            'cached_at': datetime.utcnow().isoformat(),
            'model_id': model_id,
            'parameters': parameters or {}
        }
        
        return cache_manager.set(cache_key, cached_data, ttl)
    
    @staticmethod
    def get_review_insights(product_id: str, insight_type: str = 'sentiment') -> Optional[Dict]:
        """Get cached review insights"""
        cache_key = get_cache_key('review_insights', f"{product_id}:{insight_type}")
        return cache_manager.get(cache_key)
    
    @staticmethod
    def cache_review_insights(product_id: str, insights: Dict, 
                            insight_type: str = 'sentiment') -> bool:
        """Cache review insights"""
        cache_key = get_cache_key('review_insights', f"{product_id}:{insight_type}")
        ttl = cache_manager.cache_ttls['review_insights']
        
        # Add metadata
        cached_data = {
            'insights': insights,
            'generated_at': datetime.utcnow().isoformat(),
            'product_id': product_id,
            'insight_type': insight_type
        }
        
        return cache_manager.set(cache_key, cached_data, ttl)

class SearchSuggestionsCache:
    """Caching for auto-complete suggestions and search analytics"""
    
    @staticmethod
    def get_suggestions(query_prefix: str, limit: int = 10) -> Optional[List[Dict]]:
        """Get cached auto-complete suggestions"""
        cache_key = get_cache_key('search_suggestions', f"{query_prefix}:{limit}")
        return cache_manager.get(cache_key)
    
    @staticmethod
    def cache_suggestions(query_prefix: str, suggestions: List[Dict], 
                         limit: int = 10) -> bool:
        """Cache auto-complete suggestions"""
        cache_key = get_cache_key('search_suggestions', f"{query_prefix}:{limit}")
        ttl = cache_manager.cache_ttls['search_suggestions']
        return cache_manager.set(cache_key, suggestions, ttl)
    
    @staticmethod
    def get_popular_searches(category: str = 'all', limit: int = 20) -> Optional[List[Dict]]:
        """Get cached popular search terms"""
        cache_key = get_cache_key('popular_searches', f"{category}:{limit}")
        return cache_manager.get(cache_key)
    
    @staticmethod
    def cache_popular_searches(searches: List[Dict], category: str = 'all', 
                             limit: int = 20) -> bool:
        """Cache popular search terms"""
        cache_key = get_cache_key('popular_searches', f"{category}:{limit}")
        ttl = cache_manager.cache_ttls['popular_searches']
        return cache_manager.set(cache_key, searches, ttl)
    
    @staticmethod
    def increment_search_count(search_term: str) -> int:
        """Increment search term counter"""
        cache_key = get_cache_key('search_count', search_term.lower())
        count = cache_manager.increment(cache_key)
        # Set expiration for search counters (24 hours)
        cache_manager.expire(cache_key, 86400)
        return count
    
    @staticmethod
    def get_search_count(search_term: str) -> int:
        """Get search term count"""
        cache_key = get_cache_key('search_count', search_term.lower())
        count = cache_manager.get(cache_key)
        return int(count) if count else 0

class AnalyticsCache:
    """Caching for analytics data and insights"""
    
    @staticmethod
    def get_product_analytics(product_id: str, metric_type: str) -> Optional[Dict]:
        """Get cached product analytics"""
        cache_key = get_cache_key('analytics_cache', f"product:{product_id}:{metric_type}")
        return cache_manager.get(cache_key)
    
    @staticmethod
    def cache_product_analytics(product_id: str, metric_type: str, 
                              analytics_data: Dict) -> bool:
        """Cache product analytics data"""
        cache_key = get_cache_key('analytics_cache', f"product:{product_id}:{metric_type}")
        ttl = cache_manager.cache_ttls['analytics_cache']
        
        cached_data = {
            'data': analytics_data,
            'generated_at': datetime.utcnow().isoformat(),
            'product_id': product_id,
            'metric_type': metric_type
        }
        
        return cache_manager.set(cache_key, cached_data, ttl)
    
    @staticmethod
    def get_user_recommendations(user_id: str, recommendation_type: str = 'general') -> Optional[List[Dict]]:
        """Get cached user recommendations"""
        cache_key = get_cache_key('analytics_cache', f"recommendations:{user_id}:{recommendation_type}")
        return cache_manager.get(cache_key)
    
    @staticmethod
    def cache_user_recommendations(user_id: str, recommendations: List[Dict],
                                 recommendation_type: str = 'general') -> bool:
        """Cache user recommendations"""
        cache_key = get_cache_key('analytics_cache', f"recommendations:{user_id}:{recommendation_type}")
        ttl = cache_manager.cache_ttls['analytics_cache']
        return cache_manager.set(cache_key, recommendations, ttl)

class ChatMemoryCache:
    """Caching for chat memory and conversation context"""
    
    @staticmethod
    def get_recent_messages(user_id: str, limit: int = 10) -> Optional[List[Dict]]:
        """Get recent chat messages from cache"""
        cache_key = get_cache_key('chat_memory', f"{user_id}:recent:{limit}")
        return cache_manager.get(cache_key)
    
    @staticmethod
    def cache_recent_messages(user_id: str, messages: List[Dict], 
                            limit: int = 10) -> bool:
        """Cache recent chat messages"""
        cache_key = get_cache_key('chat_memory', f"{user_id}:recent:{limit}")
        ttl = cache_manager.cache_ttls['chat_memory']
        return cache_manager.set(cache_key, messages, ttl)
    
    @staticmethod
    def add_message_to_cache(user_id: str, message: Dict, max_messages: int = 10):
        """Add new message to cached conversation"""
        cache_key = get_cache_key('chat_memory', f"{user_id}:recent:{max_messages}")
        
        # Get existing messages
        messages = cache_manager.get(cache_key) or []
        
        # Add new message and maintain limit
        messages.append(message)
        if len(messages) > max_messages:
            messages = messages[-max_messages:]
        
        # Update cache
        ttl = cache_manager.cache_ttls['chat_memory']
        cache_manager.set(cache_key, messages, ttl)
    
    @staticmethod
    def clear_user_chat_cache(user_id: str):
        """Clear all chat cache for user"""
        pattern = get_cache_key('chat_memory', f"{user_id}:*")
        cache_manager.delete_pattern(pattern)

# Cache invalidation strategies
class CacheInvalidation:
    """Centralized cache invalidation management"""
    
    @staticmethod
    def invalidate_product_related(product_id: str):
        """Invalidate all product-related caches"""
        ProductSearchCache.invalidate_product_cache(product_id)
        
        # Invalidate product analytics
        pattern = get_cache_key('analytics_cache', f"product:{product_id}:*")
        cache_manager.delete_pattern(pattern)
        
        # Invalidate review insights
        pattern = get_cache_key('review_insights', f"{product_id}:*")
        cache_manager.delete_pattern(pattern)
    
    @staticmethod
    def invalidate_user_related(user_id: str):
        """Invalidate all user-related caches"""
        SessionCache.invalidate_user_session(user_id)
        ChatMemoryCache.clear_user_chat_cache(user_id)
        
        # Invalidate user recommendations
        pattern = get_cache_key('analytics_cache', f"recommendations:{user_id}:*")
        cache_manager.delete_pattern(pattern)
    
    @staticmethod
    def invalidate_search_related():
        """Invalidate search-related caches"""
        cache_manager.delete_pattern(get_cache_key('product_search', '*'))
        cache_manager.delete_pattern(get_cache_key('search_suggestions', '*'))
        cache_manager.delete_pattern(get_cache_key('popular_searches', '*'))
    
    @staticmethod
    def invalidate_all_caches():
        """Invalidate all application caches (use with caution)"""
        pattern = get_cache_key('*', '*')
        cache_manager.delete_pattern(pattern)

# Decorator for automatic caching
def cache_result(cache_key_prefix: str, ttl: Optional[int] = None, 
                key_generator: Optional[callable] = None):
    """Decorator for automatic result caching"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Generate cache key
            if key_generator:
                cache_key = key_generator(*args, **kwargs)
            else:
                cache_key = cache_manager._generate_cache_key(cache_key_prefix, *args, **kwargs)
            
            # Try to get from cache first
            cached_result = cache_manager.get(cache_key)
            if cached_result is not None:
                logger.debug(f"Cache hit for key: {cache_key}")
                return cached_result
            
            # Execute function and cache result
            result = func(*args, **kwargs)
            if result is not None:
                cache_ttl = ttl or cache_manager.default_ttl
                cache_manager.set(cache_key, result, cache_ttl)
                logger.debug(f"Cached result for key: {cache_key}")
            
            return result
        return wrapper
    return decorator