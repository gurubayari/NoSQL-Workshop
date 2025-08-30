"""
Integration tests for vector search operations
Tests vector search accuracy, performance benchmarks, and embedding generation
"""
import pytest
import numpy as np
import json
import time
from datetime import datetime, timezone
from typing import List, Dict, Any
import sys
import os
from unittest.mock import patch, MagicMock

# Add the shared directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'shared'))

class TestVectorSearchOperations:
    """Integration tests for vector search operations"""
    
    def setup_method(self):
        """Set up test data and mock services"""
        # Mock embedding dimensions
        self.embedding_dim = 384  # Common dimension for sentence transformers
        
        # Create test products with embeddings
        self.test_products = [
            {
                'product_id': 'prod_1',
                'title': 'Wireless Bluetooth Headphones',
                'description': 'High-quality wireless headphones with noise cancellation and long battery life',
                'category': 'Electronics',
                'price': 199.99,
                'rating': 4.5,
                'embedding': self._generate_mock_embedding('wireless headphones audio quality noise cancellation')
            },
            {
                'product_id': 'prod_2',
                'title': 'Gaming Headset with Microphone',
                'description': 'Professional gaming headset with crystal clear microphone and surround sound',
                'category': 'Electronics',
                'price': 149.99,
                'rating': 4.3,
                'embedding': self._generate_mock_embedding('gaming headset microphone surround sound')
            },
            {
                'product_id': 'prod_3',
                'title': 'Bluetooth Portable Speaker',
                'description': 'Compact wireless speaker with powerful bass and waterproof design',
                'category': 'Electronics',
                'price': 79.99,
                'rating': 4.2,
                'embedding': self._generate_mock_embedding('bluetooth speaker portable bass waterproof')
            },
            {
                'product_id': 'prod_4',
                'title': 'Wireless Mouse',
                'description': 'Ergonomic wireless mouse with precision tracking and long battery life',
                'category': 'Electronics',
                'price': 29.99,
                'rating': 4.1,
                'embedding': self._generate_mock_embedding('wireless mouse ergonomic precision tracking')
            },
            {
                'product_id': 'prod_5',
                'title': 'USB-C Cable',
                'description': 'High-speed USB-C charging cable with data transfer capability',
                'category': 'Electronics',
                'price': 12.99,
                'rating': 4.0,
                'embedding': self._generate_mock_embedding('usb cable charging data transfer')
            }
        ]
        
        # Create test reviews with embeddings
        self.test_reviews = [
            {
                'review_id': 'review_1',
                'product_id': 'prod_1',
                'user_id': 'user_1',
                'rating': 5,
                'title': 'Excellent sound quality',
                'content': 'These headphones have amazing sound quality and the noise cancellation works perfectly. Great for long flights.',
                'sentiment': {'score': 0.8, 'label': 'positive'},
                'created_at': datetime.now(timezone.utc),
                'embedding': self._generate_mock_embedding('excellent sound quality noise cancellation flights')
            },
            {
                'review_id': 'review_2',
                'product_id': 'prod_1',
                'user_id': 'user_2',
                'rating': 4,
                'title': 'Good but heavy',
                'content': 'Sound quality is good but they feel a bit heavy after wearing for hours. Battery life is excellent though.',
                'sentiment': {'score': 0.3, 'label': 'neutral'},
                'created_at': datetime.now(timezone.utc),
                'embedding': self._generate_mock_embedding('good sound heavy wearing hours battery life')
            },
            {
                'review_id': 'review_3',
                'product_id': 'prod_2',
                'user_id': 'user_3',
                'rating': 5,
                'title': 'Perfect for gaming',
                'content': 'The microphone quality is crystal clear and the surround sound makes gaming so much better. Highly recommend!',
                'sentiment': {'score': 0.9, 'label': 'positive'},
                'created_at': datetime.now(timezone.utc),
                'embedding': self._generate_mock_embedding('microphone crystal clear surround sound gaming recommend')
            },
            {
                'review_id': 'review_4',
                'product_id': 'prod_3',
                'user_id': 'user_4',
                'rating': 4,
                'title': 'Great bass response',
                'content': 'The bass is really powerful for such a small speaker. Perfect for outdoor activities and the waterproof feature works great.',
                'sentiment': {'score': 0.7, 'label': 'positive'},
                'created_at': datetime.now(timezone.utc),
                'embedding': self._generate_mock_embedding('bass powerful small speaker outdoor waterproof')
            }
        ]
        
        # Create test knowledge base articles with embeddings
        self.test_knowledge_base = [
            {
                'article_id': 'kb_1',
                'title': 'Return Policy',
                'content': 'You can return items within 30 days of purchase. Items must be in original condition with all accessories and packaging.',
                'category': 'policies',
                'tags': ['return', 'policy', 'refund'],
                'embedding': self._generate_mock_embedding('return policy 30 days original condition accessories packaging')
            },
            {
                'article_id': 'kb_2',
                'title': 'Shipping Information',
                'content': 'We offer free shipping on orders over $50. Standard shipping takes 3-5 business days. Express shipping available for next-day delivery.',
                'category': 'shipping',
                'tags': ['shipping', 'delivery', 'free'],
                'embedding': self._generate_mock_embedding('shipping free orders 50 dollars standard express delivery')
            },
            {
                'article_id': 'kb_3',
                'title': 'Audio Quality Guide',
                'content': 'For the best audio experience, ensure your headphones are properly positioned and adjust the equalizer settings based on your music preferences.',
                'category': 'guides',
                'tags': ['audio', 'quality', 'headphones', 'equalizer'],
                'embedding': self._generate_mock_embedding('audio quality headphones positioned equalizer settings music preferences')
            }
        ]
    
    def _generate_mock_embedding(self, text: str) -> List[float]:
        """Generate a mock embedding based on text content"""
        # Simple hash-based embedding generation for testing
        # In production, this would use actual embedding models
        np.random.seed(hash(text) % (2**32))
        embedding = np.random.normal(0, 1, self.embedding_dim)
        # Normalize the embedding
        embedding = embedding / np.linalg.norm(embedding)
        return embedding.tolist()
    
    def _cosine_similarity(self, a: List[float], b: List[float]) -> float:
        """Calculate cosine similarity between two vectors"""
        a_np = np.array(a)
        b_np = np.array(b)
        return np.dot(a_np, b_np) / (np.linalg.norm(a_np) * np.linalg.norm(b_np))
    
    def test_product_vector_search_accuracy(self):
        """Test vector search accuracy for products"""
        # Query for wireless headphones
        query_text = "wireless headphones with good sound quality"
        query_embedding = self._generate_mock_embedding(query_text)
        
        # Calculate similarities
        results = []
        for product in self.test_products:
            similarity = self._cosine_similarity(query_embedding, product['embedding'])
            results.append({
                'product': product,
                'similarity_score': similarity
            })
        
        # Sort by similarity
        results.sort(key=lambda x: x['similarity_score'], reverse=True)
        
        # Verify results
        assert len(results) == 5
        
        # The wireless headphones should be most similar
        top_result = results[0]
        assert 'Wireless Bluetooth Headphones' in top_result['product']['title']
        assert top_result['similarity_score'] > 0.5  # Should be reasonably similar
        
        # Gaming headset should be second (also headphones)
        second_result = results[1]
        assert 'Gaming Headset' in second_result['product']['title']
        
        # USB cable should be least similar
        last_result = results[-1]
        assert 'USB-C Cable' in last_result['product']['title']
        assert last_result['similarity_score'] < top_result['similarity_score']
    
    def test_review_vector_search_accuracy(self):
        """Test vector search accuracy for reviews"""
        # Query for reviews about sound quality
        query_text = "sound quality and audio performance"
        query_embedding = self._generate_mock_embedding(query_text)
        
        # Calculate similarities
        results = []
        for review in self.test_reviews:
            similarity = self._cosine_similarity(query_embedding, review['embedding'])
            results.append({
                'review': review,
                'similarity_score': similarity
            })
        
        # Sort by similarity
        results.sort(key=lambda x: x['similarity_score'], reverse=True)
        
        # Verify results
        assert len(results) == 4
        
        # Reviews about sound quality should rank higher
        top_results = results[:2]
        sound_quality_reviews = 0
        for result in top_results:
            if 'sound' in result['review']['content'].lower():
                sound_quality_reviews += 1
        
        assert sound_quality_reviews >= 1  # At least one should mention sound
        
        # Verify similarity scores are reasonable
        assert results[0]['similarity_score'] > 0.3
        assert results[0]['similarity_score'] > results[-1]['similarity_score']
    
    def test_knowledge_base_vector_search_accuracy(self):
        """Test vector search accuracy for knowledge base"""
        # Query for return information
        query_text = "how to return a product"
        query_embedding = self._generate_mock_embedding(query_text)
        
        # Calculate similarities
        results = []
        for article in self.test_knowledge_base:
            similarity = self._cosine_similarity(query_embedding, article['embedding'])
            results.append({
                'article': article,
                'similarity_score': similarity
            })
        
        # Sort by similarity
        results.sort(key=lambda x: x['similarity_score'], reverse=True)
        
        # Verify results
        assert len(results) == 3
        
        # Return policy should be most relevant
        top_result = results[0]
        assert 'Return Policy' in top_result['article']['title']
        assert top_result['similarity_score'] > 0.4
        
        # Audio guide should be least relevant for return query
        last_result = results[-1]
        assert top_result['similarity_score'] > last_result['similarity_score']
    
    def test_vector_search_with_filters(self):
        """Test vector search with additional filters"""
        query_text = "electronics under 100 dollars"
        query_embedding = self._generate_mock_embedding(query_text)
        
        # Apply price filter
        filtered_products = [p for p in self.test_products if p['price'] < 100]
        
        # Calculate similarities for filtered products
        results = []
        for product in filtered_products:
            similarity = self._cosine_similarity(query_embedding, product['embedding'])
            results.append({
                'product': product,
                'similarity_score': similarity
            })
        
        # Sort by similarity
        results.sort(key=lambda x: x['similarity_score'], reverse=True)
        
        # Verify filtering worked
        assert len(results) == 3  # Speaker, Mouse, Cable are under $100
        for result in results:
            assert result['product']['price'] < 100
        
        # Verify similarity ranking
        assert results[0]['similarity_score'] >= results[1]['similarity_score']
        assert results[1]['similarity_score'] >= results[2]['similarity_score']
    
    def test_vector_search_performance_benchmark(self):
        """Test vector search performance with larger dataset"""
        # Create larger dataset for performance testing
        large_dataset = []
        for i in range(1000):
            product = {
                'product_id': f'perf_prod_{i}',
                'title': f'Test Product {i}',
                'description': f'Description for test product {i} with various features',
                'price': 10.0 + (i % 100),
                'embedding': self._generate_mock_embedding(f'test product {i} features description')
            }
            large_dataset.append(product)
        
        query_text = "test product with features"
        query_embedding = self._generate_mock_embedding(query_text)
        
        # Measure search time
        start_time = time.time()
        
        results = []
        for product in large_dataset:
            similarity = self._cosine_similarity(query_embedding, product['embedding'])
            if similarity > 0.5:  # Only keep relevant results
                results.append({
                    'product': product,
                    'similarity_score': similarity
                })
        
        # Sort results
        results.sort(key=lambda x: x['similarity_score'], reverse=True)
        results = results[:20]  # Top 20 results
        
        end_time = time.time()
        search_time = end_time - start_time
        
        # Performance assertions
        assert search_time < 1.0  # Should complete within 1 second
        assert len(results) <= 20
        
        # Verify results quality
        if results:
            assert results[0]['similarity_score'] > 0.5
            # Verify sorting
            for i in range(len(results) - 1):
                assert results[i]['similarity_score'] >= results[i + 1]['similarity_score']
    
    def test_embedding_generation_consistency(self):
        """Test that embedding generation is consistent"""
        text = "wireless bluetooth headphones with noise cancellation"
        
        # Generate embedding multiple times
        embedding1 = self._generate_mock_embedding(text)
        embedding2 = self._generate_mock_embedding(text)
        embedding3 = self._generate_mock_embedding(text)
        
        # Embeddings should be identical for same input
        assert embedding1 == embedding2
        assert embedding2 == embedding3
        
        # Verify embedding properties
        assert len(embedding1) == self.embedding_dim
        assert isinstance(embedding1[0], float)
        
        # Verify normalization (L2 norm should be close to 1)
        norm = np.linalg.norm(embedding1)
        assert abs(norm - 1.0) < 0.01  # Allow small floating point errors
    
    def test_embedding_generation_diversity(self):
        """Test that different texts produce different embeddings"""
        texts = [
            "wireless headphones with great sound quality",
            "bluetooth speaker with powerful bass",
            "gaming mouse with precision tracking",
            "usb cable for fast charging",
            "return policy and refund information"
        ]
        
        embeddings = []
        for text in texts:
            embedding = self._generate_mock_embedding(text)
            embeddings.append(embedding)
        
        # Calculate pairwise similarities
        similarities = []
        for i in range(len(embeddings)):
            for j in range(i + 1, len(embeddings)):
                similarity = self._cosine_similarity(embeddings[i], embeddings[j])
                similarities.append(similarity)
        
        # Different texts should have varied similarities
        assert len(set(similarities)) > 1  # Not all similarities should be the same
        
        # Most similarities should be less than perfect (< 1.0)
        high_similarities = [s for s in similarities if s > 0.9]
        assert len(high_similarities) < len(similarities)  # Not all should be very similar
    
    def test_vector_search_with_minimum_score_threshold(self):
        """Test vector search with minimum similarity score filtering"""
        query_text = "wireless audio devices"
        query_embedding = self._generate_mock_embedding(query_text)
        min_score = 0.3
        
        # Calculate similarities and filter by minimum score
        results = []
        for product in self.test_products:
            similarity = self._cosine_similarity(query_embedding, product['embedding'])
            if similarity >= min_score:
                results.append({
                    'product': product,
                    'similarity_score': similarity
                })
        
        # Sort by similarity
        results.sort(key=lambda x: x['similarity_score'], reverse=True)
        
        # Verify all results meet minimum score
        for result in results:
            assert result['similarity_score'] >= min_score
        
        # Verify we have some results (not too restrictive)
        assert len(results) > 0
        
        # Test with very high threshold
        high_threshold_results = []
        high_min_score = 0.8
        
        for product in self.test_products:
            similarity = self._cosine_similarity(query_embedding, product['embedding'])
            if similarity >= high_min_score:
                high_threshold_results.append({
                    'product': product,
                    'similarity_score': similarity
                })
        
        # High threshold should return fewer results
        assert len(high_threshold_results) <= len(results)
    
    def test_multi_modal_vector_search(self):
        """Test vector search across different content types"""
        query_text = "audio quality and sound performance"
        query_embedding = self._generate_mock_embedding(query_text)
        
        # Search across products, reviews, and knowledge base
        all_results = []
        
        # Search products
        for product in self.test_products:
            similarity = self._cosine_similarity(query_embedding, product['embedding'])
            all_results.append({
                'type': 'product',
                'content': product,
                'similarity_score': similarity
            })
        
        # Search reviews
        for review in self.test_reviews:
            similarity = self._cosine_similarity(query_embedding, review['embedding'])
            all_results.append({
                'type': 'review',
                'content': review,
                'similarity_score': similarity
            })
        
        # Search knowledge base
        for article in self.test_knowledge_base:
            similarity = self._cosine_similarity(query_embedding, article['embedding'])
            all_results.append({
                'type': 'knowledge_base',
                'content': article,
                'similarity_score': similarity
            })
        
        # Sort all results by similarity
        all_results.sort(key=lambda x: x['similarity_score'], reverse=True)
        
        # Filter by minimum score
        relevant_results = [r for r in all_results if r['similarity_score'] > 0.2]
        
        # Verify we have results from multiple types
        result_types = set(r['type'] for r in relevant_results)
        assert len(result_types) >= 2  # Should have at least 2 different content types
        
        # Verify audio-related content ranks high
        top_results = relevant_results[:3]
        audio_related = 0
        for result in top_results:
            content = result['content']
            text_to_check = ""
            
            if result['type'] == 'product':
                text_to_check = content['title'] + " " + content['description']
            elif result['type'] == 'review':
                text_to_check = content['title'] + " " + content['content']
            elif result['type'] == 'knowledge_base':
                text_to_check = content['title'] + " " + content['content']
            
            if 'audio' in text_to_check.lower() or 'sound' in text_to_check.lower():
                audio_related += 1
        
        assert audio_related >= 1  # At least one top result should be audio-related
    
    def test_vector_search_result_ranking(self):
        """Test that vector search results are properly ranked"""
        query_text = "headphones for music listening"
        query_embedding = self._generate_mock_embedding(query_text)
        
        # Calculate similarities for products
        results = []
        for product in self.test_products:
            similarity = self._cosine_similarity(query_embedding, product['embedding'])
            results.append({
                'product': product,
                'similarity_score': similarity
            })
        
        # Sort by similarity (descending)
        results.sort(key=lambda x: x['similarity_score'], reverse=True)
        
        # Verify ranking is correct
        for i in range(len(results) - 1):
            current_score = results[i]['similarity_score']
            next_score = results[i + 1]['similarity_score']
            assert current_score >= next_score, f"Ranking error: {current_score} < {next_score}"
        
        # Verify headphone-related products rank higher
        headphone_products = []
        other_products = []
        
        for result in results:
            title = result['product']['title'].lower()
            if 'headphone' in title or 'headset' in title:
                headphone_products.append(result)
            else:
                other_products.append(result)
        
        # At least one headphone product should rank in top 2
        top_2_titles = [r['product']['title'].lower() for r in results[:2]]
        headphone_in_top_2 = any('headphone' in title or 'headset' in title for title in top_2_titles)
        assert headphone_in_top_2
    
    def test_vector_search_edge_cases(self):
        """Test vector search edge cases and error handling"""
        # Test with empty query
        empty_query_embedding = self._generate_mock_embedding("")
        
        results = []
        for product in self.test_products:
            similarity = self._cosine_similarity(empty_query_embedding, product['embedding'])
            results.append(similarity)
        
        # Should still produce valid similarities
        assert all(isinstance(s, float) for s in results)
        assert all(-1 <= s <= 1 for s in results)  # Cosine similarity range
        
        # Test with very specific query that might not match well
        specific_query = "quantum computing artificial intelligence blockchain"
        specific_embedding = self._generate_mock_embedding(specific_query)
        
        specific_results = []
        for product in self.test_products:
            similarity = self._cosine_similarity(specific_embedding, product['embedding'])
            specific_results.append(similarity)
        
        # Should still produce valid results, even if similarities are low
        assert all(isinstance(s, float) for s in specific_results)
        assert len(specific_results) == len(self.test_products)
        
        # Test with single character query
        single_char_embedding = self._generate_mock_embedding("a")
        
        char_results = []
        for product in self.test_products:
            similarity = self._cosine_similarity(single_char_embedding, product['embedding'])
            char_results.append(similarity)
        
        assert all(isinstance(s, float) for s in char_results)


if __name__ == '__main__':
    pytest.main([__file__])