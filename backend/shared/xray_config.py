"""
AWS X-Ray configuration and utilities for Unicorn E-Commerce Lambda functions.
Provides comprehensive distributed tracing capabilities.
"""

import os
import json
import logging
from typing import Dict, Any, Optional
from aws_xray_sdk.core import xray_recorder, patch_all
from aws_xray_sdk.core.context import Context
from aws_xray_sdk.core.models import http
from aws_xray_sdk.core.plugins import ec2_plugin, ecs_plugin
from aws_xray_sdk.core.sampling.sampling_rule import SamplingRule

logger = logging.getLogger(__name__)

# Configure X-Ray recorder
def configure_xray():
    """Configure X-Ray recorder with custom settings."""
    
    # Set service name from environment or default
    service_name = os.environ.get('AWS_LAMBDA_FUNCTION_NAME', 'unicorn-ecommerce')
    xray_recorder.configure(
        service=service_name,
        plugins=('EC2Plugin', 'ECSPlugin'),
        daemon_address=os.environ.get('_X_AMZN_TRACE_ID'),
        use_ssl=True
    )
    
    # Patch AWS SDK and other libraries
    patch_all()
    
    # Configure sampling rules
    configure_sampling_rules()
    
    logger.info(f"X-Ray configured for service: {service_name}")

def configure_sampling_rules():
    """Configure custom sampling rules for different service patterns."""
    
    # High-priority endpoints (always sample)
    high_priority_rule = {
        "version": 2,
        "default": {
            "fixed_target": 2,
            "rate": 0.1
        },
        "rules": [
            {
                "description": "High priority endpoints",
                "service_name": "*",
                "http_method": "*",
                "url_path": "/api/orders*",
                "fixed_target": 2,
                "rate": 1.0
            },
            {
                "description": "Authentication endpoints",
                "service_name": "*",
                "http_method": "*",
                "url_path": "/api/auth*",
                "fixed_target": 1,
                "rate": 0.5
            },
            {
                "description": "Search endpoints",
                "service_name": "*",
                "http_method": "*",
                "url_path": "/api/search*",
                "fixed_target": 1,
                "rate": 0.3
            },
            {
                "description": "Product endpoints",
                "service_name": "*",
                "http_method": "*",
                "url_path": "/api/products*",
                "fixed_target": 1,
                "rate": 0.2
            }
        ]
    }
    
    try:
        # Set sampling rules if running in Lambda
        if os.environ.get('AWS_LAMBDA_FUNCTION_NAME'):
            xray_recorder.configure(sampling_rules=high_priority_rule)
    except Exception as e:
        logger.warning(f"Failed to configure sampling rules: {e}")

class XRayTracer:
    """Enhanced X-Ray tracing utilities."""
    
    def __init__(self, service_name: str):
        self.service_name = service_name
    
    def trace_database_operation(self, operation: str, table_name: str, 
                               query: Optional[Dict[str, Any]] = None):
        """Create a subsegment for database operations."""
        def decorator(func):
            def wrapper(*args, **kwargs):
                subsegment_name = f"db_{operation}_{table_name}"
                
                with xray_recorder.in_subsegment(subsegment_name) as subsegment:
                    if subsegment:
                        # Add annotations for filtering
                        subsegment.put_annotation('operation', operation)
                        subsegment.put_annotation('table_name', table_name)
                        subsegment.put_annotation('service', self.service_name)
                        
                        # Add metadata for detailed information
                        if query:
                            subsegment.put_metadata('query', query, 'database')
                        
                        # Set namespace for database operations
                        subsegment.namespace = 'aws'
                    
                    try:
                        result = func(*args, **kwargs)
                        
                        if subsegment:
                            # Add success metadata
                            subsegment.put_metadata('status', 'success', 'database')
                            if hasattr(result, '__len__'):
                                subsegment.put_metadata('result_count', len(result), 'database')
                        
                        return result
                        
                    except Exception as e:
                        if subsegment:
                            # Add error information
                            subsegment.put_metadata('error', {
                                'type': type(e).__name__,
                                'message': str(e)
                            }, 'database')
                            subsegment.add_exception(e)
                        raise
            
            return wrapper
        return decorator
    
    def trace_external_service(self, service_name: str, operation: str):
        """Create a subsegment for external service calls."""
        def decorator(func):
            def wrapper(*args, **kwargs):
                subsegment_name = f"{service_name}_{operation}"
                
                with xray_recorder.in_subsegment(subsegment_name) as subsegment:
                    if subsegment:
                        # Add annotations
                        subsegment.put_annotation('service', service_name)
                        subsegment.put_annotation('operation', operation)
                        
                        # Set namespace for AWS services
                        if service_name.lower() in ['bedrock', 'cognito', 'elasticache', 's3']:
                            subsegment.namespace = 'aws'
                        else:
                            subsegment.namespace = 'remote'
                    
                    try:
                        result = func(*args, **kwargs)
                        
                        if subsegment:
                            subsegment.put_metadata('status', 'success', service_name)
                        
                        return result
                        
                    except Exception as e:
                        if subsegment:
                            subsegment.put_metadata('error', {
                                'type': type(e).__name__,
                                'message': str(e)
                            }, service_name)
                            subsegment.add_exception(e)
                        raise
            
            return wrapper
        return decorator
    
    def trace_business_logic(self, operation: str):
        """Create a subsegment for business logic operations."""
        def decorator(func):
            def wrapper(*args, **kwargs):
                subsegment_name = f"business_{operation}"
                
                with xray_recorder.in_subsegment(subsegment_name) as subsegment:
                    if subsegment:
                        subsegment.put_annotation('operation', operation)
                        subsegment.put_annotation('service', self.service_name)
                        subsegment.namespace = 'local'
                    
                    try:
                        result = func(*args, **kwargs)
                        
                        if subsegment:
                            subsegment.put_metadata('status', 'success', 'business')
                        
                        return result
                        
                    except Exception as e:
                        if subsegment:
                            subsegment.put_metadata('error', {
                                'type': type(e).__name__,
                                'message': str(e)
                            }, 'business')
                            subsegment.add_exception(e)
                        raise
            
            return wrapper
        return decorator

