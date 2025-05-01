# HR Assistant API for Copilot Studio Integration

This project provides an HR Assistant API with OpenAPI/Swagger 2.0 specification for easy integration with Microsoft Copilot Studio custom connectors. The API leverages Azure OpenAI and Azure AI Search for RAG (Retrieval-Augmented Generation) to answer career-related questions using internal company documents.

## API Overview

The HR Assistant API provides endpoints for:

- **Health Checks**: GET `/health` - Returns the health status of the API components
- **Career Planning**: POST `/api/career-plan` - Generates career guidance using RAG techniques

The API uses Azure OpenAI to generate contextually relevant responses based on information found in HR documents stored in Azure AI Search.

## OpenAPI Specification

The project includes both OpenAPI 3.0.3 (openapi.yaml) and OpenAPI/Swagger 2.0 (openapi.json) specifications that define:

- **Endpoints**: Complete definition of all API endpoints
- **Request Schemas**: Detailed schema for the career plan request, including query and conversation history
- **Response Schemas**: Definition of successful and error response formats
- **Examples**: Sample requests and responses for common scenarios

For Copilot Studio integration, use the `openapi.json` file (Swagger 2.0 format) which is fully compatible with Copilot Studio custom connectors.

## Project Structure

```
/
├── openapi.yaml           # OpenAPI 3.0.3 specification
├── openapi.json           # OpenAPI/Swagger 2.0 specification for Copilot Studio
├── infra/                 # Bicep templates for Azure infrastructure
│   ├── main.bicep         # Main Bicep file defining resources (App Service, AI Search)
│   └── main.parameters.json # Parameters for the Bicep template
├── scripts/               # Helper scripts
│   ├── setup_search_index.py # Script to create/update the AI Search index
│   ├── requirements_index.txt # Python dependencies for the search index script
│   └── docs/              # Sample HR documents for AI Search indexing
├── src/                   # Application source code
│   ├── app.py             # Main Flask API application code
│   ├── requirements.txt   # Python dependencies for the API
│   └── Procfile           # Defines process for Gunicorn (used by App Service)
├── deploy_app.sh          # Script to deploy application code to Azure App Service
├── azuredeploy.json       # ARM template for one-click Azure deployment
└── README.md              # This file
```

## Using with Copilot Studio

To use this API with Microsoft Copilot Studio:

1. **Create a custom connector** in Copilot Studio using the `openapi.json` file
2. **Configure authentication** for your custom connector
3. **Create actions** in Copilot Studio that call the API endpoints
4. **Train your copilot** to use these actions appropriately

## Deployment to Azure

This project includes everything needed to deploy the HR Assistant API to Azure, including:

- Bicep templates for infrastructure provisioning
- Scripts for setting up the AI Search index
- Deployment scripts for the API application

### Prerequisites

Before you begin, ensure you have the following:

1. **Azure CLI**: For interacting with Azure services
2. **Azure Bicep**: For infrastructure as code
3. **Python 3.10+**: For running the search setup script
4. **Azure Subscription**: With permissions to create resources
5. **Azure OpenAI Service**: With a deployed model (e.g., GPT-4o)

### Deployment Steps

Follow these steps to deploy the infrastructure and application:

**Step 1: Clone or Download the Project**

Ensure you have this project structure on your local machine.

**Step 2: Configure Parameters**

Review and update the `infra/main.parameters.json` file. Key parameters:

*   `location`: Azure region for deployment.
*   `appServicePlanName`: Name for the App Service Plan.
*   `webAppName`: Unique name for the Web App.
*   `aiSearchServiceName`: Unique name for the AI Search service.
*   `openAiEndpoint`: Your Azure OpenAI service endpoint.
*   `openAiDeploymentName`: Your Azure OpenAI model deployment name (set to `gpt-4o` based on preference).

**Step 3: Provision Azure Infrastructure using Bicep**

Open your terminal in the project root directory and run the following Azure CLI command. The resource group `hr-assistant-demo` will be used.

```bash
# Define location (use location from parameters file)
LOCATION="swedencentral" # Or the location specified in main.parameters.json

# Create the resource group (if it doesn't exist)
az group create --name "hr-assistant-demo" --location "$LOCATION"

# Check if AI Search service already exists
AI_SEARCH_NAME=$(jq -r ".parameters.aiSearchServiceName.value" ./infra/main.parameters.json)
SEARCH_EXISTS=$(az search service show --name "$AI_SEARCH_NAME" --resource-group "hr-assistant-demo" --query name --output tsv 2>/dev/null)

if [ ! -z "$SEARCH_EXISTS" ]; then
  echo "⚠️ Warning: Azure AI Search service '$AI_SEARCH_NAME' already exists."
  echo "  You cannot change the SKU of an existing search service via deployment."
  echo "  Options:"
  echo "  1. Delete the existing search service: az search service delete --name \"$AI_SEARCH_NAME\" --resource-group \"hr-assistant-demo\" --yes"
  echo "  2. Use a different name for the search service in main.parameters.json"
  echo "  3. Continue deployment (existing search service will be unmodified)"
  echo ""
  read -p "Do you want to delete the existing search service? (y/N): " DELETE_CHOICE
  if [[ "$DELETE_CHOICE" == "y" || "$DELETE_CHOICE" == "Y" ]]; then
    az search service delete --name "$AI_SEARCH_NAME" --resource-group "hr-assistant-demo" --yes
    echo "Deleted existing search service. Proceeding with deployment..."
  else
    echo "Using existing search service. Note that any SKU changes in the Bicep template will be ignored."
  fi
fi

# Deploy the Bicep template
az deployment group create \
    --resource-group "hr-assistant-demo" \
    --template-file "./infra/main.bicep" \
    --parameters "./infra/main.parameters.json"
```

