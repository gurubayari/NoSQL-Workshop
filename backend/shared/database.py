"""
Database connection utilities for AWS NoSQL Workshop
Enhanced with connection pooling, query optimization, and error handling
"""
import boto3
import redis
from pymongo import MongoClient, ReadPreference
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError, OperationFailure
from botocore.exceptions import ClientError, BotoCoreError
from typing import Optional, Dict, Any, List, Union
import ssl
import logging
import time
import threading
from contextlib import contextmanager
from functools import wraps
import json
import os

try:
    from .config import config
except ImportError:
    from config import config

logger = logging.getLogger(__name__)

class ConnectionPool:
    """Enhanced connection pool with health monitoring and retry logic"""
    
    def __init__(self):
        self._lock = threading.Lock()
        self._connections = {}
        self._connection_health = {}
        self._retry_counts = {}
        self._max_retries = 3
        self._retry_delay = 1.0
    
    def _is_connection_healthy(self, conn_type: str) -> bool:
        """Check if connection is healthy"""
        try:
            if conn_type == 'documentdb' and self._connections.get('documentdb'):
                self._connections['documentdb'].admin.command('ping')
                return True
            elif conn_type == 'elasticache' and self._connections.get('elasticache'):
                self._connections['elasticache'].ping()
                return True
            elif conn_type == 'dynamodb' and self._connections.get('dynamodb'):
                # DynamoDB doesn't have a ping, so we'll assume it's healthy if it exists
                return True
        except Exception as e:
            logger.warning(f"Connection health check failed for {conn_type}: {e}")
            return False
        return False
    
    def _create_documentdb_connection(self):
        """Create DocumentDB connection with optimized settings"""
        try:
            # Check if SSL certificate file exists, use local one if available
            ssl_ca_file = None
            if os.path.exists(config.DOCUMENTDB_SSL_CA_CERTS):
                ssl_ca_file = config.DOCUMENTDB_SSL_CA_CERTS
            elif os.path.exists('./rds-ca-2019-root.pem'):
                ssl_ca_file = './rds-ca-2019-root.pem'
            
            # Build connection string
            if ssl_ca_file:
                connection_string = (
                    f"mongodb://{config.DOCUMENTDB_USERNAME}:{config.DOCUMENTDB_PASSWORD}"
                    f"@{config.DOCUMENTDB_HOST}:{config.DOCUMENTDB_PORT}/"
                    f"{config.DOCUMENTDB_DATABASE}?ssl=true&tlsCAFile={ssl_ca_file}"
                    f"&replicaSet=rs0&readPreference=secondaryPreferred&retryWrites=false"
                )
            else:
                # Fallback without SSL certificate file (less secure but may work for testing)
                logger.warning("SSL certificate file not found, connecting without certificate verification")
                connection_string = (
                    f"mongodb://{config.DOCUMENTDB_USERNAME}:{config.DOCUMENTDB_PASSWORD}"
                    f"@{config.DOCUMENTDB_HOST}:{config.DOCUMENTDB_PORT}/"
                    f"{config.DOCUMENTDB_DATABASE}?ssl=true&tlsAllowInvalidCertificates=true"
                    f"&replicaSet=rs0&readPreference=secondaryPreferred&retryWrites=false"
                )
            
            client = MongoClient(
                connection_string,
                read_preference=ReadPreference.SECONDARY_PREFERRED,
                # Connection pool settings
                maxPoolSize=50,
                minPoolSize=5,
                maxIdleTimeMS=30000,
                # Timeout settings
                serverSelectionTimeoutMS=5000,
                connectTimeoutMS=10000,
                socketTimeoutMS=20000,
                # Health monitoring
                heartbeatFrequencyMS=10000
            )
            
            # Test connection
            client.admin.command('ping')
            logger.info("DocumentDB connection pool established")
            return client
            
        except Exception as e:
            logger.error(f"Failed to create DocumentDB connection: {e}")
            raise
    
    def _create_elasticache_connection(self):
        """Create ElastiCache connection with connection pooling"""
        try:
            # Create connection pool
            pool = redis.ConnectionPool(
                host=config.ELASTICACHE_HOST,
                port=config.ELASTICACHE_PORT,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5,
                retry_on_timeout=True,
                max_connections=50,
                health_check_interval=30
            )
            
            client = redis.Redis(connection_pool=pool)
            
            # Test connection
            client.ping()
            logger.info("ElastiCache connection pool established")
            return client
            
        except Exception as e:
            logger.error(f"Failed to create ElastiCache connection: {e}")
            raise
    
    def _create_dynamodb_connection(self):
        """Create DynamoDB resource with optimized configuration"""
        try:
            # Configure boto3 session with connection pooling
            session = boto3.Session()
            
            # Create DynamoDB resource with custom config
            dynamodb = session.resource(
                'dynamodb',
                region_name=config.AWS_REGION,
                config=boto3.session.Config(
                    max_pool_connections=50,
                    retries={'max_attempts': 3, 'mode': 'adaptive'},
                    read_timeout=60,
                    connect_timeout=10
                )
            )
            
            logger.info("DynamoDB connection established")
            return dynamodb
            
        except Exception as e:
            logger.error(f"Failed to create DynamoDB connection: {e}")
            raise
    
    def get_connection(self, conn_type: str):
        """Get connection with health checking and retry logic"""
        with self._lock:
            # Check if we have a healthy connection
            if (conn_type in self._connections and 
                self._is_connection_healthy(conn_type)):
                return self._connections[conn_type]
            
            # Need to create or recreate connection
            retry_count = self._retry_counts.get(conn_type, 0)
            
            if retry_count >= self._max_retries:
                raise ConnectionError(f"Max retries exceeded for {conn_type}")
            
            try:
                if conn_type == 'documentdb':
                    self._connections[conn_type] = self._create_documentdb_connection()
                elif conn_type == 'elasticache':
                    self._connections[conn_type] = self._create_elasticache_connection()
                elif conn_type == 'dynamodb':
                    self._connections[conn_type] = self._create_dynamodb_connection()
                else:
                    raise ValueError(f"Unknown connection type: {conn_type}")
                
                # Reset retry count on successful connection
                self._retry_counts[conn_type] = 0
                self._connection_health[conn_type] = time.time()
                
                return self._connections[conn_type]
                
            except Exception as e:
                self._retry_counts[conn_type] = retry_count + 1
                logger.error(f"Connection attempt {retry_count + 1} failed for {conn_type}: {e}")
                
                if retry_count < self._max_retries - 1:
                    time.sleep(self._retry_delay * (2 ** retry_count))  # Exponential backoff
                
                raise
    
    def close_connections(self):
        """Close all connections"""
        with self._lock:
            for conn_type, connection in self._connections.items():
                try:
                    if conn_type == 'documentdb':
                        connection.close()
                    elif conn_type == 'elasticache':
                        connection.close()
                    # DynamoDB connections are managed by boto3
                    logger.info(f"Closed {conn_type} connection")
                except Exception as e:
                    logger.warning(f"Error closing {conn_type} connection: {e}")
            
            self._connections.clear()
            self._connection_health.clear()
            self._retry_counts.clear()

