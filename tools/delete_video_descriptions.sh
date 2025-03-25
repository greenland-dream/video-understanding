#!/bin/bash

# Check if directory path is provided
if [ $# -ne 1 ]; then
    echo "Usage: $0 <directory_path>"
    exit 1
fi

directory="$1"

# Check if the directory exists
if [ ! -d "$directory" ]; then
    echo "Error: Directory '$directory' does not exist"
    exit 1
fi

# Find and delete all video_descriptions.txt files
echo "Searching for video_descriptions.txt files in '$directory'..."
found_files=$(find "$directory" -type f -name "video_descriptions.txt")

if [ -z "$found_files" ]; then
    echo "No video_descriptions.txt files found."
    exit 0
fi

# Count found files
file_count=$(echo "$found_files" | wc -l)
echo "Found $file_count video_descriptions.txt files to delete."

# Show files and confirm deletion
echo "Files to be deleted:"
echo "$found_files"

read -p "Do you want to proceed with deletion? (y/n): " confirm
if [[ $confirm != [yY] ]]; then
    echo "Operation cancelled."
    exit 0
fi

# Delete the files
find "$directory" -type f -name "video_descriptions.txt" -delete
echo "All video_descriptions.txt files have been deleted." 