"""
Vector Embedding Generation System for AWS NoSQL Workshop
Integrates with Amazon Bedrock Titan for text embeddings with caching and batch processing
"""
import boto3
import json
import logging
import time
from typing import List, Dict, Any, Optional, Union
from datetime import datetime, timedelta
import hashlib
import numpy as np
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
from dataclasses import dataclass

try:
    from .config import config
    from .database import cache_get, cache_set, get_cache_key
except ImportError:
    from config import config
    from database import cache_get, cache_set, get_cache_key

logger = logging.getLogger(__name__)

@dataclass
class EmbeddingRequest:
    """Data class for embedding requests"""
    text: str
    identifier: str
    metadata: Optional[Dict[str, Any]] = None

@dataclass
class EmbeddingResult:
    """Data class for embedding results"""
    identifier: str
    embedding: List[float]
    text: str
    success: bool
    error: Optional[str] = None
    cached: bool = False
    processing_time_ms: float = 0.0

class BedrockEmbeddingGenerator:
    """Manages vector embedding generation using Amazon Bedrock Titan"""
    
    def __init__(self):
        self.bedrock_client = boto3.client('bedrock-runtime', region_name=config.AWS_REGION)
        self.model_id = config.BEDROCK_EMBEDDING_MODEL_ID
        self.max_retries = 3
        self.retry_delay = 1.0  # seconds
        self.rate_limit_delay = 0.1  # seconds between requests
        self.max_concurrent_requests = 10
        self.cache_ttl = 86400 * 7  # 7 days for embeddings
        
        # Thread-local storage for rate limiting
        self._local = threading.local()
        
        logger.info(f"Initialized Bedrock embedding generator with model: {self.model_id}")
    
    def _get_text_hash(self, text: str) -> str:
        """Generate hash for text to use as cache key"""
        return hashlib.sha256(text.encode('utf-8')).hexdigest()[:16]
    
    def _get_embedding_from_cache(self, text: str) -> Optional[List[float]]:
        """Get embedding from cache if available"""
        try:
            text_hash = self._get_text_hash(text)
            cache_key = get_cache_key("embedding", text_hash)
            cached_result = cache_get(cache_key)
            
            if cached_result:
                embedding_data = json.loads(cached_result)
                return embedding_data.get('embedding')
                
        except Exception as e:
            logger.warning(f"Failed to get embedding from cache: {e}")
        
        return None
    
    def _cache_embedding(self, text: str, embedding: List[float]) -> bool:
        """Cache embedding result"""
        try:
            text_hash = self._get_text_hash(text)
            cache_key = get_cache_key("embedding", text_hash)
            
            embedding_data = {
                'embedding': embedding,
                'text_length': len(text),
                'created_at': datetime.utcnow().isoformat(),
                'model_id': self.model_id
            }
            
            return cache_set(cache_key, json.dumps(embedding_data), self.cache_ttl)
            
        except Exception as e:
            logger.warning(f"Failed to cache embedding: {e}")
            return False
    
    def _rate_limit(self):
        """Simple rate limiting to avoid overwhelming Bedrock"""
        if not hasattr(self._local, 'last_request_time'):
            self._local.last_request_time = 0
        
        current_time = time.time()
        time_since_last = current_time - self._local.last_request_time
        
        if time_since_last < self.rate_limit_delay:
            sleep_time = self.rate_limit_delay - time_since_last
            time.sleep(sleep_time)
        
        self._local.last_request_time = time.time()
    
    def _call_bedrock_with_retry(self, text: str) -> Optional[List[float]]:
        """Call Bedrock API with retry logic"""
        for attempt in range(self.max_retries):
            try:
                self._rate_limit()
                
                # Prepare request body for Titan embedding model
                request_body = {
                    "inputText": text
                }
                
                # Call Bedrock
                response = self.bedrock_client.invoke_model(
                    modelId=self.model_id,
                    body=json.dumps(request_body),
                    contentType='application/json',
                    accept='application/json'
                )
                
                # Parse response
                response_body = json.loads(response['body'].read())
                embedding = response_body.get('embedding')
                
                if embedding and isinstance(embedding, list):
                    return embedding
                else:
                    logger.error(f"Invalid embedding response format: {response_body}")
                    return None
                    
            except Exception as e:
                logger.warning(f"Bedrock API call attempt {attempt + 1} failed: {e}")
                
                if attempt < self.max_retries - 1:
                    # Exponential backoff
                    sleep_time = self.retry_delay * (2 ** attempt)
                    time.sleep(sleep_time)
                else:
                    logger.error(f"All Bedrock API attempts failed for text: {text[:100]}...")
                    return None
        
        return None
    
    def generate_embedding(self, text: str, use_cache: bool = True) -> EmbeddingResult:
        """
        Generate embedding for a single text
        
        Args:
            text: Text to generate embedding for
            use_cache: Whether to use caching
            
        Returns:
            EmbeddingResult with embedding and metadata
        """
        start_time = time.time()
        
        # Input validation
        if not text or not text.strip():
            return EmbeddingResult(
                identifier="",
                embedding=[],
                text=text,
                success=False,
                error="Empty or invalid text provided"
            )
        
        # Truncate text if too long (Titan has limits)
        max_length = 8000  # Conservative limit for Titan
        if len(text) > max_length:
            text = text[:max_length]
            logger.warning(f"Text truncated to {max_length} characters")
        
        # Try cache first
        embedding = None
        cached = False
        
        if use_cache:
            embedding = self._get_embedding_from_cache(text)
            if embedding:
                cached = True
                logger.debug("Retrieved embedding from cache")
        
        # Generate embedding if not cached
        if embedding is None:
            embedding = self._call_bedrock_with_retry(text)
            
            if embedding and use_cache:
                self._cache_embedding(text, embedding)
        
        processing_time = (time.time() - start_time) * 1000
        
        if embedding:
            return EmbeddingResult(
                identifier=self._get_text_hash(text),
                embedding=embedding,
                text=text,
                success=True,
                cached=cached,
                processing_time_ms=processing_time
            )
        else:
            return EmbeddingResult(
                identifier=self._get_text_hash(text),
                embedding=[],
                text=text,
                success=False,
                error="Failed to generate embedding",
                processing_time_ms=processing_time
            )
    
    def generate_embeddings_batch(
        self,
        requests: List[EmbeddingRequest],
        use_cache: bool = True,
        max_workers: Optional[int] = None
    ) -> List[EmbeddingResult]:
        """
        Generate embeddings for multiple texts in parallel
        
        Args:
            requests: List of EmbeddingRequest objects
            use_cache: Whether to use caching
            max_workers: Maximum number of concurrent workers
            
        Returns:
            List of EmbeddingResult objects
        """
        if not requests:
            return []
        
        max_workers = max_workers or min(self.max_concurrent_requests, len(requests))
        results = []
        
        logger.info(f"Processing {len(requests)} embedding requests with {max_workers} workers")
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all tasks
            future_to_request = {
                executor.submit(
                    self.generate_embedding,
                    request.text,
                    use_cache
                ): request for request in requests
            }
            
            # Collect results
            for future in as_completed(future_to_request):
                request = future_to_request[future]
                try:
                    result = future.result()
                    # Update identifier with original request identifier
                    result.identifier = request.identifier
                    results.append(result)
                    
                except Exception as e:
                    logger.error(f"Failed to process embedding request {request.identifier}: {e}")
                    results.append(EmbeddingResult(
                        identifier=request.identifier,
                        embedding=[],
                        text=request.text,
                        success=False,
                        error=str(e)
                    ))
        
        # Sort results by original order
        request_order = {req.identifier: i for i, req in enumerate(requests)}
        results.sort(key=lambda r: request_order.get(r.identifier, float('inf')))
        
        successful = sum(1 for r in results if r.success)
        cached = sum(1 for r in results if r.cached)
        
        logger.info(f"Batch processing complete: {successful}/{len(results)} successful, {cached} from cache")
        
        return results
    
    def generate_product_embeddings(self, products: List[Dict[str, Any]]) -> List[EmbeddingResult]:
        """Generate embeddings for product descriptions"""
        requests = []
        
        for product in products:
            # Combine title and description for better semantic representation
            text_parts = []
            
            if product.get('title'):
                text_parts.append(product['title'])
            
            if product.get('description'):
                text_parts.append(product['description'])
            
            if product.get('category'):
                text_parts.append(f"Category: {product['category']}")
            
            if product.get('tags'):
                tags = product['tags'] if isinstance(product['tags'], list) else [product['tags']]
                text_parts.append(f"Tags: {', '.join(tags)}")
            
            combined_text = '. '.join(text_parts)
            
            requests.append(EmbeddingRequest(
                text=combined_text,
                identifier=product.get('product_id', str(product.get('_id', ''))),
                metadata={'type': 'product', 'category': product.get('category')}
            ))
        
        return self.generate_embeddings_batch(requests)
    
    def generate_review_embeddings(self, reviews: List[Dict[str, Any]]) -> List[EmbeddingResult]:
        """Generate embeddings for review content"""
        requests = []
        
        for review in reviews:
            # Combine title and content for better semantic representation
            text_parts = []
            
            if review.get('title'):
                text_parts.append(review['title'])
            
            if review.get('content'):
                text_parts.append(review['content'])
            
            # Add rating context
            if review.get('rating'):
                rating_text = f"Rating: {review['rating']} stars"
                text_parts.append(rating_text)
            
            combined_text = '. '.join(text_parts)
            
            requests.append(EmbeddingRequest(
                text=combined_text,
                identifier=review.get('review_id', str(review.get('_id', ''))),
                metadata={'type': 'review', 'product_id': review.get('product_id')}
            ))
        
        return self.generate_embeddings_batch(requests)
    
    def generate_knowledge_base_embeddings(self, articles: List[Dict[str, Any]]) -> List[EmbeddingResult]:
        """Generate embeddings for knowledge base articles"""
        requests = []
        
        for article in articles:
            # Combine title and content
            text_parts = []
            
            if article.get('title'):
                text_parts.append(article['title'])
            
            if article.get('content'):
                text_parts.append(article['content'])
            
            if article.get('category'):
                text_parts.append(f"Category: {article['category']}")
            
            combined_text = '. '.join(text_parts)
            
            requests.append(EmbeddingRequest(
                text=combined_text,
                identifier=article.get('article_id', str(article.get('_id', ''))),
                metadata={'type': 'knowledge_base', 'category': article.get('category')}
            ))
        
        return self.generate_embeddings_batch(requests)
    
    def get_embedding_stats(self) -> Dict[str, Any]:
        """Get statistics about embedding generation"""
        # This would typically query cache or database for stats
        # For now, return basic info
        return {
            'model_id': self.model_id,
            'cache_ttl_hours': self.cache_ttl / 3600,
            'max_concurrent_requests': self.max_concurrent_requests,
            'rate_limit_delay_ms': self.rate_limit_delay * 1000,
            'max_retries': self.max_retries
        }

# Global embedding generator instance
embedding_generator = BedrockEmbeddingGenerator()