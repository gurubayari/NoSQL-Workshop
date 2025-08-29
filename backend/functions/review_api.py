"""
Review API Lambda Function for AWS NoSQL Workshop
Handles review operations including creation, retrieval, voting, and moderation
"""
import json
import logging
import boto3
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
from botocore.exceptions import ClientError
import uuid
import re

# Import shared utilities
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'shared'))

from database import (
    get_documentdb_collection, 
    get_dynamodb_table,
    cache_get, 
    cache_set, 
    cache_delete,
    get_cache_key
)
from config import config

# Configure logging
logger = logging.getLogger()
logger.setLevel(getattr(logging, config.LOG_LEVEL))

# Initialize Bedrock client for sentiment analysis
bedrock_client = boto3.client('bedrock-runtime', region_name=config.AWS_REGION)

class ReviewAPI:
    """Review API handler class"""
    
    def __init__(self):
        self.reviews_collection = get_documentdb_collection('reviews')
        self.users_table = get_dynamodb_table(config.USERS_TABLE)
        self.orders_table = get_dynamodb_table(config.ORDERS_TABLE)
        
        # Moderation keywords for basic content filtering
        self.moderation_keywords = [
            'spam', 'fake', 'scam', 'terrible', 'worst', 'hate',
            'stupid', 'garbage', 'trash', 'awful', 'horrible'
        ]
    
    def create_review(self, event_body: Dict) -> Dict:
        """Create a new product review"""
        try:
            # Extract review data
            user_id = event_body.get('userId')
            product_id = event_body.get('productId')
            rating = event_body.get('rating')
            title = event_body.get('title', '')
            content = event_body.get('content', '')
            images = event_body.get('images', [])
            aspect_ratings = event_body.get('aspectRatings', {})
            
            # Validate required fields
            if not all([user_id, product_id, rating]):
                return {
                    'statusCode': 400,
                    'body': json.dumps({
                        'error': 'Missing required fields: userId, productId, rating'
                    })
                }
            
            # Validate rating range
            if not isinstance(rating, (int, float)) or rating < 1 or rating > 5:
                return {
                    'statusCode': 400,
                    'body': json.dumps({
                        'error': 'Rating must be between 1 and 5'
                    })
                }
            
            # Check if user has already reviewed this product
            existing_review = self.reviews_collection.find_one({
                'userId': user_id,
                'productId': product_id
            })
            
            if existing_review:
                return {
                    'statusCode': 409,
                    'body': json.dumps({
                        'error': 'User has already reviewed this product'
                    })
                }
            
            # Check if user has purchased this product (verified purchase)
            is_verified_purchase = self._check_verified_purchase(user_id, product_id)
            
            # Perform content moderation
            moderation_result = self._moderate_content(title + ' ' + content)
            if not moderation_result['approved']:
                return {
                    'statusCode': 400,
                    'body': json.dumps({
                        'error': 'Review content violates community guidelines',
                        'reason': moderation_result['reason']
                    })
                }
            
            # Generate sentiment analysis using Bedrock
            sentiment_analysis = self._analyze_sentiment(content)
            
            # Create review document
            review_id = str(uuid.uuid4())
            review_doc = {
                'reviewId': review_id,
                'userId': user_id,
                'productId': product_id,
                'rating': float(rating),
                'title': title.strip(),
                'content': content.strip(),
                'images': images,
                'aspectRatings': aspect_ratings,
                'isVerifiedPurchase': is_verified_purchase,
                'helpfulCount': 0,
                'notHelpfulCount': 0,
                'helpfulVotes': [],  # List of user IDs who voted helpful
                'notHelpfulVotes': [],  # List of user IDs who voted not helpful
                'sentiment': sentiment_analysis,
                'isModerated': False,
                'isApproved': True,
                'createdAt': datetime.now(timezone.utc),
                'updatedAt': datetime.now(timezone.utc)
            }
            
            # Insert review into DocumentDB
            result = self.reviews_collection.insert_one(review_doc)
            
            if result.inserted_id:
                # Clear product reviews cache
                cache_key = get_cache_key('product_reviews', product_id)
                cache_delete(cache_key)
                
                # Clear user reviews cache
                user_cache_key = get_cache_key('user_reviews', user_id)
                cache_delete(user_cache_key)
                
                logger.info(f"Review created successfully: {review_id}")
                
                return {
                    'statusCode': 201,
                    'body': json.dumps({
                        'message': 'Review created successfully',
                        'reviewId': review_id,
                        'isVerifiedPurchase': is_verified_purchase,
                        'sentiment': sentiment_analysis
                    })
                }
            else:
                raise Exception("Failed to insert review")
                
        except Exception as e:
            logger.error(f"Error creating review: {str(e)}")
            return {
                'statusCode': 500,
                'body': json.dumps({
                    'error': 'Internal server error',
                    'message': str(e)
                })
            }
    
    def get_reviews(self, query_params: Dict) -> Dict:
        """Get reviews with filtering and pagination"""
        try:
            product_id = query_params.get('productId')
            user_id = query_params.get('userId')
            rating_filter = query_params.get('rating')
            verified_only = query_params.get('verifiedOnly', 'false').lower() == 'true'
            sort_by = query_params.get('sortBy', 'createdAt')  # createdAt, rating, helpful
            sort_order = query_params.get('sortOrder', 'desc')
            page = int(query_params.get('page', '1'))
            limit = min(int(query_params.get('limit', '20')), config.MAX_PAGE_SIZE)
            
            # Build query filter
            query_filter = {}
            if product_id:
                query_filter['productId'] = product_id
            if user_id:
                query_filter['userId'] = user_id
            if rating_filter:
                query_filter['rating'] = {'$gte': float(rating_filter)}
            if verified_only:
                query_filter['isVerifiedPurchase'] = True
            
            # Only show approved reviews
            query_filter['isApproved'] = True
            
            # Check cache for product reviews
            cache_key = None
            if product_id and not user_id:
                cache_key = get_cache_key('product_reviews', f"{product_id}_{rating_filter}_{verified_only}_{sort_by}_{sort_order}_{page}_{limit}")
                cached_result = cache_get(cache_key)
                if cached_result:
                    return {
                        'statusCode': 200,
                        'body': cached_result
                    }
            
            # Build sort criteria
            sort_criteria = []
            if sort_by == 'helpful':
                sort_criteria.append(('helpfulCount', -1 if sort_order == 'desc' else 1))
            elif sort_by == 'rating':
                sort_criteria.append(('rating', -1 if sort_order == 'desc' else 1))
            else:  # createdAt
                sort_criteria.append(('createdAt', -1 if sort_order == 'desc' else 1))
            
            # Calculate skip for pagination
            skip = (page - 1) * limit
            
            # Execute query
            cursor = self.reviews_collection.find(query_filter).sort(sort_criteria).skip(skip).limit(limit)
            reviews = list(cursor)
            
            # Get total count for pagination
            total_count = self.reviews_collection.count_documents(query_filter)
            
            # Format reviews for response
            formatted_reviews = []
            for review in reviews:
                formatted_review = {
                    'reviewId': review['reviewId'],
                    'userId': review['userId'],
                    'productId': review['productId'],
                    'rating': review['rating'],
                    'title': review['title'],
                    'content': review['content'],
                    'images': review.get('images', []),
                    'aspectRatings': review.get('aspectRatings', {}),
                    'isVerifiedPurchase': review['isVerifiedPurchase'],
                    'helpfulCount': review['helpfulCount'],
                    'notHelpfulCount': review['notHelpfulCount'],
                    'sentiment': review.get('sentiment', {}),
                    'createdAt': review['createdAt'].isoformat(),
                    'updatedAt': review['updatedAt'].isoformat()
                }
                formatted_reviews.append(formatted_review)
            
            response_data = {
                'reviews': formatted_reviews,
                'pagination': {
                    'page': page,
                    'limit': limit,
                    'totalCount': total_count,
                    'totalPages': (total_count + limit - 1) // limit,
                    'hasNext': skip + limit < total_count,
                    'hasPrevious': page > 1
                }
            }
            
            response_body = json.dumps(response_data)
            
            # Cache the result if it's a product query
            if cache_key:
                cache_set(cache_key, response_body, ttl=300)  # Cache for 5 minutes
            
            return {
                'statusCode': 200,
                'body': response_body
            }
            
        except Exception as e:
            logger.error(f"Error getting reviews: {str(e)}")
            return {
                'statusCode': 500,
                'body': json.dumps({
                    'error': 'Internal server error',
                    'message': str(e)
                })
            }
    
    def vote_helpful(self, event_body: Dict) -> Dict:
        """Vote on review helpfulness"""
        try:
            review_id = event_body.get('reviewId')
            user_id = event_body.get('userId')
            is_helpful = event_body.get('isHelpful', True)
            
            if not all([review_id, user_id]):
                return {
                    'statusCode': 400,
                    'body': json.dumps({
                        'error': 'Missing required fields: reviewId, userId'
                    })
                }
            
            # Find the review
            review = self.reviews_collection.find_one({'reviewId': review_id})
            if not review:
                return {
                    'statusCode': 404,
                    'body': json.dumps({
                        'error': 'Review not found'
                    })
                }
            
            # Check if user has already voted
            helpful_votes = review.get('helpfulVotes', [])
            not_helpful_votes = review.get('notHelpfulVotes', [])
            
            # Remove previous votes by this user
            if user_id in helpful_votes:
                helpful_votes.remove(user_id)
            if user_id in not_helpful_votes:
                not_helpful_votes.remove(user_id)
            
            # Add new vote
            if is_helpful:
                helpful_votes.append(user_id)
            else:
                not_helpful_votes.append(user_id)
            
            # Update review
            update_result = self.reviews_collection.update_one(
                {'reviewId': review_id},
                {
                    '$set': {
                        'helpfulVotes': helpful_votes,
                        'notHelpfulVotes': not_helpful_votes,
                        'helpfulCount': len(helpful_votes),
                        'notHelpfulCount': len(not_helpful_votes),
                        'updatedAt': datetime.now(timezone.utc)
                    }
                }
            )
            
            if update_result.modified_count > 0:
                # Clear cache
                cache_key = get_cache_key('product_reviews', review['productId'])
                cache_delete(cache_key)
                
                return {
                    'statusCode': 200,
                    'body': json.dumps({
                        'message': 'Vote recorded successfully',
                        'helpfulCount': len(helpful_votes),
                        'notHelpfulCount': len(not_helpful_votes)
                    })
                }
            else:
                raise Exception("Failed to update review vote")
                
        except Exception as e:
            logger.error(f"Error voting on review: {str(e)}")
            return {
                'statusCode': 500,
                'body': json.dumps({
                    'error': 'Internal server error',
                    'message': str(e)
                })
            }
    
    def _check_verified_purchase(self, user_id: str, product_id: str) -> bool:
        """Check if user has purchased the product"""
        try:
            # Query orders table to check if user has purchased this product
            response = self.orders_table.scan(
                FilterExpression='userId = :user_id',
                ExpressionAttributeValues={':user_id': user_id}
            )
            
            for order in response.get('Items', []):
                order_items = order.get('items', [])
                for item in order_items:
                    if item.get('productId') == product_id:
                        return True
            
            return False
            
        except Exception as e:
            logger.warning(f"Error checking verified purchase: {str(e)}")
            return False
    
    def _moderate_content(self, content: str) -> Dict:
        """Basic content moderation using keyword filtering"""
        try:
            content_lower = content.lower()
            
            # Check for moderation keywords
            for keyword in self.moderation_keywords:
                if keyword in content_lower:
                    return {
                        'approved': False,
                        'reason': f'Content contains inappropriate language: {keyword}'
                    }
            
            # Check content length
            if len(content.strip()) < 10:
                return {
                    'approved': False,
                    'reason': 'Review content is too short (minimum 10 characters)'
                }
            
            # Check for excessive repetition (basic spam detection)
            words = content_lower.split()
            if len(words) > 5:
                word_count = {}
                for word in words:
                    word_count[word] = word_count.get(word, 0) + 1
                
                # If any word appears more than 50% of the time, flag as spam
                max_word_count = max(word_count.values())
                if max_word_count > len(words) * 0.5:
                    return {
                        'approved': False,
                        'reason': 'Content appears to be spam (excessive word repetition)'
                    }
            
            return {'approved': True, 'reason': None}
            
        except Exception as e:
            logger.warning(f"Error in content moderation: {str(e)}")
            return {'approved': True, 'reason': None}  # Default to approved if moderation fails
    
    def _analyze_sentiment(self, content: str) -> Dict:
        """Analyze review sentiment using Amazon Bedrock"""
        try:
            if not content.strip():
                return {
                    'score': 0.0,
                    'label': 'neutral',
                    'confidence': 0.0,
                    'aspects': {}
                }
            
            # Prepare prompt for sentiment analysis
            prompt = f"""
            Analyze the sentiment of this product review and provide aspect-based scoring.
            
            Review: "{content}"
            
            Please provide:
            1. Overall sentiment score (-1 to 1, where -1 is very negative, 0 is neutral, 1 is very positive)
            2. Sentiment label (positive, negative, neutral)
            3. Confidence score (0 to 1)
            4. Aspect scores for: quality, value, comfort, design, durability (each -1 to 1)
            
            Respond in JSON format only:
            {{
                "score": 0.0,
                "label": "neutral",
                "confidence": 0.0,
                "aspects": {{
                    "quality": 0.0,
                    "value": 0.0,
                    "comfort": 0.0,
                    "design": 0.0,
                    "durability": 0.0
                }}
            }}
            """
            
            # Call Bedrock
            response = bedrock_client.invoke_model(
                modelId=config.BEDROCK_MODEL_ID,
                body=json.dumps({
                    "anthropic_version": "bedrock-2023-05-31",
                    "max_tokens": 500,
                    "messages": [
                        {
                            "role": "user",
                            "content": prompt
                        }
                    ]
                })
            )
            
            response_body = json.loads(response['body'].read())
            ai_response = response_body['content'][0]['text']
            
            # Parse JSON response
            try:
                sentiment_data = json.loads(ai_response)
                return sentiment_data
            except json.JSONDecodeError:
                # Fallback to basic sentiment if AI response is not valid JSON
                logger.warning("Failed to parse Bedrock sentiment response")
                return self._basic_sentiment_analysis(content)
                
        except Exception as e:
            logger.warning(f"Error in Bedrock sentiment analysis: {str(e)}")
            return self._basic_sentiment_analysis(content)
    
    def _basic_sentiment_analysis(self, content: str) -> Dict:
        """Basic sentiment analysis fallback"""
        positive_words = ['good', 'great', 'excellent', 'amazing', 'love', 'perfect', 'awesome', 'fantastic']
        negative_words = ['bad', 'terrible', 'awful', 'hate', 'horrible', 'worst', 'disappointing']
        
        content_lower = content.lower()
        positive_count = sum(1 for word in positive_words if word in content_lower)
        negative_count = sum(1 for word in negative_words if word in content_lower)
        
        if positive_count > negative_count:
            score = min(0.8, positive_count * 0.2)
            label = 'positive'
        elif negative_count > positive_count:
            score = max(-0.8, -negative_count * 0.2)
            label = 'negative'
        else:
            score = 0.0
            label = 'neutral'
        
        return {
            'score': score,
            'label': label,
            'confidence': 0.6,
            'aspects': {
                'quality': score * 0.8,
                'value': score * 0.7,
                'comfort': score * 0.6,
                'design': score * 0.5,
                'durability': score * 0.4
            }
        }

