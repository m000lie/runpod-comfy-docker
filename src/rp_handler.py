import runpod
from runpod.serverless.utils import rp_upload
import json
import urllib.request
import urllib.parse
import time
import os
import requests
import base64
from io import BytesIO
from io import StringIO
from PIL import Image
import sys

# Time to wait between API check attempts in milliseconds
COMFY_API_AVAILABLE_INTERVAL_MS = 50
# Maximum number of API check attempts
COMFY_API_AVAILABLE_MAX_RETRIES = 500
# Time to wait between poll attempts in milliseconds
COMFY_POLLING_INTERVAL_MS = int(os.environ.get("COMFY_POLLING_INTERVAL_MS", 5000))
# Maximum number of poll attempts
COMFY_POLLING_MAX_RETRIES = int(os.environ.get("COMFY_POLLING_MAX_RETRIES", 500))
# Host where ComfyUI is running
COMFY_HOST = "127.0.0.1:8188"
# Enforce a clean state after each job is done
# see https://docs.runpod.io/docs/handler-additional-controls#refresh-worker
REFRESH_WORKER = os.environ.get("REFRESH_WORKER", "false").lower() == "true"
COMFY_LORA_PATH = os.environ.get("COMFY_LORA_PATH", "/comfyui/trained_loras")

def validate_input(job_input):
    """
    Validates the input for the handler function.

    Args:
        job_input (dict): The input data to validate.

    Returns:
        tuple: A tuple containing the validated data and an error message, if any.
               The structure is (validated_data, error_message).
    """
    # Validate if job_input is provided
    if job_input is None:
        return None, "Please provide input"

    # Check if input is a string and try to parse it as JSON
    if isinstance(job_input, str):
        try:
            job_input = json.loads(job_input)
        except json.JSONDecodeError:
            return None, "Invalid JSON format in input"

    # Validate 'workflow' in input
    workflow = job_input.get("workflow")
    if workflow is None:
        return None, "Missing 'workflow' parameter"

    # Validate 'images' in input, if provided
    images = job_input.get("images")
    if images is not None:
        if not isinstance(images, list) or not all(
            "name" in image and "image" in image for image in images
        ):
            return (
                None,
                "'images' must be a list of objects with 'name' and 'image' keys",
            )

    # Return validated data and no error
    return {"workflow": workflow, "images": images}, None


def check_server(url, retries=500, delay=50):
    """
    Check if a server is reachable via HTTP GET request

    Args:
    - url (str): The URL to check
    - retries (int, optional): The number of times to attempt connecting to the server. Default is 50
    - delay (int, optional): The time in milliseconds to wait between retries. Default is 500

    Returns:
    bool: True if the server is reachable within the given number of retries, otherwise False
    """

    for i in range(retries):
        try:
            response = requests.get(url)

            # If the response status code is 200, the server is up and running
            if response.status_code == 200:
                print(f"runpod-worker-comfy - API is reachable")
                return True
        except requests.RequestException as e:
            # If an exception occurs, the server may not be ready
            pass

        # Wait for the specified delay before retrying
        time.sleep(delay / 1000)

    print(
        f"runpod-worker-comfy - Failed to connect to server at {url} after {retries} attempts."
    )
    return False


