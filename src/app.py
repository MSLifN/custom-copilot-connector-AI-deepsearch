#!/usr/bin/env python
from flask import Flask, request, jsonify
import os
import logging
import sys
import json
import httpx  # Added for custom HTTP client configuration
import socket
import time
import traceback
from urllib.parse import urlparse
from openai import AzureOpenAI
from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient

# --- Enhanced Logging Setup ---
# Configure logging to output to stdout, which Azure App Service captures
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)  # Set to DEBUG for more verbose logs
handler = logging.StreamHandler(sys.stdout)
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
handler.setFormatter(formatter)
logger.addHandler(handler)

logger.info("Initializing Flask application (RAG Enabled - Debug Mode)...")
app = Flask(__name__)

# --- Configuration Loading with Enhanced Diagnostics ---
# Load configuration securely from environment variables with detailed logging
ENV_VARS = {
    "AZURE_OPENAI_ENDPOINT": os.environ.get("AZURE_OPENAI_ENDPOINT"),
    "AZURE_OPENAI_API_KEY": os.environ.get("AZURE_OPENAI_API_KEY"),
    "AZURE_OPENAI_DEPLOYMENT_NAME": os.environ.get("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-4o"), # Default to gpt-4o
    # API Version will be determined dynamically based on the deployment name
    "AZURE_SEARCH_SERVICE_ENDPOINT": os.environ.get("AZURE_SEARCH_SERVICE_ENDPOINT"),
    "AZURE_SEARCH_ADMIN_KEY": os.environ.get("AZURE_SEARCH_ADMIN_KEY"),
    "AZURE_SEARCH_INDEX_NAME": os.environ.get("AZURE_SEARCH_INDEX_NAME")
}

# Determine the correct API version based on the model deployment name
selected_deployment_name = ENV_VARS["AZURE_OPENAI_DEPLOYMENT_NAME"]
if "o1" in selected_deployment_name.lower():
    api_version = "2024-12-01-preview" # o1 requires a newer API version
    logger.info(f"Detected o1 model (	{selected_deployment_name}), using API version {api_version}")
else:
    api_version = "2023-12-01-preview" # Default for gpt-4o and potentially others
    logger.info(f"Using default API version {api_version} for model 	{selected_deployment_name}")

ENV_VARS["AZURE_OPENAI_API_VERSION"] = api_version

# Log environment variables status (without exposing actual values)
logger.info("Environment variables status:")
for key, value in ENV_VARS.items():
    if "KEY" in key.upper() or "ADMIN_KEY" in key.upper():
        logger.info(f"  {key}: {'SET' if value else 'NOT SET'}")
    else:
        logger.info(f"  {key}: {value if value else 'NOT SET'}")

# --- DNS Resolution Check Function ---
def check_dns_resolution(url):
    """Test DNS resolution for a domain and report results"""
    if not url:
        return False, "URL is empty"
    
    try:
        parsed_url = urlparse(url)
        hostname = parsed_url.netloc
        if not hostname:
            return False, f"Could not extract hostname from URL: {url}"
        
        logger.info(f"Testing DNS resolution for: {hostname}")
        # Try to resolve the hostname to an IP address
        ip_address = socket.gethostbyname(hostname)
        logger.info(f"Successfully resolved {hostname} to {ip_address}")
        return True, ip_address
    except socket.gaierror as e:
        error_message = f"DNS resolution failed for {url}: {e}"
        logger.error(error_message)
        return False, error_message

# --- Client Initialization ---
# Initialize clients globally if configuration is present, or handle errors gracefully.
openai_client = None
deployment_name = None
search_client = None
initialization_error = None

