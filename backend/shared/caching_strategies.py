"""
Comprehensive caching strategies for AWS NoSQL Workshop
Implements cache invalidation, warming, and consistency patterns
"""
import json
import logging
from typing import Any, Dict, List, Optional, Set, Callable
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
import time

try:
    from .cache_manager import (
        cache_manager, ProductSearchCache, SessionCache, BedrockPromptCache,
        SearchSuggestionsCache, AnalyticsCache, ChatMemoryCache
    )
    from .database import db, get_cache_key
    from .config import config
except ImportError:
    from cache_manager import (
        cache_manager, ProductSearchCache, SessionCache, BedrockPromptCache,
        SearchSuggestionsCache, AnalyticsCache, ChatMemoryCache
    )
    from database import db, get_cache_key
    from config import config

logger = logging.getLogger(__name__)

class CacheInvalidationStrategy:
    """Advanced cache invalidation strategies with dependency tracking"""
    
    def __init__(self):
        self._dependency_graph = {}
        self._invalidation_queue = []
        self._lock = threading.Lock()
    
    def register_dependency(self, parent_key: str, dependent_keys: List[str]):
        """Register cache dependencies for cascade invalidation"""
        with self._lock:
            if parent_key not in self._dependency_graph:
                self._dependency_graph[parent_key] = set()
            self._dependency_graph[parent_key].update(dependent_keys)
    
    def invalidate_with_dependencies(self, cache_key: str, cascade: bool = True) -> int:
        """Invalidate cache key and its dependencies"""
        invalidated_count = 0
        
        with self._lock:
            # Add to invalidation queue
            self._invalidation_queue.append(cache_key)
            
            # Process invalidation queue
            while self._invalidation_queue:
                current_key = self._invalidation_queue.pop(0)
                
                # Invalidate current key
                if cache_manager.delete(current_key):
                    invalidated_count += 1
                    logger.debug(f"Invalidated cache key: {current_key}")
                
                # Add dependencies to queue if cascading
                if cascade and current_key in self._dependency_graph:
                    for dependent_key in self._dependency_graph[current_key]:
                        if dependent_key not in self._invalidation_queue:
                            self._invalidation_queue.append(dependent_key)
        
        return invalidated_count
    
    def invalidate_by_pattern_with_dependencies(self, pattern: str, cascade: bool = True) -> int:
        """Invalidate cache keys by pattern and their dependencies"""
        try:
            # Get all keys matching pattern
            keys = db.elasticache.keys(pattern)
            total_invalidated = 0
            
            for key in keys:
                total_invalidated += self.invalidate_with_dependencies(key, cascade)
            
            return total_invalidated
        except Exception as e:
            logger.error(f"Pattern invalidation failed for {pattern}: {e}")
            return 0

