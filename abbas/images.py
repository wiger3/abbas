import os
import json
import base64
import asyncio
import hashlib
from urllib.parse import urlparse
import httpx
from PIL import Image
import replicate
import replicate.client
import replicate.version

tenor_apikey = os.getenv('TENOR_APIKEY')

if os.path.isdir('tmp'):
    from shutil import rmtree
    rmtree('tmp')

async def interrogate_clip(url: str, remove_files: bool = True) -> str:
    """
    Describes an image using CLIP
    This routine downloads the image from the internet, converts it to 512p JPEG, and then sends to a CLIP interrogator.

    Args:
        url: URL for the image. It will be downloaded and processed. Supports Tenor links
    Returns:
        Result of interrogating CLIP on the image
    """
    # download the image from the internet
    img = url
    uri = urlparse(url)
    if uri.hostname == 'tenor.com':
        img = await parse_tenor(url)
    if img is None:
        return None
    async with httpx.AsyncClient() as client:
        r = await client.head(img)
        if not r.headers['Content-Type'].startswith('image'):
            return None
        r = await client.get(img)
    filename = 'tmp/' + hashlib.md5(r.content).hexdigest() + "." + r.headers['Content-Type'].split('/')[-1]
    if not os.path.isdir('tmp'):
        os.mkdir('tmp')
    with open(filename, 'wb') as file:
        file.write(r.content)
    
    # convert the image to 512 jpg
    orig_file = filename
    im = Image.open(filename)
    if im.mode != 'RGB':
        im = im.convert("RGB")
    if any(a > 512 for a in im.size):
        x, y = im.size
        if x > y:
            y = int(y*512/x)
            x = 512
        else:
            x = int(x*512/y)
            y = 512
        im = im.resize((x, y))
    filename = os.path.splitext(filename)[0] + ".jpg"
    if remove_files and orig_file != filename:
        try:
            os.remove(orig_file)
        except OSError:
            pass
    im.save(filename)
    im.close()

    # ask clip about the image
    print("starting clip", end='\r')
    model = await replicate.models.async_get('pharmapsychotic/clip-interrogator')
    with open(filename, 'rb') as file:
        data = base64.b64encode(file.read()).decode('utf-8')
        image = f"data:application/octet-stream;base64,{data}"
    input = {
        "mode": "classic",
        "clip_model_name": "ViT-H-14/laion2b_s32b_b79k",
        "image": image
    }
    prediction = await replicate.predictions.async_create(
        model.latest_version,
        input=input
    )
    try:
        async with asyncio.timeout(10):
            await prediction.async_wait()
    except TimeoutError:
        print("ERROR: CLIP timed out (10 seconds)")
        prediction.cancel()
    if prediction.status != "succeeded":
        return None
    if remove_files:
        try:
            os.remove(filename)
        except OSError:
            pass
    return prediction.output


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

async def main():
    caption = await interrogate_clip(input("File link: "), False)
    if caption is None:
        print(":(")
        return
    print(caption)

if __name__ == "__main__":
    asyncio.run(main())
