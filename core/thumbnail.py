import time
from io import BytesIO

import requests
from PIL import Image, ImageOps


THUMBNAIL_SIZE = (200, 113)
THUMBNAIL_MAX_BYTES = 2 * 1024 * 1024   # real YouTube thumbnails are well under 1MB
THUMBNAIL_MAX_SECONDS = 10              # total budget; requests' timeout= is per-read only
THUMBNAIL_MAX_PIXELS = 4096 * 4096      # checked from the header, before decoding anything


""" Downloads and decodes a thumbnail with hard limits, since the URL and the bytes both come
from remote metadata: caps size and total time, requires an image Content-Type, and rejects
huge dimensions before decoding (decompression bombs). Blocking: call it from a worker thread. """
def fetch_thumbnail(url: str, size=THUMBNAIL_SIZE):
    deadline = time.monotonic() + THUMBNAIL_MAX_SECONDS
    with requests.get(url, timeout=5, stream=True) as response:
        response.raise_for_status()
        if not response.headers.get("Content-Type", "").startswith("image/"):
            raise ValueError("Thumbnail is not an image")

        data = BytesIO()
        for chunk in response.iter_content(chunk_size=64 * 1024):
            data.write(chunk)
            if data.tell() > THUMBNAIL_MAX_BYTES:
                raise ValueError("Thumbnail too large")
            if time.monotonic() > deadline:
                raise TimeoutError("Thumbnail download too slow")

    data.seek(0)
    image_pil = Image.open(data)  # lazy: only the header is parsed here
    if image_pil.width * image_pil.height > THUMBNAIL_MAX_PIXELS:
        raise ValueError("Thumbnail dimensions too large")

    # Uses ImageOps.fit to crop and resize the image without distortion
    return ImageOps.fit(image_pil, size, Image.Resampling.LANCZOS)