def lambda_handler(event, context):
    """Main Lambda handler"""
    try:
        # Parse the event
        http_method = event.get('httpMethod', '')
        path = event.get('path', '')
        query_params = event.get('queryStringParameters') or {}
        
        # Parse body if present
        body = {}
        if event.get('body'):
            try:
                body = json.loads(event['body'])
            except json.JSONDecodeError:
                return {
                    'statusCode': 400,
                    'headers': {
                        'Content-Type': 'application/json',
                        'Access-Control-Allow-Origin': '*',
                        'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token',
                        'Access-Control-Allow-Methods': 'GET,POST,PUT,DELETE,OPTIONS'
                    },
                    'body': json.dumps({'error': 'Invalid JSON in request body'})
                }
        
        # Initialize API handler
        review_api = ReviewAPI()
        
        # Route requests
        if http_method == 'POST' and '/reviews' in path:
            if 'helpful' in path:
                # POST /reviews/{reviewId}/helpful
                result = review_api.vote_helpful(body)
            else:
                # POST /reviews
                result = review_api.create_review(body)
        elif http_method == 'GET' and '/reviews' in path:
            # GET /reviews
            result = review_api.get_reviews(query_params)
        else:
            result = {
                'statusCode': 404,
                'body': json.dumps({'error': 'Endpoint not found'})
            }
        
        # Add CORS headers
        result['headers'] = {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token',
            'Access-Control-Allow-Methods': 'GET,POST,PUT,DELETE,OPTIONS'
        }
        
        return result
        
    except Exception as e:
        logger.error(f"Unhandled error in lambda_handler: {str(e)}")
        return {
            'statusCode': 500,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token',
                'Access-Control-Allow-Methods': 'GET,POST,PUT,DELETE,OPTIONS'
            },
            'body': json.dumps({
                'error': 'Internal server error',
                'message': str(e)
            })
        }