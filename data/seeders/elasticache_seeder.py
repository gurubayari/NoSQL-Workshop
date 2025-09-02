#!/usr/bin/env python3
"""
ElastiCache Seeder for Unicorn E-Commerce
Seeds popular search terms and auto-complete suggestions to ElastiCache (Redis)
"""
import json
import os
import sys
import redis
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
                self.redis_client.delete('search:popular_terms')
                print("✅ Cleared existing popular terms cache")
            except Exception as e:
                print(f"⚠️  Warning: Could not clear existing cache: {e}")
            
            # Prepare popular terms list (top 50 terms)
            popular_terms_list = []
            for term_data in terms_data[:50]:  # Top 50 terms
                popular_terms_list.append({
                    'term': term_data['searchTerm'],
                    'frequency': term_data['frequency'],
                    'rank': term_data['rank'],
                    'category': term_data['category']
                })
            
            # Cache popular terms list (1 hour TTL)
            self.redis_client.setex(
                'search:popular_terms',
                3600,  # 1 hour TTL
                json.dumps(popular_terms_list)
            )
            print(f"✅ Cached {len(popular_terms_list)} popular search terms")
            
            # Cache individual term suggestions (30 minutes TTL)
            suggestions_count = 0
            for term_data in terms_data:
                search_term = term_data['searchTerm']
                suggestions = term_data.get('suggestions', [])
                
                if suggestions:
                    cache_key = f"search_suggestions:{search_term}"
                    self.redis_client.setex(
                        cache_key,
                        1800,  # 30 minutes TTL
                        json.dumps(suggestions)
                    )
                    suggestions_count += 1
            
            print(f"✅ Cached suggestions for {suggestions_count} search terms")
            
            # Cache trending terms (2 hours TTL)
            trending_terms = []
            for term_data in terms_data[:10]:  # Top 10 as trending
                trending_terms.append({
                    'term': term_data['searchTerm'],
                    'frequency': term_data['frequency'],
                    'category': term_data['category']
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
                categories[category].append(term_data['searchTerm'])
            
            for category, terms in categories.items():
                cache_key = f"search:category:{category}"
                self.redis_client.setex(
                    cache_key,
                    3600,  # 1 hour TTL
                    json.dumps(terms[:20])  # Top 20 terms per category
                )
            
            print(f"✅ Cached search terms for {len(categories)} categories")
            
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
            
            # Check a few suggestion keys
            suggestion_keys = self.redis_client.keys('search_suggestions:*')
            print(f"✅ Auto-complete suggestions: {len(suggestion_keys)} terms cached")
            
            # Check category keys
            category_keys = self.redis_client.keys('search:category:*')
            print(f"✅ Category searches: {len(category_keys)} categories cached")
            
            print("✅ ElastiCache verification completed successfully")
            return True
            
        except Exception as e:
            print(f"❌ Error verifying cache data: {e}")
            return False


def main():
    """Main function to seed ElastiCache with search data"""
    try:
        print("🚀 Starting ElastiCache seeding...")
        
        # Initialize seeder
        seeder = ElastiCacheSeeder()
        
        # Load popular search terms
        terms_data = seeder.load_popular_terms_from_json()
        
        if not terms_data:
            print("❌ No popular search terms data available")
            return False
        
        # Seed popular terms to cache
        if not seeder.seed_popular_terms_to_cache(terms_data):
            print("❌ Failed to seed popular terms to ElastiCache")
            return False
        
        # Seed search behaviors to cache
        if not seeder.seed_search_behaviors_to_cache():
            print("⚠️  Failed to seed search behaviors to ElastiCache (non-critical)")
        
        # Verify cached data
        if not seeder.verify_cache_data():
            print("❌ Cache verification failed")
            return False
        
        print("✅ ElastiCache seeding completed successfully!")
        return True
        
    except Exception as e:
        print(f"❌ Error in ElastiCache seeding: {e}")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)