#!/bin/bash

echo "Cleaning Redis Streams..."

# Clean old messages from each stream, keeping only the most recent messages
docker exec redis redis-cli XTRIM health.assessment.raw MAXLEN 100
docker exec redis redis-cli XTRIM logistics.requests.raw MAXLEN 100
docker exec redis redis-cli XTRIM cluemeister.analysis.raw MAXLEN 100
docker exec redis redis-cli XTRIM photo.analysis.raw MAXLEN 50
docker exec redis redis-cli XTRIM interview.analysis.raw MAXLEN 10
docker exec redis redis-cli XTRIM history.out.raw MAXLEN 10
docker exec redis redis-cli XTRIM path.analysis.raw MAXLEN 5
docker exec redis redis-cli XTRIM weather.forecast.raw MAXLEN 20

echo ""
echo "Redis streams cleaned!"
echo "Remaining message counts:"
docker exec redis redis-cli --scan --pattern "*.raw" 2>/dev/null | while read stream; do count=$(docker exec redis redis-cli XLEN "$stream" 2>/dev/null); echo "  $stream: $count"; done

