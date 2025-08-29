#!/usr/bin/env python3
"""
Batch processing script for generating vector embeddings
Processes existing data in DocumentDB and adds vector embeddings using Bedrock Titan
"""
import sys
import os
import json
import logging
from datetime import datetime
from typing import List, Dict, Any

# Add the backend directory to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from shared.embeddings import embedding_generator
from shared.database import get_documentdb_collection, db

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class EmbeddingBatchProcessor:
    """Processes collections in batches to generate embeddings"""
    
    def __init__(self, batch_size: int = 50):
        self.batch_size = batch_size
        self.collections_config = {
            'products': {
                'collection_name': 'products',
                'embedding_field': 'description_embedding',
                'processor_method': 'generate_product_embeddings'
            },
            'reviews': {
                'collection_name': 'reviews', 
                'embedding_field': 'content_embedding',
                'processor_method': 'generate_review_embeddings'
            },
            'knowledge_base': {
                'collection_name': 'knowledge_base',
                'embedding_field': 'content_embedding',
                'processor_method': 'generate_knowledge_base_embeddings'
            }
        }
    
    def get_documents_without_embeddings(self, collection_name: str, embedding_field: str) -> List[Dict[str, Any]]:
        """Get documents that don't have embeddings yet"""
        try:
            collection = get_documentdb_collection(collection_name)
            
            # Find documents without embedding field or with empty embeddings
            query = {
                "$or": [
                    {embedding_field: {"$exists": False}},
                    {embedding_field: {"$eq": None}},
                    {embedding_field: {"$eq": []}},
                    {embedding_field: {"$size": 0}}
                ]
            }
            
            documents = list(collection.find(query))
            logger.info(f"Found {len(documents)} documents without embeddings in {collection_name}")
            
            return documents
            
        except Exception as e:
            logger.error(f"Failed to query {collection_name}: {e}")
            return []
    
    def update_documents_with_embeddings(
        self,
        collection_name: str,
        embedding_field: str,
        embedding_results: List[Any]
    ) -> Dict[str, int]:
        """Update documents with generated embeddings"""
        stats = {'updated': 0, 'failed': 0}
        
        try:
            collection = get_documentdb_collection(collection_name)
            
            for result in embedding_results:
                if not result.success:
                    logger.warning(f"Skipping failed embedding for {result.identifier}: {result.error}")
                    stats['failed'] += 1
                    continue
                
                try:
                    # Update document with embedding
                    update_result = collection.update_one(
                        self._get_document_filter(collection_name, result.identifier),
                        {
                            "$set": {
                                embedding_field: result.embedding,
                                f"{embedding_field}_metadata": {
                                    "generated_at": datetime.utcnow(),
                                    "model_id": embedding_generator.model_id,
                                    "text_length": len(result.text),
                                    "cached": result.cached,
                                    "processing_time_ms": result.processing_time_ms
                                }
                            }
                        }
                    )
                    
                    if update_result.modified_count > 0:
                        stats['updated'] += 1
                        logger.debug(f"Updated embedding for {result.identifier}")
                    else:
                        logger.warning(f"No document updated for {result.identifier}")
                        stats['failed'] += 1
                        
                except Exception as e:
                    logger.error(f"Failed to update document {result.identifier}: {e}")
                    stats['failed'] += 1
            
            logger.info(f"Updated {stats['updated']} documents, {stats['failed']} failed in {collection_name}")
            
        except Exception as e:
            logger.error(f"Failed to update documents in {collection_name}: {e}")
        
        return stats
    
    def _get_document_filter(self, collection_name: str, identifier: str) -> Dict[str, Any]:
        """Get filter to identify document by collection type"""
        if collection_name == 'products':
            return {"product_id": identifier}
        elif collection_name == 'reviews':
            return {"review_id": identifier}
        elif collection_name == 'knowledge_base':
            return {"article_id": identifier}
        else:
            return {"_id": identifier}
    
    def process_collection(self, collection_type: str) -> Dict[str, Any]:
        """Process a single collection to generate embeddings"""
        if collection_type not in self.collections_config:
            raise ValueError(f"Unknown collection type: {collection_type}")
        
        config = self.collections_config[collection_type]
        collection_name = config['collection_name']
        embedding_field = config['embedding_field']
        processor_method = config['processor_method']
        
        logger.info(f"Processing {collection_type} collection...")
        
        # Get documents without embeddings
        documents = self.get_documents_without_embeddings(collection_name, embedding_field)
        
        if not documents:
            logger.info(f"No documents need embedding generation in {collection_name}")
            return {
                'collection': collection_type,
                'total_documents': 0,
                'processed': 0,
                'updated': 0,
                'failed': 0,
                'batches': 0
            }
        
        # Process in batches
        total_updated = 0
        total_failed = 0
        batch_count = 0
        
        for i in range(0, len(documents), self.batch_size):
            batch = documents[i:i + self.batch_size]
            batch_count += 1
            
            logger.info(f"Processing batch {batch_count} ({len(batch)} documents)...")
            
            try:
                # Generate embeddings using the appropriate method
                processor = getattr(embedding_generator, processor_method)
                embedding_results = processor(batch)
                
                # Update documents with embeddings
                stats = self.update_documents_with_embeddings(
                    collection_name,
                    embedding_field,
                    embedding_results
                )
                
                total_updated += stats['updated']
                total_failed += stats['failed']
                
                logger.info(f"Batch {batch_count} complete: {stats['updated']} updated, {stats['failed']} failed")
                
            except Exception as e:
                logger.error(f"Failed to process batch {batch_count}: {e}")
                total_failed += len(batch)
        
        result = {
            'collection': collection_type,
            'total_documents': len(documents),
            'processed': len(documents),
            'updated': total_updated,
            'failed': total_failed,
            'batches': batch_count
        }
        
        logger.info(f"Collection {collection_type} processing complete: {result}")
        return result
    
    def process_all_collections(self) -> Dict[str, Any]:
        """Process all collections to generate embeddings"""
        logger.info("Starting batch embedding generation for all collections...")
        
        start_time = datetime.utcnow()
        results = {
            'start_time': start_time.isoformat(),
            'collections': {},
            'summary': {
                'total_documents': 0,
                'total_updated': 0,
                'total_failed': 0,
                'total_batches': 0
            }
        }
        
        for collection_type in self.collections_config.keys():
            try:
                collection_result = self.process_collection(collection_type)
                results['collections'][collection_type] = collection_result
                
                # Update summary
                results['summary']['total_documents'] += collection_result['total_documents']
                results['summary']['total_updated'] += collection_result['updated']
                results['summary']['total_failed'] += collection_result['failed']
                results['summary']['total_batches'] += collection_result['batches']
                
            except Exception as e:
                logger.error(f"Failed to process collection {collection_type}: {e}")
                results['collections'][collection_type] = {
                    'collection': collection_type,
                    'error': str(e)
                }
        
        end_time = datetime.utcnow()
        results['end_time'] = end_time.isoformat()
        results['duration_seconds'] = (end_time - start_time).total_seconds()
        
        return results

