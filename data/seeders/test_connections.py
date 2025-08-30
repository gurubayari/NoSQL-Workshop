#!/usr/bin/env python3
"""
Test script for database connections
Tests all three database connections (DocumentDB, DynamoDB, ElastiCache)
"""
import sys
import os

# Add current directory to path for imports
sys.path.append(os.path.dirname(__file__))

from database_connections import (
    test_all_connections,
    get_documentdb_collection,
    get_dynamodb_table,
    get_elasticache_client,
    DatabaseConnectionManager
)

def main():
    """Test all database connections"""
    print("🦄 Unicorn E-Commerce Database Connection Test")
    print("=" * 60)
    
    # Test using the convenience functions
    print("\n1. Testing individual connection functions...")
    
    try:
        print("\n📄 Testing DocumentDB connection...")
        products_collection = get_documentdb_collection('products')
        print(f"✅ DocumentDB products collection: {products_collection.name}")
    except Exception as e:
        print(f"❌ DocumentDB connection failed: {e}")
    
    try:
        print("\n📊 Testing DynamoDB connection...")
        inventory_table = get_dynamodb_table('INVENTORY_TABLE')
        print(f"✅ DynamoDB inventory table: {inventory_table.table_name}")
    except Exception as e:
        print(f"❌ DynamoDB connection failed: {e}")
    
    try:
        print("\n🔄 Testing ElastiCache connection...")
        redis_client = get_elasticache_client()
        redis_client.ping()
        print(f"✅ ElastiCache connection successful")
    except Exception as e:
        print(f"❌ ElastiCache connection failed: {e}")
    
    # Test using the comprehensive test function
    print("\n2. Running comprehensive connection tests...")
    test_all_connections()
    
    # Test using context manager
    print("\n3. Testing context manager...")
    try:
        with DatabaseConnectionManager() as db:
            products_collection = db.get_documentdb_collection('products')
            print(f"✅ Context manager test successful")
    except Exception as e:
        print(f"❌ Context manager test failed: {e}")
    
    print("\n🎉 Database connection tests completed!")

if __name__ == "__main__":
    main()