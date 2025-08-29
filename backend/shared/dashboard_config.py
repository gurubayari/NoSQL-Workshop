"""
CloudWatch Dashboard configuration for Unicorn E-Commerce monitoring.
Provides comprehensive monitoring dashboards for all application components.
"""

import json
from typing import Dict, Any, List

def create_main_dashboard(project_name: str, environment: str, region: str) -> Dict[str, Any]:
    """Create the main application monitoring dashboard."""
    
    dashboard_body = {
        "widgets": [
            # API Gateway Overview
            {
                "type": "metric",
                "x": 0,
                "y": 0,
                "width": 12,
                "height": 6,
                "properties": {
                    "metrics": [
                        ["AWS/ApiGateway", "Count", "ApiName", f"{project_name}-{environment}-api"],
                        [".", "4XXError", ".", "."],
                        [".", "5XXError", ".", "."]
                    ],
                    "view": "timeSeries",
                    "stacked": False,
                    "region": region,
                    "title": "API Gateway - Requests and Errors",
                    "period": 300,
                    "stat": "Sum",
                    "yAxis": {
                        "left": {
                            "min": 0
                        }
                    }
                }
            },
            
            # API Gateway Latency
            {
                "type": "metric",
                "x": 12,
                "y": 0,
                "width": 12,
                "height": 6,
                "properties": {
                    "metrics": [
                        ["AWS/ApiGateway", "Latency", "ApiName", f"{project_name}-{environment}-api"],
                        [".", "IntegrationLatency", ".", "."]
                    ],
                    "view": "timeSeries",
                    "stacked": False,
                    "region": region,
                    "title": "API Gateway - Latency",
                    "period": 300,
                    "stat": "Average",
                    "yAxis": {
                        "left": {
                            "min": 0
                        }
                    }
                }
            },
            
            # Lambda Functions Overview
            {
                "type": "metric",
                "x": 0,
                "y": 6,
                "width": 8,
                "height": 6,
                "properties": {
                    "metrics": [
                        ["AWS/Lambda", "Invocations", "FunctionName", f"{project_name}-{environment}-product-api"],
                        [".", ".", ".", f"{project_name}-{environment}-cart-api"],
                        [".", ".", ".", f"{project_name}-{environment}-order-api"],
                        [".", ".", ".", f"{project_name}-{environment}-chat-api"],
                        [".", ".", ".", f"{project_name}-{environment}-review-api"],
                        [".", ".", ".", f"{project_name}-{environment}-search-api"]
                    ],
                    "view": "timeSeries",
                    "stacked": False,
                    "region": region,
                    "title": "Lambda Functions - Invocations",
                    "period": 300,
                    "stat": "Sum"
                }
            },
            
            # Lambda Errors
            {
                "type": "metric",
                "x": 8,
                "y": 6,
                "width": 8,
                "height": 6,
                "properties": {
                    "metrics": [
                        ["AWS/Lambda", "Errors", "FunctionName", f"{project_name}-{environment}-product-api"],
                        [".", ".", ".", f"{project_name}-{environment}-cart-api"],
                        [".", ".", ".", f"{project_name}-{environment}-order-api"],
                        [".", ".", ".", f"{project_name}-{environment}-chat-api"],
                        [".", ".", ".", f"{project_name}-{environment}-review-api"],
                        [".", ".", ".", f"{project_name}-{environment}-search-api"]
                    ],
                    "view": "timeSeries",
                    "stacked": False,
                    "region": region,
                    "title": "Lambda Functions - Errors",
                    "period": 300,
                    "stat": "Sum",
                    "yAxis": {
                        "left": {
                            "min": 0
                        }
                    }
                }
            },
            
            # Lambda Duration
            {
                "type": "metric",
                "x": 16,
                "y": 6,
                "width": 8,
                "height": 6,
                "properties": {
                    "metrics": [
                        ["AWS/Lambda", "Duration", "FunctionName", f"{project_name}-{environment}-product-api"],
                        [".", ".", ".", f"{project_name}-{environment}-cart-api"],
                        [".", ".", ".", f"{project_name}-{environment}-order-api"],
                        [".", ".", ".", f"{project_name}-{environment}-chat-api"],
                        [".", ".", ".", f"{project_name}-{environment}-review-api"],
                        [".", ".", ".", f"{project_name}-{environment}-search-api"]
                    ],
                    "view": "timeSeries",
                    "stacked": False,
                    "region": region,
                    "title": "Lambda Functions - Duration",
                    "period": 300,
                    "stat": "Average"
                }
            },
            
            # DynamoDB Metrics
            {
                "type": "metric",
                "x": 0,
                "y": 12,
                "width": 12,
                "height": 6,
                "properties": {
                    "metrics": [
                        ["AWS/DynamoDB", "ConsumedReadCapacityUnits", "TableName", f"{project_name}-{environment}-users"],
                        [".", "ConsumedWriteCapacityUnits", ".", "."],
                        [".", "ConsumedReadCapacityUnits", ".", f"{project_name}-{environment}-orders"],
                        [".", "ConsumedWriteCapacityUnits", ".", "."],
                        [".", "ConsumedReadCapacityUnits", ".", f"{project_name}-{environment}-shopping-cart"],
                        [".", "ConsumedWriteCapacityUnits", ".", "."]
                    ],
                    "view": "timeSeries",
                    "stacked": False,
                    "region": region,
                    "title": "DynamoDB - Capacity Consumption",
                    "period": 300,
                    "stat": "Sum"
                }
            },
            
            # DynamoDB Throttles and Errors
            {
                "type": "metric",
                "x": 12,
                "y": 12,
                "width": 12,
                "height": 6,
                "properties": {
                    "metrics": [
                        ["AWS/DynamoDB", "ThrottledRequests", "TableName", f"{project_name}-{environment}-users"],
                        [".", ".", ".", f"{project_name}-{environment}-orders"],
                        [".", ".", ".", f"{project_name}-{environment}-shopping-cart"],
                        [".", ".", ".", f"{project_name}-{environment}-inventory"],
                        [".", "SystemErrors", ".", f"{project_name}-{environment}-users"],
                        [".", ".", ".", f"{project_name}-{environment}-orders"]
                    ],
                    "view": "timeSeries",
                    "stacked": False,
                    "region": region,
                    "title": "DynamoDB - Throttles and Errors",
                    "period": 300,
                    "stat": "Sum",
                    "yAxis": {
                        "left": {
                            "min": 0
                        }
                    }
                }
            },
            
            # Custom Business Metrics
            {
                "type": "metric",
                "x": 0,
                "y": 18,
                "width": 8,
                "height": 6,
                "properties": {
                    "metrics": [
                        [f"UnicornECommerce/{environment}", "ProductViews", "Service", "product-api"],
                        [".", "ProductSearches", ".", "search-api"],
                        [".", "OrdersCreated", ".", "order-api"],
                        [".", "ReviewsCreated", ".", "review-api"]
                    ],
                    "view": "timeSeries",
                    "stacked": False,
                    "region": region,
                    "title": "Business Metrics - User Actions",
                    "period": 300,
                    "stat": "Sum"
                }
            },
            
            # Security Events
            {
                "type": "metric",
                "x": 8,
                "y": 18,
                "width": 8,
                "height": 6,
                "properties": {
                    "metrics": [
                        [f"UnicornECommerce/{environment}", "SecurityEvents", "EventType", "authentication_attempt", "Severity", "WARN"],
                        [".", ".", ".", "rate_limit_exceeded", ".", "."],
                        [".", ".", ".", "suspicious_activity", ".", "ERROR"]
                    ],
                    "view": "timeSeries",
                    "stacked": False,
                    "region": region,
                    "title": "Security Events",
                    "period": 300,
                    "stat": "Sum",
                    "yAxis": {
                        "left": {
                            "min": 0
                        }
                    }
                }
            },
            
            # Performance Metrics
            {
                "type": "metric",
                "x": 16,
                "y": 18,
                "width": 8,
                "height": 6,
                "properties": {
                    "metrics": [
                        [f"UnicornECommerce/{environment}", "ExecutionTime", "Service", "product-api"],
                        [".", ".", ".", "cart-api"],
                        [".", ".", ".", "order-api"],
                        [".", ".", ".", "chat-api"]
                    ],
                    "view": "timeSeries",
                    "stacked": False,
                    "region": region,
                    "title": "Service Performance - Execution Time",
                    "period": 300,
                    "stat": "Average"
                }
            }
        ]
    }
    
    return dashboard_body

