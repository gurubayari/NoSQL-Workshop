"""
Chat API Lambda Function for AWS NoSQL Workshop
Implements AI-powered chatbot with Bedrock integration, conversation management, and RAG functionality
"""
import json
import logging
import boto3
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
import uuid
import os
import sys

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
    from shared.chat_memory import chat_memory_manager
except ImportError:
    from config import config
    from database import (
        get_dynamodb_table, get_documentdb_collection,
        cache_get, cache_set, cache_delete, get_cache_key, db
    )
    from embeddings import embedding_generator
    from vector_search import vector_search_manager
    from chat_memory import chat_memory_manager

# Configure logging
logging.basicConfig(level=getattr(logging, config.LOG_LEVEL))
logger = logging.getLogger(__name__)

class ChatService:
    """Service class for chat functionality with Bedrock integration"""
    
    def __init__(self):
        self.bedrock_client = boto3.client('bedrock-runtime', region_name=config.AWS_REGION)
        self.model_id = config.BEDROCK_MODEL_ID
        self.max_context_messages = 10
        
        logger.info(f"Initialized ChatService with model: {self.model_id}")
    

    
    def _perform_rag_search(self, query: str) -> Dict[str, Any]:
        """Perform RAG search across products, reviews, and knowledge base"""
        try:
            # Generate embedding for the query
            embedding_result = embedding_generator.generate_embedding(query)
            
            if not embedding_result.success:
                logger.error(f"Failed to generate embedding for query: {query}")
                return {'context': [], 'sources': []}
            
            query_embedding = embedding_result.embedding
            context_items = []
            sources = []
            
            # Search knowledge base (highest priority for general questions)
            kb_results = vector_search_manager.vector_search_knowledge_base(
                query_embedding=query_embedding,
                limit=3,
                min_score=0.8
            )
            
            for result in kb_results:
                context_items.append({
                    'type': 'knowledge_base',
                    'title': result.get('title', ''),
                    'content': result.get('content', ''),
                    'score': result.get('similarity_score', 0),
                    'category': result.get('category', '')
                })
                sources.append(f"Knowledge Base: {result.get('title', 'Article')}")
            
            # Search products (for product-specific questions)
            product_results = vector_search_manager.vector_search_products(
                query_embedding=query_embedding,
                limit=3,
                min_score=0.7
            )
            
            for result in product_results:
                context_items.append({
                    'type': 'product',
                    'title': result.get('title', ''),
                    'description': result.get('description', ''),
                    'price': result.get('price', 0),
                    'rating': result.get('rating', 0),
                    'score': result.get('similarity_score', 0),
                    'product_id': result.get('product_id', '')
                })
                sources.append(f"Product: {result.get('title', 'Unknown Product')}")
            
            # Search reviews (for experience-based questions)
            review_results = vector_search_manager.vector_search_reviews(
                query_embedding=query_embedding,
                limit=2,
                min_score=0.7
            )
            
            for result in review_results:
                context_items.append({
                    'type': 'review',
                    'title': result.get('title', ''),
                    'content': result.get('content', ''),
                    'rating': result.get('rating', 0),
                    'score': result.get('similarity_score', 0),
                    'product_id': result.get('product_id', '')
                })
                sources.append(f"Customer Review: {result.get('title', 'Review')}")
            
            logger.info(f"RAG search found {len(context_items)} relevant items")
            
            return {
                'context': context_items,
                'sources': sources
            }
            
        except Exception as e:
            logger.error(f"RAG search failed: {e}")
            return {'context': [], 'sources': []}
    
    def _build_system_prompt(self, rag_context: Dict[str, Any]) -> str:
        """Build system prompt with RAG context"""
        base_prompt = """You are a helpful AI assistant for Unicorn E-Commerce, an online shopping platform. 
You help customers find products, answer questions about orders, policies, and provide shopping recommendations.

Guidelines:
- Be friendly, helpful, and professional
- Provide accurate information based on the context provided
- If you don't know something, say so rather than guessing
- Suggest relevant products when appropriate
- Help with shopping decisions and comparisons
- Keep responses concise but informative"""
        
        if rag_context.get('context'):
            context_text = "\n\nRelevant Information:\n"
            
            for item in rag_context['context']:
                if item['type'] == 'knowledge_base':
                    context_text += f"\nKnowledge Base - {item['title']}:\n{item['content']}\n"
                elif item['type'] == 'product':
                    context_text += f"\nProduct - {item['title']}:\n{item['description']}\nPrice: ${item['price']}, Rating: {item['rating']}/5\n"
                elif item['type'] == 'review':
                    context_text += f"\nCustomer Review - {item['title']}:\n{item['content']}\nRating: {item['rating']}/5\n"
            
            base_prompt += context_text
        
        return base_prompt
    
    def _call_bedrock_claude(self, messages: List[Dict[str, Any]], system_prompt: str) -> Optional[str]:
        """Call Bedrock Claude model for chat completion"""
        try:
            # Format messages for Claude
            formatted_messages = []
            for msg in messages:
                formatted_messages.append({
                    "role": msg["role"],
                    "content": msg["content"]
                })
            
            # Prepare request body for Claude
            request_body = {
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 1000,
                "system": system_prompt,
                "messages": formatted_messages,
                "temperature": 0.7,
                "top_p": 0.9
            }
            
            # Call Bedrock
            response = self.bedrock_client.invoke_model(
                modelId=self.model_id,
                body=json.dumps(request_body),
                contentType='application/json',
                accept='application/json'
            )
            
            # Parse response
            response_body = json.loads(response['body'].read())
            
            if 'content' in response_body and response_body['content']:
                return response_body['content'][0].get('text', '')
            else:
                logger.error(f"Invalid Claude response format: {response_body}")
                return None
                
        except Exception as e:
            logger.error(f"Bedrock Claude API call failed: {e}")
            return None
    
    def send_message(self, user_id: str, message: str, session_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Send a message and get AI response
        
        Args:
            user_id: User identifier
            message: User message
            session_id: Optional session identifier
            
        Returns:
            Response with AI message and metadata
        """
        try:
            # Generate message ID
            message_id = str(uuid.uuid4())
            timestamp = datetime.utcnow().isoformat()
            
            # Create user message
            user_message = {
                'message_id': message_id,
                'role': 'user',
                'content': message,
                'timestamp': timestamp,
                'metadata': {'session_id': session_id}
            }
            
            # Add user message to memory
            chat_memory_manager.add_message(user_id, user_message)
            
            # Get recent conversation context for AI
            recent_messages = chat_memory_manager.get_recent_messages(user_id)
            
            # Perform RAG search for relevant context
            rag_context = self._perform_rag_search(message)
            
            # Build system prompt with context
            system_prompt = self._build_system_prompt(rag_context)
            
            # Build conversation context for Claude
            claude_messages = chat_memory_manager.build_conversation_context(
                user_id, 
                max_context_messages=self.max_context_messages,
                include_system_messages=False
            )
            
            # Get AI response
            ai_response = self._call_bedrock_claude(claude_messages, system_prompt)
            
            if ai_response is None:
                return {
                    'success': False,
                    'error': 'Failed to generate AI response',
                    'message_id': message_id
                }
            
            # Create assistant message
            assistant_message_id = str(uuid.uuid4())
            assistant_message = {
                'message_id': assistant_message_id,
                'role': 'assistant',
                'content': ai_response,
                'timestamp': datetime.utcnow().isoformat(),
                'metadata': {
                    'session_id': session_id,
                    'rag_sources': rag_context.get('sources', []),
                    'context_items_count': len(rag_context.get('context', []))
                }
            }
            
            # Add assistant message to memory
            chat_memory_manager.add_message(user_id, assistant_message)
            
            return {
                'success': True,
                'message_id': assistant_message_id,
                'response': ai_response,
                'sources': rag_context.get('sources', []),
                'timestamp': assistant_message['timestamp'],
                'session_id': session_id
            }
            
        except Exception as e:
            logger.error(f"Failed to send message: {e}")
            return {
                'success': False,
                'error': str(e),
                'message_id': message_id if 'message_id' in locals() else None
            }
    
    def get_chat_history(self, user_id: str, limit: int = 20, last_message_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Get chat history with pagination using ChatMemoryManager
        
        Args:
            user_id: User identifier
            limit: Maximum number of messages to return
            last_message_id: Last message ID for pagination
            
        Returns:
            Chat history with pagination info
        """
        try:
            # Use ChatMemoryManager for history retrieval
            result = chat_memory_manager.get_conversation_history(
                user_id=user_id,
                limit=limit,
                last_message_id=last_message_id,
                include_recent=True
            )
            
            return result
            
        except Exception as e:
            logger.error(f"Failed to get chat history: {e}")
            return {
                'success': False,
                'error': str(e),
                'messages': []
            }
    
    def clear_conversation(self, user_id: str) -> Dict[str, Any]:
        """Clear conversation context using ChatMemoryManager"""
        try:
            success = chat_memory_manager.clear_recent_messages(user_id)
            
            if success:
                return {
                    'success': True,
                    'message': 'Conversation context cleared'
                }
            else:
                return {
                    'success': False,
                    'error': 'Failed to clear conversation context'
                }
            
        except Exception as e:
            logger.error(f"Failed to clear conversation: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def get_memory_stats(self, user_id: str) -> Dict[str, Any]:
        """Get memory usage statistics for a user"""
        try:
            stats = chat_memory_manager.get_memory_stats(user_id)
            return {
                'success': True,
                'stats': stats
            }
            
        except Exception as e:
            logger.error(f"Failed to get memory stats: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def archive_old_messages(self, user_id: str, days_to_keep: int = None) -> Dict[str, Any]:
        """Archive old messages for a user"""
        try:
            result = chat_memory_manager.archive_old_messages(user_id, days_to_keep)
            return result
            
        except Exception as e:
            logger.error(f"Failed to archive old messages: {e}")
            return {
                'success': False,
                'error': str(e)
            }

# Global chat service instance
chat_service = ChatService()

def lambda_handler(event, context):
    """
    Lambda handler for chat API
    
    Supported operations:
    - POST /chat/message - Send a message
    - GET /chat/history - Get chat history
    - DELETE /chat/conversation - Clear conversation
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
        if http_method == 'POST' and '/chat/message' in path:
            # Send message
            user_id = request_data.get('user_id')
            message = request_data.get('message')
            session_id = request_data.get('session_id')
            
            if not user_id or not message:
                return {
                    'statusCode': 400,
                    'headers': {
                        'Content-Type': 'application/json',
                        'Access-Control-Allow-Origin': '*'
                    },
                    'body': json.dumps({
                        'success': False,
                        'error': 'user_id and message are required'
                    })
                }
            
            result = chat_service.send_message(user_id, message, session_id)
            status_code = 200 if result.get('success') else 500
            
            return {
                'statusCode': status_code,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps(result)
            }
        
        elif http_method == 'GET' and '/chat/history' in path:
            # Get chat history
            user_id = query_params.get('user_id')
            limit = int(query_params.get('limit', 20))
            last_message_id = query_params.get('last_message_id')
            
            if not user_id:
                return {
                    'statusCode': 400,
                    'headers': {
                        'Content-Type': 'application/json',
                        'Access-Control-Allow-Origin': '*'
                    },
                    'body': json.dumps({
                        'success': False,
                        'error': 'user_id is required'
                    })
                }
            
            result = chat_service.get_chat_history(user_id, limit, last_message_id)
            status_code = 200 if result.get('success') else 500
            
            return {
                'statusCode': status_code,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps(result)
            }
        
        elif http_method == 'DELETE' and '/chat/conversation' in path:
            # Clear conversation
            user_id = request_data.get('user_id') or query_params.get('user_id')
            
            if not user_id:
                return {
                    'statusCode': 400,
                    'headers': {
                        'Content-Type': 'application/json',
                        'Access-Control-Allow-Origin': '*'
                    },
                    'body': json.dumps({
                        'success': False,
                        'error': 'user_id is required'
                    })
                }
            
            result = chat_service.clear_conversation(user_id)
            status_code = 200 if result.get('success') else 500
            
            return {
                'statusCode': status_code,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps(result)
            }
        
        elif http_method == 'GET' and '/chat/memory/stats' in path:
            # Get memory statistics
            user_id = query_params.get('user_id')
            
            if not user_id:
                return {
                    'statusCode': 400,
                    'headers': {
                        'Content-Type': 'application/json',
                        'Access-Control-Allow-Origin': '*'
                    },
                    'body': json.dumps({
                        'success': False,
                        'error': 'user_id is required'
                    })
                }
            
            result = chat_service.get_memory_stats(user_id)
            status_code = 200 if result.get('success') else 500
            
            return {
                'statusCode': status_code,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps(result)
            }
        
        elif http_method == 'POST' and '/chat/archive' in path:
            # Archive old messages
            user_id = request_data.get('user_id')
            days_to_keep = request_data.get('days_to_keep')
            
            if not user_id:
                return {
                    'statusCode': 400,
                    'headers': {
                        'Content-Type': 'application/json',
                        'Access-Control-Allow-Origin': '*'
                    },
                    'body': json.dumps({
                        'success': False,
                        'error': 'user_id is required'
                    })
                }
            
            result = chat_service.archive_old_messages(user_id, days_to_keep)
            status_code = 200 if result.get('success') else 500
            
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