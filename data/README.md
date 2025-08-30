# Data Generation and Seeding Utilities

This directory contains comprehensive data generation and seeding utilities for the Unicorn E-Commerce AWS NoSQL Workshop. These utilities generate realistic sample data for products, reviews, inventory, knowledge base content, and search analytics.

## Overview

The data generators create realistic sample data that demonstrates real-world use cases for AWS NoSQL databases:

- **DynamoDB**: User profiles, shopping carts, orders, inventory, and search analytics
- **DocumentDB**: Product catalog, customer reviews, and knowledge base content with vector embeddings
- **ElastiCache**: Popular search terms and auto-complete suggestions

## Directory Structure

```
data/
├── generators/           # Data generation scripts
│   ├── product_generator.py              # Generate 100 realistic products
│   ├── review_generator.py               # Generate customer reviews with sentiment analysis
│   ├── inventory_seeder.py               # Generate inventory data across warehouses
│   ├── knowledge_base_generator.py       # Generate support content and FAQs
│   ├── search_analytics_seeder.py        # Generate search terms and analytics
│   └── test_*.py                         # Test scripts for each generator
├── seeders/              # Database seeding utilities
└── output/               # Generated data files (JSON backups)
```

## Prerequisites

1. **Python Environment**: Python 3.8+ with required packages
2. **AWS Configuration**: AWS credentials and region configured
3. **Database Access**: Access to DynamoDB, DocumentDB, and ElastiCache instances
4. **Environment Variables**: Properly configured environment variables

### Required Python Packages

```bash
pip install boto3 pymongo redis
```

### Environment Variables

Set these environment variables or update `backend/shared/config.py`:

```bash
# AWS Configuration
export AWS_REGION=us-west-2

# DynamoDB Tables
export INVENTORY_TABLE=unicorn-ecommerce-dev-inventory
export SEARCH_ANALYTICS_TABLE=unicorn-ecommerce-dev-search-analytics

# DocumentDB Configuration
export DOCUMENTDB_HOST=your-documentdb-cluster.cluster-xyz.us-west-2.docdb.amazonaws.com
export DOCUMENTDB_USERNAME=your-username
export DOCUMENTDB_PASSWORD=your-password
export DOCUMENTDB_DATABASE=unicorn_ecommerce_dev

# ElastiCache Configuration
export ELASTICACHE_HOST=your-elasticache-cluster.xyz.cache.amazonaws.com

# Bedrock Configuration
export BEDROCK_EMBEDDING_MODEL_ID=amazon.titan-embed-text-v1
```

## Data Generators

### 1. Product Generator (`product_generator.py`)

Generates 100 realistic products across 10 categories with complete metadata.

**Features:**
- 10 product categories (Electronics, Clothing, Home & Garden, etc.)
- Realistic product names, descriptions, and specifications
- Pricing with occasional discounts
- Product images (placeholder URLs)
- Vector embeddings for semantic search
- SEO metadata and tags

**Usage:**
```bash
python data/generators/product_generator.py
```

**Output:**
- DocumentDB `products` collection
- JSON backup: `data/output/products.json`

### 2. Review Generator (`review_generator.py`)

Generates realistic customer reviews with sentiment analysis and aspect-based scoring.

**Features:**
- 5-25 reviews per product
- Realistic review content based on rating (1-5 stars)
- Sentiment analysis using Amazon Bedrock
- Aspect-based scoring (audio quality, comfort, value, etc.)
- Review helpfulness voting
- Verified purchase flags
- Vector embeddings for semantic search

**Usage:**
```bash
python data/generators/review_generator.py
```

**Dependencies:** Requires products to be generated first

**Output:**
- DocumentDB `reviews` collection
- JSON backup: `data/output/reviews.json`

### 3. Inventory Seeder (`inventory_seeder.py`)

Generates inventory data distributed across multiple warehouses.

**Features:**
- 5 warehouse locations (Seattle, NYC, Chicago, Dallas, LA)
- Realistic stock levels based on product characteristics
- Regional distribution patterns
- Inventory alerts for low stock
- Movement history (sales, restocks, returns)
- Supplier information and reorder points

