#!/bin/bash

# Simplified Deployment Script for Web App Code (Hardcoded Resource Group)

# --- Configuration ---
# Text colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Hardcoded Resource Group Name
RESOURCE_GROUP="hr-assistant-demo"

# --- Helper Functions ---
step_info() {
    printf "\n${YELLOW}>>> %s...${NC}\n" "$1"
}

step_success() {
    printf "${GREEN}✓ Success: %s${NC}\n" "$1"
}

step_error_exit() {
    printf "${RED}✗ Error: %s${NC}\n" "$1" >&2
    exit 1
}

step_warning() {
    printf "${YELLOW}⚠ Warning: %s${NC}\n" "$1"
}

# --- Check Prerequisites ---
if ! command -v az >/dev/null 2>&1; then
    step_error_exit "Azure CLI (az) is not installed. Please install it."
fi
if ! command -v zip >/dev/null 2>&1; then
    step_error_exit "zip utility is not installed. Please install it (e.g., brew install zip on macOS, sudo apt install zip on Debian/Ubuntu)."
fi
if ! command -v jq >/dev/null 2>&1; then
    step_error_exit "jq utility is not installed. Please install it (e.g., brew install jq). Needed to read web app name from parameters."
fi

# --- Input Parameters ---
# Default model
MODEL_NAME="gpt-4o"

# Parse command-line options
while getopts ":m:" opt; do
  case $opt in
    m)
      MODEL_NAME="$OPTARG"
      ;;
    \?)
      echo "Invalid option: -$OPTARG" >&2
      exit 1
      ;;
    :)
      echo "Option -$OPTARG requires an argument." >&2
      exit 1
      ;;
  esac
done
shift $((OPTIND-1))

# Validate model name
if [[ "$MODEL_NAME" != "gpt-4o" && "$MODEL_NAME" != "o1" ]]; then
    step_error_exit "Invalid model name specified with -m. Must be either \"gpt-4o\" or \"o1\"."
fi

# Read Web App Name from parameters file (assuming script is run from project root)
if [ ! -f "./infra/main.parameters.json" ]; then
    step_error_exit "Parameter file not found at ./infra/main.parameters.json. Run script from project root."
fi
WEB_APP_NAME=$(jq -r ".parameters.webAppName.value" ./infra/main.parameters.json)

if [ -z "$WEB_APP_NAME" ]; then
    step_error_exit "Could not read webAppName from ./infra/main.parameters.json"
fi

step_info "Deployment Configuration"
printf "  Resource Group: %s (Hardcoded)\n" "$RESOURCE_GROUP"
printf "  Web App Name: %s (from parameters file)\n" "$WEB_APP_NAME"
printf "  Selected Model: %s\n" "$MODEL_NAME"

# --- Deployment ---
step_info "Creating deployment package (app-deployment.zip) from src directory"

# Navigate to the script's directory to ensure relative paths work
SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
cd "$SCRIPT_DIR" || step_error_exit "Failed to change directory to script directory."

# Check if src directory exists
if [ ! -d "./src" ]; then
    step_error_exit "src directory not found in the current directory."
fi

# Verify critical files exist before packaging
cd ./src || step_error_exit "Failed to change directory to src."

# Pre-deployment verification - Check critical files
printf "Verifying critical files before packaging...\n"
CRITICAL_FILES=("app.py" "requirements.txt" "Procfile")
MISSING_FILES=()

for file in "${CRITICAL_FILES[@]}"; do
    if [ ! -f "./$file" ]; then
        MISSING_FILES+=("$file")
    fi
done

