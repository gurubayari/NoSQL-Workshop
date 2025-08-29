"""
Review Analytics Lambda Function for AWS NoSQL Workshop
Handles AI-powered review insights, sentiment analysis, and product recommendations
"""
import json
import logging
import boto3
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any
from botocore.exceptions import ClientError
import uuid
from collections import defaultdict, Counter
import statistics

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

# Initialize Bedrock client for AI analysis
bedrock_client = boto3.client('bedrock-runtime', region_name=config.AWS_REGION)

class ReviewAnalytics:
    """Review Analytics handler class"""
    
    def __init__(self):
        self.reviews_collection = get_documentdb_collection('reviews')
        self.products_collection = get_documentdb_collection('products')
        self.users_table = get_dynamodb_table(config.USERS_TABLE)
    
    def get_product_review_insights(self, query_params: Dict) -> Dict:
        """Get AI-powered insights for a specific product's reviews"""
        try:
            product_id = query_params.get('productId')
            if not product_id:
                return {
                    'statusCode': 400,
                    'body': json.dumps({
                        'error': 'Missing required parameter: productId'
                    })
                }
            
            # Check cache first
            cache_key = get_cache_key('product_insights', product_id)
            cached_result = cache_get(cache_key)
            if cached_result:
                return {
                    'statusCode': 200,
                    'body': cached_result
                }
            
            # Get all approved reviews for the product
            reviews = list(self.reviews_collection.find({
                'productId': product_id,
                'isApproved': True
            }))
            
            if not reviews:
                return {
                    'statusCode': 404,
                    'body': json.dumps({
                        'error': 'No reviews found for this product'
                    })
                }
            
            # Generate comprehensive insights
            insights = self._generate_product_insights(reviews, product_id)
            
            response_body = json.dumps(insights)
            
            # Cache the result for 1 hour
            cache_set(cache_key, response_body, ttl=3600)
            
            return {
                'statusCode': 200,
                'body': response_body
            }
            
        except Exception as e:
            logger.error(f"Error getting product review insights: {str(e)}")
            return {
                'statusCode': 500,
                'body': json.dumps({
                    'error': 'Internal server error',
                    'message': str(e)
                })
            }
    
    def search_reviews_semantic(self, event_body: Dict) -> Dict:
        """Perform semantic search across reviews using vector search"""
        try:
            query = event_body.get('query', '').strip()
            product_ids = event_body.get('productIds', [])
            min_rating = event_body.get('minRating', 1)
            max_results = min(event_body.get('maxResults', 20), 100)
            
            if not query:
                return {
                    'statusCode': 400,
                    'body': json.dumps({
                        'error': 'Missing required field: query'
                    })
                }
            
            # Generate embedding for the search query
            query_embedding = self._generate_embedding(query)
            if not query_embedding:
                return {
                    'statusCode': 500,
                    'body': json.dumps({
                        'error': 'Failed to generate query embedding'
                    })
                }
            
            # Build search filter
            search_filter = {
                'isApproved': True,
                'rating': {'$gte': min_rating}
            }
            
            if product_ids:
                search_filter['productId'] = {'$in': product_ids}
            
            # Perform vector search using DocumentDB
            pipeline = [
                {
                    '$vectorSearch': {
                        'index': 'review_vector_index',
                        'path': 'contentEmbedding',
                        'queryVector': query_embedding,
                        'numCandidates': max_results * 3,
                        'limit': max_results,
                        'filter': search_filter
                    }
                },
                {
                    '$project': {
                        'reviewId': 1,
                        'userId': 1,
                        'productId': 1,
                        'rating': 1,
                        'title': 1,
                        'content': 1,
                        'isVerifiedPurchase': 1,
                        'helpfulCount': 1,
                        'sentiment': 1,
                        'createdAt': 1,
                        'score': {'$meta': 'vectorSearchScore'}
                    }
                }
            ]
            
            # Execute vector search
            search_results = list(self.reviews_collection.aggregate(pipeline))
            
            # Format results
            formatted_results = []
            for result in search_results:
                formatted_result = {
                    'reviewId': result['reviewId'],
                    'userId': result['userId'],
                    'productId': result['productId'],
                    'rating': result['rating'],
                    'title': result['title'],
                    'content': result['content'],
                    'isVerifiedPurchase': result['isVerifiedPurchase'],
                    'helpfulCount': result['helpfulCount'],
                    'sentiment': result.get('sentiment', {}),
                    'createdAt': result['createdAt'].isoformat(),
                    'relevanceScore': result.get('score', 0.0)
                }
                formatted_results.append(formatted_result)
            
            # Generate AI summary of search results
            search_summary = self._generate_search_summary(query, formatted_results)
            
            response_data = {
                'query': query,
                'totalResults': len(formatted_results),
                'results': formatted_results,
                'summary': search_summary
            }
            
            return {
                'statusCode': 200,
                'body': json.dumps(response_data)
            }
            
        except Exception as e:
            logger.error(f"Error in semantic review search: {str(e)}")
            return {
                'statusCode': 500,
                'body': json.dumps({
                    'error': 'Internal server error',
                    'message': str(e)
                })
            }
    
    def get_product_recommendations(self, query_params: Dict) -> Dict:
        """Get AI-powered product recommendations based on review analysis"""
        try:
            user_id = query_params.get('userId')
            category = query_params.get('category')
            min_rating = float(query_params.get('minRating', '4.0'))
            max_results = min(int(query_params.get('maxResults', '10')), 20)
            
            # Check cache
            cache_key = get_cache_key('product_recommendations', f"{user_id}_{category}_{min_rating}_{max_results}")
            cached_result = cache_get(cache_key)
            if cached_result:
                return {
                    'statusCode': 200,
                    'body': cached_result
                }
            
            # Get user's review history for personalization
            user_reviews = []
            if user_id:
                user_reviews = list(self.reviews_collection.find({
                    'userId': user_id,
                    'isApproved': True
                }))
            
            # Build product filter
            product_filter = {}
            if category:
                product_filter['category'] = category
            
            # Get products with high-rated reviews
            pipeline = [
                {'$match': {'isApproved': True, 'rating': {'$gte': min_rating}}},
                {'$group': {
                    '_id': '$productId',
                    'avgRating': {'$avg': '$rating'},
                    'reviewCount': {'$sum': 1},
                    'positiveReviews': {
                        '$sum': {'$cond': [{'$gte': ['$rating', 4]}, 1, 0]}
                    },
                    'recentReviews': {
                        '$push': {
                            '$cond': [
                                {'$gte': ['$createdAt', datetime.now(timezone.utc) - timedelta(days=30)]},
                                {
                                    'content': '$content',
                                    'rating': '$rating',
                                    'sentiment': '$sentiment'
                                },
                                None
                            ]
                        }
                    }
                }},
                {'$match': {
                    'reviewCount': {'$gte': 3},  # At least 3 reviews
                    'avgRating': {'$gte': min_rating}
                }},
                {'$sort': {'avgRating': -1, 'reviewCount': -1}},
                {'$limit': max_results * 2}  # Get more candidates for filtering
            ]
            
            review_aggregation = list(self.reviews_collection.aggregate(pipeline))
            
            if not review_aggregation:
                return {
                    'statusCode': 200,
                    'body': json.dumps({
                        'recommendations': [],
                        'message': 'No products found matching criteria'
                    })
                }
            
            # Get product details
            product_ids = [item['_id'] for item in review_aggregation]
            products = list(self.products_collection.find({
                'productId': {'$in': product_ids},
                **product_filter
            }))
            
            # Create product lookup
            product_lookup = {p['productId']: p for p in products}
            
            # Generate personalized recommendations
            recommendations = self._generate_personalized_recommendations(
                review_aggregation, 
                product_lookup, 
                user_reviews, 
                max_results
            )
            
            response_data = {
                'recommendations': recommendations,
                'totalFound': len(recommendations),
                'criteria': {
                    'minRating': min_rating,
                    'category': category,
                    'personalized': bool(user_id)
                }
            }
            
            response_body = json.dumps(response_data)
            
            # Cache for 30 minutes
            cache_set(cache_key, response_body, ttl=1800)
            
            return {
                'statusCode': 200,
                'body': response_body
            }
            
        except Exception as e:
            logger.error(f"Error getting product recommendations: {str(e)}")
            return {
                'statusCode': 500,
                'body': json.dumps({
                    'error': 'Internal server error',
                    'message': str(e)
                })
            }
    
    def analyze_review_trends(self, query_params: Dict) -> Dict:
        """Analyze review trends and patterns"""
        try:
            product_id = query_params.get('productId')
            category = query_params.get('category')
            days = int(query_params.get('days', '30'))
            
            # Build filter
            date_filter = {
                'createdAt': {'$gte': datetime.now(timezone.utc) - timedelta(days=days)},
                'isApproved': True
            }
            
            if product_id:
                date_filter['productId'] = product_id
            elif category:
                # Get products in category first
                products = list(self.products_collection.find({'category': category}))
                product_ids = [p['productId'] for p in products]
                date_filter['productId'] = {'$in': product_ids}
            
            # Aggregate review trends
            pipeline = [
                {'$match': date_filter},
                {'$group': {
                    '_id': {
                        'date': {'$dateToString': {'format': '%Y-%m-%d', 'date': '$createdAt'}},
                        'rating': '$rating'
                    },
                    'count': {'$sum': 1},
                    'avgSentiment': {'$avg': '$sentiment.score'}
                }},
                {'$sort': {'_id.date': 1}}
            ]
            
            trend_data = list(self.reviews_collection.aggregate(pipeline))
            
            # Process trend data
            trends = self._process_trend_data(trend_data)
            
            # Get overall statistics
            overall_stats = self._get_overall_stats(date_filter)
            
            response_data = {
                'trends': trends,
                'statistics': overall_stats,
                'period': {
                    'days': days,
                    'startDate': (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(),
                    'endDate': datetime.now(timezone.utc).isoformat()
                }
            }
            
            return {
                'statusCode': 200,
                'body': json.dumps(response_data)
            }
            
        except Exception as e:
            logger.error(f"Error analyzing review trends: {str(e)}")
            return {
                'statusCode': 500,
                'body': json.dumps({
                    'error': 'Internal server error',
                    'message': str(e)
                })
            }
    
    def _generate_product_insights(self, reviews: List[Dict], product_id: str) -> Dict:
        """Generate comprehensive insights for a product based on its reviews"""
        try:
            # Basic statistics
            total_reviews = len(reviews)
            ratings = [r['rating'] for r in reviews]
            avg_rating = statistics.mean(ratings)
            
            # Sentiment analysis
            sentiments = [r.get('sentiment', {}).get('score', 0) for r in reviews]
            avg_sentiment = statistics.mean(sentiments) if sentiments else 0
            
            # Aspect analysis
            aspect_scores = defaultdict(list)
            for review in reviews:
                aspects = review.get('sentiment', {}).get('aspects', {})
                for aspect, score in aspects.items():
                    aspect_scores[aspect].append(score)
            
            aspect_averages = {
                aspect: statistics.mean(scores) 
                for aspect, scores in aspect_scores.items()
            }
            
            # Common themes using AI
            review_texts = [r['content'] for r in reviews[-20:]]  # Last 20 reviews
            themes = self._extract_common_themes(review_texts)
            
            # Helpfulness analysis
            helpful_reviews = [r for r in reviews if r.get('helpfulCount', 0) > 0]
            most_helpful = sorted(helpful_reviews, key=lambda x: x.get('helpfulCount', 0), reverse=True)[:3]
            
            # Recent trends (last 30 days)
            recent_date = datetime.now(timezone.utc) - timedelta(days=30)
            recent_reviews = [r for r in reviews if r.get('createdAt', datetime.min.replace(tzinfo=timezone.utc)) > recent_date]
            
            recent_trend = 'stable'
            if len(recent_reviews) >= 5:
                recent_ratings = [r['rating'] for r in recent_reviews]
                recent_avg = statistics.mean(recent_ratings)
                if recent_avg > avg_rating + 0.3:
                    recent_trend = 'improving'
                elif recent_avg < avg_rating - 0.3:
                    recent_trend = 'declining'
            
            # Verified purchase analysis
            verified_reviews = [r for r in reviews if r.get('isVerifiedPurchase', False)]
            verified_percentage = (len(verified_reviews) / total_reviews) * 100 if total_reviews > 0 else 0
            
            return {
                'productId': product_id,
                'summary': {
                    'totalReviews': total_reviews,
                    'averageRating': round(avg_rating, 2),
                    'averageSentiment': round(avg_sentiment, 2),
                    'verifiedPurchasePercentage': round(verified_percentage, 1),
                    'recentTrend': recent_trend
                },
                'aspectScores': {
                    aspect: round(score, 2) 
                    for aspect, score in aspect_averages.items()
                },
                'commonThemes': themes,
                'mostHelpfulReviews': [
                    {
                        'reviewId': r['reviewId'],
                        'title': r['title'],
                        'content': r['content'][:200] + '...' if len(r['content']) > 200 else r['content'],
                        'rating': r['rating'],
                        'helpfulCount': r.get('helpfulCount', 0)
                    }
                    for r in most_helpful
                ],
                'ratingDistribution': {
                    str(i): ratings.count(i) for i in range(1, 6)
                },
                'generatedAt': datetime.now(timezone.utc).isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error generating product insights: {str(e)}")
            return {
                'productId': product_id,
                'error': 'Failed to generate insights',
                'summary': {
                    'totalReviews': len(reviews),
                    'averageRating': statistics.mean([r['rating'] for r in reviews]) if reviews else 0
                }
            }
    
    def _generate_embedding(self, text: str) -> Optional[List[float]]:
        """Generate text embedding using Bedrock"""
        try:
            response = bedrock_client.invoke_model(
                modelId=config.BEDROCK_EMBEDDING_MODEL_ID,
                body=json.dumps({
                    'inputText': text
                })
            )
            
            response_body = json.loads(response['body'].read())
            return response_body.get('embedding')
            
        except Exception as e:
            logger.error(f"Error generating embedding: {str(e)}")
            return None
    
    def _generate_search_summary(self, query: str, results: List[Dict]) -> Dict:
        """Generate AI summary of search results"""
        try:
            if not results:
                return {
                    'message': 'No reviews found matching your search criteria.',
                    'insights': []
                }
            
            # Prepare summary data
            avg_rating = statistics.mean([r['rating'] for r in results])
            sentiment_scores = [r.get('sentiment', {}).get('score', 0) for r in results]
            avg_sentiment = statistics.mean(sentiment_scores) if sentiment_scores else 0
            
            # Get top review snippets
            top_reviews = sorted(results, key=lambda x: x.get('relevanceScore', 0), reverse=True)[:3]
            review_snippets = [r['content'][:100] + '...' for r in top_reviews]
            
            # Generate AI summary using Bedrock
            prompt = f"""
            Analyze these product review search results for the query: "{query}"
            
            Results summary:
            - Total reviews found: {len(results)}
            - Average rating: {avg_rating:.1f}/5
            - Average sentiment: {avg_sentiment:.2f}
            
            Top review snippets:
            {chr(10).join(f"- {snippet}" for snippet in review_snippets)}
            
            Provide a brief summary of what customers are saying about "{query}" based on these reviews.
            Focus on key insights and common themes. Keep it concise (2-3 sentences).
            """
            
            response = bedrock_client.invoke_model(
                modelId=config.BEDROCK_MODEL_ID,
                body=json.dumps({
                    "anthropic_version": "bedrock-2023-05-31",
                    "max_tokens": 200,
                    "messages": [
                        {
                            "role": "user",
                            "content": prompt
                        }
                    ]
                })
            )
            
            response_body = json.loads(response['body'].read())
            ai_summary = response_body['content'][0]['text']
            
            return {
                'message': ai_summary,
                'statistics': {
                    'totalResults': len(results),
                    'averageRating': round(avg_rating, 1),
                    'averageSentiment': round(avg_sentiment, 2),
                    'sentimentLabel': 'positive' if avg_sentiment > 0.1 else 'negative' if avg_sentiment < -0.1 else 'neutral'
                }
            }
            
        except Exception as e:
            logger.error(f"Error generating search summary: {str(e)}")
            return {
                'message': f'Found {len(results)} reviews matching your search for "{query}".',
                'statistics': {
                    'totalResults': len(results),
                    'averageRating': round(statistics.mean([r['rating'] for r in results]), 1) if results else 0
                }
            }
    
    def _generate_personalized_recommendations(self, review_data: List[Dict], product_lookup: Dict, user_reviews: List[Dict], max_results: int) -> List[Dict]:
        """Generate personalized product recommendations"""
        try:
            recommendations = []
            
            # Analyze user preferences from their reviews
            user_preferences = self._analyze_user_preferences(user_reviews)
            
            for item in review_data[:max_results]:
                product_id = item['_id']
                product = product_lookup.get(product_id)
                
                if not product:
                    continue
                
                # Calculate recommendation score
                base_score = (item['avgRating'] * 0.6) + (min(item['reviewCount'] / 10, 1.0) * 0.4)
                
                # Adjust score based on user preferences
                personalization_boost = self._calculate_personalization_boost(
                    product, item, user_preferences
                )
                
                final_score = base_score + personalization_boost
                
                # Get recent positive review highlights
                recent_highlights = self._get_review_highlights(item.get('recentReviews', []))
                
                recommendation = {
                    'productId': product_id,
                    'title': product.get('title', 'Unknown Product'),
                    'category': product.get('category', 'Unknown'),
                    'price': product.get('price', 0),
                    'imageUrl': product.get('imageUrl', ''),
                    'averageRating': round(item['avgRating'], 1),
                    'reviewCount': item['reviewCount'],
                    'recommendationScore': round(final_score, 2),
                    'highlights': recent_highlights,
                    'reasonForRecommendation': self._generate_recommendation_reason(
                        product, item, user_preferences
                    )
                }
                
                recommendations.append(recommendation)
            
            # Sort by recommendation score
            recommendations.sort(key=lambda x: x['recommendationScore'], reverse=True)
            
            return recommendations
            
        except Exception as e:
            logger.error(f"Error generating personalized recommendations: {str(e)}")
            return []
    
    def _analyze_user_preferences(self, user_reviews: List[Dict]) -> Dict:
        """Analyze user preferences from their review history"""
        if not user_reviews:
            return {}
        
        preferences = {
            'preferred_categories': [],
            'rating_tendency': 0,
            'sentiment_tendency': 0,
            'aspect_preferences': {}
        }
        
        try:
            # Analyze categories
            categories = [r.get('productCategory', '') for r in user_reviews if r.get('productCategory')]
            if categories:
                category_counts = Counter(categories)
                preferences['preferred_categories'] = [cat for cat, _ in category_counts.most_common(3)]
            
            # Analyze rating tendency
            ratings = [r['rating'] for r in user_reviews]
            preferences['rating_tendency'] = statistics.mean(ratings) if ratings else 0
            
            # Analyze sentiment tendency
            sentiments = [r.get('sentiment', {}).get('score', 0) for r in user_reviews]
            preferences['sentiment_tendency'] = statistics.mean(sentiments) if sentiments else 0
            
            # Analyze aspect preferences
            aspect_scores = defaultdict(list)
            for review in user_reviews:
                aspects = review.get('sentiment', {}).get('aspects', {})
                for aspect, score in aspects.items():
                    aspect_scores[aspect].append(score)
            
            preferences['aspect_preferences'] = {
                aspect: statistics.mean(scores)
                for aspect, scores in aspect_scores.items()
            }
            
        except Exception as e:
            logger.error(f"Error analyzing user preferences: {str(e)}")
        
        return preferences
    
    def _calculate_personalization_boost(self, product: Dict, review_data: Dict, user_preferences: Dict) -> float:
        """Calculate personalization boost for recommendation score"""
        boost = 0.0
        
        try:
            # Category preference boost
            product_category = product.get('category', '')
            if product_category in user_preferences.get('preferred_categories', []):
                boost += 0.2
            
            # Rating alignment boost
            user_rating_tendency = user_preferences.get('rating_tendency', 0)
            product_avg_rating = review_data['avgRating']
            rating_diff = abs(user_rating_tendency - product_avg_rating)
            if rating_diff < 0.5:
                boost += 0.1
            
            # Sentiment alignment boost
            user_sentiment_tendency = user_preferences.get('sentiment_tendency', 0)
            recent_reviews = review_data.get('recentReviews', [])
            if recent_reviews:
                recent_sentiments = [r.get('sentiment', {}).get('score', 0) for r in recent_reviews if r]
                if recent_sentiments:
                    avg_recent_sentiment = statistics.mean(recent_sentiments)
                    sentiment_diff = abs(user_sentiment_tendency - avg_recent_sentiment)
                    if sentiment_diff < 0.3:
                        boost += 0.1
            
        except Exception as e:
            logger.error(f"Error calculating personalization boost: {str(e)}")
        
        return boost
    
    def _get_review_highlights(self, recent_reviews: List[Dict]) -> List[str]:
        """Extract highlights from recent reviews"""
        highlights = []
        
        try:
            positive_reviews = [r for r in recent_reviews if r and r.get('rating', 0) >= 4]
            
            for review in positive_reviews[:3]:
                content = review.get('content', '')
                if len(content) > 50:
                    # Extract first sentence or first 100 characters
                    sentences = content.split('.')
                    highlight = sentences[0] if sentences else content[:100]
                    if len(highlight) > 20:
                        highlights.append(highlight.strip() + ('.' if not highlight.endswith('.') else ''))
            
        except Exception as e:
            logger.error(f"Error extracting review highlights: {str(e)}")
        
        return highlights[:2]  # Return max 2 highlights
    
    def _generate_recommendation_reason(self, product: Dict, review_data: Dict, user_preferences: Dict) -> str:
        """Generate reason for recommendation"""
        try:
            reasons = []
            
            # High rating reason
            if review_data['avgRating'] >= 4.5:
                reasons.append(f"Highly rated ({review_data['avgRating']:.1f}/5)")
            
            # Popular reason
            if review_data['reviewCount'] >= 20:
                reasons.append(f"Popular choice ({review_data['reviewCount']} reviews)")
            
            # Category preference reason
            product_category = product.get('category', '')
            if product_category in user_preferences.get('preferred_categories', []):
                reasons.append(f"Matches your interest in {product_category}")
            
            # Default reason
            if not reasons:
                reasons.append("Great customer feedback")
            
            return ", ".join(reasons[:2])  # Max 2 reasons
            
        except Exception as e:
            logger.error(f"Error generating recommendation reason: {str(e)}")
            return "Recommended based on reviews"
    
    def _extract_common_themes(self, review_texts: List[str]) -> List[Dict]:
        """Extract common themes from reviews using AI"""
        try:
            if not review_texts:
                return []
            
            # Combine recent reviews for analysis
            combined_text = " ".join(review_texts[:10])  # Use first 10 reviews
            
            prompt = f"""
            Analyze these product reviews and identify the top 3 common themes or topics that customers frequently mention.
            
            Reviews: {combined_text[:2000]}
            
            For each theme, provide:
            1. Theme name (2-3 words)
            2. Brief description
            3. Sentiment (positive/negative/neutral)
            
            Respond in JSON format:
            [
                {{"theme": "Audio Quality", "description": "Sound clarity and bass", "sentiment": "positive"}},
                {{"theme": "Battery Life", "description": "Long-lasting power", "sentiment": "positive"}},
                {{"theme": "Comfort", "description": "Fit and wearability", "sentiment": "neutral"}}
            ]
            """
            
            response = bedrock_client.invoke_model(
                modelId=config.BEDROCK_MODEL_ID,
                body=json.dumps({
                    "anthropic_version": "bedrock-2023-05-31",
                    "max_tokens": 300,
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
                themes = json.loads(ai_response)
                return themes if isinstance(themes, list) else []
            except json.JSONDecodeError:
                logger.warning("Failed to parse AI themes response")
                return []
                
        except Exception as e:
            logger.error(f"Error extracting common themes: {str(e)}")
            return []
    
    def _process_trend_data(self, trend_data: List[Dict]) -> Dict:
        """Process trend data for visualization"""
        try:
            daily_stats = defaultdict(lambda: {'total': 0, 'ratings': [], 'sentiment': []})
            
            for item in trend_data:
                date = item['_id']['date']
                rating = item['_id']['rating']
                count = item['count']
                sentiment = item.get('avgSentiment', 0)
                
                daily_stats[date]['total'] += count
                daily_stats[date]['ratings'].extend([rating] * count)
                daily_stats[date]['sentiment'].append(sentiment)
            
            # Calculate daily averages
            processed_trends = []
            for date, stats in sorted(daily_stats.items()):
                avg_rating = statistics.mean(stats['ratings']) if stats['ratings'] else 0
                avg_sentiment = statistics.mean(stats['sentiment']) if stats['sentiment'] else 0
                
                processed_trends.append({
                    'date': date,
                    'totalReviews': stats['total'],
                    'averageRating': round(avg_rating, 2),
                    'averageSentiment': round(avg_sentiment, 2)
                })
            
            return {
                'daily': processed_trends,
                'summary': {
                    'totalDays': len(processed_trends),
                    'totalReviews': sum(day['totalReviews'] for day in processed_trends),
                    'overallAvgRating': round(statistics.mean([day['averageRating'] for day in processed_trends]), 2) if processed_trends else 0
                }
            }
            
        except Exception as e:
            logger.error(f"Error processing trend data: {str(e)}")
            return {'daily': [], 'summary': {}}
    
    def _get_overall_stats(self, date_filter: Dict) -> Dict:
        """Get overall statistics for the filtered period"""
        try:
            pipeline = [
                {'$match': date_filter},
                {'$group': {
                    '_id': None,
                    'totalReviews': {'$sum': 1},
                    'avgRating': {'$avg': '$rating'},
                    'avgSentiment': {'$avg': '$sentiment.score'},
                    'ratingDistribution': {
                        '$push': '$rating'
                    }
                }}
            ]
            
            result = list(self.reviews_collection.aggregate(pipeline))
            
            if not result:
                return {}
            
            stats = result[0]
            ratings = stats.get('ratingDistribution', [])
            
            return {
                'totalReviews': stats.get('totalReviews', 0),
                'averageRating': round(stats.get('avgRating', 0), 2),
                'averageSentiment': round(stats.get('avgSentiment', 0), 2),
                'ratingDistribution': {
                    str(i): ratings.count(i) for i in range(1, 6)
                }
            }
            
        except Exception as e:
            logger.error(f"Error getting overall stats: {str(e)}")
            return {}

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
        
        # Initialize analytics handler
        analytics = ReviewAnalytics()
        
        # Route requests
        if http_method == 'GET' and '/analytics/reviews/insights' in path:
            # GET /analytics/reviews/insights?productId=xxx
            result = analytics.get_product_review_insights(query_params)
        elif http_method == 'POST' and '/analytics/reviews/search' in path:
            # POST /analytics/reviews/search
            result = analytics.search_reviews_semantic(body)
        elif http_method == 'GET' and '/analytics/products/recommendations' in path:
            # GET /analytics/products/recommendations
            result = analytics.get_product_recommendations(query_params)
        elif http_method == 'GET' and '/analytics/reviews/trends' in path:
            # GET /analytics/reviews/trends
            result = analytics.analyze_review_trends(query_params)
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