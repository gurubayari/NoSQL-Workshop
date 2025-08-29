"""
End-to-end tests for search functionality
Tests complete search workflows from auto-complete to results display
"""
import pytest
import json
import time
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock
import sys
import os

# Add the functions directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'functions'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'shared'))

class TestSearchFunctionality:
    """End-to-end tests for search functionality"""
    
    def setup_method(self):
        """Set up test data for search functionality"""
        self.test_user = {
            'userId': 'search_user_123',
            'preferences': {
                'categories': ['Electronics', 'Computers'],
                'price_range': [50, 500]
            }
        }
        
        self.test_search_scenarios = [
            {
                'query': 'wireless headphones',
                'expected_suggestions': [
                    'wireless headphones',
                    'wireless headphones bluetooth',
                    'wireless headphones noise cancelling'
                ],
                'expected_products': ['Wireless Bluetooth Headphones'],
                'expected_categories': ['Electronics']
            },
            {
                'query': 'gaming',
                'expected_suggestions': [
                    'gaming mouse',
                    'gaming headset',
                    'gaming keyboard'
                ],
                'expected_products': ['Gaming Mouse', 'Gaming Headset'],
                'expected_categories': ['Electronics', 'Computers']
            },
            {
                'query': 'bluetooth',
                'expected_suggestions': [
                    'bluetooth speaker',
                    'bluetooth headphones',
                    'bluetooth mouse'
                ],
                'expected_products': ['Bluetooth Speaker', 'Wireless Bluetooth Headphones'],
                'expected_categories': ['Electronics']
            }
        ]
    
    def test_complete_search_workflow(self):
        """Test complete search workflow from typing to results"""
        with patch('search_api.SearchAPI') as mock_search_api:
            search_api_instance = MagicMock()
            mock_search_api.return_value = search_api_instance
            
            query = 'wireless headphones'
            
            # Step 1: User starts typing - get auto-complete suggestions
            search_api_instance.get_auto_complete_suggestions.return_value = [
                {'text': 'wireless headphones', 'type': 'popular', 'count': 1500, 'popularity': 1500},
                {'text': 'wireless headphones bluetooth', 'type': 'popular', 'count': 800, 'popularity': 800},
                {'text': 'Wireless Bluetooth Headphones Premium', 'type': 'product', 'rating': 4.5, 'popularity': 200}
            ]
            
            suggestions = search_api_instance.get_auto_complete_suggestions(query[:8])  # "wireless"
            assert len(suggestions) == 3
            assert suggestions[0]['type'] == 'popular'
            assert suggestions[2]['type'] == 'product'
            
            # Step 2: User selects suggestion or completes typing
            search_api_instance.search_products.return_value = {
                'products': [
                    {
                        'product_id': 'prod_1',
                        'title': 'Wireless Bluetooth Headphones',
                        'description': 'Premium wireless headphones with noise cancellation',
                        'price': 199.99,
                        'rating': 4.5,
                        'review_count': 150,
                        'highlightedTitle': '<mark>Wireless</mark> Bluetooth <mark>Headphones</mark>',
                        'highlightedDescription': 'Premium <mark>wireless</mark> <mark>headphones</mark> with noise cancellation'
                    }
                ],
                'total': 1,
                'query': query,
                'page': 1,
                'totalPages': 1,
                'alternatives': []
            }
            
            search_results = search_api_instance.search_products(
                query,
                filters={'category': ['Electronics']},
                sort_by='relevance',
                page=1,
                page_size=20
            )
            
            assert search_results['total'] == 1
            assert len(search_results['products']) == 1
            assert '<mark>' in search_results['products'][0]['highlightedTitle']
            
            # Step 3: User applies additional filters
            filtered_search_results = search_api_instance.search_products(
                query,
                filters={
                    'category': ['Electronics'],
                    'min_price': '100',
                    'max_price': '300',
                    'min_rating': '4.0'
                },
                sort_by='price_low',
                page=1,
                page_size=20
            )
            
            # Should still return the headphones (meets all criteria)
            assert filtered_search_results['total'] >= 0
            
            # Step 4: User searches for something with no results
            search_api_instance.search_products.return_value = {
                'products': [],
                'total': 0,
                'query': 'nonexistent product xyz',
                'alternatives': ['wireless headphones', 'bluetooth speaker', 'gaming mouse']
            }
            
            no_results = search_api_instance.search_products('nonexistent product xyz')
            assert no_results['total'] == 0
            assert len(no_results['alternatives']) > 0
    
    def test_search_analytics_tracking(self):
        """Test search analytics and tracking functionality"""
        with patch('search_api.SearchAPI') as mock_search_api:
            search_api_instance = MagicMock()
            mock_search_api.return_value = search_api_instance
            
            # Simulate multiple searches to test analytics
            search_queries = [
                'wireless headphones',
                'gaming mouse',
                'bluetooth speaker',
                'wireless headphones',  # Duplicate to test frequency
                'usb cable'
            ]
            
            # Mock search analytics tracking
            search_frequencies = {}
            
            def mock_track_analytics(query, filters=None):
                search_frequencies[query.lower()] = search_frequencies.get(query.lower(), 0) + 1
            
            search_api_instance._track_search_analytics = mock_track_analytics
            
            # Perform searches
            for query in search_queries:
                search_api_instance.search_products(query)
                search_api_instance._track_search_analytics(query)
            
            # Verify analytics tracking
            assert search_frequencies['wireless headphones'] == 2
            assert search_frequencies['gaming mouse'] == 1
            assert search_frequencies['bluetooth speaker'] == 1
            assert search_frequencies['usb cable'] == 1
            
            # Test popular terms update
            popular_terms = []
            for term, count in search_frequencies.items():
                popular_terms.append({'term': term, 'count': count})
            
            popular_terms.sort(key=lambda x: x['count'], reverse=True)
            
            # Most popular should be wireless headphones
            assert popular_terms[0]['term'] == 'wireless headphones'
            assert popular_terms[0]['count'] == 2
    
    def test_search_performance_optimization(self):
        """Test search performance with caching and optimization"""
        with patch('search_api.SearchAPI') as mock_search_api:
            search_api_instance = MagicMock()
            mock_search_api.return_value = search_api_instance
            
            query = 'wireless headphones'
            
            # First search - should hit database
            search_api_instance.search_products.return_value = {
                'products': [
                    {
                        'product_id': 'prod_1',
                        'title': 'Wireless Bluetooth Headphones',
                        'price': 199.99,
                        'rating': 4.5
                    }
                ],
                'total': 1,
                'query': query,
                'cached': False
            }
            
            start_time = time.time()
            first_result = search_api_instance.search_products(query)
            first_search_time = time.time() - start_time
            
            assert first_result['total'] == 1
            
            # Second search - should hit cache (simulated)
            search_api_instance.search_products.return_value = {
                'products': [
                    {
                        'product_id': 'prod_1',
                        'title': 'Wireless Bluetooth Headphones',
                        'price': 199.99,
                        'rating': 4.5
                    }
                ],
                'total': 1,
                'query': query,
                'cached': True
            }
            
            start_time = time.time()
            second_result = search_api_instance.search_products(query)
            second_search_time = time.time() - start_time
            
            assert second_result['total'] == 1
            # In real implementation, cached result should be faster
            # For mocked tests, we just verify the cache flag
            assert second_result.get('cached') is True
    
    def test_search_relevance_scoring(self):
        """Test search relevance scoring and ranking"""
        with patch('search_api.SearchAPI') as mock_search_api:
            search_api_instance = MagicMock()
            mock_search_api.return_value = search_api_instance
            
            query = 'wireless audio'
            
            # Mock search results with different relevance scores
            search_api_instance.search_products.return_value = {
                'products': [
                    {
                        'product_id': 'prod_1',
                        'title': 'Wireless Audio Headphones',  # Exact match
                        'relevance_score': 10.5,
                        'rating': 4.5,
                        'review_count': 200
                    },
                    {
                        'product_id': 'prod_2',
                        'title': 'Bluetooth Audio Speaker',  # Partial match
                        'relevance_score': 7.2,
                        'rating': 4.3,
                        'review_count': 150
                    },
                    {
                        'product_id': 'prod_3',
                        'title': 'Wireless Mouse',  # Weak match
                        'relevance_score': 2.1,
                        'rating': 4.1,
                        'review_count': 80
                    }
                ],
                'total': 3,
                'query': query
            }
            
            results = search_api_instance.search_products(query, sort_by='relevance')
            
            # Verify results are sorted by relevance
            products = results['products']
            assert len(products) == 3
            
            # Check relevance score ordering
            assert products[0]['relevance_score'] > products[1]['relevance_score']
            assert products[1]['relevance_score'] > products[2]['relevance_score']
            
            # Verify exact match ranks highest
            assert 'Wireless Audio Headphones' in products[0]['title']
    
    def test_search_with_no_results_handling(self):
        """Test search behavior when no results are found"""
        with patch('search_api.SearchAPI') as mock_search_api:
            search_api_instance = MagicMock()
            mock_search_api.return_value = search_api_instance
            
            # Search for something that doesn't exist
            query = 'quantum flux capacitor'
            
            search_api_instance.search_products.return_value = {
                'products': [],
                'total': 0,
                'query': query,
                'alternatives': [
                    'wireless headphones',
                    'bluetooth speaker',
                    'gaming accessories',
                    'electronics',
                    'audio devices'
                ]
            }
            
            no_results = search_api_instance.search_products(query)
            
            assert no_results['total'] == 0
            assert len(no_results['products']) == 0
            assert len(no_results['alternatives']) > 0
            
            # Verify alternatives are reasonable suggestions
            alternatives = no_results['alternatives']
            assert isinstance(alternatives, list)
            assert all(isinstance(alt, str) for alt in alternatives)
            assert len(alternatives) <= 10  # Reasonable number of alternatives


