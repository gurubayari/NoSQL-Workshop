#!/usr/bin/env python3
"""
Test script for vector embedding generation system
Tests Bedrock integration, caching, batch processing, and real-time generation
"""
import sys
import os
import json
import time
from datetime import datetime
import logging

# Add the backend directory to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from shared.embeddings import embedding_generator, EmbeddingRequest
from shared.realtime_embeddings import realtime_embedding_service
from shared.database import db

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_basic_embedding_generation():
    """Test basic embedding generation functionality"""
    print("\n🧪 Test 1: Basic Embedding Generation")
    print("-" * 50)
    
    test_texts = [
        "Wireless Bluetooth headphones with noise cancellation",
        "Gaming laptop with high-performance graphics card",
        "Smart fitness tracker with heart rate monitoring",
        "Organic cotton t-shirt in multiple colors",
        "Professional camera with 4K video recording"
    ]
    
    results = []
    
    for i, text in enumerate(test_texts, 1):
        print(f"  Generating embedding {i}/5: {text[:50]}...")
        
        start_time = time.time()
        result = embedding_generator.generate_embedding(text, use_cache=False)
        end_time = time.time()
        
        if result.success:
            print(f"    ✅ Success - Dimensions: {len(result.embedding)}, Time: {(end_time - start_time) * 1000:.2f}ms")
            results.append({
                'text': text,
                'success': True,
                'dimensions': len(result.embedding),
                'processing_time_ms': result.processing_time_ms,
                'cached': result.cached
            })
        else:
            print(f"    ❌ Failed: {result.error}")
            results.append({
                'text': text,
                'success': False,
                'error': result.error
            })
    
    success_count = sum(1 for r in results if r['success'])
    print(f"\n  Summary: {success_count}/{len(test_texts)} embeddings generated successfully")
    
    return results

def test_caching_functionality():
    """Test embedding caching functionality"""
    print("\n🧪 Test 2: Caching Functionality")
    print("-" * 50)
    
    test_text = "Test caching with this specific text for embedding generation"
    
    # First call (should not be cached)
    print("  First call (no cache)...")
    result1 = embedding_generator.generate_embedding(test_text, use_cache=True)
    
    if result1.success:
        print(f"    ✅ Generated - Cached: {result1.cached}, Time: {result1.processing_time_ms:.2f}ms")
    else:
        print(f"    ❌ Failed: {result1.error}")
        return {'success': False, 'error': result1.error}
    
    # Second call (should be cached)
    print("  Second call (should be cached)...")
    result2 = embedding_generator.generate_embedding(test_text, use_cache=True)
    
    if result2.success:
        print(f"    ✅ Retrieved - Cached: {result2.cached}, Time: {result2.processing_time_ms:.2f}ms")
        
        # Verify embeddings are identical
        if result1.embedding == result2.embedding:
            print("    ✅ Embeddings match - caching working correctly")
            cache_speedup = result1.processing_time_ms / result2.processing_time_ms if result2.processing_time_ms > 0 else float('inf')
            print(f"    📈 Cache speedup: {cache_speedup:.1f}x faster")
        else:
            print("    ❌ Embeddings don't match - caching issue")
            return {'success': False, 'error': 'Cached embeddings do not match'}
    else:
        print(f"    ❌ Failed: {result2.error}")
        return {'success': False, 'error': result2.error}
    
    return {
        'success': True,
        'first_call_cached': result1.cached,
        'second_call_cached': result2.cached,
        'embeddings_match': result1.embedding == result2.embedding,
        'speedup': result1.processing_time_ms / result2.processing_time_ms if result2.processing_time_ms > 0 else float('inf')
    }