def create_database_dashboard(project_name: str, environment: str, region: str) -> Dict[str, Any]:
    """Create database-specific monitoring dashboard."""
    
    dashboard_body = {
        "widgets": [
            # DynamoDB Read/Write Capacity
            {
                "type": "metric",
                "x": 0,
                "y": 0,
                "width": 12,
                "height": 6,
                "properties": {
                    "metrics": [
                        ["AWS/DynamoDB", "ConsumedReadCapacityUnits", "TableName", f"{project_name}-{environment}-users"],
                        [".", "ConsumedWriteCapacityUnits", ".", "."],
                        [".", "ConsumedReadCapacityUnits", ".", f"{project_name}-{environment}-orders"],
                        [".", "ConsumedWriteCapacityUnits", ".", "."],
                        [".", "ConsumedReadCapacityUnits", ".", f"{project_name}-{environment}-shopping-cart"],
                        [".", "ConsumedWriteCapacityUnits", ".", "."],
                        [".", "ConsumedReadCapacityUnits", ".", f"{project_name}-{environment}-inventory"],
                        [".", "ConsumedWriteCapacityUnits", ".", "."]
                    ],
                    "view": "timeSeries",
                    "stacked": False,
                    "region": region,
                    "title": "DynamoDB - Capacity Units Consumed",
                    "period": 300,
                    "stat": "Sum"
                }
            },
            
            # DynamoDB Item Count
            {
                "type": "metric",
                "x": 12,
                "y": 0,
                "width": 12,
                "height": 6,
                "properties": {
                    "metrics": [
                        ["AWS/DynamoDB", "ItemCount", "TableName", f"{project_name}-{environment}-users"],
                        [".", ".", ".", f"{project_name}-{environment}-orders"],
                        [".", ".", ".", f"{project_name}-{environment}-shopping-cart"],
                        [".", ".", ".", f"{project_name}-{environment}-inventory"]
                    ],
                    "view": "timeSeries",
                    "stacked": False,
                    "region": region,
                    "title": "DynamoDB - Item Count",
                    "period": 3600,
                    "stat": "Average"
                }
            },
            
            # Custom Database Metrics
            {
                "type": "metric",
                "x": 0,
                "y": 6,
                "width": 12,
                "height": 6,
                "properties": {
                    "metrics": [
                        ["UnicornECommerce/Database", "listDuration", "TableName", "products", "Operation", "list"],
                        [".", "getDuration", ".", ".", ".", "get"],
                        [".", "queryDuration", ".", "reviews", ".", "query"],
                        [".", "insertDuration", ".", "orders", ".", "insert"]
                    ],
                    "view": "timeSeries",
                    "stacked": False,
                    "region": region,
                    "title": "Database Operation Duration",
                    "period": 300,
                    "stat": "Average"
                }
            },
            
            # Database Success Rate
            {
                "type": "metric",
                "x": 12,
                "y": 6,
                "width": 12,
                "height": 6,
                "properties": {
                    "metrics": [
                        ["UnicornECommerce/Database", "listCount", "TableName", "products", "Success", "True"],
                        [".", ".", ".", ".", ".", "False"],
                        [".", "queryCount", ".", "reviews", ".", "True"],
                        [".", ".", ".", ".", ".", "False"]
                    ],
                    "view": "timeSeries",
                    "stacked": False,
                    "region": region,
                    "title": "Database Operation Success Rate",
                    "period": 300,
                    "stat": "Sum"
                }
            }
        ]
    }
    
    return dashboard_body

