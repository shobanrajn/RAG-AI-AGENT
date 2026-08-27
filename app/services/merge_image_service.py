import time
import boto3
from PIL import Image
from io import BytesIO
from fastapi import HTTPException
from fastapi.security import HTTPBasicCredentials
from urllib.parse import urlparse
from pdf2image import convert_from_bytes
from pathlib import Path
from app.core.logging import *
from app.core.config import settings
from app.schemas.pydantic_schema import ImageMergeRequest, ImageMergeResponse

# Try to import pdf2image, fallback if not available
try:
    PDF_SUPPORT_AVAILABLE = True
except ImportError:
    PDF_SUPPORT_AVAILABLE = False


async def download_file_from_s3(s3_url: str, s3_client) -> bytes:
    """
    Download file (image or PDF) from S3 URL and return bytes
    """
    try:
        # Parse S3 URL to extract bucket and key
        parsed_url = urlparse(s3_url)
        
        # Handle both virtual-hosted-style and path-style S3 URLs
        if parsed_url.netloc.endswith('.amazonaws.com'):
            # Virtual-hosted-style: bucket.s3.region.amazonaws.com/key
            if '.s3' in parsed_url.netloc:
                bucket = parsed_url.netloc.split('.s3')[0]
                key = parsed_url.path.lstrip('/')
            else:
                # Path-style: s3.region.amazonaws.com/bucket/key
                path_parts = parsed_url.path.lstrip('/').split('/', 1)
                bucket = path_parts[0]
                key = path_parts[1] if len(path_parts) > 1 else ''
        else:
            raise ValueError(f"Invalid S3 URL format: {s3_url}")
        
        # Download object from S3
        response = s3_client.get_object(Bucket=bucket, Key=key)
        file_bytes = response['Body'].read()
        
        return file_bytes
    except Exception as e:
        raise Exception(f"Failed to download file from S3: {str(e)}")


def _get_file_type(s3_url: str) -> str:
    """
    Determine file type from S3 URL extension
    Returns: 'pdf', 'image', or 'unknown'
    """
    url_path = urlparse(s3_url).path.lower()
    
    pdf_extensions = ['.pdf']
    image_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp']
    
    for ext in pdf_extensions:
        if url_path.endswith(ext):
            return 'pdf'
    
    for ext in image_extensions:
        if url_path.endswith(ext):
            return 'image'
    
    return 'unknown'


def _convert_pdf_to_image(pdf_bytes: bytes, logger, merge_all_pages: bool = False) -> Image.Image:
    """
    Convert PDF to PIL Image object.
    If merge_all_pages is False: uses first page of PDF
    If merge_all_pages is True: merges all pages into a single image
    """
    if not PDF_SUPPORT_AVAILABLE:
        raise HTTPException(
            status_code=400,
            detail="PDF support not available. Please install 'pdf2image' and 'poppler-utils'"
        )
    
    try:
        # Convert all PDF pages to images
        images = convert_from_bytes(pdf_bytes, dpi=200)
        
        if not images:
            raise ValueError("PDF contains no pages")
        
        logger.info(f"PDF contains {len(images)} page(s)")
        
        # If single page or merge_all_pages is False, return first page
        if len(images) == 1 or not merge_all_pages:
            img = images[0]
            logger.info(f"PDF converted to image with dimensions: {img.width}x{img.height}")
            return img
        
        # Merge all pages vertically
        logger.info(f"Merging {len(images)} PDF pages into single image...")
        
        # Ensure all images are in RGB mode
        rgb_images = []
        for page_img in images:
            if page_img.mode != 'RGB':
                page_img = page_img.convert('RGB')
            rgb_images.append(page_img)
        
        # Calculate total dimensions
        max_width = max(img.width for img in rgb_images)
        total_height = sum(img.height for img in rgb_images)
        
        # Create merged image
        merged_image = Image.new("RGB", (max_width, total_height))
        
        # Paste all pages vertically
        y_offset = 0
        for page_img in rgb_images:
            # Resize page to match max width if needed
            if page_img.width != max_width:
                page_img = page_img.resize((max_width, int(page_img.height * (max_width / page_img.width))), resample=Image.Resampling.LANCZOS)
            merged_image.paste(page_img, (0, y_offset))
            y_offset += page_img.height
        
        logger.info(f"PDF pages merged. Final dimensions: {merged_image.width}x{merged_image.height}")
        return merged_image
    except Exception as e:
        raise Exception(f"Failed to convert PDF to image: {str(e)}")


