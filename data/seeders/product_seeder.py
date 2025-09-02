"""
Product Database Seeder for Unicorn E-Commerce
Seeds pre-generated product data to DocumentDB
"""
import json
import os
import sys
from datetime import datetime
from typing import List, Dict, Any

# Import common database connections
from database_connections import get_documentdb_collection

class ProductSeeder:
    """Seed product data to DocumentDB"""
    
    def __init__(self):
        self.products_collection = get_documentdb_collection('products')
    
    def load_products_from_json(self, filename: str = "products.json") -> List[Dict[str, Any]]:
        """Load product records from JSON file"""
        try:
            filepath = os.path.join(os.path.dirname(__file__), '..', 'output', filename)
            
            if os.path.exists(filepath):
                with open(filepath, 'r', encoding='utf-8') as f:
                    products = json.load(f)
                print(f"Loaded {len(products)} products from {filepath}")
                return products
            
            print(f"No products file found at {filepath}")
            return []
            
        except Exception as e:
            print(f"Error loading products from JSON: {e}")
            return []
    
    def validate_product_data(self, products: List[Dict[str, Any]]) -> bool:
        """Validate product data before seeding"""
        if not products:
            print("No products to validate")
            return False
        
        required_fields = ['productId', 'name', 'category', 'currentPrice']
        
        valid_count = 0
        for i, product in enumerate(products):
            # Check required fields
            missing_fields = [field for field in required_fields if field not in product]
            if missing_fields:
                print(f"Product {i+1} missing required fields: {missing_fields}")
                continue
            
            # Check data types
            if not isinstance(product['currentPrice'], (int, float)):
                print(f"Product {i+1} has invalid price type: {type(product['currentPrice'])}")
                continue
            
            if product['currentPrice'] <= 0:
                print(f"Product {i+1} has invalid price: {product['currentPrice']}")
                continue
            
            valid_count += 1
        
        validation_percentage = (valid_count / len(products)) * 100
        print(f"Product validation: {valid_count}/{len(products)} valid ({validation_percentage:.1f}%)")
        
        return validation_percentage > 95  # At least 95% valid
    
    def seed_to_documentdb(self, products: List[Dict[str, Any]]) -> bool:
        """Seed product records to DocumentDB"""
            
        try:
            # Clear existing products (for development)
            print("Clearing existing products...")
            delete_result = self.products_collection.delete_many({})
            print(f"Deleted {delete_result.deleted_count} existing products")
            
            # Insert new products
            print("Inserting new products...")
            
            # Prepare products for MongoDB (ensure proper data types)
            prepared_products = []
            for product in products:
                prepared_product = self._prepare_for_documentdb(product)
                prepared_products.append(prepared_product)
            
            # Insert in batches
            batch_size = 100
            inserted_count = 0
            
            for i in range(0, len(prepared_products), batch_size):
                batch = prepared_products[i:i + batch_size]
                insert_result = self.products_collection.insert_many(batch)
                inserted_count += len(insert_result.inserted_ids)
                
                print(f"Inserted {inserted_count}/{len(prepared_products)} products")
            
            print(f"Successfully seeded {inserted_count} products to DocumentDB")
            
            # Create indexes for better performance
            self._create_indexes()
            
            # Verify the seeding
            actual_count = self.products_collection.count_documents({})
            print(f"Verification: {actual_count} products found in DocumentDB collection")
            
            return actual_count == len(products)
            
        except Exception as e:
            print(f"Error seeding products to DocumentDB: {e}")
            return False
    
    def _prepare_for_documentdb(self, product: Dict[str, Any]) -> Dict[str, Any]:
        """Prepare product for DocumentDB by ensuring proper data types and setting _id"""
        def convert_recursive(obj):
            if isinstance(obj, str):
                # Try to parse ISO datetime strings back to datetime objects
                if obj.endswith('Z') or '+' in obj[-6:] or obj.count('T') == 1:
                    try:
                        from datetime import datetime
                        return datetime.fromisoformat(obj.replace('Z', '+00:00'))
                    except:
                        return obj
                return obj
            elif isinstance(obj, dict):
                return {k: convert_recursive(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [convert_recursive(item) for item in obj]
            else:
                return obj
        
        prepared_product = convert_recursive(product)
        
        # Set _id field with productId for DocumentDB
        if 'productId' in prepared_product:
            prepared_product['_id'] = prepared_product['productId']
        
        return prepared_product
    
    def _create_indexes(self):
        """Create indexes for better query performance"""
        try:
            # Create indexes on commonly queried fields
            indexes = [
                ("productId", 1),  # Unique index on productId
                ("category", 1),   # Index on category
                ("name", "text"),  # Text index for search
                ("tags", 1),       # Index on tags
                ("currentPrice", 1),  # Index on price
                ("rating", 1),     # Index on rating
                ("inStock", 1),    # Index on stock status
            ]
            
            for field, direction in indexes:
                try:
                    if field == "name":
                        # Text index for full-text search
                        self.products_collection.create_index([(field, direction)])
                    else:
                        self.products_collection.create_index([(field, direction)])
                    print(f"Created index on {field}")
                except Exception as e:
                    print(f"Index on {field} may already exist: {e}")
            
            # Create compound indexes
            compound_indexes = [
                [("category", 1), ("currentPrice", 1)],  # Category + price
                [("category", 1), ("rating", -1)],       # Category + rating (desc)
                [("inStock", 1), ("category", 1)],       # Stock + category
            ]
            
            for compound_index in compound_indexes:
                try:
                    self.products_collection.create_index(compound_index)
                    field_names = ", ".join([f[0] for f in compound_index])
                    print(f"Created compound index on {field_names}")
                except Exception as e:
                    print(f"Compound index may already exist: {e}")
                    
        except Exception as e:
            print(f"Error creating indexes: {e}")
    
    def print_seeding_summary(self, products: List[Dict[str, Any]]):
        """Print summary of seeded product data"""
        if not products:
            return
        
        print(f"\n📊 Product Seeding Summary")
        print(f"{'='*50}")
        
        # Basic stats
        total_products = len(products)
        total_value = sum(product.get("currentPrice", 0) for product in products)
        avg_price = total_value / total_products if total_products > 0 else 0
        
        print(f"Total products: {total_products}")
        print(f"Total catalog value: ${total_value:,.2f}")
        print(f"Average price: ${avg_price:.2f}")
        
        # Category breakdown
        category_stats = {}
        for product in products:
            category = product.get("category", "Unknown")
            if category not in category_stats:
                category_stats[category] = {"count": 0, "total_value": 0}
            
            category_stats[category]["count"] += 1
            category_stats[category]["total_value"] += product.get("currentPrice", 0)
        
        print(f"\nProducts by category:")
        for category, stats in sorted(category_stats.items()):
            avg_cat_price = stats["total_value"] / stats["count"] if stats["count"] > 0 else 0
            print(f"  {category}: {stats['count']} products (avg: ${avg_cat_price:.2f})")
        
        # Price ranges
        price_ranges = {
            "Under $50": 0,
            "$50-$100": 0,
            "$100-$500": 0,
            "$500-$1000": 0,
            "Over $1000": 0
        }
        
        for product in products:
            price = product.get("currentPrice", 0)
            if price < 50:
                price_ranges["Under $50"] += 1
            elif price < 100:
                price_ranges["$50-$100"] += 1
            elif price < 500:
                price_ranges["$100-$500"] += 1
            elif price < 1000:
                price_ranges["$500-$1000"] += 1
            else:
                price_ranges["Over $1000"] += 1
        
        print(f"\nPrice distribution:")
        for range_name, count in price_ranges.items():
            percentage = (count / total_products) * 100 if total_products > 0 else 0
            print(f"  {range_name}: {count} products ({percentage:.1f}%)")
        
        # Stock status
        in_stock = sum(1 for product in products if product.get("inStock", False))
        out_of_stock = total_products - in_stock
        
        print(f"\nStock status:")
        print(f"  In stock: {in_stock} products ({(in_stock/total_products)*100:.1f}%)")
        print(f"  Out of stock: {out_of_stock} products ({(out_of_stock/total_products)*100:.1f}%)")
        
        # Featured and new products
        featured = sum(1 for product in products if product.get("isFeatured", False))
        new_products = sum(1 for product in products if product.get("isNew", False))
        
        print(f"\nSpecial products:")
        print(f"  Featured: {featured} products")
        print(f"  New: {new_products} products")

def main():
    """Main function to seed product data to DocumentDB"""
    try:
        print("🦄 Unicorn E-Commerce Product Database Seeder")
        print("=" * 60)
        print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        # Initialize seeder
        seeder = ProductSeeder()
        
        # Load product records from JSON
        products = seeder.load_products_from_json()
        
        if not products:
            print("No products found. Please run product_generator.py first.")
            return
        
        # Validate product data
        print("\nValidating product data...")
        data_valid = seeder.validate_product_data(products)
        
        if not data_valid:
            print("Warning: Product data validation failed")
            response = input("Continue anyway? (y/N): ")
            if response.lower() != 'y':
                print("Seeding cancelled")
                return
        
        # Seed to DocumentDB
        print(f"\nSeeding {len(products)} products to DocumentDB...")
        success = seeder.seed_to_documentdb(products)
        
        if success:
            print("✅ Product seeding completed successfully!")
            seeder.print_seeding_summary(products)
            
            print(f"\n🚀 Product data is now available in DocumentDB collection: products")
            print(f"   Products are indexed for efficient querying")
            print(f"   Each product includes embeddings for vector search")
            print(f"   Product IDs correlate with inventory in DynamoDB")
        else:
            print("❌ Product seeding failed")
            return
            
    except Exception as e:
        print(f"Error in main execution: {e}")
        raise

if __name__ == "__main__":
    main()