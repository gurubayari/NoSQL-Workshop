"""
Real-time embedding generation utilities for new content
Handles embedding generation for new products, reviews, and knowledge base articles
"""
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime

try:
    from .embeddings import embedding_generator, EmbeddingRequest
    from .database import get_documentdb_collection
except ImportError:
    from embeddings import embedding_generator, EmbeddingRequest
    from database import get_documentdb_collection

logger = logging.getLogger(__name__)

class RealtimeEmbeddingService:
    """Service for generating embeddings in real-time for new content"""
    
    def __init__(self):
        self.embedding_generator = embedding_generator
    
    def add_product_with_embedding(self, product_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Add a new product with generated embedding
        
        Args:
            product_data: Product data dictionary
            
        Returns:
            Result dictionary with success status and product_id
        """
        try:
            # Generate embedding for product
            embedding_result = self.embedding_generator.generate_product_embeddings([product_data])
            
            if not embedding_result or not embedding_result[0].success:
                error_msg = embedding_result[0].error if embedding_result else "Failed to generate embedding"
                logger.error(f"Failed to generate product embedding: {error_msg}")
                return {
                    'success': False,
                    'error': f"Failed to generate embedding: {error_msg}",
                    'product_id': product_data.get('product_id')
                }
            
            # Add embedding to product data
            product_data['description_embedding'] = embedding_result[0].embedding
            product_data['description_embedding_metadata'] = {
                'generated_at': datetime.utcnow(),
                'model_id': self.embedding_generator.model_id,
                'text_length': len(embedding_result[0].text),
                'cached': embedding_result[0].cached,
                'processing_time_ms': embedding_result[0].processing_time_ms
            }
            
            # Insert product into DocumentDB
            products_collection = get_documentdb_collection('products')
            insert_result = products_collection.insert_one(product_data)
            
            logger.info(f"Added product with embedding: {product_data.get('product_id')}")
            
            return {
                'success': True,
                'product_id': product_data.get('product_id'),
                'document_id': str(insert_result.inserted_id),
                'embedding_cached': embedding_result[0].cached,
                'processing_time_ms': embedding_result[0].processing_time_ms
            }
            
        except Exception as e:
            logger.error(f"Failed to add product with embedding: {e}")
            return {
                'success': False,
                'error': str(e),
                'product_id': product_data.get('product_id')
            }
    
    def add_review_with_embedding(self, review_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Add a new review with generated embedding
        
        Args:
            review_data: Review data dictionary
            
        Returns:
            Result dictionary with success status and review_id
        """
        try:
            # Generate embedding for review
            embedding_result = self.embedding_generator.generate_review_embeddings([review_data])
            
            if not embedding_result or not embedding_result[0].success:
                error_msg = embedding_result[0].error if embedding_result else "Failed to generate embedding"
                logger.error(f"Failed to generate review embedding: {error_msg}")
                return {
                    'success': False,
                    'error': f"Failed to generate embedding: {error_msg}",
                    'review_id': review_data.get('review_id')
                }
            
            # Add embedding to review data
            review_data['content_embedding'] = embedding_result[0].embedding
            review_data['content_embedding_metadata'] = {
                'generated_at': datetime.utcnow(),
                'model_id': self.embedding_generator.model_id,
                'text_length': len(embedding_result[0].text),
                'cached': embedding_result[0].cached,
                'processing_time_ms': embedding_result[0].processing_time_ms
            }
            
            # Insert review into DocumentDB
            reviews_collection = get_documentdb_collection('reviews')
            insert_result = reviews_collection.insert_one(review_data)
            
            logger.info(f"Added review with embedding: {review_data.get('review_id')}")
            
            return {
                'success': True,
                'review_id': review_data.get('review_id'),
                'document_id': str(insert_result.inserted_id),
                'embedding_cached': embedding_result[0].cached,
                'processing_time_ms': embedding_result[0].processing_time_ms
            }
            
        except Exception as e:
            logger.error(f"Failed to add review with embedding: {e}")
            return {
                'success': False,
                'error': str(e),
                'review_id': review_data.get('review_id')
            }
    
    def add_knowledge_base_article_with_embedding(self, article_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Add a new knowledge base article with generated embedding
        
        Args:
            article_data: Article data dictionary
            
        Returns:
            Result dictionary with success status and article_id
        """
        try:
            # Generate embedding for article
            embedding_result = self.embedding_generator.generate_knowledge_base_embeddings([article_data])
            
            if not embedding_result or not embedding_result[0].success:
                error_msg = embedding_result[0].error if embedding_result else "Failed to generate embedding"
                logger.error(f"Failed to generate knowledge base embedding: {error_msg}")
                return {
                    'success': False,
                    'error': f"Failed to generate embedding: {error_msg}",
                    'article_id': article_data.get('article_id')
                }
            
            # Add embedding to article data
            article_data['content_embedding'] = embedding_result[0].embedding
            article_data['content_embedding_metadata'] = {
                'generated_at': datetime.utcnow(),
                'model_id': self.embedding_generator.model_id,
                'text_length': len(embedding_result[0].text),
                'cached': embedding_result[0].cached,
                'processing_time_ms': embedding_result[0].processing_time_ms
            }
            
            # Insert article into DocumentDB
            kb_collection = get_documentdb_collection('knowledge_base')
            insert_result = kb_collection.insert_one(article_data)
            
            logger.info(f"Added knowledge base article with embedding: {article_data.get('article_id')}")
            
            return {
                'success': True,
                'article_id': article_data.get('article_id'),
                'document_id': str(insert_result.inserted_id),
                'embedding_cached': embedding_result[0].cached,
                'processing_time_ms': embedding_result[0].processing_time_ms
            }
            
        except Exception as e:
            logger.error(f"Failed to add knowledge base article with embedding: {e}")
            return {
                'success': False,
                'error': str(e),
                'article_id': article_data.get('article_id')
            }
    
    def update_product_embedding(self, product_id: str, updated_fields: Dict[str, Any]) -> Dict[str, Any]:
        """
        Update product and regenerate embedding if content changed
        
        Args:
            product_id: Product ID to update
            updated_fields: Fields to update
            
        Returns:
            Result dictionary with success status
        """
        try:
            products_collection = get_documentdb_collection('products')
            
            # Check if embedding-relevant fields changed
            embedding_fields = ['title', 'description', 'category', 'tags']
            needs_embedding_update = any(field in updated_fields for field in embedding_fields)
            
            if needs_embedding_update:
                # Get current product data
                current_product = products_collection.find_one({'product_id': product_id})
                if not current_product:
                    return {
                        'success': False,
                        'error': f"Product {product_id} not found"
                    }
                
                # Merge updated fields
                updated_product = {**current_product, **updated_fields}
                
                # Generate new embedding
                embedding_result = self.embedding_generator.generate_product_embeddings([updated_product])
                
                if embedding_result and embedding_result[0].success:
                    updated_fields['description_embedding'] = embedding_result[0].embedding
                    updated_fields['description_embedding_metadata'] = {
                        'generated_at': datetime.utcnow(),
                        'model_id': self.embedding_generator.model_id,
                        'text_length': len(embedding_result[0].text),
                        'cached': embedding_result[0].cached,
                        'processing_time_ms': embedding_result[0].processing_time_ms
                    }
                    
                    logger.info(f"Regenerated embedding for updated product: {product_id}")
                else:
                    logger.warning(f"Failed to regenerate embedding for product {product_id}, updating without embedding")
            
            # Update product
            update_result = products_collection.update_one(
                {'product_id': product_id},
                {'$set': updated_fields}
            )
            
            if update_result.modified_count > 0:
                return {
                    'success': True,
                    'product_id': product_id,
                    'embedding_updated': needs_embedding_update,
                    'fields_updated': list(updated_fields.keys())
                }
            else:
                return {
                    'success': False,
                    'error': f"No product updated for ID: {product_id}"
                }
                
        except Exception as e:
            logger.error(f"Failed to update product {product_id}: {e}")
            return {
                'success': False,
                'error': str(e),
                'product_id': product_id
            }
    
    def update_review_embedding(self, review_id: str, updated_fields: Dict[str, Any]) -> Dict[str, Any]:
        """
        Update review and regenerate embedding if content changed
        
        Args:
            review_id: Review ID to update
            updated_fields: Fields to update
            
        Returns:
            Result dictionary with success status
        """
        try:
            reviews_collection = get_documentdb_collection('reviews')
            
            # Check if embedding-relevant fields changed
            embedding_fields = ['title', 'content', 'rating']
            needs_embedding_update = any(field in updated_fields for field in embedding_fields)
            
            if needs_embedding_update:
                # Get current review data
                current_review = reviews_collection.find_one({'review_id': review_id})
                if not current_review:
                    return {
                        'success': False,
                        'error': f"Review {review_id} not found"
                    }
                
                # Merge updated fields
                updated_review = {**current_review, **updated_fields}
                
                # Generate new embedding
                embedding_result = self.embedding_generator.generate_review_embeddings([updated_review])
                
                if embedding_result and embedding_result[0].success:
                    updated_fields['content_embedding'] = embedding_result[0].embedding
                    updated_fields['content_embedding_metadata'] = {
                        'generated_at': datetime.utcnow(),
                        'model_id': self.embedding_generator.model_id,
                        'text_length': len(embedding_result[0].text),
                        'cached': embedding_result[0].cached,
                        'processing_time_ms': embedding_result[0].processing_time_ms
                    }
                    
                    logger.info(f"Regenerated embedding for updated review: {review_id}")
                else:
                    logger.warning(f"Failed to regenerate embedding for review {review_id}, updating without embedding")
            
            # Update review
            update_result = reviews_collection.update_one(
                {'review_id': review_id},
                {'$set': updated_fields}
            )
            
            if update_result.modified_count > 0:
                return {
                    'success': True,
                    'review_id': review_id,
                    'embedding_updated': needs_embedding_update,
                    'fields_updated': list(updated_fields.keys())
                }
            else:
                return {
                    'success': False,
                    'error': f"No review updated for ID: {review_id}"
                }
                
        except Exception as e:
            logger.error(f"Failed to update review {review_id}: {e}")
            return {
                'success': False,
                'error': str(e),
                'review_id': review_id
            }
    
    def generate_query_embedding(self, query_text: str) -> Dict[str, Any]:
        """
        Generate embedding for search query
        
        Args:
            query_text: Search query text
            
        Returns:
            Result dictionary with embedding and metadata
        """
        try:
            embedding_result = self.embedding_generator.generate_embedding(query_text, use_cache=True)
            
            if embedding_result.success:
                return {
                    'success': True,
                    'embedding': embedding_result.embedding,
                    'query_text': query_text,
                    'cached': embedding_result.cached,
                    'processing_time_ms': embedding_result.processing_time_ms
                }
            else:
                return {
                    'success': False,
                    'error': embedding_result.error,
                    'query_text': query_text
                }
                
        except Exception as e:
            logger.error(f"Failed to generate query embedding: {e}")
            return {
                'success': False,
                'error': str(e),
                'query_text': query_text
            }

# Global realtime embedding service instance
realtime_embedding_service = RealtimeEmbeddingService()