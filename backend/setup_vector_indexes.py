#!/usr/bin/env python3
"""
Setup script for DocumentDB vector indexes
Creates HNSW vector indexes for products, reviews, and knowledge base collections
"""
import sys
import os
import json
import logging
from datetime import datetime

# Add the backend directory to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from shared.vector_search import vector_search_manager
from shared.database import db

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def main():
    """Main setup function"""
    print("🦄 Unicorn E-Commerce - DocumentDB Vector Search Setup")
    print("=" * 60)
    
    try:
        # Test database connection
        print("📡 Testing DocumentDB connection...")
        database = db.get_documentdb_database()
        database.command('ping')
        print("✅ DocumentDB connection successful")
        
        # Create vector indexes
        print("\n🔍 Creating vector indexes...")
        vector_results = vector_search_manager.create_vector_indexes()
        
        print("\nVector Index Creation Results:")
        for collection, success in vector_results.items():
            status = "✅ Success" if success else "❌ Failed"
            print(f"  {collection}: {status}")
        
        # Create supporting indexes
        print("\n📊 Creating supporting indexes...")
        supporting_results = vector_search_manager.create_supporting_indexes()
        
        print("\nSupporting Index Creation Results:")
        for index_type, success in supporting_results.items():
            status = "✅ Success" if success else "❌ Failed"
            print(f"  {index_type}: {status}")
        
        # Get index statistics
        print("\n📈 Getting index statistics...")
        stats = vector_search_manager.get_index_stats()
        
        print("\nIndex Statistics:")
        for collection, collection_stats in stats.items():
            print(f"\n  {collection.upper()}:")
            if 'error' in collection_stats:
                print(f"    ❌ Error: {collection_stats['error']}")
            else:
                print(f"    Documents: {collection_stats.get('document_count', 0):,}")
                print(f"    Size: {collection_stats.get('size_bytes', 0):,} bytes")
                print(f"    Vector Index: {'✅ Exists' if collection_stats.get('vector_index_exists') else '❌ Missing'}")
                print(f"    Total Indexes: {collection_stats.get('total_indexes', 0)}")
        
        # Test vector search performance
        print("\n🧪 Testing vector search performance...")
        test_results = vector_search_manager.test_vector_search_performance()
        
        print("\nPerformance Test Results:")
        for test_name, test_result in test_results['tests'].items():
            print(f"\n  {test_name.upper()}:")
            if test_result.get('success'):
                print(f"    ✅ Success")
                print(f"    Results: {test_result.get('results_count', 0)}")
                print(f"    Response Time: {test_result.get('response_time_ms', 0):.2f}ms")
                if test_result.get('sample_scores'):
                    print(f"    Sample Scores: {test_result['sample_scores']}")
            else:
                print(f"    ❌ Failed: {test_result.get('error', 'Unknown error')}")
        
        # Save detailed results to file
        results_file = f"vector_search_setup_results_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
        detailed_results = {
            'timestamp': datetime.utcnow().isoformat(),
            'vector_indexes': vector_results,
            'supporting_indexes': supporting_results,
            'statistics': stats,
            'performance_tests': test_results
        }
        
        with open(results_file, 'w') as f:
            json.dump(detailed_results, f, indent=2, default=str)
        
        print(f"\n💾 Detailed results saved to: {results_file}")
        
        # Summary
        all_vector_success = all(vector_results.values())
        all_supporting_success = all(supporting_results.values())
        
        print("\n" + "=" * 60)
        if all_vector_success and all_supporting_success:
            print("🎉 Vector search setup completed successfully!")
            print("✅ All indexes created and tested")
        else:
            print("⚠️  Vector search setup completed with some issues")
            print("❌ Some indexes failed to create - check logs above")
        
        print("\nNext steps:")
        print("1. Run the embedding generation system (task 7.2)")
        print("2. Populate collections with vector embeddings")
        print("3. Test semantic search functionality")
        
    except Exception as e:
        logger.error(f"Setup failed: {e}")
        print(f"\n❌ Setup failed: {e}")
        sys.exit(1)
    
    finally:
        # Close database connections
        try:
            db.close_connections()
            print("\n🔌 Database connections closed")
        except:
            pass

if __name__ == "__main__":
    main()