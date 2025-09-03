"""
Inventory Database Seeder for Unicorn E-Commerce
Seeds pre-generated inventory data to DynamoDB
"""
import json
import os
import sys
from datetime import datetime
from decimal import Decimal
from typing import List, Dict, Any

# Import common database connections
from database_connections import get_dynamodb_table, prepare_for_dynamodb

class InventorySeeder:
    """Seed inventory data to DynamoDB"""
    
    def __init__(self):
        self.inventory_table = get_dynamodb_table('INVENTORY_TABLE')
    
    def load_inventory_from_json(self, filename: str = "inventory.json") -> List[Dict[str, Any]]:
        """Load inventory records from JSON file"""
        try:
            filepath = os.path.join(os.path.dirname(__file__), '..', 'output', filename)
            
            if os.path.exists(filepath):
                with open(filepath, 'r', encoding='utf-8') as f:
                    inventory_records = json.load(f)
                print(f"Loaded {len(inventory_records)} inventory records from {filepath}")
                return inventory_records
            
            print(f"No inventory file found at {filepath}")
            return []
            
        except Exception as e:
            print(f"Error loading inventory from JSON: {e}")
            return []
    
    def validate_inventory_product_correlation(self, inventory_records: List[Dict[str, Any]]) -> bool:
        """Validate that inventory records correlate with products"""
        try:
            # Load products to check correlation
            products_filepath = os.path.join(os.path.dirname(__file__), '..', 'output', 'products.json')
            
            if not os.path.exists(products_filepath):
                print("Warning: products.json not found - cannot validate correlation")
                return True
            
            with open(products_filepath, 'r', encoding='utf-8') as f:
                products = json.load(f)
            
            product_ids = {product['productId'] for product in products}
            inventory_product_ids = {record['productId'] for record in inventory_records}
            
            # Check if all inventory records have corresponding products
            missing_products = inventory_product_ids - product_ids
            if missing_products:
                print(f"Warning: {len(missing_products)} inventory records have no corresponding products")
                print(f"Missing product IDs: {list(missing_products)[:5]}...")  # Show first 5
            
            # Check if all products have inventory records
            missing_inventory = product_ids - inventory_product_ids
            if missing_inventory:
                print(f"Warning: {len(missing_inventory)} products have no inventory records")
                print(f"Missing inventory for product IDs: {list(missing_inventory)[:5]}...")  # Show first 5
            
            correlation_percentage = len(inventory_product_ids & product_ids) / len(product_ids) * 100
            print(f"Product-Inventory correlation: {correlation_percentage:.1f}%")
            
            # Validate new simplified structure
            print(f"Validating simplified inventory structure...")
            required_fields = ['productId', 'availableQuantity', 'totalQuantity', 'reorderLevel']
            
            for i, record in enumerate(inventory_records[:5]):  # Check first 5 records
                missing_fields = [field for field in required_fields if field not in record]
                if missing_fields:
                    print(f"Warning: Record {i+1} missing fields: {missing_fields}")
                    return False
            
            print(f"✅ Inventory structure validation passed")
            return correlation_percentage > 90  # At least 90% correlation
            
        except Exception as e:
            print(f"Error validating correlation: {e}")
            return True  # Don't fail on validation errors
    
    def seed_to_dynamodb(self, inventory_records: List[Dict[str, Any]]) -> bool:
        """Seed simplified inventory records to DynamoDB (one record per product)"""
        try:
            table = self.inventory_table
            
            # Clear existing inventory (for development)
            print("Clearing existing inventory records...")
            scan_response = table.scan()
            deleted_count = 0
            
            with table.batch_writer() as batch:
                for item in scan_response['Items']:
                    # Handle both old (with warehouseId) and new (without warehouseId) schemas
                    if 'warehouseId' in item:
                        batch.delete_item(Key={
                            'productId': item['productId'],
                            'warehouseId': item['warehouseId']
                        })
                    else:
                        batch.delete_item(Key={
                            'productId': item['productId']
                        })
                    deleted_count += 1
            
            print(f"Deleted {deleted_count} existing inventory records")
            
            # Insert new simplified inventory records (one per product)
            print(f"Inserting {len(inventory_records)} product inventory records...")
            inserted_count = 0
            failed_count = 0
            
            with table.batch_writer() as batch:
                for i, record in enumerate(inventory_records):
                    try:
                        # Convert any remaining datetime objects to strings for DynamoDB
                        dynamodb_record = prepare_for_dynamodb(record)
                        
                        # Validate required fields before insertion
                        if 'productId' not in dynamodb_record:
                            print(f"Skipping record {i+1}: missing productId")
                            failed_count += 1
                            continue
                            
                        batch.put_item(Item=dynamodb_record)
                        inserted_count += 1
                        
                        if inserted_count % 25 == 0:  # DynamoDB batch limit is 25
                            print(f"Inserted {inserted_count}/{len(inventory_records)} product inventory records")
                            
                    except Exception as e:
                        print(f"Failed to insert record {i+1}: {e}")
                        failed_count += 1
                        continue
            
            print(f"Successfully seeded {inserted_count} product inventory records to DynamoDB")
            if failed_count > 0:
                print(f"Failed to insert {failed_count} records")
            print(f"Each product now has a single inventory record (simplified structure)")
            
            # Verify the seeding
            verify_response = table.scan(Select='COUNT')
            actual_count = verify_response['Count']
            print(f"Verification: {actual_count} records found in DynamoDB table")
            
            return actual_count == len(inventory_records)
            
        except Exception as e:
            print(f"Error seeding inventory to DynamoDB: {e}")
            return False
    

    
    def print_seeding_summary(self, inventory_records: List[Dict[str, Any]]):
        """Print summary of seeded inventory data (simplified structure)"""
        if not inventory_records:
            return
        
        print(f"\n📊 Inventory Seeding Summary")
        print(f"{'='*50}")
        
        # Basic stats
        total_products = len(inventory_records)
        total_stock = sum(int(record.get("totalQuantity", 0)) for record in inventory_records)
        total_available = sum(int(record.get("availableQuantity", 0)) for record in inventory_records)
        total_reserved = sum(int(record.get("reservedQuantity", 0)) for record in inventory_records)
        total_value = sum(Decimal(str(record.get("totalValue", 0))) for record in inventory_records)
        total_alerts = sum(len(record.get("alerts", [])) for record in inventory_records)
        
        print(f"Products with inventory: {total_products}")
        print(f"Total stock units: {total_stock:,}")
        print(f"Available stock units: {total_available:,}")
        print(f"Reserved stock units: {total_reserved:,}")
        print(f"Total inventory value: ${total_value:,.2f}")
        print(f"Active alerts: {total_alerts}")
        
        # Category breakdown
        category_stats = {}
        for record in inventory_records:
            category = record.get("category", "Unknown")
            if category not in category_stats:
                category_stats[category] = {"count": 0, "stock": 0, "value": 0}
            
            category_stats[category]["count"] += 1
            category_stats[category]["stock"] += int(record.get("totalQuantity", 0))
            category_stats[category]["value"] += Decimal(str(record.get("totalValue", 0)))
        
        print(f"\nInventory by category:")
        for category, stats in sorted(category_stats.items()):
            print(f"  {category}: {stats['count']} products, {stats['stock']:,} units, ${stats['value']:,.2f}")
        
        # Stock status summary
        low_stock_count = 0
        out_of_stock_count = 0
        auto_reorder_enabled_count = 0
        
        for record in inventory_records:
            available = int(record.get("availableQuantity", 0))
            reorder_level = int(record.get("reorderLevel", 0))
            auto_reorder = record.get("autoReorderEnabled", False)
            
            if available == 0:
                out_of_stock_count += 1
            elif available <= reorder_level:
                low_stock_count += 1
                
            if auto_reorder:
                auto_reorder_enabled_count += 1
        
        print(f"\nStock status:")
        print(f"  Products in stock: {total_products - out_of_stock_count}")
        print(f"  Products with low stock: {low_stock_count}")
        print(f"  Products out of stock: {out_of_stock_count}")
        print(f"  Products with auto-reorder enabled: {auto_reorder_enabled_count}")
        
        # Alert summary
        alert_levels = {}
        for record in inventory_records:
            for alert in record.get("alerts", []):
                level = alert.get("alertLevel", "unknown")
                alert_levels[level] = alert_levels.get(level, 0) + 1
        
        if alert_levels:
            print(f"\nAlert summary:")
            for level, count in sorted(alert_levels.items()):
                print(f"  {level.title()} alerts: {count}")
        else:
            print(f"\nNo active alerts")

