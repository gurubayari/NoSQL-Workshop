"""
Unit tests for Chat Memory Management System
Tests message caching, archival, and conversation context building
"""
import pytest
import json
import uuid
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta
import sys
import os

# Add the shared directory to the path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'shared'))

# Mock AWS services before importing
with patch('boto3.client'), patch('boto3.resource'):
    from chat_memory import ChatMemoryManager

class TestChatMemoryManager:
    """Test cases for ChatMemoryManager class"""
    
    @pytest.fixture
    def mock_dependencies(self):
        """Mock all external dependencies"""
        with patch('chat_memory.get_dynamodb_table') as mock_table, \
             patch('chat_memory.cache_get') as mock_cache_get, \
             patch('chat_memory.cache_set') as mock_cache_set, \
             patch('chat_memory.cache_delete') as mock_cache_delete, \
             patch('chat_memory.get_cache_key') as mock_get_cache_key:
            
            # Setup mocks
            mock_dynamodb_table = Mock()
            mock_table.return_value = mock_dynamodb_table
            
            mock_get_cache_key.side_effect = lambda prefix, key: f"test:{prefix}:{key}"
            
            yield {
                'dynamodb_table': mock_dynamodb_table,
                'cache_get': mock_cache_get,
                'cache_set': mock_cache_set,
                'cache_delete': mock_cache_delete,
                'get_cache_key': mock_get_cache_key
            }
    
    @pytest.fixture
    def memory_manager(self, mock_dependencies):
        """Create ChatMemoryManager instance with mocked dependencies"""
        return ChatMemoryManager()
    
    def test_add_message_success(self, memory_manager, mock_dependencies):
        """Test successful message addition"""
        # Setup
        user_id = "test_user_123"
        message = {
            'role': 'user',
            'content': 'Hello, how are you?',
            'metadata': {'session_id': 'session_456'}
        }
        
        # Mock DynamoDB success
        mock_dependencies['dynamodb_table'].put_item.return_value = {}
        
        # Mock cache operations
        mock_dependencies['cache_get'].return_value = json.dumps({
            'user_id': user_id,
            'messages': [],
            'updated_at': datetime.utcnow().isoformat()
        })
        mock_dependencies['cache_set'].return_value = True
        
        # Execute
        result = memory_manager.add_message(user_id, message)
        
        # Assert
        assert result is True
        
        # Verify DynamoDB put_item was called
        mock_dependencies['dynamodb_table'].put_item.assert_called_once()
        call_args = mock_dependencies['dynamodb_table'].put_item.call_args
        stored_item = call_args[1]['Item']
        
        assert stored_item['user_id'] == user_id
        assert stored_item['role'] == 'user'
        assert stored_item['content'] == 'Hello, how are you?'
        assert 'message_id' in stored_item
        assert 'timestamp' in stored_item
        assert 'ttl' in stored_item
        
        # Verify cache was updated
        mock_dependencies['cache_set'].assert_called_once()
    
    def test_add_message_auto_generates_id_and_timestamp(self, memory_manager, mock_dependencies):
        """Test that message ID and timestamp are auto-generated if missing"""
        # Setup
        user_id = "test_user_123"
        message = {
            'role': 'user',
            'content': 'Test message'
        }
        
        mock_dependencies['dynamodb_table'].put_item.return_value = {}
        mock_dependencies['cache_get'].return_value = None
        mock_dependencies['cache_set'].return_value = True
        
        # Execute
        result = memory_manager.add_message(user_id, message)
        
        # Assert
        assert result is True
        
        # Verify auto-generated fields
        call_args = mock_dependencies['dynamodb_table'].put_item.call_args
        stored_item = call_args[1]['Item']
        
        assert 'message_id' in stored_item
        assert 'timestamp' in stored_item
        assert len(stored_item['message_id']) > 0
        assert stored_item['timestamp'] is not None
    
    def test_add_message_dynamodb_failure(self, memory_manager, mock_dependencies):
        """Test message addition when DynamoDB fails"""
        # Setup
        user_id = "test_user_123"
        message = {'role': 'user', 'content': 'Test'}
        
        mock_dependencies['dynamodb_table'].put_item.side_effect = Exception("DynamoDB error")
        
        # Execute
        result = memory_manager.add_message(user_id, message)
        
        # Assert
        assert result is False
    
    def test_get_recent_messages_from_cache(self, memory_manager, mock_dependencies):
        """Test getting recent messages from cache"""
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
        result = memory_manager.get_recent_messages(user_id)
        
        # Assert
        assert result == cached_messages
        mock_dependencies['cache_get'].assert_called_once()
    
    def test_get_recent_messages_cache_miss_populates_from_db(self, memory_manager, mock_dependencies):
        """Test getting recent messages when cache is empty, populates from DB"""
        # Setup
        user_id = "test_user_123"
        
        # Cache miss
        mock_dependencies['cache_get'].return_value = None
        
        # Mock DB response
        db_messages = [
            {
                'message_id': 'msg1',
                'role': 'user',
                'content': 'Hello',
                'timestamp': '2024-01-01T10:00:00Z',
                'metadata': {}
            }
        ]
        
        mock_dependencies['dynamodb_table'].query.return_value = {
            'Items': [
                {
                    'message_id': 'msg1',
                    'role': 'user',
                    'content': 'Hello',
                    'timestamp': '2024-01-01T10:00:00Z',
                    'metadata': {}
                }
            ]
        }
        
        mock_dependencies['cache_set'].return_value = True
        
        # Execute
        result = memory_manager.get_recent_messages(user_id)
        
        # Assert
        assert len(result) == 1
        assert result[0]['message_id'] == 'msg1'
        
        # Verify DB was queried
        mock_dependencies['dynamodb_table'].query.assert_called_once()
        
        # Verify cache was populated
        mock_dependencies['cache_set'].assert_called_once()
    
    def test_get_recent_messages_empty_result(self, memory_manager, mock_dependencies):
        """Test getting recent messages when both cache and DB are empty"""
        # Setup
        user_id = "test_user_123"
        
        mock_dependencies['cache_get'].return_value = None
        mock_dependencies['dynamodb_table'].query.return_value = {'Items': []}
        
        # Execute
        result = memory_manager.get_recent_messages(user_id)
        
        # Assert
        assert result == []
    
    def test_get_conversation_history_with_recent_messages(self, memory_manager, mock_dependencies):
        """Test getting conversation history including recent messages"""
        # Setup
        user_id = "test_user_123"
        limit = 20
        
        # Mock recent messages from cache
        recent_messages = [
            {'message_id': 'recent1', 'timestamp': '2024-01-01T10:00:00Z'},
            {'message_id': 'recent2', 'timestamp': '2024-01-01T10:00:01Z'}
        ]
        
        with patch.object(memory_manager, 'get_recent_messages') as mock_get_recent:
            mock_get_recent.return_value = recent_messages
            
            # Mock additional messages from DB
            with patch.object(memory_manager, '_get_messages_from_db') as mock_get_db:
                mock_get_db.return_value = {
                    'messages': [
                        {'message_id': 'older1', 'timestamp': '2024-01-01T09:00:00Z'}
                    ],
                    'has_more': False,
                    'last_message_id': None
                }
                
                # Execute
                result = memory_manager.get_conversation_history(user_id, limit)
        
        # Assert
        assert result['success'] is True
        assert len(result['messages']) == 3
        assert result['has_more'] is False
        
        # Verify messages are sorted chronologically
        timestamps = [msg['timestamp'] for msg in result['messages']]
        assert timestamps == sorted(timestamps)
    
    def test_get_conversation_history_with_pagination(self, memory_manager, mock_dependencies):
        """Test conversation history with pagination"""
        # Setup
        user_id = "test_user_123"
        limit = 10
        last_message_id = "last_msg_123"
        
        with patch.object(memory_manager, 'get_recent_messages') as mock_get_recent:
            mock_get_recent.return_value = []  # No recent messages for pagination
            
            with patch.object(memory_manager, '_get_messages_from_db') as mock_get_db:
                mock_get_db.return_value = {
                    'messages': [
                        {'message_id': 'msg1', 'timestamp': '2024-01-01T10:00:00Z'}
                    ],
                    'has_more': True,
                    'last_message_id': 'next_msg_id'
                }
                
                # Execute
                result = memory_manager.get_conversation_history(
                    user_id, limit, last_message_id, include_recent=False
                )
        
        # Assert
        assert result['success'] is True
        assert result['has_more'] is True
        assert result['last_message_id'] == 'next_msg_id'
        
        # Verify pagination was passed to DB query
        mock_get_db.assert_called_once_with(user_id, limit, last_message_id, exclude_recent=False)
    
    def test_build_conversation_context(self, memory_manager, mock_dependencies):
        """Test building conversation context for AI"""
        # Setup
        user_id = "test_user_123"
        max_context_messages = 5
        
        recent_messages = [
            {
                'message_id': 'msg1',
                'role': 'user',
                'content': 'Hello',
                'timestamp': '2024-01-01T10:00:00Z',
                'metadata': {'session_id': 'session1'}
            },
            {
                'message_id': 'msg2',
                'role': 'assistant',
                'content': 'Hi there!',
                'timestamp': '2024-01-01T10:00:01Z',
                'metadata': {}
            },
            {
                'message_id': 'msg3',
                'role': 'system',
                'content': 'System message',
                'timestamp': '2024-01-01T10:00:02Z'
            },
            {
                'message_id': 'msg4',
                'role': 'user',
                'content': '',  # Empty content should be skipped
                'timestamp': '2024-01-01T10:00:03Z'
            },
            {
                'message_id': 'msg5',
                'role': 'user',
                'content': 'How are you?',
                'timestamp': '2024-01-01T10:00:04Z'
            }
        ]
        
        with patch.object(memory_manager, 'get_recent_messages') as mock_get_recent:
            mock_get_recent.return_value = recent_messages
            
            # Execute
            result = memory_manager.build_conversation_context(user_id, max_context_messages)
        
        # Assert
        assert len(result) == 3  # Should exclude system message and empty content
        
        # Verify structure
        assert result[0]['role'] == 'user'
        assert result[0]['content'] == 'Hello'
        assert 'metadata' in result[0]
        
        assert result[1]['role'] == 'assistant'
        assert result[1]['content'] == 'Hi there!'
        
        assert result[2]['role'] == 'user'
        assert result[2]['content'] == 'How are you?'
    
    def test_build_conversation_context_include_system_messages(self, memory_manager, mock_dependencies):
        """Test building conversation context including system messages"""
        # Setup
        user_id = "test_user_123"
        
        recent_messages = [
            {
                'role': 'system',
                'content': 'System initialization',
                'timestamp': '2024-01-01T10:00:00Z'
            },
            {
                'role': 'user',
                'content': 'Hello',
                'timestamp': '2024-01-01T10:00:01Z'
            }
        ]
        
        with patch.object(memory_manager, 'get_recent_messages') as mock_get_recent:
            mock_get_recent.return_value = recent_messages
            
            # Execute
            result = memory_manager.build_conversation_context(
                user_id, max_context_messages=10, include_system_messages=True
            )
        
        # Assert
        assert len(result) == 2
        assert result[0]['role'] == 'system'
        assert result[1]['role'] == 'user'
    
    def test_clear_recent_messages_success(self, memory_manager, mock_dependencies):
        """Test successful clearing of recent messages"""
        # Setup
        user_id = "test_user_123"
        mock_dependencies['cache_delete'].return_value = True
        
        # Execute
        result = memory_manager.clear_recent_messages(user_id)
        
        # Assert
        assert result is True
        mock_dependencies['cache_delete'].assert_called_once()
    
    def test_clear_recent_messages_failure(self, memory_manager, mock_dependencies):
        """Test clearing recent messages when cache delete fails"""
        # Setup
        user_id = "test_user_123"
        mock_dependencies['cache_delete'].return_value = False
        
        # Execute
        result = memory_manager.clear_recent_messages(user_id)
        
        # Assert
        assert result is False
    
    def test_archive_old_messages_success(self, memory_manager, mock_dependencies):
        """Test successful archiving of old messages"""
        # Setup
        user_id = "test_user_123"
        days_to_keep = 30
        
        # Mock old messages query
        old_messages = [
            {
                'user_id': user_id,
                'message_id': 'old_msg_1',
                'timestamp': (datetime.utcnow() - timedelta(days=35)).isoformat()
            },
            {
                'user_id': user_id,
                'message_id': 'old_msg_2',
                'timestamp': (datetime.utcnow() - timedelta(days=40)).isoformat()
            }
        ]
        
        mock_dependencies['dynamodb_table'].query.return_value = {
            'Items': old_messages
        }
        
        # Mock update_item success
        mock_dependencies['dynamodb_table'].update_item.return_value = {}
        
        # Execute
        result = memory_manager.archive_old_messages(user_id, days_to_keep)
        
        # Assert
        assert result['success'] is True
        assert result['archived_count'] == 2
        assert 'cutoff_date' in result
        
        # Verify update_item was called for each message
        assert mock_dependencies['dynamodb_table'].update_item.call_count == 2
    
    def test_archive_old_messages_no_old_messages(self, memory_manager, mock_dependencies):
        """Test archiving when no old messages exist"""
        # Setup
        user_id = "test_user_123"
        
        mock_dependencies['dynamodb_table'].query.return_value = {'Items': []}
        
        # Execute
        result = memory_manager.archive_old_messages(user_id)
        
        # Assert
        assert result['success'] is True
        assert result['archived_count'] == 0
        assert 'No old messages' in result['message']
    
    def test_archive_old_messages_partial_failure(self, memory_manager, mock_dependencies):
        """Test archiving with some update failures"""
        # Setup
        user_id = "test_user_123"
        
        old_messages = [
            {'user_id': user_id, 'message_id': 'msg1'},
            {'user_id': user_id, 'message_id': 'msg2'}
        ]
        
        mock_dependencies['dynamodb_table'].query.return_value = {'Items': old_messages}
        
        # Mock update_item with one success and one failure
        def update_side_effect(*args, **kwargs):
            key = kwargs['Key']['message_id']
            if key == 'msg1':
                return {}
            else:
                raise Exception("Update failed")
        
        mock_dependencies['dynamodb_table'].update_item.side_effect = update_side_effect
        
        # Execute
        result = memory_manager.archive_old_messages(user_id)
        
        # Assert
        assert result['success'] is True
        assert result['archived_count'] == 1  # Only one succeeded
    
    def test_get_memory_stats_success(self, memory_manager, mock_dependencies):
        """Test getting memory usage statistics"""
        # Setup
        user_id = "test_user_123"
        
        # Mock recent messages
        with patch.object(memory_manager, 'get_recent_messages') as mock_get_recent:
            mock_get_recent.return_value = [
                {'message_id': 'msg1'},
                {'message_id': 'msg2'}
            ]
            
            # Mock total count query
            mock_dependencies['dynamodb_table'].query.return_value = {'Count': 25}
            
            # Mock cache check
            mock_dependencies['cache_get'].return_value = '{"messages": []}'
            
            # Execute
            result = memory_manager.get_memory_stats(user_id)
        
        # Assert
        assert result['user_id'] == user_id
        assert result['recent_messages_count'] == 2
        assert result['total_messages_count'] == 25
        assert result['cache_active'] is True
        assert result['max_recent_messages'] == memory_manager.max_recent_messages
        assert result['cache_ttl_seconds'] == memory_manager.cache_ttl
        assert result['long_term_retention_days'] == memory_manager.long_term_retention_days
    
    def test_get_memory_stats_no_cache(self, memory_manager, mock_dependencies):
        """Test memory stats when cache is not active"""
        # Setup
        user_id = "test_user_123"
        
        with patch.object(memory_manager, 'get_recent_messages') as mock_get_recent:
            mock_get_recent.return_value = []
            
            mock_dependencies['dynamodb_table'].query.return_value = {'Count': 10}
            mock_dependencies['cache_get'].return_value = None  # No cache
            
            # Execute
            result = memory_manager.get_memory_stats(user_id)
        
        # Assert
        assert result['cache_active'] is False
    
    def test_update_recent_messages_cache_with_limit(self, memory_manager, mock_dependencies):
        """Test that recent messages cache respects the limit"""
        # Setup
        user_id = "test_user_123"
        
        # Create more messages than the limit
        existing_messages = [
            {'message_id': f'msg{i}', 'timestamp': f'2024-01-01T10:00:{i:02d}Z'}
            for i in range(12)  # More than max_recent_messages (10)
        ]
        
        new_message = {
            'message_id': 'new_msg',
            'timestamp': '2024-01-01T10:00:15Z'
        }
        
        # Mock getting existing messages
        with patch.object(memory_manager, 'get_recent_messages') as mock_get_recent:
            mock_get_recent.return_value = existing_messages
            
            mock_dependencies['cache_set'].return_value = True
            
            # Execute
            result = memory_manager._update_recent_messages_cache(user_id, new_message)
        
        # Assert
        assert result is True
        
        # Verify cache_set was called
        mock_dependencies['cache_set'].assert_called_once()
        
        # Verify the cached data has the right number of messages
        call_args = mock_dependencies['cache_set'].call_args
        cached_data = json.loads(call_args[0][1])
        
        assert len(cached_data['messages']) == memory_manager.max_recent_messages
        assert cached_data['messages'][-1]['message_id'] == 'new_msg'  # New message should be last
    
    def test_get_messages_from_db_with_pagination(self, memory_manager, mock_dependencies):
        """Test getting messages from DB with pagination parameters"""
        # Setup
        user_id = "test_user_123"
        limit = 10
        last_message_id = "last_msg_id"
        
        mock_dependencies['dynamodb_table'].query.return_value = {
            'Items': [
                {
                    'message_id': 'msg1',
                    'role': 'user',
                    'content': 'Hello',
                    'timestamp': '2024-01-01T10:00:00Z',
                    'metadata': {}
                }
            ],
            'LastEvaluatedKey': {
                'user_id': user_id,
                'message_id': 'next_msg_id'
            }
        }
        
        # Execute
        result = memory_manager._get_messages_from_db(user_id, limit, last_message_id)
        
        # Assert
        assert len(result['messages']) == 1
        assert result['has_more'] is True
        assert result['last_message_id'] == 'next_msg_id'
        
        # Verify query parameters
        call_args = mock_dependencies['dynamodb_table'].query.call_args[1]
        assert 'ExclusiveStartKey' in call_args
        assert call_args['ExclusiveStartKey']['message_id'] == last_message_id
    
    def test_get_messages_from_db_exclude_recent(self, memory_manager, mock_dependencies):
        """Test getting messages from DB excluding recent ones"""
        # Setup
        user_id = "test_user_123"
        limit = 10
        
        mock_dependencies['dynamodb_table'].query.return_value = {
            'Items': [],
            'Count': 0
        }
        
        # Execute
        result = memory_manager._get_messages_from_db(user_id, limit, exclude_recent=True)
        
        # Assert
        assert result['messages'] == []
        
        # Verify filter expression was added
        call_args = mock_dependencies['dynamodb_table'].query.call_args[1]
        assert 'FilterExpression' in call_args
        assert 'ExpressionAttributeNames' in call_args
        assert '#ts' in call_args['ExpressionAttributeNames']

if __name__ == '__main__':
    pytest.main([__file__])