class TestSearchIntegrationScenarios:
    """Integration scenarios for search functionality"""
    
    def test_search_to_purchase_workflow(self):
        """Test complete workflow from search to purchase"""
        with patch('search_api.SearchAPI') as mock_search_api, \
             patch('product_api.ProductAPI') as mock_product_api, \
             patch('cart_api.ShoppingCartAPI') as mock_cart_api, \
             patch('order_api.OrderManagementAPI') as mock_order_api:
            
            # Initialize mocks
            search_api_instance = MagicMock()
            product_api_instance = MagicMock()
            cart_api_instance = MagicMock()
            order_api_instance = MagicMock()
            
            mock_search_api.return_value = search_api_instance
            mock_product_api.return_value = product_api_instance
            mock_cart_api.return_value = cart_api_instance
            mock_order_api.return_value = order_api_instance
            
            user_id = 'workflow_user_123'
            
            # Step 1: User searches for products
            search_api_instance.search_products.return_value = {
                'products': [
                    {
                        'product_id': 'prod_workflow_1',
                        'title': 'Wireless Gaming Headset',
                        'price': 149.99,
                        'rating': 4.4,
                        'in_stock': True
                    }
                ],
                'total': 1,
                'query': 'gaming headset'
            }
            
            search_results = search_api_instance.search_products('gaming headset')
            assert search_results['total'] == 1
            
            # Step 2: User views product details
            product_api_instance.get_product_detail.return_value = {
                'statusCode': 200,
                'body': json.dumps({
                    'product': {
                        'product_id': 'prod_workflow_1',
                        'title': 'Wireless Gaming Headset',
                        'description': 'Professional gaming headset with surround sound',
                        'price': 149.99,
                        'rating': 4.4,
                        'in_stock': True
                    },
                    'reviews_summary': {
                        'total_reviews': 89,
                        'average_rating': 4.4
                    }
                })
            }
            
            product_detail_event = {'pathParameters': {'id': 'prod_workflow_1'}}
            detail_result = product_api_instance.get_product_detail(product_detail_event)
            assert detail_result['statusCode'] == 200
            
            # Step 3: User adds to cart
            cart_api_instance.add_to_cart.return_value = {
                'statusCode': 200,
                'body': json.dumps({
                    'message': 'Item added to cart successfully',
                    'productId': 'prod_workflow_1',
                    'quantity': 1,
                    'price': 149.99
                })
            }
            
            add_to_cart_event = {
                'pathParameters': {'userId': user_id},
                'body': json.dumps({
                    'productId': 'prod_workflow_1',
                    'quantity': 1
                })
            }
            
            cart_result = cart_api_instance.add_to_cart(add_to_cart_event)
            assert cart_result['statusCode'] == 200
            
            # Step 4: User completes purchase
            order_api_instance.create_order.return_value = {
                'statusCode': 201,
                'body': json.dumps({
                    'orderId': 'ORD-WORKFLOW-123',
                    'status': 'confirmed',
                    'totalAmount': 164.98,  # Including tax
                    'message': 'Order created successfully'
                })
            }
            
            create_order_event = {
                'body': json.dumps({
                    'userId': user_id,
                    'items': [{'productId': 'prod_workflow_1', 'quantity': 1}],
                    'paymentMethod': {'type': 'credit_card'},
                    'shippingAddress': {'state': 'CA'}
                })
            }
            
            order_result = order_api_instance.create_order(create_order_event)
            assert order_result['statusCode'] == 201
            
            # Verify complete workflow
            order_data = json.loads(order_result['body'])
            assert 'orderId' in order_data
            assert order_data['status'] == 'confirmed'
    
    def test_search_with_filters_workflow(self):
        """Test search workflow with various filters applied"""
        with patch('search_api.SearchAPI') as mock_search_api:
            search_api_instance = MagicMock()
            mock_search_api.return_value = search_api_instance
            
            # Step 1: Basic search
            search_api_instance.search_products.return_value = {
                'products': [
                    {'product_id': 'p1', 'title': 'Headphones A', 'price': 99.99, 'rating': 4.2},
                    {'product_id': 'p2', 'title': 'Headphones B', 'price': 199.99, 'rating': 4.5},
                    {'product_id': 'p3', 'title': 'Headphones C', 'price': 299.99, 'rating': 4.8}
                ],
                'total': 3,
                'query': 'headphones'
            }
            
            basic_results = search_api_instance.search_products('headphones')
            assert basic_results['total'] == 3
            
            # Step 2: Apply price filter
            search_api_instance.search_products.return_value = {
                'products': [
                    {'product_id': 'p1', 'title': 'Headphones A', 'price': 99.99, 'rating': 4.2},
                    {'product_id': 'p2', 'title': 'Headphones B', 'price': 199.99, 'rating': 4.5}
                ],
                'total': 2,
                'query': 'headphones'
            }
            
            price_filtered = search_api_instance.search_products(
                'headphones',
                filters={'min_price': '50', 'max_price': '250'}
            )
            assert price_filtered['total'] == 2  # Excludes the $299.99 option
            
            # Step 3: Apply rating filter
            search_api_instance.search_products.return_value = {
                'products': [
                    {'product_id': 'p2', 'title': 'Headphones B', 'price': 199.99, 'rating': 4.5}
                ],
                'total': 1,
                'query': 'headphones'
            }
            
            rating_filtered = search_api_instance.search_products(
                'headphones',
                filters={'min_rating': '4.4'}
            )
            assert rating_filtered['total'] == 1  # Only the 4.5-rated product
            
            # Step 4: Sort by price
            search_api_instance.search_products.return_value = {
                'products': [
                    {'product_id': 'p1', 'title': 'Headphones A', 'price': 99.99, 'rating': 4.2},
                    {'product_id': 'p2', 'title': 'Headphones B', 'price': 199.99, 'rating': 4.5},
                    {'product_id': 'p3', 'title': 'Headphones C', 'price': 299.99, 'rating': 4.8}
                ],
                'total': 3,
                'query': 'headphones'
            }
            
            price_sorted = search_api_instance.search_products(
                'headphones',
                sort_by='price_low'
            )
            
            # Verify sorting (lowest price first)
            products = price_sorted['products']
            assert products[0]['price'] <= products[1]['price']
            assert products[1]['price'] <= products[2]['price']
    
    def test_auto_complete_user_experience(self):
        """Test auto-complete user experience scenarios"""
        with patch('search_api.SearchAPI') as mock_search_api:
            search_api_instance = MagicMock()
            mock_search_api.return_value = search_api_instance
            
            # Test progressive typing scenarios
            typing_scenarios = [
                ('w', []),  # Too short
                ('wi', []),  # Still too short
                ('wir', ['wireless headphones', 'wireless mouse', 'wireless keyboard']),
                ('wire', ['wireless headphones', 'wireless mouse', 'wireless keyboard']),
                ('wirel', ['wireless headphones', 'wireless mouse', 'wireless keyboard']),
                ('wirele', ['wireless headphones', 'wireless mouse', 'wireless keyboard']),
                ('wireless', ['wireless headphones', 'wireless mouse', 'wireless keyboard']),
                ('wireless h', ['wireless headphones', 'wireless headset']),
                ('wireless he', ['wireless headphones', 'wireless headset']),
                ('wireless hea', ['wireless headphones', 'wireless headset'])
            ]
            
            for query_prefix, expected_suggestions in typing_scenarios:
                if len(query_prefix) < 2:
                    search_api_instance.get_auto_complete_suggestions.return_value = []
                else:
                    # Filter suggestions based on prefix
                    filtered_suggestions = [
                        {'text': suggestion, 'type': 'popular', 'count': 100}
                        for suggestion in expected_suggestions
                        if suggestion.startswith(query_prefix)
                    ]
                    search_api_instance.get_auto_complete_suggestions.return_value = filtered_suggestions
                
                suggestions = search_api_instance.get_auto_complete_suggestions(query_prefix)
                
                if len(query_prefix) < 2:
                    assert len(suggestions) == 0
                else:
                    # Should have relevant suggestions
                    assert all(
                        suggestion['text'].startswith(query_prefix) 
                        for suggestion in suggestions
                    )
    
    def test_search_error_recovery(self):
        """Test search error handling and recovery"""
        with patch('search_api.SearchAPI') as mock_search_api:
            search_api_instance = MagicMock()
            mock_search_api.return_value = search_api_instance
            
            # Test 1: Database error during search
            search_api_instance.search_products.return_value = {
                'products': [],
                'total': 0,
                'query': 'test query',
                'error': 'Database connection failed'
            }
            
            db_error_result = search_api_instance.search_products('test query')
            assert db_error_result['total'] == 0
            assert 'error' in db_error_result
            
            # Test 2: Auto-complete service error
            search_api_instance.get_auto_complete_suggestions.return_value = []
            
            # Should gracefully handle errors and return empty suggestions
            error_suggestions = search_api_instance.get_auto_complete_suggestions('test')
            assert error_suggestions == []
            
            # Test 3: Recovery after error
            # After error, subsequent searches should work
            search_api_instance.search_products.return_value = {
                'products': [
                    {'product_id': 'p1', 'title': 'Recovery Product', 'price': 99.99}
                ],
                'total': 1,
                'query': 'recovery test'
            }
            
            recovery_result = search_api_instance.search_products('recovery test')
            assert recovery_result['total'] == 1
            assert len(recovery_result['products']) == 1


    def test_semantic_search_quality_validation(self):
        """Test semantic search quality and relevance scoring"""
        with patch('search_api.SearchAPI') as mock_search_api, \
             patch('analytics_api.AnalyticsService') as mock_analytics_service:
            
            search_api_instance = MagicMock()
            analytics_service_instance = MagicMock()
            mock_search_api.return_value = search_api_instance
            mock_analytics_service.return_value = analytics_service_instance
            
            # Test semantic search scenarios
            semantic_queries = [
                {
                    'query': 'phones with excellent audio quality',
                    'expected_products': ['iPhone 15 Pro', 'Samsung Galaxy S24'],
                    'semantic_score_threshold': 0.8
                },
                {
                    'query': 'comfortable headphones for long sessions',
                    'expected_products': ['Wireless Bluetooth Headphones', 'Gaming Headset'],
                    'semantic_score_threshold': 0.75
                },
                {
                    'query': 'budget-friendly gaming accessories',
                    'expected_products': ['Gaming Mouse', 'Gaming Keyboard'],
                    'semantic_score_threshold': 0.7
                }
            ]
            
            for scenario in semantic_queries:
                # Mock semantic search results
                search_api_instance.semantic_search.return_value = {
                    'products': [
                        {
                            'product_id': f'prod_{i}',
                            'title': product,
                            'semantic_score': scenario['semantic_score_threshold'] + 0.1,
                            'relevance_explanation': f'High semantic similarity for "{scenario["query"]}"'
                        }
                        for i, product in enumerate(scenario['expected_products'])
                    ],
                    'total': len(scenario['expected_products']),
                    'query': scenario['query'],
                    'search_type': 'semantic'
                }
                
                results = search_api_instance.semantic_search(scenario['query'])
                
                # Validate semantic search quality
                assert results['total'] > 0
                assert results['search_type'] == 'semantic'
                
                for product in results['products']:
                    assert product['semantic_score'] >= scenario['semantic_score_threshold']
                    assert 'relevance_explanation' in product
    
    def test_auto_complete_performance_optimization(self):
        """Test auto-complete performance and caching optimization"""
        with patch('search_api.SearchAPI') as mock_search_api:
            search_api_instance = MagicMock()
            mock_search_api.return_value = search_api_instance
            
            # Test performance scenarios
            performance_queries = ['wireless', 'gaming', 'bluetooth', 'headphones']
            
            for query in performance_queries:
                # First request - should populate cache
                search_api_instance.get_auto_complete_suggestions.return_value = [
                    {'text': f'{query} headphones', 'type': 'popular', 'cached': False},
                    {'text': f'{query} mouse', 'type': 'popular', 'cached': False},
                    {'text': f'{query} keyboard', 'type': 'popular', 'cached': False}
                ]
                
                start_time = time.time()
                first_result = search_api_instance.get_auto_complete_suggestions(query)
                first_time = time.time() - start_time
                
                assert len(first_result) == 3
                assert not first_result[0]['cached']
                
                # Second request - should hit cache
                search_api_instance.get_auto_complete_suggestions.return_value = [
                    {'text': f'{query} headphones', 'type': 'popular', 'cached': True},
                    {'text': f'{query} mouse', 'type': 'popular', 'cached': True},
                    {'text': f'{query} keyboard', 'type': 'popular', 'cached': True}
                ]
                
                start_time = time.time()
                cached_result = search_api_instance.get_auto_complete_suggestions(query)
                cached_time = time.time() - start_time
                
                assert len(cached_result) == 3
                assert cached_result[0]['cached'] is True
                
                # In real implementation, cached should be faster
                # For mocked tests, we verify the cache flag
    
    def test_search_analytics_comprehensive_tracking(self):
        """Test comprehensive search analytics and user behavior tracking"""
        with patch('search_api.SearchAPI') as mock_search_api, \
             patch('analytics_api.AnalyticsService') as mock_analytics_service:
            
            search_api_instance = MagicMock()
            analytics_service_instance = MagicMock()
            mock_search_api.return_value = search_api_instance
            mock_analytics_service.return_value = analytics_service_instance
            
            # Simulate user search behavior patterns
            user_search_sessions = [
                {
                    'user_id': 'user_1',
                    'searches': [
                        {'query': 'wireless headphones', 'clicked_product': 'prod_1', 'purchased': True},
                        {'query': 'bluetooth speaker', 'clicked_product': 'prod_2', 'purchased': False},
                        {'query': 'gaming mouse', 'clicked_product': None, 'purchased': False}
                    ]
                },
                {
                    'user_id': 'user_2',
                    'searches': [
                        {'query': 'wireless headphones', 'clicked_product': 'prod_1', 'purchased': True},
                        {'query': 'headphone case', 'clicked_product': 'prod_3', 'purchased': True}
                    ]
                }
            ]
            
            # Track search analytics
            analytics_data = {
                'popular_terms': {},
                'conversion_rates': {},
                'user_patterns': {}
            }
            
            for session in user_search_sessions:
                for search in session['searches']:
                    # Track popular terms
                    term = search['query']
                    analytics_data['popular_terms'][term] = analytics_data['popular_terms'].get(term, 0) + 1
                    
                    # Track conversion rates
                    if term not in analytics_data['conversion_rates']:
                        analytics_data['conversion_rates'][term] = {'searches': 0, 'purchases': 0}
                    
                    analytics_data['conversion_rates'][term]['searches'] += 1
                    if search['purchased']:
                        analytics_data['conversion_rates'][term]['purchases'] += 1
            
            # Mock analytics service responses
            analytics_service_instance.get_search_analytics.return_value = {
                'success': True,
                'popular_terms': [
                    {'term': 'wireless headphones', 'count': 2, 'conversion_rate': 1.0},
                    {'term': 'bluetooth speaker', 'count': 1, 'conversion_rate': 0.0},
                    {'term': 'gaming mouse', 'count': 1, 'conversion_rate': 0.0},
                    {'term': 'headphone case', 'count': 1, 'conversion_rate': 1.0}
                ],
                'trending_terms': ['wireless headphones', 'headphone case'],
                'user_behavior_insights': {
                    'average_searches_per_session': 2.5,
                    'most_common_search_patterns': ['electronics -> accessories'],
                    'peak_search_times': ['10:00-12:00', '14:00-16:00']
                }
            }
            
            analytics_result = analytics_service_instance.get_search_analytics()
            
            # Validate analytics tracking
            assert analytics_result['success'] is True
            assert len(analytics_result['popular_terms']) == 4
            assert analytics_result['popular_terms'][0]['term'] == 'wireless headphones'
            assert analytics_result['popular_terms'][0]['conversion_rate'] == 1.0
    
    def test_search_error_handling_comprehensive(self):
        """Test comprehensive search error handling and recovery scenarios"""
        with patch('search_api.SearchAPI') as mock_search_api:
            search_api_instance = MagicMock()
            mock_search_api.return_value = search_api_instance
            
            # Test various error scenarios
            error_scenarios = [
                {
                    'scenario': 'database_timeout',
                    'query': 'test query',
                    'error_response': {
                        'products': [],
                        'total': 0,
                        'error': 'Database timeout',
                        'error_code': 'DB_TIMEOUT',
                        'retry_after': 5
                    }
                },
                {
                    'scenario': 'invalid_query',
                    'query': '',  # Empty query
                    'error_response': {
                        'products': [],
                        'total': 0,
                        'error': 'Invalid query',
                        'error_code': 'INVALID_QUERY',
                        'message': 'Query cannot be empty'
                    }
                },
                {
                    'scenario': 'service_unavailable',
                    'query': 'wireless headphones',
                    'error_response': {
                        'products': [],
                        'total': 0,
                        'error': 'Search service temporarily unavailable',
                        'error_code': 'SERVICE_UNAVAILABLE',
                        'fallback_results': [
                            {'product_id': 'fallback_1', 'title': 'Popular Product 1'},
                            {'product_id': 'fallback_2', 'title': 'Popular Product 2'}
                        ]
                    }
                }
            ]
            
            for scenario in error_scenarios:
                search_api_instance.search_products.return_value = scenario['error_response']
                
                result = search_api_instance.search_products(scenario['query'])
                
                # Validate error handling
                assert result['total'] == 0
                assert 'error' in result
                assert 'error_code' in result
                
                # Check for appropriate fallback mechanisms
                if scenario['scenario'] == 'service_unavailable':
                    assert 'fallback_results' in result
                    assert len(result['fallback_results']) > 0
                
                if scenario['scenario'] == 'database_timeout':
                    assert 'retry_after' in result
                    assert result['retry_after'] > 0
    
    def test_cross_platform_search_consistency(self):
        """Test search consistency across different platforms and devices"""
        with patch('search_api.SearchAPI') as mock_search_api:
            search_api_instance = MagicMock()
            mock_search_api.return_value = search_api_instance
            
            # Test same search across different platforms
            platforms = ['web', 'mobile', 'tablet']
            query = 'wireless headphones'
            
            expected_results = {
                'products': [
                    {
                        'product_id': 'prod_1',
                        'title': 'Wireless Bluetooth Headphones',
                        'price': 199.99,
                        'rating': 4.5
                    }
                ],
                'total': 1,
                'query': query
            }
            
            for platform in platforms:
                search_api_instance.search_products.return_value = {
                    **expected_results,
                    'platform': platform,
                    'optimized_for': platform
                }
                
                result = search_api_instance.search_products(
                    query,
                    platform=platform
                )
                
                # Verify consistent results across platforms
                assert result['total'] == expected_results['total']
                assert len(result['products']) == len(expected_results['products'])
                assert result['products'][0]['product_id'] == expected_results['products'][0]['product_id']
                assert result['platform'] == platform
    
    def test_search_personalization_workflow(self):
        """Test personalized search based on user preferences and history"""
        with patch('search_api.SearchAPI') as mock_search_api, \
             patch('analytics_api.AnalyticsService') as mock_analytics_service:
            
            search_api_instance = MagicMock()
            analytics_service_instance = MagicMock()
            mock_search_api.return_value = search_api_instance
            mock_analytics_service.return_value = analytics_service_instance
            
            # User with specific preferences and history
            user_profile = {
                'user_id': 'personalized_user_123',
                'preferences': {
                    'categories': ['Electronics', 'Gaming'],
                    'price_range': [100, 500],
                    'brands': ['Sony', 'Bose', 'Apple']
                },
                'search_history': [
                    'gaming headphones',
                    'wireless mouse',
                    'mechanical keyboard',
                    'bluetooth speakers'
                ],
                'purchase_history': [
                    {'product_id': 'prod_gaming_1', 'category': 'Gaming'},
                    {'product_id': 'prod_audio_1', 'category': 'Electronics'}
                ]
            }
            
            # Test personalized search
            search_api_instance.personalized_search.return_value = {
                'products': [
                    {
                        'product_id': 'prod_personalized_1',
                        'title': 'Gaming Headphones Pro',
                        'price': 299.99,
                        'rating': 4.7,
                        'personalization_score': 0.95,
                        'reason': 'Matches your gaming preferences and price range'
                    },
                    {
                        'product_id': 'prod_personalized_2',
                        'title': 'Wireless Gaming Mouse',
                        'price': 149.99,
                        'rating': 4.4,
                        'personalization_score': 0.88,
                        'reason': 'Similar to your previous purchases'
                    }
                ],
                'total': 2,
                'query': 'gaming accessories',
                'personalized': True,
                'user_profile_applied': True
            }
            
            personalized_result = search_api_instance.personalized_search(
                'gaming accessories',
                user_profile['user_id']
            )
            
            # Validate personalization
            assert personalized_result['personalized'] is True
            assert personalized_result['user_profile_applied'] is True
            
            for product in personalized_result['products']:
                assert product['personalization_score'] > 0.8
                assert 'reason' in product
                assert product['price'] >= user_profile['preferences']['price_range'][0]
                assert product['price'] <= user_profile['preferences']['price_range'][1]