def test_batch_processing():
    """Test batch embedding processing"""
    print("\n🧪 Test 3: Batch Processing")
    print("-" * 50)
    
    # Create batch requests
    batch_texts = [
        "High-quality wireless earbuds with long battery life",
        "Professional DSLR camera for photography enthusiasts", 
        "Ergonomic office chair with lumbar support",
        "Stainless steel water bottle with insulation",
        "Bluetooth speaker with waterproof design",
        "Mechanical keyboard for gaming and typing",
        "Smart home security camera with night vision",
        "Portable power bank with fast charging",
        "Noise-cancelling headphones for travel",
        "Fitness smartwatch with GPS tracking"
    ]
    
    requests = [
        EmbeddingRequest(text=text, identifier=f"batch-{i}")
        for i, text in enumerate(batch_texts)
    ]
    
    print(f"  Processing batch of {len(requests)} requests...")
    
    start_time = time.time()
    results = embedding_generator.generate_embeddings_batch(requests, use_cache=False, max_workers=5)
    end_time = time.time()
    
    total_time = end_time - start_time
    successful = sum(1 for r in results if r.success)
    
    print(f"  ✅ Batch complete: {successful}/{len(requests)} successful")
    print(f"  ⏱️  Total time: {total_time:.2f}s")
    print(f"  📊 Rate: {successful / total_time:.2f} embeddings/second")
    
    # Check for any failures
    failures = [r for r in results if not r.success]
    if failures:
        print(f"  ❌ {len(failures)} failures:")
        for failure in failures[:3]:  # Show first 3 failures
            print(f"    - {failure.identifier}: {failure.error}")
    
    return {
        'success': successful == len(requests),
        'total_requests': len(requests),
        'successful': successful,
        'failed': len(failures),
        'total_time_seconds': total_time,
        'rate_per_second': successful / total_time if total_time > 0 else 0
    }

def test_product_embedding_generation():
    """Test product-specific embedding generation"""
    print("\n🧪 Test 4: Product Embedding Generation")
    print("-" * 50)
    
    sample_products = [
        {
            'product_id': 'test-prod-1',
            'title': 'Wireless Bluetooth Headphones',
            'description': 'Premium wireless headphones with active noise cancellation and 30-hour battery life',
            'category': 'Electronics',
            'tags': ['wireless', 'bluetooth', 'headphones', 'noise-cancelling']
        },
        {
            'product_id': 'test-prod-2',
            'title': 'Gaming Mechanical Keyboard',
            'description': 'RGB backlit mechanical keyboard with tactile switches, perfect for gaming and productivity',
            'category': 'Electronics',
            'tags': ['gaming', 'keyboard', 'mechanical', 'rgb']
        }
    ]
    
    print(f"  Generating embeddings for {len(sample_products)} products...")
    
    results = embedding_generator.generate_product_embeddings(sample_products)
    
    successful = sum(1 for r in results if r.success)
    print(f"  ✅ Generated: {successful}/{len(sample_products)} product embeddings")
    
    for result in results:
        if result.success:
            print(f"    - {result.identifier}: {len(result.embedding)} dimensions, {result.processing_time_ms:.2f}ms")
        else:
            print(f"    - {result.identifier}: ❌ {result.error}")
    
    return {
        'success': successful == len(sample_products),
        'total_products': len(sample_products),
        'successful': successful,
        'results': results
    }

def test_review_embedding_generation():
    """Test review-specific embedding generation"""
    print("\n🧪 Test 5: Review Embedding Generation")
    print("-" * 50)
    
    sample_reviews = [
        {
            'review_id': 'test-review-1',
            'product_id': 'test-prod-1',
            'title': 'Excellent sound quality!',
            'content': 'These headphones have amazing audio quality and the noise cancellation works perfectly. Great for long flights.',
            'rating': 5
        },
        {
            'review_id': 'test-review-2',
            'product_id': 'test-prod-2',
            'title': 'Great for gaming',
            'content': 'The mechanical switches feel great and the RGB lighting is customizable. Perfect for gaming sessions.',
            'rating': 4
        }
    ]
    
    print(f"  Generating embeddings for {len(sample_reviews)} reviews...")
    
    results = embedding_generator.generate_review_embeddings(sample_reviews)
    
    successful = sum(1 for r in results if r.success)
    print(f"  ✅ Generated: {successful}/{len(sample_reviews)} review embeddings")
    
    for result in results:
        if result.success:
            print(f"    - {result.identifier}: {len(result.embedding)} dimensions, {result.processing_time_ms:.2f}ms")
        else:
            print(f"    - {result.identifier}: ❌ {result.error}")
    
    return {
        'success': successful == len(sample_reviews),
        'total_reviews': len(sample_reviews),
        'successful': successful,
        'results': results
    }

def test_realtime_embedding_service():
    """Test real-time embedding service"""
    print("\n🧪 Test 6: Real-time Embedding Service")
    print("-" * 50)
    
    # Test query embedding generation
    print("  Testing query embedding generation...")
    query_result = realtime_embedding_service.generate_query_embedding("wireless headphones with good sound quality")
    
    if query_result['success']:
        print(f"    ✅ Query embedding generated: {len(query_result['embedding'])} dimensions")
        print(f"    📊 Cached: {query_result['cached']}, Time: {query_result['processing_time_ms']:.2f}ms")
    else:
        print(f"    ❌ Query embedding failed: {query_result['error']}")
    
    return {
        'query_embedding_success': query_result['success'],
        'query_embedding_dimensions': len(query_result.get('embedding', [])),
        'query_embedding_cached': query_result.get('cached', False)
    }