def upload_images(images):
    """
    Upload a list of base64 encoded images to the ComfyUI server using the /upload/image endpoint.

    Args:
        images (list): A list of dictionaries, each containing the 'name' of the image and the 'image' as a base64 encoded string.
        server_address (str): The address of the ComfyUI server.

    Returns:
        list: A list of responses from the server for each image upload.
    """
    if not images:
        return {"status": "success", "message": "No images to upload", "details": []}

    responses = []
    upload_errors = []

    print(f"runpod-worker-comfy - image(s) upload")

    for image in images:
        name = image["name"]
        image_data = image["image"]
        subfolder_name = image.get(
            "subfolder", False
        )  # Default to empty string if not provided
        # check if it's a text file
        text = image.get("text", False)

        if text:
            files = {
                "image": (name, StringIO(image_data), "text/plain"),
                "overwrite": (None, "true")
            }
        else: 
            blob = base64.b64decode(image_data)
            files = {
                "image": (name, BytesIO(blob), "image/png"),
                "overwrite": (None, "true"),
            }
        if subfolder_name:  # Only add subfolder if it's not empty
            files["subfolder"] = (None, subfolder_name)

        # POST request to upload the image
        response = requests.post(f"http://{COMFY_HOST}/upload/image", files=files)
        if response.status_code != 200:
            upload_errors.append(f"Error uploading {name}: {response.text}")
        else:
            responses.append(f"Successfully uploaded {name}")

    if upload_errors:
        print(f"runpod-worker-comfy - image(s) upload with errors")
        return {
            "status": "error",
            "message": "Some images failed to upload",
            "details": upload_errors,
        }

    print(f"runpod-worker-comfy - image(s) upload complete")
    return {
        "status": "success",
        "message": "All images uploaded successfully",
        "details": responses,
    }


def queue_workflow(workflow):
    """
    Queue a workflow to be processed by ComfyUI

    Args:
        workflow (dict): A dictionary containing the workflow to be processed

    Returns:
        dict: The JSON response from ComfyUI after processing the workflow
    """

    # The top level element "prompt" is required by ComfyUI
    data = json.dumps({"prompt": workflow}).encode("utf-8")

    req = urllib.request.Request(f"http://{COMFY_HOST}/prompt", data=data)
    return json.loads(urllib.request.urlopen(req).read())


def get_history(prompt_id):
    """
    Retrieve the history of a given prompt using its ID

    Args:
        prompt_id (str): The ID of the prompt whose history is to be retrieved

    Returns:
        dict: The history of the prompt, containing all the processing steps and results
    """
    with urllib.request.urlopen(f"http://{COMFY_HOST}/history/{prompt_id}") as response:
        return json.loads(response.read())


def base64_encode(img_path):
    """
    Returns base64 encoded image.

    Args:
        img_path (str): The path to the image

    Returns:
        str: The base64 encoded image
    """
    with open(img_path, "rb") as image_file:
        encoded_string = base64.b64encode(image_file.read()).decode("utf-8")
        return f"{encoded_string}"


def convert_webp_to_gif(input_path, output_path=None, fps=16):
    """
    Convert a WebP image to GIF format while preserving quality.
    Handles both single and multi-frame WebP files.
    
    Args:
        input_path (str): Path to the input WebP file
        output_path (str, optional): Path for the output GIF file. If not provided,
                                   will use the same name as input with .gif extension
        fps (int): Frames per second for the output GIF (default: 16)
    """
    try:
        # Open the WebP image
        with Image.open(input_path) as img:
            # If output path is not specified, create one with .gif extension
            if output_path is None:
                output_path = os.path.splitext(input_path)[0] + '.gif'
            
            # Calculate frame duration in milliseconds (1000ms / fps)
            duration = int(1000 / fps)
            
            # Prepare frames list
            frames = []
            
            # Convert each frame
            for frame in range(img.n_frames):
                img.seek(frame)
                
                # Convert to RGB if the image is in RGBA mode
                if img.mode in ('RGBA', 'LA'):
                    background = Image.new('RGB', img.size, (255, 255, 255))
                    background.paste(img, mask=img.split()[-1])
                    frame_img = background
                else:
                    frame_img = img.convert('RGB')
                
                frames.append(frame_img)
            
            # Save as animated GIF
            frames[0].save(
                output_path,
                save_all=True,
                append_images=frames[1:],
                duration=duration,
                loop=0,  # 0 means loop forever
                optimize=False
            )
            
            print(f"Successfully converted {input_path} to {output_path}")
            print(f"Number of frames: {len(frames)}")
            print(f"FPS: {fps} (frame duration: {duration}ms)")
            return output_path
            
    except Exception as e:
        print(f"Error converting image: {str(e)}")
        raise e


