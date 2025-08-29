# AWS NoSQL Workshop - Unicorn E-Commerce

A comprehensive workshop demonstrating modern NoSQL database patterns using AWS services including DynamoDB, DocumentDB, and ElastiCache with a React-based e-commerce application.

## 🦄 Project Overview

This workshop showcases a modern e-commerce platform called "Unicorn E-Commerce" that demonstrates:

- **Real-time & High-Volume Applications** (Lab 1)
- **GenAI and Analytics** (Lab 2)
- **Modern Web 3.0 UI Design** with React
- **Comprehensive Review System** with AI-powered insights
- **Intelligent Search** with auto-complete and semantic capabilities

## 🏗️ Architecture

### Frontend
- **React 18** with modern Web 3.0 design patterns
- **Responsive UI** with Unicorn E-Commerce branding
- **State Management** using React Context
- **Modern CSS** with gradients and animations

### Backend Services
- **AWS Lambda** functions for serverless compute
- **API Gateway** for REST API endpoints
- **Amazon Cognito** for user authentication
- **Amazon Bedrock** for AI/ML capabilities

### Data Layer
- **DynamoDB** for transactional data (users, cart, orders, inventory)
- **DocumentDB** for product catalog and reviews with vector search
- **ElastiCache** for caching and session management

### Infrastructure
- **CloudFormation** for Infrastructure as Code
- **VPC** with public/private subnets
- **S3 + CloudFront** for static website hosting

## 📁 Project Structure

```
aws-nosql-workshop/
├── frontend/                 # React application (current directory)
│   ├── src/
│   │   ├── components/      # Reusable UI components
│   │   ├── pages/          # Page components
│   │   ├── context/        # React Context for state management
│   │   └── data/           # Mock data services
│   ├── public/             # Static assets
│   └── package.json        # Frontend dependencies
├── backend/                 # Python Lambda functions
│   ├── functions/          # Individual Lambda functions
│   ├── shared/             # Shared utilities and models
│   ├── tests/              # Unit and integration tests
│   └── requirements.txt    # Python dependencies
├── infrastructure/          # CloudFormation templates
│   └── cloudformation-template.yaml
├── data/                   # Data generation scripts
│   ├── generators/         # Data generation utilities
│   └── seeders/           # Database seeding scripts
└── docs/                   # Workshop documentation
    ├── lab1/              # Lab 1 instructions
    └── lab2/              # Lab 2 instructions
```

## 🚀 Quick Start

### Prerequisites
- Node.js 18+ and npm
- Python 3.9+
- AWS CLI configured
- AWS CDK (optional)

### Frontend Development
```bash
# Install dependencies
npm install

# Start development server
npm start

# Build for production
npm run build
```

### Backend Development
```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r backend/requirements.txt

# Run tests
pytest backend/tests/
```

### Infrastructure Deployment
```bash
# Deploy CloudFormation stack
aws cloudformation deploy \
  --template-file infrastructure/cloudformation-template.yaml \
  --stack-name unicorn-ecommerce-dev \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameter-overrides Environment=dev
```

## 🎯 Workshop Labs

### Lab 1: Real-time & High-Volume Applications
- Set up DynamoDB tables for transactional data
- Implement shopping cart with real-time updates
- Build order management with inventory tracking
- Configure ElastiCache for performance optimization

### Lab 2: GenAI and Analytics
- Integrate Amazon Bedrock for AI capabilities
- Implement semantic search with DocumentDB vector search
- Build AI-powered review insights and recommendations
- Create intelligent chat interface with context retention

## 🌟 Key Features

### Modern UI Components
- **Product Catalog** with filtering and sorting
- **Product Detail** pages with image galleries
- **Shopping Cart** with real-time inventory updates
- **Checkout** flow with secure payment processing
- **User Dashboard** with order history and reviews
- **AI Chat Interface** for customer support
- **Review System** with ratings and photo uploads
- **Search Interface** with auto-complete suggestions

### AI-Powered Features
- **Semantic Search** using vector embeddings
- **Review Sentiment Analysis** with aspect-based scoring
- **Product Recommendations** based on user behavior
- **Intelligent Chat** with context-aware responses
- **Auto-complete Suggestions** for search queries

### Performance Optimizations
- **ElastiCache** for API response caching
- **Connection Pooling** for database efficiency
- **CDN Distribution** via CloudFront
- **Lazy Loading** and code splitting in React

## 🔧 Configuration

### Environment Variables
Create a `.env` file in the frontend directory:
```env
REACT_APP_API_ENDPOINT=https://your-api-gateway-url
REACT_APP_USER_POOL_ID=your-cognito-user-pool-id
REACT_APP_USER_POOL_CLIENT_ID=your-cognito-client-id
REACT_APP_REGION=us-west-2
```

### AWS Services Configuration
- **DynamoDB**: Tables for users, cart, orders, inventory, chat history, search analytics
- **DocumentDB**: Collections for products, reviews, knowledge base
- **ElastiCache**: Redis cluster for caching and session management
- **Cognito**: User pool for authentication with email verification
- **Bedrock**: Claude model for AI chat and text embeddings for search

## 🧪 Testing

### Frontend Testing
```bash
# Run unit tests
npm test

# Run with coverage
npm test -- --coverage
```

### Backend Testing
```bash
# Run unit tests
pytest backend/tests/unit/

# Run integration tests
pytest backend/tests/integration/

# Run with coverage
pytest --cov=backend backend/tests/
```

## 📚 Documentation

- [Lab 1 Instructions](docs/lab1/README.md)
- [Lab 2 Instructions](docs/lab2/README.md)
- [API Documentation](docs/api/README.md)
- [Architecture Guide](docs/architecture/README.md)
- [Troubleshooting](docs/troubleshooting/README.md)

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add some amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🆘 Support

For workshop support and questions:
- Check the [Troubleshooting Guide](docs/troubleshooting/README.md)
- Review [Common Issues](docs/common-issues.md)
- Contact the workshop facilitators

## 🎉 Acknowledgments

- AWS NoSQL team for workshop content
- React community for excellent documentation
- Contributors and workshop participants

---

**Happy Learning! 🚀**