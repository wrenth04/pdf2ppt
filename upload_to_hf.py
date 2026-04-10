import os
from huggingface_hub import HfApi

api = HfApi()
repo_id = "wrenth04/pdf2ppt"
token = os.environ.get("HF_TOKEN")

if not token:
    print("Error: HF_TOKEN not found in environment")
    exit(1)

# Files to upload individually or via folder
files_to_upload = [
    "app.py",
    "requirements.txt",
    "packages.txt",
]

for file in files_to_upload:
    if os.path.exists(file):
        print(f"Uploading {file}...")
        api.upload_file(
            path_or_fileobj=file,
            path_in_repo=file,
            repo_id=repo_id,
            repo_type="space",
            token=token
        )
    else:
        print(f"Warning: {file} not found, skipping.")

# Upload the src directory
if os.path.exists("src"):
    print("Uploading src directory...")
    api.upload_folder(
        folder_path="src",
        path_in_repo="src",
        repo_id=repo_id,
        repo_type="space",
        token=token
    )
else:
    print("Error: src directory not found!")

print("Upload complete!")