This command will create the Resource Group, App Service Plan, Web App (with System Managed Identity enabled), and AI Search service based on the Bicep template.

> **Important Note**: Azure AI Search service SKUs cannot be modified after creation. If deployment fails with an error like `Cannot update sku for an existing search service`, you'll need to either:
> 1. Delete the existing search service and deploy again
> 2. Use a new name for the search service in `main.parameters.json`
> 3. Modify your Bicep template to use the `existing` keyword for the search service to avoid trying to modify it

**Step 4: Configure Application Secrets (API Keys)**

The Bicep template sets up placeholders for API keys but does not deploy the actual secrets for security reasons. You need to configure these in the Azure App Service Application Settings:

1.  **Get AI Search Admin Key:**
    ```bash
    AI_SEARCH_NAME=$(jq -r ".parameters.aiSearchServiceName.value" ./infra/main.parameters.json)
    AI_SEARCH_KEY=$(az search admin-key show --resource-group "hr-assistant-demo" --service-name "$AI_SEARCH_NAME" --query primaryKey -o tsv)
    echo "AI Search Key: $AI_SEARCH_KEY"
    ```
2.  **Get Your Azure OpenAI API Key:** Retrieve this from your Azure OpenAI service deployment in the Azure portal.
3.  **Set App Settings:**
    ```bash
    WEB_APP_NAME=$(jq -r ".parameters.webAppName.value" ./infra/main.parameters.json)
    # Replace <your-openai-api-key> with your actual key
    OPENAI_API_KEY="<your-openai-api-key>"

    az webapp config appsettings set \
        --resource-group "hr-assistant-demo" \
        --name "$WEB_APP_NAME" \
        --settings \
        AZURE_OPENAI_API_KEY="$OPENAI_API_KEY" \
        AZURE_SEARCH_ADMIN_KEY="$AI_SEARCH_KEY"
    ```

**Recommendation:** For production environments, use Azure Key Vault to store these secrets and configure the App Service to reference them using Managed Identity. The Bicep template already enables System Managed Identity on the Web App.

**Step 5: Set Up AI Search Index**

This step creates the search index and uploads the sample documents. Run this from the project root directory:

```bash
# Navigate to the scripts directory
cd scripts

# Create a virtual environment and install dependencies
python3 -m venv venv_index
source venv_index/bin/activate
pip install -r requirements_index.txt

# Run the setup script (using values from parameters file)
AI_SEARCH_ENDPOINT="https://$(jq -r ".parameters.aiSearchServiceName.value" ../infra/main.parameters.json).search.windows.net"
AI_SEARCH_INDEX_NAME=$(jq -r ".parameters.aiSearchIndexName.value" ../infra/main.parameters.json)
# The AI_SEARCH_KEY was retrieved in the previous step

python setup_search_index.py \
    --endpoint "$AI_SEARCH_ENDPOINT" \
    --key "$AI_SEARCH_KEY" \
    --index-name "$AI_SEARCH_INDEX_NAME"

# Deactivate the virtual environment
deactivate

# Navigate back to the project root
cd ..
```

**Step 6: Deploy Application Code**

Run the simplified deployment script from the project root directory. It will automatically use the resource group `hr-assistant-demo` and read the web app name from `infra/main.parameters.json`.

```bash
# Make the script executable (if needed)
chmod +x deploy_app.sh

# Run the deployment script (no arguments needed)
./deploy_app.sh
```

This script will:
1.  Zip the contents of the `src` directory.
2.  Use `az webapp deploy` to upload the zip file to your App Service.
3.  Azure App Service (Oryx build system) will automatically detect `requirements.txt` and install the dependencies.
4.  Restart the Web App.

**Step 7: Verify Deployment**

Once the deployment script finishes, your application should be available at `https://<web-app-name>.azurewebsites.net`.

*   Access the root URL (`/`) to see the status.
*   Check the health endpoint (`/health`).
*   Test the API endpoint (`/api/career-plan`) using a tool like `curl` or Postman.

Example curl command to test the career plan endpoint:

```bash
# Test the API with a simple career question
curl -X POST https://<web-app-name>.azurewebsites.net/api/career-plan \
  -H "Content-Type: application/json" \
  -d '{
    "query": "What skills do I need to become a project leader at Contoso?",
    "conversation_history": []
  }'
```

The API should return a JSON response with career guidance based on the HR documents in your Azure AI Search index.

## Security Considerations

The HR Assistant API is designed with Azure best practices in mind:

- **System-Assigned Managed Identity**: Used for secure access to Azure resources
- **Azure Key Vault integration**: Recommended for storing secrets
- **HTTPS Only**: All endpoints are secured with TLS
- **API Key Management**: No hardcoded secrets in the codebase

## Contributing

Contributions to improve the API or OpenAPI specifications are welcome. Please submit pull requests to the GitHub repository.

## License

This project is licensed under MIT license.