**Usage:**
```bash
python data/generators/inventory_seeder.py
```

**Dependencies:** Requires products to be generated first

**Output:**
- DynamoDB inventory table
- JSON backup: `data/output/inventory.json`

### 4. Knowledge Base Generator (`knowledge_base_generator.py`)

Generates comprehensive support content for the AI chatbot.

**Features:**
- Shipping and return policies
- Product care guides
- Warranty information
- Frequently asked questions
- Vector embeddings for RAG functionality
- Content categorization and tagging

**Usage:**
```bash
python data/generators/knowledge_base_generator.py
```

**Output:**
- DocumentDB `knowledge_base` collection
- JSON backup: `data/output/knowledge_base.json`

### 5. Search Analytics Seeder (`search_analytics_seeder.py`)

Generates search analytics data and popular terms for auto-complete functionality.

**Features:**
- User search behavior patterns
- Popular search terms with frequencies
- Seasonal search trends
- Auto-complete suggestions
- Search analytics summary
- Device and platform distribution

**Usage:**
```bash
python data/generators/search_analytics_seeder.py
```

**Output:**
- DynamoDB search analytics table
- ElastiCache popular terms and suggestions
- JSON backups: `data/output/search_*.json`

## Testing

Each generator includes a test script that can run without AWS dependencies:

```bash
# Test individual generators
python data/generators/test_product_generator.py
python data/generators/test_review_generator.py
python data/generators/test_inventory_seeder.py
python data/generators/test_knowledge_base_generator.py
python data/generators/test_search_analytics_seeder.py
```

## Running All Generators

To generate all sample data in the correct order:

```bash
# 1. Generate products first (required by other generators)
python data/generators/product_generator.py

# 2. Generate reviews (depends on products)
python data/generators/review_generator.py

# 3. Generate inventory (depends on products)
python data/generators/inventory_seeder.py

# 4. Generate knowledge base content
python data/generators/knowledge_base_generator.py

# 5. Generate search analytics
python data/generators/search_analytics_seeder.py
```

## Generated Data Statistics

After running all generators, you'll have:

- **100 products** across 10 categories
- **500-2,500 customer reviews** with sentiment analysis
- **Inventory records** for all products across 5 warehouses
- **15+ knowledge base articles** for customer support
- **100 popular search terms** with analytics data
- **1,000+ search behavior records** from 100 simulated users

## Data Relationships

The generated data maintains realistic relationships:

- Reviews reference valid product IDs
- Inventory records correspond to existing products
- Search terms relate to actual product categories
- Knowledge base content covers real product policies

## Vector Search Capabilities

Several generators create vector embeddings for semantic search:

- **Products**: Searchable by name, description, and features
- **Reviews**: Searchable by content and sentiment
- **Knowledge Base**: Searchable for customer support queries

## Troubleshooting

### Common Issues

1. **Missing Dependencies**: Install required Python packages
2. **AWS Permissions**: Ensure proper IAM permissions for DynamoDB, DocumentDB, ElastiCache, and Bedrock
3. **Network Access**: DocumentDB requires VPC access or VPN connection
4. **Environment Variables**: Verify all required environment variables are set

### Error Handling

All generators include comprehensive error handling and will:
- Continue processing if individual records fail
- Provide detailed error messages
- Save successful data even if some operations fail
- Create JSON backups for data recovery

### Performance Considerations

- Generators use batch operations where possible
- Vector embedding generation may take time (uses Amazon Bedrock)
- Large datasets are processed in chunks
- Progress indicators show generation status

## Integration with Workshop

This generated data supports both workshop labs:

**Lab 1 - Real-time & High-Volume Applications:**
- Product catalog browsing
- Shopping cart management
- Inventory tracking
- Order processing

**Lab 2 - GenAI & Analytics:**
- AI-powered chatbot with RAG
- Semantic search across products and reviews
- Review sentiment analysis
- Search analytics and recommendations

## Customization

You can customize the generators by modifying:

- Product categories and brands
- Review sentiment patterns
- Warehouse locations
- Knowledge base content
- Search term patterns

Each generator includes configuration sections at the top of the file for easy customization.