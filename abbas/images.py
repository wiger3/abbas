import io
import json
import base64
import asyncio
from abc import ABC, abstractmethod
from urllib.parse import urlparse
import httpx
from PIL import Image

class ImagesManager:
    def __init__(self, blip_source: str, remote_blip_timeout: int, img_max_size: int, ocr: bool, tenor_apikey: str):
        self.blip_source = blip_source
        self.remote_blip_timeout = remote_blip_timeout
        self.img_max_size = img_max_size
        self.ocr = ocr
        self.tenor_apikey = tenor_apikey
        
        if blip_source != "replicate":
            self.blip = LocalCaptioner(blip_source)
        else:
            self.blip = ReplicateCaptioner(remote_blip_timeout)
        if ocr:
            self.ocr_engine = OCR(['en', 'pl'])

    async def caption_image(self, url: str, ignore_errors: bool = True) -> str:
        """
        Describes an image using BLIP
        This routine downloads the image from the internet, scales it down to MAX_SIZE, converts it to PNG, and then sends to a BLIP captioner.
        It also detects text using EasyOCR if ImagesManager is configured to do so.
        Note: In some places (mostly the config), BLIP is referred to as "CLIP". This is a mistake, but was kept for legacy reasons.

        Args:
            url: URL for the image. It will be downloaded and processed. Supports Tenor links
            ignore_errors: return None if an exception occurs
        Returns:
            Caption describing the image
        """

        uri = urlparse(url)
        if uri.hostname == 'tenor.com':
            try:
                url = await self.parse_tenor(url)
            except RuntimeError:
                if not ignore_errors:
                    raise
                return None
        
        try:
            image = await self.download_file(url)
        except RuntimeError:
            if not ignore_errors:
                raise
            return None
        
        image = self.convert_and_scale(image)
        caption = await self.blip.get_caption(image)
        if caption is None:
            return None
        
        if self.ocr:
            text = await self.ocr_engine.get_text(image)
            if text:
                caption += f", with text saying \"{text}\""
        
        if caption.startswith('araf'): # "arafed", captioner halucination
            caption = caption.split(' ', 1)[1]
        
        return caption

    async def parse_tenor(self, url: str) -> tuple[str, str]:
        """
        Retrieves a direct image link from a Tenor link.

        Args:
            url: tenor.com/view/name-of-the-gif-1234567890
        Returns:
            Image URL from Google API
        Raises:
            RuntimeError: Couldn't retrieve GIF id from URL
            RuntimeError: Google API response doesn't contain image URL
        """
        uri = urlparse(url)
        if not uri.path.startswith('/view/'):
            if not uri.path.endswith('.gif'):
                raise RuntimeError(f"Unsupported link type: {url}")
            async with httpx.AsyncClient() as client:
                r = await client.head(url)
            if r.status_code != 301 or not 'location' in r.headers:
                raise RuntimeError(f"Couldn't find GIF id for Tenor short link: {url}")
            return await self.parse_tenor(r.headers['location'])
        gif_id = uri.path.split('-')[-1]
        if not gif_id.isnumeric():
            raise RuntimeError(f"Couldn't find GIF id in URL {url}")
        api = f"https://tenor.googleapis.com/v2/posts?key={self.tenor_apikey}&ids={gif_id}&media_filter=gifpreview"
        async with httpx.AsyncClient() as client:
            r = await client.get(api)
        response = json.loads(r.text)
        try:
            return (response['results'][0]['media_formats']['gifpreview']['url'])
        except KeyError:
            raise RuntimeError(f"API call failed!\n{r.text}")

    async def download_file(self, url: str, content_type: str | None = 'image') -> bytes:
        """
        Downloads a file from the Internet.

        Args:
            url: Link to the file
            content_type: Expected Content-Type of the file
        Returns:
            Downloaded file as bytes
        Raises:
            RuntimeError: Content-Type is different than expected
        """
        async with httpx.AsyncClient() as client:
            if content_type is not None:
                r = await client.head(url)
                if not r.headers['Content-Type'].startswith(content_type):
                    raise RuntimeError(f"Wrong Content-Type! Expected '{content_type}', got '{r.headers['Content-Type']}'")
            r = await client.get(url)
        return r.content

    def convert_and_scale(self, image: bytes, size: int = None, format: str = "png") -> bytes:
        """
        Converts an image to RGB mode, scales it down keeping aspect ratio, and converts to required format.

        Args:
            image: The image in bytes format
            size: Maximum length of the longest size of the image. Default: self.img_max_size
            format: Desired output format (eg. 'png', 'jpeg')
        """
        
        if size is None:
            size = self.img_max_size
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