def create_security_dashboard(project_name: str, environment: str, region: str) -> Dict[str, Any]:
    """Create security monitoring dashboard."""
    
    dashboard_body = {
        "widgets": [
            # Authentication Events
            {
                "type": "metric",
                "x": 0,
                "y": 0,
                "width": 12,
                "height": 6,
                "properties": {
                    "metrics": [
                        [f"UnicornECommerce/{environment}", "SecurityEvents", "EventType", "authentication_attempt", "Severity", "INFO"],
                        [".", ".", ".", ".", ".", "WARN"],
                        [".", ".", ".", ".", ".", "ERROR"]
                    ],
                    "view": "timeSeries",
                    "stacked": False,
                    "region": region,
                    "title": "Authentication Events",
                    "period": 300,
                    "stat": "Sum"
                }
            },
            
            # Rate Limiting Events
            {
                "type": "metric",
                "x": 12,
                "y": 0,
                "width": 12,
                "height": 6,
                "properties": {
                    "metrics": [
                        [f"UnicornECommerce/{environment}", "SecurityEvents", "EventType", "rate_limit_exceeded", "Severity", "WARN"],
                        [".", ".", ".", "suspicious_activity", ".", "ERROR"]
                    ],
                    "view": "timeSeries",
                    "stacked": False,
                    "region": region,
                    "title": "Security Violations",
                    "period": 300,
                    "stat": "Sum",
                    "yAxis": {
                        "left": {
                            "min": 0
                        }
                    }
                }
            },
            
            # API Gateway Throttling
            {
                "type": "metric",
                "x": 0,
                "y": 6,
                "width": 12,
                "height": 6,
                "properties": {
                    "metrics": [
                        ["AWS/ApiGateway", "ThrottleCount", "ApiName", f"{project_name}-{environment}-api"],
                        [".", "CacheHitCount", ".", "."],
                        [".", "CacheMissCount", ".", "."]
                    ],
                    "view": "timeSeries",
                    "stacked": False,
                    "region": region,
                    "title": "API Gateway - Throttling and Caching",
                    "period": 300,
                    "stat": "Sum"
                }
            },
            
            # Error Rate by Service
            {
                "type": "metric",
                "x": 12,
                "y": 6,
                "width": 12,
                "height": 6,
                "properties": {
                    "metrics": [
                        [f"UnicornECommerce/{environment}", "ErrorRate", "Service", "product-api"],
                        [".", ".", ".", "cart-api"],
                        [".", ".", ".", "order-api"],
                        [".", ".", ".", "chat-api"]
                    ],
                    "view": "timeSeries",
                    "stacked": False,
                    "region": region,
                    "title": "Error Rate by Service",
                    "period": 300,
                    "stat": "Average",
                    "yAxis": {
                        "left": {
                            "min": 0,
                            "max": 100
                        }
                    }
                }
            }
        ]
    }
    
    return dashboard_body