class CacheWarmingStrategy:
    """Cache warming strategies for proactive cache population"""
    
    def __init__(self):
        self._warming_tasks = {}
        self._executor = ThreadPoolExecutor(max_workers=5, thread_name_prefix="cache_warmer")
    
    def warm_product_caches(self, product_ids: List[str], priority: str = 'normal'):
        """Warm product-related caches"""
        def warm_single_product(product_id: str):
            try:
                # This would call actual product API functions to populate cache
                logger.debug(f"Warming product cache for: {product_id}")
                
                # Example: warm product details cache
                # product_data = get_product_details(product_id)
                # ProductSearchCache.cache_product_details(product_id, product_data)
                
                return product_id
            except Exception as e:
                logger.warning(f"Failed to warm product cache for {product_id}: {e}")
                return None
        
        # Submit warming tasks
        futures = []
        for product_id in product_ids:
            future = self._executor.submit(warm_single_product, product_id)
            futures.append(future)
        
        # Track completion
        warmed_count = 0
        for future in as_completed(futures, timeout=30):
            try:
                result = future.result()
                if result:
                    warmed_count += 1
            except Exception as e:
                logger.warning(f"Cache warming task failed: {e}")
        
        logger.info(f"Warmed {warmed_count}/{len(product_ids)} product caches")
        return warmed_count
    
    def warm_search_caches(self, popular_terms: List[str]):
        """Warm search-related caches"""
        def warm_search_term(term: str):
            try:
                # This would call search functions to populate cache
                logger.debug(f"Warming search cache for: {term}")
                
                # Example: warm search suggestions
                # suggestions = generate_search_suggestions(term)
                # SearchSuggestionsCache.cache_suggestions(term, suggestions)
                
                return term
            except Exception as e:
                logger.warning(f"Failed to warm search cache for {term}: {e}")
                return None
        
        futures = []
        for term in popular_terms:
            future = self._executor.submit(warm_search_term, term)
            futures.append(future)
        
        warmed_count = 0
        for future in as_completed(futures, timeout=20):
            try:
                result = future.result()
                if result:
                    warmed_count += 1
            except Exception as e:
                logger.warning(f"Search cache warming task failed: {e}")
        
        logger.info(f"Warmed {warmed_count}/{len(popular_terms)} search caches")
        return warmed_count
    
    def warm_bedrock_responses(self, common_prompts: List[Dict[str, Any]]):
        """Warm Bedrock response caches for common prompts"""
        def warm_bedrock_prompt(prompt_data: Dict[str, Any]):
            try:
                prompt = prompt_data.get('prompt', '')
                model_id = prompt_data.get('model_id', config.BEDROCK_MODEL_ID)
                parameters = prompt_data.get('parameters', {})
                
                logger.debug(f"Warming Bedrock cache for prompt: {prompt[:50]}...")
                
                # This would call actual Bedrock function to populate cache
                # response = call_bedrock_model(prompt, model_id, parameters)
                # BedrockPromptCache.cache_response(prompt, model_id, response, parameters)
                
                return prompt_data
            except Exception as e:
                logger.warning(f"Failed to warm Bedrock cache: {e}")
                return None
        
        futures = []
        for prompt_data in common_prompts:
            future = self._executor.submit(warm_bedrock_prompt, prompt_data)
            futures.append(future)
        
        warmed_count = 0
        for future in as_completed(futures, timeout=60):
            try:
                result = future.result()
                if result:
                    warmed_count += 1
            except Exception as e:
                logger.warning(f"Bedrock cache warming task failed: {e}")
        
        logger.info(f"Warmed {warmed_count}/{len(common_prompts)} Bedrock caches")
        return warmed_count
    
    def schedule_warming_task(self, task_name: str, warming_func: Callable, 
                            interval_minutes: int = 60):
        """Schedule periodic cache warming task"""
        def run_periodic_warming():
            while task_name in self._warming_tasks:
                try:
                    warming_func()
                    logger.debug(f"Completed scheduled warming task: {task_name}")
                except Exception as e:
                    logger.error(f"Scheduled warming task {task_name} failed: {e}")
                
                # Wait for next interval
                time.sleep(interval_minutes * 60)
        
        # Start warming task in background
        if task_name not in self._warming_tasks:
            thread = threading.Thread(target=run_periodic_warming, 
                                     name=f"warming_{task_name}")
            thread.daemon = True
            thread.start()
            self._warming_tasks[task_name] = thread
            logger.info(f"Started periodic warming task: {task_name}")
    
    def stop_warming_task(self, task_name: str):
        """Stop scheduled warming task"""
        if task_name in self._warming_tasks:
            del self._warming_tasks[task_name]
            logger.info(f"Stopped warming task: {task_name}")

