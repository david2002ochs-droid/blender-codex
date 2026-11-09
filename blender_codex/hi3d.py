"""Synchronous, stdlib Hi3D v3.0 adapter; call from a background thread.

No bpy, login files, automatic paid-task retries, or global urllib configuration.
Provider messages and transport exception strings are deliberately never surfaced:
they can echo credentials, uploaded data, and signed result URLs.
"""

import base64
import http.client
import ipaddress
import json
import math
import os
import re
import struct
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import zlib

_BASE = "https://api.hitem3d.ai"
_TASK_ID = re.compile(r"[A-Za-z0-9._-]{1,256}\Z")
_STATES = {"created", "queueing", "processing", "success", "failed"}
VIEW_ORDER = ("front", "back", "left", "right")


class Hi3DError(Exception):
    """A user-displayable error containing no provider echo or secret URL."""


def normalize_views(views):
    """Validate local view inputs, returning canonical provider order."""
    if not isinstance(views, list) or not 2 <= len(views) <= 4:
        raise Hi3DError("views must contain 2 to 4 images, including front.")
    by_role = {}
    for item in views:
        if not isinstance(item, dict) or set(item) != {"view", "image_path"}:
            raise Hi3DError("Each view requires only view and image_path.")
        role, path = item["view"], item["image_path"]
        if not isinstance(role, str) or role not in VIEW_ORDER or role in by_role:
            raise Hi3DError("View labels must be unique front, back, left or right.")
        if not isinstance(path, str) or not path or not os.path.isabs(path) or "\x00" in path:
            raise Hi3DError("Each view image_path must be an absolute local path.")
        by_role[role] = path
    if "front" not in by_role:
        raise Hi3DError("views must include front.")
    return [{"view": role, "image_path": by_role[role]} for role in VIEW_ORDER if role in by_role]


def _check_image_container(image, mime):
    """Reject truncated/forged containers without adding a decoder dependency.

    This checks structure, not whether a decoder can reconstruct every pixel.
    The legacy single-image path retains its original signature validation.
    """
    valid = False
    if mime == "image/png":
        offset, kinds = 8, []
        while offset + 12 <= len(image):
            size = int.from_bytes(image[offset:offset + 4], "big")
            end = offset + 12 + size
            if end > len(image):
                break
            kind = image[offset + 4:offset + 8]
            data = image[offset + 8:end - 4]
            if zlib.crc32(image[offset + 4:end - 4]) != int.from_bytes(image[end - 4:end], "big"):
                break
            if not kinds and (kind != b"IHDR" or size != 13 or not all(struct.unpack(">II", data[:8]))):
                break
            kinds.append(kind)
            offset = end
            if kind == b"IEND":
                valid = size == 0 and offset == len(image) and b"IDAT" in kinds
                break
    elif mime == "image/jpeg":
        offset, frame = 2, False
        while offset + 4 <= len(image) and image[offset] == 255:
            offset += 1
            while offset < len(image) and image[offset] == 255:
                offset += 1
            if offset + 3 > len(image):
                break
            marker = image[offset]
            size = int.from_bytes(image[offset + 1:offset + 3], "big")
            if size < 2 or offset + 1 + size > len(image):
                break
            if marker in (0xc0, 0xc1, 0xc2):
                frame = size >= 8 and all(struct.unpack(">HH", image[offset + 4:offset + 8]))
            if marker == 0xda:
                valid = frame and size >= 6 and image.endswith(b"\xff\xd9")
                break
            offset += 1 + size
    elif mime == "image/webp":
        offset, frame = 12, False
        if len(image) >= 20 and int.from_bytes(image[4:8], "little") + 8 == len(image):
            while offset + 8 <= len(image):
                kind = image[offset:offset + 4]
                size = int.from_bytes(image[offset + 4:offset + 8], "little")
                end = offset + 8 + size + (size % 2)
                if end > len(image):
                    break
                data = image[offset + 8:offset + 8 + size]
                frame |= (kind == b"VP8 " and size >= 10 and data[3:6] == b"\x9d\x01\x2a"
                          or kind == b"VP8L" and size >= 5 and data[0] == 0x2f)
                offset = end
            valid = frame and offset == len(image)
    if not valid:
        raise Hi3DError("A view image has an invalid or truncated PNG, JPEG or WEBP container.")


def estimate_credits(resolution="2048quality", pbr=True):
    """Published credit estimate only, not a guaranteed provider quote.

    https://docs.hi3d.ai/en/api/getting-started/pricing (2026-11-07).
    """
    if resolution not in ("2048quality", "2048master"):
        raise Hi3DError("Choose 2048quality or 2048master.")
    return (40 if resolution == "2048quality" else 140) + (5 if pbr else 0)


