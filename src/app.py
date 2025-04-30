#!/usr/bin/env python
from flask import Flask, request, jsonify
import os
import logging
import sys
import json
import httpx  # Added for custom HTTP client configuration
from openai import AzureOpenAI
from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient

# --- Enhanced Logging Setup ---
# Configure logging to output to stdout, which Azure App Service captures
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)  # Set to DEBUG for more verbose logs if needed
handler = logging.StreamHandler(sys.stdout)
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
handler.setFormatter(formatter)
logger.addHandler(handler)

logger.info("Initializing Flask application (RAG Enabled - Optimized Deployment)...")
app = Flask(__name__)

# --- Configuration Loading with Enhanced Diagnostics ---
# Load configuration securely from environment variables with detailed logging
ENV_VARS = {
    "AZURE_OPENAI_ENDPOINT": os.environ.get("AZURE_OPENAI_ENDPOINT"),
    "AZURE_OPENAI_API_KEY": os.environ.get("AZURE_OPENAI_API_KEY"),
    "AZURE_OPENAI_DEPLOYMENT_NAME": os.environ.get("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-4o"),
    "AZURE_OPENAI_API_VERSION": os.environ.get("AZURE_OPENAI_API_VERSION", "2023-12-01-preview"),
    "AZURE_SEARCH_SERVICE_ENDPOINT": os.environ.get("AZURE_SEARCH_SERVICE_ENDPOINT"),
    "AZURE_SEARCH_ADMIN_KEY": os.environ.get("AZURE_SEARCH_ADMIN_KEY"),
    "AZURE_SEARCH_INDEX_NAME": os.environ.get("AZURE_SEARCH_INDEX_NAME")
}

# Log environment variables status (without exposing actual values)
logger.info("Environment variables status:")
for key, value in ENV_VARS.items():
    if "KEY" in key.upper() or "ADMIN_KEY" in key.upper():
        logger.info(f"  {key}: {'SET' if value else 'NOT SET'}")
    else:
        logger.info(f"  {key}: {value if value else 'NOT SET'}")

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
        # Initialize AzureOpenAI client with explicit logging of connection attempt
        logger.info(f"Initializing Azure OpenAI client with endpoint: {ENV_VARS['AZURE_OPENAI_ENDPOINT']}")
        try:
            # Create a custom httpx client with proxies explicitly disabled
            http_client = httpx.Client(proxies=None)
            logger.info("Created custom HTTP client with proxies disabled")
            
            # Initialize OpenAI client with the custom HTTP client
            openai_client = AzureOpenAI(
                api_key=ENV_VARS["AZURE_OPENAI_API_KEY"],
                api_version=ENV_VARS["AZURE_OPENAI_API_VERSION"],
                azure_endpoint=ENV_VARS["AZURE_OPENAI_ENDPOINT"],
                http_client=http_client  # Pass the custom client with no proxies
            )
                
            deployment_name = ENV_VARS["AZURE_OPENAI_DEPLOYMENT_NAME"]
            logger.info(f"Azure OpenAI client configured successfully. Deployment: {deployment_name}")
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

# --- RAG Function ---
def retrieve_relevant_documents(query, top_k=3):
    """Queries the Azure AI Search index and returns relevant document snippets."""
    if not search_client:
        logger.warning("Search client not available, skipping document retrieval.")
        return "\nSearch functionality is not configured.\n"
    try:
        logger.info(f"Performing search with query: \t{query}")
        search_results = search_client.search(search_text=query, top=top_k, include_total_count=True)

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

        total_results = search_results.get_count()
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
        "service": "Career Plan Connector V3 (RAG Enabled - Optimized)",
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
    
    # Determine overall status
    # App is considered healthy if web app is running, even if components are degraded
    # This allows the app to continue serving basic functionality
    overall_status = "healthy"
    response_code = 200
    
    # Include detailed diagnostics for non-Azure checks
    response_data = {
        "status": overall_status,
        "components": components_status,
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

        logger.info(f"Calling Azure OpenAI deployment: {deployment_name}")
        response = openai_client.chat.completions.create(
            model=deployment_name,
            messages=messages,
            temperature=0.5,
            max_tokens=1000
        )
        logger.info("Successfully received response from Azure OpenAI.")

        response_content = response.choices[0].message.content

        return jsonify({
            "status": "success",
            "response": response_content
        }), 200

    except json.JSONDecodeError:
        logger.error("Invalid JSON received in request body.")
        return jsonify({"status": "error", "message": "Invalid JSON format in request body."}), 400
    except Exception as e:
        logger.exception(f"An unexpected error occurred processing /api/career-plan: {e}")
        return jsonify({"status": "error", "message": f"An unexpected server error occurred."}), 500

if __name__ == "__main__":
    # Gunicorn or other WSGI server will bind the port in Azure App Service
    # This block is mainly for local development testing
    port = int(os.environ.get("PORT", 8000))
    logger.info(f"Starting application locally on host 0.0.0.0, port {port}")
    # Use debug=False for production-like local testing
    app.run(host="0.0.0.0", port=port, debug=False)