if [ ${#MISSING_FILES[@]} -gt 0 ]; then
    step_error_exit "Critical file(s) missing: ${MISSING_FILES[*]}. Cannot proceed with deployment."
fi

# Visual confirmation of files being included
printf "Including the following critical files in deployment package:\n"
for file in "${CRITICAL_FILES[@]}"; do
    printf "  - %s\n" "$file"
    if [ "$file" = "requirements.txt" ]; then
        printf "    Dependencies:\n"
        head -n 5 ./requirements.txt | while read -r line; do
            printf "      %s\n" "$line"
        done
        if [ $(wc -l < ./requirements.txt) -gt 5 ]; then
            printf "      ... and %s more packages\n" "$(($(wc -l < ./requirements.txt) - 5))"
        fi
    fi
done

# Create zip file from src directory contents
printf "Creating deployment zip package...\n"
zip -r ../app-deployment.zip . -x "*.pyc" -x "__pycache__/*" -x ".git/*" -x ".venv/*"
if [ $? -ne 0 ]; then
    cd "$SCRIPT_DIR" # Go back to original script dir before exiting
    step_error_exit "Failed to create zip package from src directory."
fi
step_success "Deployment package created: ../app-deployment.zip"

# Navigate back to the script's directory (project root)
cd "$SCRIPT_DIR" || step_error_exit "Failed to return to script directory."

step_info "Deploying application code via zip deployment to $WEB_APP_NAME"

az webapp deploy \
    --name "$WEB_APP_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --src-path "./app-deployment.zip" \
    --type zip \
    --async false # Wait for deployment to complete

DEPLOY_STATUS=$?

step_info "Cleaning up temporary deployment package"
rm -f ./app-deployment.zip
step_success "Cleanup complete"

if [ $DEPLOY_STATUS -ne 0 ]; then
    step_error_exit "Failed to deploy application zip package. Check Azure portal or logs."
fi

# --- Set App Settings for Selected Model ---
step_info "Updating App Service configuration for selected model: $MODEL_NAME"
az webapp config appsettings set \
    --name "$WEB_APP_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --settings AZURE_OPENAI_DEPLOYMENT_NAME="$MODEL_NAME" \
    --output none

if [ $? -ne 0 ]; then
    step_warning "Failed to set AZURE_OPENAI_DEPLOYMENT_NAME app setting. The application might use the wrong model or default."
else
    step_success "App Service configured to use model: $MODEL_NAME"
fi

# --- Post-deployment verification ---
step_info "Verifying deployment"

# Function to get publishing credentials
get_publish_profile() {
    # Get the publishing profile and extract credentials
    PUBLISH_PROFILE=$(az webapp deployment list-publishing-profiles \
        --name "$WEB_APP_NAME" \
        --resource-group "$RESOURCE_GROUP" \
        --output json)
    
    if [ -z "$PUBLISH_PROFILE" ]; then
        step_warning "Could not retrieve publishing profile. Skipping post-deployment verification."
        return 1
    fi
    
    # Extract the first publishing username and password
    PUBLISH_USERNAME=$(echo "$PUBLISH_PROFILE" | jq -r '.[0].userName')
    PUBLISH_PASSWORD=$(echo "$PUBLISH_PROFILE" | jq -r '.[0].userPWD')
    
    if [ -z "$PUBLISH_USERNAME" ] || [ -z "$PUBLISH_PASSWORD" ]; then
        step_warning "Could not extract publishing credentials. Skipping post-deployment verification."
        return 1
    fi
    
    return 0
}

verify_file_deployed() {
    local file_path="$1"
    local display_name="$2"
    local kudu_url="https://${WEB_APP_NAME}.scm.azurewebsites.net/api/vfs/site/wwwroot/${file_path}"
    
    # Use curl with basic auth to check if file exists
    HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -u "$PUBLISH_USERNAME:$PUBLISH_PASSWORD" "$kudu_url")
    
    if [ "$HTTP_STATUS" = "200" ]; then
        printf "${GREEN}✓ %s successfully deployed${NC}\n" "$display_name"
        return 0
    else
        printf "${YELLOW}⚠ Warning: Could not verify %s deployment (HTTP status: %s)${NC}\n" "$display_name" "$HTTP_STATUS"
        return 1
    fi
}

# Only proceed with verification if we can get publishing credentials
if get_publish_profile; then
    printf "Verifying critical files were deployed...\n"
    verify_file_deployed "app.py" "Application code"
    verify_file_deployed "requirements.txt" "Python dependencies"
    verify_file_deployed "Procfile" "Deployment configuration"
else
    printf "Skipping post-deployment verification due to credential issues.\n"
fi

# --- Finalization ---
step_success "Application code deployment completed successfully."

# Restart the web app
step_info "Restarting Web App $WEB_APP_NAME"
az webapp restart --name "$WEB_APP_NAME" --resource-group "$RESOURCE_GROUP" --output none
if [ $? -ne 0 ]; then
    printf "${YELLOW}⚠ Warning: Failed to issue restart command for the web app. Please check the Azure portal.${NC}\n"
else
    step_success "Web App restart command issued."
fi

# Print out the app URL
WEB_APP_URL="https://$(az webapp show --name "$WEB_APP_NAME" --resource-group "$RESOURCE_GROUP" --query defaultHostName -o tsv)"
step_success "Deployment finished. App should be available at: ${WEB_APP_URL}"

# Print helpful links
printf "\n${YELLOW}Useful links:${NC}\n"
printf "  Application URL: ${GREEN}%s${NC}\n" "$WEB_APP_URL"
printf "  Health endpoint: ${GREEN}%s/health${NC}\n" "$WEB_APP_URL"
printf "  App logs: ${GREEN}https://portal.azure.com/#@/resource/subscriptions/a3b64ac1-4ca3-4f9c-9465-f5a9abfbfb38/resourceGroups/%s/providers/%s/type/logStreams${NC}\n" "$RESOURCE_GROUP" "$WEB_APP_NAME"