def test_error_handling():
    """Test error handling and edge cases"""
    print("\n🧪 Test 7: Error Handling")
    print("-" * 50)
    
    test_cases = [
        ("Empty text", ""),
        ("Very long text", "A" * 10000),  # Test truncation
        ("Special characters", "🦄🎧🎮💻📱⭐🔥💯"),
        ("Mixed languages", "Hello 你好 Bonjour Hola こんにちは"),
    ]
    
    results = []
    
    for test_name, test_text in test_cases:
        print(f"  Testing {test_name}...")
        result = embedding_generator.generate_embedding(test_text, use_cache=False)
        
        if result.success:
            print(f"    ✅ Success: {len(result.embedding)} dimensions")
            results.append({'test': test_name, 'success': True, 'dimensions': len(result.embedding)})
        else:
            print(f"    ❌ Failed: {result.error}")
            results.append({'test': test_name, 'success': False, 'error': result.error})
    
    successful_tests = sum(1 for r in results if r['success'])
    print(f"\n  Summary: {successful_tests}/{len(test_cases)} error handling tests passed")
    
    return {
        'total_tests': len(test_cases),
        'successful': successful_tests,
        'results': results
    }

def main():
    """Main test function"""
    print("🦄 Unicorn E-Commerce - Embedding System Testing")
    print("=" * 60)
    
    try:
        # Test database connection
        print("📡 Testing database connections...")
        database = db.get_documentdb_database()
        database.command('ping')
        print("✅ DocumentDB connection successful")
        
        # Run all tests
        test_results = {
            'timestamp': datetime.utcnow().isoformat(),
            'tests': {}
        }
        
        # Test 1: Basic embedding generation
        test_results['tests']['basic_generation'] = test_basic_embedding_generation()
        
        # Test 2: Caching functionality
        test_results['tests']['caching'] = test_caching_functionality()
        
        # Test 3: Batch processing
        test_results['tests']['batch_processing'] = test_batch_processing()
        
        # Test 4: Product embeddings
        test_results['tests']['product_embeddings'] = test_product_embedding_generation()
        
        # Test 5: Review embeddings
        test_results['tests']['review_embeddings'] = test_review_embedding_generation()
        
        # Test 6: Real-time service
        test_results['tests']['realtime_service'] = test_realtime_embedding_service()
        
        # Test 7: Error handling
        test_results['tests']['error_handling'] = test_error_handling()
        
        # Save results to file
        results_file = f"embedding_test_results_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
        with open(results_file, 'w') as f:
            json.dump(test_results, f, indent=2, default=str)
        
        print(f"\n💾 Test results saved to: {results_file}")
        
        # Summary
        print("\n" + "=" * 60)
        print("📊 TEST SUMMARY")
        print("=" * 60)
        
        total_tests = len(test_results['tests'])
        successful_tests = 0
        
        for test_name, test_result in test_results['tests'].items():
            if isinstance(test_result, dict) and test_result.get('success', False):
                successful_tests += 1
                status = "✅ PASS"
            elif isinstance(test_result, list):
                # Handle list results (like basic generation)
                if all(r.get('success', False) for r in test_result):
                    successful_tests += 1
                    status = "✅ PASS"
                else:
                    status = "❌ FAIL"
            else:
                status = "❌ FAIL"
            
            print(f"  {test_name}: {status}")
        
        print(f"\nOverall: {successful_tests}/{total_tests} tests passed")
        
        if successful_tests == total_tests:
            print("\n🎉 All embedding system tests passed!")
            print("✅ Embedding system is working correctly")
        else:
            print(f"\n⚠️  {total_tests - successful_tests} tests failed")
            print("❌ Check the results above for details")
        
        # Display embedding generator stats
        print("\n📈 Embedding Generator Statistics:")
        stats = embedding_generator.get_embedding_stats()
        for key, value in stats.items():
            print(f"  {key}: {value}")
        
    except Exception as e:
        logger.error(f"Test failed: {e}")
        print(f"\n❌ Test failed: {e}")
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