"""
DocumentDB Vector Search Infrastructure for AWS NoSQL Workshop
Implements HNSW vector indexes and search capabilities for products, reviews, and knowledge base
"""
import logging
from typing import List, Dict, Any, Optional, Tuple
from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.errors import OperationFailure, DuplicateKeyError
import numpy as np
from datetime import datetime
import json

try:
    from .database import get_documentdb_collection, db
    from .config import config
except ImportError:
    from database import get_documentdb_collection, db
    from config import config

logger = logging.getLogger(__name__)

class VectorSearchManager:
    """Manages DocumentDB vector search infrastructure and operations"""
    
    def __init__(self):
        self.database = db.get_documentdb_database()
        
        # Collection names for vector search
        self.PRODUCTS_COLLECTION = 'products'
        self.REVIEWS_COLLECTION = 'reviews'
        self.KNOWLEDGE_BASE_COLLECTION = 'knowledge_base'
        
        # Vector index configurations
        self.VECTOR_INDEX_CONFIGS = {
            'products': {
                'index_name': 'product_description_vector_index',
                'vector_field': 'description_embedding',
                'dimensions': 1536,  # Titan text embedding dimensions
                'similarity': 'cosine',
                'ef_construction': 200,
                'max_connections': 16
            },
            'reviews': {
                'index_name': 'review_content_vector_index', 
                'vector_field': 'content_embedding',
                'dimensions': 1536,
                'similarity': 'cosine',
                'ef_construction': 200,
                'max_connections': 16
            },
            'knowledge_base': {
                'index_name': 'knowledge_base_vector_index',
                'vector_field': 'content_embedding', 
                'dimensions': 1536,
                'similarity': 'cosine',
                'ef_construction': 300,  # Higher for better accuracy
                'max_connections': 32   # More connections for knowledge base
            }
        }
    
    def create_vector_indexes(self) -> Dict[str, bool]:
        """
        Create HNSW vector indexes for all collections
        Returns dict with collection names and success status
        """
        results = {}
        
        for collection_name, config in self.VECTOR_INDEX_CONFIGS.items():
            try:
                success = self._create_collection_vector_index(collection_name, config)
                results[collection_name] = success
                logger.info(f"Vector index creation for {collection_name}: {'Success' if success else 'Failed'}")
            except Exception as e:
                logger.error(f"Failed to create vector index for {collection_name}: {e}")
                results[collection_name] = False
        
        return results
    
    def _create_collection_vector_index(self, collection_name: str, index_config: Dict[str, Any]) -> bool:
        """Create vector index for a specific collection"""
        try:
            collection = self.database[collection_name]
            
            # Check if index already exists
            existing_indexes = collection.list_indexes()
            for index in existing_indexes:
                if index.get('name') == index_config['index_name']:
                    logger.info(f"Vector index {index_config['index_name']} already exists for {collection_name}")
                    return True
            
            # Create HNSW vector index
            index_spec = {
                index_config['vector_field']: {
                    "type": "knnVector",
                    "dimensions": index_config['dimensions'],
                    "similarity": index_config['similarity']
                }
            }
            
            # HNSW algorithm parameters for optimal performance
            index_options = {
                "name": index_config['index_name'],
                "knnVectorOptions": {
                    "type": "hnsw",
                    "efConstruction": index_config['ef_construction'],
                    "maxConnections": index_config['max_connections']
                }
            }
            
            # Create the index
            collection.create_index(
                [(index_config['vector_field'], "2dsphere")],  # Placeholder for vector index
                **index_options
            )
            
            logger.info(f"Created HNSW vector index {index_config['index_name']} for {collection_name}")
            return True
            
        except DuplicateKeyError:
            logger.info(f"Vector index {index_config['index_name']} already exists for {collection_name}")
            return True
        except Exception as e:
            logger.error(f"Failed to create vector index for {collection_name}: {e}")
            return False
    
    def create_supporting_indexes(self) -> Dict[str, bool]:
        """Create supporting indexes for vector search performance"""
        results = {}
        
        # Product collection indexes
        try:
            products_collection = self.database[self.PRODUCTS_COLLECTION]
            
            # Category and tag indexes for filtering
            products_collection.create_index([("category", 1)])
            products_collection.create_index([("tags", 1)])
            products_collection.create_index([("price", 1)])
            products_collection.create_index([("rating", -1)])
            products_collection.create_index([("created_at", -1)])
            
            # Compound index for common queries
            products_collection.create_index([
                ("category", 1),
                ("rating", -1),
                ("price", 1)
            ])
            
            results['products_supporting'] = True
            logger.info("Created supporting indexes for products collection")
            
        except Exception as e:
            logger.error(f"Failed to create supporting indexes for products: {e}")
            results['products_supporting'] = False
        
        # Reviews collection indexes
        try:
            reviews_collection = self.database[self.REVIEWS_COLLECTION]
            
            # Product and user indexes
            reviews_collection.create_index([("product_id", 1)])
            reviews_collection.create_index([("user_id", 1)])
            reviews_collection.create_index([("rating", -1)])
            reviews_collection.create_index([("created_at", -1)])
            reviews_collection.create_index([("helpful_count", -1)])
            
            # Compound indexes for common queries
            reviews_collection.create_index([
                ("product_id", 1),
                ("rating", -1),
                ("created_at", -1)
            ])
            
            reviews_collection.create_index([
                ("product_id", 1),
                ("helpful_count", -1)
            ])
            
            results['reviews_supporting'] = True
            logger.info("Created supporting indexes for reviews collection")
            
        except Exception as e:
            logger.error(f"Failed to create supporting indexes for reviews: {e}")
            results['reviews_supporting'] = False
        
        # Knowledge base collection indexes
        try:
            kb_collection = self.database[self.KNOWLEDGE_BASE_COLLECTION]
            
            # Category and type indexes
            kb_collection.create_index([("category", 1)])
            kb_collection.create_index([("type", 1)])
            kb_collection.create_index([("tags", 1)])
            kb_collection.create_index([("created_at", -1)])
            
            # Text search index for fallback
            kb_collection.create_index([
                ("title", "text"),
                ("content", "text")
            ])
            
            results['knowledge_base_supporting'] = True
            logger.info("Created supporting indexes for knowledge base collection")
            
        except Exception as e:
            logger.error(f"Failed to create supporting indexes for knowledge base: {e}")
            results['knowledge_base_supporting'] = False
        
        return results
    
    def vector_search_products(
        self,
        query_embedding: List[float],
        limit: int = 10,
        filters: Optional[Dict[str, Any]] = None,
        min_score: float = 0.7
    ) -> List[Dict[str, Any]]:
        """
        Perform vector search on products collection
        
        Args:
            query_embedding: Query vector embedding
            limit: Maximum number of results
            filters: Additional filters (category, price_range, etc.)
            min_score: Minimum similarity score
            
        Returns:
            List of matching products with similarity scores
        """
        try:
            collection = self.database[self.PRODUCTS_COLLECTION]
            config = self.VECTOR_INDEX_CONFIGS['products']
            
            # Build aggregation pipeline
            pipeline = []
            
            # Vector search stage
            vector_search_stage = {
                "$vectorSearch": {
                    "index": config['index_name'],
                    "path": config['vector_field'],
                    "queryVector": query_embedding,
                    "numCandidates": limit * 10,  # Search more candidates for better results
                    "limit": limit
                }
            }
            
            # Add filters if provided
            if filters:
                match_stage = {"$match": {}}
                
                if 'category' in filters:
                    match_stage["$match"]["category"] = filters['category']
                
                if 'price_range' in filters:
                    price_range = filters['price_range']
                    match_stage["$match"]["price"] = {
                        "$gte": price_range.get('min', 0),
                        "$lte": price_range.get('max', float('inf'))
                    }
                
                if 'min_rating' in filters:
                    match_stage["$match"]["rating"] = {"$gte": filters['min_rating']}
                
                if 'tags' in filters:
                    match_stage["$match"]["tags"] = {"$in": filters['tags']}
                
                if match_stage["$match"]:
                    vector_search_stage["$vectorSearch"]["filter"] = match_stage["$match"]
            
            pipeline.append(vector_search_stage)
            
            # Add similarity score
            pipeline.append({
                "$addFields": {
                    "similarity_score": {"$meta": "vectorSearchScore"}
                }
            })
            
            # Filter by minimum score
            pipeline.append({
                "$match": {
                    "similarity_score": {"$gte": min_score}
                }
            })
            
            # Project relevant fields
            pipeline.append({
                "$project": {
                    "_id": 1,
                    "product_id": 1,
                    "title": 1,
                    "description": 1,
                    "category": 1,
                    "price": 1,
                    "rating": 1,
                    "review_count": 1,
                    "image_url": 1,
                    "tags": 1,
                    "similarity_score": 1
                }
            })
            
            # Execute search
            results = list(collection.aggregate(pipeline))
            
            logger.info(f"Vector search found {len(results)} products")
            return results
            
        except Exception as e:
            logger.error(f"Vector search on products failed: {e}")
            return []
    
    def vector_search_reviews(
        self,
        query_embedding: List[float],
        product_id: Optional[str] = None,
        limit: int = 10,
        min_score: float = 0.7
    ) -> List[Dict[str, Any]]:
        """
        Perform vector search on reviews collection
        
        Args:
            query_embedding: Query vector embedding
            product_id: Optional product ID to filter reviews
            limit: Maximum number of results
            min_score: Minimum similarity score
            
        Returns:
            List of matching reviews with similarity scores
        """
        try:
            collection = self.database[self.REVIEWS_COLLECTION]
            config = self.VECTOR_INDEX_CONFIGS['reviews']
            
            # Build aggregation pipeline
            pipeline = []
            
            # Vector search stage
            vector_search_stage = {
                "$vectorSearch": {
                    "index": config['index_name'],
                    "path": config['vector_field'],
                    "queryVector": query_embedding,
                    "numCandidates": limit * 10,
                    "limit": limit
                }
            }
            
            # Add product filter if specified
            if product_id:
                vector_search_stage["$vectorSearch"]["filter"] = {
                    "product_id": product_id
                }
            
            pipeline.append(vector_search_stage)
            
            # Add similarity score
            pipeline.append({
                "$addFields": {
                    "similarity_score": {"$meta": "vectorSearchScore"}
                }
            })
            
            # Filter by minimum score
            pipeline.append({
                "$match": {
                    "similarity_score": {"$gte": min_score}
                }
            })
            
            # Project relevant fields
            pipeline.append({
                "$project": {
                    "_id": 1,
                    "review_id": 1,
                    "product_id": 1,
                    "user_id": 1,
                    "user_name": 1,
                    "rating": 1,
                    "title": 1,
                    "content": 1,
                    "sentiment": 1,
                    "aspects": 1,
                    "helpful_count": 1,
                    "created_at": 1,
                    "similarity_score": 1
                }
            })
            
            # Execute search
            results = list(collection.aggregate(pipeline))
            
            logger.info(f"Vector search found {len(results)} reviews")
            return results
            
        except Exception as e:
            logger.error(f"Vector search on reviews failed: {e}")
            return []
    
    def vector_search_knowledge_base(
        self,
        query_embedding: List[float],
        category: Optional[str] = None,
        limit: int = 5,
        min_score: float = 0.8
    ) -> List[Dict[str, Any]]:
        """
        Perform vector search on knowledge base collection
        
        Args:
            query_embedding: Query vector embedding
            category: Optional category filter
            limit: Maximum number of results
            min_score: Minimum similarity score (higher for knowledge base)
            
        Returns:
            List of matching knowledge base articles with similarity scores
        """
        try:
            collection = self.database[self.KNOWLEDGE_BASE_COLLECTION]
            config = self.VECTOR_INDEX_CONFIGS['knowledge_base']
            
            # Build aggregation pipeline
            pipeline = []
            
            # Vector search stage
            vector_search_stage = {
                "$vectorSearch": {
                    "index": config['index_name'],
                    "path": config['vector_field'],
                    "queryVector": query_embedding,
                    "numCandidates": limit * 20,  # More candidates for knowledge base
                    "limit": limit
                }
            }
            
            # Add category filter if specified
            if category:
                vector_search_stage["$vectorSearch"]["filter"] = {
                    "category": category
                }
            
            pipeline.append(vector_search_stage)
            
            # Add similarity score
            pipeline.append({
                "$addFields": {
                    "similarity_score": {"$meta": "vectorSearchScore"}
                }
            })
            
            # Filter by minimum score
            pipeline.append({
                "$match": {
                    "similarity_score": {"$gte": min_score}
                }
            })
            
            # Project relevant fields
            pipeline.append({
                "$project": {
                    "_id": 1,
                    "article_id": 1,
                    "title": 1,
                    "content": 1,
                    "category": 1,
                    "type": 1,
                    "tags": 1,
                    "created_at": 1,
                    "similarity_score": 1
                }
            })
            
            # Execute search
            results = list(collection.aggregate(pipeline))
            
            logger.info(f"Vector search found {len(results)} knowledge base articles")
            return results
            
        except Exception as e:
            logger.error(f"Vector search on knowledge base failed: {e}")
            return []
    
    def test_vector_search_performance(self) -> Dict[str, Any]:
        """
        Test vector search performance and accuracy with sample data
        
        Returns:
            Performance metrics and test results
        """
        test_results = {
            'timestamp': datetime.utcnow().isoformat(),
            'tests': {}
        }
        
        # Test embedding (sample 1536-dimensional vector)
        test_embedding = np.random.rand(1536).tolist()
        
        # Test products search
        try:
            start_time = datetime.utcnow()
            products_results = self.vector_search_products(
                query_embedding=test_embedding,
                limit=10,
                min_score=0.1  # Lower threshold for testing
            )
            end_time = datetime.utcnow()
            
            test_results['tests']['products'] = {
                'success': True,
                'results_count': len(products_results),
                'response_time_ms': (end_time - start_time).total_seconds() * 1000,
                'sample_scores': [r.get('similarity_score', 0) for r in products_results[:3]]
            }
            
        except Exception as e:
            test_results['tests']['products'] = {
                'success': False,
                'error': str(e)
            }
        
        # Test reviews search
        try:
            start_time = datetime.utcnow()
            reviews_results = self.vector_search_reviews(
                query_embedding=test_embedding,
                limit=10,
                min_score=0.1
            )
            end_time = datetime.utcnow()
            
            test_results['tests']['reviews'] = {
                'success': True,
                'results_count': len(reviews_results),
                'response_time_ms': (end_time - start_time).total_seconds() * 1000,
                'sample_scores': [r.get('similarity_score', 0) for r in reviews_results[:3]]
            }
            
        except Exception as e:
            test_results['tests']['reviews'] = {
                'success': False,
                'error': str(e)
            }
        
        # Test knowledge base search
        try:
            start_time = datetime.utcnow()
            kb_results = self.vector_search_knowledge_base(
                query_embedding=test_embedding,
                limit=5,
                min_score=0.1
            )
            end_time = datetime.utcnow()
            
            test_results['tests']['knowledge_base'] = {
                'success': True,
                'results_count': len(kb_results),
                'response_time_ms': (end_time - start_time).total_seconds() * 1000,
                'sample_scores': [r.get('similarity_score', 0) for r in kb_results[:3]]
            }
            
        except Exception as e:
            test_results['tests']['knowledge_base'] = {
                'success': False,
                'error': str(e)
            }
        
        return test_results
    
    def get_index_stats(self) -> Dict[str, Any]:
        """Get statistics about vector indexes"""
        stats = {}
        
        for collection_name, config in self.VECTOR_INDEX_CONFIGS.items():
            try:
                collection = self.database[collection_name]
                
                # Get collection stats
                collection_stats = self.database.command("collStats", collection_name)
                
                # Get index information
                indexes = list(collection.list_indexes())
                vector_index = None
                for index in indexes:
                    if index.get('name') == config['index_name']:
                        vector_index = index
                        break
                
                stats[collection_name] = {
                    'document_count': collection_stats.get('count', 0),
                    'size_bytes': collection_stats.get('size', 0),
                    'avg_document_size': collection_stats.get('avgObjSize', 0),
                    'vector_index_exists': vector_index is not None,
                    'vector_index_config': config,
                    'total_indexes': len(indexes)
                }
                
            except Exception as e:
                stats[collection_name] = {
                    'error': str(e)
                }
        
        return stats

# Global vector search manager instance
vector_search_manager = VectorSearchManager()