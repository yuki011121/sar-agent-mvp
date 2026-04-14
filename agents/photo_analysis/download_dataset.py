#!/usr/bin/env python3
"""
Script to download and prepare the Kaggle SAR dataset for the photo analysis agent.
Dataset: https://www.kaggle.com/datasets/nikolasgegenava/sard-search-and-rescue
"""

import os
import zipfile
import requests
import logging
from pathlib import Path

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def download_kaggle_dataset():
    """Download the SAR dataset from Kaggle."""
    dataset_url = "https://www.kaggle.com/api/v1/datasets/download/nikolasgegenava/sard-search-and-rescue"
    output_dir = Path("datasets/sar_kaggle")
    zip_path = output_dir / "sar_dataset.zip"
    
    # Create output directory
    output_dir.mkdir(parents=True, exist_ok=True)
    
    print("⚠️  IMPORTANT: You need to authenticate with Kaggle first!")
    print("1. Go to https://www.kaggle.com/settings/account")
    print("2. Scroll down to 'API' section and click 'Create New API Token'")
    print("3. Download the kaggle.json file")
    print("4. Place kaggle.json in your home directory (~/.kaggle/kaggle.json)")
    print("5. Run: pip install kaggle")
    print("6. Then run this script again")
    
    # Check if kaggle is installed and authenticated
    try:
        import kaggle
        print("✅ Kaggle API is available")
    except ImportError:
        print("❌ Kaggle package not found. Install with: pip install kaggle")
        return False
    
    try:
        # Download dataset using kaggle API
        import kaggle
        kaggle.api.authenticate()
        kaggle.api.dataset_download_files(
            'nikolasgegenava/sard-search-and-rescue',
            path=str(output_dir),
            unzip=True
        )
        print(f"✅ Dataset downloaded to {output_dir}")
        return True
    except Exception as e:
        print(f"❌ Error downloading dataset: {e}")
        return False

def prepare_dataset_for_agent():
    """Prepare the downloaded dataset for use with the photo analysis agent."""
    dataset_dir = Path("datasets/sar_kaggle")
    
    if not dataset_dir.exists():
        print("❌ Dataset directory not found. Run download_kaggle_dataset() first.")
        return False
    
    # Create input_images directory if it doesn't exist
    input_images_dir = Path("agents/photo_analysis/input_images")
    input_images_dir.mkdir(exist_ok=True)
    
    # Find all image files in the dataset
    image_extensions = ['.jpg', '.jpeg', '.png', '.bmp']
    image_files = []
    
    for ext in image_extensions:
        image_files.extend(dataset_dir.rglob(f"*{ext}"))
        image_files.extend(dataset_dir.rglob(f"*{ext.upper()}"))
    
    print(f"Found {len(image_files)} image files in dataset")
    
    # Copy a subset of images to input_images for testing
    # You can modify this to copy all images or a specific subset
    test_images = image_files[:10]  # Copy first 10 images for testing
    
    for img_path in test_images:
        dest_path = input_images_dir / img_path.name
        if not dest_path.exists():
            import shutil
            shutil.copy2(img_path, dest_path)
            print(f"Copied {img_path.name} to input_images")
    
    print(f"✅ Copied {len(test_images)} images to input_images directory")
    return True

def main():
    """Main function to download and prepare the dataset."""
    print("=== SAR Dataset Download and Setup ===")
    
    # Step 1: Download dataset
    if download_kaggle_dataset():
        # Step 2: Prepare for agent
        prepare_dataset_for_agent()
        print("\n🎉 Dataset setup complete!")
        print("You can now run your photo analysis agent:")
        print("poetry run python -m agents.photo_analysis.main")
    else:
        print("\n❌ Dataset setup failed. Please check the instructions above.")

if __name__ == "__main__":
    main() 