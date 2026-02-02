# Backend Deployment Guide

This document provides instructions for deploying the NutriWealth backend to AWS Lambda using GitHub Actions.

## Prerequisites

1. **AWS Account** with necessary permissions
2. **GitHub Repository** with Actions enabled
3. **AWS Lambda Function** created
4. **ECR Repository** (will be created automatically if doesn't exist)
5. **GitHub OIDC Setup** for secure AWS authentication

## AWS Infrastructure Setup

### 1. Create Lambda Function

```bash
# Create Lambda function (using container image)
aws lambda create-function \
  --function-name nutriwealth-backend-api \
  --package-type Image \
  --code ImageUri=ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/nutriwealth-backend:latest \
  --role arn:aws:iam::ACCOUNT_ID:role/lambda-execution-role \
  --timeout 30 \
  --memory-size 512 \
  --environment Variables={IBEX_API_KEY=your-key,OPENAI_API_KEY=your-key}
```

### 2. Create Lambda Execution Role

Create an IAM role with these policies:
- `AWSLambdaBasicExecutionRole` (managed policy)
- Custom policy for your specific needs (DynamoDB, S3, etc.)

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "logs:CreateLogGroup",
        "logs:CreateLogStream",
        "logs:PutLogEvents"
      ],
      "Resource": "arn:aws:logs:*:*:*"
    }
  ]
}
```

### 3. Setup GitHub OIDC Authentication

Run the setup script from the ajna-github-workflows repo:

```bash
# Clone the workflows repo if you haven't already
git clone https://github.com/ajnacloud-ksj/ajna-github-workflows.git

# Run the OIDC setup script
cd ajna-github-workflows
./setup_oidc.sh
```

This creates an IAM role that GitHub Actions can assume using OIDC (no long-lived credentials needed).

The role should have these permissions:
- ECR push/pull access
- Lambda update function code
- CloudWatch Logs (optional, for viewing deployment logs)

Example trust policy:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Federated": "arn:aws:iam::ACCOUNT_ID:oidc-provider/token.actions.githubusercontent.com"
      },
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Condition": {
        "StringEquals": {
          "token.actions.githubusercontent.com:aud": "sts.amazonaws.com"
        },
        "StringLike": {
          "token.actions.githubusercontent.com:sub": "repo:ajnacloud-ksj/ajna_nutri_wealth_backend_v2:*"
        }
      }
    }
  ]
}
```

Example permissions policy:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "ecr:GetAuthorizationToken",
        "ecr:BatchCheckLayerAvailability",
        "ecr:GetDownloadUrlForLayer",
        "ecr:BatchGetImage",
        "ecr:PutImage",
        "ecr:InitiateLayerUpload",
        "ecr:UploadLayerPart",
        "ecr:CompleteLayerUpload",
        "ecr:DescribeRepositories",
        "ecr:CreateRepository"
      ],
      "Resource": "*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "lambda:UpdateFunctionCode",
        "lambda:GetFunction",
        "lambda:GetFunctionConfiguration"
      ],
      "Resource": "arn:aws:lambda:*:ACCOUNT_ID:function:nutriwealth-backend-api"
    }
  ]
}
```

## GitHub Secrets Configuration

Add these secrets to your GitHub repository:

**Settings → Secrets and variables → Actions → New repository secret**

### Required Secrets

1. **AWS_ROLE_ARN**
   - The ARN of the GitHub OIDC IAM role
   - Format: `arn:aws:iam::ACCOUNT_ID:role/GitHubActionsRole`

### Optional Secrets (for Lambda environment variables)

These can be set directly in Lambda or passed during deployment:

2. **IBEX_API_KEY** - Your Ibex Database API key
3. **OPENAI_API_KEY** - Your OpenAI API key

## Workflow Configuration

The deployment workflow is defined in `.github/workflows/deploy-backend.yml`:

```yaml
name: Deploy Backend to Lambda

on:
  push:
    branches: [main]  # Deploy on push to main
  workflow_dispatch:   # Allow manual deployment

jobs:
  deploy:
    uses: ajnacloud-ksj/ajna-github-workflows/.github/workflows/reusable-lambda.yml@main
    with:
      aws-region: 'us-east-1'
      ecr-repository: 'nutriwealth-backend'
      lambda-function-name: 'nutriwealth-backend-api'
      role-to-assume: ${{ secrets.AWS_ROLE_ARN }}
      working-directory: '.'