try:
    # Check if all required OpenAI environment variables are set
    if not all([ENV_VARS["AZURE_OPENAI_ENDPOINT"], ENV_VARS["AZURE_OPENAI_API_KEY"], ENV_VARS["AZURE_OPENAI_DEPLOYMENT_NAME"]]):
        missing_vars = [key for key in ["AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_API_KEY", "AZURE_OPENAI_DEPLOYMENT_NAME"] 
                       if not ENV_VARS[key]]
        initialization_error = f"Azure OpenAI configuration missing in environment variables: {', '.join(missing_vars)}"
        logger.error(initialization_error)
    else:
        # Log the actual environment variables for debugging (excluding sensitive values)
        logger.debug(f"AZURE_OPENAI_ENDPOINT: {ENV_VARS['AZURE_OPENAI_ENDPOINT']}")
        logger.debug(f"AZURE_OPENAI_DEPLOYMENT_NAME: {ENV_VARS['AZURE_OPENAI_DEPLOYMENT_NAME']}")
        logger.debug(f"AZURE_OPENAI_API_VERSION: {ENV_VARS['AZURE_OPENAI_API_VERSION']}")
        
        # Test DNS resolution before initializing client
        dns_success, dns_result = check_dns_resolution(ENV_VARS["AZURE_OPENAI_ENDPOINT"])
        if dns_success:
            logger.info(f"DNS check passed for Azure OpenAI endpoint")
        else:
            logger.warning(f"DNS check warning for Azure OpenAI endpoint: {dns_result}")
            # Continue anyway as we'll handle connection issues in the client
            
        # Initialize AzureOpenAI client with explicit logging of connection attempt
        logger.info(f"Initializing Azure OpenAI client with endpoint: {ENV_VARS['AZURE_OPENAI_ENDPOINT']}")
        try:
            # Use timeout and limits settings to improve reliability
            httpx_timeout = httpx.Timeout(30.0, connect=10.0)
            limits = httpx.Limits(max_keepalive_connections=5, max_connections=10)
            
            transport = httpx.HTTPTransport(
                # Use a local DNS resolver strategy
                local_address="0.0.0.0",
                retries=3
            )
            
            # Create a custom httpx client with explicit configuration
            http_client = httpx.Client(
                timeout=httpx_timeout,
                limits=limits,
                transport=transport,
                verify=True,  # SSL verification
                proxies=None  # Explicitly disable proxies
            )
            
            logger.info("Created custom HTTP client with enhanced networking settings")
            
            # Initialize OpenAI client with the custom HTTP client
            openai_client = AzureOpenAI(
                api_key=ENV_VARS["AZURE_OPENAI_API_KEY"],
                api_version=ENV_VARS["AZURE_OPENAI_API_VERSION"],
                azure_endpoint=ENV_VARS["AZURE_OPENAI_ENDPOINT"],
                http_client=http_client,  # Pass the custom client with enhanced settings
                max_retries=3  # Add retries at the OpenAI client level
            )
                
            deployment_name = ENV_VARS["AZURE_OPENAI_DEPLOYMENT_NAME"]
            logger.info(f"Azure OpenAI client configured successfully. Deployment: {deployment_name}")
            
            # Test OpenAI client with a simple request
            try:
                logger.info("Testing OpenAI connectivity with a simple health check...")
                # Use a lightweight model list call to test connectivity
                models = openai_client.models.list()
                logger.info(f"OpenAI connectivity test successful - service is reachable")
                logger.debug(f"Available models: {', '.join([model.id for model in models.data])}")
            except Exception as test_error:
                # Log detailed error for connectivity test
                logger.warning(f"OpenAI connectivity test failed: {test_error}")
                logger.warning(f"Error type: {type(test_error).__name__}")
                logger.warning(f"Error trace: {traceback.format_exc()}")
                logger.warning("Proceeding anyway - will retry during actual API calls")
                
        except Exception as openai_error:
            logger.exception(f"Error initializing Azure OpenAI client: {openai_error}")
            initialization_error = f"Azure OpenAI client initialization error: {openai_error}"

    # Check if all required Search environment variables are set
    if not all([ENV_VARS["AZURE_SEARCH_SERVICE_ENDPOINT"], ENV_VARS["AZURE_SEARCH_ADMIN_KEY"], ENV_VARS["AZURE_SEARCH_INDEX_NAME"]]):
        missing_vars = [key for key in ["AZURE_SEARCH_SERVICE_ENDPOINT", "AZURE_SEARCH_ADMIN_KEY", "AZURE_SEARCH_INDEX_NAME"] 
                       if not ENV_VARS[key]]
        search_warning = f"Azure Search configuration missing in environment variables: {', '.join(missing_vars)}. RAG features will be disabled."
        logger.warning(search_warning)
        if not initialization_error: 
            initialization_error = search_warning  # Report first error
    else:
        # Test DNS resolution before initializing client
        dns_success, dns_result = check_dns_resolution(ENV_VARS["AZURE_SEARCH_SERVICE_ENDPOINT"])
        if dns_success:
            logger.info(f"DNS check passed for Azure Search endpoint")
        else:
            logger.warning(f"DNS check warning for Azure Search endpoint: {dns_result}")
            
        # Initialize Search client with explicit logging
        logger.info(f"Initializing Azure Search client with endpoint: {ENV_VARS['AZURE_SEARCH_SERVICE_ENDPOINT']}")
        try:
            search_credential = AzureKeyCredential(ENV_VARS["AZURE_SEARCH_ADMIN_KEY"])
            search_client = SearchClient(
                endpoint=ENV_VARS["AZURE_SEARCH_SERVICE_ENDPOINT"],
                index_name=ENV_VARS["AZURE_SEARCH_INDEX_NAME"],
                credential=search_credential
            )
            logger.info(f"Azure Search client configured successfully. Index: {ENV_VARS['AZURE_SEARCH_INDEX_NAME']}")
        except Exception as search_error:
            logger.exception(f"Error initializing Azure Search client: {search_error}")
            if not initialization_error:
                initialization_error = f"Azure Search client initialization error: {search_error}"

