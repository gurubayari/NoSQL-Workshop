"""
Comprehensive error handling utilities for Unicorn E-Commerce Lambda functions.
Provides standardized error responses, logging, and monitoring integration.
"""

import json
import logging
from typing import Dict, Any, Optional, Union
from enum import Enum
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger(__name__)

class ErrorCode(Enum):
    """Standardized error codes for the application."""
    
    # Authentication & Authorization Errors (1000-1099)
    UNAUTHORIZED = "AUTH_001"
    FORBIDDEN = "AUTH_002"
    TOKEN_EXPIRED = "AUTH_003"
    INVALID_TOKEN = "AUTH_004"
    USER_NOT_FOUND = "AUTH_005"
    
    # Validation Errors (1100-1199)
    INVALID_INPUT = "VAL_001"
    MISSING_REQUIRED_FIELD = "VAL_002"
    INVALID_FORMAT = "VAL_003"
    VALUE_OUT_OF_RANGE = "VAL_004"
    DUPLICATE_VALUE = "VAL_005"
    
    # Business Logic Errors (1200-1299)
    PRODUCT_NOT_FOUND = "BIZ_001"
    INSUFFICIENT_INVENTORY = "BIZ_002"
    ORDER_NOT_FOUND = "BIZ_003"
    CART_EMPTY = "BIZ_004"
    REVIEW_NOT_FOUND = "BIZ_005"
    INVALID_RATING = "BIZ_006"
    SEARCH_FAILED = "BIZ_007"
    
    # Database Errors (1300-1399)
    DATABASE_CONNECTION_ERROR = "DB_001"
    DATABASE_TIMEOUT = "DB_002"
    DATABASE_CONSTRAINT_VIOLATION = "DB_003"
    ITEM_NOT_FOUND = "DB_004"
    TRANSACTION_FAILED = "DB_005"
    
    # External Service Errors (1400-1499)
    BEDROCK_API_ERROR = "EXT_001"
    COGNITO_ERROR = "EXT_002"
    ELASTICACHE_ERROR = "EXT_003"
    S3_ERROR = "EXT_004"
    
    # System Errors (1500-1599)
    INTERNAL_SERVER_ERROR = "SYS_001"
    SERVICE_UNAVAILABLE = "SYS_002"
    TIMEOUT = "SYS_003"
    RATE_LIMIT_EXCEEDED = "SYS_004"
    CONFIGURATION_ERROR = "SYS_005"

@dataclass
class ErrorDetails:
    """Structured error details."""
    code: ErrorCode
    message: str
    details: Optional[Dict[str, Any]] = None
    user_message: Optional[str] = None
    retry_after: Optional[int] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result = {
            'code': self.code.value,
            'message': self.message
        }
        
        if self.user_message:
            result['user_message'] = self.user_message
        if self.details:
            result['details'] = self.details
        if self.retry_after:
            result['retry_after'] = self.retry_after
            
        return result

class UnicornECommerceException(Exception):
    """Base exception class for Unicorn E-Commerce application."""
    
    def __init__(self, error_details: ErrorDetails, status_code: int = 500):
        self.error_details = error_details
        self.status_code = status_code
        super().__init__(error_details.message)

class AuthenticationError(UnicornECommerceException):
    """Authentication-related errors."""
    
    def __init__(self, error_details: ErrorDetails):
        super().__init__(error_details, 401)

class AuthorizationError(UnicornECommerceException):
    """Authorization-related errors."""
    
    def __init__(self, error_details: ErrorDetails):
        super().__init__(error_details, 403)

class ValidationError(UnicornECommerceException):
    """Input validation errors."""
    
    def __init__(self, error_details: ErrorDetails):
        super().__init__(error_details, 400)

class BusinessLogicError(UnicornECommerceException):
    """Business logic errors."""
    
    def __init__(self, error_details: ErrorDetails):
        super().__init__(error_details, 422)

class DatabaseError(UnicornECommerceException):
    """Database-related errors."""
    
    def __init__(self, error_details: ErrorDetails):
        super().__init__(error_details, 500)

