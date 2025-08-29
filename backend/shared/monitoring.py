"""
Comprehensive monitoring and logging utilities for Unicorn E-Commerce Lambda functions.
Provides CloudWatch logging, X-Ray tracing, and performance monitoring capabilities.
"""

import json
import time
import logging
import traceback
from datetime import datetime
from functools import wraps
from typing import Dict, Any, Optional, Callable
import boto3
from aws_xray_sdk.core import xray_recorder, patch_all
from aws_xray_sdk.core.context import Context

# Patch AWS SDK calls for X-Ray tracing
patch_all()

# Configure structured logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Remove default handler and add custom formatter
if logger.handlers:
    for handler in logger.handlers:
        logger.removeHandler(handler)

# Create custom handler with structured logging
handler = logging.StreamHandler()
formatter = logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
handler.setFormatter(formatter)
logger.addHandler(handler)

# CloudWatch client for custom metrics
cloudwatch = boto3.client('cloudwatch')

class PerformanceMonitor:
    """Performance monitoring and metrics collection."""
    
    def __init__(self, service_name: str, environment: str):
        self.service_name = service_name
        self.environment = environment
        self.namespace = f"UnicornECommerce/{environment}"
    
    def put_metric(self, metric_name: str, value: float, unit: str = 'Count', 
                   dimensions: Optional[Dict[str, str]] = None):
        """Put custom metric to CloudWatch."""
        try:
            metric_data = {
                'MetricName': metric_name,
                'Value': value,
                'Unit': unit,
                'Timestamp': datetime.utcnow()
            }
            
            if dimensions:
                metric_data['Dimensions'] = [
                    {'Name': k, 'Value': v} for k, v in dimensions.items()
                ]
            
            cloudwatch.put_metric_data(
                Namespace=self.namespace,
                MetricData=[metric_data]
            )
            
        except Exception as e:
            logger.error(f"Failed to put metric {metric_name}: {str(e)}")
    
    def put_business_metric(self, metric_name: str, value: float, 
                           user_id: Optional[str] = None, 
                           product_id: Optional[str] = None):
        """Put business-specific metrics with common dimensions."""
        dimensions = {
            'Service': self.service_name,
            'Environment': self.environment
        }
        
        if user_id:
            dimensions['UserId'] = user_id
        if product_id:
            dimensions['ProductId'] = product_id
            
        self.put_metric(metric_name, value, dimensions=dimensions)

class SecurityMonitor:
    """Security monitoring and alerting."""
    
    def __init__(self, service_name: str, environment: str):
        self.service_name = service_name
        self.environment = environment
        self.performance_monitor = PerformanceMonitor(service_name, environment)
    
    def log_security_event(self, event_type: str, details: Dict[str, Any], 
                          severity: str = 'INFO', user_id: Optional[str] = None):
        """Log security-related events with structured format."""
        security_log = {
            'timestamp': datetime.utcnow().isoformat(),
            'service': self.service_name,
            'environment': self.environment,
            'event_type': event_type,
            'severity': severity,
            'user_id': user_id,
            'details': details
        }
        
        if severity in ['WARN', 'ERROR', 'CRITICAL']:
            logger.warning(f"SECURITY_EVENT: {json.dumps(security_log)}")
            # Put metric for security events
            self.performance_monitor.put_metric(
                'SecurityEvents',
                1,
                dimensions={
                    'EventType': event_type,
                    'Severity': severity,
                    'Service': self.service_name
                }
            )
        else:
            logger.info(f"SECURITY_EVENT: {json.dumps(security_log)}")
    
    def log_authentication_attempt(self, user_id: str, success: bool, 
                                 ip_address: Optional[str] = None):
        """Log authentication attempts."""
        self.log_security_event(
            'authentication_attempt',
            {
                'user_id': user_id,
                'success': success,
                'ip_address': ip_address
            },
            severity='WARN' if not success else 'INFO'
        )
    
    def log_rate_limit_exceeded(self, user_id: Optional[str], endpoint: str, 
                              ip_address: Optional[str] = None):
        """Log rate limiting events."""
        self.log_security_event(
            'rate_limit_exceeded',
            {
                'user_id': user_id,
                'endpoint': endpoint,
                'ip_address': ip_address
            },
            severity='WARN'
        )
    
    def log_suspicious_activity(self, activity_type: str, details: Dict[str, Any], 
                              user_id: Optional[str] = None):
        """Log suspicious activities."""
        self.log_security_event(
            'suspicious_activity',
            {
                'activity_type': activity_type,
                'user_id': user_id,
                **details
            },
            severity='ERROR'
        )

