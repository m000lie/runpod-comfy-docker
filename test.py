import os
import cv2

# The caption to write into each .txt file
caption = "my cat named taby"

# Directory where the image files are located (update this to your directory path)
directory = "/Users/rw/taby"  # Replace with the actual path to your images

# Supported image file extensions
image_extensions = (".jpg", ".jpeg", ".png")

# Loop through all files in the directory
for filename in os.listdir(directory):
    # Check if the file is an image based on its extension
    if filename.lower().endswith(image_extensions):
        # Get the base name of the file (without the extension)
        base_name = os.path.splitext(filename)[0]
        
        # Create the corresponding .txt file name
        txt_filename = f"{base_name}.txt"
        
        # Define the full path for the .txt file
        txt_filepath = os.path.join(directory, txt_filename)
        
        # Write the caption to the .txt file
        with open(txt_filepath, "w") as txt_file:
            txt_file.write(caption)
        
        print(f"Created {txt_filename} with the caption.")

print("Done creating .txt files for all images.")