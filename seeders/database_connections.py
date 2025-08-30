"""
Common Database Connection Handler for Unicorn E-Commerce Seeders
Provides centralized connection management for DocumentDB, DynamoDB, and ElastiCache
"""
import os
import sys
from typing import Optional, Dict, Any
from urllib.parse import quote_plus

# Check for required dependencies
try:
    import pymongo
    from pymongo import MongoClient
    PYMONGO_AVAILABLE = True
except ImportError:
    PYMONGO_AVAILABLE = False

try:
    import boto3
    from botocore.exceptions import ClientError
    BOTO3_AVAILABLE = True
except ImportError:
    BOTO3_AVAILABLE = False

try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False


class DatabaseConnections:
    """Centralized database connection manager"""
    
    def __init__(self):
        self.documentdb_client = None
        self.documentdb_db = None
        self.dynamodb_resource = None
        self.elasticache_client = None
        self._region = None
        self._database_name = None
    
    def get_documentdb_connection(self):
        """Get DocumentDB connection and database"""
        if self.documentdb_client is None:
            self._connect_to_documentdb()
        return self.documentdb_client, self.documentdb_db
    
    def get_documentdb_collection(self, collection_name: str):
        """Get a specific DocumentDB collection"""
        client, db = self.get_documentdb_connection()
        return db[collection_name]
    
    def get_dynamodb_table(self, table_env_var: str):
        """Get DynamoDB table using environment variable name"""
        if self.dynamodb_resource is None:
            self._connect_to_dynamodb()
        
        table_name = os.environ.get(table_env_var)
        if not table_name:
            print(f"ERROR: Missing required DynamoDB table environment variable: {table_env_var}")
            sys.exit(1)
        
        try:
            table = self.dynamodb_resource.Table(table_name)
            # Test the connection by describing the table
            table_description = table.meta.client.describe_table(TableName=table_name)
            print(f"✅ Connected to DynamoDB table: {table_name}")
            print(f"   Table status: {table_description['Table']['TableStatus']}")
            return table
        except Exception as e:
            print(f"ERROR: Failed to connect to DynamoDB table {table_name}: {e}")
            sys.exit(1)
    
    def get_elasticache_connection(self):
        """Get ElastiCache Redis connection"""
        if self.elasticache_client is None:
            self._connect_to_elasticache()
        return self.elasticache_client
    
    def _connect_to_documentdb(self):
        """Connect to DocumentDB using environment variables"""
        if not PYMONGO_AVAILABLE:
            print("ERROR: pymongo is required but not available")
            print("Please install pymongo: pip install pymongo")
            sys.exit(1)
        
        # Get connection details from environment variables
        host = os.environ.get('DOCUMENTDB_HOST')
        port = os.environ.get('DOCUMENTDB_PORT', '27017')
        username = os.environ.get('DOCUMENTDB_USERNAME')
        password = os.environ.get('DOCUMENTDB_PASSWORD')
        database = os.environ.get('DOCUMENTDB_DATABASE', 'unicorn_ecommerce_dev')
        ssl_ca_certs = os.environ.get('DOCUMENTDB_SSL_CA_CERTS')
        
        if not all([host, username, password]):
            print("ERROR: Missing required DocumentDB environment variables:")
            print("  DOCUMENTDB_HOST:", "✓" if host else "✗ Missing")
            print("  DOCUMENTDB_USERNAME:", "✓" if username else "✗ Missing") 
            print("  DOCUMENTDB_PASSWORD:", "✓" if password else "✗ Missing")
            print("\nPlease ensure the environment variables are set correctly.")
            sys.exit(1)
        
        try:
            # URL encode username and password to handle special characters
            encoded_username = quote_plus(username)
            encoded_password = quote_plus(password)
            
            # Build connection string with properly encoded credentials and TLS settings
            connection_string = f'mongodb://{encoded_username}:{encoded_password}@{host}:{port}/{database}?tls=true&tlsAllowInvalidCertificates=true&replicaSet=rs0&readPreference=secondaryPreferred&retryWrites=false'
            
            print(f"Connecting to DocumentDB at {host}:{port}")
            
            # Prepare connection options
            connection_options = {
                'serverSelectionTimeoutMS': 10000,  # 10 second timeout
                'connectTimeoutMS': 10000,
                'socketTimeoutMS': 10000
            }
            
            # Add SSL CA certificate file if provided
            if ssl_ca_certs:
                connection_options['tlsCAFile'] = ssl_ca_certs
                print(f"Using SSL CA certificate file: {ssl_ca_certs}")
            
            # Connect to DocumentDB
            self.documentdb_client = MongoClient(
                connection_string,
                **connection_options
            )
            
            # Test the connection
            self.documentdb_client.admin.command('ping')
            
            # Set up database
            self.documentdb_db = self.documentdb_client[database]
            self._database_name = database
            
            print(f"✅ Successfully connected to DocumentDB database: {database}")
            
        except Exception as e:
            print(f"ERROR: Failed to connect to DocumentDB: {e}")
            print(f"Connection details:")
            print(f"  Host: {host}")
            print(f"  Port: {port}")
            print(f"  Database: {database}")
            print(f"  Username: {username}")
            print(f"  SSL CA Certs: {ssl_ca_certs}")
            sys.exit(1)
    
    def _connect_to_dynamodb(self):
        """Connect to DynamoDB using environment variables"""
        if not BOTO3_AVAILABLE:
            print("ERROR: boto3 is required but not available")
            print("Please install boto3: pip install boto3")
            sys.exit(1)
        
        # Get connection details from environment variables
        region = os.environ.get('AWS_REGION', os.environ.get('AWS_DEFAULT_REGION'))
        
        if not region:
            print("ERROR: Missing required AWS region environment variable:")
            print("  AWS_REGION or AWS_DEFAULT_REGION must be set")
            sys.exit(1)
        
        try:
            print(f"Connecting to DynamoDB in region: {region}")
            
            # Connect to DynamoDB
            self.dynamodb_resource = boto3.resource('dynamodb', region_name=region)
            self._region = region
            
            print(f"✅ Successfully connected to DynamoDB in region: {region}")
            
        except Exception as e:
            print(f"ERROR: Failed to connect to DynamoDB: {e}")
            print(f"Connection details:")
            print(f"  Region: {region}")
            sys.exit(1)
    
    def _connect_to_elasticache(self):
        """Connect to ElastiCache Redis using environment variables"""
        if not REDIS_AVAILABLE:
            print("ERROR: redis is required but not available")
            print("Please install redis: pip install redis")
            sys.exit(1)
        
        # Get connection details from environment variables
        host = os.environ.get('ELASTICACHE_HOST')
        port = os.environ.get('ELASTICACHE_PORT', '6379')
        
        if not host:
            print("ERROR: Missing required ElastiCache environment variables:")
            print("  ELASTICACHE_HOST:", "✓" if host else "✗ Missing")
            print("\nPlease ensure the environment variables are set correctly.")
            sys.exit(1)
        
        try:
            print(f"Connecting to ElastiCache at {host}:{port}")
            
            # Connect to ElastiCache Redis
            self.elasticache_client = redis.Redis(
                host=host,
                port=int(port),
                decode_responses=True,
                socket_connect_timeout=10,
                socket_timeout=10
            )
            
            # Test the connection
            self.elasticache_client.ping()
            
            print(f"✅ Successfully connected to ElastiCache: {host}:{port}")
            
        except Exception as e:
            print(f"ERROR: Failed to connect to ElastiCache: {e}")
            print(f"Connection details:")
            print(f"  Host: {host}")
            print(f"  Port: {port}")
            sys.exit(1)
    
    def close_connections(self):
        """Close all database connections"""
        if self.documentdb_client:
            self.documentdb_client.close()
            print("DocumentDB connection closed")
        
        if self.elasticache_client:
            self.elasticache_client.close()
            print("ElastiCache connection closed")
        
        # DynamoDB resource doesn't need explicit closing
        print("All database connections closed")
    
    def test_all_connections(self):
        """Test all database connections"""
        print("Testing all database connections...")
        
        try:
            # Test DocumentDB
            client, db = self.get_documentdb_connection()
            client.admin.command('ping')
            print("✅ DocumentDB connection test: PASSED")
        except Exception as e:
            print(f"❌ DocumentDB connection test: FAILED - {e}")
        
        try:
            # Test DynamoDB (we'll test with a common table)
            if os.environ.get('INVENTORY_TABLE'):
                table = self.get_dynamodb_table('INVENTORY_TABLE')
                print("✅ DynamoDB connection test: PASSED")
        except Exception as e:
            print(f"❌ DynamoDB connection test: FAILED - {e}")
        
        try:
            # Test ElastiCache
            redis_client = self.get_elasticache_connection()
            redis_client.ping()
            print("✅ ElastiCache connection test: PASSED")
        except Exception as e:
            print(f"❌ ElastiCache connection test: FAILED - {e}")


# Global instance for reuse across seeders
db_connections = DatabaseConnections()


def get_documentdb_collection(collection_name: str):
    """Convenience function to get DocumentDB collection"""
    return db_connections.get_documentdb_collection(collection_name)


def get_dynamodb_table(table_env_var: str):
    """Convenience function to get DynamoDB table"""
    return db_connections.get_dynamodb_table(table_env_var)


def get_elasticache_client():
    """Convenience function to get ElastiCache client"""
    return db_connections.get_elasticache_connection()


def close_all_connections():
    """Convenience function to close all connections"""
    db_connections.close_connections()


def test_all_connections():
    """Convenience function to test all connections"""
    db_connections.test_all_connections()


# Context manager for automatic connection cleanup
class DatabaseConnectionManager:
    """Context manager for database connections with automatic cleanup"""
    
    def __enter__(self):
        return db_connections
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        db_connections.close_connections()


if __name__ == "__main__":
    # Test script
    print("Testing database connections...")
    test_all_connections()