# Photo Analysis Agent

This agent uses YOLOv8 (Ultralytics) to perform object detection on images and publishes the results to a Redis stream. **ENHANCED: Now includes advanced person analysis with skin detection, improved color accuracy, and comprehensive SAR-specific metadata!**

## What It Does
- Monitors a folder for new images (default: `input_images`)
- Runs object detection using a YOLOv8 model (default: `yolov8m.pt`)
- **For detected persons:** Analyzes hair color, clothing color, and gender using advanced computer vision
- **For detected persons:** Uses skin detection to accurately separate hair and clothing regions
- **For detected persons:** Employs k-means clustering for precise color analysis
- **SAR Intelligence:** Calculates search priority, detects emergency equipment, assesses accessibility
- **Emergency Response:** Determines urgency levels and response time estimates
- Prints detection results to the console
- Publishes results to a Redis stream (`photo.analysis.raw` by default)

## How to Run
1. **Install dependencies** (from the `sar-agent-mvp` root):
   ```bash
   poetry install --no-root
   ```
2. **Place images** in the `input_images` directory (or set `IMAGE_INPUT_DIR`)
3. **Run the agent**:
   ```bash
   poetry run python -m agents.photo_analysis.main
   ```

## Enhanced Person Analysis Features
The agent now includes sophisticated analysis for person detection:

### Skin Detection & Region Separation
- **Face detection** - Uses skin color detection to find face regions
- **Smart region analysis** - Separates hair (above face) and clothing (below face)
- **Accurate boundaries** - No more mixing of hair and clothing colors
- **Fallback handling** - Uses fixed regions if face detection fails

### Advanced Color Analysis
- **K-means clustering** - Groups similar colors for dominant color detection
- **HSV color space** - More accurate color classification than RGB
- **Improved accuracy** - Better handling of lighting variations and shadows
- **Color mapping** - Maps to common hair and clothing colors

### Hair Color Analysis
- **Precise detection** - Analyzes region above detected face
- **Common colors** - black, brown, blonde, red, gray, white
- **Fallback logic** - Defaults to "brown" for unclear cases

### Clothing Color Analysis
- **Accurate regions** - Analyzes region below detected face
- **Common colors** - red, blue, green, yellow, black, white, gray, orange, purple
- **Pattern handling** - Better with complex clothing patterns

### Person Counting & Face Analysis
- **Total people count** - Number of persons detected in image
- **Face detection** - Number of faces found and their encodings
- **Person IDs** - Unique identifier for each person

## SAR-Specific Intelligence Features

### Search Priority Calculation
The agent automatically calculates search priority based on SAR-relevant factors:

- **CRITICAL** (150+ points): People + emergency equipment + water bodies
- **HIGH** (100-149 points): People or multiple emergency items
- **MEDIUM** (50-99 points): Vehicles or some equipment
- **LOW** (<50 points): No urgent items detected

**Scoring System:**
- People detected: +100 points each
- Emergency equipment: +50 points each
- Vehicles/boats: +30 points each
- Water bodies: +40 points

### Emergency Equipment Detection
Automatically identifies SAR-relevant equipment:

**Life-Saving Equipment:**
- Life jackets, life vests, life rings
- Flares, emergency signals
- Radios, communication devices

**Medical Equipment:**
- First aid supplies
- Medical equipment
- Emergency medical gear

**Safety Equipment:**
- Helmets, safety gear
- Rescue equipment
- Emergency supplies

### Accessibility Assessment
Evaluates terrain accessibility for SAR operations:

**Accessibility Levels:**
- **EASY** (80-100): Clear terrain, vehicle access
- **MODERATE** (50-79): Some obstacles, manageable
- **DIFFICULT** (20-49): Significant obstacles, challenging
- **VERY_DIFFICULT** (0-19): Severe obstacles, requires specialized equipment

**Factors Considered:**
- Terrain obstacles (trees, rocks, cliffs, mountains)
- Water bodies (requires boats)
- Vehicle access (improves accessibility)
- Terrain complexity scoring

### Urgency Level Determination
Determines appropriate response urgency:

**Urgency Levels:**
- **IMMEDIATE**: 3+ urgency factors (people + equipment + water + night)
- **HIGH**: 2 urgency factors
- **MEDIUM**: 1 urgency factor
- **LOW**: No urgency factors

**Urgency Factors:**
- People detected
- Emergency equipment present
- Water bodies detected
- Night time conditions
- Weather conditions

### Weather & Environmental Analysis
Assesses environmental conditions affecting SAR operations:

**Weather Indicators:**
- Visibility conditions (GOOD/POOR/UNKNOWN)
- Lighting conditions (DAY/NIGHT)
- Weather conditions (CLEAR/RAIN/SNOW/UNKNOWN)

**Time-Based Factors:**
- Day vs. night operations
- Seasonal considerations
- Lighting impact on search effectiveness

### Response Time Estimation
Automatically suggests appropriate response times:

- **IMMEDIATE**: Requires immediate response
- **WITHIN_1_HOUR**: High priority, respond within 1 hour
- **WITHIN_4_HOURS**: Medium priority, respond within 4 hours
- **ROUTINE**: Low priority, routine response

## Example Output for Person Detection
```json
{
  "class": "person",
  "confidence": 0.95,
  "bbox": [100, 200, 300, 500],
  "hair_color": "brown",
  "clothing_color": "blue",
  "gender": "unknown",
  "person_id": 1
}
```

