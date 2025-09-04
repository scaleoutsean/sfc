#!/bin/sh

###############################################################################
# Synopsis:                                                                   #
# Entrypoint script for InfluxDB 3 Core container in SolidFire Collector      #
#   version 2.1 and above.                                                    #
#                                                                             #
# Author: @scaleoutSean (Github)                                              #
# Repository: https://github.com/scaleoutsean/sfc                             #
# License: the Apache License Version 2.0                                     #
###############################################################################


# Entrypoint for influxdb3-core: loads S3 credentials if present, then execs influxdb3

echo "[DEBUG]    echo "SFC token already exists, attempting to delete and recreate..."
    DELETE_RESPONSE=$(echo "yes" | influxdb3 token delete --token-name "sfc" --host "$SERVER_URL" --token "$ADMIN_TOKEN" 2>&1)
    echo "Delete response: $DELETE_RESPONSE"DE_ID=$NODE_ID"

# Load credentials file if present
if [ -f "${S3_CREDENTIALS_FILE:-/influxdb_credentials/credentials}" ]; then
  set -a
  . "${S3_CREDENTIALS_FILE:-/influxdb_credentials/credentials}"
  set +a
fi

# Ensure NODE_ID is set (Compose wins if present)
if [ -z "$NODE_ID" ]; then
  NODE_ID="s169"
fi
export NODE_ID

echo "[DEBUG] NODE_ID=$NODE_ID"
echo "[DEBUG] Environment dump:"
env


curl -v --cacert /home/influxdb3/certs/ca.crt https://s3:7070/
# 
ls -l /home/influxdb3/certs/ca.crt
echo ""
echo ""
sleep 1

# Export TLS CA certificate path for InfluxDB
export INFLUXDB3_TLS_CA="${INFLUXDB3_TLS_CA:-/home/influxdb3/certs/ca.crt}"

# Also set common SSL environment variables that HTTP clients use
export SSL_CERT_FILE="${INFLUXDB3_TLS_CA}"
export CURL_CA_BUNDLE="${INFLUXDB3_TLS_CA}"
export REQUESTS_CA_BUNDLE="${INFLUXDB3_TLS_CA}"

echo "[DEBUG] SSL environment variables:"
echo "INFLUXDB3_TLS_CA=$INFLUXDB3_TLS_CA"
echo "SSL_CERT_FILE=$SSL_CERT_FILE"
echo "CURL_CA_BUNDLE=$CURL_CA_BUNDLE"