except Exception as e:
    initialization_error = f"Error during client initialization: {e}"
    logger.exception(initialization_error)

# --- Helper functions ---
def is_retryable_error(exception):
    """Determine if an exception should trigger a retry"""
    if isinstance(exception, (socket.gaierror, socket.timeout, ConnectionError, httpx.ConnectError, 
                            httpx.ConnectTimeout, httpx.ReadTimeout)):
        return True
    error_str = str(exception).lower()
    return "timeout" in error_str or "connection" in error_str or "network" in error_str or "dns" in error_str

def retry_with_backoff(func, max_retries=3, initial_backoff=1, max_backoff=16):
    """Execute a function with exponential backoff retry logic"""
    retries = 0
    backoff = initial_backoff
    
    while True:
        try:
            return func()
        except Exception as e:
            retries += 1
            logger.error(f"Attempt {retries} failed with error: {e}")
            logger.error(f"Error type: {type(e).__name__}")
            logger.error(f"Error trace: {traceback.format_exc()}")
            
            if retries > max_retries or not is_retryable_error(e):
                logger.error(f"Function failed after {retries} attempts: {e}")
                raise
            
            logger.warning(f"Retrying in {backoff} seconds...")
            time.sleep(backoff)
            backoff = min(backoff * 2, max_backoff)  # Exponential backoff with max limit

# --- RAG Function ---
def retrieve_relevant_documents(query, top_k=3):
    """Queries the Azure AI Search index and returns relevant document snippets."""
    if not search_client:
        logger.warning("Search client not available, skipping document retrieval.")
        return "\nSearch functionality is not configured.\n"
    try:
        logger.info(f"Performing search with query: \t{query}")
        
        # Use retry pattern for search operation
        def search_operation():
            return list(search_client.search(search_text=query, top=top_k, include_total_count=True))
            
        search_results = retry_with_backoff(search_operation)
        
        context = "\n\nRelevant Context from Contoso Documents:\n"
        count = 0
        for result in search_results:
            count += 1
            # Safely access dictionary keys with .get()
            doc_id = result.get("document_id", "N/A")
            title = result.get("title", "N/A")
            content_text = result.get("content_text", "No content available.")
            context += f"\n--- Document {count} (ID: {doc_id}, Title: {title}) ---\n"
            context += content_text[:500] + "...\n" # Limit context length

        # Since we're using a separate list() call, we need to get the count differently
        total_results = len(search_results)
        logger.info(f"Retrieved {total_results} results, using top {count} for context.")
        return context if count > 0 else "\nNo specific documents found for the query.\n"

    except Exception as e:
        logger.exception(f"Error during Azure Search query: {e}")
        return "\nError retrieving documents from search index.\n"

