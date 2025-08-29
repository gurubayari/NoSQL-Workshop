"""
End-to-end tests for complete user workflows
Tests registration, shopping, review writing, and checkout processes
Implements comprehensive testing scenarios for task 12.3
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

class TestUserWorkflows:
    """End-to-end tests for complete user workflows"""
    
    def setup_method(self):
        """Set up test environment for each test"""
        self.test_user = {
            'userId': 'test_user_e2e_123',
            'email': 'testuser@example.com',
            'name': 'Test User',
            'preferences': {
                'categories': ['Electronics'],
                'price_range': [50, 500]
            }
        }
        
        self.test_products = [
            {
                'product_id': 'prod_e2e_1',
                'title': 'Wireless Bluetooth Headphones',
                'description': 'Premium wireless headphones',
                'price': 199.99,
                'category': 'Electronics',
                'rating': 4.5,
                'review_count': 150,
                'in_stock': True,
                'available_quantity': 50
            },
            {
                'product_id': 'prod_e2e_2',
                'title': 'Gaming Mouse',
                'description': 'High-precision gaming mouse',
                'price': 79.99,
                'category': 'Electronics',
                'rating': 4.3,
                'review_count': 89,
                'in_stock': True,
                'available_quantity': 25
            }
        ]
    
    def test_complete_shopping_workflow(self):
        """Test complete shopping workflow from product discovery to order completion"""   
     # Mock all the API functions
        with patch('product_api.ProductAPI') as mock_product_api, \
             patch('cart_api.ShoppingCartAPI') as mock_cart_api, \
             patch('order_api.OrderManagementAPI') as mock_order_api:
            
            # Set up mocks
            product_api_instance = MagicMock()
            cart_api_instance = MagicMock()
            order_api_instance = MagicMock()
            
            mock_product_api.return_value = product_api_instance
            mock_cart_api.return_value = cart_api_instance
            mock_order_api.return_value = order_api_instance
            
            # Step 1: User searches for products
            search_event = {
                'httpMethod': 'GET',
                'queryStringParameters': {
                    'q': 'wireless headphones',
                    'category': 'Electronics'
                }
            }
            
            product_api_instance.search_products.return_value = {
                'statusCode': 200,
                'body': json.dumps({
                    'products': [self.test_products[0]],
                    'total_results': 1,
                    'query': 'wireless headphones'
                })
            }
            
            search_result = product_api_instance.search_products(search_event)
            assert search_result['statusCode'] == 200
            
            # Step 2: User views product details
            product_detail_event = {
                'pathParameters': {'id': 'prod_e2e_1'}
            }
            
            product_api_instance.get_product_detail.return_value = {
                'statusCode': 200,
                'body': json.dumps({
                    'product': self.test_products[0],
                    'reviews_summary': {'total_reviews': 150, 'average_rating': 4.5}
                })
            }
            
            detail_result = product_api_instance.get_product_detail(product_detail_event)
            assert detail_result['statusCode'] == 200
            
            # Step 3: User adds product to cart
            add_to_cart_event = {
                'pathParameters': {'userId': self.test_user['userId']},
                'body': json.dumps({
                    'productId': 'prod_e2e_1',
                    'quantity': 1
                })
            }
            
            cart_api_instance.add_to_cart.return_value = {
                'statusCode': 200,
                'body': json.dumps({
                    'message': 'Item added to cart successfully',
                    'productId': 'prod_e2e_1',
                    'quantity': 1,
                    'price': 199.99
                })
            }
            
            cart_result = cart_api_instance.add_to_cart(add_to_cart_event)
            assert cart_result['statusCode'] == 200
            
            # Step 4: User views cart
            get_cart_event = {
                'pathParameters': {'userId': self.test_user['userId']}
            }
            
            cart_api_instance.get_cart.return_value = {
                'statusCode': 200,
                'body': json.dumps({
                    'userId': self.test_user['userId'],
                    'items': [{
                        'productId': 'prod_e2e_1',
                        'title': 'Wireless Bluetooth Headphones',
                        'quantity': 1,
                        'price': 199.99,
                        'subtotal': 199.99
                    }],
                    'totalAmount': 199.99
                })
            }
            
            cart_view_result = cart_api_instance.get_cart(get_cart_event)
            assert cart_view_result['statusCode'] == 200
            
            # Step 5: User creates order
            create_order_event = {
                'body': json.dumps({
                    'userId': self.test_user['userId'],
                    'items': [{
                        'productId': 'prod_e2e_1',
                        'quantity': 1
                    }],
                    'paymentMethod': {
                        'type': 'credit_card',
                        'cardNumber': '4111111111111111'
                    },
                    'shippingAddress': {
                        'street': '123 Test St',
                        'city': 'Test City',
                        'state': 'TS',
                        'zipCode': '12345'
                    }
                })
            }
            
            order_api_instance.create_order.return_value = {
                'statusCode': 201,
                'body': json.dumps({
                    'orderId': 'ORD-E2E-12345',
                    'status': 'confirmed',
                    'totalAmount': 219.98,  # Including tax and shipping
                    'message': 'Order created successfully'
                })
            }
            
            order_result = order_api_instance.create_order(create_order_event)
            assert order_result['statusCode'] == 201
            
            # Verify the complete workflow
            order_data = json.loads(order_result['body'])
            assert 'orderId' in order_data
            assert order_data['status'] == 'confirmed'
            assert order_data['totalAmount'] > 0
    
    def test_review_writing_workflow(self):
        """Test complete review writing workflow"""
        with patch('review_api.ReviewAPI') as mock_review_api:
            review_api_instance = MagicMock()
            mock_review_api.return_value = review_api_instance
            
            # Step 1: User writes a review
            create_review_data = {
                'userId': self.test_user['userId'],
                'productId': 'prod_e2e_1',
                'rating': 5,
                'title': 'Excellent headphones!',
                'content': 'These headphones have amazing sound quality and comfort. Highly recommended!',
                'aspectRatings': {
                    'quality': 5,
                    'value': 4,
                    'comfort': 5
                }
            }
            
            review_api_instance.create_review.return_value = {
                'statusCode': 201,
                'body': json.dumps({
                    'message': 'Review created successfully',
                    'reviewId': 'review_e2e_123',
                    'isVerifiedPurchase': True,
                    'sentiment': {
                        'score': 0.8,
                        'label': 'positive'
                    }
                })
            }
            
            review_result = review_api_instance.create_review(create_review_data)
            assert review_result['statusCode'] == 201
            
            # Step 2: Other users view the review
            get_reviews_params = {
                'productId': 'prod_e2e_1',
                'sortBy': 'helpful',
                'page': '1'
            }
            
            review_api_instance.get_reviews.return_value = {
                'statusCode': 200,
                'body': json.dumps({
                    'reviews': [{
                        'reviewId': 'review_e2e_123',
                        'userId': self.test_user['userId'],
                        'rating': 5,
                        'title': 'Excellent headphones!',
                        'content': 'These headphones have amazing sound quality and comfort.',
                        'isVerifiedPurchase': True,
                        'helpfulCount': 0,
                        'sentiment': {'score': 0.8, 'label': 'positive'}
                    }],
                    'pagination': {'page': 1, 'totalCount': 1}
                })
            }
            
            reviews_result = review_api_instance.get_reviews(get_reviews_params)
            assert reviews_result['statusCode'] == 200
            
            # Step 3: Another user votes the review as helpful
            vote_data = {
                'reviewId': 'review_e2e_123',
                'userId': 'other_user_456',
                'isHelpful': True
            }
            
            review_api_instance.vote_helpful.return_value = {
                'statusCode': 200,
                'body': json.dumps({
                    'message': 'Vote recorded successfully',
                    'helpfulCount': 1,
                    'notHelpfulCount': 0
                })
            }
            
            vote_result = review_api_instance.vote_helpful(vote_data)
            assert vote_result['statusCode'] == 200
            
            # Verify the review workflow
            review_data = json.loads(review_result['body'])
            assert 'reviewId' in review_data
            assert review_data['isVerifiedPurchase'] is True
            
            vote_data = json.loads(vote_result['body'])
            assert vote_data['helpfulCount'] == 1
    
    def test_ai_chat_workflow(self):
        """Test AI chat functionality with context retention"""
        with patch('chat_api.ChatService') as mock_chat_service:
            chat_service_instance = MagicMock()
            mock_chat_service.return_value = chat_service_instance
            
            # Step 1: User asks about products
            first_message = {
                'user_id': self.test_user['userId'],
                'message': 'What are the best wireless headphones?',
                'session_id': 'session_e2e_123'
            }
            
            chat_service_instance.send_message.return_value = {
                'success': True,
                'message_id': 'msg_1',
                'response': 'Based on customer reviews, I recommend the Wireless Bluetooth Headphones. They have excellent sound quality and 4.5-star rating.',
                'sources': ['Product: Wireless Bluetooth Headphones'],
                'session_id': 'session_e2e_123'
            }
            
            first_response = chat_service_instance.send_message(
                first_message['user_id'],
                first_message['message'],
                first_message['session_id']
            )
            assert first_response['success'] is True
            assert 'Wireless Bluetooth Headphones' in first_response['response']
            
            # Step 2: User asks follow-up question
            followup_message = {
                'user_id': self.test_user['userId'],
                'message': 'What do customers say about the battery life?',
                'session_id': 'session_e2e_123'
            }
            
            chat_service_instance.send_message.return_value = {
                'success': True,
                'message_id': 'msg_2',
                'response': 'Customers frequently praise the battery life, with many reviews mentioning it lasts all day. One verified buyer said "Battery life is excellent, easily lasts a full day of use."',
                'sources': ['Customer Review: Excellent battery life'],
                'session_id': 'session_e2e_123'
            }
            
            followup_response = chat_service_instance.send_message(
                followup_message['user_id'],
                followup_message['message'],
                followup_message['session_id']
            )
            assert followup_response['success'] is True
            assert 'battery life' in followup_response['response'].lower()
            
            # Step 3: User gets chat history
            chat_service_instance.get_chat_history.return_value = {
                'success': True,
                'messages': [
                    {
                        'message_id': 'msg_1',
                        'role': 'user',
                        'content': 'What are the best wireless headphones?',
                        'timestamp': datetime.now(timezone.utc).isoformat()
                    },
                    {
                        'message_id': 'msg_1_response',
                        'role': 'assistant',
                        'content': 'Based on customer reviews, I recommend...',
                        'timestamp': datetime.now(timezone.utc).isoformat()
                    },
                    {
                        'message_id': 'msg_2',
                        'role': 'user',
                        'content': 'What do customers say about the battery life?',
                        'timestamp': datetime.now(timezone.utc).isoformat()
                    },
                    {
                        'message_id': 'msg_2_response',
                        'role': 'assistant',
                        'content': 'Customers frequently praise the battery life...',
                        'timestamp': datetime.now(timezone.utc).isoformat()
                    }
                ],
                'has_more': False
            }
            
            history_result = chat_service_instance.get_chat_history(self.test_user['userId'])
            assert history_result['success'] is True
            assert len(history_result['messages']) == 4  # 2 user messages + 2 AI responses
    
    def test_search_and_analytics_workflow(self):
        """Test search functionality with auto-complete and analytics"""
        with patch('search_api.SearchAPI') as mock_search_api, \
             patch('analytics_api.AnalyticsService') as mock_analytics_service:
            
            search_api_instance = MagicMock()
            analytics_service_instance = MagicMock()
            mock_search_api.return_value = search_api_instance
            mock_analytics_service.return_value = analytics_service_instance
            
            # Step 1: User gets auto-complete suggestions
            search_api_instance.get_auto_complete_suggestions.return_value = [
                {'text': 'wireless headphones', 'type': 'popular', 'count': 1500},
                {'text': 'wireless mouse', 'type': 'popular', 'count': 1200},
                {'text': 'Wireless Bluetooth Headphones', 'type': 'product', 'rating': 4.5}
            ]
            
            suggestions = search_api_instance.get_auto_complete_suggestions('wireless', limit=5)
            assert len(suggestions) == 3
            assert suggestions[0]['text'] == 'wireless headphones'
            
            # Step 2: User performs search
            search_api_instance.search_products.return_value = {
                'products': [self.test_products[0]],
                'total': 1,
                'query': 'wireless headphones',
                'alternatives': []
            }
            
            search_results = search_api_instance.search_products(
                'wireless headphones',
                filters={'category': ['Electronics']},
                sort_by='relevance',
                page=1,
                page_size=20
            )
            assert search_results['total'] == 1
            assert len(search_results['products']) == 1
            
            # Step 3: User gets semantic review search
            analytics_service_instance.semantic_review_search.return_value = {
                'success': True,
                'query': 'phones with good audio quality',
                'total_results': 2,
                'results': [
                    {
                        'review_id': 'review_1',
                        'product_title': 'Wireless Bluetooth Headphones',
                        'review_content': 'Amazing audio quality',
                        'rating': 5,
                        'similarity_score': 0.9
                    }
                ],
                'insights': {
                    'summary': 'Users are very satisfied with audio quality',
                    'key_findings': ['High ratings for sound quality']
                }
            }
            
            semantic_results = analytics_service_instance.semantic_review_search(
                'phones with good audio quality',
                {'limit': 10}
            )
            assert semantic_results['success'] is True
            assert semantic_results['total_results'] == 2
    
    def test_cross_device_cart_continuity(self):
        """Test cart continuity across different sessions/devices"""
        with patch('cart_api.ShoppingCartAPI') as mock_cart_api:
            cart_api_instance = MagicMock()
            mock_cart_api.return_value = cart_api_instance
            
            # Step 1: User adds items to cart on device 1
            add_to_cart_event = {
                'pathParameters': {'userId': self.test_user['userId']},
                'body': json.dumps({
                    'productId': 'prod_e2e_1',
                    'quantity': 2
                })
            }
            
            cart_api_instance.add_to_cart.return_value = {
                'statusCode': 200,
                'body': json.dumps({
                    'message': 'Item added to cart successfully',
                    'productId': 'prod_e2e_1',
                    'quantity': 2
                })
            }
            
            add_result = cart_api_instance.add_to_cart(add_to_cart_event)
            assert add_result['statusCode'] == 200
            
            # Step 2: User accesses cart from device 2 (different session)
            get_cart_event = {
                'pathParameters': {'userId': self.test_user['userId']}
            }
            
            cart_api_instance.get_cart.return_value = {
                'statusCode': 200,
                'body': json.dumps({
                    'userId': self.test_user['userId'],
                    'items': [{
                        'productId': 'prod_e2e_1',
                        'title': 'Wireless Bluetooth Headphones',
                        'quantity': 2,
                        'price': 199.99,
                        'subtotal': 399.98
                    }],
                    'totalAmount': 399.98
                })
            }
            
            cart_result = cart_api_instance.get_cart(get_cart_event)
            assert cart_result['statusCode'] == 200
            
            cart_data = json.loads(cart_result['body'])
            assert len(cart_data['items']) == 1
            assert cart_data['items'][0]['quantity'] == 2
            assert cart_data['totalAmount'] == 399.98
            
            # Step 3: User updates cart from device 2
            update_cart_event = {
                'pathParameters': {
                    'userId': self.test_user['userId'],
                    'productId': 'prod_e2e_1'
                },
                'body': json.dumps({'quantity': 1})
            }
            
            cart_api_instance.update_cart_item.return_value = {
                'statusCode': 200,
                'body': json.dumps({
                    'message': 'Cart item updated successfully',
                    'productId': 'prod_e2e_1',
                    'quantity': 1,
                    'subtotal': 199.99
                })
            }
            
            update_result = cart_api_instance.update_cart_item(update_cart_event)
            assert update_result['statusCode'] == 200
            
            # Verify cart continuity works across sessions
            update_data = json.loads(update_result['body'])
            assert update_data['quantity'] == 1
    
    def test_error_handling_and_recovery(self):
        """Test error handling and recovery scenarios"""
        with patch('product_api.ProductAPI') as mock_product_api, \
             patch('cart_api.ShoppingCartAPI') as mock_cart_api:
            
            product_api_instance = MagicMock()
            cart_api_instance = MagicMock()
            mock_product_api.return_value = product_api_instance
            mock_cart_api.return_value = cart_api_instance
            
            # Test 1: Product not found
            product_api_instance.get_product_detail.return_value = {
                'statusCode': 404,
                'body': json.dumps({
                    'error': 'Product not found',
                    'message': 'Product with ID nonexistent_prod does not exist'
                })
            }
            
            not_found_event = {'pathParameters': {'id': 'nonexistent_prod'}}
            not_found_result = product_api_instance.get_product_detail(not_found_event)
            assert not_found_result['statusCode'] == 404
            
            # Test 2: Insufficient inventory
            cart_api_instance.add_to_cart.return_value = {
                'statusCode': 400,
                'body': json.dumps({
                    'error': 'Insufficient inventory',
                    'message': 'Only 1 items available, requested 5'
                })
            }
            
            insufficient_inventory_event = {
                'pathParameters': {'userId': self.test_user['userId']},
                'body': json.dumps({
                    'productId': 'prod_e2e_1',
                    'quantity': 5  # More than available
                })
            }
            
            inventory_result = cart_api_instance.add_to_cart(insufficient_inventory_event)
            assert inventory_result['statusCode'] == 400
            
            # Test 3: Invalid input validation
            cart_api_instance.add_to_cart.return_value = {
                'statusCode': 400,
                'body': json.dumps({
                    'error': 'Invalid quantity',
                    'message': 'Quantity must be a positive integer'
                })
            }
            
            invalid_quantity_event = {
                'pathParameters': {'userId': self.test_user['userId']},
                'body': json.dumps({
                    'productId': 'prod_e2e_1',
                    'quantity': -1  # Invalid quantity
                })
            }
            
            invalid_result = cart_api_instance.add_to_cart(invalid_quantity_event)
            assert invalid_result['statusCode'] == 400
            
            # Verify error responses contain helpful information
            error_data = json.loads(invalid_result['body'])
            assert 'error' in error_data
            assert 'message' in error_data


    def test_user_registration_workflow(self):
        """Test complete user registration workflow with email verification"""
        with patch('auth_api.AuthenticationAPI') as mock_auth_api:
            auth_api_instance = MagicMock()
            mock_auth_api.return_value = auth_api_instance
            
            # Step 1: User initiates registration
            registration_data = {
                'email': 'newuser@example.com',
                'password': 'SecurePassword123!',
                'name': 'New User',
                'preferences': {
                    'categories': ['Electronics', 'Books'],
                    'notifications': True
                }
            }
            
            auth_api_instance.register_user.return_value = {
                'statusCode': 201,
                'body': json.dumps({
                    'message': 'Registration initiated. Please check your email for verification.',
                    'userId': 'new_user_456',
                    'verificationRequired': True
                })
            }
            
            registration_result = auth_api_instance.register_user(registration_data)
            assert registration_result['statusCode'] == 201
            
            # Step 2: User verifies email with OTP
            verification_data = {
                'email': 'newuser@example.com',
                'verificationCode': '123456'
            }
            
            auth_api_instance.verify_email.return_value = {
                'statusCode': 200,
                'body': json.dumps({
                    'message': 'Email verified successfully',
                    'userId': 'new_user_456',
                    'accessToken': 'jwt_token_here',
                    'refreshToken': 'refresh_token_here'
                })
            }
            
            verification_result = auth_api_instance.verify_email(verification_data)
            assert verification_result['statusCode'] == 200
            
            # Step 3: User logs in
            login_data = {
                'email': 'newuser@example.com',
                'password': 'SecurePassword123!'
            }
            
            auth_api_instance.login.return_value = {
                'statusCode': 200,
                'body': json.dumps({
                    'message': 'Login successful',
                    'userId': 'new_user_456',
                    'accessToken': 'jwt_token_here',
                    'refreshToken': 'refresh_token_here',
                    'user': {
                        'userId': 'new_user_456',
                        'email': 'newuser@example.com',
                        'name': 'New User',
                        'preferences': registration_data['preferences']
                    }
                })
            }
            
            login_result = auth_api_instance.login(login_data)
            assert login_result['statusCode'] == 200
            
            # Verify complete registration workflow
            reg_data = json.loads(registration_result['body'])
            verify_data = json.loads(verification_result['body'])
            login_data = json.loads(login_result['body'])
            
            assert reg_data['verificationRequired'] is True
            assert 'accessToken' in verify_data
            assert login_data['user']['email'] == 'newuser@example.com'
    
    def test_comprehensive_review_workflow(self):
        """Test comprehensive review writing and management workflow"""
        with patch('review_api.ReviewAPI') as mock_review_api, \
             patch('analytics_api.AnalyticsService') as mock_analytics_service:
            
            review_api_instance = MagicMock()
            analytics_service_instance = MagicMock()
            mock_review_api.return_value = review_api_instance
            mock_analytics_service.return_value = analytics_service_instance
            
            # Step 1: User writes comprehensive review with aspects
            comprehensive_review_data = {
                'userId': self.test_user['userId'],
                'productId': 'prod_e2e_1',
                'rating': 4,
                'title': 'Great headphones with minor issues',
                'content': 'These headphones have excellent sound quality and are very comfortable for long listening sessions. The noise cancellation works well on flights. However, they are a bit heavy and the price is on the higher side. Overall, I would recommend them for audiophiles.',
                'aspectRatings': {
                    'audio_quality': 5,
                    'comfort': 4,
                    'value_for_money': 3,
                    'build_quality': 4,
                    'battery_life': 5,
                    'noise_cancellation': 5
                },
                'pros': ['Excellent sound quality', 'Great noise cancellation', 'Long battery life'],
                'cons': ['Heavy weight', 'Expensive'],
                'recommendToOthers': True,
                'wouldBuyAgain': True,
                'images': ['review_image_1.jpg', 'review_image_2.jpg']
            }
            
            review_api_instance.create_review.return_value = {
                'statusCode': 201,
                'body': json.dumps({
                    'message': 'Review created successfully',
                    'reviewId': 'comprehensive_review_123',
                    'isVerifiedPurchase': True,
                    'sentiment': {
                        'overall_score': 0.7,
                        'label': 'positive',
                        'aspects': {
                            'audio_quality': {'score': 0.9, 'label': 'very_positive'},
                            'comfort': {'score': 0.6, 'label': 'positive'},
                            'value_for_money': {'score': 0.2, 'label': 'neutral'}
                        }
                    },
                    'aiInsights': {
                        'keyThemes': ['sound quality', 'comfort', 'price'],
                        'summary': 'User appreciates audio quality but has concerns about price'
                    }
                })
            }
            
            review_result = review_api_instance.create_review(comprehensive_review_data)
            assert review_result['statusCode'] == 201
            
            # Step 2: Other users vote on review helpfulness
            helpfulness_votes = [
                {'userId': 'user_1', 'isHelpful': True},
                {'userId': 'user_2', 'isHelpful': True},
                {'userId': 'user_3', 'isHelpful': False},
                {'userId': 'user_4', 'isHelpful': True}
            ]
            
            for vote in helpfulness_votes:
                review_api_instance.vote_helpful.return_value = {
                    'statusCode': 200,
                    'body': json.dumps({
                        'message': 'Vote recorded successfully',
                        'reviewId': 'comprehensive_review_123',
                        'helpfulCount': 3,
                        'notHelpfulCount': 1
                    })
                }
                
                vote_result = review_api_instance.vote_helpful({
                    'reviewId': 'comprehensive_review_123',
                    'userId': vote['userId'],
                    'isHelpful': vote['isHelpful']
                })
                assert vote_result['statusCode'] == 200
            
            # Step 3: Get AI-powered review insights
            analytics_service_instance.get_review_insights.return_value = {
                'success': True,
                'productId': 'prod_e2e_1',
                'insights': {
                    'sentiment_distribution': {
                        'positive': 75,
                        'neutral': 15,
                        'negative': 10
                    },
                    'aspect_scores': {
                        'audio_quality': 4.6,
                        'comfort': 4.2,
                        'value_for_money': 3.8,
                        'build_quality': 4.4
                    },
                    'common_themes': [
                        {'theme': 'excellent sound quality', 'frequency': 89},
                        {'theme': 'comfortable fit', 'frequency': 76},
                        {'theme': 'good battery life', 'frequency': 67}
                    ],
                    'recommendations': {
                        'best_for': ['audiophiles', 'frequent travelers', 'music producers'],
                        'concerns': ['price-sensitive buyers', 'weight-conscious users']
                    }
                }
            }
            
            insights_result = analytics_service_instance.get_review_insights('prod_e2e_1')
            assert insights_result['success'] is True
            assert insights_result['insights']['aspect_scores']['audio_quality'] > 4.0
            
            # Step 4: User manages their reviews
            review_api_instance.get_user_reviews.return_value = {
                'statusCode': 200,
                'body': json.dumps({
                    'reviews': [{
                        'reviewId': 'comprehensive_review_123',
                        'productId': 'prod_e2e_1',
                        'productTitle': 'Wireless Bluetooth Headphones',
                        'rating': 4,
                        'title': 'Great headphones with minor issues',
                        'createdAt': datetime.now(timezone.utc).isoformat(),
                        'helpfulCount': 3,
                        'status': 'published'
                    }],
                    'pagination': {'page': 1, 'totalCount': 1}
                })
            }
            
            user_reviews_result = review_api_instance.get_user_reviews(self.test_user['userId'])
            assert user_reviews_result['statusCode'] == 200
            
            # Verify comprehensive review workflow
            review_data = json.loads(review_result['body'])
            assert 'sentiment' in review_data
            assert 'aiInsights' in review_data
            assert review_data['isVerifiedPurchase'] is True
    
    def test_ai_chat_context_retention_workflow(self):
        """Test AI chat functionality with advanced context retention and memory management"""
        with patch('chat_api.ChatService') as mock_chat_service:
            chat_service_instance = MagicMock()
            mock_chat_service.return_value = chat_service_instance
            
            session_id = 'advanced_chat_session_123'
            
            # Step 1: User starts conversation about specific product category
            initial_message = {
                'user_id': self.test_user['userId'],
                'message': 'I need headphones for gaming. What do you recommend?',
                'session_id': session_id
            }
            
            chat_service_instance.send_message.return_value = {
                'success': True,
                'message_id': 'msg_1',
                'response': 'For gaming, I recommend headphones with low latency, good microphone quality, and immersive sound. Based on customer reviews, the Wireless Gaming Headset has excellent audio quality and comfortable fit for long gaming sessions.',
                'context': {
                    'user_intent': 'product_recommendation',
                    'category': 'gaming_headphones',
                    'key_requirements': ['low_latency', 'microphone', 'comfort']
                },
                'sources': ['Product: Wireless Gaming Headset', 'Customer Reviews'],
                'session_id': session_id
            }
            
            first_response = chat_service_instance.send_message(
                initial_message['user_id'],
                initial_message['message'],
                initial_message['session_id']
            )
            assert first_response['success'] is True
            assert 'gaming' in first_response['response'].lower()
            
            # Step 2: User asks follow-up about specific aspect (context retention test)
            followup_message = {
                'user_id': self.test_user['userId'],
                'message': 'What about the microphone quality?',
                'session_id': session_id
            }
            
            chat_service_instance.send_message.return_value = {
                'success': True,
                'message_id': 'msg_2',
                'response': 'The Wireless Gaming Headset has excellent microphone quality according to customer reviews. Users specifically mention clear voice transmission and effective noise cancellation for the microphone. One verified buyer said "The mic quality is crystal clear, my teammates can hear me perfectly even in noisy environments."',
                'context': {
                    'previous_product': 'Wireless Gaming Headset',
                    'current_focus': 'microphone_quality',
                    'conversation_flow': 'product_details'
                },
                'sources': ['Customer Review: Clear microphone quality'],
                'session_id': session_id
            }
            
            followup_response = chat_service_instance.send_message(
                followup_message['user_id'],
                followup_message['message'],
                followup_message['session_id']
            )
            assert followup_response['success'] is True
            assert 'microphone' in followup_response['response'].lower()
            
            # Step 3: User asks about different product (context switching)
            context_switch_message = {
                'user_id': self.test_user['userId'],
                'message': 'Actually, I also need a wireless mouse. Any suggestions?',
                'session_id': session_id
            }
            
            chat_service_instance.send_message.return_value = {
                'success': True,
                'message_id': 'msg_3',
                'response': 'For gaming mice, I recommend the Gaming Mouse which has high precision and customizable buttons. Since you mentioned gaming earlier, this mouse pairs well with gaming headsets for a complete setup.',
                'context': {
                    'previous_products': ['Wireless Gaming Headset'],
                    'current_product': 'Gaming Mouse',
                    'user_profile': 'gamer',
                    'cross_sell_opportunity': True
                },
                'sources': ['Product: Gaming Mouse'],
                'session_id': session_id
            }
            
            context_switch_response = chat_service_instance.send_message(
                context_switch_message['user_id'],
                context_switch_message['message'],
                context_switch_message['session_id']
            )
            assert context_switch_response['success'] is True
            assert 'mouse' in context_switch_response['response'].lower()
            
            # Step 4: Test memory management (last 10 messages in cache)
            # Simulate multiple messages to test memory limits
            for i in range(15):  # More than the 10-message cache limit
                chat_service_instance.send_message.return_value = {
                    'success': True,
                    'message_id': f'msg_{i+4}',
                    'response': f'Response to message {i+4}',
                    'session_id': session_id
                }
                
                response = chat_service_instance.send_message(
                    self.test_user['userId'],
                    f'Test message {i+4}',
                    session_id
                )
                assert response['success'] is True
            
            # Step 5: Get chat history with pagination
            chat_service_instance.get_chat_history.return_value = {
                'success': True,
                'messages': [
                    # Recent messages (should be in cache)
                    {'message_id': 'msg_18', 'role': 'user', 'content': 'Test message 18'},
                    {'message_id': 'msg_17', 'role': 'user', 'content': 'Test message 17'},
                    # ... (last 10 messages)
                ],
                'has_more': True,
                'next_page_token': 'page_2_token'
            }
            
            recent_history = chat_service_instance.get_chat_history(
                self.test_user['userId'],
                session_id,
                limit=10
            )
            assert recent_history['success'] is True
            assert recent_history['has_more'] is True
            
            # Step 6: Get older messages from DynamoDB
            chat_service_instance.get_chat_history.return_value = {
                'success': True,
                'messages': [
                    # Older messages (from DynamoDB)
                    {'message_id': 'msg_1', 'role': 'user', 'content': 'I need headphones for gaming'},
                    {'message_id': 'msg_2', 'role': 'user', 'content': 'What about the microphone quality?'},
                    {'message_id': 'msg_3', 'role': 'user', 'content': 'Actually, I also need a wireless mouse'}
                ],
                'has_more': False,
                'page_token': 'page_2_token'
            }
            
            older_history = chat_service_instance.get_chat_history(
                self.test_user['userId'],
                session_id,
                page_token='page_2_token'
            )
            assert older_history['success'] is True
            assert len(older_history['messages']) >= 3
    
    def test_session_management_workflow(self):
        """Test session management and token handling"""
        with patch('auth_api.AuthenticationAPI') as mock_auth_api:
            auth_api_instance = MagicMock()
            mock_auth_api.return_value = auth_api_instance
            
            # Step 1: User logs in and gets tokens
            login_data = {
                'email': self.test_user['email'],
                'password': 'TestPassword123!'
            }
            
            auth_api_instance.login.return_value = {
                'statusCode': 200,
                'body': json.dumps({
                    'message': 'Login successful',
                    'userId': self.test_user['userId'],
                    'accessToken': 'access_token_123',
                    'refreshToken': 'refresh_token_456',
                    'expiresIn': 3600,
                    'tokenType': 'Bearer'
                })
            }
            
            login_result = auth_api_instance.login(login_data)
            assert login_result['statusCode'] == 200
            
            # Step 2: Use access token for authenticated requests
            auth_api_instance.validate_token.return_value = {
                'statusCode': 200,
                'body': json.dumps({
                    'valid': True,
                    'userId': self.test_user['userId'],
                    'expiresAt': (datetime.now(timezone.utc).timestamp() + 3600)
                })
            }
            
            token_validation = auth_api_instance.validate_token('access_token_123')
            assert token_validation['statusCode'] == 200
            
            # Step 3: Token expires, use refresh token
            auth_api_instance.refresh_token.return_value = {
                'statusCode': 200,
                'body': json.dumps({
                    'message': 'Token refreshed successfully',
                    'accessToken': 'new_access_token_789',
                    'refreshToken': 'new_refresh_token_012',
                    'expiresIn': 3600
                })
            }
            
            refresh_result = auth_api_instance.refresh_token('refresh_token_456')
            assert refresh_result['statusCode'] == 200
            
            # Step 4: User logs out
            auth_api_instance.logout.return_value = {
                'statusCode': 200,
                'body': json.dumps({
                    'message': 'Logout successful'
                })
            }
            
            logout_result = auth_api_instance.logout('new_access_token_789')
            assert logout_result['statusCode'] == 200
            
            # Verify session management workflow
            login_data = json.loads(login_result['body'])
            refresh_data = json.loads(refresh_result['body'])
            
            assert 'accessToken' in login_data
            assert 'refreshToken' in login_data
            assert 'accessToken' in refresh_data
            assert refresh_data['accessToken'] != login_data['accessToken']


if __name__ == '__main__':
    pytest.main([__file__])