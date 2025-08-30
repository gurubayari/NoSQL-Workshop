"""
Unit tests for Chat API Lambda function
Tests AI chat functionality, conversation management, and RAG integration
"""
import pytest
import json
import unittest.mock as mock
from unittest.mock import MagicMock, patch, Mock
from datetime import datetime, timezone
import uuid
import sys
import os

# Add the functions directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'functions'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'shared'))

# Mock the shared modules before importing
with patch.dict('sys.modules', {
    'shared.config': MagicMock(),
    'shared.database': MagicMock(),
    'shared.embeddings': MagicMock(),
    'shared.vector_search': MagicMock(),
    'shared.chat_memory': MagicMock(),
    'config': MagicMock(),
    'database': MagicMock(),
    'embeddings': MagicMock(),
    'vector_search': MagicMock(),
    'chat_memory': MagicMock()
}):
    from chat_api import ChatService, lambda_handler

class TestChatService:
    """Test cases for ChatService class"""
    
    def setup_method(self):
        """Set up test fixtures"""
        self.mock_bedrock_client = MagicMock()
        self.mock_embedding_generator = MagicMock()
        self.mock_vector_search_manager = MagicMock()
        self.mock_chat_memory_manager = MagicMock()
        
        with patch('chat_api.boto3.client') as mock_boto3_client, \
             patch('chat_api.embedding_generator') as mock_embedding, \
             patch('chat_api.vector_search_manager') as mock_vector_search, \
             patch('chat_api.chat_memory_manager') as mock_chat_memory:
            
            mock_boto3_client.return_value = self.mock_bedrock_client
            mock_embedding.return_value = self.mock_embedding_generator
            mock_vector_search.return_value = self.mock_vector_search_manager
            mock_chat_memory.return_value = self.mock_chat_memory_manager
            
            self.service = ChatService()
    
    def test_send_message_success(self):
        """Test successful message sending with AI response"""
        user_id = 'user_123'
        message = 'What are the best wireless headphones?'
        session_id = 'session_456'
        
        # Mock RAG search results
        mock_rag_context = {
            'context': [
                {
                    'type': 'product',
                    'title': 'Sony WH-1000XM4',
                    'description': 'Premium noise-canceling headphones',
                    'price': 299.99,
                    'rating': 4.5,
                    'score': 0.9
                }
            ],
            'sources': ['Product: Sony WH-1000XM4']
        }
        
        # Mock conversation context
        mock_conversation_context = [
            {'role': 'user', 'content': message}
        ]
        
        # Mock Bedrock response
        mock_bedrock_response = {
            'body': MagicMock()
        }
        mock_bedrock_response['body'].read.return_value = json.dumps({
            'content': [{
                'text': 'Based on customer reviews, the Sony WH-1000XM4 are excellent wireless headphones with great noise cancellation and sound quality.'
            }]
        }).encode()
        
        with patch.object(self.service, '_perform_rag_search', return_value=mock_rag_context), \
             patch.object(self.service, '_build_system_prompt', return_value='System prompt'), \
             patch.object(self.service, '_call_bedrock_claude', return_value='AI response'), \
             patch('chat_api.chat_memory_manager') as mock_memory:
            
            mock_memory.add_message.return_value = True
            mock_memory.get_recent_messages.return_value = []
            mock_memory.build_conversation_context.return_value = mock_conversation_context
            
            result = self.service.send_message(user_id, message, session_id)
            
            assert result['success'] is True
            assert 'message_id' in result
            assert 'response' in result
            assert 'sources' in result
            assert result['session_id'] == session_id
            assert len(result['sources']) > 0
    
    def test_send_message_bedrock_failure(self):
        """Test message sending when Bedrock fails"""
        user_id = 'user_123'
        message = 'Test message'
        
        with patch.object(self.service, '_perform_rag_search', return_value={'context': [], 'sources': []}), \
             patch.object(self.service, '_build_system_prompt', return_value='System prompt'), \
             patch.object(self.service, '_call_bedrock_claude', return_value=None), \
             patch('chat_api.chat_memory_manager') as mock_memory:
            
            mock_memory.add_message.return_value = True
            mock_memory.get_recent_messages.return_value = []
            mock_memory.build_conversation_context.return_value = []
            
            result = self.service.send_message(user_id, message)
            
            assert result['success'] is False
            assert 'Failed to generate AI response' in result['error']
    
    def test_perform_rag_search_success(self):
        """Test successful RAG search across different collections"""
        query = 'wireless headphones with good battery life'
        
        # Mock embedding generation
        mock_embedding_result = MagicMock()
        mock_embedding_result.success = True
        mock_embedding_result.embedding = [0.1, 0.2, 0.3]
        
        # Mock search results
        mock_kb_results = [
            {
                'title': 'Battery Life Guide',
                'content': 'Tips for maximizing headphone battery life',
                'similarity_score': 0.85,
                'category': 'guides'
            }
        ]
        
        mock_product_results = [
            {
                'title': 'Sony WH-1000XM4',
                'description': 'Premium wireless headphones',
                'price': 299.99,
                'rating': 4.5,
                'similarity_score': 0.9,
                'product_id': 'prod_123'
            }
        ]
        
        mock_review_results = [
            {
                'title': 'Great battery life',
                'content': 'These headphones last all day',
                'rating': 5,
                'similarity_score': 0.8,
                'product_id': 'prod_123'
            }
        ]
        
        with patch('chat_api.embedding_generator') as mock_embedding, \
             patch('chat_api.vector_search_manager') as mock_vector_search:
            
            mock_embedding.generate_embedding.return_value = mock_embedding_result
            mock_vector_search.vector_search_knowledge_base.return_value = mock_kb_results
            mock_vector_search.vector_search_products.return_value = mock_product_results
            mock_vector_search.vector_search_reviews.return_value = mock_review_results
            
            result = self.service._perform_rag_search(query)
            
            assert len(result['context']) == 3  # KB + Product + Review
            assert len(result['sources']) == 3
            assert any(item['type'] == 'knowledge_base' for item in result['context'])
            assert any(item['type'] == 'product' for item in result['context'])
            assert any(item['type'] == 'review' for item in result['context'])
    
    def test_perform_rag_search_embedding_failure(self):
        """Test RAG search when embedding generation fails"""
        query = 'test query'
        
        # Mock embedding failure
        mock_embedding_result = MagicMock()
        mock_embedding_result.success = False
        
        with patch('chat_api.embedding_generator') as mock_embedding:
            mock_embedding.generate_embedding.return_value = mock_embedding_result
            
            result = self.service._perform_rag_search(query)
            
            assert result['context'] == []
            assert result['sources'] == []
    
    def test_build_system_prompt_with_context(self):
        """Test building system prompt with RAG context"""
        rag_context = {
            'context': [
                {
                    'type': 'knowledge_base',
                    'title': 'Return Policy',
                    'content': 'You can return items within 30 days'
                },
                {
                    'type': 'product',
                    'title': 'Wireless Headphones',
                    'description': 'Premium audio quality',
                    'price': 199.99,
                    'rating': 4.5
                },
                {
                    'type': 'review',
                    'title': 'Great sound',
                    'content': 'Amazing audio quality',
                    'rating': 5
                }
            ]
        }
        
        result = self.service._build_system_prompt(rag_context)
        
        assert 'Unicorn E-Commerce' in result
        assert 'Return Policy' in result
        assert 'Wireless Headphones' in result
        assert 'Great sound' in result
        assert 'Premium audio quality' in result
    
    def test_build_system_prompt_without_context(self):
        """Test building system prompt without RAG context"""
        rag_context = {'context': []}
        
        result = self.service._build_system_prompt(rag_context)
        
        assert 'Unicorn E-Commerce' in result
        assert 'helpful AI assistant' in result
        # Should not contain context-specific information
        assert 'Relevant Information:' not in result
    
    def test_call_bedrock_claude_success(self):
        """Test successful Bedrock Claude API call"""
        messages = [
            {'role': 'user', 'content': 'What are the best headphones?'}
        ]
        system_prompt = 'You are a helpful assistant.'
        
        # Mock Bedrock response
        mock_response = {
            'body': MagicMock()
        }
        mock_response['body'].read.return_value = json.dumps({
            'content': [{
                'text': 'I recommend the Sony WH-1000XM4 headphones for their excellent sound quality and noise cancellation.'
            }]
        }).encode()
        
        self.mock_bedrock_client.invoke_model.return_value = mock_response
        
        result = self.service._call_bedrock_claude(messages, system_prompt)
        
        assert result is not None
        assert 'Sony WH-1000XM4' in result
        
        # Verify the request was formatted correctly
        call_args = self.mock_bedrock_client.invoke_model.call_args
        request_body = json.loads(call_args[1]['body'])
        assert request_body['anthropic_version'] == 'bedrock-2023-05-31'
        assert request_body['system'] == system_prompt
        assert len(request_body['messages']) == 1
    
    def test_call_bedrock_claude_api_error(self):
        """Test Bedrock Claude API call with error"""
        messages = [{'role': 'user', 'content': 'Test message'}]
        system_prompt = 'System prompt'
        
        # Mock API error
        self.mock_bedrock_client.invoke_model.side_effect = Exception("API Error")
        
        result = self.service._call_bedrock_claude(messages, system_prompt)
        
        assert result is None
    
    def test_call_bedrock_claude_invalid_response(self):
        """Test Bedrock Claude API call with invalid response format"""
        messages = [{'role': 'user', 'content': 'Test message'}]
        system_prompt = 'System prompt'
        
        # Mock invalid response
        mock_response = {
            'body': MagicMock()
        }
        mock_response['body'].read.return_value = json.dumps({
            'invalid_format': 'no content field'
        }).encode()
        
        self.mock_bedrock_client.invoke_model.return_value = mock_response
        
        result = self.service._call_bedrock_claude(messages, system_prompt)
        
        assert result is None
    
    def test_get_chat_history_success(self):
        """Test successful chat history retrieval"""
        user_id = 'user_123'
        limit = 20
        last_message_id = 'msg_456'
        
        mock_history_result = {
            'success': True,
            'messages': [
                {
                    'message_id': 'msg_1',
                    'role': 'user',
                    'content': 'Hello',
                    'timestamp': datetime.now(timezone.utc).isoformat()
                },
                {
                    'message_id': 'msg_2',
                    'role': 'assistant',
                    'content': 'Hi there!',
                    'timestamp': datetime.now(timezone.utc).isoformat()
                }
            ],
            'has_more': False
        }
        
        with patch('chat_api.chat_memory_manager') as mock_memory:
            mock_memory.get_conversation_history.return_value = mock_history_result
            
            result = self.service.get_chat_history(user_id, limit, last_message_id)
            
            assert result['success'] is True
            assert len(result['messages']) == 2
            assert result['messages'][0]['role'] == 'user'
            assert result['messages'][1]['role'] == 'assistant'
    
    def test_get_chat_history_error(self):
        """Test chat history retrieval with error"""
        user_id = 'user_123'
        
        with patch('chat_api.chat_memory_manager') as mock_memory:
            mock_memory.get_conversation_history.side_effect = Exception("Database error")
            
            result = self.service.get_chat_history(user_id)
            
            assert result['success'] is False
            assert 'error' in result
            assert result['messages'] == []
    
    def test_clear_conversation_success(self):
        """Test successful conversation clearing"""
        user_id = 'user_123'
        
        with patch('chat_api.chat_memory_manager') as mock_memory:
            mock_memory.clear_recent_messages.return_value = True
            
            result = self.service.clear_conversation(user_id)
            
            assert result['success'] is True
            assert 'cleared' in result['message']
    
    def test_clear_conversation_failure(self):
        """Test conversation clearing failure"""
        user_id = 'user_123'
        
        with patch('chat_api.chat_memory_manager') as mock_memory:
            mock_memory.clear_recent_messages.return_value = False
            
            result = self.service.clear_conversation(user_id)
            
            assert result['success'] is False
            assert 'Failed to clear' in result['error']
    
    def test_get_memory_stats_success(self):
        """Test successful memory stats retrieval"""
        user_id = 'user_123'
        mock_stats = {
            'recent_messages_count': 10,
            'total_messages_count': 100,
            'cache_size_bytes': 1024
        }
        
        with patch('chat_api.chat_memory_manager') as mock_memory:
            mock_memory.get_memory_stats.return_value = mock_stats
            
            result = self.service.get_memory_stats(user_id)
            
            assert result['success'] is True
            assert result['stats'] == mock_stats
    
    def test_archive_old_messages_success(self):
        """Test successful message archiving"""
        user_id = 'user_123'
        days_to_keep = 30
        
        mock_archive_result = {
            'success': True,
            'archived_count': 50,
            'message': 'Messages archived successfully'
        }
        
        with patch('chat_api.chat_memory_manager') as mock_memory:
            mock_memory.archive_old_messages.return_value = mock_archive_result
            
            result = self.service.archive_old_messages(user_id, days_to_keep)
            
            assert result['success'] is True
            assert result['archived_count'] == 50


