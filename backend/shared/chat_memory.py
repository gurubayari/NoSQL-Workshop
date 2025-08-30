"""
Chat Memory Management System for AWS NoSQL Workshop
Manages conversation context, message caching, and automatic archival
"""
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
import uuid
from collections import deque

try:
    from .config import config
    from .database import (
        get_dynamodb_table, cache_get, cache_set, cache_delete, 
        get_cache_key, db
    )
except ImportError:
    from config import config
    from database import (
        get_dynamodb_table, cache_get, cache_set, cache_delete,
        get_cache_key, db
    )

logger = logging.getLogger(__name__)

class ChatMemoryManager:
    """Manages chat memory with ElastiCache for recent messages and DynamoDB for long-term storage"""
    
    def __init__(self):
        self.chat_history_table = get_dynamodb_table(config.CHAT_HISTORY_TABLE)
        self.max_recent_messages = 10
        self.cache_ttl = config.CHAT_CACHE_TTL_SECONDS
        self.long_term_retention_days = 90
        
        logger.info(f"Initialized ChatMemoryManager with {self.max_recent_messages} recent messages cache")
    
    def add_message(self, user_id: str, message: Dict[str, Any]) -> bool:
        """
        Add a message to both cache and long-term storage
        
        Args:
            user_id: User identifier
            message: Message data with role, content, timestamp, etc.
            
        Returns:
            Success status
        """
        try:
            # Ensure message has required fields
            if 'message_id' not in message:
                message['message_id'] = str(uuid.uuid4())
            
            if 'timestamp' not in message:
                message['timestamp'] = datetime.utcnow().isoformat()
            
            # Store in DynamoDB for long-term storage
            success = self._store_message_long_term(user_id, message)
            if not success:
                logger.error(f"Failed to store message in long-term storage for user {user_id}")
                return False
            
            # Update recent messages cache
            self._update_recent_messages_cache(user_id, message)
            
            logger.debug(f"Added message {message['message_id']} for user {user_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to add message for user {user_id}: {e}")
            return False
    
    def get_recent_messages(self, user_id: str) -> List[Dict[str, Any]]:
        """
        Get recent messages from cache (last 10 messages)
        
        Args:
            user_id: User identifier
            
        Returns:
            List of recent messages in chronological order
        """
        try:
            cache_key = self._get_recent_messages_cache_key(user_id)
            cached_data = cache_get(cache_key)
            
            if cached_data:
                conversation_data = json.loads(cached_data)
                messages = conversation_data.get('messages', [])
                logger.debug(f"Retrieved {len(messages)} recent messages from cache for user {user_id}")
                return messages
            
            # If cache is empty, try to populate from recent DynamoDB entries
            recent_messages = self._get_recent_messages_from_db(user_id, self.max_recent_messages)
            if recent_messages:
                self._cache_recent_messages(user_id, recent_messages)
                logger.debug(f"Populated cache with {len(recent_messages)} messages from DB for user {user_id}")
                return recent_messages
            
            return []
            
        except Exception as e:
            logger.error(f"Failed to get recent messages for user {user_id}: {e}")
            return []
    
    def get_conversation_history(
        self, 
        user_id: str, 
        limit: int = 50, 
        last_message_id: Optional[str] = None,
        include_recent: bool = True
    ) -> Dict[str, Any]:
        """
        Get conversation history with pagination support
        
        Args:
            user_id: User identifier
            limit: Maximum number of messages to return
            last_message_id: Last message ID for pagination
            include_recent: Whether to include recent cached messages
            
        Returns:
            Conversation history with pagination info
        """
        try:
            messages = []
            has_more = False
            next_message_id = None
            
            # Get recent messages from cache first if requested
            if include_recent and not last_message_id:
                recent_messages = self.get_recent_messages(user_id)
                messages.extend(recent_messages)
                limit -= len(recent_messages)
            
            # Get additional messages from DynamoDB if needed
            if limit > 0:
                db_result = self._get_messages_from_db(user_id, limit, last_message_id, exclude_recent=include_recent)
                
                if db_result['messages']:
                    # Avoid duplicates if we included recent messages
                    if include_recent and not last_message_id:
                        recent_message_ids = {msg['message_id'] for msg in messages}
                        db_messages = [msg for msg in db_result['messages'] if msg['message_id'] not in recent_message_ids]
                    else:
                        db_messages = db_result['messages']
                    
                    messages.extend(db_messages)
                
                has_more = db_result['has_more']
                next_message_id = db_result['last_message_id']
            
            # Sort messages chronologically
            messages.sort(key=lambda x: x.get('timestamp', ''))
            
            return {
                'success': True,
                'messages': messages,
                'total_returned': len(messages),
                'has_more': has_more,
                'last_message_id': next_message_id
            }
            
        except Exception as e:
            logger.error(f"Failed to get conversation history for user {user_id}: {e}")
            return {
                'success': False,
                'error': str(e),
                'messages': []
            }
    
    def build_conversation_context(
        self, 
        user_id: str, 
        max_context_messages: int = 10,
        include_system_messages: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Build conversation context for AI responses
        
        Args:
            user_id: User identifier
            max_context_messages: Maximum number of messages to include in context
            include_system_messages: Whether to include system messages
            
        Returns:
            List of messages formatted for AI context
        """
        try:
            # Get recent messages
            recent_messages = self.get_recent_messages(user_id)
            
            # Filter and format messages for AI context
            context_messages = []
            
            for message in recent_messages[-max_context_messages:]:
                role = message.get('role', '')
                content = message.get('content', '')
                
                # Skip empty messages or system messages if not requested
                if not content or (role == 'system' and not include_system_messages):
                    continue
                
                # Format for AI consumption
                context_message = {
                    'role': role,
                    'content': content
                }
                
                # Add metadata if available
                metadata = message.get('metadata', {})
                if metadata:
                    context_message['metadata'] = metadata
                
                context_messages.append(context_message)
            
            logger.debug(f"Built context with {len(context_messages)} messages for user {user_id}")
            return context_messages
            
        except Exception as e:
            logger.error(f"Failed to build conversation context for user {user_id}: {e}")
            return []
    
    def clear_recent_messages(self, user_id: str) -> bool:
        """
        Clear recent messages from cache
        
        Args:
            user_id: User identifier
            
        Returns:
            Success status
        """
        try:
            cache_key = self._get_recent_messages_cache_key(user_id)
            success = cache_delete(cache_key)
            
            if success:
                logger.info(f"Cleared recent messages cache for user {user_id}")
            else:
                logger.warning(f"Failed to clear recent messages cache for user {user_id}")
            
            return success
            
        except Exception as e:
            logger.error(f"Failed to clear recent messages for user {user_id}: {e}")
            return False
    
    def archive_old_messages(self, user_id: str, days_to_keep: int = None) -> Dict[str, Any]:
        """
        Archive old messages by updating TTL (automatic cleanup)
        
        Args:
            user_id: User identifier
            days_to_keep: Number of days to keep messages (default from config)
            
        Returns:
            Archive operation result
        """
        try:
            days_to_keep = days_to_keep or self.long_term_retention_days
            cutoff_date = datetime.utcnow() - timedelta(days=days_to_keep)
            
            # Query old messages
            response = self.chat_history_table.query(
                KeyConditionExpression='user_id = :user_id',
                FilterExpression='#ts < :cutoff_date',
                ExpressionAttributeNames={'#ts': 'timestamp'},
                ExpressionAttributeValues={
                    ':user_id': user_id,
                    ':cutoff_date': cutoff_date.isoformat()
                }
            )
            
            old_messages = response.get('Items', [])
            
            if not old_messages:
                return {
                    'success': True,
                    'archived_count': 0,
                    'message': 'No old messages to archive'
                }
            
            # Update TTL for old messages (they will be automatically deleted)
            archived_count = 0
            for message in old_messages:
                try:
                    # Set TTL to expire in 24 hours
                    expire_time = int((datetime.utcnow() + timedelta(hours=24)).timestamp())
                    
                    self.chat_history_table.update_item(
                        Key={
                            'user_id': message['user_id'],
                            'message_id': message['message_id']
                        },
                        UpdateExpression='SET #ttl = :ttl',
                        ExpressionAttributeNames={'#ttl': 'ttl'},
                        ExpressionAttributeValues={':ttl': expire_time}
                    )
                    
                    archived_count += 1
                    
                except Exception as e:
                    logger.warning(f"Failed to archive message {message['message_id']}: {e}")
            
            logger.info(f"Archived {archived_count} old messages for user {user_id}")
            
            return {
                'success': True,
                'archived_count': archived_count,
                'cutoff_date': cutoff_date.isoformat()
            }
            
        except Exception as e:
            logger.error(f"Failed to archive old messages for user {user_id}: {e}")
            return {
                'success': False,
                'error': str(e),
                'archived_count': 0
            }
    
    def get_memory_stats(self, user_id: str) -> Dict[str, Any]:
        """
        Get memory usage statistics for a user
        
        Args:
            user_id: User identifier
            
        Returns:
            Memory usage statistics
        """
        try:
            # Get recent messages count from cache
            recent_messages = self.get_recent_messages(user_id)
            recent_count = len(recent_messages)
            
            # Get total messages count from DynamoDB
            response = self.chat_history_table.query(
                KeyConditionExpression='user_id = :user_id',
                ExpressionAttributeValues={':user_id': user_id},
                Select='COUNT'
            )
            
            total_count = response.get('Count', 0)
            
            # Calculate cache hit ratio (approximate)
            cache_key = self._get_recent_messages_cache_key(user_id)
            cache_exists = cache_get(cache_key) is not None
            
            return {
                'user_id': user_id,
                'recent_messages_count': recent_count,
                'total_messages_count': total_count,
                'cache_active': cache_exists,
                'max_recent_messages': self.max_recent_messages,
                'cache_ttl_seconds': self.cache_ttl,
                'long_term_retention_days': self.long_term_retention_days
            }
            
        except Exception as e:
            logger.error(f"Failed to get memory stats for user {user_id}: {e}")
            return {
                'user_id': user_id,
                'error': str(e)
            }
    
    def _store_message_long_term(self, user_id: str, message: Dict[str, Any]) -> bool:
        """Store message in DynamoDB for long-term storage"""
        try:
            # Prepare item for DynamoDB
            message_item = {
                'user_id': user_id,
                'message_id': message['message_id'],
                'timestamp': message['timestamp'],
                'role': message.get('role', 'user'),
                'content': message.get('content', ''),
                'metadata': message.get('metadata', {}),
                'ttl': int((datetime.utcnow() + timedelta(days=self.long_term_retention_days)).timestamp())
            }
            
            self.chat_history_table.put_item(Item=message_item)
            return True
            
        except Exception as e:
            logger.error(f"Failed to store message in DynamoDB: {e}")
            return False
    
    def _update_recent_messages_cache(self, user_id: str, new_message: Dict[str, Any]) -> bool:
        """Update recent messages cache with new message"""
        try:
            # Get current cached messages
            recent_messages = self.get_recent_messages(user_id)
            
            # Add new message
            recent_messages.append(new_message)
            
            # Keep only the last N messages
            if len(recent_messages) > self.max_recent_messages:
                recent_messages = recent_messages[-self.max_recent_messages:]
            
            # Cache updated messages
            return self._cache_recent_messages(user_id, recent_messages)
            
        except Exception as e:
            logger.error(f"Failed to update recent messages cache: {e}")
            return False
    
    def _cache_recent_messages(self, user_id: str, messages: List[Dict[str, Any]]) -> bool:
        """Cache recent messages in ElastiCache"""
        try:
            conversation_data = {
                'user_id': user_id,
                'messages': messages,
                'updated_at': datetime.utcnow().isoformat(),
                'message_count': len(messages)
            }
            
            cache_key = self._get_recent_messages_cache_key(user_id)
            return cache_set(cache_key, json.dumps(conversation_data), self.cache_ttl)
            
        except Exception as e:
            logger.error(f"Failed to cache recent messages: {e}")
            return False
    
    def _get_recent_messages_from_db(self, user_id: str, limit: int) -> List[Dict[str, Any]]:
        """Get recent messages from DynamoDB"""
        try:
            response = self.chat_history_table.query(
                KeyConditionExpression='user_id = :user_id',
                ExpressionAttributeValues={':user_id': user_id},
                ScanIndexForward=False,  # Most recent first
                Limit=limit
            )
            
            messages = []
            for item in reversed(response.get('Items', [])):  # Reverse for chronological order
                messages.append({
                    'message_id': item['message_id'],
                    'role': item['role'],
                    'content': item['content'],
                    'timestamp': item['timestamp'],
                    'metadata': item.get('metadata', {})
                })
            
            return messages
            
        except Exception as e:
            logger.error(f"Failed to get recent messages from DB: {e}")
            return []
    
    def _get_messages_from_db(
        self, 
        user_id: str, 
        limit: int, 
        last_message_id: Optional[str] = None,
        exclude_recent: bool = False
    ) -> Dict[str, Any]:
        """Get messages from DynamoDB with pagination"""
        try:
            query_params = {
                'KeyConditionExpression': 'user_id = :user_id',
                'ExpressionAttributeValues': {':user_id': user_id},
                'ScanIndexForward': False,  # Most recent first
                'Limit': limit
            }
            
            # Add pagination if specified
            if last_message_id:
                query_params['ExclusiveStartKey'] = {
                    'user_id': user_id,
                    'message_id': last_message_id
                }
            
            # Exclude recent messages if requested (to avoid duplicates with cache)
            if exclude_recent:
                recent_cutoff = datetime.utcnow() - timedelta(seconds=self.cache_ttl)
                query_params['FilterExpression'] = '#ts < :cutoff'
                query_params['ExpressionAttributeNames'] = {'#ts': 'timestamp'}
                query_params['ExpressionAttributeValues'][':cutoff'] = recent_cutoff.isoformat()
            
            response = self.chat_history_table.query(**query_params)
            
            messages = []
            for item in reversed(response.get('Items', [])):  # Reverse for chronological order
                messages.append({
                    'message_id': item['message_id'],
                    'role': item['role'],
                    'content': item['content'],
                    'timestamp': item['timestamp'],
                    'metadata': item.get('metadata', {})
                })
            
            return {
                'messages': messages,
                'has_more': 'LastEvaluatedKey' in response,
                'last_message_id': response.get('LastEvaluatedKey', {}).get('message_id')
            }
            
        except Exception as e:
            logger.error(f"Failed to get messages from DB: {e}")
            return {
                'messages': [],
                'has_more': False,
                'last_message_id': None
            }
    
    def _get_recent_messages_cache_key(self, user_id: str) -> str:
        """Get cache key for recent messages"""
        return get_cache_key("chat_recent", user_id)

# Global chat memory manager instance
chat_memory_manager = ChatMemoryManager()