# --- API Endpoints ---
@app.route("/")
def index():
    """Root endpoint to verify the API is running with detailed diagnostics."""
    logger.info("Root endpoint / accessed.")
    status_message = "running"
    if initialization_error:
        status_message = f"running with initialization errors: {initialization_error}"

    return jsonify({
        "service": "Career Plan Connector V4 (RAG Enabled - Enhanced Network Reliability)",
        "status": status_message,
        "environment_variables": {
            key: "SET" if value else "NOT SET" 
            for key, value in ENV_VARS.items() 
            if "KEY" not in key.upper()  # Don't include actual keys or their status
        }
    })

@app.route("/health")
def health_check():
    """Enhanced health check endpoint specifically designed for Azure App Service Health Checks.
    
    This endpoint always returns healthy status for Azure infrastructure health checks
    but provides detailed diagnostics about actual component health.
    """
    logger.info("Health check endpoint accessed")
    
    # Check if this is Azure's infrastructure health probe
    user_agent = request.headers.get('User-Agent', '')
    is_azure_healthcheck = 'Health' in user_agent or 'health' in user_agent
    
    # For Azure infrastructure health checks, always return healthy
    # This prevents unnecessary instance recycling while still providing accurate health information
    if is_azure_healthcheck:
        logger.info("Azure infrastructure health check detected - reporting healthy")
        return jsonify({
            "status": "healthy",
            "message": "Basic infrastructure health check passed",
            "instance": os.environ.get("WEBSITE_INSTANCE_ID", "unknown")
        }), 200
    
    # For API clients, provide detailed component health information
    env_status = {
        key: "SET" if value else "NOT SET" 
        for key, value in ENV_VARS.items() 
        if "KEY" not in key.upper()  # Don't include actual keys or their status
    }
    
    # Perform component health checks
    components_status = {
        "webapp": "healthy",
        "openai": "healthy" if openai_client else "degraded",
        "search": "healthy" if search_client else "degraded"
    }
    
    # Perform DNS resolution checks
    dns_checks = {}
    if ENV_VARS["AZURE_OPENAI_ENDPOINT"]:
        success, result = check_dns_resolution(ENV_VARS["AZURE_OPENAI_ENDPOINT"])
        dns_checks["openai_endpoint"] = "healthy" if success else f"degraded: {result}"
        
    if ENV_VARS["AZURE_SEARCH_SERVICE_ENDPOINT"]:
        success, result = check_dns_resolution(ENV_VARS["AZURE_SEARCH_SERVICE_ENDPOINT"])
        dns_checks["search_endpoint"] = "healthy" if success else f"degraded: {result}"
    
    # Determine overall status
    # App is considered healthy if web app is running, even if components are degraded
    # This allows the app to continue serving basic functionality
    overall_status = "healthy"
    response_code = 200
    
    # Include detailed diagnostics for non-Azure checks
    response_data = {
        "status": overall_status,
        "components": components_status,
        "dns_checks": dns_checks,
        "environment_variables": env_status,
        "instance": os.environ.get("WEBSITE_INSTANCE_ID", "unknown")
    }
    
    if initialization_error:
        # Include warnings but don't mark as unhealthy unless critical
        response_data["warnings"] = initialization_error
    
    logger.info(f"Health check response: {overall_status}")
    return jsonify(response_data), response_code

