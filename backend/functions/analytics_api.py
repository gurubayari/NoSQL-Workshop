"""
Analytics API Lambda Function for AWS NoSQL Workshop
Implements semantic review search, sentiment analysis, and AI-powered product insights
"""
import json
import logging
import boto3
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
import uuid
import os
import sys
import statistics
from collections import defaultdict, Counter

# Add the shared directory to the path
sys.path.append('/opt/python')
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'shared'))

try:
    from shared.config import config
    from shared.database import (
        get_dynamodb_table, get_documentdb_collection, 
        cache_get, cache_set, cache_delete, get_cache_key, db
    )
    from shared.embeddings import embedding_generator
    from shared.vector_search import vector_search_manager
except ImportError:
    from config import config
    from database import (
        get_dynamodb_table, get_documentdb_collection,
        cache_get, cache_set, cache_delete, get_cache_key, db
    )
    from embeddings import embedding_generator
    from vector_search import vector_search_manager

# Configure logging
logging.basicConfig(level=getattr(logging, config.LOG_LEVEL))
logger = logging.getLogger(__name__)

class AnalyticsService:
    """Service class for analytics functionality with semantic search"""
    
    def __init__(self):
        self.bedrock_client = boto3.client('bedrock-runtime', region_name=config.AWS_REGION)
        self.reviews_collection = get_documentdb_collection('reviews')
        self.products_collection = get_documentdb_collection('products')
        self.knowledge_base_collection = get_documentdb_collection('knowledge_base')
        self.model_id = config.BEDROCK_MODEL_ID
        self.cache_ttl = config.CACHE_TTL_SECONDS
        
        logger.info(f"Initialized AnalyticsService with model: {self.model_id}")
    
    def semantic_review_search(self, query: str, filters: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Perform semantic search across product reviews using DocumentDB vector search
        
        Args:
            query: Natural language search query
            filters: Optional filters (product_ids, categories, min_rating, etc.)
            
        Returns:
            Search results with AI-powered insights
        """
        try:
            # Input validation
            if not query or not query.strip():
                return {
                    'success': False,
                    'error': 'Query cannot be empty',
                    'results': []
                }
            
            query = query.strip()
            filters = filters or {}
            
            # Check cache first
            cache_key = get_cache_key("semantic_search", f"{query}_{hash(str(filters))}")
            cached_result = cache_get(cache_key)
            if cached_result:
                logger.info("Returning cached semantic search results")
                return json.loads(cached_result)
            
            # Generate embedding for the query
            embedding_result = embedding_generator.generate_embedding(query)
            
            if not embedding_result.success:
                logger.error(f"Failed to generate embedding for query: {query}")
                return {
                    'success': False,
                    'error': 'Failed to process search query',
                    'results': []
                }
            
            # Perform vector search on reviews
            search_results = vector_search_manager.vector_search_reviews(
                query_embedding=embedding_result.embedding,
                limit=filters.get('limit', 20),
                min_score=filters.get('min_score', 0.7)
            )
            
            # Apply additional filters if specified
            if filters.get('product_ids'):
                search_results = [r for r in search_results if r.get('product_id') in filters['product_ids']]
            
            if filters.get('min_rating'):
                search_results = [r for r in search_results if r.get('rating', 0) >= filters['min_rating']]
            
            if filters.get('categories'):
                # Get product categories for filtering
                product_ids = [r.get('product_id') for r in search_results]
                products = list(self.products_collection.find(
                    {'product_id': {'$in': product_ids}},
                    {'product_id': 1, 'category': 1}
                ))
                product_categories = {p['product_id']: p.get('category') for p in products}
                
                search_results = [
                    r for r in search_results 
                    if product_categories.get(r.get('product_id')) in filters['categories']
                ]
            
            # Enhance results with product information
            enhanced_results = self._enhance_search_results(search_results)
            
            # Generate AI-powered insights
            insights = self._generate_search_insights(query, enhanced_results)
            
            # Prepare response
            response = {
                'success': True,
                'query': query,
                'total_results': len(enhanced_results),
                'results': enhanced_results,
                'insights': insights,
                'filters_applied': filters,
                'timestamp': datetime.utcnow().isoformat()
            }
            
            # Cache the results
            cache_set(cache_key, json.dumps(response), self.cache_ttl)
            
            logger.info(f"Semantic search completed: {len(enhanced_results)} results for query '{query}'")
            return response
            
        except Exception as e:
            logger.error(f"Semantic review search failed: {e}")
            return {
                'success': False,
                'error': 'Internal server error during search',
                'results': []
            }
    
    def get_review_sentiment_analysis(self, product_id: str) -> Dict[str, Any]:
        """
        Get comprehensive sentiment analysis for a product's reviews using Bedrock
        
        Args:
            product_id: Product identifier
            
        Returns:
            Detailed sentiment analysis and insights
        """
        try:
            # Check cache first
            cache_key = get_cache_key("sentiment_analysis", product_id)
            cached_result = cache_get(cache_key)
            if cached_result:
                return json.loads(cached_result)
            
            # Get all reviews for the product
            reviews = list(self.reviews_collection.find({
                'product_id': product_id
            }).sort('created_at', -1))
            
            if not reviews:
                return {
                    'success': False,
                    'error': 'No reviews found for this product',
                    'product_id': product_id
                }
            
            # Analyze sentiment using existing data and Bedrock for deeper insights
            sentiment_analysis = self._analyze_review_sentiments(reviews)
            
            # Generate aspect-based insights
            aspect_insights = self._generate_aspect_insights(reviews)
            
            # Get trending sentiment over time
            sentiment_trends = self._analyze_sentiment_trends(reviews)
            
            # Generate AI summary
            ai_summary = self._generate_sentiment_summary(reviews, sentiment_analysis)
            
            response = {
                'success': True,
                'product_id': product_id,
                'total_reviews': len(reviews),
                'sentiment_analysis': sentiment_analysis,
                'aspect_insights': aspect_insights,
                'sentiment_trends': sentiment_trends,
                'ai_summary': ai_summary,
                'generated_at': datetime.utcnow().isoformat()
            }
            
            # Cache for 1 hour
            cache_set(cache_key, json.dumps(response), 3600)
            
            return response
            
        except Exception as e:
            logger.error(f"Sentiment analysis failed for product {product_id}: {e}")
            return {
                'success': False,
                'error': 'Failed to analyze sentiment',
                'product_id': product_id
            }
    
    def get_product_recommendations_by_reviews(self, query: str, user_preferences: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Generate product recommendations based on review analysis and user preferences
        
        Args:
            query: Natural language query describing what the user is looking for
            user_preferences: Optional user preference data
            
        Returns:
            AI-powered product recommendations
        """
        try:
            # Check cache
            cache_key = get_cache_key("review_recommendations", f"{query}_{hash(str(user_preferences))}")
            cached_result = cache_get(cache_key)
            if cached_result:
                return json.loads(cached_result)
            
            # First, search reviews to understand what users are saying about the query
            review_search = self.semantic_review_search(query, {'limit': 50, 'min_score': 0.6})
            
            if not review_search.get('success') or not review_search.get('results'):
                return {
                    'success': False,
                    'error': 'No relevant reviews found for the query',
                    'recommendations': []
                }
            
            # Extract product IDs from review results
            product_ids = list(set([r['product_id'] for r in review_search['results']]))
            
            # Get product details
            products = list(self.products_collection.find({
                'product_id': {'$in': product_ids}
            }))
            
            # Analyze reviews for each product to generate recommendations
            recommendations = self._generate_review_based_recommendations(
                products, review_search['results'], query, user_preferences
            )
            
            # Generate AI explanation for recommendations
            recommendation_explanation = self._generate_recommendation_explanation(
                query, recommendations[:5]  # Top 5 for explanation
            )
            
            response = {
                'success': True,
                'query': query,
                'total_recommendations': len(recommendations),
                'recommendations': recommendations,
                'explanation': recommendation_explanation,
                'based_on_reviews': len(review_search['results']),
                'generated_at': datetime.utcnow().isoformat()
            }
            
            # Cache for 30 minutes
            cache_set(cache_key, json.dumps(response), 1800)
            
            return response
            
        except Exception as e:
            logger.error(f"Review-based recommendations failed: {e}")
            return {
                'success': False,
                'error': 'Failed to generate recommendations',
                'recommendations': []
            }
    
    def get_review_insights_by_aspect(self, aspect: str, category: Optional[str] = None) -> Dict[str, Any]:
        """
        Get insights about a specific aspect (e.g., "audio quality", "battery life") across products
        
        Args:
            aspect: The aspect to analyze (e.g., "audio quality", "comfort", "value")
            category: Optional product category filter
            
        Returns:
            Aspect-specific insights across products
        """
        try:
            # Check cache
            cache_key = get_cache_key("aspect_insights", f"{aspect}_{category}")
            cached_result = cache_get(cache_key)
            if cached_result:
                return json.loads(cached_result)
            
            # Search reviews that mention the aspect
            aspect_search = self.semantic_review_search(
                aspect, 
                {'limit': 100, 'min_score': 0.6, 'categories': [category] if category else None}
            )
            
            if not aspect_search.get('success') or not aspect_search.get('results'):
                return {
                    'success': False,
                    'error': f'No reviews found discussing {aspect}',
                    'aspect': aspect
                }
            
            # Group reviews by product
            product_reviews = defaultdict(list)
            for review in aspect_search['results']:
                product_reviews[review['product_id']].append(review)
            
            # Analyze aspect performance for each product
            product_insights = []
            for product_id, reviews in product_reviews.items():
                if len(reviews) >= 2:  # At least 2 reviews mentioning the aspect
                    insight = self._analyze_product_aspect(product_id, aspect, reviews)
                    if insight:
                        product_insights.append(insight)
            
            # Sort by aspect score
            product_insights.sort(key=lambda x: x.get('aspect_score', 0), reverse=True)
            
            # Generate overall insights
            overall_insights = self._generate_aspect_overview(aspect, product_insights)
            
            response = {
                'success': True,
                'aspect': aspect,
                'category': category,
                'total_products_analyzed': len(product_insights),
                'total_reviews_analyzed': len(aspect_search['results']),
                'product_insights': product_insights[:20],  # Top 20 products
                'overall_insights': overall_insights,
                'generated_at': datetime.utcnow().isoformat()
            }
            
            # Cache for 2 hours
            cache_set(cache_key, json.dumps(response), 7200)
            
            return response
            
        except Exception as e:
            logger.error(f"Aspect insights failed for {aspect}: {e}")
            return {
                'success': False,
                'error': 'Failed to analyze aspect',
                'aspect': aspect
            }
    
    def _enhance_search_results(self, search_results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Enhance search results with product information"""
        try:
            if not search_results:
                return []
            
            # Get unique product IDs
            product_ids = list(set([r.get('product_id') for r in search_results if r.get('product_id')]))
            
            # Get product information
            products = list(self.products_collection.find(
                {'product_id': {'$in': product_ids}},
                {
                    'product_id': 1, 'title': 1, 'category': 1, 'price': 1, 
                    'rating': 1, 'image_url': 1, 'review_count': 1
                }
            ))
            
            # Create product lookup
            product_lookup = {p['product_id']: p for p in products}
            
            # Enhance results
            enhanced_results = []
            for result in search_results:
                product_id = result.get('product_id')
                product_info = product_lookup.get(product_id, {})
                
                enhanced_result = {
                    'review_id': result.get('review_id'),
                    'product_id': product_id,
                    'product_title': product_info.get('title', 'Unknown Product'),
                    'product_category': product_info.get('category', 'Unknown'),
                    'product_price': product_info.get('price', 0),
                    'product_rating': product_info.get('rating', 0),
                    'product_image_url': product_info.get('image_url', ''),
                    'review_title': result.get('title', ''),
                    'review_content': result.get('content', ''),
                    'review_rating': result.get('rating', 0),
                    'review_user_name': result.get('user_name', 'Anonymous'),
                    'review_created_at': result.get('created_at'),
                    'review_helpful_count': result.get('helpful_count', 0),
                    'sentiment': result.get('sentiment', {}),
                    'similarity_score': result.get('similarity_score', 0)
                }
                
                enhanced_results.append(enhanced_result)
            
            return enhanced_results
            
        except Exception as e:
            logger.error(f"Failed to enhance search results: {e}")
            return search_results
    
    def _generate_search_insights(self, query: str, results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Generate AI-powered insights from search results"""
        try:
            if not results:
                return {
                    'summary': f'No reviews found matching "{query}"',
                    'key_findings': [],
                    'sentiment_overview': 'neutral'
                }
            
            # Basic statistics
            total_results = len(results)
            avg_rating = statistics.mean([r.get('review_rating', 0) for r in results])
            
            # Sentiment analysis
            sentiment_scores = []
            for result in results:
                sentiment = result.get('sentiment', {})
                if isinstance(sentiment, dict) and 'score' in sentiment:
                    sentiment_scores.append(sentiment['score'])
            
            avg_sentiment = statistics.mean(sentiment_scores) if sentiment_scores else 0
            
            # Product distribution
            product_counts = Counter([r.get('product_title', 'Unknown') for r in results])
            top_products = product_counts.most_common(5)
            
            # Generate AI summary using Bedrock
            ai_summary = self._generate_ai_search_summary(query, results, avg_rating, avg_sentiment)
            
            return {
                'summary': ai_summary,
                'statistics': {
                    'total_results': total_results,
                    'average_rating': round(avg_rating, 1),
                    'average_sentiment': round(avg_sentiment, 2),
                    'sentiment_label': self._get_sentiment_label(avg_sentiment)
                },
                'top_products': [{'product': name, 'mention_count': count} for name, count in top_products],
                'key_findings': self._extract_key_findings(results)
            }
            
        except Exception as e:
            logger.error(f"Failed to generate search insights: {e}")
            return {
                'summary': f'Found {len(results)} reviews related to "{query}"',
                'key_findings': [],
                'sentiment_overview': 'neutral'
            }
    
    def _generate_ai_search_summary(self, query: str, results: List[Dict], avg_rating: float, avg_sentiment: float) -> str:
        """Generate AI summary using Bedrock"""
        try:
            # Prepare context from top results
            top_results = sorted(results, key=lambda x: x.get('similarity_score', 0), reverse=True)[:5]
            review_snippets = []
            
            for result in top_results:
                content = result.get('review_content', '')
                if content:
                    snippet = content[:150] + '...' if len(content) > 150 else content
                    rating = result.get('review_rating', 0)
                    review_snippets.append(f"({rating}/5 stars) {snippet}")
            
            prompt = f"""Based on customer reviews, provide insights about "{query}".

Review Analysis:
- Total reviews analyzed: {len(results)}
- Average rating: {avg_rating:.1f}/5 stars
- Average sentiment: {avg_sentiment:.2f}

Sample reviews:
{chr(10).join(review_snippets)}

Provide a concise summary (2-3 sentences) of what customers are saying about "{query}" based on these reviews. Focus on common themes, satisfaction levels, and key insights."""
            
            response = self.bedrock_client.invoke_model(
                modelId=self.model_id,
                body=json.dumps({
                    "anthropic_version": "bedrock-2023-05-31",
                    "max_tokens": 200,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.3
                }),
                contentType='application/json',
                accept='application/json'
            )
            
            response_body = json.loads(response['body'].read())
            return response_body['content'][0]['text'].strip()
            
        except Exception as e:
            logger.error(f"Failed to generate AI summary: {e}")
            return f"Found {len(results)} customer reviews discussing {query}. Average rating: {avg_rating:.1f}/5 stars."
    
    def _analyze_review_sentiments(self, reviews: List[Dict]) -> Dict[str, Any]:
        """Analyze sentiment distribution and patterns"""
        try:
            sentiment_scores = []
            aspect_sentiments = defaultdict(list)
            
            for review in reviews:
                sentiment = review.get('sentiment', {})
                
                # Overall sentiment
                if isinstance(sentiment, dict) and 'score' in sentiment:
                    sentiment_scores.append(sentiment['score'])
                
                # Aspect sentiments
                aspects = sentiment.get('aspects', {}) if isinstance(sentiment, dict) else {}
                for aspect, score in aspects.items():
                    aspect_sentiments[aspect].append(score)
            
            # Calculate distributions
            positive_count = sum(1 for s in sentiment_scores if s > 0.1)
            negative_count = sum(1 for s in sentiment_scores if s < -0.1)
            neutral_count = len(sentiment_scores) - positive_count - negative_count
            
            return {
                'overall_sentiment': {
                    'average_score': round(statistics.mean(sentiment_scores), 3) if sentiment_scores else 0,
                    'distribution': {
                        'positive': positive_count,
                        'neutral': neutral_count,
                        'negative': negative_count,
                        'total': len(sentiment_scores)
                    }
                },
                'aspect_sentiments': {
                    aspect: {
                        'average_score': round(statistics.mean(scores), 3),
                        'review_count': len(scores)
                    }
                    for aspect, scores in aspect_sentiments.items()
                    if len(scores) >= 3  # Only include aspects with at least 3 mentions
                }
            }
            
        except Exception as e:
            logger.error(f"Failed to analyze sentiments: {e}")
            return {'overall_sentiment': {'average_score': 0, 'distribution': {}}}
    
    def _generate_aspect_insights(self, reviews: List[Dict]) -> Dict[str, Any]:
        """Generate insights about specific product aspects"""
        try:
            aspect_data = defaultdict(lambda: {'scores': [], 'mentions': []})
            
            for review in reviews:
                sentiment = review.get('sentiment', {})
                aspects = sentiment.get('aspects', {}) if isinstance(sentiment, dict) else {}
                
                for aspect, score in aspects.items():
                    aspect_data[aspect]['scores'].append(score)
                    # Extract mention context from review content
                    content = review.get('content', '').lower()
                    if aspect.lower() in content:
                        # Find sentence containing the aspect
                        sentences = content.split('.')
                        for sentence in sentences:
                            if aspect.lower() in sentence:
                                aspect_data[aspect]['mentions'].append(sentence.strip())
                                break
            
            # Generate insights for each aspect
            insights = {}
            for aspect, data in aspect_data.items():
                if len(data['scores']) >= 3:  # At least 3 mentions
                    avg_score = statistics.mean(data['scores'])
                    insights[aspect] = {
                        'average_score': round(avg_score, 3),
                        'mention_count': len(data['scores']),
                        'sentiment_label': self._get_sentiment_label(avg_score),
                        'sample_mentions': data['mentions'][:3]  # Top 3 mentions
                    }
            
            return insights
            
        except Exception as e:
            logger.error(f"Failed to generate aspect insights: {e}")
            return {}
    
    def _analyze_sentiment_trends(self, reviews: List[Dict]) -> Dict[str, Any]:
        """Analyze sentiment trends over time"""
        try:
            # Group reviews by month
            monthly_sentiments = defaultdict(list)
            
            for review in reviews:
                created_at = review.get('created_at')
                if created_at:
                    if isinstance(created_at, str):
                        created_at = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                    
                    month_key = created_at.strftime('%Y-%m')
                    sentiment = review.get('sentiment', {})
                    if isinstance(sentiment, dict) and 'score' in sentiment:
                        monthly_sentiments[month_key].append(sentiment['score'])
            
            # Calculate monthly averages
            trends = []
            for month, scores in sorted(monthly_sentiments.items()):
                if scores:
                    trends.append({
                        'month': month,
                        'average_sentiment': round(statistics.mean(scores), 3),
                        'review_count': len(scores)
                    })
            
            # Determine overall trend
            if len(trends) >= 2:
                recent_avg = statistics.mean([t['average_sentiment'] for t in trends[-3:]])
                older_avg = statistics.mean([t['average_sentiment'] for t in trends[:-3]]) if len(trends) > 3 else trends[0]['average_sentiment']
                
                if recent_avg > older_avg + 0.1:
                    trend_direction = 'improving'
                elif recent_avg < older_avg - 0.1:
                    trend_direction = 'declining'
                else:
                    trend_direction = 'stable'
            else:
                trend_direction = 'insufficient_data'
            
            return {
                'monthly_trends': trends,
                'trend_direction': trend_direction,
                'total_months': len(trends)
            }
            
        except Exception as e:
            logger.error(f"Failed to analyze sentiment trends: {e}")
            return {'monthly_trends': [], 'trend_direction': 'unknown'}
    
    def _generate_sentiment_summary(self, reviews: List[Dict], sentiment_analysis: Dict) -> str:
        """Generate AI-powered sentiment summary"""
        try:
            overall_sentiment = sentiment_analysis.get('overall_sentiment', {})
            avg_score = overall_sentiment.get('average_score', 0)
            distribution = overall_sentiment.get('distribution', {})
            
            # Prepare context for AI
            context = f"""
Product has {len(reviews)} reviews with sentiment analysis:
- Average sentiment score: {avg_score:.2f}
- Positive reviews: {distribution.get('positive', 0)}
- Neutral reviews: {distribution.get('neutral', 0)}
- Negative reviews: {distribution.get('negative', 0)}

Top aspects mentioned:
{json.dumps(sentiment_analysis.get('aspect_sentiments', {}), indent=2)}
"""
            
            prompt = f"""Based on this sentiment analysis of customer reviews, provide a brief summary (2-3 sentences) of the overall customer satisfaction and key sentiment patterns.

{context}

Focus on the main sentiment trends and what customers are most satisfied or dissatisfied with."""
            
            response = self.bedrock_client.invoke_model(
                modelId=self.model_id,
                body=json.dumps({
                    "anthropic_version": "bedrock-2023-05-31",
                    "max_tokens": 150,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.3
                }),
                contentType='application/json',
                accept='application/json'
            )
            
            response_body = json.loads(response['body'].read())
            return response_body['content'][0]['text'].strip()
            
        except Exception as e:
            logger.error(f"Failed to generate sentiment summary: {e}")
            return f"Based on {len(reviews)} reviews, the overall sentiment is {self._get_sentiment_label(sentiment_analysis.get('overall_sentiment', {}).get('average_score', 0))}."
    
    def _generate_review_based_recommendations(self, products: List[Dict], review_results: List[Dict], query: str, user_preferences: Optional[Dict]) -> List[Dict]:
        """Generate product recommendations based on review analysis"""
        try:
            # Group reviews by product
            product_reviews = defaultdict(list)
            for review in review_results:
                product_reviews[review['product_id']].append(review)
            
            recommendations = []
            
            for product in products:
                product_id = product['product_id']
                reviews = product_reviews.get(product_id, [])
                
                if not reviews:
                    continue
                
                # Calculate recommendation score
                avg_similarity = statistics.mean([r.get('similarity_score', 0) for r in reviews])
                avg_rating = statistics.mean([r.get('review_rating', 0) for r in reviews])
                review_count = len(reviews)
                
                # Base score calculation
                base_score = (avg_similarity * 0.4) + (avg_rating / 5.0 * 0.4) + (min(review_count / 10, 1.0) * 0.2)
                
                # Apply user preferences if available
                preference_boost = 0
                if user_preferences:
                    if product.get('category') in user_preferences.get('preferred_categories', []):
                        preference_boost += 0.1
                    
                    if product.get('price', 0) <= user_preferences.get('max_price', float('inf')):
                        preference_boost += 0.05
                
                final_score = base_score + preference_boost
                
                # Extract key review highlights
                highlights = self._extract_review_highlights(reviews, query)
                
                recommendation = {
                    'product_id': product_id,
                    'title': product.get('title', 'Unknown Product'),
                    'category': product.get('category', 'Unknown'),
                    'price': product.get('price', 0),
                    'rating': product.get('rating', 0),
                    'image_url': product.get('image_url', ''),
                    'recommendation_score': round(final_score, 3),
                    'relevant_reviews_count': review_count,
                    'average_similarity': round(avg_similarity, 3),
                    'highlights': highlights,
                    'why_recommended': self._generate_recommendation_reason(product, reviews, query)
                }
                
                recommendations.append(recommendation)
            
            # Sort by recommendation score
            recommendations.sort(key=lambda x: x['recommendation_score'], reverse=True)
            
            return recommendations
            
        except Exception as e:
            logger.error(f"Failed to generate recommendations: {e}")
            return []
    
    def _extract_review_highlights(self, reviews: List[Dict], query: str) -> List[str]:
        """Extract key highlights from reviews relevant to the query"""
        try:
            highlights = []
            
            # Sort reviews by similarity score
            sorted_reviews = sorted(reviews, key=lambda x: x.get('similarity_score', 0), reverse=True)
            
            for review in sorted_reviews[:3]:  # Top 3 most relevant reviews
                content = review.get('review_content', '')
                if content and len(content) > 20:
                    # Extract first sentence or first 100 characters
                    sentences = content.split('.')
                    highlight = sentences[0].strip() if sentences else content[:100]
                    
                    if len(highlight) > 20 and highlight not in highlights:
                        highlights.append(highlight + ('.' if not highlight.endswith('.') else ''))
            
            return highlights[:2]  # Return max 2 highlights
            
        except Exception as e:
            logger.error(f"Failed to extract highlights: {e}")
            return []
    
    def _generate_recommendation_reason(self, product: Dict, reviews: List[Dict], query: str) -> str:
        """Generate reason for recommendation"""
        try:
            reasons = []
            
            # High similarity to query
            avg_similarity = statistics.mean([r.get('similarity_score', 0) for r in reviews])
            if avg_similarity > 0.8:
                reasons.append("highly relevant to your search")
            
            # High ratings
            avg_rating = statistics.mean([r.get('review_rating', 0) for r in reviews])
            if avg_rating >= 4.5:
                reasons.append(f"excellent customer ratings ({avg_rating:.1f}/5)")
            
            # Multiple relevant reviews
            if len(reviews) >= 5:
                reasons.append(f"mentioned in {len(reviews)} relevant reviews")
            
            # Price consideration
            price = product.get('price', 0)
            if price > 0 and price < 100:
                reasons.append("good value")
            
            if reasons:
                return f"Recommended because it has {', '.join(reasons[:2])}"
            else:
                return "Recommended based on customer review analysis"
                
        except Exception as e:
            logger.error(f"Failed to generate recommendation reason: {e}")
            return "Recommended based on review analysis"
    
    def _generate_recommendation_explanation(self, query: str, recommendations: List[Dict]) -> str:
        """Generate AI explanation for recommendations"""
        try:
            if not recommendations:
                return f"No products found matching '{query}' in customer reviews."
            
            # Prepare context
            top_products = []
            for rec in recommendations[:3]:
                top_products.append(f"- {rec['title']} (Score: {rec['recommendation_score']:.2f}, {rec['relevant_reviews_count']} relevant reviews)")
            
            prompt = f"""Explain why these products are recommended for the search query "{query}" based on customer review analysis:

Top recommendations:
{chr(10).join(top_products)}

Provide a brief explanation (2-3 sentences) of why these products match the user's search and what customers are saying about them."""
            
            response = self.bedrock_client.invoke_model(
                modelId=self.model_id,
                body=json.dumps({
                    "anthropic_version": "bedrock-2023-05-31",
                    "max_tokens": 150,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.3
                }),
                contentType='application/json',
                accept='application/json'
            )
            
            response_body = json.loads(response['body'].read())
            return response_body['content'][0]['text'].strip()
            
        except Exception as e:
            logger.error(f"Failed to generate recommendation explanation: {e}")
            return f"These products are recommended based on customer reviews that mention '{query}' and have high satisfaction ratings."
    
    def _analyze_product_aspect(self, product_id: str, aspect: str, reviews: List[Dict]) -> Optional[Dict]:
        """Analyze how a specific product performs on a given aspect"""
        try:
            # Get product info
            product = self.products_collection.find_one({'product_id': product_id})
            if not product:
                return None
            
            # Calculate aspect score from reviews
            aspect_scores = []
            relevant_mentions = []
            
            for review in reviews:
                sentiment = review.get('sentiment', {})
                aspects = sentiment.get('aspects', {}) if isinstance(sentiment, dict) else {}
                
                # Look for the specific aspect or similar aspects
                for asp, score in aspects.items():
                    if aspect.lower() in asp.lower() or asp.lower() in aspect.lower():
                        aspect_scores.append(score)
                        
                        # Extract mention from review content
                        content = review.get('review_content', '')
                        if content and aspect.lower() in content.lower():
                            sentences = content.split('.')
                            for sentence in sentences:
                                if aspect.lower() in sentence.lower():
                                    relevant_mentions.append(sentence.strip())
                                    break
            
            if not aspect_scores:
                return None
            
            avg_aspect_score = statistics.mean(aspect_scores)
            
            return {
                'product_id': product_id,
                'product_title': product.get('title', 'Unknown Product'),
                'product_category': product.get('category', 'Unknown'),
                'product_price': product.get('price', 0),
                'product_rating': product.get('rating', 0),
                'aspect_score': round(avg_aspect_score, 3),
                'aspect_mentions': len(aspect_scores),
                'sentiment_label': self._get_sentiment_label(avg_aspect_score),
                'sample_mentions': relevant_mentions[:2]
            }
            
        except Exception as e:
            logger.error(f"Failed to analyze product aspect: {e}")
            return None
    
    def _generate_aspect_overview(self, aspect: str, product_insights: List[Dict]) -> Dict[str, Any]:
        """Generate overview insights for an aspect across products"""
        try:
            if not product_insights:
                return {'summary': f'No products found with sufficient data about {aspect}'}
            
            # Calculate statistics
            aspect_scores = [p['aspect_score'] for p in product_insights]
            avg_score = statistics.mean(aspect_scores)
            
            # Find best and worst performers
            best_product = max(product_insights, key=lambda x: x['aspect_score'])
            worst_product = min(product_insights, key=lambda x: x['aspect_score'])
            
            # Category analysis
            category_scores = defaultdict(list)
            for product in product_insights:
                category_scores[product['product_category']].append(product['aspect_score'])
            
            category_averages = {
                cat: statistics.mean(scores) 
                for cat, scores in category_scores.items()
            }
            
            best_category = max(category_averages.items(), key=lambda x: x[1]) if category_averages else ('Unknown', 0)
            
            return {
                'summary': f'Analyzed {len(product_insights)} products for {aspect}',
                'overall_aspect_score': round(avg_score, 3),
                'sentiment_label': self._get_sentiment_label(avg_score),
                'best_performer': {
                    'product': best_product['product_title'],
                    'score': best_product['aspect_score']
                },
                'worst_performer': {
                    'product': worst_product['product_title'],
                    'score': worst_product['aspect_score']
                },
                'best_category': {
                    'category': best_category[0],
                    'average_score': round(best_category[1], 3)
                },
                'total_mentions': sum(p['aspect_mentions'] for p in product_insights)
            }
            
        except Exception as e:
            logger.error(f"Failed to generate aspect overview: {e}")
            return {'summary': f'Analysis completed for {aspect}'}
    
    def _get_sentiment_label(self, score: float) -> str:
        """Convert sentiment score to label"""
        if score > 0.3:
            return 'very_positive'
        elif score > 0.1:
            return 'positive'
        elif score > -0.1:
            return 'neutral'
        elif score > -0.3:
            return 'negative'
        else:
            return 'very_negative'
    
    def _extract_key_findings(self, results: List[Dict]) -> List[str]:
        """Extract key findings from search results"""
        try:
            findings = []
            
            # Most mentioned products
            product_counts = Counter([r.get('product_title', 'Unknown') for r in results])
            if product_counts:
                top_product, count = product_counts.most_common(1)[0]
                findings.append(f"Most discussed product: {top_product} ({count} reviews)")
            
            # Rating distribution
            ratings = [r.get('review_rating', 0) for r in results]
            if ratings:
                high_ratings = sum(1 for r in ratings if r >= 4)
                if high_ratings / len(ratings) > 0.7:
                    findings.append(f"{high_ratings}/{len(ratings)} reviews are 4+ stars")
            
            # Sentiment patterns
            sentiment_scores = []
            for result in results:
                sentiment = result.get('sentiment', {})
                if isinstance(sentiment, dict) and 'score' in sentiment:
                    sentiment_scores.append(sentiment['score'])
            
            if sentiment_scores:
                positive_count = sum(1 for s in sentiment_scores if s > 0.1)
                if positive_count / len(sentiment_scores) > 0.6:
                    findings.append(f"Predominantly positive sentiment ({positive_count}/{len(sentiment_scores)} reviews)")
            
            return findings[:3]  # Return max 3 findings
            
        except Exception as e:
            logger.error(f"Failed to extract key findings: {e}")
            return []

# Global analytics service instance
analytics_service = AnalyticsService()

def lambda_handler(event, context):
    """
    Lambda handler for analytics API
    
    Supported operations:
    - POST /analytics/search/reviews - Semantic review search
    - GET /analytics/sentiment/{product_id} - Get sentiment analysis
    - POST /analytics/recommendations - Get review-based recommendations
    - GET /analytics/aspects/{aspect} - Get aspect insights
    """
    try:
        # Parse request
        http_method = event.get('httpMethod', '')
        path = event.get('path', '')
        body = event.get('body', '{}')
        query_params = event.get('queryStringParameters') or {}
        path_params = event.get('pathParameters') or {}
        
        # Parse body if present
        request_data = {}
        if body:
            try:
                request_data = json.loads(body)
            except json.JSONDecodeError:
                return {
                    'statusCode': 400,
                    'headers': {
                        'Content-Type': 'application/json',
                        'Access-Control-Allow-Origin': '*',
                        'Access-Control-Allow-Headers': 'Content-Type,Authorization',
                        'Access-Control-Allow-Methods': 'GET,POST,PUT,DELETE,OPTIONS'
                    },
                    'body': json.dumps({
                        'success': False,
                        'error': 'Invalid JSON in request body'
                    })
                }
        
        # Handle OPTIONS request for CORS
        if http_method == 'OPTIONS':
            return {
                'statusCode': 200,
                'headers': {
                    'Access-Control-Allow-Origin': '*',
                    'Access-Control-Allow-Headers': 'Content-Type,Authorization',
                    'Access-Control-Allow-Methods': 'GET,POST,PUT,DELETE,OPTIONS'
                },
                'body': ''
            }
        
        # Route requests
        if http_method == 'POST' and '/analytics/search/reviews' in path:
            # Semantic review search
            query = request_data.get('query')
            filters = request_data.get('filters', {})
            
            if not query:
                return {
                    'statusCode': 400,
                    'headers': {
                        'Content-Type': 'application/json',
                        'Access-Control-Allow-Origin': '*'
                    },
                    'body': json.dumps({
                        'success': False,
                        'error': 'query is required'
                    })
                }
            
            result = analytics_service.semantic_review_search(query, filters)
            status_code = 200 if result.get('success') else 400
            
            return {
                'statusCode': status_code,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps(result)
            }
        
        elif http_method == 'GET' and '/analytics/sentiment/' in path:
            # Get sentiment analysis
            product_id = path_params.get('product_id')
            
            if not product_id:
                return {
                    'statusCode': 400,
                    'headers': {
                        'Content-Type': 'application/json',
                        'Access-Control-Allow-Origin': '*'
                    },
                    'body': json.dumps({
                        'success': False,
                        'error': 'product_id is required'
                    })
                }
            
            result = analytics_service.get_review_sentiment_analysis(product_id)
            status_code = 200 if result.get('success') else 404
            
            return {
                'statusCode': status_code,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps(result)
            }
        
        elif http_method == 'POST' and '/analytics/recommendations' in path:
            # Get review-based recommendations
            query = request_data.get('query')
            user_preferences = request_data.get('user_preferences')
            
            if not query:
                return {
                    'statusCode': 400,
                    'headers': {
                        'Content-Type': 'application/json',
                        'Access-Control-Allow-Origin': '*'
                    },
                    'body': json.dumps({
                        'success': False,
                        'error': 'query is required'
                    })
                }
            
            result = analytics_service.get_product_recommendations_by_reviews(query, user_preferences)
            status_code = 200 if result.get('success') else 400
            
            return {
                'statusCode': status_code,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps(result)
            }
        
        elif http_method == 'GET' and '/analytics/aspects/' in path:
            # Get aspect insights
            aspect = path_params.get('aspect')
            category = query_params.get('category')
            
            if not aspect:
                return {
                    'statusCode': 400,
                    'headers': {
                        'Content-Type': 'application/json',
                        'Access-Control-Allow-Origin': '*'
                    },
                    'body': json.dumps({
                        'success': False,
                        'error': 'aspect is required'
                    })
                }
            
            result = analytics_service.get_review_insights_by_aspect(aspect, category)
            status_code = 200 if result.get('success') else 404
            
            return {
                'statusCode': status_code,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps(result)
            }
        
        else:
            return {
                'statusCode': 404,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps({
                    'success': False,
                    'error': 'Endpoint not found'
                })
            }
    
    except Exception as e:
        logger.error(f"Lambda handler error: {e}")
        return {
            'statusCode': 500,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({
                'success': False,
                'error': 'Internal server error'
            })
        }