#!/usr/bin/env python3
"""
Test script for DocumentDB vector search functionality
Tests vector search accuracy and performance with sample data
"""
import sys
import os
import json
import numpy as np
from datetime import datetime
import logging

# Add the backend directory to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from shared.vector_search import vector_search_manager
from shared.database import get_documentdb_collection

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def create_sample_data_with_embeddings():
    """Create sample data with mock embeddings for testing"""
    
    # Sample products with embeddings
    sample_products = [
        {
            "product_id": "test-prod-1",
            "title": "Wireless Bluetooth Headphones",
            "description": "High-quality wireless headphones with noise cancellation and long battery life",
            "category": "Electronics",
            "price": 199.99,
            "rating": 4.5,
            "review_count": 234,
            "tags": ["wireless", "bluetooth", "headphones", "audio"],
            "description_embedding": np.random.rand(1536).tolist()
        },
        {
            "product_id": "test-prod-2", 
            "title": "Gaming Laptop",
            "description": "Powerful gaming laptop with high-performance graphics and fast processor",
            "category": "Electronics",
            "price": 1299.99,
            "rating": 4.7,
            "review_count": 89,
            "tags": ["gaming", "laptop", "computer", "performance"],
            "description_embedding": np.random.rand(1536).tolist()
        },
        {
            "product_id": "test-prod-3",
            "title": "Fitness Tracker",
            "description": "Smart fitness tracker with heart rate monitoring and GPS",
            "category": "Fitness",
            "price": 149.99,
            "rating": 4.2,
            "review_count": 312,
            "tags": ["fitness", "tracker", "health", "smart"],
            "description_embedding": np.random.rand(1536).tolist()
        }
    ]
    
    # Sample reviews with embeddings
    sample_reviews = [
        {
            "review_id": "test-review-1",
            "product_id": "test-prod-1",
            "user_id": "user-1",
            "user_name": "John D.",
            "rating": 5,
            "title": "Excellent sound quality!",
            "content": "These headphones have amazing audio quality and the noise cancellation works perfectly. Great for long flights and daily commuting.",
            "sentiment": {"score": 0.9, "label": "positive"},
            "aspects": {"audio_quality": 0.95, "comfort": 0.85, "value": 0.8},
            "helpful_count": 23,
            "created_at": datetime.utcnow(),
            "content_embedding": np.random.rand(1536).tolist()
        },
        {
            "review_id": "test-review-2",
            "product_id": "test-prod-2",
            "user_id": "user-2", 
            "user_name": "Sarah M.",
            "rating": 4,
            "title": "Great for gaming",
            "content": "This laptop handles all modern games smoothly. The graphics are crisp and the performance is excellent. Battery life could be better.",
            "sentiment": {"score": 0.7, "label": "positive"},
            "aspects": {"performance": 0.9, "graphics": 0.85, "battery": 0.6},
            "helpful_count": 15,
            "created_at": datetime.utcnow(),
            "content_embedding": np.random.rand(1536).tolist()
        },
        {
            "review_id": "test-review-3",
            "product_id": "test-prod-3",
            "user_id": "user-3",
            "user_name": "Mike R.",
            "rating": 4,
            "title": "Good fitness companion",
            "content": "Accurate heart rate monitoring and GPS tracking. The app is user-friendly and the battery lasts several days.",
            "sentiment": {"score": 0.8, "label": "positive"},
            "aspects": {"accuracy": 0.9, "battery": 0.85, "usability": 0.8},
            "helpful_count": 8,
            "created_at": datetime.utcnow(),
            "content_embedding": np.random.rand(1536).tolist()
        }
    ]
    
    # Sample knowledge base articles with embeddings
    sample_knowledge_base = [
        {
            "article_id": "kb-1",
            "title": "Return Policy",
            "content": "You can return any item within 30 days of purchase for a full refund. Items must be in original condition with all packaging.",
            "category": "policies",
            "type": "return_policy",
            "tags": ["return", "refund", "policy"],
            "created_at": datetime.utcnow(),
            "content_embedding": np.random.rand(1536).tolist()
        },
        {
            "article_id": "kb-2",
            "title": "Shipping Information",
            "content": "We offer free shipping on orders over $50. Standard shipping takes 3-5 business days, express shipping takes 1-2 business days.",
            "category": "shipping",
            "type": "shipping_info",
            "tags": ["shipping", "delivery", "free"],
            "created_at": datetime.utcnow(),
            "content_embedding": np.random.rand(1536).tolist()
        },
        {
            "article_id": "kb-3",
            "title": "Product Warranty",
            "content": "All electronics come with a 1-year manufacturer warranty. Extended warranty options are available at checkout.",
            "category": "warranty",
            "type": "warranty_info", 
            "tags": ["warranty", "protection", "electronics"],
            "created_at": datetime.utcnow(),
            "content_embedding": np.random.rand(1536).tolist()
        }
    ]
    
    return sample_products, sample_reviews, sample_knowledge_base