def _safe_download_url(url):
    try:
        if not isinstance(url, str) or not url or len(url) > 16384:
            raise ValueError()
        if any(ord(c) <= 32 or ord(c) == 127 for c in url) or "\\" in url:
            raise ValueError()
        parsed = urllib.parse.urlsplit(url)
        host = parsed.hostname
        if (parsed.scheme != "https" or not host or parsed.username is not None
                or parsed.password is not None or parsed.port not in (None, 443)
                or parsed.fragment):
            raise ValueError()
        host = host.lower().rstrip(".")
        if host == "localhost" or host.endswith((".localhost", ".local", ".internal")):
            raise ValueError()
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            # Require a regular public-style DNS name; reject numeric legacy IPs.
            if "." not in host or not re.fullmatch(r"[a-z0-9.-]+", host) or host.replace(".", "").isdigit():
                raise ValueError()
        else:
            if not address.is_global:
                raise ValueError()
        return url
    except (ValueError, TypeError):
        raise Hi3DError("The provider returned an unsafe download address; refresh the task status.") from None


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        fp.close()
        raise Hi3DError("Hi3D API redirects are refused to protect your credentials.")


class _DownloadRedirect(urllib.request.HTTPRedirectHandler):
    max_redirections = 5
    max_repeats = 2

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Rebuild instead of copying any Authorization/Cookie or other headers.
        try:
            return urllib.request.Request(_safe_download_url(newurl), method="GET",
                                          headers={"Accept": "model/gltf-binary"})
        except Hi3DError:
            fp.close()
            raise


class _AuthExpired(Exception):
    pass