def create_business_dashboard(project_name: str, environment: str, region: str) -> Dict[str, Any]:
    """Create business metrics dashboard."""
    
    dashboard_body = {
        "widgets": [
            # User Activity
            {
                "type": "metric",
                "x": 0,
                "y": 0,
                "width": 8,
                "height": 6,
                "properties": {
                    "metrics": [
                        [f"UnicornECommerce/{environment}", "ProductViews", "Service", "product-api"],
                        [".", "ProductSearches", ".", "search-api"],
                        [".", "CartAdditions", ".", "cart-api"],
                        [".", "OrdersCreated", ".", "order-api"]
                    ],
                    "view": "timeSeries",
                    "stacked": False,
                    "region": region,
                    "title": "User Activity Metrics",
                    "period": 300,
                    "stat": "Sum"
                }
            },
            
            # Conversion Funnel
            {
                "type": "metric",
                "x": 8,
                "y": 0,
                "width": 8,
                "height": 6,
                "properties": {
                    "metrics": [
                        [f"UnicornECommerce/{environment}", "ProductViews", "Service", "product-api"],
                        [".", "CartAdditions", ".", "cart-api"],
                        [".", "CheckoutStarted", ".", "order-api"],
                        [".", "OrdersCompleted", ".", "."]
                    ],
                    "view": "timeSeries",
                    "stacked": False,
                    "region": region,
                    "title": "Conversion Funnel",
                    "period": 300,
                    "stat": "Sum"
                }
            },
            
            # Review Activity
            {
                "type": "metric",
                "x": 16,
                "y": 0,
                "width": 8,
                "height": 6,
                "properties": {
                    "metrics": [
                        [f"UnicornECommerce/{environment}", "ReviewsCreated", "Service", "review-api"],
                        [".", "ReviewsViewed", ".", "."],
                        [".", "ReviewHelpfulVotes", ".", "."]
                    ],
                    "view": "timeSeries",
                    "stacked": False,
                    "region": region,
                    "title": "Review Activity",
                    "period": 300,
                    "stat": "Sum"
                }
            },
            
            # Search Analytics
            {
                "type": "metric",
                "x": 0,
                "y": 6,
                "width": 12,
                "height": 6,
                "properties": {
                    "metrics": [
                        [f"UnicornECommerce/{environment}", "SearchQueries", "Service", "search-api"],
                        [".", "SearchResultsFound", ".", "."],
                        [".", "SearchNoResults", ".", "."],
                        [".", "AutoCompleteUsed", ".", "."]
                    ],
                    "view": "timeSeries",
                    "stacked": False,
                    "region": region,
                    "title": "Search Analytics",
                    "period": 300,
                    "stat": "Sum"
                }
            },
            
            # AI Chat Usage
            {
                "type": "metric",
                "x": 12,
                "y": 6,
                "width": 12,
                "height": 6,
                "properties": {
                    "metrics": [
                        [f"UnicornECommerce/{environment}", "ChatMessages", "Service", "chat-api"],
                        [".", "ChatSessions", ".", "."],
                        [".", "AIRecommendations", ".", "."],
                        [".", "ChatProductInquiries", ".", "."]
                    ],
                    "view": "timeSeries",
                    "stacked": False,
                    "region": region,
                    "title": "AI Chat Usage",
                    "period": 300,
                    "stat": "Sum"
                }
            }
        ]
    }
    
    return dashboard_body

def get_all_dashboards(project_name: str, environment: str, region: str) -> Dict[str, Dict[str, Any]]:
    """Get all dashboard configurations."""
    
    return {
        'main': create_main_dashboard(project_name, environment, region),
        'database': create_database_dashboard(project_name, environment, region),
        'security': create_security_dashboard(project_name, environment, region),
        'business': create_business_dashboard(project_name, environment, region)
    }

# Export dashboard configurations
__all__ = [
    'create_main_dashboard',
    'create_database_dashboard', 
    'create_security_dashboard',
    'create_business_dashboard',
    'get_all_dashboards'
]