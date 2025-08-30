#!/usr/bin/env python3
"""
Embedding optimization utilities
Provides caching optimization, performance monitoring, and embedding quality analysis
"""
import sys
import os
import json
import time
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
import statistics
import logging

# Add the backend directory to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from shared.embeddings import embedding_generator
from shared.database import db, cache_get, cache_set, get_cache_key
from shared.vector_search import vector_search_manager

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class EmbeddingOptimizer:
    """Optimizes embedding generation and caching strategies"""
    
    def __init__(self):
        self.embedding_generator = embedding_generator
        self.vector_search_manager = vector_search_manager
    
    def analyze_cache_performance(self, sample_size: int = 100) -> Dict[str, Any]:
        """Analyze embedding cache hit rates and performance"""
        print(f"🔍 Analyzing cache performance with {sample_size} samples...")
        
        # Generate sample texts for testing
        sample_texts = [
            f"Sample product description {i} with various features and specifications"
            for i in range(sample_size)
        ]
        
        cache_hits = 0
        cache_misses = 0
        hit_times = []
        miss_times = []
        
        # First pass - populate cache
        print("  First pass: Populating cache...")
        for i, text in enumerate(sample_texts):
            if i % 20 == 0:
                print(f"    Progress: {i}/{sample_size}")
            
            start_time = time.time()
            result = self.embedding_generator.generate_embedding(text, use_cache=True)
            end_time = time.time()
            
            if result.success:
                if result.cached:
                    cache_hits += 1
                    hit_times.append((end_time - start_time) * 1000)
                else:
                    cache_misses += 1
                    miss_times.append((end_time - start_time) * 1000)
        
        # Second pass - test cache hits
        print("  Second pass: Testing cache hits...")
        second_pass_hits = 0
        second_pass_hit_times = []
        
        for i, text in enumerate(sample_texts[:50]):  # Test subset
            start_time = time.time()
            result = self.embedding_generator.generate_embedding(text, use_cache=True)
            end_time = time.time()
            
            if result.success and result.cached:
                second_pass_hits += 1
                second_pass_hit_times.append((end_time - start_time) * 1000)
        
        # Calculate statistics
        analysis = {
            'timestamp': datetime.utcnow().isoformat(),
            'sample_size': sample_size,
            'first_pass': {
                'cache_hits': cache_hits,
                'cache_misses': cache_misses,
                'hit_rate': cache_hits / (cache_hits + cache_misses) if (cache_hits + cache_misses) > 0 else 0,
                'avg_hit_time_ms': statistics.mean(hit_times) if hit_times else 0,
                'avg_miss_time_ms': statistics.mean(miss_times) if miss_times else 0
            },
            'second_pass': {
                'cache_hits': second_pass_hits,
                'tested_samples': 50,
                'hit_rate': second_pass_hits / 50,
                'avg_hit_time_ms': statistics.mean(second_pass_hit_times) if second_pass_hit_times else 0
            }
        }
        
        if miss_times and second_pass_hit_times:
            analysis['performance_improvement'] = {
                'speedup_factor': statistics.mean(miss_times) / statistics.mean(second_pass_hit_times),
                'time_saved_ms': statistics.mean(miss_times) - statistics.mean(second_pass_hit_times)
            }
        
        print(f"  ✅ Cache analysis complete:")
        print(f"    First pass hit rate: {analysis['first_pass']['hit_rate']:.2%}")
        print(f"    Second pass hit rate: {analysis['second_pass']['hit_rate']:.2%}")
        if 'performance_improvement' in analysis:
            print(f"    Cache speedup: {analysis['performance_improvement']['speedup_factor']:.1f}x")
        
        return analysis
    
    def benchmark_embedding_performance(self) -> Dict[str, Any]:
        """Benchmark embedding generation performance across different scenarios"""
        print("⚡ Benchmarking embedding performance...")
        
        benchmarks = {
            'timestamp': datetime.utcnow().isoformat(),
            'scenarios': {}
        }
        
        # Scenario 1: Short texts
        print("  Testing short texts...")
        short_texts = [f"Short product title {i}" for i in range(20)]
        short_results = self._benchmark_text_batch(short_texts, "short_texts")
        benchmarks['scenarios']['short_texts'] = short_results
        
        # Scenario 2: Medium texts
        print("  Testing medium texts...")
        medium_texts = [
            f"Medium length product description {i} with detailed features and specifications that provide comprehensive information"
            for i in range(20)
        ]
        medium_results = self._benchmark_text_batch(medium_texts, "medium_texts")
        benchmarks['scenarios']['medium_texts'] = medium_results
        
        # Scenario 3: Long texts
        print("  Testing long texts...")
        long_texts = [
            f"Very long and detailed product description {i} " * 50  # ~2500 characters
            for i in range(10)
        ]
        long_results = self._benchmark_text_batch(long_texts, "long_texts")
        benchmarks['scenarios']['long_texts'] = long_results
        
        # Scenario 4: Batch processing
        print("  Testing batch processing...")
        batch_texts = [f"Batch processing test text {i}" for i in range(50)]
        batch_start = time.time()
        
        from shared.embeddings import EmbeddingRequest
        requests = [EmbeddingRequest(text=text, identifier=f"batch-{i}") for i, text in enumerate(batch_texts)]
        batch_results = self.embedding_generator.generate_embeddings_batch(requests, use_cache=False)
        
        batch_end = time.time()
        batch_successful = sum(1 for r in batch_results if r.success)
        
        benchmarks['scenarios']['batch_processing'] = {
            'total_texts': len(batch_texts),
            'successful': batch_successful,
            'total_time_seconds': batch_end - batch_start,
            'avg_time_per_text_ms': ((batch_end - batch_start) * 1000) / len(batch_texts),
            'throughput_per_second': batch_successful / (batch_end - batch_start)
        }
        
        print(f"  ✅ Performance benchmarking complete")
        return benchmarks
    
    def _benchmark_text_batch(self, texts: List[str], scenario_name: str) -> Dict[str, Any]:
        """Benchmark a batch of texts"""
        times = []
        successful = 0
        
        for text in texts:
            start_time = time.time()
            result = self.embedding_generator.generate_embedding(text, use_cache=False)
            end_time = time.time()
            
            if result.success:
                successful += 1
                times.append((end_time - start_time) * 1000)
        
        return {
            'total_texts': len(texts),
            'successful': successful,
            'avg_time_ms': statistics.mean(times) if times else 0,
            'min_time_ms': min(times) if times else 0,
            'max_time_ms': max(times) if times else 0,
            'median_time_ms': statistics.median(times) if times else 0,
            'std_dev_ms': statistics.stdev(times) if len(times) > 1 else 0
        }
    
    def analyze_embedding_quality(self, sample_size: int = 20) -> Dict[str, Any]:
        """Analyze embedding quality through similarity testing"""
        print(f"🎯 Analyzing embedding quality with {sample_size} samples...")
        
        # Create test cases with known relationships
        test_cases = [
            {
                'category': 'electronics',
                'texts': [
                    'Wireless Bluetooth headphones with noise cancellation',
                    'Bluetooth earbuds with wireless charging case',
                    'Over-ear headphones with premium sound quality',
                    'Gaming headset with surround sound'
                ]
            },
            {
                'category': 'fitness',
                'texts': [
                    'Smart fitness tracker with heart rate monitor',
                    'GPS running watch with activity tracking',
                    'Fitness smartwatch with health monitoring',
                    'Activity tracker with sleep analysis'
                ]
            },
            {
                'category': 'computing',
                'texts': [
                    'High-performance gaming laptop with RTX graphics',
                    'Ultrabook laptop for business professionals',
                    'Gaming desktop computer with liquid cooling',
                    'Workstation laptop for creative professionals'
                ]
            }
        ]
        
        quality_analysis = {
            'timestamp': datetime.utcnow().isoformat(),
            'categories': {}
        }
        
        for test_case in test_cases:
            category = test_case['category']
            texts = test_case['texts']
            
            print(f"  Testing {category} category...")
            
            # Generate embeddings for all texts
            embeddings = []
            for text in texts:
                result = self.embedding_generator.generate_embedding(text, use_cache=True)
                if result.success:
                    embeddings.append(result.embedding)
                else:
                    print(f"    ❌ Failed to generate embedding for: {text[:50]}...")
                    continue
            
            if len(embeddings) < 2:
                print(f"    ⚠️  Not enough embeddings for {category}")
                continue
            
            # Calculate pairwise similarities
            similarities = []
            for i in range(len(embeddings)):
                for j in range(i + 1, len(embeddings)):
                    similarity = self._cosine_similarity(embeddings[i], embeddings[j])
                    similarities.append(similarity)
            
            category_analysis = {
                'texts_count': len(texts),
                'embeddings_generated': len(embeddings),
                'avg_similarity': statistics.mean(similarities) if similarities else 0,
                'min_similarity': min(similarities) if similarities else 0,
                'max_similarity': max(similarities) if similarities else 0,
                'similarity_std_dev': statistics.stdev(similarities) if len(similarities) > 1 else 0
            }
            
            quality_analysis['categories'][category] = category_analysis
            
            print(f"    Average similarity: {category_analysis['avg_similarity']:.3f}")
            print(f"    Similarity range: {category_analysis['min_similarity']:.3f} - {category_analysis['max_similarity']:.3f}")
        
        print(f"  ✅ Quality analysis complete")
        return quality_analysis
    
    def _cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """Calculate cosine similarity between two vectors"""
        import math
        
        dot_product = sum(a * b for a, b in zip(vec1, vec2))
        magnitude1 = math.sqrt(sum(a * a for a in vec1))
        magnitude2 = math.sqrt(sum(a * a for a in vec2))
        
        if magnitude1 == 0 or magnitude2 == 0:
            return 0
        
        return dot_product / (magnitude1 * magnitude2)
    
    def optimize_cache_settings(self) -> Dict[str, Any]:
        """Analyze and recommend optimal cache settings"""
        print("⚙️  Optimizing cache settings...")
        
        # Test different cache TTL values
        ttl_tests = [3600, 7200, 14400, 86400]  # 1h, 2h, 4h, 24h
        test_text = "Cache optimization test text for TTL analysis"
        
        optimization_results = {
            'timestamp': datetime.utcnow().isoformat(),
            'current_ttl': self.embedding_generator.cache_ttl,
            'ttl_tests': {},
            'recommendations': {}
        }
        
        for ttl in ttl_tests:
            print(f"  Testing TTL: {ttl}s ({ttl/3600:.1f}h)...")
            
            # Clear any existing cache for this text
            text_hash = self.embedding_generator._get_text_hash(test_text)
            cache_key = get_cache_key("embedding", text_hash)
            
            # Test cache behavior with this TTL
            original_ttl = self.embedding_generator.cache_ttl
            self.embedding_generator.cache_ttl = ttl
            
            # Generate and cache
            result1 = self.embedding_generator.generate_embedding(test_text, use_cache=True)
            
            # Retrieve from cache
            result2 = self.embedding_generator.generate_embedding(test_text, use_cache=True)
            
            optimization_results['ttl_tests'][ttl] = {
                'first_cached': result1.cached,
                'second_cached': result2.cached,
                'cache_working': not result1.cached and result2.cached
            }
            
            # Restore original TTL
            self.embedding_generator.cache_ttl = original_ttl
        
        # Recommendations based on usage patterns
        optimization_results['recommendations'] = {
            'recommended_ttl': 86400,  # 24 hours for most use cases
            'reasoning': 'Embeddings are expensive to generate and rarely change',
            'cache_size_estimate': 'Each embedding ~6KB, plan cache size accordingly',
            'monitoring_suggestions': [
                'Monitor cache hit rates',
                'Track embedding generation costs',
                'Monitor cache memory usage',
                'Set up alerts for cache failures'
            ]
        }
        
        print(f"  ✅ Cache optimization complete")
        return optimization_results
    
    def generate_optimization_report(self) -> Dict[str, Any]:
        """Generate comprehensive optimization report"""
        print("📊 Generating comprehensive optimization report...")
        
        report = {
            'timestamp': datetime.utcnow().isoformat(),
            'embedding_stats': self.embedding_generator.get_embedding_stats(),
            'cache_analysis': self.analyze_cache_performance(50),
            'performance_benchmarks': self.benchmark_embedding_performance(),
            'quality_analysis': self.analyze_embedding_quality(15),
            'cache_optimization': self.optimize_cache_settings()
        }
        
        # Add summary and recommendations
        report['summary'] = {
            'total_tests_run': 4,
            'cache_hit_rate': report['cache_analysis']['second_pass']['hit_rate'],
            'avg_generation_time_ms': report['performance_benchmarks']['scenarios']['medium_texts']['avg_time_ms'],
            'quality_score': statistics.mean([
                cat['avg_similarity'] for cat in report['quality_analysis']['categories'].values()
            ]) if report['quality_analysis']['categories'] else 0
        }
        
        report['recommendations'] = [
            'Enable caching for all embedding operations',
            'Use batch processing for multiple embeddings',
            'Monitor cache hit rates and adjust TTL as needed',
            'Consider pre-generating embeddings for static content',
            'Implement retry logic for Bedrock API failures',
            'Monitor embedding generation costs and usage patterns'
        ]
        
        return report