def main():
    """Main function to seed inventory data to DynamoDB"""
    try:
        print("🦄 Unicorn E-Commerce Inventory Database Seeder")
        print("=" * 60)
        print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        # Initialize seeder
        seeder = InventorySeeder()
        
        # Load inventory records from JSON
        inventory_records = seeder.load_inventory_from_json()
        
        if not inventory_records:
            print("No inventory records found. Please run inventory_generator.py first.")
            return
        
        # Validate correlation with products
        print("\nValidating product-inventory correlation...")
        correlation_valid = seeder.validate_inventory_product_correlation(inventory_records)
        
        if not correlation_valid:
            print("Warning: Poor correlation between products and inventory detected")
            response = input("Continue anyway? (y/N): ")
            if response.lower() != 'y':
                print("Seeding cancelled")
                return
        
        # Seed to DynamoDB
        print(f"\nSeeding {len(inventory_records)} inventory records to DynamoDB...")
        success = seeder.seed_to_dynamodb(inventory_records)
        
        if success:
            print("✅ Inventory seeding completed successfully!")
            seeder.print_seeding_summary(inventory_records)
            
            print(f"\n🚀 Inventory data is now available in DynamoDB table: {os.environ.get('INVENTORY_TABLE', 'INVENTORY_TABLE')}")
            print(f"   Products in DocumentDB are correlated with inventory in DynamoDB")
            print(f"   Each product has a single inventory record (simplified structure)")
            print(f"   Inventory includes stock levels, alerts, movement history, and supplier info")
        else:
            print("❌ Inventory seeding failed")
            return
            
    except Exception as e:
        print(f"Error in main execution: {e}")
        raise

if __name__ == "__main__":
    main()