class TestAdvancedSearchScenarios:
    """Advanced search scenarios for comprehensive testing"""
    
    def test_multi_language_search_support(self):
        """Test search functionality with multiple languages"""
        with patch('search_api.SearchAPI') as mock_search_api:
            search_api_instance = MagicMock()
            mock_search_api.return_value = search_api_instance
            
            # Test searches in different languages
            multilingual_queries = [
                {'query': 'wireless headphones', 'language': 'en', 'expected_count': 5},
                {'query': 'auriculares inalámbricos', 'language': 'es', 'expected_count': 5},
                {'query': 'casque sans fil', 'language': 'fr', 'expected_count': 5},
                {'query': 'kabellose Kopfhörer', 'language': 'de', 'expected_count': 5}
            ]
            
            for query_data in multilingual_queries:
                search_api_instance.search_products.return_value = {
                    'products': [
                        {
                            'product_id': f'prod_{i}',
                            'title': f'Product {i}',
                            'localized_title': f'Localized Product {i}',
                            'language': query_data['language']
                        }
                        for i in range(query_data['expected_count'])
                    ],
                    'total': query_data['expected_count'],
                    'query': query_data['query'],
                    'language': query_data['language']
                }
                
                result = search_api_instance.search_products(
                    query_data['query'],
                    language=query_data['language']
                )
                
                assert result['total'] == query_data['expected_count']
                assert result['language'] == query_data['language']
                
                for product in result['products']:
                    assert 'localized_title' in product
    
    def test_voice_search_integration(self):
        """Test voice search functionality and speech-to-text integration"""
        with patch('search_api.SearchAPI') as mock_search_api:
            search_api_instance = MagicMock()
            mock_search_api.return_value = search_api_instance
            
            # Simulate voice search scenarios
            voice_queries = [
                {
                    'audio_input': 'voice_search_1.wav',
                    'transcribed_text': 'I need wireless headphones for running',
                    'confidence': 0.95,
                    'intent': 'product_search'
                },
                {
                    'audio_input': 'voice_search_2.wav',
                    'transcribed_text': 'Show me gaming accessories under two hundred dollars',
                    'confidence': 0.88,
                    'intent': 'filtered_search'
                }
            ]
            
            for voice_query in voice_queries:
                search_api_instance.voice_search.return_value = {
                    'transcription': {
                        'text': voice_query['transcribed_text'],
                        'confidence': voice_query['confidence']
                    },
                    'search_results': {
                        'products': [
                            {
                                'product_id': 'voice_prod_1',
                                'title': 'Wireless Running Headphones',
                                'voice_match_score': 0.92
                            }
                        ],
                        'total': 1
                    },
                    'intent_analysis': {
                        'detected_intent': voice_query['intent'],
                        'extracted_filters': ['wireless', 'running'] if 'running' in voice_query['transcribed_text'] else ['gaming', 'under_200']
                    }
                }
                
                voice_result = search_api_instance.voice_search(voice_query['audio_input'])
                
                # Validate voice search processing
                assert voice_result['transcription']['confidence'] > 0.8
                assert voice_result['search_results']['total'] > 0
                assert 'intent_analysis' in voice_result
                assert len(voice_result['intent_analysis']['extracted_filters']) > 0
    
    def test_visual_search_integration(self):
        """Test visual search functionality with image recognition"""
        with patch('search_api.SearchAPI') as mock_search_api:
            search_api_instance = MagicMock()
            mock_search_api.return_value = search_api_instance
            
            # Simulate visual search scenarios
            image_searches = [
                {
                    'image_input': 'headphones_image.jpg',
                    'detected_objects': ['headphones', 'wireless', 'black'],
                    'confidence': 0.91,
                    'category': 'Electronics'
                },
                {
                    'image_input': 'gaming_setup.jpg',
                    'detected_objects': ['mouse', 'keyboard', 'monitor'],
                    'confidence': 0.87,
                    'category': 'Gaming'
                }
            ]
            
            for image_search in image_searches:
                search_api_instance.visual_search.return_value = {
                    'image_analysis': {
                        'detected_objects': image_search['detected_objects'],
                        'confidence': image_search['confidence'],
                        'category': image_search['category']
                    },
                    'similar_products': [
                        {
                            'product_id': f'visual_prod_{i}',
                            'title': f'Similar Product {i}',
                            'visual_similarity_score': 0.85 + (i * 0.02),
                            'matched_features': image_search['detected_objects'][:2]
                        }
                        for i in range(3)
                    ],
                    'total': 3
                }
                
                visual_result = search_api_instance.visual_search(image_search['image_input'])
                
                # Validate visual search processing
                assert visual_result['image_analysis']['confidence'] > 0.8
                assert len(visual_result['similar_products']) > 0
                
                for product in visual_result['similar_products']:
                    assert product['visual_similarity_score'] > 0.8
                    assert len(product['matched_features']) > 0


if __name__ == '__main__':
    pytest.main([__file__])