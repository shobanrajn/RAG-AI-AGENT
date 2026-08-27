import io
import base64
import time
import pymupdf
import face_recognition
import numpy as np
from PIL import Image
from io import BytesIO
from fastapi import HTTPException
from fastapi.security import HTTPBasicCredentials
from app.core.logging import *
from app.core.config import settings
from app.schemas.pydantic_schema import ImageExtractRequest, ImageExtractResponse



def extract_images_from_pdf(base64_pdf_str, logger):
    try:
        pdf_data = base64.b64decode(base64_pdf_str) 
        logger.info(f"pdf_data: {pdf_data}")
        pdf_doc = pymupdf.open(stream=BytesIO(pdf_data), filetype="pdf")
        logger.info(f"pdf_doc: {pdf_doc}")
        base64_images = []  
            
        # Step 5: Convert the pixmap to a PIL Image
        for page_index in range(len(pdf_doc)):
            page = pdf_doc.load_page(page_index)
            image_list = page.get_images(full=True)
            if(image_list == None or len(image_list) == 0):
                return "", ""
            else:
                for image_index, img in enumerate(image_list, start=1):
                    xref = img[0]  # Get the XREF ID
                    base_image = pdf_doc.extract_image(xref)
                    image_bytes = base_image["image"]
                    image_ext = base_image["ext"]
                    pil_image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
                    image_np = np.array(pil_image)
                    
                    # 2. Find all face locations on the page
                    # Using "hog" (CPU-friendly) or "cnn" (requires GPU for speed)
                    face_locations = face_recognition.face_locations(image_np, model="hog")

                    face_img_len = len(face_locations)
        
                    if(face_img_len > 0):
                        # Example: Split a 3x4 grid image
                        print(image_np.shape)
                        rows, cols, channels = image_np.shape
                        col = round(cols/face_img_len)
                        crop_images = image_np[:, :col]
                        split_pil_img = Image.fromarray(crop_images)

                        buffered = io.BytesIO()
            
                        # 2. Save the PIL image into the buffer instead of disk
                        split_pil_img.save(buffered, format=image_ext)
                        img_str = base64.b64encode(buffered.getvalue()).decode("utf-8")

                        with open("image_base64.txt", "w+") as file:
                            file.write(img_str)
                        return img_str, image_ext
                        #split_uniform_grid(image_np, rows=1, cols=4)
                        # Save the image to disk
    except Exception as e:
        logger.Exception(f"Exception in image extract: {e}")
        return "", ""



async def image_process_service(
    request: ImageExtractRequest,
    credentials: HTTPBasicCredentials,
) -> ImageExtractResponse:
    """
    Identify the facial image and extract and convert into base64 and return
    """
    st = time.time()

    # =========================================================
    # Logger setup — mirrors create_log_name() from the raw file
    # =========================================================
    dt, timestamp = create_log_name()
    log_file_name = f"{settings.LOGGER_PATH}image_v1_{dt}.log"
    logger = setup_logger("image_logger", log_file_name)

    try:
        logger.info(f"User input : {request.base64_pdf}")
        _result, file_format = extract_images_from_pdf(base64_pdf_str=request.base64_pdf, logger=logger)
        logger.info(f"Image output in base64 : {_result}")
        return ImageExtractResponse(
            base64_img=_result,
            file_format=file_format
        )
    except Exception as e:
        logger.exception(f"Exception in image extraction response : {e}")
        raise HTTPException(status_code=500, detail=f"Image processing failed: {e}")