```

### Customization Options

- **aws-region**: Change to your preferred AWS region
- **ecr-repository**: Change ECR repository name
- **lambda-function-name**: Must match your Lambda function name
- **working-directory**: Change if Dockerfile is in a subdirectory

## Deployment Process

### Automatic Deployment

Push to the `main` branch triggers automatic deployment:

```bash
git add .
git commit -m "Update backend"
git push origin main
```

### Manual Deployment

Trigger manually from GitHub Actions:

1. Go to **Actions** tab in GitHub
2. Select **Deploy Backend to Lambda** workflow
3. Click **Run workflow**
4. Select branch and click **Run workflow**

## Deployment Steps (Automated)

The workflow performs these steps:

1. **Checkout code** from the repository
2. **Configure AWS credentials** using OIDC
3. **Login to Amazon ECR**
4. **Create ECR repository** if it doesn't exist
5. **Build Docker image** from Dockerfile
6. **Push image to ECR** with git SHA tag
7. **Update Lambda function** with new image
8. **Wait for Lambda update** to complete

## Monitoring Deployments

### GitHub Actions

- View deployment status in **Actions** tab
- Check logs for each deployment step
- Review build and push times

### AWS Console

- **Lambda**: Check function version and last update time
- **ECR**: Verify new image was pushed
- **CloudWatch Logs**: Monitor Lambda execution logs

### AWS CLI

```bash
# Check Lambda function status
aws lambda get-function --function-name nutriwealth-backend-api

# Get Lambda function configuration
aws lambda get-function-configuration --function-name nutriwealth-backend-api

# List ECR images
aws ecr list-images --repository-name nutriwealth-backend

# View recent Lambda logs
aws logs tail /aws/lambda/nutriwealth-backend-api --follow
```

## Testing the Deployment

### 1. Test Lambda Function URL (if configured)

```bash
curl https://your-lambda-url.lambda-url.us-east-1.on.aws/v1/auth/config
```

### 2. Test via API Gateway (if configured)

```bash
curl https://your-api-id.execute-api.us-east-1.amazonaws.com/prod/v1/auth/config
```

### 3. Test with AWS CLI

```bash
aws lambda invoke \
  --function-name nutriwealth-backend-api \
  --payload '{"path": "/v1/auth/config", "httpMethod": "GET"}' \
  response.json
  
cat response.json
```

## Troubleshooting

### Deployment Fails: "Repository does not exist"

The workflow auto-creates the ECR repository. If it fails, create manually:

```bash
aws ecr create-repository --repository-name nutriwealth-backend
```

### Deployment Fails: "Access Denied"

Check that the GitHub OIDC role has necessary permissions:

```bash
# Check role policies
aws iam list-role-policies --role-name GitHubActionsRole
aws iam list-attached-role-policies --role-name GitHubActionsRole
```

### Lambda Update Times Out

Increase the wait timeout or check Lambda console for errors:

```bash
# Check Lambda function status
aws lambda get-function --function-name nutriwealth-backend-api
```

### Docker Build Fails

- Check Dockerfile syntax
- Verify all files referenced in Dockerfile exist
- Check build logs in GitHub Actions

### Environment Variables Missing

Set environment variables in Lambda function:

```bash
aws lambda update-function-configuration \
  --function-name nutriwealth-backend-api \
  --environment Variables={IBEX_API_KEY=your-key,OPENAI_API_KEY=your-key}
```

## Best Practices

1. **Use Git Tags** for production releases
2. **Test locally** with Docker before pushing
3. **Monitor CloudWatch** logs after deployment
4. **Set up alarms** for Lambda errors
5. **Use Lambda versions and aliases** for blue-green deployments
6. **Keep secrets in AWS Secrets Manager** or Parameter Store
7. **Enable Lambda function URL** for direct HTTPS access

## Rollback

To rollback to a previous version:

```bash
# Find previous image
aws ecr list-images --repository-name nutriwealth-backend

# Update Lambda to previous image
aws lambda update-function-code \
  --function-name nutriwealth-backend-api \
  --image-uri ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/nutriwealth-backend:PREVIOUS_SHA
```

## Additional Resources

- [AWS Lambda Documentation](https://docs.aws.amazon.com/lambda/)
- [Amazon ECR Documentation](https://docs.aws.amazon.com/ecr/)
- [GitHub Actions OIDC](https://docs.github.com/en/actions/deployment/security-hardening-your-deployments/configuring-openid-connect-in-amazon-web-services)
- [Ajna GitHub Workflows](https://github.com/ajnacloud-ksj/ajna-github-workflows)

## Support

For issues or questions:
- Check GitHub Actions logs
- Review AWS CloudWatch logs
- Contact the DevOps team
