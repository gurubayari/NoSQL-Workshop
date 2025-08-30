"""
Unit tests for Chat API Lambda function
Tests chat functionality, conversation management, and RAG integration
"""
import pytest
import json
import uuid
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta
import sys
import os

# Add the functions directory to the path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'functions'))
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'shared'))

# Mock AWS services before importing
with patch('boto3.client'), patch('boto3.resource'):
    from chat_api import ChatService, lambda_handler

class TestChatService:
    """Test cases for ChatService class"""
    
    @pytest.fixture
    def mock_dependencies(self):
        """Mock all external dependencies"""
        with patch('chat_api.get_dynamodb_table') as mock_table, \
             patch('chat_api.cache_get') as mock_cache_get, \
             patch('chat_api.cache_set') as mock_cache_set, \
             patch('chat_api.cache_delete') as mock_cache_delete, \
             patch('chat_api.embedding_generator') as mock_embedding, \
             patch('chat_api.vector_search_manager') as mock_vector_search, \
             patch('boto3.client') as mock_boto_client:
            
            # Setup mocks
            mock_bedrock = Mock()
            mock_boto_client.return_value = mock_bedrock
            
            mock_dynamodb_table = Mock()
            mock_table.return_value = mock_dynamodb_table
            
            yield {
                'bedrock': mock_bedrock,
                'dynamodb_table': mock_dynamodb_table,
                'cache_get': mock_cache_get,
                'cache_set': mock_cache_set,
                'cache_delete': mock_cache_delete,
                'embedding_generator': mock_embedding,
                'vector_search_manager': mock_vector_search
            }
    
    @pytest.fixture
    def chat_service(self, mock_dependencies):
        """Create ChatService instance with mocked dependencies"""
        return ChatService()
    
    def test_get_recent_messages_from_cache_success(self, chat_service, mock_dependencies):
        """Test successful retrieval of recent messages from cache"""
        # Setup
        user_id = "test_user_123"
        cached_messages = [
            {
                'message_id': 'msg1',
                'role': 'user',
                'content': 'Hello',
                'timestamp': '2024-01-01T10:00:00Z'
            },
            {
                'message_id': 'msg2',
                'role': 'assistant',
                'content': 'Hi there!',
                'timestamp': '2024-01-01T10:00:01Z'
            }
        ]
        
        mock_dependencies['cache_get'].return_value = json.dumps({
            'user_id': user_id,
            'messages': cached_messages,
            'updated_at': '2024-01-01T10:00:01Z'
        })
        
        # Execute
        result = chat_service._get_recent_messages_from_cache(user_id)
        
        # Assert
        assert result == cached_messages
        mock_dependencies['cache_get'].assert_called_once()
    
    def test_get_recent_messages_from_cache_empty(self, chat_service, mock_dependencies):
        """Test retrieval when cache is empty"""
        # Setup
        user_id = "test_user_123"
        mock_dependencies['cache_get'].return_value = None
        
        # Execute
        result = chat_service._get_recent_messages_from_cache(user_id)
        
        # Assert
        assert result == []
    
    def test_cache_recent_messages_success(self, chat_service, mock_dependencies):
        """Test successful caching of recent messages"""
        # Setup
        user_id = "test_user_123"
        messages = [
            {'message_id': f'msg{i}', 'role': 'user', 'content': f'Message {i}'}
            for i in range(15)  # More than max_context_messages
        ]
        
        mock_dependencies['cache_set'].return_value = True
        
        # Execute
        result = chat_service._cache_recent_messages(user_id, messages)
        
        # Assert
        assert result is True
        mock_dependencies['cache_set'].assert_called_once()
        
        # Verify only last 10 messages are cached
        call_args = mock_dependencies['cache_set'].call_args
        cached_data = json.loads(call_args[0][1])
        assert len(cached_data['messages']) == 10
        assert cached_data['messages'][0]['message_id'] == 'msg5'  # Should start from 5th message
    
    def test_store_message_in_dynamodb_success(self, chat_service, mock_dependencies):
        """Test successful message storage in DynamoDB"""
        # Setup
        user_id = "test_user_123"
        message = {
            'message_id': 'test_msg_123',
            'role': 'user',
            'content': 'Test message',
            'timestamp': '2024-01-01T10:00:00Z'
        }
        
        mock_dependencies['dynamodb_table'].put_item.return_value = {}
        
        # Execute
        result = chat_service._store_message_in_dynamodb(user_id, message)
        
        # Assert
        assert result is True
        mock_dependencies['dynamodb_table'].put_item.assert_called_once()
        
        # Verify the stored item structure
        call_args = mock_dependencies['dynamodb_table'].put_item.call_args
        stored_item = call_args[1]['Item']
        assert stored_item['user_id'] == user_id
        assert stored_item['message_id'] == message['message_id']
        assert stored_item['role'] == message['role']
        assert stored_item['content'] == message['content']
        assert 'ttl' in stored_item
    
    def test_get_conversation_history_success(self, chat_service, mock_dependencies):
        """Test successful retrieval of conversation history"""
        # Setup
        user_id = "test_user_123"
        mock_items = [
            {
                'message_id': 'msg2',
                'role': 'assistant',
                'content': 'Response',
                'timestamp': '2024-01-01T10:00:01Z',
                'metadata': {}
            },
            {
                'message_id': 'msg1',
                'role': 'user',
                'content': 'Question',
                'timestamp': '2024-01-01T10:00:00Z',
                'metadata': {}
            }
        ]
        
        mock_dependencies['dynamodb_table'].query.return_value = {
            'Items': mock_items,
            'Count': 2
        }
        
        # Execute
        result = chat_service._get_conversation_history(user_id, limit=10)
        
        # Assert
        assert len(result) == 2
        # Should be in chronological order (reversed from DynamoDB result)
        assert result[0]['message_id'] == 'msg1'
        assert result[1]['message_id'] == 'msg2'
        
        mock_dependencies['dynamodb_table'].query.assert_called_once()
    
    def test_perform_rag_search_success(self, chat_service, mock_dependencies):
        """Test successful RAG search across all collections"""
        # Setup
        query = "wireless headphones"
        
        # Mock embedding generation
        mock_embedding_result = Mock()
        mock_embedding_result.success = True
        mock_embedding_result.embedding = [0.1] * 1536
        mock_dependencies['embedding_generator'].generate_embedding.return_value = mock_embedding_result
        
        # Mock vector search results
        kb_results = [
            {
                'title': 'Headphone Policy',
                'content': 'Our headphone return policy...',
                'similarity_score': 0.85,
                'category': 'policies'
            }
        ]
        
        product_results = [
            {
                'title': 'Wireless Bluetooth Headphones',
                'description': 'High-quality wireless headphones...',
                'price': 199.99,
                'rating': 4.5,
                'similarity_score': 0.9,
                'product_id': 'prod_123'
            }
        ]
        
        review_results = [
            {
                'title': 'Great sound quality',
                'content': 'These headphones have amazing audio...',
                'rating': 5,
                'similarity_score': 0.8,
                'product_id': 'prod_123'
            }
        ]
        
        mock_dependencies['vector_search_manager'].vector_search_knowledge_base.return_value = kb_results
        mock_dependencies['vector_search_manager'].vector_search_products.return_value = product_results
        mock_dependencies['vector_search_manager'].vector_search_reviews.return_value = review_results
        
        # Execute
        result = chat_service._perform_rag_search(query)
        
        # Assert
        assert 'context' in result
        assert 'sources' in result
        assert len(result['context']) == 3  # 1 KB + 1 product + 1 review
        assert len(result['sources']) == 3
        
        # Verify context items
        context_types = [item['type'] for item in result['context']]
        assert 'knowledge_base' in context_types
        assert 'product' in context_types
        assert 'review' in context_types
    
    def test_perform_rag_search_embedding_failure(self, chat_service, mock_dependencies):
        """Test RAG search when embedding generation fails"""
        # Setup
        query = "test query"
        
        mock_embedding_result = Mock()
        mock_embedding_result.success = False
        mock_dependencies['embedding_generator'].generate_embedding.return_value = mock_embedding_result
        
        # Execute
        result = chat_service._perform_rag_search(query)
        
        # Assert
        assert result == {'context': [], 'sources': []}
    
    def test_build_system_prompt_with_context(self, chat_service, mock_dependencies):
        """Test system prompt building with RAG context"""
        # Setup
        rag_context = {
            'context': [
                {
                    'type': 'knowledge_base',
                    'title': 'Return Policy',
                    'content': 'You can return items within 30 days...'
                },
                {
                    'type': 'product',
                    'title': 'Wireless Headphones',
                    'description': 'Premium audio quality...',
                    'price': 199.99,
                    'rating': 4.5
                }
            ]
        }
        
        # Execute
        result = chat_service._build_system_prompt(rag_context)
        
        # Assert
        assert 'Unicorn E-Commerce' in result
        assert 'Return Policy' in result
        assert 'Wireless Headphones' in result
        assert 'Premium audio quality' in result
        assert '$199.99' in result
    
    def test_build_system_prompt_without_context(self, chat_service, mock_dependencies):
        """Test system prompt building without RAG context"""
        # Setup
        rag_context = {'context': []}
        
        # Execute
        result = chat_service._build_system_prompt(rag_context)
        
        # Assert
        assert 'Unicorn E-Commerce' in result
        assert 'Relevant Information' not in result
    
    def test_call_bedrock_claude_success(self, chat_service, mock_dependencies):
        """Test successful Bedrock Claude API call"""
        # Setup
        messages = [
            {'role': 'user', 'content': 'Hello'},
            {'role': 'assistant', 'content': 'Hi there!'},
            {'role': 'user', 'content': 'How are you?'}
        ]
        system_prompt = "You are a helpful assistant."
        
        mock_response = {
            'body': Mock()
        }
        mock_response['body'].read.return_value = json.dumps({
            'content': [{'text': 'I am doing well, thank you!'}]
        }).encode()
        
        mock_dependencies['bedrock'].invoke_model.return_value = mock_response
        
        # Execute
        result = chat_service._call_bedrock_claude(messages, system_prompt)
        
        # Assert
        assert result == 'I am doing well, thank you!'
        mock_dependencies['bedrock'].invoke_model.assert_called_once()
        
        # Verify request format
        call_args = mock_dependencies['bedrock'].invoke_model.call_args
        request_body = json.loads(call_args[1]['body'])
        assert request_body['system'] == system_prompt
        assert len(request_body['messages']) == 3
        assert request_body['messages'][0]['role'] == 'user'
        assert request_body['messages'][0]['content'] == 'Hello'
    
    def test_call_bedrock_claude_failure(self, chat_service, mock_dependencies):
        """Test Bedrock Claude API call failure"""
        # Setup
        messages = [{'role': 'user', 'content': 'Hello'}]
        system_prompt = "You are a helpful assistant."
        
        mock_dependencies['bedrock'].invoke_model.side_effect = Exception("API Error")
        
        # Execute
        result = chat_service._call_bedrock_claude(messages, system_prompt)
        
        # Assert
        assert result is None
    
    def test_send_message_success(self, chat_service, mock_dependencies):
        """Test successful message sending with AI response"""
        # Setup
        user_id = "test_user_123"
        message = "What are your best wireless headphones?"
        session_id = "session_456"
        
        # Mock cached messages
        mock_dependencies['cache_get'].return_value = json.dumps({
            'messages': [
                {'role': 'user', 'content': 'Previous message', 'message_id': 'prev_msg'}
            ]
        })
        
        # Mock RAG search
        with patch.object(chat_service, '_perform_rag_search') as mock_rag:
            mock_rag.return_value = {
                'context': [{'type': 'product', 'title': 'Headphones'}],
                'sources': ['Product: Headphones']
            }
            
            # Mock Bedrock response
            with patch.object(chat_service, '_call_bedrock_claude') as mock_bedrock:
                mock_bedrock.return_value = "I recommend our premium wireless headphones..."
                
                # Mock storage operations
                with patch.object(chat_service, '_store_message_in_dynamodb') as mock_store:
                    mock_store.return_value = True
                    mock_dependencies['cache_set'].return_value = True
                    
                    # Execute
                    result = chat_service.send_message(user_id, message, session_id)
        
        # Assert
        assert result['success'] is True
        assert 'message_id' in result
        assert result['response'] == "I recommend our premium wireless headphones..."
        assert result['sources'] == ['Product: Headphones']
        assert result['session_id'] == session_id
        
        # Verify storage was called
        assert mock_store.call_count == 2  # User message + assistant message
    
    def test_send_message_bedrock_failure(self, chat_service, mock_dependencies):
        """Test message sending when Bedrock fails"""
        # Setup
        user_id = "test_user_123"
        message = "Hello"
        
        mock_dependencies['cache_get'].return_value = None
        
        with patch.object(chat_service, '_perform_rag_search') as mock_rag:
            mock_rag.return_value = {'context': [], 'sources': []}
            
            with patch.object(chat_service, '_call_bedrock_claude') as mock_bedrock:
                mock_bedrock.return_value = None  # Simulate failure
                
                # Execute
                result = chat_service.send_message(user_id, message)
        
        # Assert
        assert result['success'] is False
        assert 'Failed to generate AI response' in result['error']
    
    def test_get_chat_history_success(self, chat_service, mock_dependencies):
        """Test successful chat history retrieval"""
        # Setup
        user_id = "test_user_123"
        limit = 10
        
        mock_items = [
            {
                'message_id': 'msg2',
                'role': 'assistant',
                'content': 'Response',
                'timestamp': '2024-01-01T10:00:01Z',
                'metadata': {}
            },
            {
                'message_id': 'msg1',
                'role': 'user',
                'content': 'Question',
                'timestamp': '2024-01-01T10:00:00Z',
                'metadata': {}
            }
        ]
        
        mock_dependencies['dynamodb_table'].query.return_value = {
            'Items': mock_items,
            'Count': 2
        }
        
        # Execute
        result = chat_service.get_chat_history(user_id, limit)
        
        # Assert
        assert result['success'] is True
        assert len(result['messages']) == 2
        assert result['has_more'] is False
        assert result['messages'][0]['message_id'] == 'msg1'  # Chronological order
    
    def test_get_chat_history_with_pagination(self, chat_service, mock_dependencies):
        """Test chat history retrieval with pagination"""
        # Setup
        user_id = "test_user_123"
        limit = 10
        last_message_id = "last_msg_id"
        
        mock_dependencies['dynamodb_table'].query.return_value = {
            'Items': [],
            'LastEvaluatedKey': {'user_id': user_id, 'message_id': 'next_msg_id'}
        }
        
        # Execute
        result = chat_service.get_chat_history(user_id, limit, last_message_id)
        
        # Assert
        assert result['success'] is True
        assert result['has_more'] is True
        assert result['last_message_id'] == 'next_msg_id'
        
        # Verify pagination parameters were used
        call_args = mock_dependencies['dynamodb_table'].query.call_args[1]
        assert 'ExclusiveStartKey' in call_args
        assert call_args['ExclusiveStartKey']['message_id'] == last_message_id
    
    def test_clear_conversation_success(self, chat_service, mock_dependencies):
        """Test successful conversation clearing"""
        # Setup
        user_id = "test_user_123"
        mock_dependencies['cache_delete'].return_value = True
        
        # Execute
        result = chat_service.clear_conversation(user_id)
        
        # Assert
        assert result['success'] is True
        assert 'cleared' in result['message']
        mock_dependencies['cache_delete'].assert_called_once()

