import io
import os
import json
import base64
import asyncio
from urllib.parse import urlparse
import httpx
from PIL import Image
from .config import config

local_blip = (config.clip_source is not None and config.clip_source != "replicate") or False
ocr = config.ocr or False

if local_blip:
    from torch import float16
    from transformers import BlipProcessor, BlipForConditionalGeneration
    blip_device = config.clip_source
    blip_model_name = "Salesforce/blip-image-captioning-large"
    blip_processor = BlipProcessor.from_pretrained(blip_model_name, clean_up_tokenization_spaces=True)
    blip_model = BlipForConditionalGeneration.from_pretrained(blip_model_name, torch_dtype=float16).to(blip_device)
    print("Initialized local BLIP captioner model")
else:
    import replicate
if ocr:
    import easyocr
    ocr_reader = easyocr.Reader(['en'])
    print("Initialized local OCR model")

MAX_SIZE = config.clip_max_size or 512
CLIP_TIMEOUT = config.clip_timeout or 10
tenor_apikey = os.getenv('TENOR_APIKEY')

async def caption_image(url: str) -> str:
    """
    Describes an image using BLIP
    This routine downloads the image from the internet, scales it down to MAX_SIZE, converts it to JPEG, and then sends to a BLIP captioner.
    Note: In some places (mostly the config), BLIP is referred to as "CLIP". This is a mistake, but was kept for legacy reasons.

    Args:
        url: URL for the image. It will be downloaded and processed. Supports Tenor links
    Returns:
        Caption describing the image
    """

    uri = urlparse(url)
    if uri.hostname == 'tenor.com':
        url = await parse_tenor(url)
    if url is None:
        return None
    
    image = await download_file(url)
    if image is None:
        return None
    
    image = convert_and_scale(image, MAX_SIZE, 'bmp' if local_blip else 'jpeg')
    caption = await get_caption(image)
    if ocr:
        text = await asyncio.threads.to_thread(get_ocr, image)
        if text:
            caption += f", with text saying \"{text}\""
    
    if caption.startswith('araf'): # "arafed", captioner halucination
        caption = caption.split(' ', 1)[1]
    
    return caption

async def parse_tenor(url: str) -> tuple[str, str]:
    """
    Retrieves a direct image link from a Tenor link.

    Args:
        url: tenor.com/view/name-of-the-gif-1234567890
    Returns:
        Image URL from Google API
    """
    gif_id = url.split('-')[-1]
    if not gif_id.isnumeric():
        return None
    api = f"https://tenor.googleapis.com/v2/posts?key={tenor_apikey}&ids={gif_id}&media_filter=gifpreview"
    async with httpx.AsyncClient() as client:
        r = await client.get(api)
    response = json.loads(r.text)
    try:
        return (response['results'][0]['media_formats']['gifpreview']['url'])
    except KeyError:
        return None

async def download_file(url: str) -> bytes:
    async with httpx.AsyncClient() as client:
        r = await client.head(url)
        if not r.headers['Content-Type'].startswith('image'):
            return None
        r = await client.get(url)
    return r.content

def convert_and_scale(image: bytes, size: int = MAX_SIZE, format: str = "jpeg") -> bytes:
    im = Image.open(io.BytesIO(image))
    if im.mode != 'RGB':
        im = im.convert("RGB")
    if any(a > size for a in im.size):
        x, y = im.size
        if x > y:
            y = int(y*size/x)
            x = size
        else:
            x = int(x*size/y)
            y = size
        im = im.resize((x, y))
    imgio = io.BytesIO()
    im.save(imgio, format=format)
    im.close()
    imgio.seek(0)
    return imgio.read()

async def get_caption(image: bytes) -> str:
    print("starting blip", end='\r')
    if local_blip:
        def run():
            im = Image.open(io.BytesIO(image))
            inputs = blip_processor(im, return_tensors="pt").to(blip_device, float16)
            tokens = blip_model.generate(**inputs, max_new_tokens=32)
            return blip_processor.decode(tokens[0], skip_special_tokens=True)
        return await asyncio.threads.to_thread(run)
    else:
        model = await replicate.models.async_get('pharmapsychotic/clip-interrogator')
        data = base64.b64encode(image).decode('utf-8')
        image = f"data:application/octet-stream;base64,{data}"
        input = {
            "mode": "fast",
            "clip_model_name": "ViT-L-14/openai",
            "image": image
        }
        prediction = await replicate.predictions.async_create(
            model.latest_version,
            input=input
        )
        try:
            async with asyncio.timeout(CLIP_TIMEOUT):
                await prediction.async_wait()
        except TimeoutError:
            print(f"ERROR: BLIP timed out ({CLIP_TIMEOUT} seconds)")
            prediction.cancel()
        if prediction.status != "succeeded":
            return None
        return prediction.output.split(',', 1)[0]

def get_ocr(image: bytes) -> str:
    result: list = ocr_reader.readtext(image)
    if result:
        result.sort(key=lambda x: [x[0][0][1], x[0][0][0]]) # sort the text chunks left to right top to bottom
        return " ".join(x[1].strip() for x in result)

if __name__ == "__main__":
    async def main():
        caption = await caption_image(input("File link: "))
        if caption is None:
            print(":(")
            return
        print(caption)
    asyncio.run(main())