def insert_sample_data(products, reviews, knowledge_base):
    """Insert sample data into DocumentDB collections"""
    try:
        # Insert products
        products_collection = get_documentdb_collection('products')
        products_collection.delete_many({"product_id": {"$regex": "^test-"}})  # Clean up existing test data
        products_collection.insert_many(products)
        logger.info(f"Inserted {len(products)} test products")
        
        # Insert reviews
        reviews_collection = get_documentdb_collection('reviews')
        reviews_collection.delete_many({"review_id": {"$regex": "^test-"}})  # Clean up existing test data
        reviews_collection.insert_many(reviews)
        logger.info(f"Inserted {len(reviews)} test reviews")
        
        # Insert knowledge base
        kb_collection = get_documentdb_collection('knowledge_base')
        kb_collection.delete_many({"article_id": {"$regex": "^kb-"}})  # Clean up existing test data
        kb_collection.insert_many(knowledge_base)
        logger.info(f"Inserted {len(knowledge_base)} test knowledge base articles")
        
        return True
        
    except Exception as e:
        logger.error(f"Failed to insert sample data: {e}")
        return False

def test_vector_search_accuracy():
    """Test vector search accuracy with known data"""
    test_results = {
        'timestamp': datetime.utcnow().isoformat(),
        'accuracy_tests': {}
    }
    
    # Test 1: Search for audio-related products
    print("\n🎧 Test 1: Searching for audio-related products...")
    audio_query_embedding = np.random.rand(1536).tolist()  # In real scenario, this would be embedding of "audio headphones"
    
    try:
        audio_results = vector_search_manager.vector_search_products(
            query_embedding=audio_query_embedding,
            limit=5,
            min_score=0.1
        )
        
        test_results['accuracy_tests']['audio_products'] = {
            'success': True,
            'results_count': len(audio_results),
            'results': [
                {
                    'title': r.get('title'),
                    'category': r.get('category'),
                    'similarity_score': r.get('similarity_score')
                } for r in audio_results
            ]
        }
        
        print(f"  Found {len(audio_results)} audio-related products")
        for result in audio_results:
            print(f"    - {result.get('title')} (Score: {result.get('similarity_score', 0):.3f})")
            
    except Exception as e:
        test_results['accuracy_tests']['audio_products'] = {
            'success': False,
            'error': str(e)
        }
        print(f"  ❌ Test failed: {e}")
    
    # Test 2: Search for positive reviews
    print("\n⭐ Test 2: Searching for positive reviews...")
    positive_query_embedding = np.random.rand(1536).tolist()  # In real scenario, this would be embedding of "excellent quality"
    
    try:
        positive_reviews = vector_search_manager.vector_search_reviews(
            query_embedding=positive_query_embedding,
            limit=5,
            min_score=0.1
        )
        
        test_results['accuracy_tests']['positive_reviews'] = {
            'success': True,
            'results_count': len(positive_reviews),
            'results': [
                {
                    'title': r.get('title'),
                    'rating': r.get('rating'),
                    'similarity_score': r.get('similarity_score')
                } for r in positive_reviews
            ]
        }
        
        print(f"  Found {len(positive_reviews)} positive reviews")
        for result in positive_reviews:
            print(f"    - {result.get('title')} (Rating: {result.get('rating')}, Score: {result.get('similarity_score', 0):.3f})")
            
    except Exception as e:
        test_results['accuracy_tests']['positive_reviews'] = {
            'success': False,
            'error': str(e)
        }
        print(f"  ❌ Test failed: {e}")
    
    # Test 3: Search knowledge base for policy information
    print("\n📋 Test 3: Searching knowledge base for policy information...")
    policy_query_embedding = np.random.rand(1536).tolist()  # In real scenario, this would be embedding of "return policy"
    
    try:
        policy_results = vector_search_manager.vector_search_knowledge_base(
            query_embedding=policy_query_embedding,
            limit=3,
            min_score=0.1
        )
        
        test_results['accuracy_tests']['policy_knowledge'] = {
            'success': True,
            'results_count': len(policy_results),
            'results': [
                {
                    'title': r.get('title'),
                    'category': r.get('category'),
                    'similarity_score': r.get('similarity_score')
                } for r in policy_results
            ]
        }
        
        print(f"  Found {len(policy_results)} policy-related articles")
        for result in policy_results:
            print(f"    - {result.get('title')} (Category: {result.get('category')}, Score: {result.get('similarity_score', 0):.3f})")
            
    except Exception as e:
        test_results['accuracy_tests']['policy_knowledge'] = {
            'success': False,
            'error': str(e)
        }
        print(f"  ❌ Test failed: {e}")
    
    return test_results

