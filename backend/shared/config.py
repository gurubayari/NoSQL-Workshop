"""
Configuration settings for AWS NoSQL Workshop backend
"""
import os
from typing import Optional

class Config:
    """Application configuration"""
    
    # Environment
    ENVIRONMENT = os.getenv('ENVIRONMENT', 'dev')
    PROJECT_NAME = os.getenv('PROJECT_NAME', 'unicorn-ecommerce')
    
    # AWS Configuration
    AWS_REGION = os.getenv('AWS_REGION', 'us-west-2')
    
    # DynamoDB Tables
    USERS_TABLE = os.getenv('USERS_TABLE', f'{PROJECT_NAME}-{ENVIRONMENT}-users')
    SHOPPING_CART_TABLE = os.getenv('SHOPPING_CART_TABLE', f'{PROJECT_NAME}-{ENVIRONMENT}-shopping-cart')
    INVENTORY_TABLE = os.getenv('INVENTORY_TABLE', f'{PROJECT_NAME}-{ENVIRONMENT}-inventory')
    ORDERS_TABLE = os.getenv('ORDERS_TABLE', f'{PROJECT_NAME}-{ENVIRONMENT}-orders')
    CHAT_HISTORY_TABLE = os.getenv('CHAT_HISTORY_TABLE', f'{PROJECT_NAME}-{ENVIRONMENT}-chat-history')
    SEARCH_ANALYTICS_TABLE = os.getenv('SEARCH_ANALYTICS_TABLE', f'{PROJECT_NAME}-{ENVIRONMENT}-search-analytics')
    
    # DocumentDB Configuration
    DOCUMENTDB_HOST = os.getenv('DOCUMENTDB_HOST')
    DOCUMENTDB_PORT = int(os.getenv('DOCUMENTDB_PORT', '27017'))
    DOCUMENTDB_USERNAME = os.getenv('DOCUMENTDB_USERNAME')
    DOCUMENTDB_PASSWORD = os.getenv('DOCUMENTDB_PASSWORD')
    DOCUMENTDB_DATABASE = os.getenv('DOCUMENTDB_DATABASE', f'{PROJECT_NAME}_{ENVIRONMENT}')
    DOCUMENTDB_SSL_CA_CERTS = os.getenv('DOCUMENTDB_SSL_CA_CERTS', '/opt/rds-ca-2019-root.pem')
    
    # ElastiCache Configuration
    ELASTICACHE_HOST = os.getenv('ELASTICACHE_HOST')
    ELASTICACHE_PORT = int(os.getenv('ELASTICACHE_PORT', '6379'))
    
    # Cognito Configuration
    USER_POOL_ID = os.getenv('USER_POOL_ID')
    USER_POOL_CLIENT_ID = os.getenv('USER_POOL_CLIENT_ID')
    
    # Bedrock Configuration
    BEDROCK_MODEL_ID = os.getenv('BEDROCK_MODEL_ID', 'anthropic.claude-3-sonnet-20240229-v1:0')
    BEDROCK_EMBEDDING_MODEL_ID = os.getenv('BEDROCK_EMBEDDING_MODEL_ID', 'amazon.titan-embed-text-v1')
    
    # Application Settings
    JWT_SECRET_KEY = os.getenv('JWT_SECRET_KEY', 'your-secret-key-change-in-production')
    JWT_ALGORITHM = 'HS256'
    JWT_EXPIRATION_HOURS = int(os.getenv('JWT_EXPIRATION_HOURS', '24'))
    
    # Cache Settings
    CACHE_TTL_SECONDS = int(os.getenv('CACHE_TTL_SECONDS', '3600'))  # 1 hour
    CHAT_CACHE_TTL_SECONDS = int(os.getenv('CHAT_CACHE_TTL_SECONDS', '1800'))  # 30 minutes
    
    # Pagination
    DEFAULT_PAGE_SIZE = int(os.getenv('DEFAULT_PAGE_SIZE', '20'))
    MAX_PAGE_SIZE = int(os.getenv('MAX_PAGE_SIZE', '100'))
    
    # Logging
    LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
    
    @classmethod
    def validate(cls) -> bool:
        """Validate required configuration"""
        required_vars = [
            'DOCUMENTDB_HOST',
            'DOCUMENTDB_USERNAME', 
            'DOCUMENTDB_PASSWORD',
            'ELASTICACHE_HOST',
            'USER_POOL_ID',
            'USER_POOL_CLIENT_ID'
        ]
        
        missing_vars = []
        for var in required_vars:
            if not getattr(cls, var):
                missing_vars.append(var)
        
        if missing_vars:
            raise ValueError(f"Missing required environment variables: {', '.join(missing_vars)}")
        
        return True

# Create global config instance
config = Config()