class CacheConsistencyManager:
    """Manage cache consistency across different data sources"""
    
    def __init__(self):
        self._consistency_rules = {}
        self._update_timestamps = {}
        self._lock = threading.Lock()
    
    def register_consistency_rule(self, data_type: str, cache_keys: List[str], 
                                 max_staleness_seconds: int = 300):
        """Register consistency rule for data type"""
        with self._lock:
            self._consistency_rules[data_type] = {
                'cache_keys': cache_keys,
                'max_staleness': max_staleness_seconds,
                'last_updated': datetime.utcnow()
            }
    
    def mark_data_updated(self, data_type: str):
        """Mark data as updated, triggering cache invalidation if needed"""
        with self._lock:
            if data_type in self._consistency_rules:
                rule = self._consistency_rules[data_type]
                
                # Check if caches are stale
                time_since_update = datetime.utcnow() - rule['last_updated']
                if time_since_update.total_seconds() > rule['max_staleness']:
                    # Invalidate related caches
                    for cache_key in rule['cache_keys']:
                        cache_manager.delete_pattern(cache_key)
                    
                    logger.info(f"Invalidated stale caches for data type: {data_type}")
                
                # Update timestamp
                rule['last_updated'] = datetime.utcnow()
    
    def check_cache_consistency(self) -> Dict[str, bool]:
        """Check consistency of all registered cache types"""
        consistency_status = {}
        
        with self._lock:
            for data_type, rule in self._consistency_rules.items():
                time_since_update = datetime.utcnow() - rule['last_updated']
                is_consistent = time_since_update.total_seconds() <= rule['max_staleness']
                consistency_status[data_type] = is_consistent
                
                if not is_consistent:
                    logger.warning(f"Cache inconsistency detected for {data_type}")
        
        return consistency_status

class SmartCacheManager:
    """Intelligent cache management with adaptive strategies"""
    
    def __init__(self):
        self.invalidation_strategy = CacheInvalidationStrategy()
        self.warming_strategy = CacheWarmingStrategy()
        self.consistency_manager = CacheConsistencyManager()
        self._access_patterns = {}
        self._lock = threading.Lock()
    
    def track_cache_access(self, cache_key: str, hit: bool):
        """Track cache access patterns for optimization"""
        with self._lock:
            if cache_key not in self._access_patterns:
                self._access_patterns[cache_key] = {
                    'hits': 0,
                    'misses': 0,
                    'last_access': datetime.utcnow(),
                    'access_frequency': 0
                }
            
            pattern = self._access_patterns[cache_key]
            if hit:
                pattern['hits'] += 1
            else:
                pattern['misses'] += 1
            
            pattern['last_access'] = datetime.utcnow()
            pattern['access_frequency'] = pattern['hits'] + pattern['misses']
    
    def get_cache_recommendations(self) -> Dict[str, Any]:
        """Get recommendations for cache optimization"""
        recommendations = {
            'hot_keys': [],
            'cold_keys': [],
            'high_miss_rate_keys': [],
            'suggested_ttl_adjustments': {}
        }
        
        with self._lock:
            now = datetime.utcnow()
            
            for cache_key, pattern in self._access_patterns.items():
                hit_rate = pattern['hits'] / max(pattern['access_frequency'], 1)
                time_since_access = (now - pattern['last_access']).total_seconds()
                
                # Identify hot keys (frequently accessed)
                if pattern['access_frequency'] > 100 and time_since_access < 3600:
                    recommendations['hot_keys'].append({
                        'key': cache_key,
                        'frequency': pattern['access_frequency'],
                        'hit_rate': hit_rate
                    })
                
                # Identify cold keys (rarely accessed)
                elif time_since_access > 86400:  # 24 hours
                    recommendations['cold_keys'].append({
                        'key': cache_key,
                        'last_access': pattern['last_access'].isoformat(),
                        'frequency': pattern['access_frequency']
                    })
                
                # Identify keys with high miss rates
                if hit_rate < 0.5 and pattern['access_frequency'] > 10:
                    recommendations['high_miss_rate_keys'].append({
                        'key': cache_key,
                        'hit_rate': hit_rate,
                        'frequency': pattern['access_frequency']
                    })
                
                # Suggest TTL adjustments
                if hit_rate > 0.8 and pattern['access_frequency'] > 50:
                    # High hit rate and frequency - increase TTL
                    recommendations['suggested_ttl_adjustments'][cache_key] = 'increase'
                elif hit_rate < 0.3:
                    # Low hit rate - decrease TTL
                    recommendations['suggested_ttl_adjustments'][cache_key] = 'decrease'
        
        return recommendations
    
    def optimize_cache_configuration(self):
        """Apply automatic cache optimizations based on access patterns"""
        recommendations = self.get_cache_recommendations()
        
        # Warm hot keys proactively
        hot_keys = [item['key'] for item in recommendations['hot_keys']]
        if hot_keys:
            logger.info(f"Proactively warming {len(hot_keys)} hot cache keys")
            # Implementation would depend on key types
        
        # Clean up cold keys
        cold_keys = [item['key'] for item in recommendations['cold_keys']]
        for key in cold_keys:
            cache_manager.delete(key)
        
        if cold_keys:
            logger.info(f"Cleaned up {len(cold_keys)} cold cache keys")
        
        # Log optimization summary
        logger.info(f"Cache optimization completed: "
                   f"Hot keys: {len(hot_keys)}, "
                   f"Cold keys cleaned: {len(cold_keys)}, "
                   f"High miss rate keys: {len(recommendations['high_miss_rate_keys'])}")

