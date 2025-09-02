#!/usr/bin/env python3
"""
ElastiCache Seeder for Unicorn E-Commerce
Seeds popular search terms and auto-complete suggestions to ElastiCache (Redis)
"""
import json
import os
import sys
import redis
from datetime import datetime
from typing import List, Dict, Any

# Import common database connections
from database_connections import get_elasticache_client

class ElastiCacheSeeder:
    """Seed search terms and suggestions to ElastiCache (Redis)"""
    
    def __init__(self):
        self.redis_client = get_elasticache_client()
    
    def load_popular_terms_from_json(self, filename: str = "popular_search_terms.json") -> List[Dict[str, Any]]:
        """Load popular search terms from JSON file"""
        try:
            filepath = os.path.join(os.path.dirname(__file__), '..', 'output', filename)
            
            if os.path.exists(filepath):
                with open(filepath, 'r', encoding='utf-8') as f:
                    terms_data = json.load(f)
                print(f"✅ Loaded {len(terms_data)} popular search terms from {filepath}")
                return terms_data
            
            print(f"❌ No popular search terms file found at {filepath}")
            return []
            
        except Exception as e:
            print(f"❌ Error loading popular search terms from JSON: {e}")
            return []
    
    def seed_popular_terms_to_cache(self, terms_data: List[Dict[str, Any]]) -> bool:
        """Seed popular search terms to ElastiCache"""
        try:
            if not self.redis_client:
                print("❌ Redis connection not available")
                return False
            
            print("🔄 Seeding popular search terms to ElastiCache...")
            
            # Clear existing popular terms cache
            try:
                # Clear all search-related keys
                keys_to_delete = []
                keys_to_delete.extend(self.redis_client.keys('search:popular_terms'))
                keys_to_delete.extend(self.redis_client.keys('search:trending_terms'))
                keys_to_delete.extend(self.redis_client.keys('search_suggestions:*'))
                keys_to_delete.extend(self.redis_client.keys('search:category:*'))
                keys_to_delete.extend(self.redis_client.keys('search:autocomplete:*'))
                
                if keys_to_delete:
                    self.redis_client.delete(*keys_to_delete)
                    print(f"✅ Cleared {len(keys_to_delete)} existing search cache keys")
            except Exception as e:
                print(f"⚠️  Warning: Could not clear existing cache: {e}")
            
            # Prepare popular terms list (top 50 terms)
            popular_terms_list = []
            for term_data in terms_data[:50]:  # Top 50 terms
                popular_terms_list.append({
                    'term': term_data['term'],
                    'searchVolume': term_data['searchVolume'],
                    'rank': term_data['rank'],
                    'category': term_data['category'],
                    'popularityScore': term_data.get('popularityScore', 0),
                    'clickThroughRate': term_data.get('clickThroughRate', 0),
                    'conversionRate': term_data.get('conversionRate', 0)
                })
            
            # Cache popular terms list (1 hour TTL)
            self.redis_client.setex(
                'search:popular_terms',
                3600,  # 1 hour TTL
                json.dumps(popular_terms_list)
            )
            print(f"✅ Cached {len(popular_terms_list)} popular search terms")
            
            # Cache individual term data with analytics (30 minutes TTL)
            analytics_count = 0
            for term_data in terms_data:
                search_term = term_data['term']
                
                # Cache full term analytics
                analytics_data = {
                    'term': search_term,
                    'searchVolume': term_data['searchVolume'],
                    'category': term_data['category'],
                    'rank': term_data['rank'],
                    'clickThroughRate': term_data.get('clickThroughRate', 0),
                    'conversionRate': term_data.get('conversionRate', 0),
                    'bounceRate': term_data.get('bounceRate', 0),
                    'avgSessionDuration': term_data.get('avgSessionDuration', 0),
                    'seasonality': term_data.get('seasonality', 'year-round'),
                    'trendData': term_data.get('trendData', [])
                }
                
                cache_key = f"search:analytics:{search_term}"
                self.redis_client.setex(
                    cache_key,
                    1800,  # 30 minutes TTL
                    json.dumps(analytics_data)
                )
                analytics_count += 1
                
                # Cache related terms for suggestions
                related_terms = term_data.get('relatedTerms', [])
                if related_terms:
                    suggestions_key = f"search_suggestions:{search_term}"
                    self.redis_client.setex(
                        suggestions_key,
                        1800,  # 30 minutes TTL
                        json.dumps(related_terms)
                    )
            
            print(f"✅ Cached analytics for {analytics_count} search terms")
            
            # Cache trending terms (2 hours TTL)
            trending_terms = []
            for term_data in terms_data[:10]:  # Top 10 as trending
                trending_terms.append({
                    'term': term_data['term'],
                    'searchVolume': term_data['searchVolume'],
                    'category': term_data['category'],
                    'popularityScore': term_data.get('popularityScore', 0)
                })
            
            self.redis_client.setex(
                'search:trending_terms',
                7200,  # 2 hours TTL
                json.dumps(trending_terms)
            )
            print(f"✅ Cached {len(trending_terms)} trending search terms")
            
            # Cache auto-complete data by category
            categories = {}
            for term_data in terms_data:
                category = term_data['category']
                if category not in categories:
                    categories[category] = []
                categories[category].append({
                    'term': term_data['term'],
                    'searchVolume': term_data['searchVolume']
                })
            
            # Sort by search volume and cache top terms per category
            for category, terms in categories.items():
                sorted_terms = sorted(terms, key=lambda x: x['searchVolume'], reverse=True)
                cache_key = f"search:category:{category}"
                self.redis_client.setex(
                    cache_key,
                    3600,  # 1 hour TTL
                    json.dumps([t['term'] for t in sorted_terms[:20]])  # Top 20 terms per category
                )
            
            print(f"✅ Cached search terms for {len(categories)} categories")
            
            # Cache autocomplete prefixes for fast lookup
            autocomplete_count = 0
            for term_data in terms_data[:100]:  # Top 100 terms for autocomplete
                term = term_data['term'].lower()
                
                # Create prefix keys for autocomplete (1-4 characters)
                for i in range(1, min(len(term) + 1, 5)):
                    prefix = term[:i]
                    prefix_key = f"search:autocomplete:{prefix}"
                    
                    # Get existing terms for this prefix or create new list
                    try:
                        existing_terms = self.redis_client.get(prefix_key)
                        if existing_terms:
                            terms_list = json.loads(existing_terms)
                        else:
                            terms_list = []
                        
                        # Add term if not already present
                        if term not in terms_list:
                            terms_list.append(term)
                            # Keep only top 10 suggestions per prefix
                            terms_list = terms_list[:10]
                            
                            self.redis_client.setex(
                                prefix_key,
                                3600,  # 1 hour TTL
                                json.dumps(terms_list)
                            )
                            autocomplete_count += 1
                    except Exception as e:
                        # If there's an error, create new entry
                        self.redis_client.setex(
                            prefix_key,
                            3600,
                            json.dumps([term])
                        )
                        autocomplete_count += 1
            
            print(f"✅ Created {autocomplete_count} autocomplete prefix entries")
            
            return True
            
        except Exception as e:
            print(f"❌ Error seeding popular terms to ElastiCache: {e}")
            return False
    
    def seed_search_behaviors_to_cache(self, behaviors_filename: str = "search_behaviors.json") -> bool:
        """Seed recent search behaviors to ElastiCache for analytics"""
        try:
            if not self.redis_client:
                print("❌ Redis connection not available")
                return False
            
            filepath = os.path.join(os.path.dirname(__file__), '..', 'output', behaviors_filename)
            
            if not os.path.exists(filepath):
                print(f"⚠️  No search behaviors file found at {filepath}")
                return True  # Not critical, return success
            
            with open(filepath, 'r', encoding='utf-8') as f:
                behaviors_data = json.load(f)
            
            print(f"🔄 Caching recent search behaviors...")
            
            # Cache recent searches (last 100) for real-time analytics
            recent_searches = behaviors_data[-100:] if len(behaviors_data) > 100 else behaviors_data
            
            self.redis_client.setex(
                'search:recent_behaviors',
                1800,  # 30 minutes TTL
                json.dumps(recent_searches)
            )
            
            print(f"✅ Cached {len(recent_searches)} recent search behaviors")
            
            # Cache search analytics summary
            summary_filepath = os.path.join(os.path.dirname(__file__), '..', 'output', 'search_analytics_summary.json')
            if os.path.exists(summary_filepath):
                with open(summary_filepath, 'r', encoding='utf-8') as f:
                    summary_data = json.load(f)
                
                self.redis_client.setex(
                    'search:analytics_summary',
                    3600,  # 1 hour TTL
                    json.dumps(summary_data)
                )
                print("✅ Cached search analytics summary")
            
            return True
            
        except Exception as e:
            print(f"❌ Error seeding search behaviors to ElastiCache: {e}")
            return False
    
    def verify_cache_data(self) -> bool:
        """Verify that data was properly cached"""
        try:
            if not self.redis_client:
                print("❌ Redis connection not available for verification")
                return False
            
            print("🔍 Verifying cached data...")
            
            # Check popular terms
            popular_terms = self.redis_client.get('search:popular_terms')
            if popular_terms:
                terms_data = json.loads(popular_terms)
                print(f"✅ Popular terms cache: {len(terms_data)} terms")
                
                # Show sample data
                if terms_data:
                    sample_term = terms_data[0]
                    print(f"   Sample: '{sample_term['term']}' - {sample_term['searchVolume']:,} searches")
            else:
                print("❌ Popular terms cache is empty")
                return False
            
            # Check trending terms
            trending_terms = self.redis_client.get('search:trending_terms')
            if trending_terms:
                trending_data = json.loads(trending_terms)
                print(f"✅ Trending terms cache: {len(trending_data)} terms")
            else:
                print("❌ Trending terms cache is empty")
                return False
            
            # Check analytics keys
            analytics_keys = self.redis_client.keys('search:analytics:*')
            print(f"✅ Search analytics: {len(analytics_keys)} terms cached")
            
            # Check suggestion keys
            suggestion_keys = self.redis_client.keys('search_suggestions:*')
            print(f"✅ Auto-complete suggestions: {len(suggestion_keys)} terms cached")
            
            # Check category keys
            category_keys = self.redis_client.keys('search:category:*')
            print(f"✅ Category searches: {len(category_keys)} categories cached")
            
            # Check autocomplete prefix keys
            autocomplete_keys = self.redis_client.keys('search:autocomplete:*')
            print(f"✅ Autocomplete prefixes: {len(autocomplete_keys)} prefix entries")
            
            # Test a sample autocomplete lookup
            if autocomplete_keys:
                sample_key = autocomplete_keys[0].decode('utf-8') if isinstance(autocomplete_keys[0], bytes) else autocomplete_keys[0]
                sample_data = self.redis_client.get(sample_key)
                if sample_data:
                    sample_terms = json.loads(sample_data)
                    prefix = sample_key.split(':')[-1]
                    print(f"   Sample autocomplete '{prefix}': {len(sample_terms)} suggestions")
            
            print("✅ ElastiCache verification completed successfully")
            return True
            
        except Exception as e:
            print(f"❌ Error verifying cache data: {e}")
            return False


