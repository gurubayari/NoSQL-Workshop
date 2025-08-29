// AWS NoSQL Workshop - Production Configuration
// This file contains production-specific configuration for the Unicorn E-Commerce application

const productionConfig = {
  // AWS Configuration
  aws: {
    region: process.env.REACT_APP_AWS_REGION || 'us-east-1',
    apiGateway: {
      url: process.env.REACT_APP_API_GATEWAY_URL || '',
      timeout: 30000,
      retries: 3
    },
    cognito: {
      userPoolId: process.env.REACT_APP_USER_POOL_ID || '',
      userPoolClientId: process.env.REACT_APP_USER_POOL_CLIENT_ID || '',
      region: process.env.REACT_APP_AWS_REGION || 'us-east-1'
    },
    cloudfront: {
      domain: process.env.REACT_APP_CLOUDFRONT_DOMAIN || ''
    }
  },

  // Application Configuration
  app: {
    name: 'Unicorn E-Commerce',
    version: process.env.REACT_APP_VERSION || '1.0.0',
    environment: process.env.REACT_APP_ENVIRONMENT || 'production',
    projectName: process.env.REACT_APP_PROJECT_NAME || 'unicorn-ecommerce',
    
    // Feature flags
    features: {
      enableAnalytics: true,
      enableChatbot: true,
      enableReviews: true,
      enableSearch: true,
      enableRecommendations: true,
      enablePushNotifications: false,
      enableServiceWorker: true
    },

    // UI Configuration
    ui: {
      theme: 'unicorn',
      animations: true,
      lazyLoading: true,
      infiniteScroll: true,
      skeletonLoading: true
    },

    // Performance Configuration
    performance: {
      enableCaching: true,
      cacheTimeout: 300000, // 5 minutes
      enableCompression: true,
      enablePrefetch: true,
      maxRetries: 3,
      retryDelay: 1000
    }
  },

  // API Configuration
  api: {
    baseUrl: process.env.REACT_APP_API_GATEWAY_URL || '',
    timeout: 30000,
    retries: 3,
    retryDelay: 1000,
    
    // API Endpoints
    endpoints: {
      // Product API
      products: '/products',
      productDetail: '/products/{id}',
      productSearch: '/products/search',
      productRecommendations: '/products/recommendations/{userId}',
      
      // Cart API
      cart: '/cart/{userId}',
      cartItems: '/cart/{userId}/items',
      cartItem: '/cart/{userId}/items/{itemId}',
      
      // Order API
      orders: '/orders',
      orderHistory: '/orders/{userId}',
      orderDetail: '/orders/{orderId}',
      
      // Review API
      reviews: '/reviews',
      reviewDetail: '/reviews/{reviewId}',
      reviewHelpful: '/reviews/{reviewId}/helpful',
      userReviews: '/reviews/user/{userId}',
      productReviews: '/reviews/product/{productId}',
      
      // Search API
      searchSuggestions: '/search/suggestions',
      searchProducts: '/search/products',
      searchPopular: '/search/popular',
      searchAnalytics: '/search/analytics',
      
      // Chat API
      chatMessage: '/chat/message',
      chatHistory: '/chat/history/{userId}',
      chatFeedback: '/chat/feedback',
      
      // Analytics API
      analyticsReviewSearch: '/analytics/reviews/search',
      analyticsRecommendations: '/analytics/products/recommendations',
      analyticsReviewInsights: '/analytics/reviews/insights/{productId}',
      analyticsSentiment: '/analytics/reviews/sentiment',
      
      // Auth API
      auth: '/auth',
      authRefresh: '/auth/refresh',
      authLogout: '/auth/logout'
    }
  },

  // Caching Configuration
  cache: {
    // Cache keys
    keys: {
      products: 'products',
      cart: 'cart',
      user: 'user',
      search: 'search',
      reviews: 'reviews',
      chatHistory: 'chatHistory'
    },
    
    // Cache timeouts (in milliseconds)
    timeouts: {
      products: 300000,      // 5 minutes
      cart: 60000,           // 1 minute
      user: 900000,          // 15 minutes
      search: 180000,        // 3 minutes
      reviews: 600000,       // 10 minutes
      chatHistory: 300000    // 5 minutes
    },
    
    // Cache sizes (number of items)
    maxSizes: {
      products: 100,
      search: 50,
      reviews: 200,
      chatHistory: 100
    }
  },

  // Analytics Configuration
  analytics: {
    enabled: true,
    trackPageViews: true,
    trackUserInteractions: true,
    trackErrors: true,
    trackPerformance: true,
    
    // Events to track
    events: {
      productView: 'product_view',
      productSearch: 'product_search',
      addToCart: 'add_to_cart',
      removeFromCart: 'remove_from_cart',
      checkout: 'checkout',
      purchase: 'purchase',
      reviewWrite: 'review_write',
      reviewHelpful: 'review_helpful',
      chatMessage: 'chat_message',
      searchQuery: 'search_query'
    }
  },

  // Error Handling Configuration
  errorHandling: {
    enableErrorBoundary: true,
    enableErrorReporting: true,
    showErrorDetails: false, // Don't show detailed errors in production
    fallbackComponent: 'ErrorFallback',
    
    // Error types to handle
    errorTypes: {
      network: 'NETWORK_ERROR',
      authentication: 'AUTH_ERROR',
      authorization: 'AUTHZ_ERROR',
      validation: 'VALIDATION_ERROR',
      server: 'SERVER_ERROR',
      client: 'CLIENT_ERROR'
    }
  },

  // Security Configuration
  security: {
    enableCSP: true,
    enableXSSProtection: true,
    enableClickjacking: true,
    
    // Content Security Policy
    csp: {
      defaultSrc: ["'self'"],
      scriptSrc: ["'self'", "'unsafe-inline'", "https://cdn.jsdelivr.net"],
      styleSrc: ["'self'", "'unsafe-inline'", "https://fonts.googleapis.com"],
      fontSrc: ["'self'", "https://fonts.gstatic.com"],
      imgSrc: ["'self'", "data:", "https:"],
      connectSrc: ["'self'", process.env.REACT_APP_API_GATEWAY_URL || '']
    }
  },

  // Logging Configuration
  logging: {
    level: 'warn', // Only log warnings and errors in production
    enableConsoleLogging: false,
    enableRemoteLogging: true,
    
    // Log categories
    categories: {
      api: 'API',
      auth: 'AUTH',
      ui: 'UI',
      performance: 'PERFORMANCE',
      error: 'ERROR'
    }
  },

  // Monitoring Configuration
  monitoring: {
    enablePerformanceMonitoring: true,
    enableErrorMonitoring: true,
    enableUserMonitoring: false, // Respect user privacy
    
    // Performance thresholds
    thresholds: {
      pageLoadTime: 3000,     // 3 seconds
      apiResponseTime: 2000,  // 2 seconds
      renderTime: 1000,       // 1 second
      memoryUsage: 50         // 50MB
    }
  }
};

export default productionConfig;