class TestChatAPILambdaHandler:
    """Test cases for lambda_handler function"""
    
    def test_lambda_handler_send_message(self):
        """Test lambda handler for POST /chat/message"""
        with patch('chat_api.chat_service') as mock_service:
            mock_service.send_message.return_value = {
                'success': True,
                'message_id': 'msg_123',
                'response': 'AI response',
                'sources': []
            }
            
            event = {
                'httpMethod': 'POST',
                'path': '/chat/message',
                'body': json.dumps({
                    'user_id': 'user_123',
                    'message': 'Hello',
                    'session_id': 'session_456'
                })
            }
            context = MagicMock()
            
            result = lambda_handler(event, context)
            
            assert result['statusCode'] == 200
            response_body = json.loads(result['body'])
            assert response_body['success'] is True
            assert 'message_id' in response_body
            mock_service.send_message.assert_called_once_with('user_123', 'Hello', 'session_456')
    
    def test_lambda_handler_send_message_missing_fields(self):
        """Test lambda handler for send message with missing required fields"""
        event = {
            'httpMethod': 'POST',
            'path': '/chat/message',
            'body': json.dumps({
                'user_id': 'user_123'
                # Missing message field
            })
        }
        context = MagicMock()
        
        result = lambda_handler(event, context)
        
        assert result['statusCode'] == 400
        response_body = json.loads(result['body'])
        assert response_body['success'] is False
        assert 'user_id and message are required' in response_body['error']
    
    def test_lambda_handler_get_chat_history(self):
        """Test lambda handler for GET /chat/history"""
        with patch('chat_api.chat_service') as mock_service:
            mock_service.get_chat_history.return_value = {
                'success': True,
                'messages': []
            }
            
            event = {
                'httpMethod': 'GET',
                'path': '/chat/history',
                'queryStringParameters': {
                    'user_id': 'user_123',
                    'limit': '20',
                    'last_message_id': 'msg_456'
                }
            }
            context = MagicMock()
            
            result = lambda_handler(event, context)
            
            assert result['statusCode'] == 200
            mock_service.get_chat_history.assert_called_once_with('user_123', 20, 'msg_456')
    
    def test_lambda_handler_get_chat_history_missing_user_id(self):
        """Test lambda handler for get chat history with missing user_id"""
        event = {
            'httpMethod': 'GET',
            'path': '/chat/history',
            'queryStringParameters': {}
        }
        context = MagicMock()
        
        result = lambda_handler(event, context)
        
        assert result['statusCode'] == 400
        response_body = json.loads(result['body'])
        assert 'user_id is required' in response_body['error']
    
    def test_lambda_handler_clear_conversation(self):
        """Test lambda handler for DELETE /chat/conversation"""
        with patch('chat_api.chat_service') as mock_service:
            mock_service.clear_conversation.return_value = {
                'success': True,
                'message': 'Conversation cleared'
            }
            
            event = {
                'httpMethod': 'DELETE',
                'path': '/chat/conversation',
                'body': json.dumps({'user_id': 'user_123'})
            }
            context = MagicMock()
            
            result = lambda_handler(event, context)
            
            assert result['statusCode'] == 200
            mock_service.clear_conversation.assert_called_once_with('user_123')
    
    def test_lambda_handler_get_memory_stats(self):
        """Test lambda handler for GET /chat/memory/stats"""
        with patch('chat_api.chat_service') as mock_service:
            mock_service.get_memory_stats.return_value = {
                'success': True,
                'stats': {'message_count': 10}
            }
            
            event = {
                'httpMethod': 'GET',
                'path': '/chat/memory/stats',
                'queryStringParameters': {'user_id': 'user_123'}
            }
            context = MagicMock()
            
            result = lambda_handler(event, context)
            
            assert result['statusCode'] == 200
            mock_service.get_memory_stats.assert_called_once_with('user_123')
    
    def test_lambda_handler_archive_messages(self):
        """Test lambda handler for POST /chat/archive"""
        with patch('chat_api.chat_service') as mock_service:
            mock_service.archive_old_messages.return_value = {
                'success': True,
                'archived_count': 25
            }
            
            event = {
                'httpMethod': 'POST',
                'path': '/chat/archive',
                'body': json.dumps({
                    'user_id': 'user_123',
                    'days_to_keep': 30
                })
            }
            context = MagicMock()
            
            result = lambda_handler(event, context)
            
            assert result['statusCode'] == 200
            mock_service.archive_old_messages.assert_called_once_with('user_123', 30)
    
    def test_lambda_handler_options_request(self):
        """Test lambda handler for OPTIONS request (CORS)"""
        event = {'httpMethod': 'OPTIONS'}
        context = MagicMock()
        
        result = lambda_handler(event, context)
        
        assert result['statusCode'] == 200
        assert 'Access-Control-Allow-Origin' in result['headers']
        assert 'Access-Control-Allow-Methods' in result['headers']
    
    def test_lambda_handler_invalid_json(self):
        """Test lambda handler with invalid JSON"""
        event = {
            'httpMethod': 'POST',
            'path': '/chat/message',
            'body': 'invalid json'
        }
        context = MagicMock()
        
        result = lambda_handler(event, context)
        
        assert result['statusCode'] == 400
        response_body = json.loads(result['body'])
        assert 'Invalid JSON' in response_body['error']
    
    def test_lambda_handler_endpoint_not_found(self):
        """Test lambda handler with unknown endpoint"""
        event = {
            'httpMethod': 'GET',
            'path': '/unknown'
        }
        context = MagicMock()
        
        result = lambda_handler(event, context)
        
        assert result['statusCode'] == 404
        response_body = json.loads(result['body'])
        assert 'Endpoint not found' in response_body['error']
    
    def test_lambda_handler_exception_handling(self):
        """Test lambda handler exception handling"""
        with patch('chat_api.chat_service') as mock_service:
            mock_service.send_message.side_effect = Exception("Service error")
            
            event = {
                'httpMethod': 'POST',
                'path': '/chat/message',
                'body': json.dumps({
                    'user_id': 'user_123',
                    'message': 'Hello'
                })
            }
            context = MagicMock()
            
            result = lambda_handler(event, context)
            
            assert result['statusCode'] == 500
            response_body = json.loads(result['body'])
            assert 'Internal server error' in response_body['error']


if __name__ == '__main__':
    pytest.main([__file__])