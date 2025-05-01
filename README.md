# HR Assistant REST API

A production-ready REST API that provides intelligent HR assistance using Azure OpenAI and Azure AI Search. This project implements Retrieval-Augmented Generation (RAG) to answer career-related questions using internal company documents.

## Features

- **Career Planning API**: Generate personalized career guidance using RAG with Azure OpenAI
- **Health Endpoint**: Monitor service health and dependencies
- **Ready for Copilot Studio**: Includes OpenAPI/Swagger 2.0 specification for Copilot integration
- **Infrastructure as Code**: Azure Bicep templates for consistent, repeatable deployments
- **Secure by Design**: Uses Azure managed identities and best practices

## Quick Start Guide

### Prerequisites

- **Azure CLI**: [Install](https://docs.microsoft.com/en-us/cli/azure/install-azure-cli)
- **Azure Subscription**: With permissions to create resources
- **Azure OpenAI Service**: With GPT-4o or o1 model deployed
- **Python 3.10+**: For local development and scripts

### Step 1: Clone the Repository

```bash
git clone https://github.com/amir0135/restapi-demo.git
cd restapi-demo
```

### Step 2: Login to Azure

```bash
az login
```

### Step 3: Deploy Azure Infrastructure 

```bash
# Create resource group
az group create --name hr-assistant-demo --location swedencentral

# Deploy infrastructure using Bicep
az deployment group create \
  --resource-group hr-assistant-demo \
  --template-file ./infra/main.bicep \
  --parameters ./infra/main.parameters.json
```

### Step 4: Set Up API Keys

```bash
# Get AI Search admin key
AI_SEARCH_NAME=$(jq -r ".parameters.aiSearchServiceName.value" ./infra/main.parameters.json)
AI_SEARCH_KEY=$(az search admin-key show --resource-group hr-assistant-demo --service-name "$AI_SEARCH_NAME" --query primaryKey -o tsv)

# Get Web App name
WEB_APP_NAME=$(jq -r ".parameters.webAppName.value" ./infra/main.parameters.json)

# Set your OpenAI API key (replace with your actual key)
OPENAI_API_KEY="your-openai-api-key"

# Configure app settings
az webapp config appsettings set \
  --resource-group hr-assistant-demo \
  --name "$WEB_APP_NAME" \
  --settings \
  AZURE_OPENAI_API_KEY="$OPENAI_API_KEY" \
  AZURE_SEARCH_ADMIN_KEY="$AI_SEARCH_KEY"
```

### Step 5: Create and Populate Search Index

```bash
# Install dependencies
cd scripts
python -m pip install -r requirements_index.txt

# Run the setup script
python setup_search_index.py \
  --endpoint "https://$AI_SEARCH_NAME.search.windows.net" \
  --key "$AI_SEARCH_KEY" \
  --index-name "contoso-career-docs-index"

cd ..
```

### Step 6: Deploy the Application

```bash
# Make the deployment script executable
chmod +x ./deploy_app.sh

# Deploy with GPT-4o (default)
./deploy_app.sh

# OR deploy with o1 model
./deploy_app.sh -m o1
```

### Step 7: Test the API

```bash
# Check API health
curl https://$WEB_APP_NAME.azurewebsites.net/health

# Test the career plan endpoint
curl -X POST https://$WEB_APP_NAME.azurewebsites.net/api/career-plan \
  -H "Content-Type: application/json" \
  -d '{
    "query": "What career paths are available for software engineers at Contoso?",
    "conversation_history": []
  }'
```

## Project Structure

```
/
├── deploy_app.sh          # Script to deploy application code to Azure
├── infra/                 # Azure infrastructure as code
│   ├── main.bicep         # Bicep template defining all Azure resources
│   └── main.parameters.json # Parameters for infrastructure deployment
├── openapi.json           # OpenAPI/Swagger 2.0 spec for Copilot Studio
├── scripts/               # Utility scripts
│   ├── setup_search_index.py # Script to create and populate search index
│   └── docs/              # Sample HR documents for the search index
└── src/                   # Application source code
    ├── app.py             # Flask API implementation with RAG pattern
    ├── Procfile           # For Gunicorn process definition
    └── requirements.txt   # Python dependencies
```

## Detailed Setup Guide

### Azure Resources Created

The Bicep template (`infra/main.bicep`) provisions:

1. **App Service Plan**: Premium V2 tier for reliable performance
2. **Web App**: Python 3.10 App Service with Managed Identity
3. **Azure AI Search**: Basic tier search service for document indexing

### Configuring Azure OpenAI

This project is designed to work with both Azure OpenAI's GPT-4o and o1 models. The deployment script supports switching between them.

1. **Creating an Azure OpenAI Service**:
   - In Azure Portal, create an Azure OpenAI resource
   - Deploy either GPT-4o or o1 model
   - Note the endpoint URL and API key

2. **Updating Parameters**:
   - Edit `infra/main.parameters.json`
   - Update `openAiEndpoint` with your service endpoint
   - Update `openAiDeploymentName` with your model deployment name

### Managing the Search Index

The search index stores HR documents that provide context for the RAG model:

1. **Adding Custom Documents**:
   - Place JSON documents in `scripts/docs/` directory
   - Follow the format in the sample files
   - Run `setup_search_index.py` to update the index

2. **Index Schema**:
   - The default schema includes: title, content, source, and created/modified dates
   - Vector embeddings are generated for semantic search

## Using with Copilot Studio

The included OpenAPI specification (`openapi.json`) can be used to integrate with Microsoft Copilot Studio:

1. In Copilot Studio, create a new custom connector
2. Upload the `openapi.json` file
3. Configure authentication
4. Create actions for the `/api/career-plan` endpoint
5. Train your copilot to use these actions appropriately

## Troubleshooting

### Common Issues

1. **Deployment Failures**:
   - Check if resources with the same names already exist
   - Ensure you have sufficient permissions in your Azure subscription
   - Verify your Azure OpenAI service is properly configured

2. **API Errors**:
   - Check the Web App logs in Azure Portal
   - Verify environment variables are correctly set
   - Ensure your Azure OpenAI model is deployed and accessible

3. **Search Index Issues**:
   - Run the setup script with `--verbose` flag for detailed output
   - Check if the index already exists and needs to be recreated

### Getting Help

For issues with:
- The REST API code: Check the source code in `src/app.py`
- Infrastructure: Review the Bicep template in `infra/main.bicep`
- Deployment: Run the script with debug output: `AZURE_CLI_DEBUG=1 ./deploy_app.sh`

## Security Best Practices

This project follows Azure security best practices:

1. **Managed Identities**: System-assigned identity for secure service access
2. **No Hardcoded Secrets**: API keys stored in app settings (consider Key Vault for production)
3. **HTTPS Only**: All endpoints require HTTPS
4. **TLS 1.2+**: Enforced minimum TLS version

## Contributing

Contributions are welcome! Please feel free to submit a pull request.

## License

This project is licensed under MIT License.