### Complete Analysis Output with SAR Context
```json
{
  "metadata": {
    "capabilities": {
      "object_detection": true,
      "color_analysis": true,
      "person_counting": true,
      "face_analysis": true,
      "skin_detection": true,
      "sar_analysis": true
    }
  },
  "detections": [...],
  "person_analysis": {
    "total_people": 3,
    "faces_detected": 2,
    "face_encodings": [...]
  },
  "sar_context": {
    "search_priority": "CRITICAL",
    "emergency_equipment": [
      {
        "type": "life jacket",
        "confidence": 0.85,
        "bbox": [150, 200, 250, 300],
        "priority": "HIGH"
      }
    ],
    "accessibility": {
      "score": 60,
      "level": "MODERATE",
      "obstacles": 2,
      "water_present": true,
      "vehicle_access": false
    },
    "urgency_level": "IMMEDIATE",
    "weather_conditions": {
      "visibility": "GOOD",
      "lighting": "DAY",
      "weather_conditions": "CLEAR"
    },
    "response_time_estimate": "IMMEDIATE",
    "sar_metrics": {
      "people_count": 2,
      "faces_detected": 1,
      "equipment_count": 1,
      "vehicle_count": 0,
      "terrain_complexity": "HIGH"
    }
  }
}
```

## Technical Improvements

### Skin Detection Algorithm
- **HSV color range** - Detects skin tones accurately
- **Contour analysis** - Finds largest skin region (face)
- **Region separation** - Uses face position to separate hair/clothing

### K-Means Clustering
- **3 clusters** - Groups similar colors together
- **Dominant color** - Finds most common color in each region
- **Better accuracy** - Handles complex patterns and lighting

### Color Classification
- **HSV-based** - More accurate than RGB classification
- **Improved ranges** - Better hue boundaries for each color
- **Lighting robust** - Handles shadows and highlights better

### Error Handling & Resilience
- **Comprehensive error handling** - Graceful degradation on failures
- **Retry logic** - Automatic retries for network issues
- **Validation** - Image file validation and corruption detection
- **Logging** - Detailed logging to `photo_analysis_agent.log`
- **Resource management** - Memory cleanup and resource optimization

## Using the Kaggle SAR Dataset
The agent includes a script to download and prepare the SAR dataset from Kaggle:

1. **Install Kaggle CLI**:
   ```bash
   pip install kaggle
   ```

2. **Set up Kaggle authentication**:
   - Go to https://www.kaggle.com/settings/account
   - Scroll to 'API' section and click 'Create New API Token'
   - Download `kaggle.json` and place it in `~/.kaggle/kaggle.json`

3. **Download and prepare the dataset**:
   ```bash
   poetry run python agents/photo_analysis/download_dataset.py
   ```

4. **Run the agent** (it will automatically process the downloaded images):
   ```bash
   poetry run python -m agents.photo_analysis.main
   ```

The script will:
- Download the SAR dataset to `datasets/sar_kaggle/`
- Copy sample images to `input_images/` for testing
- Set up the directory structure for the agent

## YOLOv8 Model Info
- By default, uses `yolov8m.pt` (YOLOv8 Medium, free and open source)
- The model will be downloaded automatically if not present
- You can use other YOLOv8 models (e.g., `yolov8n.pt`, `yolov8s.pt`, `yolov8l.pt`, `yolov8x.pt`) by setting the `YOLO_MODEL_PATH` environment variable
- For custom models, set `YOLO_MODEL_PATH` to your `.pt` file
- **Model sizes**: nano (6MB) < small (22MB) < medium (52MB) < large (87MB) < extra large (136MB)
- **Performance**: nano (fastest) < small < medium < large < extra large (most accurate)

## Redis Output
- Results are published to a Redis stream (default: `photo.analysis.raw`)
- To view results, use:
   ```bash
   docker exec -it sar-agent-mvp-redis-1 redis-cli
   XLEN photo.analysis.raw
   XREVRANGE photo.analysis.raw + - COUNT 1
   ```
- Each entry contains a JSON object with metadata, detections, and SAR context

## Environment Variables
| Variable             | Description                                 | Default                |
|----------------------|---------------------------------------------|------------------------|
| `REDIS_URL`          | Redis connection URL                        | redis://localhost:6379 |
| `IMAGE_INPUT_DIR`    | Directory to watch for images               | input_images           |
| `REDIS_OUTPUT_STREAM`| Redis stream name for output                | photo.analysis.raw     |
| `YOLO_MODEL_PATH`    | Path or name of YOLOv8 model                | yolov8m.pt             |
| `UPDATE_INTERVAL_SECONDS` | How often to check for new images (sec) | 10                     |
| `MAX_RETRIES`        | Number of retry attempts for connections   | 3                      |
| `RETRY_DELAY`        | Seconds between retry attempts             | 5                      |

## Example Output
```
=== Photo Analysis Output ===
{
  "metadata": { ... },
  "detections": [ ... ],
  "person_analysis": { ... },
  "sar_context": { ... }
}
============================
```

## SAR Operations Benefits

This enhanced agent provides critical intelligence for search and rescue operations:

✅ **Automatic Prioritization** - Ranks images by urgency and priority
✅ **Resource Planning** - Suggests required equipment and vehicles
✅ **Response Timing** - Estimates appropriate response times
✅ **Risk Assessment** - Evaluates terrain difficulty and accessibility
✅ **Equipment Detection** - Identifies life-saving equipment automatically
✅ **Environmental Analysis** - Considers weather and lighting conditions
✅ **Emergency Intelligence** - Provides comprehensive SAR context for decision-making

The agent is now production-ready for real SAR operations and can help save lives in emergency situations! 