async def download_and_process_file_from_s3(s3_url: str, s3_client, logger, merge_all_pages: bool = False) -> Image.Image:
    """
    Download file from S3 and process it (handles both images and PDFs)
    Returns PIL Image object
    merge_all_pages: If True and file is PDF, merge all pages into single image
    """
    try:
        file_type = _get_file_type(s3_url)
        logger.info(f"Detected file type: {file_type} from URL: {s3_url}")
        
        # Download file from S3
        file_bytes = await download_file_from_s3(s3_url, s3_client)
        
        if file_type == 'pdf':
            # Convert PDF to image
            logger.info("Converting PDF to image...")
            img = _convert_pdf_to_image(file_bytes, logger, merge_all_pages)
            return img
        elif file_type == 'image':
            # Open image directly
            img = Image.open(BytesIO(file_bytes))
            logger.info(f"Image loaded with dimensions: {img.width}x{img.height}")
            return img
        else:
            # Try to auto-detect based on file content
            logger.info("File type unknown, attempting auto-detection...")
            
            # Try PDF first
            if file_bytes.startswith(b'%PDF'):
                logger.info("Auto-detected as PDF")
                img = _convert_pdf_to_image(file_bytes, logger, merge_all_pages)
                return img
            else:
                # Try as image
                logger.info("Auto-detected as image")
                img = Image.open(BytesIO(file_bytes))
                logger.info(f"Image loaded with dimensions: {img.width}x{img.height}")
                return img
    except Exception as e:
        raise Exception(f"Failed to process file from S3: {str(e)}")


