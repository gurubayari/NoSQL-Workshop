"""
Review Database Seeder for Unicorn E-Commerce
Seeds pre-generated review data to DocumentDB
"""
import json
import os
import sys
from datetime import datetime
from typing import List, Dict, Any

# Import common database connections
from database_connections import get_documentdb_collection

class ReviewSeeder:
    """Seed review data to DocumentDB"""
    
    def __init__(self):
        self.reviews_collection = get_documentdb_collection('reviews')
    
    def load_reviews_from_json(self, filename: str = "reviews.json") -> List[Dict[str, Any]]:
        """Load review records from JSON file"""
        try:
            filepath = os.path.join(os.path.dirname(__file__), '..', 'output', filename)
            
            if os.path.exists(filepath):
                with open(filepath, 'r', encoding='utf-8') as f:
                    reviews = json.load(f)
                print(f"Loaded {len(reviews)} reviews from {filepath}")
                return reviews
            
            print(f"No reviews file found at {filepath}")
            return []
            
        except Exception as e:
            print(f"Error loading reviews from JSON: {e}")
            return []
    
    def seed_to_documentdb(self, reviews: List[Dict[str, Any]]) -> bool:
        """Seed review records to DocumentDB"""
            
        try:
            # Clear existing reviews (for development)
            print("Clearing existing reviews...")
            delete_result = self.reviews_collection.delete_many({})
            print(f"Deleted {delete_result.deleted_count} existing reviews")
            
            # Insert new reviews
            print("Inserting new reviews...")
            
            # Insert in batches
            batch_size = 100
            inserted_count = 0
            
            for i in range(0, len(reviews), batch_size):
                batch = reviews[i:i + batch_size]
                insert_result = self.reviews_collection.insert_many(batch)
                inserted_count += len(insert_result.inserted_ids)
                
                print(f"Inserted {inserted_count}/{len(reviews)} reviews")
            
            print(f"Successfully seeded {inserted_count} reviews to DocumentDB")
            
            # Create indexes for better performance
            self._create_indexes()
            
            # Verify the seeding
            actual_count = self.reviews_collection.count_documents({})
            print(f"Verification: {actual_count} reviews found in DocumentDB collection")
            
            return actual_count == len(reviews)
            
        except Exception as e:
            print(f"Error seeding reviews to DocumentDB: {e}")
            return False
    
    def _create_indexes(self):
        """Create indexes for better query performance"""
        try:
            # Create indexes on commonly queried fields
            indexes = [
                ("productId", 1),     # Index on productId
                ("rating", 1),        # Index on rating
                ("sentiment", 1),     # Index on sentiment
                ("createdAt", -1),    # Index on creation date (desc)
                ("verified", 1),      # Index on verified status
            ]
            
            for field, direction in indexes:
                try:
                    self.reviews_collection.create_index([(field, direction)])
                    print(f"Created index on {field}")
                except Exception as e:
                    print(f"Index on {field} may already exist: {e}")
            
            # Create compound indexes
            compound_indexes = [
                [("productId", 1), ("rating", -1)],      # Product + rating (desc)
                [("productId", 1), ("createdAt", -1)],   # Product + date (desc)
                [("sentiment", 1), ("rating", -1)],      # Sentiment + rating
            ]
            
            for compound_index in compound_indexes:
                try:
                    self.reviews_collection.create_index(compound_index)
                    field_names = ", ".join([f[0] for f in compound_index])
                    print(f"Created compound index on {field_names}")
                except Exception as e:
                    print(f"Compound index may already exist: {e}")
                    
        except Exception as e:
            print(f"Error creating indexes: {e}")

def main():
    """Main function to seed review data to DocumentDB"""
    try:
        print("🦄 Unicorn E-Commerce Review Database Seeder")
        print("=" * 60)
        print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        # Initialize seeder
        seeder = ReviewSeeder()
        
        # Load review records from JSON
        reviews = seeder.load_reviews_from_json()
        
        if not reviews:
            print("No reviews found. Skipping review seeding.")
            return
        
        # Seed to DocumentDB
        print(f"\nSeeding {len(reviews)} reviews to DocumentDB...")
        success = seeder.seed_to_documentdb(reviews)
        
        if success:
            print("✅ Review seeding completed successfully!")
            print(f"🚀 Review data is now available in DocumentDB collection: reviews")
        else:
            print("❌ Review seeding failed")
            return
            
    except Exception as e:
        print(f"Error in main execution: {e}")
        raise

if __name__ == "__main__":
    main()