#!/bin/bash
# SAR Multi-Agent System Demo Script
# Demonstrates end-to-end functionality including:
# - Service startup
# - File upload and analysis
# - Multi-turn conversations
# - Task dispatch mechanism

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
API_URL="${API_URL:-http://localhost:8080}"
SESSION_ID="demo-$(date +%s)"

echo -e "${BLUE}================================================${NC}"
echo -e "${BLUE}   SAR Multi-Agent System Demonstration${NC}"
echo -e "${BLUE}================================================${NC}"
echo ""

# Function to wait for service
wait_for_service() {
    local url=$1
    local name=$2
    local max_attempts=30
    local attempt=1
    
    echo -e "${YELLOW}Waiting for $name to be ready...${NC}"
    while [ $attempt -le $max_attempts ]; do
        if curl -s "$url" > /dev/null 2>&1; then
            echo -e "${GREEN}✓ $name is ready${NC}"
            return 0
        fi
        echo "  Attempt $attempt/$max_attempts..."
        sleep 2
        ((attempt++))
    done
    echo -e "${RED}✗ $name failed to start${NC}"
    return 1
}

# Function to check Redis
check_redis() {
    echo -e "${YELLOW}Checking Redis connection...${NC}"
    if docker exec redis redis-cli PING 2>/dev/null | grep -q "PONG"; then
        echo -e "${GREEN}✓ Redis is running${NC}"
        return 0
    else
        echo -e "${RED}✗ Redis is not available${NC}"
        return 1
    fi
}

# Function to show stream status
show_stream_status() {
    echo -e "\n${BLUE}--- Redis Stream Status ---${NC}"
    for stream in mission.new weather.forecast.raw health.assessment.raw history.out.raw photo.analysis.raw path.analysis.raw logistics.status.raw; do
        count=$(docker exec redis redis-cli XLEN $stream 2>/dev/null || echo "0")
        echo "  $stream: $count messages"
    done
    echo ""
}

# Step 1: Start services
echo -e "\n${BLUE}Step 1: Starting services${NC}"
echo "=========================================="

if [ "$1" != "--skip-startup" ]; then
    echo "Starting Docker Compose services..."
    docker compose up -d
    
    # Wait for services
    sleep 5
    check_redis
    wait_for_service "$API_URL/health" "API Gateway"
else
    echo "Skipping service startup (--skip-startup flag)"
fi

# Step 2: Show initial status
echo -e "\n${BLUE}Step 2: Initial System Status${NC}"
echo "=========================================="
show_stream_status

# Step 3: Create a test mission
echo -e "\n${BLUE}Step 3: Creating Test Mission${NC}"
echo "=========================================="

MISSION_JSON='{
  "mission_id": "demo-mission-001",
  "status": "active",
  "location": {
    "name": "San Luis Obispo County",
    "latitude": 35.2828,
    "longitude": -120.6596,
    "area_km2": 50
  },
  "person": {
    "name": "John Smith",
    "age": 65,
    "gender": "male",
    "description": "Caucasian male, 5ft 10in, gray hair, wearing red jacket",
    "known_conditions": ["type 2 diabetes", "mild dementia"],
    "last_seen": "hiking trail near Bishop Peak",
    "time_missing": "18 hours"
  },
  "created_at": "'$(date -u +"%Y-%m-%dT%H:%M:%SZ")'"
}'

echo "Creating mission with person data..."
echo "$MISSION_JSON" | jq '.' 2>/dev/null || echo "$MISSION_JSON"

# Publish mission to Redis stream
docker exec redis redis-cli XADD mission.new '*' body "$MISSION_JSON" 2>/dev/null || {
    echo -e "${YELLOW}Note: Direct Redis write may require envelope format${NC}"
}

# Step 4: Multi-turn Conversation Demo
echo -e "\n${BLUE}Step 4: Multi-Turn Conversation Demo${NC}"
echo "=========================================="

echo -e "\n${GREEN}Query 1: Initial situation analysis${NC}"
RESPONSE1=$(curl -s -X POST "$API_URL/query" \
  -H "Content-Type: application/json" \
  -d '{
    "question": "What is the current search and rescue situation? Summarize what we know about the missing person and current conditions.",
    "session_id": "'$SESSION_ID'"
  }' 2>/dev/null || echo '{"error": "API not available"}')

echo "Response:"
echo "$RESPONSE1" | jq -r '.response // .error // .' 2>/dev/null | head -20
echo "..."

sleep 2

echo -e "\n${GREEN}Query 2: Follow-up using context${NC}"
RESPONSE2=$(curl -s -X POST "$API_URL/query" \
  -H "Content-Type: application/json" \
  -d '{
    "question": "Based on what you just told me, what should be our search priorities given the weather conditions?",
    "session_id": "'$SESSION_ID'"
  }' 2>/dev/null || echo '{"error": "API not available"}')

echo "Response:"
echo "$RESPONSE2" | jq -r '.response // .error // .' 2>/dev/null | head -20
echo "..."

sleep 2

echo -e "\n${GREEN}Query 3: Resource availability${NC}"
RESPONSE3=$(curl -s -X POST "$API_URL/query" \
  -H "Content-Type: application/json" \
  -d '{
    "question": "What resources do we have available? Check our equipment and personnel inventory.",
    "session_id": "'$SESSION_ID'"
  }' 2>/dev/null || echo '{"error": "API not available"}')

echo "Response:"
echo "$RESPONSE3" | jq -r '.response // .error // .' 2>/dev/null | head -20
echo "..."

# Step 5: Show updated stream status
echo -e "\n${BLUE}Step 5: Updated Stream Status${NC}"
echo "=========================================="
show_stream_status

# Step 6: File Upload Demo (if files exist)
echo -e "\n${BLUE}Step 6: File Upload Demo${NC}"
echo "=========================================="

TEST_IMAGE="data/test_files/sample_search_area.jpg"
if [ -f "$TEST_IMAGE" ]; then
    echo "Uploading test image for analysis..."
    curl -s -X POST "$API_URL/upload/analyze" \
      -F "files=@$TEST_IMAGE" \
      -F "mission_id=demo-mission-001" \
      -F "session_id=$SESSION_ID" 2>/dev/null | jq '.' || echo "Upload response received"
else
    echo -e "${YELLOW}No test image available at $TEST_IMAGE${NC}"
    echo "To test file upload:"
    echo "  curl -X POST $API_URL/upload/analyze -F 'files=@your_image.jpg'"
fi

# Step 7: Health endpoint check
echo -e "\n${BLUE}Step 7: API Health Check${NC}"
echo "=========================================="
curl -s "$API_URL/health" 2>/dev/null | jq '.' || echo "Health check failed"

# Summary
echo -e "\n${BLUE}================================================${NC}"
echo -e "${GREEN}Demo Complete!${NC}"
echo -e "${BLUE}================================================${NC}"
echo ""
echo "Session ID: $SESSION_ID"
echo ""
echo "Next steps:"
echo "  1. View logs: docker compose logs -f command_agent"
echo "  2. Interactive CLI: python -m agents.command_agent.main --mode cli"
echo "  3. Check streams: docker exec redis redis-cli XLEN <stream_name>"
echo ""
echo -e "${BLUE}================================================${NC}"