async def merge_images(
    request: ImageMergeRequest,
    credentials: HTTPBasicCredentials) -> ImageMergeResponse:

    st = time.time()
    dt, timestamp = create_log_name()
    log_file_name = f"{settings.LOGGER_PATH}image_merge_v1_{dt}.log"
    logger = setup_logger("image_merge_logger", log_file_name) 
    try:
        # Create S3 client with SSL verification disabled (for staging/dev only)
        s3_client = boto3.client(
            "s3",
            region_name=settings.AWS_DEFAULT_REGION,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            verify=False
        )
        
        first_file_url = request.first_image
        second_file_url = request.second_image
        logger.info(f"User input - First file: {first_file_url}")
        logger.info(f"User input - Second file: {second_file_url}")
        
        # If only first image is provided, convert it to JPEG instead of merging
        if not second_file_url:
            logger.info("Only single image provided, converting to JPEG format...")
            return await convert_image_to_jpeg(request, credentials)
        
        # Download and process files from S3 (handles both images and PDFs)
        logger.info("Processing first file from S3...")
        img1 = await download_and_process_file_from_s3(first_file_url, s3_client, logger, merge_all_pages=False)
        
        logger.info("Processing second file from S3...")
        img2 = await download_and_process_file_from_s3(second_file_url, s3_client, logger, merge_all_pages=False)

        # Ensure images are in RGB mode (required for merging)
        if img1.mode != 'RGB':
            logger.info(f"Converting first image from {img1.mode} to RGB")
            img1 = img1.convert('RGB')
        
        if img2.mode != 'RGB':
            logger.info(f"Converting second image from {img2.mode} to RGB")
            img2 = img2.convert('RGB')

        # Resize second image to match first image height
        img2_resized = img2.resize(((int(img2.width * (img1.height/img2.height))), img1.height), resample=Image.Resampling.LANCZOS)

        total_width = max(img1.width, img2_resized.width)
        total_height = img1.height + img2_resized.height

        # Create final merged image
        merged_image = Image.new("RGB", (total_width, total_height))

        merged_image.paste(img1, (0, 0))
        merged_image.paste(img2_resized, (0, img1.height))

        logger.info(f"Images merged successfully. Final dimensions: {merged_image.width}x{merged_image.height}")

        # Save merged image to bytes
        image_bytes = BytesIO()
        merged_image.save(image_bytes, format='JPEG')
        image_bytes.seek(0)
        
        # Upload to private S3 bucket with restricted access
        s3_bucket = settings.AWS_S3_BUCKET_NAME
        s3_key = f"{settings.AWS_S3_FOLDER_NAME}/{timestamp}_output.jpg"
        
        # Upload with private ACL and encryption
        s3_client.put_object(
            Bucket=s3_bucket,
            Key=s3_key,
            Body=image_bytes.getvalue(),
            ContentType='image/jpeg',
            ACL='private',  # Restrict to authenticated users only
            ServerSideEncryption='AES256'  # Enable server-side encryption
        )
        
        logger.info(f"Merged image uploaded to S3: s3://{s3_bucket}/{s3_key}")
        
        # Generate temporary presigned URL for private bucket (valid for 1 hour)
        presigned_url = s3_client.generate_presigned_url(
            'get_object',
            Params={'Bucket': s3_bucket, 'Key': s3_key},
            ExpiresIn=3600  # 1 hour in seconds
        )
        
        logger.info(f"Temporary presigned URL generated: {presigned_url}")
        
        execution_time = time.time() - st
        logger.info(f"Image merge completed in {execution_time:.2f} seconds")
        
        return ImageMergeResponse(
            merged_image=presigned_url
        )

    except Exception as e:
        logger.error(f"Error in merge_images: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
        
async def convert_image_to_jpeg(
    request,  # Can be ImageConvertRequest or ImageMergeRequest
    credentials: HTTPBasicCredentials) -> ImageMergeResponse:
    """
    Convert a single image/PDF from any format to JPEG and upload to S3.
    - If PDF with single page: converts that page to JPEG
    - If PDF with multiple pages: merges all pages into single image and converts to JPEG
    - Supports: JPG, PNG, GIF, BMP, WebP, and PDF
    """
    st = time.time()
    dt, timestamp = create_log_name()
    log_file_name = f"{settings.LOGGER_PATH}image_convert_v1_{dt}.log"
    logger = setup_logger("image_convert_logger", log_file_name)
    
    try:
        # Create S3 client
        s3_client = boto3.client(
            "s3",
            region_name=settings.AWS_DEFAULT_REGION,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            verify=False
        )
        
        # Get image URL from request (handles both ImageConvertRequest and ImageMergeRequest)
        image_url = getattr(request, 'image', None) or getattr(request, 'first_image', None)
        
        if not image_url:
            raise ValueError("No image URL provided")
        
        logger.info(f"User input - Image URL: {image_url}")
        
        # Download and process file from S3 with merge_all_pages=True for PDFs
        logger.info("Processing image/PDF from S3...")
        img = await download_and_process_file_from_s3(image_url, s3_client, logger, merge_all_pages=True)
        
        # Log original format
        logger.info(f"Original image mode: {img.mode}, dimensions: {img.width}x{img.height}")
        
        # Convert to RGB if needed
        if img.mode != 'RGB':
            logger.info(f"Converting from {img.mode} to RGB")
            img = img.convert('RGB')
        
        logger.info(f"Final image dimensions: {img.width}x{img.height}")
        
        # Save to JPEG
        image_bytes = BytesIO()
        img.save(image_bytes, format='JPEG', quality=95)
        image_bytes.seek(0)
        
        # Upload to private S3 bucket
        s3_bucket = settings.AWS_S3_BUCKET_NAME
        s3_key = f"{settings.AWS_S3_FOLDER_NAME}/{timestamp}_converted.jpg"
        
        # Upload with private ACL and encryption
        s3_client.put_object(
            Bucket=s3_bucket,
            Key=s3_key,
            Body=image_bytes.getvalue(),
            ContentType='image/jpeg',
            ACL='private',
            ServerSideEncryption='AES256'
        )
        
        logger.info(f"Converted image uploaded to S3: s3://{s3_bucket}/{s3_key}")
        logger.info(f"Converted image file size: {len(image_bytes.getvalue())} bytes")
        
        # Generate presigned URL
        presigned_url = s3_client.generate_presigned_url(
            'get_object',
            Params={'Bucket': s3_bucket, 'Key': s3_key},
            ExpiresIn=3600
        )
        logger.info(f"Presigned URL generated: {presigned_url}")
        
        execution_time = time.time() - st
        logger.info(f"Image conversion completed in {execution_time:.2f} seconds")
        
        return ImageMergeResponse(
            merged_image=presigned_url
        )
    
    except Exception as e:
        logger.error(f"Error in convert_image_to_jpeg: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