def main():
    """Main function"""
    print("🦄 Unicorn E-Commerce - Embedding Generation")
    print("=" * 60)
    
    try:
        # Test database connection
        print("📡 Testing DocumentDB connection...")
        database = db.get_documentdb_database()
        database.command('ping')
        print("✅ DocumentDB connection successful")
        
        # Test Bedrock connection
        print("🤖 Testing Bedrock connection...")
        test_result = embedding_generator.generate_embedding("test connection", use_cache=False)
        if test_result.success:
            print("✅ Bedrock connection successful")
            print(f"   Model: {embedding_generator.model_id}")
            print(f"   Embedding dimensions: {len(test_result.embedding)}")
        else:
            print(f"❌ Bedrock connection failed: {test_result.error}")
            return
        
        # Initialize batch processor
        batch_size = int(input("\nEnter batch size (default 50): ") or "50")
        processor = EmbeddingBatchProcessor(batch_size=batch_size)
        
        # Ask user which collections to process
        print("\nAvailable collections:")
        collections = list(processor.collections_config.keys())
        for i, collection in enumerate(collections, 1):
            print(f"  {i}. {collection}")
        print(f"  {len(collections) + 1}. All collections")
        
        choice = input(f"\nSelect collection to process (1-{len(collections) + 1}): ").strip()
        
        if choice == str(len(collections) + 1):
            # Process all collections
            print("\n🚀 Processing all collections...")
            results = processor.process_all_collections()
        else:
            # Process single collection
            try:
                collection_index = int(choice) - 1
                if 0 <= collection_index < len(collections):
                    collection_type = collections[collection_index]
                    print(f"\n🚀 Processing {collection_type} collection...")
                    collection_result = processor.process_collection(collection_type)
                    results = {
                        'start_time': datetime.utcnow().isoformat(),
                        'collections': {collection_type: collection_result},
                        'summary': {
                            'total_documents': collection_result['total_documents'],
                            'total_updated': collection_result['updated'],
                            'total_failed': collection_result['failed'],
                            'total_batches': collection_result['batches']
                        }
                    }
                else:
                    print("❌ Invalid selection")
                    return
            except ValueError:
                print("❌ Invalid selection")
                return
        
        # Save results to file
        results_file = f"embedding_generation_results_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
        with open(results_file, 'w') as f:
            json.dump(results, f, indent=2, default=str)
        
        print(f"\n💾 Results saved to: {results_file}")
        
        # Display summary
        print("\n" + "=" * 60)
        print("📊 EMBEDDING GENERATION SUMMARY")
        print("=" * 60)
        
        summary = results['summary']
        print(f"Total Documents: {summary['total_documents']:,}")
        print(f"Successfully Updated: {summary['total_updated']:,}")
        print(f"Failed: {summary['total_failed']:,}")
        print(f"Total Batches: {summary['total_batches']:,}")
        
        if 'duration_seconds' in results:
            duration = results['duration_seconds']
            print(f"Duration: {duration:.2f} seconds")
            
            if summary['total_updated'] > 0:
                rate = summary['total_updated'] / duration
                print(f"Processing Rate: {rate:.2f} embeddings/second")
        
        # Collection breakdown
        print("\nCollection Breakdown:")
        for collection_type, collection_result in results['collections'].items():
            if 'error' in collection_result:
                print(f"  {collection_type}: ❌ Error - {collection_result['error']}")
            else:
                updated = collection_result['updated']
                total = collection_result['total_documents']
                print(f"  {collection_type}: {updated}/{total} updated")
        
        # Success check
        if summary['total_failed'] == 0 and summary['total_updated'] > 0:
            print("\n🎉 All embeddings generated successfully!")
        elif summary['total_updated'] > 0:
            print(f"\n⚠️  Completed with {summary['total_failed']} failures")
        else:
            print("\n❌ No embeddings were generated")
        
        print("\nNext steps:")
        print("1. Verify embeddings in DocumentDB collections")
        print("2. Test vector search functionality")
        print("3. Run performance benchmarks")
        
    except KeyboardInterrupt:
        print("\n\n⏹️  Process interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Embedding generation failed: {e}")
        print(f"\n❌ Embedding generation failed: {e}")
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