class DatabaseConnections:
    """Enhanced database connections with pooling and optimization"""
    
    _instance = None
    _pool = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(DatabaseConnections, cls).__new__(cls)
            cls._pool = ConnectionPool()
        return cls._instance
    
    @property
    def dynamodb(self):
        """Get DynamoDB resource with connection pooling"""
        return self._pool.get_connection('dynamodb')
    
    @property
    def documentdb(self):
        """Get DocumentDB client with connection pooling"""
        return self._pool.get_connection('documentdb')
    
    @property
    def elasticache(self):
        """Get ElastiCache Redis client with connection pooling"""
        return self._pool.get_connection('elasticache')
    
    def get_documentdb_database(self):
        """Get DocumentDB database instance"""
        return self.documentdb[config.DOCUMENTDB_DATABASE]
    
    def close_connections(self):
        """Close all database connections"""
        if self._pool:
            self._pool.close_connections()
        logger.info("All database connections closed")

# Global database connections instance
db = DatabaseConnections()

# Error handling decorators
def retry_on_connection_error(max_retries: int = 3, delay: float = 1.0, backoff: float = 2.0):
    """Decorator to retry database operations on connection errors"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except (ConnectionFailure, ServerSelectionTimeoutError, 
                       ClientError, BotoCoreError, redis.ConnectionError) as e:
                    last_exception = e
                    if attempt < max_retries - 1:
                        wait_time = delay * (backoff ** attempt)
                        logger.warning(f"Database operation failed (attempt {attempt + 1}/{max_retries}): {e}. Retrying in {wait_time}s...")
                        time.sleep(wait_time)
                    else:
                        logger.error(f"Database operation failed after {max_retries} attempts: {e}")
                except Exception as e:
                    # Don't retry on non-connection errors
                    logger.error(f"Database operation failed with non-retryable error: {e}")
                    raise
            
            raise last_exception
        return wrapper
    return decorator

def handle_database_errors(default_return=None):
    """Decorator to handle database errors gracefully"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                logger.error(f"Database error in {func.__name__}: {e}")
                return default_return
        return wrapper
    return decorator