class ExternalServiceError(UnicornECommerceException):
    """External service errors."""
    
    def __init__(self, error_details: ErrorDetails):
        super().__init__(error_details, 502)

class RateLimitError(UnicornECommerceException):
    """Rate limiting errors."""
    
    def __init__(self, error_details: ErrorDetails):
        super().__init__(error_details, 429)

def create_error_response(error: Union[UnicornECommerceException, Exception], 
                         request_id: Optional[str] = None) -> Dict[str, Any]:
    """Create standardized error response."""
    
    if isinstance(error, UnicornECommerceException):
        status_code = error.status_code
        error_body = error.error_details.to_dict()
    else:
        # Handle unexpected exceptions
        status_code = 500
        error_body = ErrorDetails(
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            message="An unexpected error occurred",
            user_message="We're experiencing technical difficulties. Please try again later."
        ).to_dict()
        
        # Log the unexpected error
        logger.error(f"Unexpected error: {str(error)}", exc_info=True)
    
    # Add request ID and timestamp
    error_body['timestamp'] = datetime.utcnow().isoformat()
    if request_id:
        error_body['request_id'] = request_id
    
    return {
        'statusCode': status_code,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token',
            'Access-Control-Allow-Methods': 'GET,POST,PUT,DELETE,OPTIONS'
        },
        'body': json.dumps(error_body)
    }

def validate_required_fields(data: Dict[str, Any], required_fields: list) -> None:
    """Validate that all required fields are present."""
    missing_fields = [field for field in required_fields if field not in data or data[field] is None]
    
    if missing_fields:
        raise ValidationError(ErrorDetails(
            code=ErrorCode.MISSING_REQUIRED_FIELD,
            message=f"Missing required fields: {', '.join(missing_fields)}",
            user_message="Please provide all required information.",
            details={'missing_fields': missing_fields}
        ))

def validate_email_format(email: str) -> None:
    """Validate email format."""
    import re
    
    email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    if not re.match(email_pattern, email):
        raise ValidationError(ErrorDetails(
            code=ErrorCode.INVALID_FORMAT,
            message="Invalid email format",
            user_message="Please provide a valid email address."
        ))

def validate_rating(rating: Union[int, float]) -> None:
    """Validate product rating."""
    if not isinstance(rating, (int, float)) or rating < 1 or rating > 5:
        raise ValidationError(ErrorDetails(
            code=ErrorCode.INVALID_RATING,
            message="Rating must be between 1 and 5",
            user_message="Please provide a rating between 1 and 5 stars."
        ))

def validate_pagination_params(limit: Optional[int] = None, offset: Optional[int] = None) -> tuple:
    """Validate and normalize pagination parameters."""
    # Default values
    if limit is None:
        limit = 20
    if offset is None:
        offset = 0
    
    # Validate limit
    if not isinstance(limit, int) or limit < 1 or limit > 100:
        raise ValidationError(ErrorDetails(
            code=ErrorCode.VALUE_OUT_OF_RANGE,
            message="Limit must be between 1 and 100",
            user_message="Please specify a valid page size."
        ))
    
    # Validate offset
    if not isinstance(offset, int) or offset < 0:
        raise ValidationError(ErrorDetails(
            code=ErrorCode.VALUE_OUT_OF_RANGE,
            message="Offset must be non-negative",
            user_message="Please specify a valid page offset."
        ))
    
    return limit, offset