# Global cache strategy instances
cache_invalidation = CacheInvalidationStrategy()
cache_warming = CacheWarmingStrategy()
cache_consistency = CacheConsistencyManager()
smart_cache = SmartCacheManager()

# Initialize common cache dependencies and consistency rules
def initialize_cache_strategies():
    """Initialize cache strategies with common patterns"""
    
    # Register cache dependencies
    cache_invalidation.register_dependency(
        'product_details:*',
        ['product_search:*', 'product_listing:*', 'analytics_cache:product:*']
    )
    
    cache_invalidation.register_dependency(
        'user_session:*',
        ['analytics_cache:recommendations:*', 'chat_memory:*']
    )
    
    # Register consistency rules
    cache_consistency.register_consistency_rule(
        'products',
        ['product_details:*', 'product_search:*', 'product_listing:*'],
        max_staleness_seconds=1800  # 30 minutes
    )
    
    cache_consistency.register_consistency_rule(
        'reviews',
        ['review_insights:*', 'analytics_cache:product:*'],
        max_staleness_seconds=3600  # 1 hour
    )
    
    cache_consistency.register_consistency_rule(
        'search_data',
        ['search_suggestions:*', 'popular_searches:*'],
        max_staleness_seconds=900  # 15 minutes
    )
    
    logger.info("Cache strategies initialized")

# Utility functions for common cache operations
def invalidate_product_caches(product_id: str):
    """Invalidate all product-related caches"""
    patterns = [
        get_cache_key('product_details', product_id),
        get_cache_key('product_search', '*'),
        get_cache_key('product_listing', '*'),
        get_cache_key('analytics_cache', f'product:{product_id}:*'),
        get_cache_key('review_insights', f'{product_id}:*')
    ]
    
    total_invalidated = 0
    for pattern in patterns:
        total_invalidated += cache_manager.delete_pattern(pattern)
    
    logger.info(f"Invalidated {total_invalidated} cache entries for product {product_id}")
    return total_invalidated

def invalidate_user_caches(user_id: str):
    """Invalidate all user-related caches"""
    patterns = [
        get_cache_key('user_session', user_id),
        get_cache_key('chat_memory', f'{user_id}:*'),
        get_cache_key('analytics_cache', f'recommendations:{user_id}:*')
    ]
    
    total_invalidated = 0
    for pattern in patterns:
        total_invalidated += cache_manager.delete_pattern(pattern)
    
    logger.info(f"Invalidated {total_invalidated} cache entries for user {user_id}")
    return total_invalidated

def warm_popular_caches():
    """Warm caches for popular content"""
    try:
        # Get popular products (this would come from analytics)
        popular_products = ['product1', 'product2', 'product3']  # Example
        cache_warming.warm_product_caches(popular_products)
        
        # Get popular search terms
        popular_searches = ['wireless headphones', 'laptop', 'smartphone']  # Example
        cache_warming.warm_search_caches(popular_searches)
        
        # Warm common Bedrock prompts
        common_prompts = [
            {
                'prompt': 'Analyze product reviews for sentiment',
                'model_id': config.BEDROCK_MODEL_ID,
                'parameters': {'max_tokens': 1000}
            }
        ]
        cache_warming.warm_bedrock_responses(common_prompts)
        
        logger.info("Popular caches warmed successfully")
    except Exception as e:
        logger.error(f"Failed to warm popular caches: {e}")

# Initialize strategies on module import
initialize_cache_strategies()