# Function to generate tokens after InfluxDB starts
generate_tokens() {
  echo "Waiting for InfluxDB to be ready for token generation..."
  sleep 5  # Give InfluxDB time to start
  
  # Set up token file path
  TOKEN_FILE="${TOKEN_FILE:-/influxdb_tokens/sfc.token}"
  
  # Create directory if it doesn't exist
  mkdir -p "$(dirname "$TOKEN_FILE")"
   

  # Set CLI to use HTTPS with the correct hostname that matches the certificate
  export INFLUXDB3_HOST_URL="https://influxdb:8181"
  
  # Don't try to list tokens initially - we don't have a valid token yet
  echo "Starting token generation process..."

  echo "Attempting to create admin token (works if none exists)..."
  # First try to create the admin token (works if none exists)
  ADMIN_TOKEN_OUTPUT=$(/home/influx/.influxdb/influxdb3 create token --admin --host "https://influxdb:8181" --tls-ca "${INFLUXDB3_TLS_CA}" 2>&1)
  echo "Admin token creation attempt:"
  echo "$ADMIN_TOKEN_OUTPUT"
  
  # Extract the admin token from CLI output
  ADMIN_TOKEN=$(echo "$ADMIN_TOKEN_OUTPUT" | grep "^Token:" | cut -d' ' -f2)
  
  echo "DEBUG: ADMIN_TOKEN='$ADMIN_TOKEN'"
  echo "DEBUG: Checking for 'token name already exists' in output"
  echo "DEBUG: grep result:"
  echo "$ADMIN_TOKEN_OUTPUT" | grep "token name already exists" || echo "DEBUG: No match found"
  
  if [ -z "$ADMIN_TOKEN" ] && echo "$ADMIN_TOKEN_OUTPUT" | grep -q "token name already exists"; then
    echo "DEBUG: Condition matched - entering regenerate block"
    echo "Admin token already exists, using regenerate via recovery endpoint..."
    # Use regenerate to get the existing admin token
    ADMIN_TOKEN_OUTPUT=$(echo "yes" | /home/influx/.influxdb/influxdb3 create token --admin --regenerate --host "https://influxdb:8182" --tls-ca "${INFLUXDB3_TLS_CA}" 2>&1)
    echo "Admin token regeneration:"
    echo "$ADMIN_TOKEN_OUTPUT"
    # Extract token from regenerate output (different format)
    ADMIN_TOKEN=$(echo "$ADMIN_TOKEN_OUTPUT" | grep "^Token:" | cut -d' ' -f2)
    # If that doesn't work, try alternative extraction methods
    if [ -z "$ADMIN_TOKEN" ]; then
      # Try extracting from the HTTP header line
      ADMIN_TOKEN=$(echo "$ADMIN_TOKEN_OUTPUT" | grep "Authorization: Bearer" | sed 's/.*Authorization: Bearer //')
    fi
    echo "DEBUG: Extracted ADMIN_TOKEN from regenerate: '$ADMIN_TOKEN'"
  fi
  
  if [ -n "$ADMIN_TOKEN" ]; then
    # Show first 20 characters of token for verification (sh-compatible)
    ADMIN_TOKEN_PREFIX=$(echo "$ADMIN_TOKEN" | cut -c1-20)
    echo "Admin token obtained successfully: ${ADMIN_TOKEN_PREFIX}..."
    echo "Now creating named SFC token..."
    
    # First try to create the token
    TOKEN_RESPONSE=$(/home/influx/.influxdb/influxdb3 create token --admin --name "sfc" --host "https://influxdb:8181" --tls-ca "${INFLUXDB3_TLS_CA}" --token "$ADMIN_TOKEN" 2>&1)
    echo "SFC token creation response: $TOKEN_RESPONSE"
    
    # If creation failed because token exists, try to delete and recreate
    if echo "$TOKEN_RESPONSE" | grep -q "token name already exists"; then
      echo "SFC token already exists, attempting to delete and recreate..."
      DELETE_RESPONSE=$(echo "yes" | /home/influx/.influxdb/influxdb3 delete token --token-name "sfc" --host "https://influxdb:8181" --tls-ca "${INFLUXDB3_TLS_CA}" --token "$ADMIN_TOKEN" 2>&1)
      echo "Delete response: $DELETE_RESPONSE"
      
      # Try creating again
      TOKEN_RESPONSE=$(/home/influx/.influxdb/influxdb3 create token --admin --name "sfc" --host "https://influxdb:8181" --tls-ca "${INFLUXDB3_TLS_CA}" --token "$ADMIN_TOKEN" 2>&1)
      echo "SFC token recreation response: $TOKEN_RESPONSE"
    fi
  else
    echo "Failed to obtain admin token"
    echo "DEBUG: ADMIN_TOKEN_OUTPUT was:"
    echo "$ADMIN_TOKEN_OUTPUT"
    TOKEN_RESPONSE="Failed to obtain admin token"
  fi
  
  if echo "$TOKEN_RESPONSE" | grep -q "Token:"; then
    # Extract and save the SFC token from CLI output (handle potential whitespace and ANSI codes)
    echo "$TOKEN_RESPONSE" | grep "Token:" | sed 's/.*Token: *//' | sed 's/\x1b\[[0-9;]*m//g' | tr -d '\n\r ' | head -1 > "$TOKEN_FILE"
    echo "SFC token saved to $TOKEN_FILE"
    ls -lat "$TOKEN_FILE"
    
    # Create the 'sfc' database using the admin token
    echo "Creating 'sfc' database..."
    CREATE_DB_RESPONSE=$(/home/influx/.influxdb/influxdb3 create database "sfc" --host "https://influxdb:8181" --tls-ca "${INFLUXDB3_TLS_CA}" --token "$ADMIN_TOKEN" 2>&1)
    echo "Database creation response: $CREATE_DB_RESPONSE"
    
    if echo "$CREATE_DB_RESPONSE" | grep -q "successfully created" || echo "$CREATE_DB_RESPONSE" | grep -q "already exists"; then
      echo "Database 'sfc' is ready"
    else
      echo "Warning: Database creation may have failed - check response above"
    fi
    
    # Also save the admin token for reference
    if [ -f /tmp/admin_token.json ] && grep -q '"token"' /tmp/admin_token.json; then
      echo "Admin token also available in /tmp/admin_token.json"
    fi
  else
    echo "Failed to create SFC token, writing dummy token"
    echo "dummy-token-failed" > "$TOKEN_FILE"
  fi
  
  echo "Updated token list:"
  /home/influx/.influxdb/influxdb3 show tokens
  
  echo "Token generation completed"
}

# Start token generation in the background
generate_tokens &

# Start influxdb3 with all required arguments and admin token recovery endpoint
exec /home/influx/.influxdb/influxdb3 serve \
  --node-id="$NODE_ID" \
  --object-store="${OBJECT_STORE:-s3}" \
  --aws-access-key-id="${AWS_ACCESS_KEY_ID}" \
  --aws-secret-access-key="${AWS_SECRET_ACCESS_KEY}" \
  --bucket="${BUCKET}" \
  --aws-endpoint="${S3_ENDPOINT}" \
  --tls-key="${TLS_KEY}" \
  --tls-cert="${TLS_CERT}" \
  --tls-minimum-version="${TLS_MIN_VERSION:-tls-1.3}" \
  --http-bind="${HTTP_BIND:-0.0.0.0:8181}" \
  --wal-flush-interval="${WAL_FLUSH_INTERVAL:-120s}" \
  --admin-token-recovery-http-bind="0.0.0.0:8182"