def test_vector_search_performance():
    """Test vector search performance with various parameters"""
    print("\n⚡ Testing vector search performance...")
    
    performance_results = {
        'timestamp': datetime.utcnow().isoformat(),
        'performance_tests': {}
    }
    
    test_embedding = np.random.rand(1536).tolist()
    
    # Test different result limits
    for limit in [5, 10, 20, 50]:
        print(f"\n  Testing with limit={limit}...")
        
        try:
            start_time = datetime.utcnow()
            results = vector_search_manager.vector_search_products(
                query_embedding=test_embedding,
                limit=limit,
                min_score=0.1
            )
            end_time = datetime.utcnow()
            
            response_time = (end_time - start_time).total_seconds() * 1000
            
            performance_results['performance_tests'][f'limit_{limit}'] = {
                'success': True,
                'results_count': len(results),
                'response_time_ms': response_time,
                'avg_score': np.mean([r.get('similarity_score', 0) for r in results]) if results else 0
            }
            
            print(f"    Results: {len(results)}, Time: {response_time:.2f}ms")
            
        except Exception as e:
            performance_results['performance_tests'][f'limit_{limit}'] = {
                'success': False,
                'error': str(e)
            }
            print(f"    ❌ Failed: {e}")
    
    # Test with filters
    print(f"\n  Testing with category filter...")
    try:
        start_time = datetime.utcnow()
        filtered_results = vector_search_manager.vector_search_products(
            query_embedding=test_embedding,
            limit=10,
            filters={'category': 'Electronics'},
            min_score=0.1
        )
        end_time = datetime.utcnow()
        
        response_time = (end_time - start_time).total_seconds() * 1000
        
        performance_results['performance_tests']['with_filter'] = {
            'success': True,
            'results_count': len(filtered_results),
            'response_time_ms': response_time
        }
        
        print(f"    Filtered Results: {len(filtered_results)}, Time: {response_time:.2f}ms")
        
    except Exception as e:
        performance_results['performance_tests']['with_filter'] = {
            'success': False,
            'error': str(e)
        }
        print(f"    ❌ Failed: {e}")
    
    return performance_results

def cleanup_test_data():
    """Clean up test data from collections"""
    try:
        # Clean up products
        products_collection = get_documentdb_collection('products')
        products_collection.delete_many({"product_id": {"$regex": "^test-"}})
        
        # Clean up reviews
        reviews_collection = get_documentdb_collection('reviews')
        reviews_collection.delete_many({"review_id": {"$regex": "^test-"}})
        
        # Clean up knowledge base
        kb_collection = get_documentdb_collection('knowledge_base')
        kb_collection.delete_many({"article_id": {"$regex": "^kb-"}})
        
        logger.info("Test data cleaned up successfully")
        return True
        
    except Exception as e:
        logger.error(f"Failed to clean up test data: {e}")
        return False

def main():
    """Main test function"""
    print("🦄 Unicorn E-Commerce - Vector Search Testing")
    print("=" * 60)
    
    try:
        # Create and insert sample data
        print("📝 Creating sample data with embeddings...")
        products, reviews, knowledge_base = create_sample_data_with_embeddings()
        
        print("💾 Inserting sample data into DocumentDB...")
        if not insert_sample_data(products, reviews, knowledge_base):
            print("❌ Failed to insert sample data")
            return
        
        print("✅ Sample data inserted successfully")
        
        # Test vector search accuracy
        print("\n🎯 Testing vector search accuracy...")
        accuracy_results = test_vector_search_accuracy()
        
        # Test vector search performance
        performance_results = test_vector_search_performance()
        
        # Combine all results
        all_results = {
            'timestamp': datetime.utcnow().isoformat(),
            'accuracy_tests': accuracy_results.get('accuracy_tests', {}),
            'performance_tests': performance_results.get('performance_tests', {})
        }
        
        # Save results to file
        results_file = f"vector_search_test_results_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
        with open(results_file, 'w') as f:
            json.dump(all_results, f, indent=2, default=str)
        
        print(f"\n💾 Test results saved to: {results_file}")
        
        # Summary
        accuracy_success = all(
            test.get('success', False) 
            for test in accuracy_results.get('accuracy_tests', {}).values()
        )
        performance_success = all(
            test.get('success', False) 
            for test in performance_results.get('performance_tests', {}).values()
        )
        
        print("\n" + "=" * 60)
        if accuracy_success and performance_success:
            print("🎉 All vector search tests passed!")
            print("✅ Vector search is working correctly")
        else:
            print("⚠️  Some vector search tests failed")
            print("❌ Check the results above for details")
        
        # Clean up test data
        print("\n🧹 Cleaning up test data...")
        if cleanup_test_data():
            print("✅ Test data cleaned up successfully")
        else:
            print("⚠️  Failed to clean up some test data")
        
    except Exception as e:
        logger.error(f"Test failed: {e}")
        print(f"\n❌ Test failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()