# NutriWealth Backend

Python FastAPI backend service for the NutriWealth food & wellness tracking application.

## 🏗️ Architecture

- **Runtime**: AWS Lambda (Python 3.12)
- **Framework**: Custom FastAPI-like router
- **Database**: Ibex Database (external API)
- **AI**: OpenAI GPT-4 for food analysis
- **Features**:
  - Multi-tenant architecture
  - Generic CRUD API for all tables
  - AI-powered food, receipt, and workout analysis
  - Image processing and storage
  - Cost tracking

## 📁 Project Structure

```
backend/
├── src/
│   ├── app.py              # Lambda entry point
│   ├── router.py           # API routing
│   ├── handlers/           # API endpoint handlers
│   │   ├── analyze.py      # AI analysis endpoints
│   │   ├── auth.py         # Authentication
│   │   ├── data.py         # Generic CRUD operations
│   │   ├── receipts.py     # Receipt management
│   │   └── storage.py      # File storage
│   ├── lib/                # Core services
│   │   ├── ai_optimized.py # AI service
│   │   ├── ibex_client.py  # Database client
│   │   ├── tenant_manager.py
│   │   └── auth_provider.py
│   ├── schemas/            # 23 database table schemas
│   ├── prompts/            # AI prompts
│   └── utils/              # Helper utilities
├── scripts/                # Utility scripts
├── tests/                  # Test files
├── local_server.py         # Local development server
├── Dockerfile              # Production image
├── Dockerfile.dev          # Development image
└── pyproject.toml          # Python dependencies
```

## 🚀 Quick Start

### Prerequisites

- Python 3.12+
- pip or uv (recommended)

### 1. Environment Setup

```bash
# Copy environment template
cp .env.example .env

# Edit .env and add your API keys:
# IBEX_API_KEY=your-ibex-key
# OPENAI_API_KEY=your-openai-key
```

### 2. Install Dependencies

```bash
# Using uv (recommended)
uv pip install -r src/requirements.txt

# Or using pip
pip install -r src/requirements.txt
```

### 3. Run Local Server

```bash
python local_server.py

# Server runs on http://localhost:8080
```

## 📡 API Endpoints

### Authentication
- `GET /v1/auth/config` - Get auth configuration
- `POST /v1/auth/invitations/redeem` - Redeem invitation

### AI Analysis
- `POST /v1/analyze` - Analyze food/receipt/workout

### Storage
- `POST /v1/storage/upload` - Upload file
- `GET /v1/storage/{path}` - Get file

### System
- `POST /v1/system/initialize-schemas` - Initialize database

### Generic CRUD (works for all tables)
- `GET /v1/{table}` - List records
- `POST /v1/{table}` - Create record
- `GET /v1/{table}/{id}` - Get record
- `PUT /v1/{table}/{id}` - Update record
- `DELETE /v1/{table}/{id}` - Delete record

### Database Tables (23 total)
api_costs, api_usage_log, care_relationships, caretaker_notes, food_entries, food_items, health_assessments, images, invitation_codes, meal_summaries, models, participant_comments, participant_permissions, pending_analyses, permission_requests, prompts, receipt_items, receipts, user_goals, user_notifications, users, workout_exercises, workouts

## 🔧 Configuration

### Environment Variables

**Required:**
- `IBEX_API_KEY` - Ibex Database API key
- `OPENAI_API_KEY` - OpenAI API key

**Optional:**
- `IBEX_API_URL` - Ibex Database URL (default: https://smartlink.ajna.cloud/ibexdb)
- `AWS_REGION` - AWS region (default: us-east-1)

### Multi-Tenant Configuration

Edit `tenants.json` to configure tenants:

```json
{
  "tenants": {
    "demo": {
      "tenant_id": "demo-tenant",
      "namespace": "demo",
      "settings": {
        "max_api_calls_per_day": 100,
        "storage_quota_mb": 100
      }
    }
  }
}
```

## 🧪 Testing

```bash
# Run all tests
python -m pytest

# Test specific endpoints
python tests/test_all_endpoints.py

# Performance testing
python tests/test_performance.py
```

## 📦 Deployment

### AWS Lambda (Production)

```bash
# Build production image
docker build -f Dockerfile -t nutriwealth-backend .

# Push to ECR
docker tag nutriwealth-backend:latest {account}.dkr.ecr.{region}.amazonaws.com/nutriwealth-backend:latest
docker push {account}.dkr.ecr.{region}.amazonaws.com/nutriwealth-backend:latest

# Deploy with AWS CLI or update Lambda function
```

### Docker Development

```bash
# Build development image
docker build -f Dockerfile.dev -t nutriwealth-backend-dev .

# Run with docker-compose
docker-compose up backend
```

## 🐛 Troubleshooting

**"IBEX_API_KEY not found"**
- Ensure `.env` file exists and contains `IBEX_API_KEY`
- Verify the key is valid

**Database connection errors**
- Check `IBEX_API_URL` is correct
- Verify API key has necessary permissions

**Module import errors**
- Make sure all dependencies are installed: `pip install -r src/requirements.txt`
- Check Python version: `python --version` (should be 3.12+)

## 🔐 Security

### Current Implementation
- Authentication via invitation codes
- Multi-tenant isolation
- Cost tracking per tenant

### To Implement
- [ ] AWS Cognito integration
- [ ] Rate limiting
- [ ] Input validation framework
- [ ] Structured logging
- [ ] Secrets management (AWS Secrets Manager)

## 📚 Related Repositories

- **UI**: [ajna_nutri_wealth_ui_v2](https://github.com/ajnacloud-ksj/ajna_nutri_wealth_ui_v2)
- **Deployment**: [food-sense-ai-tracker](https://github.com/ajnacloud-dev/food-sense-ai-tracker-3b84f458)

## 📄 License

MIT

---

**Last Updated:** February 4, 2026  
**Version:** 2.1.0 - Async Lambda + Cognito Auth