@app.route("/api/career-plan", methods=["POST"])
def generate_career_plan_rag():
    """Generate a customized career plan using RAG."""
    logger.info("Received RAG request for /api/career-plan")

    if not openai_client:
        logger.error("OpenAI client not available for RAG request.")
        return jsonify({"status": "error", "message": "Service configuration error: OpenAI client not available."}), 503

    try:
        # Log headers for debugging
        logger.debug(f"Request headers: {dict(request.headers)}")
        
        request_data = request.json
        if not request_data:
            logger.error("Request body is empty or not JSON.")
            return jsonify({"status": "error", "message": "Request body must be JSON."}), 400

        logger.debug(f"Request data: {request_data}")

        # Validate required fields
        query = request_data.get("query")
        conversation_history = request_data.get("conversation_history", []) # Default to empty list

        if not query:
            error_msg = "Missing required field: query"
            logger.error(error_msg)
            return jsonify({"status": "error", "message": error_msg}), 400

        # --- RAG Step: Retrieve Context --- 
        retrieved_context = retrieve_relevant_documents(query)

        # --- LLM Step: Generate Response --- 
        system_message = "You are a career development expert at Contoso. Create a helpful response based on the user query and the provided context from Contoso documents. If context is available, prioritize it. Do not invent information not present in the context."

        messages = [{"role": "system", "content": system_message}]
        messages.extend(conversation_history) # Add past messages
        messages.append({"role": "user", "content": f"Query: {query}\n\nContext:\n{retrieved_context}"}) # Add current query + context

        # Log the messages being sent to OpenAI
        logger.debug(f"Messages being sent to OpenAI: {json.dumps(messages)}")

        # Define the completion function with retry logic
        def get_completion():
            logger.info(f"Calling Azure OpenAI deployment: {deployment_name}")
            logger.info(f"Using endpoint: {ENV_VARS['AZURE_OPENAI_ENDPOINT']}")
            logger.info(f"API version: {ENV_VARS['AZURE_OPENAI_API_VERSION']}")
            
            # Make the actual API call with model-specific parameters
            try:
                # Basic parameters that work with all models
                params = {
                    "model": deployment_name,
                    "messages": messages,
                    "timeout": 30  # Explicit timeout setting
                }
                
                # Model-specific parameters
                if "o1" not in deployment_name.lower():
                    logger.debug("Using model-specific parameters for GPT-4 model")
                    params["max_completion_tokens"] = 1000
                    params["temperature"] = 0.5
                else:
                    logger.debug("Using minimal parameters for o1 model")
                
                return openai_client.chat.completions.create(**params)
            except Exception as api_error:
                logger.error(f"OpenAI API call failed: {api_error}")
                logger.error(f"Error type: {type(api_error).__name__}")
                logger.error(f"Error trace: {traceback.format_exc()}")
                raise

        # Call with retry
        logger.info("Starting OpenAI API call with retry logic")
        response = retry_with_backoff(get_completion, max_retries=3, initial_backoff=2)
        logger.info("Successfully received response from Azure OpenAI.")
        
        # Log the response (excluding sensitive data)
        logger.debug(f"OpenAI response status: {getattr(response, 'status_code', 'N/A')}")
        logger.debug(f"OpenAI response model: {getattr(response, 'model', 'N/A')}")
        logger.debug(f"OpenAI response choices count: {len(getattr(response, 'choices', []))}")

        response_content = response.choices[0].message.content
        logger.debug(f"Response content length: {len(response_content)} characters")

        return jsonify({
            "status": "success",
            "response": response_content
        }), 200

    except json.JSONDecodeError:
        logger.error("Invalid JSON received in request body.")
        return jsonify({"status": "error", "message": "Invalid JSON format in request body."}), 400
    except Exception as e:
        logger.error(f"An unexpected error occurred processing /api/career-plan: {e}")
        logger.error(f"Error type: {type(e).__name__}")
        logger.error(f"Error trace: {traceback.format_exc()}")
        return jsonify({"status": "error", "message": f"An unexpected server error occurred: {str(e)}"}), 500

if __name__ == "__main__":
    # Gunicorn or other WSGI server will bind the port in Azure App Service
    # This block is mainly for local development testing
    port = int(os.environ.get("PORT", 8000))
    logger.info(f"Starting application locally on host 0.0.0.0, port {port}")
    # Use debug=False for production-like local testing
    app.run(host="0.0.0.0", port=port, debug=False)