class TestLambdaHandler:
    """Test cases for Lambda handler function"""
    
    def test_send_message_endpoint(self):
        """Test POST /chat/message endpoint"""
        # Setup
        event = {
            'httpMethod': 'POST',
            'path': '/chat/message',
            'body': json.dumps({
                'user_id': 'test_user_123',
                'message': 'Hello',
                'session_id': 'session_456'
            })
        }
        
        with patch('chat_api.chat_service') as mock_service:
            mock_service.send_message.return_value = {
                'success': True,
                'message_id': 'msg_123',
                'response': 'Hello there!',
                'sources': []
            }
            
            # Execute
            response = lambda_handler(event, {})
        
        # Assert
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['success'] is True
        assert body['response'] == 'Hello there!'
        
        # Verify CORS headers
        assert response['headers']['Access-Control-Allow-Origin'] == '*'
    
    def test_send_message_missing_parameters(self):
        """Test POST /chat/message with missing parameters"""
        # Setup
        event = {
            'httpMethod': 'POST',
            'path': '/chat/message',
            'body': json.dumps({
                'user_id': 'test_user_123'
                # Missing 'message'
            })
        }
        
        # Execute
        response = lambda_handler(event, {})
        
        # Assert
        assert response['statusCode'] == 400
        body = json.loads(response['body'])
        assert body['success'] is False
        assert 'required' in body['error']
    
    def test_get_chat_history_endpoint(self):
        """Test GET /chat/history endpoint"""
        # Setup
        event = {
            'httpMethod': 'GET',
            'path': '/chat/history',
            'queryStringParameters': {
                'user_id': 'test_user_123',
                'limit': '20'
            }
        }
        
        with patch('chat_api.chat_service') as mock_service:
            mock_service.get_chat_history.return_value = {
                'success': True,
                'messages': [
                    {'message_id': 'msg1', 'role': 'user', 'content': 'Hello'}
                ],
                'has_more': False
            }
            
            # Execute
            response = lambda_handler(event, {})
        
        # Assert
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['success'] is True
        assert len(body['messages']) == 1
    
    def test_clear_conversation_endpoint(self):
        """Test DELETE /chat/conversation endpoint"""
        # Setup
        event = {
            'httpMethod': 'DELETE',
            'path': '/chat/conversation',
            'body': json.dumps({
                'user_id': 'test_user_123'
            })
        }
        
        with patch('chat_api.chat_service') as mock_service:
            mock_service.clear_conversation.return_value = {
                'success': True,
                'message': 'Conversation context cleared'
            }
            
            # Execute
            response = lambda_handler(event, {})
        
        # Assert
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['success'] is True
    
    def test_options_request(self):
        """Test OPTIONS request for CORS preflight"""
        # Setup
        event = {
            'httpMethod': 'OPTIONS',
            'path': '/chat/message'
        }
        
        # Execute
        response = lambda_handler(event, {})
        
        # Assert
        assert response['statusCode'] == 200
        assert response['headers']['Access-Control-Allow-Origin'] == '*'
        assert 'GET,POST,PUT,DELETE,OPTIONS' in response['headers']['Access-Control-Allow-Methods']
    
    def test_invalid_endpoint(self):
        """Test request to invalid endpoint"""
        # Setup
        event = {
            'httpMethod': 'GET',
            'path': '/invalid/endpoint'
        }
        
        # Execute
        response = lambda_handler(event, {})
        
        # Assert
        assert response['statusCode'] == 404
        body = json.loads(response['body'])
        assert body['success'] is False
        assert 'not found' in body['error'].lower()
    
    def test_invalid_json_body(self):
        """Test request with invalid JSON body"""
        # Setup
        event = {
            'httpMethod': 'POST',
            'path': '/chat/message',
            'body': 'invalid json'
        }
        
        # Execute
        response = lambda_handler(event, {})
        
        # Assert
        assert response['statusCode'] == 400
        body = json.loads(response['body'])
        assert body['success'] is False
        assert 'Invalid JSON' in body['error']
    
    def test_lambda_handler_exception(self):
        """Test lambda handler with unexpected exception"""
        # Setup
        event = {
            'httpMethod': 'POST',
            'path': '/chat/message',
            'body': json.dumps({'user_id': 'test', 'message': 'hello'})
        }
        
        with patch('chat_api.chat_service') as mock_service:
            mock_service.send_message.side_effect = Exception("Unexpected error")
            
            # Execute
            response = lambda_handler(event, {})
        
        # Assert
        assert response['statusCode'] == 500
        body = json.loads(response['body'])
        assert body['success'] is False
        assert 'Internal server error' in body['error']

if __name__ == '__main__':
    pytest.main([__file__])