def convert_webp_to_mp4(input_path, output_path=None, fps=16):
    """
    Convert a WebP image to MP4 format while preserving quality.
    Handles both single and multi-frame WebP files.
    
    Args:
        input_path (str): Path to the input WebP file
        output_path (str, optional): Path for the output MP4 file. If not provided,
                                   will use the same name as input with .mp4 extension
        fps (int): Frames per second for the output MP4 (default: 16)
    """
    try:
        # Open the WebP image
        with Image.open(input_path) as img:
            # If output path is not specified, create one with .mp4 extension
            if output_path is None:
                output_path = os.path.splitext(input_path)[0] + '.mp4'
            
            # Create a temporary directory for frames
            temp_dir = os.path.join(os.path.dirname(output_path), 'temp_frames')
            os.makedirs(temp_dir, exist_ok=True)
            
            # Save each frame as PNG
            frames = []
            try:
                for frame in range(img.n_frames):
                    img.seek(frame)
                    frame_path = os.path.join(temp_dir, f'frame_{frame:04d}.png')
                    
                    # Convert to RGB if necessary
                    if img.mode in ('RGBA', 'LA'):
                        background = Image.new('RGB', img.size, (255, 255, 255))
                        background.paste(img, mask=img.split()[-1])
                        frame_img = background
                    else:
                        frame_img = img.convert('RGB')
                    
                    frame_img.save(frame_path)
                    frames.append(frame_path)
                
                # Use ffmpeg to convert frames to MP4
                frame_pattern = os.path.join(temp_dir, 'frame_%04d.png')
                os.system(f'ffmpeg -y -framerate {fps} -i {frame_pattern} -c:v libx264 -preset slow -crf 17 -pix_fmt yuv420p {output_path}')
                
                print(f"Successfully converted {input_path} to {output_path}")
                print(f"Number of frames: {len(frames)}")
                print(f"FPS: {fps}")
                
                return output_path
                
            finally:
                # Clean up temporary frames
                for frame_path in frames:
                    try:
                        os.remove(frame_path)
                    except:
                        pass
                try:
                    os.rmdir(temp_dir)
                except:
                    pass
            
    except Exception as e:
        print(f"Error converting image: {str(e)}")
        raise e


def process_output_images(outputs, job_id, bucket_name):
    """
    This function takes the "outputs" from image generation and converts the WebP image
    to an MP4 format, then returns it as a base64 encoded string.

    Args:
        outputs (dict): A dictionary containing the outputs from image generation,
                        typically includes node IDs and their respective output data.
        job_id (str): The unique identifier for the job.

    Returns:
        dict: A dictionary with the status ('success' or 'error') and the message,
              which is a base64 encoded string of the MP4 video. In case of error,
              the message details the issue.
    """

    # The path where ComfyUI stores the generated images
    COMFY_OUTPUT_PATH = os.environ.get("COMFY_OUTPUT_PATH", "/comfyui/output")

    output_images = {}

    for node_id, node_output in outputs.items():
        if "images" in node_output:
            for image in node_output["images"]:
                output_images = os.path.join(image["subfolder"], image["filename"])

    print(f"runpod-worker-comfy - image generation is done")

    # expected image output folder
    local_image_path = f"{COMFY_OUTPUT_PATH}/{output_images}"

    print(f"runpod-worker-comfy - {local_image_path}")

    # The image is in the output folder
    if os.path.exists(local_image_path):
        try:
            # Convert WebP to MP4
            mp4_path = convert_webp_to_mp4(local_image_path)
            print(f"runpod-worker-comfy - converted WebP to MP4: {mp4_path}")
            
            # Convert MP4 to base64
            video = base64_encode(mp4_path)
            print("runpod-worker-comfy - the MP4 was generated and converted to base64")
            
            # Clean up both the original WebP and the generated MP4
            try:
                os.remove(local_image_path)
                os.remove(mp4_path)
                print(f"runpod-worker-comfy - deleted local files: {local_image_path} and {mp4_path}")
            except Exception as e:
                print(f"runpod-worker-comfy - warning: failed to delete local files: {str(e)}")
                
            return {
                "status": "success",
                "message": video,
            }
        except Exception as e:
            print(f"runpod-worker-comfy - error converting WebP to MP4: {str(e)}")
            return {
                "status": "error",
                "message": f"Failed to convert WebP to MP4: {str(e)}",
            }
    else:
        print("runpod-worker-comfy - the image does not exist in the output folder")
        return {
            "status": "error",
            "message": f"the image does not exist in the specified output folder: {local_image_path}",
        }

