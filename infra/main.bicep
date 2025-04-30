param location string = resourceGroup().location
param appServicePlanName string
param webAppName string
param aiSearchServiceName string
param openAiEndpoint string // Passed for App Settings, not deployed by this template
param openAiDeploymentName string // Passed for App Settings, not deployed by this template
param aiSearchIndexName string = 'contoso-career-docs-index' // Default index name

// App Service Plan (Linux, P1v2)
resource appServicePlan 'Microsoft.Web/serverfarms@2022-09-01' = {
  name: appServicePlanName
  location: location
  sku: {
    name: 'P1v2'
    tier: 'PremiumV2'
    size: 'P1v2'
    family: 'Pv2'
    capacity: 2 // Increased from 1 to 2 instances for improved availability
  }
  kind: 'linux'
  properties: {
    reserved: true // Required for Linux plans
  }
}

// Azure AI Search Service (Basic SKU)
resource aiSearchService 'Microsoft.Search/searchServices@2023-11-01' = {
  name: aiSearchServiceName
  location: location
  // SKU is required, set to 'basic' as intended.
  // Incremental deployment should handle existing service with same SKU.
  sku: {
    name: 'basic'
  }
  properties: {
    replicaCount: 1
    partitionCount: 1
    hostingMode: 'default'
    publicNetworkAccess: 'enabled' // Explicitly enable public network access
    networkRuleSet: {
      ipRules: []  // Empty array means no IP restrictions
    }
  }
}

// Web App (Python 3.10)
resource webApp 'Microsoft.Web/sites@2022-09-01' = {
  name: webAppName
  location: location
  kind: 'app,linux'
  // Identity moved outside properties block to address BCP037 warning
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    serverFarmId: appServicePlan.id
    siteConfig: {
      linuxFxVersion: 'PYTHON|3.10'
      pythonVersion: '3.10'
      ftpsState: 'FtpsOnly'
      minTlsVersion: '1.2'
      alwaysOn: true // Recommended for Premium plans
      appSettings: [
        {
          name: 'SCM_DO_BUILD_DURING_DEPLOYMENT'
          value: 'true' // Enable Oryx build process for Python dependencies
        }
        {
          name: 'WEBSITE_WEBDEPLOY_USE_SCM'
          value: 'false' // Recommended setting with SCM_DO_BUILD_DURING_DEPLOYMENT=true
        }
        {
          name: 'AZURE_OPENAI_ENDPOINT'
          value: openAiEndpoint
        }
        {
          name: 'AZURE_OPENAI_DEPLOYMENT_NAME'
          value: openAiDeploymentName
        }
        {
          name: 'AZURE_OPENAI_API_VERSION'
          value: '2023-12-01-preview' // Or a newer stable version if available
        }
        {
          name: 'AZURE_SEARCH_SERVICE_ENDPOINT'
          value: 'https://${aiSearchServiceName}.search.windows.net' // Always use the public endpoint
        }
        {
          name: 'AZURE_SEARCH_INDEX_NAME'
          value: aiSearchIndexName
        }
        // Secrets like API keys should ideally be added post-deployment via Key Vault reference or manually/scripted
        // Placeholder for keys - REMOVE THESE FROM BICEP IN PRODUCTION
        // { name: 'AZURE_OPENAI_API_KEY', value: '[SECRET_OPENAI_KEY]' }
        // { name: 'AZURE_SEARCH_ADMIN_KEY', value: '[SECRET_SEARCH_KEY]' }
      ]
      // Startup command is set via `az webapp config set --startup-file` after deployment or can be set here
      // startupCommand: 'gunicorn --bind=0.0.0.0 --workers 2 --timeout 600 app:app'
    }
    httpsOnly: true
  }

  // Configure Health Check (optional but recommended)
  resource healthCheck 'config@2022-09-01' = {
    name: 'web'
    properties: {
      healthCheckPath: '/health'
    }
  }

  // Configure Logging (optional but recommended)
  resource logging 'config@2022-09-01' = {
    name: 'logs'
    properties: {
      applicationLogs: {
        fileSystem: {
          level: 'Verbose'
        }
      }
      httpLogs: {
        fileSystem: {
          retentionInMb: 35
          retentionInDays: 1
          enabled: true
        }
      }
      failedRequestsTracing: {
        enabled: true
      }
      detailedErrorMessages: {
        enabled: true
      }
    }
    // dependsOn removed to address no-unnecessary-dependson warning
  }
}

// Outputs
output webAppHostName string = webApp.properties.defaultHostName
output aiSearchServiceEndpoint string = 'https://${aiSearchServiceName}.search.windows.net' // Always output the public endpoint
output webAppPrincipalId string = webApp.identity.principalId // Output principal ID for granting access (e.g., to Key Vault)