class Captioner(ABC):
    @abstractmethod
    async def get_caption(self, image: bytes) -> str:
        """
        Captions the image using BLIP.

        Args:
            image: The image in bytes format
        Returns:
            A caption describing the contents of the image.
        """
        raise NotImplementedError
class LocalCaptioner(Captioner):
    def __init__(self, device: str, *, model_name: str = "Salesforce/blip-image-captioning-large"):
        from torch import float16
        from transformers import BlipProcessor, BlipForConditionalGeneration
        self.device = device
        self.dtype = float16
        self.processor = BlipProcessor.from_pretrained(model_name, clean_up_tokenization_spaces=True)
        self.model = BlipForConditionalGeneration.from_pretrained(model_name, torch_dtype=self.dtype).to(self.device)
        print("Initialized local BLIP captioner model")
    async def get_caption(self, image: bytes) -> str:
        print("starting blip", end='\r')
        def _get_caption():
            im = Image.open(io.BytesIO(image))
            inputs = self.processor(im, return_tensors="pt").to(self.device, self.dtype)
            tokens = self.model.generate(**inputs, max_new_tokens=32)
            return self.processor.decode(tokens[0], skip_special_tokens=True)
        return await asyncio.threads.to_thread(_get_caption)
class ReplicateCaptioner(Captioner):
    def __init__(self, timeout: int):
        self.timeout = timeout
    async def get_caption(self, image: bytes) -> str:
        import replicate
        print("starting blip", end='\r')
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
            async with asyncio.timeout(self.timeout):
                await prediction.async_wait()
        except TimeoutError:
            print(f"ERROR: BLIP timed out ({self.timeout} seconds)")
            prediction.cancel()
        if prediction.status != "succeeded":
            return None
        return prediction.output.split(',', 1)[0]

class OCR:
    def __init__(self, languages: list[str]):
        import easyocr
        self.reader = easyocr.Reader(languages)
        print("Initialized local OCR model")
    async def get_text(self, image: bytes, min_confidence: float = 0.6) -> str:
        """
        Extracts text from image using OCR.

        Args:
            image: The image in bytes format
            min_confidence: Minimum confidence threshold for detected text
        Returns:
            The detected text sorted left-to-right top-to-bottom or an empty string if no text was detected
        """
        def _get_text():
            result: list = self.reader.readtext(image)
            if result:
                result = [x for x in result if x[2] >= min_confidence] # only detections with confidence above 60%

                # sort the text chunks left to right top to bottom
                # the bounding box coordinates are averaged to find the center, then
                # divided by 8 to reduce sensitivity to small position variations
                result.sort(key=lambda x: [avg(*[xy[1] for xy in x[0]])//8, avg(*[xy[0] for xy in x[0]])//8])

                return " ".join(x[1].strip() for x in result)
            return ''
        return await asyncio.threads.to_thread(_get_text)

def avg(*args):
    return sum(args) / len(args)

if __name__ == "__main__":
    async def main():
        import os
        blip_source = input("Choose BLIP source (replicate/cuda/cpu): ")
        ocr = input("Enable OCR? (Y/N): ")
        ocr = ocr[0].upper() != 'N'
        images = ImagesManager(blip_source, 10, 512, ocr, os.environ['TENOR_APIKEY'])
        caption = await images.caption_image(input("File link: "))
        if caption is None:
            print(":(")
            return
        print(caption)
    asyncio.run(main())