def handle_database_error(error: Exception, operation: str, table_name: str) -> None:
    """Handle and convert database errors to application errors."""
    error_message = str(error)
    
    if "ConditionalCheckFailedException" in error_message:
        raise DatabaseError(ErrorDetails(
            code=ErrorCode.DATABASE_CONSTRAINT_VIOLATION,
            message=f"Constraint violation in {operation} on {table_name}",
            user_message="The operation could not be completed due to a data conflict."
        ))
    elif "ResourceNotFoundException" in error_message:
        raise DatabaseError(ErrorDetails(
            code=ErrorCode.ITEM_NOT_FOUND,
            message=f"Item not found in {table_name}",
            user_message="The requested item was not found."
        ))
    elif "ProvisionedThroughputExceededException" in error_message:
        raise DatabaseError(ErrorDetails(
            code=ErrorCode.DATABASE_TIMEOUT,
            message=f"Database throughput exceeded for {table_name}",
            user_message="The service is currently busy. Please try again in a moment.",
            retry_after=5
        ))
    elif "TransactionCanceledException" in error_message:
        raise DatabaseError(ErrorDetails(
            code=ErrorCode.TRANSACTION_FAILED,
            message=f"Transaction failed for {operation} on {table_name}",
            user_message="The operation could not be completed. Please try again."
        ))
    else:
        raise DatabaseError(ErrorDetails(
            code=ErrorCode.DATABASE_CONNECTION_ERROR,
            message=f"Database error in {operation} on {table_name}: {error_message}",
            user_message="We're experiencing database issues. Please try again later."
        ))

def handle_bedrock_error(error: Exception) -> None:
    """Handle Bedrock API errors."""
    error_message = str(error)
    
    if "ThrottlingException" in error_message:
        raise ExternalServiceError(ErrorDetails(
            code=ErrorCode.BEDROCK_API_ERROR,
            message="Bedrock API rate limit exceeded",
            user_message="The AI service is currently busy. Please try again in a moment.",
            retry_after=10
        ))
    elif "ValidationException" in error_message:
        raise ExternalServiceError(ErrorDetails(
            code=ErrorCode.BEDROCK_API_ERROR,
            message="Invalid request to Bedrock API",
            user_message="There was an issue with your request. Please try again."
        ))
    else:
        raise ExternalServiceError(ErrorDetails(
            code=ErrorCode.BEDROCK_API_ERROR,
            message=f"Bedrock API error: {error_message}",
            user_message="The AI service is temporarily unavailable. Please try again later."
        ))

def handle_cognito_error(error: Exception) -> None:
    """Handle Cognito authentication errors."""
    error_message = str(error)
    
    if "UserNotFoundException" in error_message:
        raise AuthenticationError(ErrorDetails(
            code=ErrorCode.USER_NOT_FOUND,
            message="User not found",
            user_message="Invalid username or password."
        ))
    elif "NotAuthorizedException" in error_message:
        raise AuthenticationError(ErrorDetails(
            code=ErrorCode.UNAUTHORIZED,
            message="Authentication failed",
            user_message="Invalid username or password."
        ))
    elif "TokenExpiredException" in error_message:
        raise AuthenticationError(ErrorDetails(
            code=ErrorCode.TOKEN_EXPIRED,
            message="Authentication token expired",
            user_message="Your session has expired. Please log in again."
        ))
    else:
        raise AuthenticationError(ErrorDetails(
            code=ErrorCode.COGNITO_ERROR,
            message=f"Cognito error: {error_message}",
            user_message="Authentication service is temporarily unavailable."
        ))

# Common error instances for reuse
PRODUCT_NOT_FOUND_ERROR = BusinessLogicError(ErrorDetails(
    code=ErrorCode.PRODUCT_NOT_FOUND,
    message="Product not found",
    user_message="The requested product was not found."
))

INSUFFICIENT_INVENTORY_ERROR = BusinessLogicError(ErrorDetails(
    code=ErrorCode.INSUFFICIENT_INVENTORY,
    message="Insufficient inventory",
    user_message="Sorry, this item is currently out of stock."
))

CART_EMPTY_ERROR = BusinessLogicError(ErrorDetails(
    code=ErrorCode.CART_EMPTY,
    message="Shopping cart is empty",
    user_message="Your cart is empty. Please add items before proceeding."
))

UNAUTHORIZED_ERROR = AuthenticationError(ErrorDetails(
    code=ErrorCode.UNAUTHORIZED,
    message="Authentication required",
    user_message="Please log in to access this feature."
))

RATE_LIMIT_EXCEEDED_ERROR = RateLimitError(ErrorDetails(
    code=ErrorCode.RATE_LIMIT_EXCEEDED,
    message="Rate limit exceeded",
    user_message="Too many requests. Please wait a moment before trying again.",
    retry_after=60
))