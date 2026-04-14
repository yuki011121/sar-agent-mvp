# Photo Analysis Agent

This agent uses YOLOv8 (Ultralytics) to perform object detection on images and publishes the results to a Redis stream. Now includes advanced person analysis with skin detection, improved color accuracy, face recognition with DeepFace, and comprehensive SAR-specific metadata!**

## What It Does
- Monitors a folder for new images (default: `input_images`)
- Runs object detection using a YOLOv8 model (default: `yolov8m.pt`)
- **For detected persons:** Analyzes hair color and clothing color using advanced computer vision
- **For detected persons:** Uses skin detection to accurately separate hair and clothing regions
- **For detected persons:** Employs k-means clustering for precise color analysis
- **Face Recognition:** Detects faces and generates face encodings for person re-identification using DeepFace
- **SAR Intelligence:** Calculates search priority and assesses accessibility
- **Emergency Response:** Determines urgency levels
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

### Person Counting
- **Total people count** - Number of persons detected in image
- **Person IDs** - Unique identifier for each person

### Face Recognition & Encoding
- **DeepFace Integration** - Uses DeepFace library for face detection and encoding
- **Face Detection** - Automatically detects faces within person bounding boxes
- **Face Encodings** - Generates unique face embeddings for person re-identification
- **Face Quality Analysis** - Assesses blur, brightness, and occlusion
- **Person Re-identification** - Face encodings enable tracking the same person across multiple images
- **Multiple Models** - Supports various DeepFace models (VGG-Face, Facenet, OpenFace, etc.)
- **Graceful Degradation** - Continues operation even if face recognition fails

## SAR-Specific Intelligence Features

### Search Priority Calculation
The agent automatically calculates search priority based on SAR-relevant factors:

- **CRITICAL** (150+ points): People + water bodies + vehicles
- **HIGH** (100-149 points): People detected
- **MEDIUM** (50-99 points): Vehicles or water bodies
- **LOW** (<50 points): No urgent items detected

**Scoring System:**
- People detected: +100 points each
- Vehicles/boats: +30 points each
- Water bodies: +40 points

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
- **IMMEDIATE**: 3+ urgency factors (people + water + night)
- **HIGH**: 2 urgency factors
- **MEDIUM**: 1 urgency factor
- **LOW**: No urgency factors

**Urgency Factors:**
- People detected
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


## Output Modes

The agent supports two output modes:

### Compact Mode (Default)
Optimized for production use with minimal noise and focused on SAR-relevant information.

### Full Mode  
Verbose output with all debugging information and detailed metadata.

## Example Output Format

### Compact Mode (Default)
```json
{
  "version": "1.0",
  "timestamp": "2025-01-24T02:59:31Z",
  "stream": "photo.analysis.raw",
  "image": {
    "id": "img_4092e67d",
    "filename": "woman1.png",
    "original_size": { "w": 612, "h": 408 },
    "model_input_size": { "w": 448, "h": 640 },
    "geo": { "lat": 35.305, "lon": -120.6625 }
  },
  "processing": {
    "agent": "photo-analysis",
    "runtime_ms": 229,
    "capabilities": { "object_detection": true, "color_analysis": true, "face_encoding": true, "sar_assessment": true }
  },
  "detections": [
    {
      "id": "det_1",
      "type": "person",
      "confidence": 0.958,
      "bbox": { "x": 162, "y": 16, "w": 264, "h": 389 },
      "attributes": {
        "appearance": { "hair_color": "white", "clothing_colors": ["yellow"] },
        "face": {
          "present": true,
          "encoding_id": "face_a3f2b1c4",
          "quality": { "blur_score": 0.85, "brightness": 0.72, "occlusion": false, "quality_score": 0.785 }
        }
      }
    }
  ],
  "aggregates": { "counts": { "person": 1 } },
  "sar_assessment": {
    "priority": { "label": "HIGH", "score": 0.80 },
    "urgency": "MEDIUM",
    "accessibility": { "terrain": "LOW_COMPLEXITY", "vehicle_access": "LIMITED" },
    "weather": { "visibility_m": 2000, "lighting": "LOW", "conditions": ["overcast"] },
    "risk_factors": [
      { "name": "low_visibility", "weight": 0.25, "contrib": 0.25 }
    ],
    "explanation": "1 person detected; low visibility."
  }
}
```

### Full Mode
The agent produces a structured JSON output with the following format:

