"""
Advanced pagination utilities for AWS NoSQL Workshop
Provides efficient pagination patterns for DynamoDB, DocumentDB, and cached results
"""
import logging
import json
import base64
from typing import Any, Dict, List, Optional, Tuple, Union, Callable
from datetime import datetime
from dataclasses import dataclass
import hashlib

try:
    from .database import db, get_dynamodb_table, get_documentdb_collection
    from .cache_manager import cache_manager
    from .config import config
except ImportError:
    from database import db, get_dynamodb_table, get_documentdb_collection
    from cache_manager import cache_manager
    from config import config

logger = logging.getLogger(__name__)

@dataclass
class PaginationResult:
    """Standardized pagination result structure"""
    items: List[Dict[str, Any]]
    total_count: Optional[int] = None
    page: int = 1
    page_size: int = 20
    has_next: bool = False
    has_prev: bool = False
    next_token: Optional[str] = None
    prev_token: Optional[str] = None
    total_pages: Optional[int] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses"""
        result = {
            'items': self.items,
            'page': self.page,
            'page_size': self.page_size,
            'has_next': self.has_next,
            'has_prev': self.has_prev,
            'item_count': len(self.items)
        }
        
        if self.total_count is not None:
            result['total_count'] = self.total_count
        if self.total_pages is not None:
            result['total_pages'] = self.total_pages
        if self.next_token:
            result['next_token'] = self.next_token
        if self.prev_token:
            result['prev_token'] = self.prev_token
            
        return result

class PaginationTokenManager:
    """Manage pagination tokens for stateless pagination"""
    
    @staticmethod
    def encode_token(data: Dict[str, Any]) -> str:
        """Encode pagination data into a token"""
        try:
            json_str = json.dumps(data, sort_keys=True, default=str)
            encoded = base64.urlsafe_b64encode(json_str.encode()).decode()
            return encoded
        except Exception as e:
            logger.error(f"Failed to encode pagination token: {e}")
            return ""
    
    @staticmethod
    def decode_token(token: str) -> Dict[str, Any]:
        """Decode pagination token back to data"""
        try:
            decoded = base64.urlsafe_b64decode(token.encode()).decode()
            return json.loads(decoded)
        except Exception as e:
            logger.error(f"Failed to decode pagination token: {e}")
            return {}
    
    @staticmethod
    def create_dynamodb_token(last_evaluated_key: Dict[str, Any], 
                             page: int, page_size: int) -> str:
        """Create token for DynamoDB pagination"""
        token_data = {
            'type': 'dynamodb',
            'last_evaluated_key': last_evaluated_key,
            'page': page,
            'page_size': page_size,
            'timestamp': datetime.utcnow().isoformat()
        }
        return PaginationTokenManager.encode_token(token_data)
    
    @staticmethod
    def create_documentdb_token(skip: int, page: int, page_size: int) -> str:
        """Create token for DocumentDB pagination"""
        token_data = {
            'type': 'documentdb',
            'skip': skip,
            'page': page,
            'page_size': page_size,
            'timestamp': datetime.utcnow().isoformat()
        }
        return PaginationTokenManager.encode_token(token_data)

class DynamoDBPaginator:
    """Advanced pagination for DynamoDB operations"""
    
    def __init__(self, table_name: str):
        self.table_name = table_name
        self.table = get_dynamodb_table(table_name)
    
    def paginate_query(self, key_condition_expression, filter_expression=None,
                      index_name: Optional[str] = None, page_size: int = 20,
                      next_token: Optional[str] = None, scan_index_forward: bool = True,
                      consistent_read: bool = False) -> PaginationResult:
        """Paginate DynamoDB query results"""
        try:
            # Decode next token if provided
            last_evaluated_key = None
            current_page = 1
            
            if next_token:
                token_data = PaginationTokenManager.decode_token(next_token)
                if token_data.get('type') == 'dynamodb':
                    last_evaluated_key = token_data.get('last_evaluated_key')
                    current_page = token_data.get('page', 1) + 1
            
            # Build query parameters
            query_params = {
                'KeyConditionExpression': key_condition_expression,
                'Limit': page_size,
                'ScanIndexForward': scan_index_forward,
                'ConsistentRead': consistent_read
            }
            
            if filter_expression:
                query_params['FilterExpression'] = filter_expression
            if index_name:
                query_params['IndexName'] = index_name
            if last_evaluated_key:
                query_params['ExclusiveStartKey'] = last_evaluated_key
            
            # Execute query
            response = self.table.query(**query_params)
            
            items = response.get('Items', [])
            new_last_evaluated_key = response.get('LastEvaluatedKey')
            
            # Create pagination result
            result = PaginationResult(
                items=items,
                page=current_page,
                page_size=page_size,
                has_prev=current_page > 1,
                has_next=new_last_evaluated_key is not None
            )
            
            # Create next token if there are more results
            if new_last_evaluated_key:
                result.next_token = PaginationTokenManager.create_dynamodb_token(
                    new_last_evaluated_key, current_page, page_size
                )
            
            return result
            
        except Exception as e:
            logger.error(f"DynamoDB pagination failed for table {self.table_name}: {e}")
            raise
    
    def paginate_scan(self, filter_expression=None, index_name: Optional[str] = None,
                     page_size: int = 20, next_token: Optional[str] = None,
                     consistent_read: bool = False) -> PaginationResult:
        """Paginate DynamoDB scan results"""
        try:
            # Decode next token if provided
            last_evaluated_key = None
            current_page = 1
            
            if next_token:
                token_data = PaginationTokenManager.decode_token(next_token)
                if token_data.get('type') == 'dynamodb':
                    last_evaluated_key = token_data.get('last_evaluated_key')
                    current_page = token_data.get('page', 1) + 1
            
            # Build scan parameters
            scan_params = {
                'Limit': page_size,
                'ConsistentRead': consistent_read
            }
            
            if filter_expression:
                scan_params['FilterExpression'] = filter_expression
            if index_name:
                scan_params['IndexName'] = index_name
            if last_evaluated_key:
                scan_params['ExclusiveStartKey'] = last_evaluated_key
            
            # Execute scan
            response = self.table.scan(**scan_params)
            
            items = response.get('Items', [])
            new_last_evaluated_key = response.get('LastEvaluatedKey')
            
            # Create pagination result
            result = PaginationResult(
                items=items,
                page=current_page,
                page_size=page_size,
                has_prev=current_page > 1,
                has_next=new_last_evaluated_key is not None
            )
            
            # Create next token if there are more results
            if new_last_evaluated_key:
                result.next_token = PaginationTokenManager.create_dynamodb_token(
                    new_last_evaluated_key, current_page, page_size
                )
            
            return result
            
        except Exception as e:
            logger.error(f"DynamoDB scan pagination failed for table {self.table_name}: {e}")
            raise

class DocumentDBPaginator:
    """Advanced pagination for DocumentDB operations"""
    
    def __init__(self, collection_name: str):
        self.collection_name = collection_name
        self.collection = get_documentdb_collection(collection_name)
    
    def paginate_find(self, filter_query: Optional[Dict[str, Any]] = None,
                     projection: Optional[Dict[str, Any]] = None,
                     sort: Optional[List[Tuple[str, int]]] = None,
                     page: int = 1, page_size: int = 20,
                     count_total: bool = True) -> PaginationResult:
        """Paginate DocumentDB find results with total count"""
        try:
            filter_query = filter_query or {}
            skip = (page - 1) * page_size
            
            # Build cursor
            cursor = self.collection.find(filter_query, projection)
            
            if sort:
                cursor = cursor.sort(sort)
            
            # Get total count if requested (can be expensive for large collections)
            total_count = None
            total_pages = None
            
            if count_total:
                total_count = self.collection.count_documents(filter_query)
                total_pages = (total_count + page_size - 1) // page_size
            
            # Apply pagination
            items = list(cursor.skip(skip).limit(page_size))
            
            # Create pagination result
            result = PaginationResult(
                items=items,
                total_count=total_count,
                page=page,
                page_size=page_size,
                total_pages=total_pages,
                has_next=len(items) == page_size,  # Approximate
                has_prev=page > 1
            )
            
            # More accurate has_next if we have total count
            if total_count is not None:
                result.has_next = page * page_size < total_count
            
            return result
            
        except Exception as e:
            logger.error(f"DocumentDB find pagination failed for collection {self.collection_name}: {e}")
            raise
    
    def paginate_aggregate(self, pipeline: List[Dict[str, Any]], 
                          page: int = 1, page_size: int = 20,
                          count_total: bool = False) -> PaginationResult:
        """Paginate DocumentDB aggregation results"""
        try:
            skip = (page - 1) * page_size
            
            # Create paginated pipeline
            paginated_pipeline = pipeline.copy()
            paginated_pipeline.extend([
                {'$skip': skip},
                {'$limit': page_size}
            ])
            
            # Execute aggregation
            items = list(self.collection.aggregate(paginated_pipeline))
            
            # Get total count if requested
            total_count = None
            total_pages = None
            
            if count_total:
                count_pipeline = pipeline + [{'$count': 'total'}]
                count_result = list(self.collection.aggregate(count_pipeline))
                total_count = count_result[0]['total'] if count_result else 0
                total_pages = (total_count + page_size - 1) // page_size
            
            # Create pagination result
            result = PaginationResult(
                items=items,
                total_count=total_count,
                page=page,
                page_size=page_size,
                total_pages=total_pages,
                has_next=len(items) == page_size,  # Approximate
                has_prev=page > 1
            )
            
            # More accurate has_next if we have total count
            if total_count is not None:
                result.has_next = page * page_size < total_count
            
            return result
            
        except Exception as e:
            logger.error(f"DocumentDB aggregation pagination failed for collection {self.collection_name}: {e}")
            raise
    
    def paginate_vector_search(self, vector: List[float], vector_field: str = 'embedding',
                              limit: int = 10, filter_query: Optional[Dict[str, Any]] = None,
                              page: int = 1, page_size: int = 10) -> PaginationResult:
        """Paginate vector search results"""
        try:
            # Vector search doesn't support traditional skip/limit pagination
            # We'll use limit and manual pagination
            total_limit = page * page_size
            skip = (page - 1) * page_size
            
            # Build vector search pipeline
            pipeline = [
                {
                    '$search': {
                        'vectorSearch': {
                            'vector': vector,
                            'path': vector_field,
                            'similarity': 'cosine',
                            'k': total_limit
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
            
            # Execute search
            all_results = list(self.collection.aggregate(pipeline))
            
            # Manual pagination
            items = all_results[skip:skip + page_size]
            
            # Create pagination result
            result = PaginationResult(
                items=items,
                page=page,
                page_size=page_size,
                has_next=len(all_results) > skip + page_size,
                has_prev=page > 1,
                total_count=len(all_results)
            )
            
            return result
            
        except Exception as e:
            logger.error(f"DocumentDB vector search pagination failed for collection {self.collection_name}: {e}")
            raise

class CachedPaginator:
    """Pagination with intelligent caching"""
    
    def __init__(self, cache_prefix: str, cache_ttl: int = 1800):
        self.cache_prefix = cache_prefix
        self.cache_ttl = cache_ttl
    
    def _generate_cache_key(self, query_hash: str, page: int, page_size: int) -> str:
        """Generate cache key for paginated results"""
        return f"{self.cache_prefix}:page:{query_hash}:{page}:{page_size}"
    
    def _generate_query_hash(self, query_params: Dict[str, Any]) -> str:
        """Generate hash for query parameters"""
        query_str = json.dumps(query_params, sort_keys=True, default=str)
        return hashlib.md5(query_str.encode()).hexdigest()[:12]
    
    def paginate_with_cache(self, query_func: Callable, query_params: Dict[str, Any],
                           page: int = 1, page_size: int = 20,
                           cache_individual_pages: bool = True) -> PaginationResult:
        """Paginate with caching support"""
        try:
            query_hash = self._generate_query_hash(query_params)
            cache_key = self._generate_cache_key(query_hash, page, page_size)
            
            # Try to get from cache first
            if cache_individual_pages:
                cached_result = cache_manager.get(cache_key)
                if cached_result:
                    logger.debug(f"Cache hit for paginated query: {cache_key}")
                    return PaginationResult(**cached_result)
            
            # Execute query function
            result = query_func(**query_params, page=page, page_size=page_size)
            
            # Cache the result
            if cache_individual_pages and isinstance(result, PaginationResult):
                cache_data = result.to_dict()
                cache_manager.set(cache_key, cache_data, self.cache_ttl)
                logger.debug(f"Cached paginated result: {cache_key}")
            
            return result
            
        except Exception as e:
            logger.error(f"Cached pagination failed: {e}")
            raise
    
    def invalidate_query_cache(self, query_params: Dict[str, Any]):
        """Invalidate all cached pages for a query"""
        query_hash = self._generate_query_hash(query_params)
        pattern = f"{self.cache_prefix}:page:{query_hash}:*"
        deleted_count = cache_manager.delete_pattern(pattern)
        logger.debug(f"Invalidated {deleted_count} cached pages for query")

class SmartPaginator:
    """Intelligent paginator that chooses optimal strategy"""
    
    def __init__(self):
        self.dynamodb_paginators = {}
        self.documentdb_paginators = {}
        self.cached_paginators = {}
    
    def get_dynamodb_paginator(self, table_name: str) -> DynamoDBPaginator:
        """Get or create DynamoDB paginator"""
        if table_name not in self.dynamodb_paginators:
            self.dynamodb_paginators[table_name] = DynamoDBPaginator(table_name)
        return self.dynamodb_paginators[table_name]
    
    def get_documentdb_paginator(self, collection_name: str) -> DocumentDBPaginator:
        """Get or create DocumentDB paginator"""
        if collection_name not in self.documentdb_paginators:
            self.documentdb_paginators[collection_name] = DocumentDBPaginator(collection_name)
        return self.documentdb_paginators[collection_name]
    
    def get_cached_paginator(self, cache_prefix: str, cache_ttl: int = 1800) -> CachedPaginator:
        """Get or create cached paginator"""
        cache_key = f"{cache_prefix}:{cache_ttl}"
        if cache_key not in self.cached_paginators:
            self.cached_paginators[cache_key] = CachedPaginator(cache_prefix, cache_ttl)
        return self.cached_paginators[cache_key]
    
    def auto_paginate(self, data_source: str, source_name: str, 
                     operation: str, **kwargs) -> PaginationResult:
        """Automatically choose and execute optimal pagination strategy"""
        try:
            if data_source == 'dynamodb':
                paginator = self.get_dynamodb_paginator(source_name)
                
                if operation == 'query':
                    return paginator.paginate_query(**kwargs)
                elif operation == 'scan':
                    return paginator.paginate_scan(**kwargs)
                else:
                    raise ValueError(f"Unsupported DynamoDB operation: {operation}")
            
            elif data_source == 'documentdb':
                paginator = self.get_documentdb_paginator(source_name)
                
                if operation == 'find':
                    return paginator.paginate_find(**kwargs)
                elif operation == 'aggregate':
                    return paginator.paginate_aggregate(**kwargs)
                elif operation == 'vector_search':
                    return paginator.paginate_vector_search(**kwargs)
                else:
                    raise ValueError(f"Unsupported DocumentDB operation: {operation}")
            
            else:
                raise ValueError(f"Unsupported data source: {data_source}")
                
        except Exception as e:
            logger.error(f"Auto pagination failed for {data_source}.{source_name}.{operation}: {e}")
            raise

# Global paginator instance
smart_paginator = SmartPaginator()

# Utility functions
def paginate_dynamodb_query(table_name: str, **kwargs) -> PaginationResult:
    """Convenience function for DynamoDB query pagination"""
    return smart_paginator.auto_paginate('dynamodb', table_name, 'query', **kwargs)

def paginate_documentdb_find(collection_name: str, **kwargs) -> PaginationResult:
    """Convenience function for DocumentDB find pagination"""
    return smart_paginator.auto_paginate('documentdb', collection_name, 'find', **kwargs)

def paginate_with_cache(cache_prefix: str, query_func: Callable, 
                       query_params: Dict[str, Any], **kwargs) -> PaginationResult:
    """Convenience function for cached pagination"""
    cached_paginator = smart_paginator.get_cached_paginator(cache_prefix)
    return cached_paginator.paginate_with_cache(query_func, query_params, **kwargs)