# Enhanced DynamoDB helpers
@retry_on_connection_error()
def get_dynamodb_table(table_name: str):
    """Get DynamoDB table resource with retry logic"""
    return db.dynamodb.Table(table_name)

@retry_on_connection_error()
def dynamodb_query_with_pagination(table_name: str, key_condition_expression, 
                                  filter_expression=None, limit: int = None,
                                  last_evaluated_key=None, index_name=None,
                                  scan_index_forward=True) -> Dict[str, Any]:
    """Enhanced DynamoDB query with pagination and error handling"""
    table = get_dynamodb_table(table_name)
    
    query_params = {
        'KeyConditionExpression': key_condition_expression,
        'ScanIndexForward': scan_index_forward
    }
    
    if filter_expression:
        query_params['FilterExpression'] = filter_expression
    if limit:
        query_params['Limit'] = limit
    if last_evaluated_key:
        query_params['ExclusiveStartKey'] = last_evaluated_key
    if index_name:
        query_params['IndexName'] = index_name
    
    try:
        response = table.query(**query_params)
        return {
            'items': response.get('Items', []),
            'last_evaluated_key': response.get('LastEvaluatedKey'),
            'count': response.get('Count', 0),
            'scanned_count': response.get('ScannedCount', 0)
        }
    except Exception as e:
        logger.error(f"DynamoDB query failed for table {table_name}: {e}")
        raise

