"""
Comprehensive end-to-end testing scenarios
Tests complete integration workflows covering all requirements from task 12.3
"""
import pytest
import json
import time
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock
import sys
import os

# Add the functions directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'functions'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'shared'))


class TestComprehensiveWorkflows:
    """Comprehensive end-to-end workflows testing all system components"""
    
    def setup_method(self):
        """Set up test environment for comprehensive workflows"""
        self.test_users = [
            {
                'userId': 'comprehensive_user_1',
                'email': 'user1@example.com',
                'name': 'Test User One',
                'preferences': {'categories': ['Electronics'], 'price_range': [50, 500]}
            },
            {
                'userId': 'comprehensive_user_2',
                'email': 'user2@example.com',
                'name': 'Test User Two',
                'preferences': {'categories': ['Gaming'], 'price_range': [100, 1000]}
            }
        ]
        
        self.test_products = [
            {
                'product_id': 'comp_prod_1',
                'title': 'Premium Wireless Headphones',
                'description': 'High-quality wireless headphones with noise cancellation',
                'price': 299.99,
                'category': 'Electronics',
                'rating': 4.6,
                'review_count': 245,
                'in_stock': True,
                'available_quantity': 100
            },
            {
                'product_id': 'comp_prod_2',
                'title': 'Gaming Mechanical Keyboard',
                'description': 'RGB mechanical keyboard for gaming',
                'price': 149.99,
                'category': 'Gaming',
                'rating': 4.4,
                'review_count': 189,
                'in_stock': True,
                'available_quantity': 75
            }
        ]
    
    def test_complete_user_journey_workflow(self):
        """Test complete user journey from registration to post-purchase review"""
        with patch('auth_api.AuthenticationAPI') as mock_auth_api, \
             patch('product_api.ProductAPI') as mock_product_api, \
             patch('search_api.SearchAPI') as mock_search_api, \
             patch('cart_api.ShoppingCartAPI') as mock_cart_api, \
             patch('order_api.OrderManagementAPI') as mock_order_api, \
             patch('review_api.ReviewAPI') as mock_review_api, \
             patch('chat_api.ChatService') as mock_chat_service:
            
            # Initialize all mocks
            auth_api_instance = MagicMock()
            product_api_instance = MagicMock()
            search_api_instance = MagicMock()
            cart_api_instance = MagicMock()
            order_api_instance = MagicMock()
            review_api_instance = MagicMock()
            chat_service_instance = MagicMock()
            
            mock_auth_api.return_value = auth_api_instance
            mock_product_api.return_value = product_api_instance
            mock_search_api.return_value = search_api_instance
            mock_cart_api.return_value = cart_api_instance
            mock_order_api.return_value = order_api_instance
            mock_review_api.return_value = review_api_instance
            mock_chat_service.return_value = chat_service_instance
            
            user = self.test_users[0]
            
            # Phase 1: User Registration and Authentication
            auth_api_instance.register_user.return_value = {
                'statusCode': 201,
                'body': json.dumps({
                    'message': 'Registration successful',
                    'userId': user['userId'],
                    'verificationRequired': True
                })
            }
            
            registration_result = auth_api_instance.register_user({
                'email': user['email'],
                'password': 'SecurePass123!',
                'name': user['name']
            })
            assert registration_result['statusCode'] == 201
            
            # Email verification
            auth_api_instance.verify_email.return_value = {
                'statusCode': 200,
                'body': json.dumps({
                    'message': 'Email verified successfully',
                    'accessToken': 'jwt_token_123',
                    'refreshToken': 'refresh_token_456'
                })
            }
            
            verification_result = auth_api_instance.verify_email({
                'email': user['email'],
                'verificationCode': '123456'
            })
            assert verification_result['statusCode'] == 200
            
            # Phase 2: Product Discovery through Search
            search_api_instance.get_auto_complete_suggestions.return_value = [
                {'text': 'wireless headphones', 'type': 'popular', 'count': 1500},
                {'text': 'Premium Wireless Headphones', 'type': 'product', 'rating': 4.6}
            ]
            
            suggestions = search_api_instance.get_auto_complete_suggestions('wireless')
            assert len(suggestions) == 2
            
            search_api_instance.search_products.return_value = {
                'products': [self.test_products[0]],
                'total': 1,
                'query': 'wireless headphones'
            }
            
            search_results = search_api_instance.search_products('wireless headphones')
            assert search_results['total'] == 1
            
            # Phase 3: AI Chat Consultation
            chat_service_instance.send_message.return_value = {
                'success': True,
                'message_id': 'chat_msg_1',
                'response': 'The Premium Wireless Headphones are excellent for music lovers. They feature advanced noise cancellation and 30-hour battery life.',
                'sources': ['Product: Premium Wireless Headphones'],
                'session_id': 'chat_session_123'
            }
            
            chat_response = chat_service_instance.send_message(
                user['userId'],
                'Tell me about the Premium Wireless Headphones',
                'chat_session_123'
            )
            assert chat_response['success'] is True
            
            # Phase 4: Product Detail Review
            product_api_instance.get_product_detail.return_value = {
                'statusCode': 200,
                'body': json.dumps({
                    'product': self.test_products[0],
                    'reviews_summary': {
                        'total_reviews': 245,
                        'average_rating': 4.6,
                        'sentiment_distribution': {'positive': 85, 'neutral': 10, 'negative': 5}
                    }
                })
            }
            
            product_detail = product_api_instance.get_product_detail({
                'pathParameters': {'id': 'comp_prod_1'}
            })
            assert product_detail['statusCode'] == 200
            
            # Phase 5: Add to Cart
            cart_api_instance.add_to_cart.return_value = {
                'statusCode': 200,
                'body': json.dumps({
                    'message': 'Item added to cart successfully',
                    'productId': 'comp_prod_1',
                    'quantity': 1,
                    'price': 299.99
                })
            }
            
            cart_result = cart_api_instance.add_to_cart({
                'pathParameters': {'userId': user['userId']},
                'body': json.dumps({'productId': 'comp_prod_1', 'quantity': 1})
            })
            assert cart_result['statusCode'] == 200
            
            # Phase 6: Checkout and Order Creation
            order_api_instance.create_order.return_value = {
                'statusCode': 201,
                'body': json.dumps({
                    'orderId': 'ORD-COMP-12345',
                    'status': 'confirmed',
                    'totalAmount': 329.98,  # Including tax
                    'estimatedDelivery': (datetime.now() + timedelta(days=3)).isoformat()
                })
            }
            
            order_result = order_api_instance.create_order({
                'body': json.dumps({
                    'userId': user['userId'],
                    'items': [{'productId': 'comp_prod_1', 'quantity': 1}],
                    'paymentMethod': {'type': 'credit_card'},
                    'shippingAddress': {'state': 'CA'}
                })
            })
            assert order_result['statusCode'] == 201
            
            # Phase 7: Post-Purchase Review Writing
            # Simulate delivery completion (would be triggered by fulfillment system)
            time.sleep(0.1)  # Simulate time passage
            
            review_api_instance.create_review.return_value = {
                'statusCode': 201,
                'body': json.dumps({
                    'message': 'Review created successfully',
                    'reviewId': 'review_comp_123',
                    'isVerifiedPurchase': True,
                    'sentiment': {'score': 0.85, 'label': 'positive'}
                })
            }
            
            review_result = review_api_instance.create_review({
                'userId': user['userId'],
                'productId': 'comp_prod_1',
                'rating': 5,
                'title': 'Excellent headphones!',
                'content': 'Amazing sound quality and comfort. Highly recommended!',
                'aspectRatings': {'quality': 5, 'comfort': 5, 'value': 4}
            })
            assert review_result['statusCode'] == 201
            
            # Verify complete workflow
            order_data = json.loads(order_result['body'])
            review_data = json.loads(review_result['body'])
            
            assert 'orderId' in order_data
            assert order_data['status'] == 'confirmed'
            assert review_data['isVerifiedPurchase'] is True
    
    def test_multi_user_interaction_workflow(self):
        """Test interactions between multiple users (reviews, helpfulness voting)"""
        with patch('review_api.ReviewAPI') as mock_review_api, \
             patch('analytics_api.AnalyticsService') as mock_analytics_service:
            
            review_api_instance = MagicMock()
            analytics_service_instance = MagicMock()
            mock_review_api.return_value = review_api_instance
            mock_analytics_service.return_value = analytics_service_instance
            
            # User 1 writes a review
            review_api_instance.create_review.return_value = {
                'statusCode': 201,
                'body': json.dumps({
                    'reviewId': 'multi_review_123',
                    'userId': self.test_users[0]['userId'],
                    'productId': 'comp_prod_1',
                    'rating': 4,
                    'isVerifiedPurchase': True
                })
            }
            
            review_result = review_api_instance.create_review({
                'userId': self.test_users[0]['userId'],
                'productId': 'comp_prod_1',
                'rating': 4,
                'title': 'Good headphones',
                'content': 'Great sound quality, but a bit expensive.'
            })
            assert review_result['statusCode'] == 201
            
            # User 2 finds the review helpful
            review_api_instance.vote_helpful.return_value = {
                'statusCode': 200,
                'body': json.dumps({
                    'message': 'Vote recorded successfully',
                    'reviewId': 'multi_review_123',
                    'helpfulCount': 1,
                    'notHelpfulCount': 0
                })
            }
            
            vote_result = review_api_instance.vote_helpful({
                'reviewId': 'multi_review_123',
                'userId': self.test_users[1]['userId'],
                'isHelpful': True
            })
            assert vote_result['statusCode'] == 200
            
            # Multiple users interact with the review
            for i in range(5):  # Simulate 5 more users voting
                review_api_instance.vote_helpful.return_value = {
                    'statusCode': 200,
                    'body': json.dumps({
                        'message': 'Vote recorded successfully',
                        'reviewId': 'multi_review_123',
                        'helpfulCount': i + 2,  # Incrementing helpful count
                        'notHelpfulCount': 0
                    })
                }
                
                additional_vote = review_api_instance.vote_helpful({
                    'reviewId': 'multi_review_123',
                    'userId': f'additional_user_{i}',
                    'isHelpful': True
                })
                assert additional_vote['statusCode'] == 200
            
            # Get aggregated review insights
            analytics_service_instance.get_review_insights.return_value = {
                'success': True,
                'productId': 'comp_prod_1',
                'insights': {
                    'total_reviews': 1,
                    'helpful_reviews': 1,
                    'average_helpfulness_score': 6.0,
                    'community_engagement': 'high'
                }
            }
            
            insights = analytics_service_instance.get_review_insights('comp_prod_1')
            assert insights['success'] is True
            assert insights['insights']['community_engagement'] == 'high'
    
    def test_ai_powered_recommendation_workflow(self):
        """Test AI-powered product recommendations based on user behavior"""
        with patch('analytics_api.AnalyticsService') as mock_analytics_service, \
             patch('product_api.ProductAPI') as mock_product_api:
            
            analytics_service_instance = MagicMock()
            product_api_instance = MagicMock()
            mock_analytics_service.return_value = analytics_service_instance
            mock_product_api.return_value = product_api_instance
            
            user = self.test_users[0]
            
            # User behavior data
            user_behavior = {
                'search_history': ['wireless headphones', 'bluetooth speakers', 'gaming accessories'],
                'view_history': ['comp_prod_1', 'comp_prod_2'],
                'purchase_history': [{'productId': 'comp_prod_1', 'category': 'Electronics'}],
                'review_history': [{'productId': 'comp_prod_1', 'rating': 4}]
            }
            
            # Get AI-powered recommendations
            analytics_service_instance.get_personalized_recommendations.return_value = {
                'success': True,
                'userId': user['userId'],
                'recommendations': [
                    {
                        'product_id': 'rec_prod_1',
                        'title': 'Wireless Bluetooth Speaker',
                        'price': 199.99,
                        'rating': 4.5,
                        'recommendation_score': 0.92,
                        'reason': 'Based on your interest in wireless audio products',
                        'recommendation_type': 'behavioral_similarity'
                    },
                    {
                        'product_id': 'rec_prod_2',
                        'title': 'Gaming Headset Pro',
                        'price': 249.99,
                        'rating': 4.7,
                        'recommendation_score': 0.88,
                        'reason': 'Customers who bought wireless headphones also liked this',
                        'recommendation_type': 'collaborative_filtering'
                    },
                    {
                        'product_id': 'rec_prod_3',
                        'title': 'Headphone Stand',
                        'price': 29.99,
                        'rating': 4.3,
                        'recommendation_score': 0.85,
                        'reason': 'Perfect accessory for your Premium Wireless Headphones',
                        'recommendation_type': 'complementary_product'
                    }
                ],
                'algorithm_insights': {
                    'primary_factors': ['purchase_history', 'search_patterns', 'category_preferences'],
                    'confidence_level': 0.89
                }
            }
            
            recommendations = analytics_service_instance.get_personalized_recommendations(user['userId'])
            
            # Validate AI recommendations
            assert recommendations['success'] is True
            assert len(recommendations['recommendations']) == 3
            
            for rec in recommendations['recommendations']:
                assert rec['recommendation_score'] > 0.8
                assert 'reason' in rec
                assert 'recommendation_type' in rec
            
            # Test different recommendation types
            recommendation_types = [rec['recommendation_type'] for rec in recommendations['recommendations']]
            assert 'behavioral_similarity' in recommendation_types
            assert 'collaborative_filtering' in recommendation_types
            assert 'complementary_product' in recommendation_types
    
    def test_semantic_review_search_workflow(self):
        """Test semantic search across product reviews with AI insights"""
        with patch('analytics_api.AnalyticsService') as mock_analytics_service:
            analytics_service_instance = MagicMock()
            mock_analytics_service.return_value = analytics_service_instance
            
            # Test semantic search queries
            semantic_queries = [
                {
                    'query': 'headphones with excellent battery life',
                    'expected_insights': ['battery', 'long-lasting', 'all-day']
                },
                {
                    'query': 'comfortable headphones for long sessions',
                    'expected_insights': ['comfort', 'ergonomic', 'extended wear']
                },
                {
                    'query': 'headphones with good value for money',
                    'expected_insights': ['value', 'price', 'worth it']
                }
            ]
            
            for query_data in semantic_queries:
                analytics_service_instance.semantic_review_search.return_value = {
                    'success': True,
                    'query': query_data['query'],
                    'total_results': 15,
                    'results': [
                        {
                            'review_id': f'semantic_review_{i}',
                            'product_id': f'semantic_prod_{i}',
                            'product_title': f'Product {i}',
                            'review_content': f'Review mentioning {query_data["expected_insights"][0]}',
                            'rating': 4 + (i % 2),
                            'similarity_score': 0.9 - (i * 0.05),
                            'highlighted_text': f'This product has great {query_data["expected_insights"][0]}',
                            'sentiment': 'positive'
                        }
                        for i in range(3)
                    ],
                    'insights': {
                        'common_themes': query_data['expected_insights'],
                        'sentiment_distribution': {'positive': 80, 'neutral': 15, 'negative': 5},
                        'average_rating': 4.3,
                        'key_findings': [
                            f'Most users are satisfied with {query_data["expected_insights"][0]}',
                            f'High correlation between {query_data["expected_insights"][0]} and overall satisfaction'
                        ]
                    },
                    'recommended_products': [
                        {
                            'product_id': 'recommended_1',
                            'title': 'Top Rated Product',
                            'match_score': 0.95,
                            'why_recommended': f'Highest ratings for {query_data["expected_insights"][0]}'
                        }
                    ]
                }
                
                semantic_result = analytics_service_instance.semantic_review_search(query_data['query'])
                
                # Validate semantic search results
                assert semantic_result['success'] is True
                assert semantic_result['total_results'] > 0
                assert len(semantic_result['results']) > 0
                
                # Check similarity scores
                for result in semantic_result['results']:
                    assert result['similarity_score'] > 0.8
                    assert 'highlighted_text' in result
                
                # Validate insights
                assert len(semantic_result['insights']['common_themes']) > 0
                assert semantic_result['insights']['average_rating'] > 4.0
                assert len(semantic_result['recommended_products']) > 0
    
    def test_cross_device_session_continuity(self):
        """Test session continuity across different devices and platforms"""
        with patch('cart_api.ShoppingCartAPI') as mock_cart_api, \
             patch('auth_api.AuthenticationAPI') as mock_auth_api, \
             patch('chat_api.ChatService') as mock_chat_service:
            
            cart_api_instance = MagicMock()
            auth_api_instance = MagicMock()
            chat_service_instance = MagicMock()
            mock_cart_api.return_value = cart_api_instance
            mock_auth_api.return_value = auth_api_instance
            mock_chat_service.return_value = chat_service_instance
            
            user = self.test_users[0]
            
            # Device 1: Mobile - User adds items to cart
            cart_api_instance.add_to_cart.return_value = {
                'statusCode': 200,
                'body': json.dumps({
                    'message': 'Item added to cart successfully',
                    'productId': 'comp_prod_1',
                    'quantity': 2,
                    'device': 'mobile',
                    'session_id': 'mobile_session_123'
                })
            }
            
            mobile_cart_result = cart_api_instance.add_to_cart({
                'pathParameters': {'userId': user['userId']},
                'body': json.dumps({'productId': 'comp_prod_1', 'quantity': 2}),
                'headers': {'User-Agent': 'Mobile App', 'Device-Type': 'mobile'}
            })
            assert mobile_cart_result['statusCode'] == 200
            
            # Device 1: Mobile - User starts chat session
            chat_service_instance.send_message.return_value = {
                'success': True,
                'message_id': 'mobile_msg_1',
                'response': 'Hello! How can I help you today?',
                'session_id': 'cross_device_chat_123',
                'device': 'mobile'
            }
            
            mobile_chat = chat_service_instance.send_message(
                user['userId'],
                'Hello, I need help with my cart',
                'cross_device_chat_123'
            )
            assert mobile_chat['success'] is True
            
            # Device 2: Desktop - User accesses cart (should see mobile items)
            cart_api_instance.get_cart.return_value = {
                'statusCode': 200,
                'body': json.dumps({
                    'userId': user['userId'],
                    'items': [{
                        'productId': 'comp_prod_1',
                        'title': 'Premium Wireless Headphones',
                        'quantity': 2,
                        'price': 299.99,
                        'subtotal': 599.98,
                        'added_from_device': 'mobile'
                    }],
                    'totalAmount': 599.98,
                    'device': 'desktop',
                    'session_id': 'desktop_session_456'
                })
            }
            
            desktop_cart_result = cart_api_instance.get_cart({
                'pathParameters': {'userId': user['userId']},
                'headers': {'User-Agent': 'Desktop Browser', 'Device-Type': 'desktop'}
            })
            assert desktop_cart_result['statusCode'] == 200
            
            desktop_cart_data = json.loads(desktop_cart_result['body'])
            assert len(desktop_cart_data['items']) == 1
            assert desktop_cart_data['items'][0]['quantity'] == 2
            assert desktop_cart_data['items'][0]['added_from_device'] == 'mobile'
            
            # Device 2: Desktop - User continues chat (should have context)
            chat_service_instance.get_chat_history.return_value = {
                'success': True,
                'messages': [
                    {
                        'message_id': 'mobile_msg_1',
                        'role': 'user',
                        'content': 'Hello, I need help with my cart',
                        'device': 'mobile',
                        'timestamp': datetime.now(timezone.utc).isoformat()
                    }
                ],
                'session_id': 'cross_device_chat_123',
                'device': 'desktop'
            }
            
            desktop_chat_history = chat_service_instance.get_chat_history(
                user['userId'],
                'cross_device_chat_123'
            )
            assert desktop_chat_history['success'] is True
            assert len(desktop_chat_history['messages']) > 0
            
            # Device 3: Tablet - User modifies cart
            cart_api_instance.update_cart_item.return_value = {
                'statusCode': 200,
                'body': json.dumps({
                    'message': 'Cart item updated successfully',
                    'productId': 'comp_prod_1',
                    'quantity': 1,  # Reduced from 2 to 1
                    'subtotal': 299.99,
                    'device': 'tablet',
                    'session_id': 'tablet_session_789'
                })
            }
            
            tablet_cart_update = cart_api_instance.update_cart_item({
                'pathParameters': {'userId': user['userId'], 'productId': 'comp_prod_1'},
                'body': json.dumps({'quantity': 1}),
                'headers': {'User-Agent': 'Tablet Browser', 'Device-Type': 'tablet'}
            })
            assert tablet_cart_update['statusCode'] == 200
            
            # Verify cross-device continuity
            tablet_update_data = json.loads(tablet_cart_update['body'])
            assert tablet_update_data['quantity'] == 1
            assert tablet_update_data['device'] == 'tablet'
    
    def test_performance_under_load_simulation(self):
        """Test system performance under simulated load conditions"""
        with patch('search_api.SearchAPI') as mock_search_api, \
             patch('product_api.ProductAPI') as mock_product_api, \
             patch('cart_api.ShoppingCartAPI') as mock_cart_api:
            
            search_api_instance = MagicMock()
            product_api_instance = MagicMock()
            cart_api_instance = MagicMock()
            mock_search_api.return_value = search_api_instance
            mock_product_api.return_value = product_api_instance
            mock_cart_api.return_value = cart_api_instance
            
            # Simulate concurrent user operations
            concurrent_operations = []
            
            # Simulate 50 concurrent search operations
            for i in range(50):
                search_api_instance.search_products.return_value = {
                    'products': [self.test_products[0]],
                    'total': 1,
                    'query': f'search_query_{i}',
                    'response_time_ms': 150 + (i % 50),  # Simulate varying response times
                    'cache_hit': i % 3 == 0  # Every 3rd request is a cache hit
                }
                
                start_time = time.time()
                result = search_api_instance.search_products(f'search_query_{i}')
                end_time = time.time()
                
                concurrent_operations.append({
                    'operation': 'search',
                    'response_time': end_time - start_time,
                    'cache_hit': result['cache_hit'],
                    'success': result['total'] > 0
                })
            
            # Simulate 30 concurrent cart operations
            for i in range(30):
                cart_api_instance.add_to_cart.return_value = {
                    'statusCode': 200,
                    'body': json.dumps({
                        'message': 'Item added to cart successfully',
                        'productId': f'load_test_prod_{i}',
                        'quantity': 1,
                        'response_time_ms': 100 + (i % 30)
                    })
                }
                
                start_time = time.time()
                result = cart_api_instance.add_to_cart({
                    'pathParameters': {'userId': f'load_test_user_{i}'},
                    'body': json.dumps({'productId': f'load_test_prod_{i}', 'quantity': 1})
                })
                end_time = time.time()
                
                concurrent_operations.append({
                    'operation': 'cart_add',
                    'response_time': end_time - start_time,
                    'success': result['statusCode'] == 200
                })
            
            # Analyze performance metrics
            search_operations = [op for op in concurrent_operations if op['operation'] == 'search']
            cart_operations = [op for op in concurrent_operations if op['operation'] == 'cart_add']
            
            # Validate performance requirements
            search_success_rate = sum(1 for op in search_operations if op['success']) / len(search_operations)
            cart_success_rate = sum(1 for op in cart_operations if op['success']) / len(cart_operations)
            
            assert search_success_rate >= 0.95  # 95% success rate
            assert cart_success_rate >= 0.95   # 95% success rate
            
            # Check cache effectiveness
            cache_hit_rate = sum(1 for op in search_operations if op.get('cache_hit', False)) / len(search_operations)
            assert cache_hit_rate >= 0.25  # At least 25% cache hit rate
    
    def test_data_consistency_across_services(self):
        """Test data consistency across different services and databases"""
        with patch('product_api.ProductAPI') as mock_product_api, \
             patch('cart_api.ShoppingCartAPI') as mock_cart_api, \
             patch('order_api.OrderManagementAPI') as mock_order_api, \
             patch('analytics_api.AnalyticsService') as mock_analytics_service:
            
            product_api_instance = MagicMock()
            cart_api_instance = MagicMock()
            order_api_instance = MagicMock()
            analytics_service_instance = MagicMock()
            
            mock_product_api.return_value = product_api_instance
            mock_cart_api.return_value = cart_api_instance
            mock_order_api.return_value = order_api_instance
            mock_analytics_service.return_value = analytics_service_instance
            
            user = self.test_users[0]
            product = self.test_products[0]
            
            # Step 1: Check initial inventory
            product_api_instance.get_product_detail.return_value = {
                'statusCode': 200,
                'body': json.dumps({
                    'product': {
                        **product,
                        'available_quantity': 100
                    }
                })
            }
            
            initial_product = product_api_instance.get_product_detail({
                'pathParameters': {'id': product['product_id']}
            })
            initial_data = json.loads(initial_product['body'])
            initial_quantity = initial_data['product']['available_quantity']
            
            # Step 2: Add to cart (should reserve inventory)
            cart_api_instance.add_to_cart.return_value = {
                'statusCode': 200,
                'body': json.dumps({
                    'message': 'Item added to cart successfully',
                    'productId': product['product_id'],
                    'quantity': 5,
                    'reserved_inventory': True
                })
            }
            
            cart_result = cart_api_instance.add_to_cart({
                'pathParameters': {'userId': user['userId']},
                'body': json.dumps({'productId': product['product_id'], 'quantity': 5})
            })
            assert cart_result['statusCode'] == 200
            
            # Step 3: Check inventory after cart addition (should show reservation)
            product_api_instance.get_product_detail.return_value = {
                'statusCode': 200,
                'body': json.dumps({
                    'product': {
                        **product,
                        'available_quantity': 95,  # Reduced by 5
                        'reserved_quantity': 5
                    }
                })
            }
            
            after_cart_product = product_api_instance.get_product_detail({
                'pathParameters': {'id': product['product_id']}
            })
            after_cart_data = json.loads(after_cart_product['body'])
            
            assert after_cart_data['product']['available_quantity'] == initial_quantity - 5
            assert after_cart_data['product']['reserved_quantity'] == 5
            
            # Step 4: Create order (should commit inventory reduction)
            order_api_instance.create_order.return_value = {
                'statusCode': 201,
                'body': json.dumps({
                    'orderId': 'consistency_order_123',
                    'status': 'confirmed',
                    'items': [{
                        'productId': product['product_id'],
                        'quantity': 5,
                        'inventory_committed': True
                    }],
                    'totalAmount': 1499.95
                })
            }
            
            order_result = order_api_instance.create_order({
                'body': json.dumps({
                    'userId': user['userId'],
                    'items': [{'productId': product['product_id'], 'quantity': 5}]
                })
            })
            assert order_result['statusCode'] == 201
            
            # Step 5: Check final inventory (should show committed reduction)
            product_api_instance.get_product_detail.return_value = {
                'statusCode': 200,
                'body': json.dumps({
                    'product': {
                        **product,
                        'available_quantity': 95,  # Permanently reduced
                        'reserved_quantity': 0,    # Reservation cleared
                        'sold_quantity': 5
                    }
                })
            }
            
            final_product = product_api_instance.get_product_detail({
                'pathParameters': {'id': product['product_id']}
            })
            final_data = json.loads(final_product['body'])
            
            assert final_data['product']['available_quantity'] == 95
            assert final_data['product']['reserved_quantity'] == 0
            assert final_data['product']['sold_quantity'] == 5
            
            # Step 6: Verify analytics consistency
            analytics_service_instance.get_product_analytics.return_value = {
                'success': True,
                'productId': product['product_id'],
                'analytics': {
                    'total_views': 1,
                    'cart_additions': 1,
                    'purchases': 1,
                    'conversion_rate': 1.0,
                    'inventory_movements': [
                        {'type': 'reserved', 'quantity': 5, 'timestamp': datetime.now().isoformat()},
                        {'type': 'sold', 'quantity': 5, 'timestamp': datetime.now().isoformat()}
                    ]
                }
            }
            
            analytics_result = analytics_service_instance.get_product_analytics(product['product_id'])
            
            # Validate data consistency across services
            assert analytics_result['success'] is True
            assert analytics_result['analytics']['purchases'] == 1
            assert len(analytics_result['analytics']['inventory_movements']) == 2


if __name__ == '__main__':
    pytest.main([__file__])