def lambda_monitor(service_name: str, environment: str = 'dev'):
    """
    Decorator for comprehensive Lambda function monitoring.
    Provides logging, X-Ray tracing, performance metrics, and error handling.
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(event: Dict[str, Any], context: Context) -> Dict[str, Any]:
            start_time = time.time()
            performance_monitor = PerformanceMonitor(service_name, environment)
            security_monitor = SecurityMonitor(service_name, environment)
            
            # Extract request information
            request_id = context.aws_request_id if context else 'unknown'
            user_id = None
            ip_address = None
            
            # Extract user info from event if available
            if 'requestContext' in event:
                request_context = event['requestContext']
                if 'authorizer' in request_context:
                    user_id = request_context['authorizer'].get('userId')
                if 'identity' in request_context:
                    ip_address = request_context['identity'].get('sourceIp')
            
            # Start X-Ray subsegment
            subsegment = xray_recorder.begin_subsegment(f'{service_name}_handler')
            
            try:
                # Log request start
                logger.info(f"REQUEST_START: {json.dumps({
                    'request_id': request_id,
                    'service': service_name,
                    'user_id': user_id,
                    'ip_address': ip_address,
                    'event_type': event.get('httpMethod', 'unknown'),
                    'path': event.get('path', 'unknown')
                })}")
                
                # Add X-Ray annotations
                if subsegment:
                    subsegment.put_annotation('service', service_name)
                    subsegment.put_annotation('environment', environment)
                    if user_id:
                        subsegment.put_annotation('user_id', user_id)
                    if 'httpMethod' in event:
                        subsegment.put_annotation('http_method', event['httpMethod'])
                    if 'path' in event:
                        subsegment.put_annotation('path', event['path'])
                
                # Execute the function
                result = func(event, context)
                
                # Calculate execution time
                execution_time = (time.time() - start_time) * 1000  # milliseconds
                
                # Log successful completion
                logger.info(f"REQUEST_SUCCESS: {json.dumps({
                    'request_id': request_id,
                    'service': service_name,
                    'execution_time_ms': execution_time,
                    'status_code': result.get('statusCode', 200) if isinstance(result, dict) else 200
                })}")
                
                # Put performance metrics
                performance_monitor.put_metric('ExecutionTime', execution_time, 'Milliseconds')
                performance_monitor.put_metric('SuccessfulInvocations', 1)
                
                # Add execution time to X-Ray
                if subsegment:
                    subsegment.put_metadata('execution_time_ms', execution_time)
                    subsegment.put_metadata('status', 'success')
                
                return result
                
            except Exception as e:
                # Calculate execution time for failed requests
                execution_time = (time.time() - start_time) * 1000
                
                # Log error with full traceback
                error_details = {
                    'request_id': request_id,
                    'service': service_name,
                    'error_type': type(e).__name__,
                    'error_message': str(e),
                    'execution_time_ms': execution_time,
                    'traceback': traceback.format_exc()
                }
                
                logger.error(f"REQUEST_ERROR: {json.dumps(error_details)}")
                
                # Log security event for certain error types
                if isinstance(e, (PermissionError, ValueError)):
                    security_monitor.log_suspicious_activity(
                        'function_error',
                        {'error_type': type(e).__name__, 'error_message': str(e)},
                        user_id=user_id
                    )
                
                # Put error metrics
                performance_monitor.put_metric('Errors', 1)
                performance_monitor.put_metric('ErrorRate', 1, 'Percent')
                
                # Add error info to X-Ray
                if subsegment:
                    subsegment.put_metadata('error', {
                        'type': type(e).__name__,
                        'message': str(e)
                    })
                    subsegment.put_metadata('status', 'error')
                    subsegment.add_exception(e)
                
                # Return error response
                return {
                    'statusCode': 500,
                    'headers': {
                        'Content-Type': 'application/json',
                        'Access-Control-Allow-Origin': '*'
                    },
                    'body': json.dumps({
                        'error': 'Internal server error',
                        'request_id': request_id
                    })
                }
                
            finally:
                # End X-Ray subsegment
                if subsegment:
                    xray_recorder.end_subsegment()
        
        return wrapper
    return decorator

def log_database_operation(operation: str, table_name: str, execution_time_ms: float, 
                          success: bool, item_count: int = 1):
    """Log database operations with performance metrics."""
    log_data = {
        'timestamp': datetime.utcnow().isoformat(),
        'operation': operation,
        'table_name': table_name,
        'execution_time_ms': execution_time_ms,
        'success': success,
        'item_count': item_count
    }
    
    if success:
        logger.info(f"DB_OPERATION: {json.dumps(log_data)}")
    else:
        logger.error(f"DB_OPERATION_FAILED: {json.dumps(log_data)}")
    
    # Put CloudWatch metrics
    try:
        cloudwatch.put_metric_data(
            Namespace='UnicornECommerce/Database',
            MetricData=[
                {
                    'MetricName': f'{operation}Duration',
                    'Value': execution_time_ms,
                    'Unit': 'Milliseconds',
                    'Dimensions': [
                        {'Name': 'TableName', 'Value': table_name},
                        {'Name': 'Operation', 'Value': operation}
                    ]
                },
                {
                    'MetricName': f'{operation}Count',
                    'Value': 1,
                    'Unit': 'Count',
                    'Dimensions': [
                        {'Name': 'TableName', 'Value': table_name},
                        {'Name': 'Success', 'Value': str(success)}
                    ]
                }
            ]
        )
    except Exception as e:
        logger.error(f"Failed to put database metrics: {str(e)}")

def log_api_call(api_name: str, endpoint: str, method: str, status_code: int, 
                execution_time_ms: float, user_id: Optional[str] = None):
    """Log API calls with comprehensive details."""
    log_data = {
        'timestamp': datetime.utcnow().isoformat(),
        'api_name': api_name,
        'endpoint': endpoint,
        'method': method,
        'status_code': status_code,
        'execution_time_ms': execution_time_ms,
        'user_id': user_id
    }
    
    if status_code < 400:
        logger.info(f"API_CALL: {json.dumps(log_data)}")
    elif status_code < 500:
        logger.warning(f"API_CALL_CLIENT_ERROR: {json.dumps(log_data)}")
    else:
        logger.error(f"API_CALL_SERVER_ERROR: {json.dumps(log_data)}")

class DatabaseMonitor:
    """Database-specific monitoring utilities."""
    
    def __init__(self, service_name: str):
        self.service_name = service_name
    
    def monitor_query(self, table_name: str, operation: str):
        """Decorator for monitoring database queries."""
        def decorator(func: Callable) -> Callable:
            @wraps(func)
            def wrapper(*args, **kwargs):
                start_time = time.time()
                
                # Start X-Ray subsegment for database operation
                subsegment = xray_recorder.begin_subsegment(f'db_{operation}_{table_name}')
                
                try:
                    if subsegment:
                        subsegment.put_annotation('table_name', table_name)
                        subsegment.put_annotation('operation', operation)
                    
                    result = func(*args, **kwargs)
                    execution_time = (time.time() - start_time) * 1000
                    
                    # Determine item count from result
                    item_count = 1
                    if isinstance(result, dict):
                        if 'Items' in result:
                            item_count = len(result['Items'])
                        elif 'Count' in result:
                            item_count = result['Count']
                    
                    log_database_operation(operation, table_name, execution_time, True, item_count)
                    
                    if subsegment:
                        subsegment.put_metadata('execution_time_ms', execution_time)
                        subsegment.put_metadata('item_count', item_count)
                        subsegment.put_metadata('status', 'success')
                    
                    return result
                    
                except Exception as e:
                    execution_time = (time.time() - start_time) * 1000
                    log_database_operation(operation, table_name, execution_time, False)
                    
                    if subsegment:
                        subsegment.put_metadata('error', str(e))
                        subsegment.put_metadata('status', 'error')
                        subsegment.add_exception(e)
                    
                    raise
                    
                finally:
                    if subsegment:
                        xray_recorder.end_subsegment()
            
            return wrapper
        return decorator

# Global instances for easy access
performance_monitor = PerformanceMonitor('unicorn-ecommerce', 'dev')
security_monitor = SecurityMonitor('unicorn-ecommerce', 'dev')
database_monitor = DatabaseMonitor('unicorn-ecommerce')