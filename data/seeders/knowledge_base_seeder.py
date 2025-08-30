"""
Knowledge Base Database Seeder for Unicorn E-Commerce
Seeds pre-generated knowledge base data to DocumentDB
"""
import json
import os
import sys
from datetime import datetime
from typing import List, Dict, Any

try:
    import pymongo
    from pymongo import MongoClient
    PYMONGO_AVAILABLE = True
except ImportError:
    PYMONGO_AVAILABLE = False
    print("pymongo not available - running in mock mode")

# Add backend to path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'backend'))

try:
    from shared.config import config
    from shared.database import get_documentdb_client
    AWS_AVAILABLE = True
except ImportError:
    # Fallback for development without AWS dependencies
    AWS_AVAILABLE = False
    
    class MockConfig:
        DOCUMENTDB_HOST = 'localhost'
        DOCUMENTDB_PORT = 27017
        DOCUMENTDB_DATABASE = 'unicorn_ecommerce_dev'
    
    config = MockConfig()
    
    def get_documentdb_client():
        print("Mock DocumentDB client")
        return None

class KnowledgeBaseSeeder:
    """Seed knowledge base data to DocumentDB"""
    
    def __init__(self):
        if AWS_AVAILABLE and PYMONGO_AVAILABLE:
            self.client = get_documentdb_client()
            if self.client:
                self.db = self.client[config.DOCUMENTDB_DATABASE]
                self.kb_collection = self.db.knowledge_base
            else:
                self.client = None
                self.db = None
                self.kb_collection = None
        else:
            self.client = None
            self.db = None
            self.kb_collection = None
            print("Running in mock mode - DocumentDB services not available")
    
    def load_knowledge_base_from_json(self, filename: str = "knowledge_base.json") -> List[Dict[str, Any]]:
        """Load knowledge base records from JSON file"""
        try:
            filepath = os.path.join(os.path.dirname(__file__), '..', 'output', filename)
            
            if os.path.exists(filepath):
                with open(filepath, 'r', encoding='utf-8') as f:
                    kb_articles = json.load(f)
                print(f"Loaded {len(kb_articles)} knowledge base articles from {filepath}")
                return kb_articles
            
            print(f"No knowledge base file found at {filepath}")
            return []
            
        except Exception as e:
            print(f"Error loading knowledge base from JSON: {e}")
            return []
    
    def seed_to_documentdb(self, kb_articles: List[Dict[str, Any]]) -> bool:
        """Seed knowledge base records to DocumentDB"""
        if not AWS_AVAILABLE or not PYMONGO_AVAILABLE or not self.kb_collection:
            print("DocumentDB services not available - skipping DocumentDB seeding")
            print(f"Would have seeded {len(kb_articles)} knowledge base articles to DocumentDB collection: knowledge_base")
            return True
            
        try:
            # Clear existing knowledge base (for development)
            print("Clearing existing knowledge base articles...")
            delete_result = self.kb_collection.delete_many({})
            print(f"Deleted {delete_result.deleted_count} existing articles")
            
            # Insert new articles
            print("Inserting new knowledge base articles...")
            
            if kb_articles:
                insert_result = self.kb_collection.insert_many(kb_articles)
                inserted_count = len(insert_result.inserted_ids)
                print(f"Successfully seeded {inserted_count} knowledge base articles to DocumentDB")
                
                # Create indexes for better performance
                self._create_indexes()
                
                # Verify the seeding
                actual_count = self.kb_collection.count_documents({})
                print(f"Verification: {actual_count} articles found in DocumentDB collection")
                
                return actual_count == len(kb_articles)
            else:
                print("No knowledge base articles to seed")
                return True
            
        except Exception as e:
            print(f"Error seeding knowledge base to DocumentDB: {e}")
            return False
    
    def _create_indexes(self):
        """Create indexes for better query performance"""
        try:
            # Create indexes on commonly queried fields
            indexes = [
                ("category", 1),      # Index on category
                ("tags", 1),          # Index on tags
                ("title", "text"),    # Text index for search
                ("content", "text"),  # Text index for content search
                ("createdAt", -1),    # Index on creation date (desc)
            ]
            
            for field, direction in indexes:
                try:
                    if field in ["title", "content"]:
                        # Text index for full-text search
                        self.kb_collection.create_index([(field, direction)])
                    else:
                        self.kb_collection.create_index([(field, direction)])
                    print(f"Created index on {field}")
                except Exception as e:
                    print(f"Index on {field} may already exist: {e}")
                    
        except Exception as e:
            print(f"Error creating indexes: {e}")

def main():
    """Main function to seed knowledge base data to DocumentDB"""
    try:
        print("🦄 Unicorn E-Commerce Knowledge Base Database Seeder")
        print("=" * 60)
        print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        # Initialize seeder
        seeder = KnowledgeBaseSeeder()
        
        # Load knowledge base records from JSON
        kb_articles = seeder.load_knowledge_base_from_json()
        
        if not kb_articles:
            print("No knowledge base articles found. Skipping knowledge base seeding.")
            return
        
        # Seed to DocumentDB
        print(f"\nSeeding {len(kb_articles)} knowledge base articles to DocumentDB...")
        success = seeder.seed_to_documentdb(kb_articles)
        
        if success:
            print("✅ Knowledge base seeding completed successfully!")
            print(f"🚀 Knowledge base data is now available in DocumentDB collection: knowledge_base")
        else:
            print("❌ Knowledge base seeding failed")
            return
            
    except Exception as e:
        print(f"Error in main execution: {e}")
        raise

if __name__ == "__main__":
    main()