@retry_on_connection_error()
def dynamodb_batch_get_items(table_name: str, keys: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Batch get items from DynamoDB with retry logic"""
    if not keys:
        return []
    
    try:
        response = db.dynamodb.batch_get_item(
            RequestItems={
                table_name: {
                    'Keys': keys
                }
            }
        )
        return response.get('Responses', {}).get(table_name, [])
    except Exception as e:
        logger.error(f"DynamoDB batch get failed for table {table_name}: {e}")
        raise

@retry_on_connection_error()
def dynamodb_batch_write_items(table_name: str, items: List[Dict[str, Any]], 
                              operation: str = 'put') -> bool:
    """Batch write items to DynamoDB with retry logic"""
    if not items:
        return True
    
    try:
        # Process items in batches of 25 (DynamoDB limit)
        batch_size = 25
        for i in range(0, len(items), batch_size):
            batch = items[i:i + batch_size]
            
            if operation == 'put':
                request_items = [{'PutRequest': {'Item': item}} for item in batch]
            elif operation == 'delete':
                request_items = [{'DeleteRequest': {'Key': item}} for item in batch]
            else:
                raise ValueError(f"Unsupported operation: {operation}")
            
            db.dynamodb.batch_write_item(
                RequestItems={
                    table_name: request_items
                }
            )
        
        return True
    except Exception as e:
        logger.error(f"DynamoDB batch write failed for table {table_name}: {e}")
        raise

# Enhanced DocumentDB helpers
@retry_on_connection_error()
def get_documentdb_collection(collection_name: str):
    """Get DocumentDB collection with retry logic"""
    database = db.get_documentdb_database()
    return database[collection_name]

@retry_on_connection_error()
def documentdb_find_with_pagination(collection_name: str, filter_query: Dict = None,
                                   projection: Dict = None, sort: List = None,
                                   page: int = 1, page_size: int = 20) -> Dict[str, Any]:
    """Enhanced DocumentDB find with pagination"""
    collection = get_documentdb_collection(collection_name)
    
    filter_query = filter_query or {}
    skip = (page - 1) * page_size
    
    try:
        # Build query
        cursor = collection.find(filter_query, projection)
        
        if sort:
            cursor = cursor.sort(sort)
        
        # Get total count for pagination
        total_count = collection.count_documents(filter_query)
        
        # Apply pagination
        items = list(cursor.skip(skip).limit(page_size))
        
        return {
            'items': items,
            'total_count': total_count,
            'page': page,
            'page_size': page_size,
            'total_pages': (total_count + page_size - 1) // page_size,
            'has_next': page * page_size < total_count,
            'has_prev': page > 1
        }
    except Exception as e:
        logger.error(f"DocumentDB find failed for collection {collection_name}: {e}")
        raise

@retry_on_connection_error()
def documentdb_aggregate_with_pagination(collection_name: str, pipeline: List[Dict],
                                        page: int = 1, page_size: int = 20) -> Dict[str, Any]:
    """Enhanced DocumentDB aggregation with pagination"""
    collection = get_documentdb_collection(collection_name)
    
    try:
        # Add pagination to pipeline
        paginated_pipeline = pipeline.copy()
        
        # Add count stage for total
        count_pipeline = pipeline + [{'$count': 'total'}]
        count_result = list(collection.aggregate(count_pipeline))
        total_count = count_result[0]['total'] if count_result else 0
        
        # Add skip and limit for pagination
        skip = (page - 1) * page_size
        paginated_pipeline.extend([
            {'$skip': skip},
            {'$limit': page_size}
        ])
        
        items = list(collection.aggregate(paginated_pipeline))
        
        return {
            'items': items,
            'total_count': total_count,
            'page': page,
            'page_size': page_size,
            'total_pages': (total_count + page_size - 1) // page_size,
            'has_next': page * page_size < total_count,
            'has_prev': page > 1
        }
    except Exception as e:
        logger.error(f"DocumentDB aggregation failed for collection {collection_name}: {e}")
        raise

@retry_on_connection_error()
def documentdb_vector_search(collection_name: str, vector: List[float], 
                           vector_field: str = 'embedding', limit: int = 10,
                           filter_query: Dict = None) -> List[Dict[str, Any]]:
    """Perform vector search in DocumentDB"""
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
                        'k': limit,
                        'filter': filter_query or {}
                    }
                }
            },
            {
                '$addFields': {
                    'score': {'$meta': 'vectorSearchScore'}
                }
            }
        ]
        
        results = list(collection.aggregate(pipeline))
        return results
    except Exception as e:
        logger.error(f"DocumentDB vector search failed for collection {collection_name}: {e}")
        raise

# Enhanced ElastiCache helpers
def get_cache_key(prefix: str, identifier: str) -> str:
    """Generate cache key with prefix"""
    return f"{config.PROJECT_NAME}:{config.ENVIRONMENT}:{prefix}:{identifier}"

@retry_on_connection_error()
@handle_database_errors(default_return=None)
def cache_get(key: str) -> Optional[str]:
    """Get value from cache with retry logic"""
    return db.elasticache.get(key)

@retry_on_connection_error()
@handle_database_errors(default_return=False)
def cache_set(key: str, value: str, ttl: int = None) -> bool:
    """Set value in cache with TTL and retry logic"""
    ttl = ttl or config.CACHE_TTL_SECONDS
    return db.elasticache.setex(key, ttl, value)

@retry_on_connection_error()
@handle_database_errors(default_return=False)
def cache_delete(key: str) -> bool:
    """Delete value from cache with retry logic"""
    return bool(db.elasticache.delete(key))

@retry_on_connection_error()
@handle_database_errors(default_return=[])
def cache_get_multiple(keys: List[str]) -> List[Optional[str]]:
    """Get multiple values from cache"""
    if not keys:
        return []
    return db.elasticache.mget(keys)

@retry_on_connection_error()
@handle_database_errors(default_return=False)
def cache_set_multiple(key_value_pairs: Dict[str, str], ttl: int = None) -> bool:
    """Set multiple values in cache"""
    if not key_value_pairs:
        return True
    
    ttl = ttl or config.CACHE_TTL_SECONDS
    pipe = db.elasticache.pipeline()
    
    for key, value in key_value_pairs.items():
        pipe.setex(key, ttl, value)
    
    results = pipe.execute()
    return all(results)

@retry_on_connection_error()
@handle_database_errors(default_return=0)
def cache_delete_pattern(pattern: str) -> int:
    """Delete all keys matching pattern"""
    keys = db.elasticache.keys(pattern)
    if keys:
        return db.elasticache.delete(*keys)
    return 0

# Context managers for database operations
@contextmanager
def documentdb_transaction():
    """Context manager for DocumentDB transactions"""
    client = db.documentdb
    session = client.start_session()
    
    try:
        with session.start_transaction():
            yield session
    except Exception as e:
        logger.error(f"DocumentDB transaction failed: {e}")
        raise
    finally:
        session.end_session()

@contextmanager
def elasticache_pipeline():
    """Context manager for ElastiCache pipeline operations"""
    pipe = db.elasticache.pipeline()
    
    try:
        yield pipe
        pipe.execute()
    except Exception as e:
        logger.error(f"ElastiCache pipeline failed: {e}")
        raise

# Database health check utilities
def check_database_health() -> Dict[str, bool]:
    """Check health of all database connections"""
    health_status = {}
    
    # Check DynamoDB
    try:
        db.dynamodb.meta.client.describe_limits()
        health_status['dynamodb'] = True
    except Exception as e:
        logger.error(f"DynamoDB health check failed: {e}")
        health_status['dynamodb'] = False
    
    # Check DocumentDB
    try:
        db.documentdb.admin.command('ping')
        health_status['documentdb'] = True
    except Exception as e:
        logger.error(f"DocumentDB health check failed: {e}")
        health_status['documentdb'] = False
    
    # Check ElastiCache
    try:
        db.elasticache.ping()
        health_status['elasticache'] = True
    except Exception as e:
        logger.error(f"ElastiCache health check failed: {e}")
        health_status['elasticache'] = False
    
    return health_status

def get_database_stats() -> Dict[str, Any]:
    """Get database connection and performance statistics"""
    stats = {}
    
    try:
        # ElastiCache stats
        redis_info = db.elasticache.info()
        stats['elasticache'] = {
            'connected_clients': redis_info.get('connected_clients', 0),
            'used_memory': redis_info.get('used_memory_human', '0B'),
            'keyspace_hits': redis_info.get('keyspace_hits', 0),
            'keyspace_misses': redis_info.get('keyspace_misses', 0),
            'hit_rate': redis_info.get('keyspace_hits', 0) / max(
                redis_info.get('keyspace_hits', 0) + redis_info.get('keyspace_misses', 0), 1
            )
        }
    except Exception as e:
        logger.warning(f"Failed to get ElastiCache stats: {e}")
        stats['elasticache'] = {}
    
    try:
        # DocumentDB stats
        db_stats = db.get_documentdb_database().command('dbStats')
        stats['documentdb'] = {
            'collections': db_stats.get('collections', 0),
            'objects': db_stats.get('objects', 0),
            'data_size': db_stats.get('dataSize', 0),
            'storage_size': db_stats.get('storageSize', 0)
        }
    except Exception as e:
        logger.warning(f"Failed to get DocumentDB stats: {e}")
        stats['documentdb'] = {}
    
    return stats