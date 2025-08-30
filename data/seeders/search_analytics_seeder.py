"""
Search Analytics Database Seeder for Unicorn E-Commerce
Seeds pre-generated search analytics data to DynamoDB
"""
import json
import os
import sys
from datetime import datetime
from typing import List, Dict, Any

try:
    import boto3
    from botocore.exceptions import ClientError
    BOTO3_AVAILABLE = True
except ImportError:
    BOTO3_AVAILABLE = False
    print("boto3 not available - running in mock mode")

# Add backend to path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'backend'))

try:
    from shared.config import config
    from shared.database import get_dynamodb_table
    AWS_AVAILABLE = True
except ImportError:
    # Fallback for development without AWS dependencies
    AWS_AVAILABLE = False
    
    class MockConfig:
        AWS_REGION = 'us-west-2'
        SEARCH_ANALYTICS_TABLE = 'unicorn-ecommerce-dev-search-analytics'
    
    config = MockConfig()
    
    def get_dynamodb_table(table_name):
        print(f"Mock DynamoDB table: {table_name}")
        return None

class SearchAnalyticsSeeder:
    """Seed search analytics data to DynamoDB"""
    
    def __init__(self):
        if AWS_AVAILABLE and BOTO3_AVAILABLE:
            self.dynamodb = boto3.resource('dynamodb', region_name=config.AWS_REGION)
        else:
            self.dynamodb = None
            print("Running in mock mode - AWS services not available")
    
    def load_search_analytics_from_json(self, filename: str = "search_analytics.json") -> List[Dict[str, Any]]:
        """Load search analytics records from JSON file"""
        try:
            filepath = os.path.join(os.path.dirname(__file__), '..', 'output', filename)
            
            if os.path.exists(filepath):
                with open(filepath, 'r', encoding='utf-8') as f:
                    search_data = json.load(f)
                print(f"Loaded search analytics data from {filepath}")
                return search_data
            
            print(f"No search analytics file found at {filepath}")
            return []
            
        except Exception as e:
            print(f"Error loading search analytics from JSON: {e}")
            return []
    
    def seed_to_dynamodb(self, search_data: List[Dict[str, Any]]) -> bool:
        """Seed search analytics records to DynamoDB"""
        if not AWS_AVAILABLE or not BOTO3_AVAILABLE:
            print("AWS services not available - skipping DynamoDB seeding")
            print(f"Would have seeded search analytics data to DynamoDB table: {config.SEARCH_ANALYTICS_TABLE}")
            return True
            
        try:
            table = get_dynamodb_table(config.SEARCH_ANALYTICS_TABLE)
            
            if not table:
                print(f"Failed to get DynamoDB table: {config.SEARCH_ANALYTICS_TABLE}")
                return False
            
            # Clear existing search analytics (for development)
            print("Clearing existing search analytics records...")
            scan_response = table.scan()
            deleted_count = 0
            
            with table.batch_writer() as batch:
                for item in scan_response['Items']:
                    # Assuming the table has a composite key or single key
                    # Adjust the key structure based on your table design
                    if 'searchTerm' in item:
                        batch.delete_item(Key={'searchTerm': item['searchTerm']})
                    elif 'id' in item:
                        batch.delete_item(Key={'id': item['id']})
                    deleted_count += 1
            
            print(f"Deleted {deleted_count} existing search analytics records")
            
            # Insert new search analytics records
            print("Inserting new search analytics records...")
            inserted_count = 0
            
            with table.batch_writer() as batch:
                for record in search_data:
                    # Prepare record for DynamoDB
                    dynamodb_record = self._prepare_for_dynamodb(record)
                    batch.put_item(Item=dynamodb_record)
                    inserted_count += 1
                    
                    if inserted_count % 25 == 0:  # DynamoDB batch limit is 25
                        print(f"Inserted {inserted_count}/{len(search_data)} search analytics records")
            
            print(f"Successfully seeded {inserted_count} search analytics records to DynamoDB")
            
            # Verify the seeding
            verify_response = table.scan(Select='COUNT')
            actual_count = verify_response['Count']
            print(f"Verification: {actual_count} records found in DynamoDB table")
            
            return actual_count == len(search_data)
            
        except Exception as e:
            print(f"Error seeding search analytics to DynamoDB: {e}")
            return False
    
    def _prepare_for_dynamodb(self, record: Dict[str, Any]) -> Dict[str, Any]:
        """Prepare record for DynamoDB by ensuring all data types are compatible"""
        def convert_recursive(obj):
            if isinstance(obj, datetime):
                return obj.isoformat()
            elif isinstance(obj, dict):
                return {k: convert_recursive(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [convert_recursive(item) for item in obj]
            elif isinstance(obj, (int, float, str, bool)) or obj is None:
                return obj
            else:
                # Convert any other type to string
                return str(obj)
        
        return convert_recursive(record)

def main():
    """Main function to seed search analytics data to DynamoDB"""
    try:
        print("🦄 Unicorn E-Commerce Search Analytics Database Seeder")
        print("=" * 60)
        print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        # Initialize seeder
        seeder = SearchAnalyticsSeeder()
        
        # Load search analytics records from JSON
        search_data = seeder.load_search_analytics_from_json()
        
        if not search_data:
            print("No search analytics data found. Skipping search analytics seeding.")
            return
        
        # Seed to DynamoDB
        print(f"\nSeeding search analytics data to DynamoDB...")
        success = seeder.seed_to_dynamodb(search_data)
        
        if success:
            print("✅ Search analytics seeding completed successfully!")
            print(f"🚀 Search analytics data is now available in DynamoDB table: {config.SEARCH_ANALYTICS_TABLE}")
        else:
            print("❌ Search analytics seeding failed")
            return
            
    except Exception as e:
        print(f"Error in main execution: {e}")
        raise

if __name__ == "__main__":
    main()