def main():
    """Main function to seed ElastiCache with search data"""
    try:
        print("🔍 Unicorn E-Commerce Popular Search Terms ElastiCache Seeder")
        print("=" * 70)
        print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        # Initialize seeder
        seeder = ElastiCacheSeeder()
        
        # Load popular search terms
        terms_data = seeder.load_popular_terms_from_json()
        
        if not terms_data:
            print("❌ No popular search terms data available")
            print("Please run popular_search_terms_generator.py first to generate the data.")
            return False
        
        print(f"\nLoaded {len(terms_data)} search terms for caching")
        
        # Seed popular terms to cache
        if not seeder.seed_popular_terms_to_cache(terms_data):
            print("❌ Failed to seed popular terms to ElastiCache")
            return False
        
        # Seed search behaviors to cache (optional)
        if not seeder.seed_search_behaviors_to_cache():
            print("⚠️  Failed to seed search behaviors to ElastiCache (non-critical)")
        
        # Verify cached data
        if not seeder.verify_cache_data():
            print("❌ Cache verification failed")
            return False
        
        print("\n✅ ElastiCache seeding completed successfully!")
        print(f"\n🚀 Popular search terms are now cached in ElastiCache:")
        print(f"   • Popular terms: search:popular_terms")
        print(f"   • Trending terms: search:trending_terms") 
        print(f"   • Analytics data: search:analytics:*")
        print(f"   • Autocomplete: search:autocomplete:*")
        print(f"   • Category terms: search:category:*")
        print(f"   • Related suggestions: search_suggestions:*")
        print(f"\n   Ready for high-performance search features!")
        
        return True
        
    except Exception as e:
        print(f"❌ Error in ElastiCache seeding: {e}")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)