#!/bin/bash

echo "=========================================="
echo "SAR Agent Integration System Test"
echo "Using Docker Compose with Individual Containers"
echo "=========================================="

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo "Docker is not running. Please start Docker first."
    exit 1
fi

# Check if containers are running
if ! docker-compose ps | grep -q "Up"; then
    echo "Starting all SAR agent containers..."
    docker-compose up -d
    echo "Waiting for containers to be ready..."
    sleep 15
fi

echo ""
echo "All Docker containers are running"
echo ""

# Function to check agent health
check_agent_health() {
    local agent_name=$1
    if docker ps | grep -q "$agent_name"; then
        echo "  [OK] $agent_name is running"
        return 0
    else
        echo "  [FAIL] $agent_name is not running"
        return 1
    fi
}

# Function to check Redis streams
check_redis_stream() {
    local stream_name=$1
    local count=$(docker exec redis redis-cli XLEN "$stream_name" 2>/dev/null)
    if [ "$count" -gt 0 ]; then
        echo "  [OK] $stream_name: $count messages"
        return 0
    else
        echo "  [PENDING] $stream_name: no messages yet"
        return 1
    fi
}

echo "Testing all agents..."
echo ""
echo "=========================================="
echo "1. CHECKING AGENT STATUS"
echo "=========================================="

# Check each agent container
check_agent_health "weather-agent"
check_agent_health "logistics-agent"
check_agent_health "health-agent"
check_agent_health "interview-agent"
check_agent_health "path-analysis-agent"
check_agent_health "photo-agent"
check_agent_health "history-agent"
check_agent_health "cluemeister-agent"

echo ""
echo "=========================================="
echo "2. CHECKING INFRASTRUCTURE"
echo "=========================================="

# Check Redis
if docker ps | grep -q "redis"; then
    echo " Redis is running"
    docker exec redis redis-cli ping > /dev/null 2>&1
    if [ $? -eq 0 ]; then
        echo " Redis is responding"
    else
        echo "Redis is not responding"
    fi
else
    echo "Redis is not running"
fi

echo ""
echo "=========================================="
echo "3. MONITORING AGENT OUTPUT"
echo "=========================================="
echo ""
echo "Waiting 30 seconds for agents to process data..."
sleep 30

echo ""
echo "Checking Redis Streams for agent output:"
echo ""

# Check outputs from each agent
check_redis_stream "weather.forecast.raw"
check_redis_stream "health.assessment.raw"
check_redis_stream "logistics.requests.raw"
check_redis_stream "interview.analysis.raw"
check_redis_stream "path.analysis.raw"
check_redis_stream "photo.analysis.raw"
check_redis_stream "history.out.raw"
check_redis_stream "cluemeister.analysis.raw"

echo ""
echo "=========================================="
echo "4. AGENT LOGS (Last 5 lines)"
echo "=========================================="
echo ""

# Show recent logs from each agent
for agent in weather-agent logistics-agent health-agent interview-agent path-analysis-agent photo-agent history-agent cluemeister-agent; do
    if docker ps | grep -q "$agent"; then
        echo "--- $agent ---"
        docker logs "$agent" --tail 5 2>&1 | tail -5
        echo ""
    fi
done

echo ""
echo "=========================================="
echo "5. SAMPLE MESSAGES"
echo "=========================================="
echo ""

# Function to show sample message from a stream
show_sample_message() {
    local stream=$1
    local agent=$2
    docker exec redis redis-cli XREVRANGE "$stream" + - COUNT 1 2>/dev/null | head -20
    if [ $? -eq 0 ]; then
        echo ""
    fi
}

echo "Recent messages from weather.forecast.raw:"
docker exec redis redis-cli XREVRANGE weather.forecast.raw + - COUNT 1 2>/dev/null | head -10
echo ""

echo "Recent messages from photo.analysis.raw:"
docker exec redis redis-cli XREVRANGE photo.analysis.raw + - COUNT 1 2>/dev/null | head -10
echo ""

echo "Recent messages from path.analysis.raw:"
docker exec redis redis-cli XREVRANGE path.analysis.raw + - COUNT 1 2>/dev/null | head -10
echo ""

echo "Recent messages from cluemeister.analysis.raw:"
docker exec redis redis-cli XREVRANGE cluemeister.analysis.raw + - COUNT 1 2>/dev/null | head -10
echo ""

echo "=========================================="
echo "FINAL SYSTEM STATUS"
echo "=========================================="
echo ""

# Count total messages in Redis
total_streams=$(docker exec redis redis-cli KEYS "*.raw" 2>/dev/null | wc -l)
total_messages=0

for stream in $(docker exec redis redis-cli KEYS "*.raw" 2>/dev/null); do
    count=$(docker exec redis redis-cli XLEN "$stream" 2>/dev/null)
    total_messages=$((total_messages + count))
done

echo "Summary:"
echo "  - Active Agents: 8"
echo "  - Redis Streams: $total_streams"
echo "  - Total Messages: $total_messages"
echo ""

# Check if system is healthy
agents_running=$(docker ps --format "{{.Names}}" | grep -E "(weather|logistics|health|interview|path|photo|history|cluemeister)-agent" | wc -l)

if [ "$agents_running" -eq 8 ]; then
    echo "System Health: ALL AGENTS RUNNING"
else
    echo "System Health: $agents_running/8 agents running"
fi