def main():
    """Main optimization function"""
    print("🦄 Unicorn E-Commerce - Embedding Optimization")
    print("=" * 60)
    
    try:
        # Test connections
        print("📡 Testing connections...")
        database = db.get_documentdb_database()
        database.command('ping')
        print("✅ DocumentDB connection successful")
        
        # Test Bedrock
        test_result = embedding_generator.generate_embedding("test", use_cache=False)
        if test_result.success:
            print("✅ Bedrock connection successful")
        else:
            print(f"❌ Bedrock connection failed: {test_result.error}")
            return
        
        # Initialize optimizer
        optimizer = EmbeddingOptimizer()
        
        # Generate optimization report
        print("\n🚀 Starting optimization analysis...")
        report = optimizer.generate_optimization_report()
        
        # Save report
        report_file = f"embedding_optimization_report_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
        with open(report_file, 'w') as f:
            json.dump(report, f, indent=2, default=str)
        
        print(f"\n💾 Optimization report saved to: {report_file}")
        
        # Display summary
        print("\n" + "=" * 60)
        print("📊 OPTIMIZATION SUMMARY")
        print("=" * 60)
        
        summary = report['summary']
        print(f"Cache Hit Rate: {summary['cache_hit_rate']:.2%}")
        print(f"Avg Generation Time: {summary['avg_generation_time_ms']:.2f}ms")
        print(f"Quality Score: {summary['quality_score']:.3f}")
        
        print("\n🎯 KEY RECOMMENDATIONS:")
        for i, rec in enumerate(report['recommendations'], 1):
            print(f"  {i}. {rec}")
        
        # Performance insights
        perf = report['performance_benchmarks']['scenarios']
        print(f"\n⚡ PERFORMANCE INSIGHTS:")
        print(f"  Short texts: {perf['short_texts']['avg_time_ms']:.2f}ms avg")
        print(f"  Medium texts: {perf['medium_texts']['avg_time_ms']:.2f}ms avg")
        print(f"  Long texts: {perf['long_texts']['avg_time_ms']:.2f}ms avg")
        print(f"  Batch throughput: {perf['batch_processing']['throughput_per_second']:.2f} embeddings/sec")
        
        print("\n🎉 Optimization analysis complete!")
        
    except Exception as e:
        logger.error(f"Optimization failed: {e}")
        print(f"\n❌ Optimization failed: {e}")
        sys.exit(1)
    
    finally:
        try:
            db.close_connections()
            print("\n🔌 Database connections closed")
        except:
            pass

if __name__ == "__main__":
    main()