class Hi3DClient:
    MAX_IMAGE_BYTES = 20_000_000
    MAX_JSON_BYTES = 1024 * 1024
    MAX_GLB_BYTES = 512 * 1024 * 1024
    HTTP_TIMEOUT = 60
    DOWNLOAD_TIMEOUT = 600
    estimate_credits = staticmethod(estimate_credits)

    def __init__(self, client_id, client_secret):
        if (not isinstance(client_id, str) or not isinstance(client_secret, str)
                or not client_id.strip() or not client_secret.strip()
                or ":" in client_id or any(c in client_id + client_secret for c in "\r\n\x00")):
            raise Hi3DError("Enter your Hi3D client ID and client secret.")
        self._client_id = client_id
        self._client_secret = client_secret
        self._token = None
        self._lock = threading.RLock()
        self._api = urllib.request.build_opener(_NoRedirect())
        self._downloads = urllib.request.build_opener(_DownloadRedirect())

    def _json(self, path, method="GET", body=None, content_type="application/json", authorization=None):
        headers = {"Accept": "application/json", "Content-Type": content_type}
        if authorization is not None:
            headers["Authorization"] = authorization
        request = urllib.request.Request(_BASE + path, data=body, headers=headers, method=method)
        try:
            with self._api.open(request, timeout=self.HTTP_TIMEOUT) as response:
                if response.status != 200:
                    raise Hi3DError("Hi3D returned an unexpected HTTP status.")
                raw = response.read(self.MAX_JSON_BYTES + 1)
            if len(raw) > self.MAX_JSON_BYTES:
                raise Hi3DError("Hi3D returned an oversized response.")
            payload = json.loads(raw)
        except urllib.error.HTTPError as exc:
            status = exc.code
            exc.close()
            if status == 401:
                raise _AuthExpired() from None
            if status == 429:
                raise Hi3DError("Hi3D rate limit reached. Wait before trying again.") from None
            raise Hi3DError("Hi3D HTTP request failed (status %d)." % status) from None
        except Hi3DError:
            raise
        except (OSError, ValueError, urllib.error.URLError, http.client.HTTPException, RecursionError):
            raise Hi3DError("Could not read a valid Hi3D response. Check your connection and credentials.") from None
        if not isinstance(payload, dict):
            raise Hi3DError("Hi3D returned an invalid response.")
        code = payload.get("code")
        if code not in (200, "200"):
            # Only fixed locally defined messages; never echo 'msg', 'message',
            # arbitrary codes, response bodies or HTTP exception URLs.
            if code in (401, "401"):
                raise _AuthExpired()
            messages = {
                "40010000": "Hi3D rejected the client credentials.",
                "30010000": "Your Hi3D credit balance is insufficient.",
                "10031001": "Hi3D rejected the image size; use an image below 20 MB.",
                "10031002": "Hi3D rejected the face count. No automatic retry was made.",
                "10031003": "Hi3D rejected the selected resolution.",
                "10031005": "Hi3D requires a PNG, JPEG or WEBP image.",
                "50010001": "Hi3D reported generation failure. Check the existing task before resubmitting.",
            }
            safe_code = str(code) if type(code) in (int, str) else ""
            raise Hi3DError(messages.get(safe_code, "Hi3D rejected the request. Check the provider dashboard."))
        if not isinstance(payload.get("data"), dict):
            raise Hi3DError("Hi3D returned invalid response data.")
        return payload["data"]

    def _authenticate(self):
        basic = base64.b64encode((self._client_id + ":" + self._client_secret).encode("utf-8")).decode("ascii")
        try:
            data = self._json("/open-api/v1/auth/token", "POST", b"{}", authorization="Basic " + basic)
        except _AuthExpired:
            raise Hi3DError("Hi3D authentication failed. Check your client ID and client secret.") from None
        token = data.get("accessToken")
        if (not isinstance(token, str) or not token or len(token) > 16384
                or any(ord(c) < 33 or ord(c) > 126 for c in token)):
            raise Hi3DError("Hi3D returned an invalid access token.")
        self._token = token

    def _authorized(self, path, method="GET", body=None, content_type="application/json"):
        with self._lock:
            if self._token is None:
                self._authenticate()
            # Retry only read-only GETs, once, after an explicit 401.
            for attempt in range(2 if method == "GET" else 1):
                try:
                    return self._json(path, method, body, content_type, "Bearer " + self._token)
                except _AuthExpired:
                    self._token = None
                    if method != "GET" or attempt:
                        raise Hi3DError("Hi3D authorization expired. Recheck credentials before continuing.") from None
                    self._authenticate()

    def balance(self):
        data = self._authorized("/open-api/v1/balance")
        value = data.get("totalBalance")
        try:
            if isinstance(value, bool) or not isinstance(value, (int, float, str)):
                raise ValueError()
            result = float(value)
            if not math.isfinite(result) or result < 0:
                raise ValueError()
            return result
        except (ValueError, OverflowError):
            raise Hi3DError("Hi3D returned an invalid credit balance.") from None

    def _image(self, image_path):
        try:
            with open(image_path, "rb") as source:
                if os.fstat(source.fileno()).st_size > self.MAX_IMAGE_BYTES:
                    raise Hi3DError("Choose an image no larger than 20 MB.")
                image = source.read(self.MAX_IMAGE_BYTES + 1)
            if not image or len(image) > self.MAX_IMAGE_BYTES:
                raise Hi3DError("Choose a nonempty image no larger than 20 MB.")
            suffix = os.path.splitext(os.fspath(image_path))[1].lower()
        except (OSError, TypeError, ValueError):
            raise Hi3DError("The input image could not be read.") from None
        if suffix == ".png" and image.startswith(b"\x89PNG\r\n\x1a\n"):
            return image, "input.png", "image/png"
        if suffix in (".jpg", ".jpeg") and image.startswith(b"\xff\xd8\xff"):
            return image, "input.jpg", "image/jpeg"
        if suffix == ".webp" and image.startswith(b"RIFF") and image[8:12] == b"WEBP":
            return image, "input.webp", "image/webp"
        raise Hi3DError("Choose a PNG, JPEG or WEBP image with a matching file extension.")

    def prepare_images(self, image_path="", views=None):
        if views is None:
            return [("single", self._image(image_path))]
        if image_path:
            raise Hi3DError("Use image_path or views, not both, for a new generation.")
        images = []
        for item in normalize_views(views):
            image = self._image(item["image_path"])
            _check_image_container(image[0], image[2])
            images.append((item["view"], image))
        return images

    def submit(self, image_path="", resolution="2048quality", pbr=True, faces=2000000, *, views=None):
        images = self.prepare_images(image_path, views)
        return self._submit_images(images, resolution, pbr, faces)

    def _submit_images(self, images, resolution="2048quality", pbr=True, faces=2000000):
        """Submit already validated snapshots; journal hashes refer to these bytes."""
        estimate_credits(resolution, pbr)  # Validate before authenticating/uploading.
        if type(faces) is not int or not 100000 <= faces <= 5000000:
            raise Hi3DError("Choose a face count between 100000 and 5000000.")
        boundary = "Hi3D-" + uuid.uuid4().hex
        fields = {"model": "hi3dv3.0", "request_type": "3", "resolution": resolution,
                  "pbr": "1" if pbr else "0", "format": "2", "face": str(faces)}
        multi = images[0][0] != "single"
        if multi:
            fields["multi_images_bit"] = "".join("1" if any(role == view for role, _ in images)
                                                else "0" for view in VIEW_ORDER)
        chunks = []
        for name, value in fields.items():
            chunks.append(("--%s\r\nContent-Disposition: form-data; name=\"%s\"\r\n\r\n%s\r\n" %
                           (boundary, name, value)).encode("ascii"))
        for role, (image, filename, mime) in images:
            field = "multi_images" if multi else "images"
            if multi:
                filename = role + os.path.splitext(filename)[1]
            chunks.extend([("--%s\r\nContent-Disposition: form-data; name=\"%s\"; filename=\"%s\"\r\n"
                            "Content-Type: %s\r\n\r\n" % (boundary, field, filename, mime)).encode("ascii"),
                           image, b"\r\n"])
        chunks.append(("--%s--\r\n" % boundary).encode("ascii"))
        try:
            data = self._authorized("/open-api/v1/submit-task", "POST", b"".join(chunks),
                                    "multipart/form-data; boundary=" + boundary)
            task_id = data.get("task_id")
            if not isinstance(task_id, str) or not _TASK_ID.fullmatch(task_id):
                raise Hi3DError("Hi3D did not return a usable task ID.")
            return task_id
        except Hi3DError as exc:
            raise Hi3DError(str(exc) + " Submission was not retried. A paid task may already exist; "
                             "check your provider task history before submitting again.") from None

    def query(self, task_id):
        if not isinstance(task_id, str) or not _TASK_ID.fullmatch(task_id):
            raise Hi3DError("Enter a valid Hi3D task ID.")
        data = self._authorized("/open-api/v1/query-task?" + urllib.parse.urlencode({"task_id": task_id}))
        if not isinstance(data.get("state"), str) or data["state"] not in _STATES:
            raise Hi3DError("Hi3D returned an unknown task state. Keep the task ID and check again later.")
        if data.get("task_id", task_id) != task_id:
            raise Hi3DError("Hi3D returned a different task ID; no result was accepted.")
        result = {"state": data["state"], "task_id": task_id}
        for key in ("url", "cover_url"):
            if data.get(key):
                result[key] = _safe_download_url(data[key])
        return result

    def download(self, url, destination):
        url = _safe_download_url(url)
        temporary = None
        try:
            destination = os.path.abspath(os.fspath(destination))
            request = urllib.request.Request(url, headers={"Accept": "model/gltf-binary"}, method="GET")
            deadline = time.monotonic() + self.DOWNLOAD_TIMEOUT
            with self._downloads.open(request, timeout=self.HTTP_TIMEOUT) as response:
                if response.status != 200:
                    raise Hi3DError("The model download returned an unexpected HTTP status.")
                length_header = response.headers.get("Content-Length")
                expected = None
                if length_header is not None:
                    try:
                        expected = int(length_header)
                    except (TypeError, ValueError):
                        raise Hi3DError("The model download has an invalid size header.") from None
                    if not 12 <= expected <= self.MAX_GLB_BYTES:
                        raise Hi3DError("The model download exceeds the size limit or is empty.")
                with tempfile.NamedTemporaryFile(mode="w+b", prefix=".hi3d-", suffix=".part",
                                                 dir=os.path.dirname(destination), delete=False) as output:
                    temporary = output.name
                    total = 0
                    header = b""
                    while True:
                        if time.monotonic() > deadline:
                            raise Hi3DError("The model download timed out. Refresh the task and try downloading again.")
                        chunk = response.read(min(65536, self.MAX_GLB_BYTES - total + 1))
                        if not chunk:
                            break
                        total += len(chunk)
                        if total > self.MAX_GLB_BYTES:
                            raise Hi3DError("The model download exceeds the size limit.")
                        if len(header) < 12:
                            header += chunk[:12 - len(header)]
                        output.write(chunk)
                    if len(header) != 12 or header[:4] != b"glTF":
                        raise Hi3DError("The downloaded file is not a GLB model.")
                    version, declared = struct.unpack("<II", header[4:])
                    if version != 2 or total < 20 or declared != total or (expected is not None and expected != total):
                        raise Hi3DError("The downloaded GLB is incomplete or has an invalid length/version.")
                    output.flush()
                    os.fsync(output.fileno())
            os.replace(temporary, destination)
            temporary = None
            return destination
        except Hi3DError:
            raise
        except urllib.error.HTTPError as exc:
            exc.close()
            raise Hi3DError("The model download failed. Refresh the task URL before downloading again.") from None
        except (OSError, ValueError, TypeError, urllib.error.URLError, http.client.HTTPException):
            raise Hi3DError("The model could not be downloaded or saved. Refresh the task URL and check the destination.") from None
        finally:
            if temporary is not None:
                try:
                    os.unlink(temporary)
                except OSError:
                    pass
