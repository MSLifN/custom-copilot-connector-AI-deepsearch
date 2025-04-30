#!/usr/bin/env python3
import os
import json
import argparse
import glob
from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    SearchIndex,
    SearchField,
    SearchFieldDataType,
    SimpleField,
    SearchableField
)

# Define the index schema
def create_index_schema(index_name):
    fields = [
        SimpleField(name="document_id", type=SearchFieldDataType.String, key=True, sortable=True, filterable=True, facetable=True),
        SearchableField(name="title", type=SearchFieldDataType.String, sortable=True, filterable=True, facetable=True),
        SearchableField(name="content_text", type=SearchFieldDataType.String),  # Flattened content for searching
        SearchableField(name="provider", type=SearchFieldDataType.String, filterable=True, facetable=True, sortable=True),
        SearchableField(name="department", type=SearchFieldDataType.String, filterable=True, facetable=True, sortable=True),
        SimpleField(name="company", type=SearchFieldDataType.String, filterable=True, facetable=True, sortable=True),
        SimpleField(name="last_updated", type=SearchFieldDataType.DateTimeOffset, sortable=True, filterable=True),
        # Add other relevant fields as needed, ensure they are filterable/searchable as required
    ]
    
    # Define the index
    index = SearchIndex(name=index_name, fields=fields)
    return index

# Function to flatten JSON content for indexing
def flatten_json_content(data, parent_key='', sep='_'):
    items = []
    if isinstance(data, dict):
        for k, v in data.items():
            new_key = f"{parent_key}{sep}{k}" if parent_key else k
            items.extend(flatten_json_content(v, new_key, sep=sep).items())
    elif isinstance(data, list):
        for i, v in enumerate(data):
            # Represent lists as key_index: value pairs or just concatenate strings
            if isinstance(v, (str, int, float, bool)):
                items.append((f"{parent_key}_{i}", str(v)))
            else:
                items.extend(flatten_json_content(v, f"{parent_key}_{i}", sep=sep).items())
    else:
        # Handle primitive types
        if isinstance(data, (str, int, float, bool)):
            items.append((parent_key, str(data)))
    return dict(items)

def prepare_document_for_indexing(doc_path):
    try:
        with open(doc_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Get filename and sanitize it for use as a key
        # Remove file extension and replace any non-allowed characters with underscores
        base_filename = os.path.basename(doc_path)
        sanitized_id = os.path.splitext(base_filename)[0].replace('.', '_')
        
        # Flatten the nested 'content' field into a single searchable string
        content_flat_dict = flatten_json_content(data.get('content', {}))
        content_text = ' '.join([f"{k}: {v}" for k, v in content_flat_dict.items()])
        
        # Map top-level fields and the flattened content
        index_doc = {
            "@search.action": "upload",  # Action for batch upload
            "document_id": data.get('document_id', sanitized_id),  # Use sanitized filename if ID missing
            "title": data.get('title', ''),
            "content_text": content_text,
            "provider": data.get('provider', ''),
            "department": data.get('department', ''),
            "company": data.get('company', 'Contoso'),  # Default if missing
            "last_updated": data.get('last_updated')  # Assumes ISO 8601 format
            # Add mappings for other fields defined in the schema
        }
        
        # Handle potential missing last_updated or convert format if needed
        if not index_doc["last_updated"]:
            del index_doc["last_updated"]  # Remove if empty/null
        
        return index_doc
    except Exception as e:
        print(f"Error processing document {doc_path}: {e}")
        return None

def main():
    parser = argparse.ArgumentParser(description='Setup Azure AI Search index and upload documents.')
    parser.add_argument('--endpoint', required=True, help='Azure AI Search service endpoint (e.g., https://your-search-service.search.windows.net)')
    parser.add_argument('--key', required=True, help='Azure AI Search admin key')
    parser.add_argument('--index-name', required=True, help='Name of the search index to create/update')
    parser.add_argument('--docs-path', default='./docs/samples', help='Path to the directory containing JSON documents')
    args = parser.parse_args()
    
    # Validate the endpoint URL
    if not args.endpoint or not args.endpoint.startswith(('http://', 'https://')):
        print(f"Error: Invalid endpoint URL: '{args.endpoint}'. The endpoint must start with http:// or https://")
        exit(1)
        
    print(f"Using AI Search endpoint: {args.endpoint}")
    print(f"Using index name: {args.index_name}")
    
    # Authenticate clients with retry policy
    credential = AzureKeyCredential(args.key)
    index_client = SearchIndexClient(endpoint=args.endpoint, credential=credential)
    search_client = SearchClient(endpoint=args.endpoint, index_name=args.index_name, credential=credential)
    
    # Create index with error handling
    try:
        print(f"Attempting to create or update index '{args.index_name}'...")
        index_schema = create_index_schema(args.index_name)
        result = index_client.create_or_update_index(index=index_schema)
        print(f"Index '{result.name}' created/updated successfully.")
    except Exception as e:
        print(f"Error creating/updating index: {e}")
        exit(1)
    
    # Load and upload documents with error handling
    try:
        doc_files = glob.glob(os.path.join(args.docs_path, '*.json'))
        if not doc_files:
            print(f"No JSON documents found in {args.docs_path}. Skipping upload.")
            exit(0)
        
        print(f"Found {len(doc_files)} JSON documents to upload.")
        
        documents_to_upload = []
        for doc_path in doc_files:
            index_doc = prepare_document_for_indexing(doc_path)
            if index_doc:
                documents_to_upload.append(index_doc)
        
        if not documents_to_upload:
            print("No valid documents prepared for upload.")
            exit(1)
        
        # Upload in batches with error handling
        print(f"Uploading {len(documents_to_upload)} documents to index '{args.index_name}'...")
        result = search_client.upload_documents(documents=documents_to_upload)
        successful_uploads = sum(1 for r in result if r.succeeded)
        print(f"Document upload completed. {successful_uploads}/{len(documents_to_upload)} documents uploaded successfully.")
        
        # Print errors for failed uploads
        for r in result:
            if not r.succeeded:
                print(f"  Failed to upload document with key {r.key}: {r.error_message}")
    except Exception as e:
        print(f"Error uploading documents: {e}")
        exit(1)

if __name__ == '__main__':
    main()