```json
{
  "version": "1.0",
  "timestamp": "2025-01-23T19:12:04Z",
  "stream": "photo.analysis.raw",

  "image": {
    "id": "img_17392",
    "filename": "frame_00123.jpg",
    "width": 1920,
    "height": 1080,
    "source": "uav_camera_1",
    "capture_time": "2025-01-23T19:11:59Z",
    "geo": { "lat": 35.3050, "lon": -120.6625 }
  },

  "processing": {
    "agent": "photo-analysis",
    "runtime_ms": 142,
    "models": {
      "yolov8": "v8m-2024.01",
      "opencv": "4.8.0"
    },
    "capabilities": {
      "object_detection": true,
      "color_analysis": true,
      "face_encoding": true,
      "sar_assessment": true
    },
    "errors": []
  },

  "detections": [
    {
      "id": "det_1",
      "type": "person",
      "confidence": 0.95,
      "bbox": { "x": 100, "y": 200, "w": 200, "h": 300 },
      "attributes": {
        "appearance": {
          "hair_color": "brown",
          "clothing_colors": ["blue"]
        },
        "face": {
          "present": true,
          "encoding_id": "face_a3f2b1c4",
          "encoding": [0.123, -0.456, 0.789, ...],  // Full face embedding vector (4096 dims for VGG-Face)
          "quality": {
            "blur_score": 0.85,
            "brightness": 0.72,
            "occlusion": false,
            "quality_score": 0.785
          },
          "bbox": [120, 210, 180, 270]
        },
        "equipment": []
      }
    }
  ],

  "aggregates": {
    "counts": { "person": 3, "vehicle": 0, "boat": 0 },
    "class_confidence_avg": { "person": 0.92 }
  },

  "sar_assessment": {
    "priority": { "label": "CRITICAL", "score": 0.95 },
    "urgency": "IMMEDIATE",
    "accessibility": {
      "terrain": "HIGH_COMPLEXITY",
      "vehicle_access": "LIMITED",
      "water_presence": true,
      "obstacles": ["dense_vegetation"]
    },
    "weather": {
      "visibility_m": 1800,
      "lighting": "GOOD",
      "conditions": ["clear"]
    },
    "equipment_detected": [],
    "risk_factors": [
      { "name": "multiple_persons", "weight": 0.4, "contrib": 0.32 },
      { "name": "water_presence", "weight": 0.35, "contrib": 0.35 }
    ],
    "explanation": "3 person(s) detected; water presence."
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
| `OUTPUT_MODE`        | Output mode: compact or full                | compact                |
| `INCLUDE_DEBUG`      | Include debug information (true/false)      | false                  |
| `CONFIDENCE_THRESHOLD` | Minimum confidence for detections (0.0-1.0) | 0.50                   |
| `CLASS_ALLOWLIST`    | Comma-separated list of allowed classes     | person,vehicle,boat,car,truck,motorcycle |
| `ENABLE_FACE_RECOGNITION` | Enable face recognition (true/false)      | true                   |
| `FACE_MODEL`         | DeepFace model name (VGG-Face, Facenet, etc.) | VGG-Face              |

## Face Recognition Usage

### Basic Usage
Face recognition is enabled by default. The agent will automatically:
- Detect faces in person detections
- Generate face encodings for re-identification
- Analyze face quality (blur, brightness, occlusion)

### Using Face Recognition with a Database
To match faces against a database of known persons:

1. **Create a database directory** with subdirectories for each person:
   ```
   face_database/
   ├── person_1/
   │   ├── photo1.jpg
   │   └── photo2.jpg
   ├── person_2/
   │   └── photo1.jpg
   └── ...
   ```

2. **Use the FaceRecognizer class** programmatically:
   ```python
   from agents.photo_analysis.face_recognition import FaceRecognizer
   
   recognizer = FaceRecognizer(model_name="VGG-Face")
   result = recognizer.recognize_face(face_image, database_path="face_database")
   ```

3. **The result** will include:
   - `identity`: Path to the matched person's directory
   - `confidence`: Match confidence (0.0-1.0)
   - `distance`: Distance metric (lower = better match)

### Available DeepFace Models
- **VGG-Face** (default): Good balance of accuracy and speed
- **Facenet**: High accuracy, good for large databases
- **OpenFace**: Fast, good for real-time applications
- **DeepID**: Alternative high-accuracy model
- **ArcFace**: State-of-the-art accuracy

### Performance Notes
- First run will download the model (can be large, ~500MB-1GB)
- Face encoding adds ~100-300ms per person detection
- Models are cached after first download
- To disable face recognition: `export ENABLE_FACE_RECOGNITION=false`

## Configuration Examples

### Compact Mode (Production)
```bash
export OUTPUT_MODE="compact"
export CONFIDENCE_THRESHOLD="0.50"
export CLASS_ALLOWLIST="person,vehicle,boat"
poetry run python -m agents.photo_analysis.main
```

### Full Mode (Debugging)
```bash
export OUTPUT_MODE="full"
export INCLUDE_DEBUG="true"
export CONFIDENCE_THRESHOLD="0.30"
poetry run python -m agents.photo_analysis.main
```

### Custom Class Filtering
```bash
export CLASS_ALLOWLIST="person,car,truck"
export CONFIDENCE_THRESHOLD="0.70"
poetry run python -m agents.photo_analysis.main
```

## Example Console Output
```
=== Photo Analysis Output ===
{
  "version": "1.0",
  "timestamp": "2025-01-23T19:12:04Z",
  "stream": "photo.analysis.raw",
  "image": { ... },
  "processing": { ... },
  "detections": [ ... ],
  "aggregates": { ... },
  "sar_assessment": { ... }
}
============================
```

## SAR Operations Benefits

This enhanced agent provides critical intelligence for search and rescue operations:

✅ **Automatic Prioritization** - Ranks images by urgency and priority
✅ **Resource Planning** - Suggests required vehicles and terrain access
✅ **Risk Assessment** - Evaluates terrain difficulty and accessibility
✅ **Environmental Analysis** - Considers weather and lighting conditions
✅ **Emergency Intelligence** - Provides comprehensive SAR context for decision-making

The agent is now production-ready for real SAR operations and can help save lives in emergency situations! 