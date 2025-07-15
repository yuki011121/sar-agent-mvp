# Photo Analysis Agent

This agent uses YOLOv8 (Ultralytics) to perform object detection on images and publishes the results to a Redis stream.

## What It Does
- Monitors a folder for new images (default: `input_images`)
- Runs object detection using a YOLOv8 model (default: `yolov8s.pt`)
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

## YOLOv8 Model Info
- By default, uses `yolov8s.pt` (YOLOv8 Small, free and open source)
- The model will be downloaded automatically if not present
- You can use other YOLOv8 models (e.g., `yolov8n.pt`, `yolov8m.pt`, `yolov8l.pt`, `yolov8x.pt`) by setting the `YOLO_MODEL_PATH` environment variable
- For custom models, set `YOLO_MODEL_PATH` to your `.pt` file

## Redis Output
- Results are published to a Redis stream (default: `photo.analysis.raw`)
- To view results, use:
   ```bash
   docker exec -it sar-agent-mvp-redis-1 redis-cli
   XLEN photo.analysis.raw
   XREVRANGE photo.analysis.raw + - COUNT 1
   ```
- Each entry contains a JSON object with metadata and detections

## Environment Variables
| Variable             | Description                                 | Default                |
|----------------------|---------------------------------------------|------------------------|
| `REDIS_URL`          | Redis connection URL                        | redis://localhost:6379 |
| `IMAGE_INPUT_DIR`    | Directory to watch for images               | input_images           |
| `REDIS_OUTPUT_STREAM`| Redis stream name for output                | photo.analysis.raw     |
| `YOLO_MODEL_PATH`    | Path or name of YOLOv8 model                | yolov8s.pt             |
| `UPDATE_INTERVAL_SECONDS` | How often to check for new images (sec) | 10                     |

## Example Output
```
=== Photo Analysis Output ===
{
  "metadata": { ... },
  "detections": [ ... ]
}
============================
``` 