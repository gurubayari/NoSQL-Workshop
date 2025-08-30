"""
Database query optimization utilities for AWS NoSQL Workshop
Provides query optimization, indexing strategies, and performance monitoring
"""
import logging
import time
from typing import Any, Dict, List, Optional, Tuple, Union
from functools import wraps
from datetime import datetime, timedelta
import json
import threading
from collections import defaultdict, deque

try:
    from .database import db, get_documentdb_collection, get_dynamodb_table
    from .config import config
    from .cache_manager import cache_manager
except ImportError:
    from database import db, get_documentdb_collection, get_dynamodb_table
    from config import config
    from cache_manager import cache_manager

logger = logging.getLogger(__name__)

class QueryPerformanceMonitor:
    """Monitor and analyze database query performance"""
    
    def __init__(self, max_history: int = 1000):
        self._query_history = deque(maxlen=max_history)
        self._query_stats = defaultdict(lambda: {
            'count': 0,
            'total_time': 0.0,
            'avg_time': 0.0,
            'min_time': float('inf'),
            'max_time': 0.0,
            'errors': 0
        })
        self._lock = threading.Lock()
    
    def record_query(self, query_type: str, query_info: Dict[str, Any], 
                    execution_time: float, success: bool = True):
        """Record query execution metrics"""
        with self._lock:
            # Add to history
            record = {
                'timestamp': datetime.utcnow(),
                'query_type': query_type,
                'query_info': query_info,
                'execution_time': execution_time,
                'success': success
            }
            self._query_history.append(record)
            
            # Update statistics
            stats = self._query_stats[query_type]
            stats['count'] += 1
            
            if success:
                stats['total_time'] += execution_time
                stats['avg_time'] = stats['total_time'] / (stats['count'] - stats['errors'])
                stats['min_time'] = min(stats['min_time'], execution_time)
                stats['max_time'] = max(stats['max_time'], execution_time)
            else:
                stats['errors'] += 1
    
    def get_query_stats(self, query_type: Optional[str] = None) -> Dict[str, Any]:
        """Get query performance statistics"""
        with self._lock:
            if query_type:
                return dict(self._query_stats.get(query_type, {}))
            return {k: dict(v) for k, v in self._query_stats.items()}
    
    def get_slow_queries(self, threshold_seconds: float = 1.0, 
                        limit: int = 10) -> List[Dict[str, Any]]:
        """Get slow queries above threshold"""
        with self._lock:
            slow_queries = [
                record for record in self._query_history
                if record['execution_time'] > threshold_seconds and record['success']
            ]
            # Sort by execution time descending
            slow_queries.sort(key=lambda x: x['execution_time'], reverse=True)
            return slow_queries[:limit]
    
    def get_error_queries(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent failed queries"""
        with self._lock:
            error_queries = [
                record for record in self._query_history
                if not record['success']
            ]
            return list(reversed(error_queries))[:limit]
    
    def reset_stats(self):
        """Reset all statistics"""
        with self._lock:
            self._query_history.clear()
            self._query_stats.clear()

# Global performance monitor
query_monitor = QueryPerformanceMonitor()

def monitor_query_performance(query_type: str):
    """Decorator to monitor query performance"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.time()
            success = True
            result = None
            
            try:
                result = func(*args, **kwargs)
                return result
            except Exception as e:
                success = False
                raise
            finally:
                execution_time = time.time() - start_time
                query_info = {
                    'function': func.__name__,
                    'args_count': len(args),
                    'kwargs_keys': list(kwargs.keys())
                }
                query_monitor.record_query(query_type, query_info, execution_time, success)
        
        return wrapper
    return decorator

class DynamoDBOptimizer:
    """Optimization utilities for DynamoDB operations"""
    
    @staticmethod
    def build_key_condition_expression(partition_key: str, partition_value: Any,
                                     sort_key: Optional[str] = None,
                                     sort_value: Optional[Any] = None,
                                     sort_operator: str = '=') -> Tuple[Any, Dict[str, Any]]:
        """Build optimized key condition expression"""
        from boto3.dynamodb.conditions import Key
        
        # Build partition key condition
        key_condition = Key(partition_key).eq(partition_value)
        expression_values = {f':{partition_key}': partition_value}
        
        # Add sort key condition if provided
        if sort_key and sort_value is not None:
            if sort_operator == '=':
                key_condition = key_condition & Key(sort_key).eq(sort_value)
            elif sort_operator == '<':
                key_condition = key_condition & Key(sort_key).lt(sort_value)
            elif sort_operator == '<=':
                key_condition = key_condition & Key(sort_key).lte(sort_value)
            elif sort_operator == '>':
                key_condition = key_condition & Key(sort_key).gt(sort_value)
            elif sort_operator == '>=':
                key_condition = key_condition & Key(sort_key).gte(sort_value)
            elif sort_operator == 'begins_with':
                key_condition = key_condition & Key(sort_key).begins_with(sort_value)
            elif sort_operator == 'between':
                if isinstance(sort_value, (list, tuple)) and len(sort_value) == 2:
                    key_condition = key_condition & Key(sort_key).between(sort_value[0], sort_value[1])
            
            expression_values[f':{sort_key}'] = sort_value
        
        return key_condition, expression_values
    
    @staticmethod
    def build_filter_expression(filters: Dict[str, Any]) -> Tuple[Any, Dict[str, Any]]:
        """Build optimized filter expression"""
        from boto3.dynamodb.conditions import Attr
        
        if not filters:
            return None, {}
        
        filter_expression = None
        expression_values = {}
        
        for attr_name, filter_config in filters.items():
            if isinstance(filter_config, dict):
                operator = filter_config.get('operator', '=')
                value = filter_config.get('value')
            else:
                operator = '='
                value = filter_config
            
            # Build attribute condition
            attr_condition = None
            if operator == '=':
                attr_condition = Attr(attr_name).eq(value)
            elif operator == '!=':
                attr_condition = Attr(attr_name).ne(value)
            elif operator == '<':
                attr_condition = Attr(attr_name).lt(value)
            elif operator == '<=':
                attr_condition = Attr(attr_name).lte(value)
            elif operator == '>':
                attr_condition = Attr(attr_name).gt(value)
            elif operator == '>=':
                attr_condition = Attr(attr_name).gte(value)
            elif operator == 'contains':
                attr_condition = Attr(attr_name).contains(value)
            elif operator == 'begins_with':
                attr_condition = Attr(attr_name).begins_with(value)
            elif operator == 'in':
                attr_condition = Attr(attr_name).is_in(value)
            elif operator == 'exists':
                attr_condition = Attr(attr_name).exists() if value else Attr(attr_name).not_exists()
            
            if attr_condition:
                if filter_expression is None:
                    filter_expression = attr_condition
                else:
                    filter_expression = filter_expression & attr_condition
                
                expression_values[f':{attr_name}'] = value
        
        return filter_expression, expression_values
    
    @staticmethod
    @monitor_query_performance('dynamodb_query')
    def optimized_query(table_name: str, partition_key: str, partition_value: Any,
                       sort_key: Optional[str] = None, sort_value: Optional[Any] = None,
                       sort_operator: str = '=', filters: Optional[Dict[str, Any]] = None,
                       index_name: Optional[str] = None, limit: Optional[int] = None,
                       scan_index_forward: bool = True, 
                       last_evaluated_key: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Perform optimized DynamoDB query"""
        table = get_dynamodb_table(table_name)
        
        # Build key condition
        key_condition, _ = DynamoDBOptimizer.build_key_condition_expression(
            partition_key, partition_value, sort_key, sort_value, sort_operator
        )
        
        # Build filter expression
        filter_expression, _ = DynamoDBOptimizer.build_filter_expression(filters or {})
        
        # Build query parameters
        query_params = {
            'KeyConditionExpression': key_condition,
            'ScanIndexForward': scan_index_forward
        }
        
        if filter_expression:
            query_params['FilterExpression'] = filter_expression
        if index_name:
            query_params['IndexName'] = index_name
        if limit:
            query_params['Limit'] = limit
        if last_evaluated_key:
            query_params['ExclusiveStartKey'] = last_evaluated_key
        
        try:
            response = table.query(**query_params)
            return {
                'items': response.get('Items', []),
                'count': response.get('Count', 0),
                'scanned_count': response.get('ScannedCount', 0),
                'last_evaluated_key': response.get('LastEvaluatedKey'),
                'consumed_capacity': response.get('ConsumedCapacity')
            }
        except Exception as e:
            logger.error(f"DynamoDB query failed for table {table_name}: {e}")
            raise
    
    @staticmethod
    @monitor_query_performance('dynamodb_batch_get')
    def optimized_batch_get(table_name: str, keys: List[Dict[str, Any]], 
                           consistent_read: bool = False) -> List[Dict[str, Any]]:
        """Perform optimized batch get with automatic chunking"""
        if not keys:
            return []
        
        all_items = []
        batch_size = 100  # DynamoDB limit
        
        try:
            for i in range(0, len(keys), batch_size):
                batch_keys = keys[i:i + batch_size]
                
                response = db.dynamodb.batch_get_item(
                    RequestItems={
                        table_name: {
                            'Keys': batch_keys,
                            'ConsistentRead': consistent_read
                        }
                    }
                )
                
                items = response.get('Responses', {}).get(table_name, [])
                all_items.extend(items)
                
                # Handle unprocessed keys
                unprocessed = response.get('UnprocessedKeys', {})
                while unprocessed:
                    time.sleep(0.1)  # Brief delay for throttling
                    response = db.dynamodb.batch_get_item(RequestItems=unprocessed)
                    items = response.get('Responses', {}).get(table_name, [])
                    all_items.extend(items)
                    unprocessed = response.get('UnprocessedKeys', {})
            
            return all_items
        except Exception as e:
            logger.error(f"DynamoDB batch get failed for table {table_name}: {e}")
            raise

class DocumentDBOptimizer:
    """Optimization utilities for DocumentDB operations"""
    
    @staticmethod
    def build_optimized_pipeline(base_pipeline: List[Dict[str, Any]], 
                                optimization_hints: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """Build optimized aggregation pipeline"""
        optimized_pipeline = base_pipeline.copy()
        hints = optimization_hints or {}
        
        # Add index hints if provided
        if hints.get('use_index'):
            # MongoDB will automatically use appropriate indexes
            pass
        
        # Optimize $match stages - move them early in pipeline
        match_stages = []
        other_stages = []
        
        for stage in optimized_pipeline:
            if '$match' in stage:
                match_stages.append(stage)
            else:
                other_stages.append(stage)
        
        # Reconstruct pipeline with $match stages first
        optimized_pipeline = match_stages + other_stages
        
        # Add $limit early if specified
        if hints.get('early_limit'):
            limit_stage = {'$limit': hints['early_limit']}
            # Insert after $match stages but before complex operations
            insert_index = len(match_stages)
            optimized_pipeline.insert(insert_index, limit_stage)
        
        return optimized_pipeline
    
    @staticmethod
    @monitor_query_performance('documentdb_find')
    def optimized_find(collection_name: str, filter_query: Optional[Dict[str, Any]] = None,
                      projection: Optional[Dict[str, Any]] = None,
                      sort: Optional[List[Tuple[str, int]]] = None,
                      limit: Optional[int] = None, skip: Optional[int] = None,
                      hint: Optional[str] = None) -> List[Dict[str, Any]]:
        """Perform optimized DocumentDB find operation"""
        collection = get_documentdb_collection(collection_name)
        
        try:
            # Build cursor
            cursor = collection.find(filter_query or {}, projection)
            
            # Apply hint if provided
            if hint:
                cursor = cursor.hint(hint)
            
            # Apply sort
            if sort:
                cursor = cursor.sort(sort)
            
            # Apply skip and limit
            if skip:
                cursor = cursor.skip(skip)
            if limit:
                cursor = cursor.limit(limit)
            
            return list(cursor)
        except Exception as e:
            logger.error(f"DocumentDB find failed for collection {collection_name}: {e}")
            raise
    
    @staticmethod
    @monitor_query_performance('documentdb_aggregate')
    def optimized_aggregate(collection_name: str, pipeline: List[Dict[str, Any]],
                           optimization_hints: Optional[Dict[str, Any]] = None,
                           allow_disk_use: bool = False) -> List[Dict[str, Any]]:
        """Perform optimized DocumentDB aggregation"""
        collection = get_documentdb_collection(collection_name)
        
        try:
            # Optimize pipeline
            optimized_pipeline = DocumentDBOptimizer.build_optimized_pipeline(
                pipeline, optimization_hints
            )
            
            # Execute aggregation
            cursor = collection.aggregate(
                optimized_pipeline,
                allowDiskUse=allow_disk_use
            )
            
            return list(cursor)
        except Exception as e:
            logger.error(f"DocumentDB aggregation failed for collection {collection_name}: {e}")
            raise
    
    @staticmethod
    @monitor_query_performance('documentdb_vector_search')
    def optimized_vector_search(collection_name: str, vector: List[float],
                               vector_field: str = 'embedding', limit: int = 10,
                               filter_query: Optional[Dict[str, Any]] = None,
                               similarity_threshold: Optional[float] = None) -> List[Dict[str, Any]]:
        """Perform optimized vector search"""
        collection = get_documentdb_collection(collection_name)
        
        try:
            # Build vector search pipeline
            pipeline = [
                {
                    '$search': {
                        'vectorSearch': {
                            'vector': vector,
                            'path': vector_field,
                            'similarity': 'cosine',
                            'k': limit
                        }
                    }
                },
                {
                    '$addFields': {
                        'score': {'$meta': 'vectorSearchScore'}
                    }
                }
            ]
            
            # Add filter if provided
            if filter_query:
                pipeline[0]['$search']['vectorSearch']['filter'] = filter_query
            
            # Add similarity threshold filter
            if similarity_threshold:
                pipeline.append({
                    '$match': {
                        'score': {'$gte': similarity_threshold}
                    }
                })
            
            return list(collection.aggregate(pipeline))
        except Exception as e:
            logger.error(f"DocumentDB vector search failed for collection {collection_name}: {e}")
            raise
    
    @staticmethod
    def create_optimized_indexes(collection_name: str, index_specs: List[Dict[str, Any]]):
        """Create optimized indexes for collection"""
        collection = get_documentdb_collection(collection_name)
        
        for index_spec in index_specs:
            try:
                index_fields = index_spec.get('fields', {})
                index_options = index_spec.get('options', {})
                
                # Set default options for performance
                if 'background' not in index_options:
                    index_options['background'] = True
                
                collection.create_index(
                    [(field, direction) for field, direction in index_fields.items()],
                    **index_options
                )
                
                logger.info(f"Created index on {collection_name}: {index_fields}")
            except Exception as e:
                logger.warning(f"Failed to create index on {collection_name}: {e}")

class QueryOptimizationRecommendations:
    """Generate query optimization recommendations"""
    
    @staticmethod
    def analyze_query_patterns() -> Dict[str, Any]:
        """Analyze query patterns and provide optimization recommendations"""
        stats = query_monitor.get_query_stats()
        slow_queries = query_monitor.get_slow_queries(threshold_seconds=0.5)
        
        recommendations = {
            'performance_issues': [],
            'indexing_suggestions': [],
            'query_optimizations': [],
            'caching_opportunities': []
        }
        
        # Analyze performance issues
        for query_type, query_stats in stats.items():
            if query_stats['avg_time'] > 1.0:
                recommendations['performance_issues'].append({
                    'query_type': query_type,
                    'avg_time': query_stats['avg_time'],
                    'suggestion': 'Consider adding indexes or optimizing query structure'
                })
            
            if query_stats['errors'] > 0:
                error_rate = query_stats['errors'] / query_stats['count']
                if error_rate > 0.1:  # More than 10% error rate
                    recommendations['performance_issues'].append({
                        'query_type': query_type,
                        'error_rate': error_rate,
                        'suggestion': 'High error rate detected, review query logic and error handling'
                    })
        
        # Analyze slow queries for patterns
        slow_query_types = defaultdict(int)
        for query in slow_queries:
            slow_query_types[query['query_type']] += 1
        
        for query_type, count in slow_query_types.items():
            if count > 5:  # Frequent slow queries
                recommendations['query_optimizations'].append({
                    'query_type': query_type,
                    'slow_count': count,
                    'suggestion': 'Frequently slow query type, consider optimization'
                })
        
        # Suggest caching opportunities
        for query_type, query_stats in stats.items():
            if (query_stats['count'] > 100 and 
                query_stats['avg_time'] > 0.1 and 
                'search' in query_type.lower()):
                recommendations['caching_opportunities'].append({
                    'query_type': query_type,
                    'frequency': query_stats['count'],
                    'avg_time': query_stats['avg_time'],
                    'suggestion': 'High frequency query suitable for caching'
                })
        
        return recommendations
    
    @staticmethod
    def get_index_recommendations(collection_name: str, 
                                query_patterns: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Get index recommendations based on query patterns"""
        recommendations = []
        field_usage = defaultdict(int)
        sort_usage = defaultdict(int)
        
        # Analyze query patterns
        for pattern in query_patterns:
            # Count field usage in filters
            if 'filter' in pattern:
                for field in pattern['filter'].keys():
                    field_usage[field] += pattern.get('frequency', 1)
            
            # Count sort field usage
            if 'sort' in pattern:
                for field, _ in pattern['sort']:
                    sort_usage[field] += pattern.get('frequency', 1)
        
        # Generate recommendations
        for field, usage_count in field_usage.items():
            if usage_count > 10:  # Frequently queried field
                recommendations.append({
                    'collection': collection_name,
                    'index_type': 'single_field',
                    'fields': {field: 1},
                    'reason': f'Field {field} used in {usage_count} queries',
                    'priority': 'high' if usage_count > 50 else 'medium'
                })
        
        # Compound index recommendations
        frequent_combinations = []
        for pattern in query_patterns:
            if pattern.get('frequency', 0) > 20 and 'filter' in pattern:
                filter_fields = list(pattern['filter'].keys())
                if len(filter_fields) > 1:
                    frequent_combinations.append(tuple(sorted(filter_fields)))
        
        # Count combinations
        combination_counts = defaultdict(int)
        for combo in frequent_combinations:
            combination_counts[combo] += 1
        
        for combo, count in combination_counts.items():
            if count > 5:
                recommendations.append({
                    'collection': collection_name,
                    'index_type': 'compound',
                    'fields': {field: 1 for field in combo},
                    'reason': f'Field combination {combo} used in {count} query patterns',
                    'priority': 'high' if count > 15 else 'medium'
                })
        
        return recommendations

# Global optimizer instances
dynamodb_optimizer = DynamoDBOptimizer()
documentdb_optimizer = DocumentDBOptimizer()
query_recommendations = QueryOptimizationRecommendations()

# Utility functions for common optimizations
def optimize_pagination_query(query_func: callable, page_size: int = 20, 
                             max_pages: int = 100) -> callable:
    """Optimize pagination queries with intelligent prefetching"""
    @wraps(query_func)
    def wrapper(*args, **kwargs):
        # Extract pagination parameters
        page = kwargs.get('page', 1)
        requested_page_size = kwargs.get('page_size', page_size)
        
        # Optimize page size for better performance
        optimized_page_size = min(requested_page_size, 100)  # Cap at 100
        kwargs['page_size'] = optimized_page_size
        
        # Check if we should prefetch next page
        result = query_func(*args, **kwargs)
        
        # Add prefetching logic here if needed
        return result
    
    return wrapper

def create_query_cache_key(query_type: str, *args, **kwargs) -> str:
    """Create consistent cache key for query results"""
    # Remove sensitive or non-cacheable parameters
    cache_kwargs = kwargs.copy()
    cache_kwargs.pop('auth_token', None)
    cache_kwargs.pop('user_session', None)
    
    # Create deterministic key
    key_data = {
        'type': query_type,
        'args': args,
        'kwargs': cache_kwargs
    }
    
    key_string = json.dumps(key_data, sort_keys=True, default=str)
    import hashlib
    key_hash = hashlib.md5(key_string.encode()).hexdigest()[:12]
    
    return f"query_cache:{query_type}:{key_hash}"

def get_query_performance_report() -> Dict[str, Any]:
    """Get comprehensive query performance report"""
    stats = query_monitor.get_query_stats()
    slow_queries = query_monitor.get_slow_queries()
    error_queries = query_monitor.get_error_queries()
    recommendations = query_recommendations.analyze_query_patterns()
    
    return {
        'timestamp': datetime.utcnow().isoformat(),
        'query_statistics': stats,
        'slow_queries': slow_queries,
        'error_queries': error_queries,
        'recommendations': recommendations,
        'summary': {
            'total_query_types': len(stats),
            'total_slow_queries': len(slow_queries),
            'total_error_queries': len(error_queries),
            'avg_query_time': sum(s['avg_time'] for s in stats.values()) / len(stats) if stats else 0
        }
    }