# bucket name is the user id
def process_lora(outputs, job_id, lora_name, bucket_name):

    for node_id, node_output in outputs.items():
        if node_id == "105":
            break

    # upload the lora to the bucket
    lora_path = f"{COMFY_LORA_PATH}/{lora_name}.safetensors"
    lora_file_name = lora_name + ".safetensors"
    rp_upload.upload_file_to_bucket(lora_file_name, lora_path, bucket_name=bucket_name)
    return {
        "status": "success",
        "message": lora_path,
    }



def handler(job):
    """
    The main function that handles a job of generating an image.

    This function validates the input, sends a prompt to ComfyUI for processing,
    polls ComfyUI for result, and retrieves generated images.

    Args:
        job (dict): A dictionary containing job details and input parameters.

    Returns:
        dict: A dictionary containing either an error message or a success status with generated images.
    """
    job_input = job["input"]
    SB_USER_ID = job_input.get("sb_user_id", False)
    if not SB_USER_ID:
        return {"error": "NO USER ID FOUND"}
    lora_name = job_input.get("lora", False)

    # Make sure that the input is valid
    validated_data, error_message = validate_input(job_input)
    if error_message:
        return {"error": error_message}

    # Extract validated data
    workflow = validated_data["workflow"]
    images = validated_data.get("images")

    # Make sure that the ComfyUI API is available
    check_server(
        f"http://{COMFY_HOST}",
        COMFY_API_AVAILABLE_MAX_RETRIES,
        COMFY_API_AVAILABLE_INTERVAL_MS,
    )

    # Upload images if they exist
    upload_result = upload_images(images)

    if upload_result["status"] == "error":
        return upload_result

    # Queue the workflow
    try:
        queued_workflow = queue_workflow(workflow)
        prompt_id = queued_workflow["prompt_id"]
        print(f"runpod-worker-comfy - queued workflow with ID {prompt_id}")
    except Exception as e:
        return {"error": f"Error queuing workflow: {str(e)}"}

    # check to see if subfolder is provided which signals LORA or not
    # check to see if the "lora" key is in the job object, if yes then set the lora enable to true
    # if no subfolder is provided, then set the lora enable to false

    
    if lora_name:
        lora_enable = True
    else:
        lora_enable = False

    # Poll for completion
    print(f"runpod-worker-comfy - wait until image generation is complete")
    retries = 0
    try:
        while retries < COMFY_POLLING_MAX_RETRIES:
            history = get_history(prompt_id)

            # Exit the loop if we have found the history
            if prompt_id in history and history[prompt_id].get("outputs"):
                print(history[prompt_id])
                break
            else:
                # Wait before trying again
                time.sleep(COMFY_POLLING_INTERVAL_MS / 1000)
                retries += 1
        else:
            return {"error": "Max retries reached while waiting for image generation"}
    except Exception as e:
        return {"error": f"Error waiting for image generation: {str(e)}"}
    
    # check to see if we trained a lora or generated an image
    if lora_enable:
        lora_name = lora_name + "_rank16_bf16"
        process_lora(history[prompt_id].get("outputs"), job["id"], lora_name, bucket_name=SB_USER_ID)
    else:
        # Get the generated image and return it as URL in an AWS bucket or as base64
        images_result = process_output_images(history[prompt_id].get("outputs"), job["id"], bucket_name=SB_USER_ID)

    result = {**images_result, "refresh_worker": REFRESH_WORKER}

    return result


# Start the handler only if this script is run directly
if __name__ == "__main__":
    runpod.serverless.start({"handler": handler})