def add_http_metadata(event: Dict[str, Any], subsegment: Optional[Any] = None):
    """Add HTTP request metadata to X-Ray trace."""
    if not subsegment:
        subsegment = xray_recorder.current_subsegment()
    
    if not subsegment:
        return
    
    try:
        # Extract HTTP information from API Gateway event
        http_method = event.get('httpMethod')
        path = event.get('path')
        query_params = event.get('queryStringParameters')
        headers = event.get('headers', {})
        
        if http_method and path:
            # Create HTTP metadata
            http_meta = {
                'request': {
                    'method': http_method,
                    'url': path,
                    'user_agent': headers.get('User-Agent', 'unknown')
                }
            }
            
            if query_params:
                http_meta['request']['query_params'] = query_params
            
            # Add client IP if available
            if 'requestContext' in event and 'identity' in event['requestContext']:
                client_ip = event['requestContext']['identity'].get('sourceIp')
                if client_ip:
                    http_meta['request']['client_ip'] = client_ip
            
            subsegment.put_metadata('http', http_meta)
            
            # Add annotations for filtering
            subsegment.put_annotation('http.method', http_method)
            subsegment.put_annotation('http.path', path)
            
    except Exception as e:
        logger.warning(f"Failed to add HTTP metadata: {e}")

def add_user_metadata(user_id: Optional[str], subsegment: Optional[Any] = None):
    """Add user information to X-Ray trace."""
    if not user_id or not subsegment:
        return
    
    try:
        subsegment.put_annotation('user.id', user_id)
        subsegment.put_metadata('user', {'id': user_id}, 'user_info')
    except Exception as e:
        logger.warning(f"Failed to add user metadata: {e}")

def add_business_metadata(operation: str, entity_type: str, entity_id: Optional[str] = None,
                         additional_data: Optional[Dict[str, Any]] = None,
                         subsegment: Optional[Any] = None):
    """Add business-specific metadata to X-Ray trace."""
    if not subsegment:
        subsegment = xray_recorder.current_subsegment()
    
    if not subsegment:
        return
    
    try:
        # Add annotations for filtering
        subsegment.put_annotation('business.operation', operation)
        subsegment.put_annotation('business.entity_type', entity_type)
        
        if entity_id:
            subsegment.put_annotation('business.entity_id', entity_id)
        
        # Add detailed metadata
        business_meta = {
            'operation': operation,
            'entity_type': entity_type
        }
        
        if entity_id:
            business_meta['entity_id'] = entity_id
        
        if additional_data:
            business_meta.update(additional_data)
        
        subsegment.put_metadata('business', business_meta)
        
    except Exception as e:
        logger.warning(f"Failed to add business metadata: {e}")

def create_custom_segment(name: str, trace_id: Optional[str] = None):
    """Create a custom segment for standalone operations."""
    try:
        if trace_id:
            # Continue existing trace
            segment = xray_recorder.begin_segment(name, traceid=trace_id)
        else:
            # Start new trace
            segment = xray_recorder.begin_segment(name)
        
        return segment
    except Exception as e:
        logger.warning(f"Failed to create custom segment: {e}")
        return None

# Initialize X-Ray configuration
configure_xray()

# Create global tracer instance
tracer = XRayTracer('unicorn-ecommerce')

# Export commonly used functions
__all__ = [
    'configure_xray',
    'XRayTracer',
    'tracer',
    'add_http_metadata',
    'add_user_metadata',
    'add_business_metadata',
    'create_custom_segment'
]