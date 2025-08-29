// AWS NoSQL Workshop - Configuration Manager
// This file manages configuration for different environments

import productionConfig from './production';

// Development configuration (for local development)
const developmentConfig = {
  ...productionConfig,
  
  // Override specific settings for development
  app: {
    ...productionConfig.app,
    environment: 'development',
    features: {
      ...productionConfig.app.features,
      enableServiceWorker: false // Disable service worker in development
    }
  },
  
  // More verbose logging in development
  logging: {
    ...productionConfig.logging,
    level: 'debug',
    enableConsoleLogging: true,
    enableRemoteLogging: false
  },
  
  // Show error details in development
  errorHandling: {
    ...productionConfig.errorHandling,
    showErrorDetails: true
  },
  
  // Disable some security features for easier development
  security: {
    ...productionConfig.security,
    enableCSP: false
  },
  
  // Shorter cache timeouts for development
  cache: {
    ...productionConfig.cache,
    timeouts: {
      products: 30000,       // 30 seconds
      cart: 10000,           // 10 seconds
      user: 60000,           // 1 minute
      search: 30000,         // 30 seconds
      reviews: 60000,        // 1 minute
      chatHistory: 30000     // 30 seconds
    }
  }
};

// Test configuration (for testing environments)
const testConfig = {
  ...developmentConfig,
  
  app: {
    ...developmentConfig.app,
    environment: 'test'
  },
  
  // Disable analytics in test
  analytics: {
    ...developmentConfig.analytics,
    enabled: false
  },
  
  // Disable caching in test
  cache: {
    ...developmentConfig.cache,
    timeouts: {
      products: 0,
      cart: 0,
      user: 0,
      search: 0,
      reviews: 0,
      chatHistory: 0
    }
  }
};

// Get configuration based on environment
const getConfig = () => {
  const env = process.env.NODE_ENV || 'development';
  
  switch (env) {
    case 'production':
      return productionConfig;
    case 'test':
      return testConfig;
    case 'development':
    default:
      return developmentConfig;
  }
};

// Export the configuration
const config = getConfig();

// Validate required configuration
const validateConfig = () => {
  const requiredFields = [
    'aws.region',
    'aws.apiGateway.url',
    'aws.cognito.userPoolId',
    'aws.cognito.userPoolClientId'
  ];
  
  const missingFields = [];
  
  requiredFields.forEach(field => {
    const keys = field.split('.');
    let value = config;
    
    for (const key of keys) {
      value = value?.[key];
    }
    
    if (!value) {
      missingFields.push(field);
    }
  });
  
  if (missingFields.length > 0) {
    console.warn('Missing required configuration fields:', missingFields);
    
    // In development, show helpful message
    if (config.app.environment === 'development') {
      console.warn('Please ensure your .env file contains all required environment variables.');
      console.warn('See .env.example for reference.');
    }
  }
  
  return missingFields.length === 0;
};

// Validate configuration on import
validateConfig();

// Helper functions
export const getApiUrl = (endpoint, params = {}) => {
  let url = config.api.baseUrl + config.api.endpoints[endpoint];
  
  // Replace path parameters
  Object.keys(params).forEach(key => {
    url = url.replace(`{${key}}`, params[key]);
  });
  
  return url;
};

export const getCacheKey = (type, id = '') => {
  return `${config.cache.keys[type]}${id ? `_${id}` : ''}`;
};

export const getCacheTimeout = (type) => {
  return config.cache.timeouts[type] || 300000; // Default 5 minutes
};

export const isFeatureEnabled = (feature) => {
  return config.app.features[feature] || false;
};

export const getThreshold = (type) => {
  return config.monitoring.thresholds[type];
};

export const shouldLogLevel = (level) => {
  const levels = ['debug', 'info', 'warn', 'error'];
  const currentLevelIndex = levels.indexOf(config.logging.level);
  const requestedLevelIndex = levels.indexOf(level);
  
  return requestedLevelIndex >= currentLevelIndex;
};

// Export default configuration
export default config;