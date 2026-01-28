This file is a merged representation of a subset of the codebase, containing specifically included files, combined into a single document by Repomix.

================================================================
File Summary
================================================================

Purpose:
--------
This file contains a packed representation of a subset of the repository's contents that is considered the most important context.
It is designed to be easily consumable by AI systems for analysis, code review,
or other automated processes.

File Format:
------------
The content is organized as follows:
1. This summary section
2. Repository information
3. Directory structure
4. Repository files (if enabled)
5. Multiple file entries, each consisting of:
  a. A separator line (================)
  b. The file path (File: path/to/file)
  c. Another separator line
  d. The full contents of the file
  e. A blank line

Usage Guidelines:
-----------------
- This file should be treated as read-only. Any changes should be made to the
  original repository files, not this packed version.
- When processing this file, use the file path to distinguish
  between different files in the repository.
- Be aware that this file may contain sensitive information. Handle it with
  the same level of security as you would the original repository.

Notes:
------
- Some files may have been excluded based on .gitignore rules and Repomix's configuration
- Binary files are not included in this packed representation. Please refer to the Repository Structure section for a complete list of file paths, including binary files
- Only files matching these patterns are included: **/downloader/*.py, **/extractor/*.py, **/postprocessor/*.py
- Files matching patterns in .gitignore are excluded
- Files matching default ignore patterns are excluded
- Files are sorted by Git change count (files with more changes are at the bottom)


================================================================
Directory Structure
================================================================
gallery_dl/
  downloader/
    __init__.py
    common.py
    http.py
    text.py
    ytdl.py
  extractor/
    __init__.py
    common.py
    generic.py
    hitomi.py
    message.py
    noop.py
    nozomi.py
  postprocessor/
    __init__.py
    classify.py
    common.py
    compare.py
    directory.py
    exec.py
    hash.py
    metadata.py
    mtime.py
    python.py
    rename.py
    ugoira.py
    zip.py

================================================================
Files
================================================================

================
File: gallery_dl/downloader/__init__.py
================
# -*- coding: utf-8 -*-

# Copyright 2015-2021 Mike Fährmann
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 as
# published by the Free Software Foundation.

"""Downloader modules"""

modules = [
    "http",
    "text",
    "ytdl",
]


def find(scheme):
    """Return downloader class suitable for handling the given scheme"""
    try:
        return _cache[scheme]
    except KeyError:
        pass

    cls = None
    if scheme == "https":
        scheme = "http"
    if scheme in modules:  # prevent unwanted imports
        try:
            module = __import__(scheme, globals(), None, None, 1)
        except ImportError:
            pass
        else:
            cls = module.__downloader__

    if scheme == "http":
        _cache["http"] = _cache["https"] = cls
    else:
        _cache[scheme] = cls
    return cls


# --------------------------------------------------------------------
# internals

_cache = {}

================
File: gallery_dl/downloader/common.py
================
# -*- coding: utf-8 -*-

# Copyright 2014-2025 Mike Fährmann
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 as
# published by the Free Software Foundation.

"""Common classes and constants used by downloader modules."""

import os
from .. import config, util
_config = config._config


class DownloaderBase():
    """Base class for downloaders"""
    scheme = ""

    def __init__(self, job):
        extractor = job.extractor
        self.log = job.get_logger("downloader." + self.scheme)

        if opts := self._extractor_config(extractor):
            self.opts = opts
            self.config = self.config_opts

        self.out = job.out
        self.session = extractor.session
        self.part = self.config("part", True)
        self.partdir = self.config("part-directory")

        if self.partdir:
            if isinstance(self.partdir, dict):
                self.partdir = [
                    (util.compile_filter(expr) if expr else util.true,
                     util.expand_path(pdir))
                    for expr, pdir in self.partdir.items()
                ]
            else:
                self.partdir = util.expand_path(self.partdir)
                os.makedirs(self.partdir, exist_ok=True)

        proxies = self.config("proxy", util.SENTINEL)
        if proxies is util.SENTINEL:
            self.proxies = extractor._proxies
        else:
            self.proxies = util.build_proxy_map(proxies, self.log)

    def config(self, key, default=None):
        """Interpolate downloader config value for 'key'"""
        return config.interpolate(("downloader", self.scheme), key, default)

    def config_opts(self, key, default=None, conf=_config):
        if key in conf:
            return conf[key]
        value = self.opts.get(key, util.SENTINEL)
        if value is not util.SENTINEL:
            return value
        return config.interpolate(("downloader", self.scheme), key, default)

    def _extractor_config(self, extractor):
        path = extractor._cfgpath
        if not isinstance(path, list):
            return self._extractor_opts(path[1], path[2])

        opts = {}
        for cat, sub in reversed(path):
            if popts := self._extractor_opts(cat, sub):
                opts.update(popts)
        return opts

    def _extractor_opts(self, category, subcategory):
        cfg = config.get(("extractor",), category)
        if not cfg:
            return None

        if copts := cfg.get(self.scheme):
            if subcategory in cfg:
                try:
                    if sopts := cfg[subcategory].get(self.scheme):
                        opts = copts.copy()
                        opts.update(sopts)
                        return opts
                except Exception:
                    self._report_config_error(subcategory, cfg[subcategory])
            return copts

        if subcategory in cfg:
            try:
                return cfg[subcategory].get(self.scheme)
            except Exception:
                self._report_config_error(subcategory, cfg[subcategory])

        return None

    def _report_config_error(self, subcategory, value):
        config.log.warning("Subcategory '%s' set to '%s' instead of object",
                           subcategory, util.json_dumps(value).strip('"'))

    def download(self, url, pathfmt):
        """Write data from 'url' into the file specified by 'pathfmt'"""

================
File: gallery_dl/downloader/http.py
================
# -*- coding: utf-8 -*-

# Copyright 2014-2025 Mike Fährmann
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 as
# published by the Free Software Foundation.

"""Downloader module for http:// and https:// URLs"""

import time
import mimetypes
from requests.exceptions import RequestException, ConnectionError, Timeout
from .common import DownloaderBase
from .. import text, util, output, exception
from ssl import SSLError
FLAGS = util.FLAGS


class HttpDownloader(DownloaderBase):
    scheme = "http"

    def __init__(self, job):
        DownloaderBase.__init__(self, job)
        extractor = job.extractor
        self.downloading = False

        self.adjust_extension = self.config("adjust-extensions", True)
        self.chunk_size = self.config("chunk-size", 32768)
        self.metadata = extractor.config("http-metadata")
        self.progress = self.config("progress", 3.0)
        self.validate = self.config("validate", True)
        self.validate_html = self.config("validate-html", True)
        self.headers = self.config("headers")
        self.minsize = self.config("filesize-min")
        self.maxsize = self.config("filesize-max")
        self.retries = self.config("retries", extractor._retries)
        self.retry_codes = self.config("retry-codes", extractor._retry_codes)
        self.timeout = self.config("timeout", extractor._timeout)
        self.verify = self.config("verify", extractor._verify)
        self.mtime = self.config("mtime", True)
        self.rate = self.config("rate")
        interval_429 = self.config("sleep-429")

        if not self.config("consume-content", False):
            # this resets the underlying TCP connection, and therefore
            # if the program makes another request to the same domain,
            # a new connection (either TLS or plain TCP) must be made
            self.release_conn = lambda resp: resp.close()

        if self.retries < 0:
            self.retries = float("inf")
        if self.minsize:
            minsize = text.parse_bytes(self.minsize)
            if not minsize:
                self.log.warning(
                    "Invalid minimum file size (%r)", self.minsize)
            self.minsize = minsize
        if self.maxsize:
            maxsize = text.parse_bytes(self.maxsize)
            if not maxsize:
                self.log.warning(
                    "Invalid maximum file size (%r)", self.maxsize)
            self.maxsize = maxsize
        if isinstance(self.chunk_size, str):
            chunk_size = text.parse_bytes(self.chunk_size)
            if not chunk_size:
                self.log.warning(
                    "Invalid chunk size (%r)", self.chunk_size)
                chunk_size = 32768
            self.chunk_size = chunk_size
        if self.rate:
            func = util.build_selection_func(self.rate, 0, text.parse_bytes)
            if rmax := func.args[1] if hasattr(func, "args") else func():
                if rmax < self.chunk_size:
                    # reduce chunk_size to allow for one iteration each second
                    self.chunk_size = rmax
                self.rate = func
                self.receive = self._receive_rate
            else:
                self.log.warning("Invalid rate limit (%r)", self.rate)
                self.rate = False
        if self.progress is not None:
            self.receive = self._receive_rate
            if self.progress < 0.0:
                self.progress = 0.0
        if interval_429 is None:
            self.interval_429 = extractor._interval_429
        else:
            self.interval_429 = util.build_duration_func(interval_429)

    def download(self, url, pathfmt):
        try:
            return self._download_impl(url, pathfmt)
        except Exception as exc:
            if self.downloading:
                output.stderr_write("\n")
            self.log.traceback(exc)
            raise
        finally:
            # remove file from incomplete downloads
            if self.downloading and not self.part:
                util.remove_file(pathfmt.temppath)

    def _download_impl(self, url, pathfmt):
        response = None
        tries = code = 0
        msg = ""

        metadata = self.metadata
        kwdict = pathfmt.kwdict
        expected_status = kwdict.get(
            "_http_expected_status", ())
        adjust_extension = kwdict.get(
            "_http_adjust_extension", self.adjust_extension)

        if self.part and not metadata:
            pathfmt.part_enable(self.partdir)

        while True:
            if tries:
                if response:
                    self.release_conn(response)
                    response = None

                self.log.warning("%s (%s/%s)", msg, tries, self.retries+1)
                if tries > self.retries:
                    return False

                if code == 429 and self.interval_429:
                    s = self.interval_429()
                    time.sleep(s if s > tries else tries)
                else:
                    time.sleep(tries)
                code = 0

            tries += 1
            file_header = None

            # collect HTTP headers
            headers = {"Accept": "*/*"}
            #   file-specific headers
            if extra := kwdict.get("_http_headers"):
                headers.update(extra)
            #   general headers
            if self.headers:
                headers.update(self.headers)
            #   partial content
            if file_size := pathfmt.part_size():
                headers["Range"] = f"bytes={file_size}-"

            # connect to (remote) source
            try:
                response = self.session.request(
                    kwdict.get("_http_method", "GET"), url,
                    stream=True,
                    headers=headers,
                    data=kwdict.get("_http_data"),
                    timeout=self.timeout,
                    proxies=self.proxies,
                    verify=self.verify,
                )
            except ConnectionError as exc:
                try:
                    reason = exc.args[0].reason
                    cls = reason.__class__.__name__
                    pre, _, err = str(reason.args[-1]).partition(":")
                    msg = f"{cls}: {(err or pre).lstrip()}"
                except Exception:
                    msg = str(exc)
                continue
            except Timeout as exc:
                msg = str(exc)
                continue
            except Exception as exc:
                self.log.warning(exc)
                return False

            # check response
            code = response.status_code
            if code == 200 or code in expected_status:  # OK
                offset = 0
                size = response.headers.get("Content-Length")
            elif code == 206:  # Partial Content
                offset = file_size
                size = response.headers["Content-Range"].rpartition("/")[2]
            elif code == 416 and file_size:  # Requested Range Not Satisfiable
                break
            else:
                msg = f"'{code} {response.reason}' for '{url}'"

                challenge = util.detect_challenge(response)
                if challenge is not None:
                    self.log.warning(challenge)

                if code in self.retry_codes or 500 <= code < 600:
                    continue
                retry = kwdict.get("_http_retry")
                if retry and retry(response):
                    continue
                self.release_conn(response)
                self.log.warning(msg)
                return False

            # check for invalid responses
            if self.validate and \
                    (validate := kwdict.get("_http_validate")) is not None:
                try:
                    result = validate(response)
                except Exception:
                    self.release_conn(response)
                    raise
                if isinstance(result, str):
                    url = result
                    tries -= 1
                    continue
                if not result:
                    self.release_conn(response)
                    self.log.warning("Invalid response")
                    return False
            if self.validate_html and response.headers.get(
                    "content-type", "").startswith("text/html") and \
                    pathfmt.extension not in ("html", "htm"):
                if response.history:
                    self.log.warning("HTTP redirect to '%s'", response.url)
                else:
                    self.log.warning("HTML response")
                return False

            # check file size
            size = text.parse_int(size, None)
            if size is not None:
                if not size:
                    self.release_conn(response)
                    self.log.warning("Empty file")
                    return False
                if self.minsize and size < self.minsize:
                    self.release_conn(response)
                    self.log.warning(
                        "File size smaller than allowed minimum (%s < %s)",
                        size, self.minsize)
                    pathfmt.temppath = ""
                    return True
                if self.maxsize and size > self.maxsize:
                    self.release_conn(response)
                    self.log.warning(
                        "File size larger than allowed maximum (%s > %s)",
                        size, self.maxsize)
                    pathfmt.temppath = ""
                    return True

            build_path = False

            # set missing filename extension from MIME type
            if not pathfmt.extension:
                pathfmt.set_extension(self._find_extension(response))
                build_path = True

            # set metadata from HTTP headers
            if metadata:
                kwdict[metadata] = util.extract_headers(response)
                build_path = True

            # build and check file path
            if build_path:
                pathfmt.build_path()
                if pathfmt.exists():
                    pathfmt.temppath = ""
                    # release the connection back to pool by explicitly
                    # calling .close()
                    # see https://requests.readthedocs.io/en/latest/user
                    # /advanced/#body-content-workflow
                    # when the image size is on the order of megabytes,
                    # re-establishing a TLS connection will typically be faster
                    # than consuming the whole response
                    response.close()
                    return True
                if self.part and metadata:
                    pathfmt.part_enable(self.partdir)
                metadata = False

            content = response.iter_content(self.chunk_size)

            validate_sig = kwdict.get("_http_signature")
            validate_ext = (adjust_extension and
                            pathfmt.extension in SIGNATURE_CHECKS)

            # check filename extension against file header
            if not offset and (validate_ext or validate_sig):
                try:
                    file_header = next(
                        content if response.raw.chunked
                        else response.iter_content(16), b"")
                except (RequestException, SSLError) as exc:
                    msg = str(exc)
                    continue
                if validate_sig:
                    result = validate_sig(file_header)
                    if result is not True:
                        self.release_conn(response)
                        self.log.warning(
                            result or "Invalid file signature bytes")
                        return False
                if validate_ext and self._adjust_extension(
                        pathfmt, file_header) and pathfmt.exists():
                    pathfmt.temppath = ""
                    response.close()
                    return True

            # set open mode
            if not offset:
                mode = "w+b"
                if file_size:
                    self.log.debug("Unable to resume partial download")
            else:
                mode = "r+b"
                self.log.debug("Resuming download at byte %d", offset)

            # download content
            self.downloading = True
            with pathfmt.open(mode) as fp:
                if fp is None:
                    # '.part' file no longer exists
                    break
                if file_header:
                    fp.write(file_header)
                    offset += len(file_header)
                elif offset:
                    if adjust_extension and \
                            pathfmt.extension in SIGNATURE_CHECKS:
                        self._adjust_extension(pathfmt, fp.read(16))
                    fp.seek(offset)

                self.out.start(pathfmt.path)
                try:
                    self.receive(fp, content, size, offset)
                except (RequestException, SSLError) as exc:
                    msg = str(exc)
                    output.stderr_write("\n")
                    continue
                except exception.StopExtraction:
                    response.close()
                    return False
                except exception.ControlException:
                    response.close()
                    raise

                # check file size
                if size and (fsize := fp.tell()) < size:
                    if (segmented := kwdict.get("_http_segmented")) and \
                            segmented is True or segmented == fsize:
                        tries -= 1
                        msg = "Resuming segmented download"
                        output.stdout_write("\r")
                    else:
                        msg = f"file size mismatch ({fsize} < {size})"
                        output.stderr_write("\n")
                    continue

            break

        self.downloading = False
        if self.mtime:
            if "_http_lastmodified" in kwdict:
                kwdict["_mtime_http"] = kwdict["_http_lastmodified"]
            else:
                kwdict["_mtime_http"] = response.headers.get("Last-Modified")
        else:
            kwdict["_mtime_http"] = None

        return True

    def release_conn(self, response):
        """Release connection back to pool by consuming response body"""
        try:
            for _ in response.iter_content(self.chunk_size):
                pass
        except (RequestException, SSLError) as exc:
            output.stderr_write("\n")
            self.log.debug(
                "Unable to consume response body (%s: %s); "
                "closing the connection anyway", exc.__class__.__name__, exc)
            response.close()

    def receive(self, fp, content, bytes_total, bytes_start):
        write = fp.write
        for data in content:
            write(data)

            if FLAGS.DOWNLOAD is not None:
                FLAGS.process("DOWNLOAD")

    def _receive_rate(self, fp, content, bytes_total, bytes_start):
        rate = self.rate() if self.rate else None
        write = fp.write
        progress = self.progress

        bytes_downloaded = 0
        time_start = time.monotonic()

        for data in content:
            time_elapsed = time.monotonic() - time_start
            bytes_downloaded += len(data)

            write(data)

            if FLAGS.DOWNLOAD is not None:
                FLAGS.process("DOWNLOAD")

            if progress is not None:
                if time_elapsed > progress:
                    self.out.progress(
                        bytes_total,
                        bytes_start + bytes_downloaded,
                        int(bytes_downloaded / time_elapsed),
                    )

            if rate is not None:
                time_expected = bytes_downloaded / rate
                if time_expected > time_elapsed:
                    time.sleep(time_expected - time_elapsed)

    def _find_extension(self, response):
        """Get filename extension from MIME type"""
        mtype = response.headers.get("Content-Type", "image/jpeg")
        mtype = mtype.partition(";")[0].lower()

        if "/" not in mtype:
            mtype = "image/" + mtype

        if mtype in MIME_TYPES:
            return MIME_TYPES[mtype]

        if ext := mimetypes.guess_extension(mtype, strict=False):
            return ext[1:]

        self.log.warning("Unknown MIME type '%s'", mtype)
        return "bin"

    def _adjust_extension(self, pathfmt, file_header):
        """Check filename extension against file header"""
        if not SIGNATURE_CHECKS[pathfmt.extension](file_header):
            for ext, check in SIGNATURE_CHECKS.items():
                if check(file_header):
                    self.log.debug(
                        "Adjusting filename extension of '%s' to '%s'",
                        pathfmt.filename, ext)
                    pathfmt.set_extension(ext)
                    pathfmt.build_path()
                    return True
        return False


MIME_TYPES = {
    "image/jpeg"    : "jpg",
    "image/jpg"     : "jpg",
    "image/png"     : "png",
    "image/gif"     : "gif",
    "image/bmp"     : "bmp",
    "image/x-bmp"   : "bmp",
    "image/x-ms-bmp": "bmp",
    "image/webp"    : "webp",
    "image/avif"    : "avif",
    "image/heic"    : "heic",
    "image/heif"    : "heif",
    "image/svg+xml" : "svg",
    "image/ico"     : "ico",
    "image/icon"    : "ico",
    "image/x-icon"  : "ico",
    "image/vnd.microsoft.icon" : "ico",
    "image/x-photoshop"        : "psd",
    "application/x-photoshop"  : "psd",
    "image/vnd.adobe.photoshop": "psd",

    "video/webm": "webm",
    "video/ogg" : "ogg",
    "video/mp4" : "mp4",
    "video/m4v" : "m4v",
    "video/x-m4v": "m4v",
    "video/quicktime": "mov",

    "audio/wav"  : "wav",
    "audio/x-wav": "wav",
    "audio/webm" : "webm",
    "audio/ogg"  : "ogg",
    "audio/mpeg" : "mp3",
    "audio/aac"  : "aac",
    "audio/x-aac": "aac",

    "application/vnd.apple.mpegurl": "m3u8",
    "application/x-mpegurl"        : "m3u8",
    "application/dash+xml"         : "mpd",

    "application/zip"  : "zip",
    "application/x-zip": "zip",
    "application/x-zip-compressed": "zip",
    "application/rar"  : "rar",
    "application/x-rar": "rar",
    "application/x-rar-compressed": "rar",
    "application/x-7z-compressed" : "7z",

    "application/pdf"  : "pdf",
    "application/x-pdf": "pdf",
    "application/x-shockwave-flash": "swf",

    "text/html": "html",

    "application/ogg": "ogg",
    # https://www.iana.org/assignments/media-types/model/obj
    "model/obj": "obj",
    "application/octet-stream": "bin",
}


def _signature_html(s):
    s = s[:14].lstrip()
    return s and b"<!doctype html".startswith(s.lower())


# https://en.wikipedia.org/wiki/List_of_file_signatures
SIGNATURE_CHECKS = {
    "jpg" : lambda s: s[0:3] == b"\xFF\xD8\xFF",
    "png" : lambda s: s[0:8] == b"\x89PNG\r\n\x1A\n",
    "gif" : lambda s: s[0:6] in (b"GIF87a", b"GIF89a"),
    "bmp" : lambda s: s[0:2] == b"BM",
    "webp": lambda s: (s[0:4] == b"RIFF" and
                       s[8:12] == b"WEBP"),
    "avif": lambda s: s[4:11] == b"ftypavi" and s[11] in b"fs",
    "heic": lambda s: (s[4:10] == b"ftyphe" and s[10:12] in (
                       b"ic", b"im", b"is", b"ix", b"vc", b"vm", b"vs")),
    "svg" : lambda s: s[0:5] == b"<?xml",
    "ico" : lambda s: s[0:4] == b"\x00\x00\x01\x00",
    "cur" : lambda s: s[0:4] == b"\x00\x00\x02\x00",
    "psd" : lambda s: s[0:4] == b"8BPS",
    "mp4" : lambda s: (s[4:8] == b"ftyp" and s[8:11] in (
                       b"mp4", b"avc", b"iso")),
    "m4v" : lambda s: s[4:11] == b"ftypM4V",
    "mov" : lambda s: s[4:12] == b"ftypqt  ",
    "webm": lambda s: s[0:4] == b"\x1A\x45\xDF\xA3",
    "ogg" : lambda s: s[0:4] == b"OggS",
    "wav" : lambda s: (s[0:4] == b"RIFF" and
                       s[8:12] == b"WAVE"),
    "mp3" : lambda s: (s[0:3] == b"ID3" or
                       s[0:2] in (b"\xFF\xFB", b"\xFF\xF3", b"\xFF\xF2")),
    "aac" : lambda s: s[0:2] in (b"\xFF\xF9", b"\xFF\xF1"),
    "m3u8": lambda s: s[0:7] == b"#EXTM3U",
    "mpd" : lambda s: b"<MPD" in s,
    "zip" : lambda s: s[0:4] in (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08"),
    "rar" : lambda s: s[0:6] == b"Rar!\x1A\x07",
    "7z"  : lambda s: s[0:6] == b"\x37\x7A\xBC\xAF\x27\x1C",
    "pdf" : lambda s: s[0:5] == b"%PDF-",
    "swf" : lambda s: s[0:3] in (b"CWS", b"FWS"),
    "html": _signature_html,
    "htm" : _signature_html,
    "blend": lambda s: s[0:7] == b"BLENDER",
    # unfortunately the Wavefront .obj format doesn't have a signature,
    # so we check for the existence of Blender's comment
    "obj" : lambda s: s[0:11] == b"# Blender v",
    # Celsys Clip Studio Paint format
    # https://github.com/rasensuihei/cliputils/blob/master/README.md
    "clip": lambda s: s[0:8] == b"CSFCHUNK",
    # check 'bin' files against all other file signatures
    "bin" : lambda s: False,
}

__downloader__ = HttpDownloader

================
File: gallery_dl/downloader/text.py
================
# -*- coding: utf-8 -*-

# Copyright 2014-2019 Mike Fährmann
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 as
# published by the Free Software Foundation.

"""Downloader module for text: URLs"""

from .common import DownloaderBase


class TextDownloader(DownloaderBase):
    scheme = "text"

    def download(self, url, pathfmt):
        if self.part:
            pathfmt.part_enable(self.partdir)
        self.out.start(pathfmt.path)
        with pathfmt.open("wb") as fp:
            fp.write(url.encode()[5:])
        return True


__downloader__ = TextDownloader

================
File: gallery_dl/downloader/ytdl.py
================
# -*- coding: utf-8 -*-

# Copyright 2018-2025 Mike Fährmann
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 as
# published by the Free Software Foundation.

"""Downloader module for URLs requiring youtube-dl support"""

from .common import DownloaderBase
from .. import ytdl, text
from xml.etree import ElementTree
from http.cookiejar import Cookie
import os


class YoutubeDLDownloader(DownloaderBase):
    scheme = "ytdl"

    def __init__(self, job):
        DownloaderBase.__init__(self, job)

        extractor = job.extractor
        self.retries = self.config("retries", extractor._retries)
        self.ytdl_opts = {
            "retries": self.retries+1 if self.retries >= 0 else float("inf"),
            "socket_timeout": self.config("timeout", extractor._timeout),
            "nocheckcertificate": not self.config("verify", extractor._verify),
            "proxy": self.proxies.get("http") if self.proxies else None,
            "ignoreerrors": True,
        }

        self.ytdl_instance = None
        self.rate_dyn = None
        self.forward_cookies = self.config("forward-cookies", True)
        self.progress = self.config("progress", 3.0)
        self.outtmpl = self.config("outtmpl")

    def download(self, url, pathfmt):
        kwdict = pathfmt.kwdict
        tries = 0

        kwdict["_mtime_http"] = None
        if ytdl_instance := kwdict.pop("_ytdl_instance", None):
            # 'ytdl' extractor
            self._prepare(ytdl_instance)
            info_dict = kwdict.pop("_ytdl_info_dict")
        else:
            # other extractors
            ytdl_instance = self.ytdl_instance
            if not ytdl_instance:
                try:
                    module = ytdl.import_module(self.config("module"))
                except (ImportError, SyntaxError) as exc:
                    if exc.__context__:
                        self.log.error("Cannot import yt-dlp or youtube-dl")
                    else:
                        self.log.error("Cannot import module '%s'",
                                       getattr(exc, "name", ""))
                    self.log.traceback(exc)
                    self.download = lambda u, p: False
                    return False

                try:
                    ytdl_version = module.version.__version__
                except Exception:
                    ytdl_version = ""
                self.log.debug("Using %s version %s", module, ytdl_version)

                self.ytdl_instance = ytdl_instance = ytdl.construct_YoutubeDL(
                    module, self, self.ytdl_opts, kwdict.get("_ytdl_params"))
                self.ytdl_pp = module.postprocessor
                if self.outtmpl == "default":
                    self.outtmpl = module.DEFAULT_OUTTMPL
                self._prepare(ytdl_instance)

            if self.forward_cookies:
                self.log.debug("Forwarding cookies to %s",
                               ytdl_instance.__module__)
                set_cookie = ytdl_instance.cookiejar.set_cookie
                for cookie in self.session.cookies:
                    set_cookie(cookie)

            url = url[5:]
            manifest = kwdict.get("_ytdl_manifest")
            while True:
                tries += 1
                self.error = None
                try:
                    if manifest is None:
                        info_dict = self._extract_url(
                            ytdl_instance, url)
                    else:
                        info_dict = self._extract_manifest(
                            ytdl_instance, url, kwdict)
                except Exception as exc:
                    self.log.traceback(exc)
                    cls = exc.__class__
                    if cls.__module__ == "builtins":
                        tries = False
                    msg = f"{cls.__name__}: {exc}"
                else:
                    if self.error is not None:
                        msg = self.error
                    elif not info_dict:
                        msg = "Empty 'info_dict' data"
                    else:
                        break

                if tries:
                    self.log.error("%s (%s/%s)", msg, tries, self.retries+1)
                else:
                    self.log.error(msg)
                    return False
                if tries > self.retries:
                    return False

        if extra := kwdict.get("_ytdl_extra"):
            info_dict.update(extra)

        while True:
            tries += 1
            self.error = None
            try:
                if "entries" in info_dict:
                    success = self._download_playlist(
                        ytdl_instance, pathfmt, info_dict)
                else:
                    success = self._download_video(
                        ytdl_instance, pathfmt, info_dict)
            except Exception as exc:
                self.log.traceback(exc)
                cls = exc.__class__
                if cls.__module__ == "builtins":
                    tries = False
                msg = f"{cls.__name__}: {exc}"
            else:
                if self.error is not None:
                    msg = self.error
                elif not success:
                    msg = "Error"
                else:
                    break

            if tries:
                self.log.error("%s (%s/%s)", msg, tries, self.retries+1)
            else:
                self.log.error(msg)
                return False
            if tries > self.retries:
                return False
        return True

    def _extract_url(self, ytdl, url):
        return ytdl.extract_info(url, download=False)

    def _extract_manifest(self, ytdl, url, kwdict):
        extr = ytdl.get_info_extractor("Generic")
        video_id = extr._generic_id(url)

        if cookies := kwdict.get("_ytdl_manifest_cookies"):
            if isinstance(cookies, dict):
                cookies = cookies.items()
            set_cookie = ytdl.cookiejar.set_cookie
            for name, value in cookies:
                set_cookie(Cookie(
                    0, name, value, None, False,
                    "", False, False, "/", False,
                    False, None, False, None, None, {},
                ))

        type = kwdict["_ytdl_manifest"]
        data = kwdict.get("_ytdl_manifest_data")
        remux = kwdict.get("_ytdl_manifest_remux")
        headers = kwdict.get("_ytdl_manifest_headers")
        if type == "hls":
            ext = "ytdl" if remux else "mp4"
            protocol = "m3u8_native"

            if data is None:
                try:
                    fmts, subs = extr._extract_m3u8_formats_and_subtitles(
                        url, video_id, ext, protocol, headers=headers)
                except AttributeError:
                    fmts = extr._extract_m3u8_formats(
                        url, video_id, ext, protocol, headers=headers)
                    subs = None
            else:
                try:
                    fmts, subs = extr._parse_m3u8_formats_and_subtitles(
                        data, url, ext, protocol, headers=headers)
                except AttributeError:
                    fmts = extr._parse_m3u8_formats(
                        data, url, ext, protocol, headers=headers)
                    subs = None

        elif type == "dash":
            if data is None:
                try:
                    fmts, subs = extr._extract_mpd_formats_and_subtitles(
                        url, video_id, headers=headers)
                except AttributeError:
                    fmts = extr._extract_mpd_formats(
                        url, video_id, headers=headers)
                    subs = None
            else:
                if isinstance(data, str):
                    data = ElementTree.fromstring(data)
                try:
                    fmts, subs = extr._parse_mpd_formats_and_subtitles(
                        data, mpd_id="dash")
                except AttributeError:
                    fmts = extr._parse_mpd_formats(
                        data, mpd_id="dash")
                    subs = None

        else:
            raise ValueError(f"Unsupported manifest type '{type}'")

        if headers:
            for fmt in fmts:
                fmt["http_headers"] = headers

        info_dict = {
            "extractor": "",
            "id"       : video_id,
            "title"    : video_id,
            "formats"  : fmts,
            "subtitles": subs,
        }
        info_dict = ytdl.process_ie_result(info_dict, download=False)

        if remux:
            info_dict["__postprocessors"] = [
                self.ytdl_pp.FFmpegVideoRemuxerPP(self.ytdl_instance, remux)]

        return info_dict

    def _download_video(self, ytdl_instance, pathfmt, info_dict):
        if "url" in info_dict:
            if "filename" in pathfmt.kwdict:
                pathfmt.kwdict["extension"] = \
                    text.ext_from_url(info_dict["url"])
            else:
                text.nameext_from_url(info_dict["url"], pathfmt.kwdict)

        formats = info_dict.get("requested_formats")
        if formats and not compatible_formats(formats):
            info_dict["ext"] = "mkv"
        elif "ext" not in info_dict:
            try:
                info_dict["ext"] = info_dict["formats"][0]["ext"]
            except LookupError:
                info_dict["ext"] = "mp4"

        if self.outtmpl:
            self._set_outtmpl(ytdl_instance, self.outtmpl)
            pathfmt.filename = filename = \
                ytdl_instance.prepare_filename(info_dict)
            pathfmt.extension = info_dict["ext"]
            pathfmt.path = pathfmt.directory + filename
            pathfmt.realpath = pathfmt.temppath = (
                pathfmt.realdirectory + filename)
        elif info_dict["ext"] != "ytdl":
            pathfmt.set_extension(info_dict["ext"])
            pathfmt.build_path()

        if pathfmt.exists():
            pathfmt.temppath = ""
            return True

        if self.rate_dyn is not None:
            # static ratelimits are set in ytdl.construct_YoutubeDL
            ytdl_instance.params["ratelimit"] = self.rate_dyn()

        self.out.start(pathfmt.path)
        if self.part:
            pathfmt.kwdict["extension"] = pathfmt.prefix
            filename = pathfmt.build_filename(pathfmt.kwdict)
            pathfmt.kwdict["extension"] = info_dict["ext"]
            if self.partdir:
                path = os.path.join(self.partdir, filename)
            else:
                path = pathfmt.realdirectory + filename
            path = path.replace("%", "%%") + "%(ext)s"
        else:
            path = pathfmt.realpath.replace("%", "%%")

        self._set_outtmpl(ytdl_instance, path)
        ytdl_instance.process_info(info_dict)
        pathfmt.temppath = info_dict.get("filepath") or info_dict["_filename"]
        return True

    def _download_playlist(self, ytdl_instance, pathfmt, info_dict):
        pathfmt.kwdict["extension"] = pathfmt.prefix
        filename = pathfmt.build_filename(pathfmt.kwdict)
        pathfmt.kwdict["extension"] = pathfmt.extension
        path = pathfmt.realdirectory + filename
        path = path.replace("%", "%%") + "%(playlist_index)s.%(ext)s"
        self._set_outtmpl(ytdl_instance, path)

        status = False
        for entry in info_dict["entries"]:
            if not entry:
                continue
            if self.rate_dyn is not None:
                ytdl_instance.params["ratelimit"] = self.rate_dyn()
            try:
                ytdl_instance.process_info(entry)
                status = True
            except Exception as exc:
                self.log.traceback(exc)
                self.log.error("%s: %s", exc.__class__.__name__, exc)
        return status

    def _prepare(self, ytdl_instance):
        if "__gdl_initialize" not in ytdl_instance.params:
            return

        del ytdl_instance.params["__gdl_initialize"]
        if self.progress is not None:
            ytdl_instance.add_progress_hook(self._progress_hook)
        if rlf := ytdl_instance.params.pop("__gdl_ratelimit_func", False):
            self.rate_dyn = rlf
        ytdl_instance.params["logger"] = LoggerAdapter(self, ytdl_instance)

    def _progress_hook(self, info):
        if info["status"] == "downloading" and \
                info["elapsed"] >= self.progress:
            total = info.get("total_bytes") or info.get("total_bytes_estimate")
            speed = info.get("speed")
            self.out.progress(
                None if total is None else int(total),
                info["downloaded_bytes"],
                int(speed) if speed else 0,
            )

    def _set_outtmpl(self, ytdl_instance, outtmpl):
        try:
            ytdl_instance._parse_outtmpl
        except AttributeError:
            try:
                ytdl_instance.outtmpl_dict["default"] = outtmpl
            except AttributeError:
                ytdl_instance.params["outtmpl"] = outtmpl
        else:
            ytdl_instance.params["outtmpl"] = {"default": outtmpl}


class LoggerAdapter():
    __slots__ = ("obj", "log")

    def __init__(self, obj, ytdl_instance):
        self.obj = obj
        self.log = ytdl_instance.params.get("logger")

    def debug(self, msg):
        if self.log is not None:
            if msg[0] == "[":
                msg = msg[msg.find("]")+2:]
            self.log.debug(msg)

    def warning(self, msg):
        if self.log is not None:
            if "WARNING:" in msg:
                msg = msg[msg.find(" ")+1:]
            self.log.warning(msg)

    def error(self, msg):
        if "ERROR:" in msg:
            msg = msg[msg.find(" ")+1:]
        self.obj.error = msg


def compatible_formats(formats):
    """Returns True if 'formats' are compatible for merge"""
    video_ext = formats[0].get("ext")
    audio_ext = formats[1].get("ext")

    if video_ext == "webm" and audio_ext == "webm":
        return True

    exts = ("mp3", "mp4", "m4a", "m4p", "m4b", "m4r", "m4v", "ismv", "isma")
    return video_ext in exts and audio_ext in exts


__downloader__ = YoutubeDLDownloader

================
File: gallery_dl/extractor/generic.py
================
# -*- coding: utf-8 -*-

# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 as
# published by the Free Software Foundation.

"""Generic information extractor"""

from .common import Extractor, Message
from .. import config, text
import os.path


class GenericExtractor(Extractor):
    """Extractor for images in a generic web page."""
    category = "generic"
    directory_fmt = ("{category}", "{subcategory}", "{path}")
    archive_fmt = "{imageurl}"

    # By default, the generic extractor is disabled
    # and the "g(eneric):" prefix in url is required.
    # If the extractor is enabled, make the prefix optional
    pattern = r"(?i)(?P<generic>g(?:eneric)?:)"
    if config.get(("extractor", "generic"), "enabled"):
        pattern += r"?"

    # The generic extractor pattern should match (almost) any valid url
    # Based on: https://tools.ietf.org/html/rfc3986#appendix-B
    pattern += (
        r"(?P<scheme>https?://)?"          # optional http(s) scheme
        r"(?P<domain>[-\w\.]+)"            # required domain
        r"(?P<path>/[^?#]*)?"              # optional path
        r"(?:\?(?P<query>[^#]*))?"         # optional query
        r"(?:\#(?P<fragment>.*))?"         # optional fragment
    )
    example = "generic:https://www.nongnu.org/lzip/"

    def __init__(self, match):
        self.subcategory = match['domain']
        Extractor.__init__(self, match)

        # Strip the "g(eneric):" prefix
        # and inform about "forced" or "fallback" mode
        if match['generic']:
            self.url = match[0].partition(":")[2]
        else:
            self.log.info("Falling back on generic information extractor.")
            self.url = match[0]

        # Make sure we have a scheme, or use https
        if match['scheme']:
            self.scheme = match['scheme']
        else:
            self.scheme = 'https://'
            self.url = text.ensure_http_scheme(self.url, self.scheme)

        self.path = match['path']

        # Used to resolve relative image urls
        self.root = self.scheme + match['domain']

    def items(self):
        """Get page, extract metadata & images, yield them in suitable messages

        Adapted from common.GalleryExtractor.items()

        """
        page = self.request(self.url).text
        data = self.metadata(page)
        imgs = self.images(page)

        try:
            data["count"] = len(imgs)
        except TypeError:
            pass
        images = enumerate(imgs, 1)

        yield Message.Directory, "", data

        for data["num"], (url, imgdata) in images:
            if imgdata:
                data.update(imgdata)
                if "extension" not in imgdata:
                    text.nameext_from_url(url, data)
            else:
                text.nameext_from_url(url, data)
            yield Message.Url, url, data

    def metadata(self, page):
        """Extract generic webpage metadata, return them in a dict."""
        data = {
            "title"         : text.extr(
                page, "<title>", "</title>"),
            "description"   : text.extr(
                page, '<meta name="description" content="', '"'),
            "keywords"      : text.extr(
                page, '<meta name="keywords" content="', '"'),
            "language"      : text.extr(
                page, '<meta name="language" content="', '"'),
            "name"          : text.extr(
                page, '<meta itemprop="name" content="', '"'),
            "copyright"     : text.extr(
                page, '<meta name="copyright" content="', '"'),
            "og_site"       : text.extr(
                page, '<meta property="og:site" content="', '"'),
            "og_site_name"  : text.extr(
                page, '<meta property="og:site_name" content="', '"'),
            "og_title"      : text.extr(
                page, '<meta property="og:title" content="', '"'),
            "og_description": text.extr(
                page, '<meta property="og:description" content="', '"'),

        }

        data = {k: text.unescape(v) for k, v in data.items() if v}
        data["path"] = self.path.replace("/", "")
        data["pageurl"] = self.url

        return data

    def images(self, page):
        """Extract image urls, return a list of (image url, metadata) tuples.

        The extractor aims at finding as many _likely_ image urls as possible,
        using two strategies (see below); since these often overlap, any
        duplicate urls will be removed at the end of the process.

        Note: since we are using re.findall() (see below), it's essential that
        the following patterns contain 0 or at most 1 capturing group, so that
        re.findall() return a list of urls (instead of a list of tuples of
        matching groups). All other groups used in the pattern should be
        non-capturing (?:...).

        1: Look in src/srcset attributes of img/video/source elements

        See:
        https://www.w3schools.com/tags/att_src.asp
        https://www.w3schools.com/tags/att_source_srcset.asp

        We allow both absolute and relative urls here.

        Note that srcset attributes often contain multiple space separated
        image urls; this pattern matches only the first url; remaining urls
        will be matched by the "imageurl_pattern_ext" pattern below.
        """

        imageurl_pattern_src = (
            r"(?i)"
            r"<(?:img|video|source)\s[^>]*"    # <img>, <video> or <source>
            r"src(?:set)?=[\"']?"              # src or srcset attributes
            r"(?P<URL>[^\"'\s>]+)"             # url
        )

        """
        2: Look anywhere for urls containing common image/video extensions

        The list of allowed extensions is borrowed from the directlink.py
        extractor; other could be added, see
        https://en.wikipedia.org/wiki/List_of_file_formats

        Compared to the "pattern" class variable, here we must exclude also
        other special characters (space, ", ', <, >), since we are looking for
        urls in html tags.
        """

        imageurl_pattern_ext = (
            r"(?i)"
            r"(?:[^?&#\"'>\s]+)"           # anything until dot+extension
                                           # dot + image/video extensions
            r"\.(?:jpe?g|jpe|png|gif|web[mp]|mp4|mkv|og[gmv]|opus)"
            r"(?:[^\"'<>\s]*)?"            # optional query and fragment
        )

        imageurls_src = text.re(imageurl_pattern_src).findall(page)
        imageurls_ext = text.re(imageurl_pattern_ext).findall(page)
        imageurls = imageurls_src + imageurls_ext

        # Resolve relative urls
        #
        # Image urls catched so far may be relative, so we must resolve them
        # by prepending a suitable base url.
        #
        # If the page contains a <base> element, use it as base url
        basematch = text.re(
            r"(?i)(?:<base\s.*?href=[\"']?)(?P<url>[^\"' >]+)").search(page)
        if basematch:
            self.baseurl = basematch['url'].rstrip('/')
        # Otherwise, extract the base url from self.url
        else:
            if self.url.endswith("/"):
                self.baseurl = self.url.rstrip('/')
            else:
                self.baseurl = os.path.dirname(self.url)

        # Build the list of absolute image urls
        absimageurls = []
        for u in imageurls:
            # Absolute urls are taken as-is
            if u.startswith('http'):
                absimageurls.append(u)
            # // relative urls are prefixed with current scheme
            elif u.startswith('//'):
                absimageurls.append(self.scheme + u.lstrip('/'))
            # / relative urls are prefixed with current scheme+domain
            elif u.startswith('/'):
                absimageurls.append(self.root + u)
            # other relative urls are prefixed with baseurl
            else:
                absimageurls.append(self.baseurl + '/' + u)

        # Remove duplicates
        absimageurls = dict.fromkeys(absimageurls)

        # Create the image metadata dict and add imageurl to it
        # (image filename and extension are added by items())
        images = [(u, {'imageurl': u}) for u in absimageurls]

        return images

================
File: gallery_dl/extractor/message.py
================
# -*- coding: utf-8 -*-

# Copyright 2015-2025 Mike Fährmann
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 as
# published by the Free Software Foundation.


class Message():
    """Enum for message identifiers

    Extractors yield their results as message-tuples, where the first element
    is one of the following identifiers. This message-identifier determines
    the type and meaning of the other elements in such a tuple.

    - Message.Version:  # obsolete
      - Message protocol version (currently always '1')
      - 2nd element specifies the version of all following messages as integer

    - Message.Directory:
      - Sets the target directory for all following images
      - 2nd element is unused
      - 3rd element is a dictionary containing general metadata

    - Message.Url:
      - Image URL and its metadata
      - 2nd element is the URL as a string
      - 3rd element is a dictionary with image-specific metadata

    - Message.Headers:  # obsolete
      - HTTP headers to use while downloading
      - 2nd element is a dictionary with header-name and -value pairs

    - Message.Cookies:  # obsolete
      - Cookies to use while downloading
      - 2nd element is a dictionary with cookie-name and -value pairs

    - Message.Queue:
      - (External) URL that should be handled by another extractor
      - 2nd element is the (external) URL as a string
      - 3rd element is a dictionary containing URL-specific metadata

    - Message.Urllist:  # obsolete
      - Same as Message.Url, but its 2nd element is a list of multiple URLs
      - The additional URLs serve as a fallback if the primary one fails
    """

    #  Version = 1
    Directory = 2
    Url = 3
    #  Headers = 4
    #  Cookies = 5
    Queue = 6
    #  Urllist = 7
    #  Metadata = 8

================
File: gallery_dl/extractor/noop.py
================
# -*- coding: utf-8 -*-

# Copyright 2024 Mike Fährmann
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 as
# published by the Free Software Foundation.

"""noop extractor"""

from .common import Extractor


class NoopExtractor(Extractor):
    category = "noop"
    pattern = r"(?i)noo?p$"
    example = "noop"

    def items(self):
        # Save cookies manually, since it happens automatically only after
        # extended extractor initialization, i.e. Message.Directory, which
        # itself might cause some unintended effects.
        if self.cookies:
            self.cookies_store()
        return iter(((-1, "", None),))

================
File: gallery_dl/extractor/nozomi.py
================
# -*- coding: utf-8 -*-

# Copyright 2019-2025 Mike Fährmann
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 as
# published by the Free Software Foundation.

"""Extractors for https://nozomi.la/"""

from .common import Extractor, Message
from .. import text, dt


def decode_nozomi(n):
    for i in range(0, len(n), 4):
        yield (n[i] << 24) + (n[i+1] << 16) + (n[i+2] << 8) + n[i+3]


class NozomiExtractor(Extractor):
    """Base class for nozomi extractors"""
    category = "nozomi"
    root = "https://nozomi.la"
    domain = "gold-usergeneratedcontent.net"
    filename_fmt = "{postid} {dataid}.{extension}"
    archive_fmt = "{dataid}"

    def _init(self):
        self.session.headers["Origin"] = self.root

    def items(self):
        data = self.metadata()

        for post_id in map(str, self.posts()):
            url = (f"https://j.{self.domain}/post"
                   f"/{post_id[-1]}/{post_id[-3:-1]}/{post_id}.json")
            response = self.request(url, fatal=False)

            if response.status_code >= 400:
                self.log.warning(
                    "Skipping post %s ('%s %s')",
                    post_id, response.status_code, response.reason)
                continue

            post = response.json()
            post["tags"] = self._list(post.get("general"))
            post["artist"] = self._list(post.get("artist"))
            post["copyright"] = self._list(post.get("copyright"))
            post["character"] = self._list(post.get("character"))

            try:
                post["date"] = dt.parse_iso(post["date"] + ":00")
            except Exception:
                post["date"] = dt.NONE

            post.update(data)

            images = post["imageurls"]
            for key in ("general", "imageurl", "imageurls"):
                if key in post:
                    del post[key]

            yield Message.Directory, "", post
            for post["num"], image in enumerate(images, 1):
                post["filename"] = post["dataid"] = did = image["dataid"]
                post["is_video"] = video = \
                    True if image.get("is_video") else False

                ext = image["type"]
                if video:
                    subdomain = "v"
                elif ext == "gif":
                    subdomain = "g"
                else:
                    subdomain = "w"
                    ext = "webp"

                post["extension"] = ext
                post["url"] = url = (f"https://{subdomain}.{self.domain}"
                                     f"/{did[-1]}/{did[-3:-1]}/{did}.{ext}")
                yield Message.Url, url, post

    def posts(self):
        url = "https://n.nozomi.la" + self.nozomi
        offset = (text.parse_int(self.pnum, 1) - 1) * 256

        while True:
            headers = {"Range": f"bytes={offset}-{offset + 255}"}
            response = self.request(url, headers=headers)
            yield from decode_nozomi(response.content)

            offset += 256
            cr = response.headers.get("Content-Range", "").rpartition("/")[2]
            if text.parse_int(cr, offset) <= offset:
                return

    def metadata(self):
        return {}

    def _list(self, src):
        return [x["tagname_display"] for x in src] if src else ()


class NozomiPostExtractor(NozomiExtractor):
    """Extractor for individual posts on nozomi.la"""
    subcategory = "post"
    pattern = r"(?:https?://)?nozomi\.la/post/(\d+)"
    example = "https://nozomi.la/post/12345.html"

    def __init__(self, match):
        NozomiExtractor.__init__(self, match)
        self.post_id = match[1]

    def posts(self):
        return (self.post_id,)


class NozomiIndexExtractor(NozomiExtractor):
    """Extractor for the nozomi.la index"""
    subcategory = "index"
    pattern = (r"(?:https?://)?nozomi\.la/"
               r"(?:(index(?:-Popular)?)-(\d+)\.html)?(?:$|#|\?)")
    example = "https://nozomi.la/index-1.html"

    def __init__(self, match):
        NozomiExtractor.__init__(self, match)
        index, self.pnum = match.groups()
        self.nozomi = f"/{index or 'index'}.nozomi"


class NozomiTagExtractor(NozomiExtractor):
    """Extractor for posts from tag searches on nozomi.la"""
    subcategory = "tag"
    directory_fmt = ("{category}", "{search_tags}")
    archive_fmt = "t_{search_tags}_{dataid}"
    pattern = r"(?:https?://)?nozomi\.la/tag/([^/?#]+)-(\d+)\."
    example = "https://nozomi.la/tag/TAG-1.html"

    def __init__(self, match):
        NozomiExtractor.__init__(self, match)
        tags, self.pnum = match.groups()
        self.tags = text.unquote(tags)
        self.nozomi = f"/nozomi/{self.tags}.nozomi"

    def metadata(self):
        return {"search_tags": self.tags}


class NozomiSearchExtractor(NozomiExtractor):
    """Extractor for search results on nozomi.la"""
    subcategory = "search"
    directory_fmt = ("{category}", "{search_tags:J }")
    archive_fmt = "t_{search_tags}_{dataid}"
    pattern = r"(?:https?://)?nozomi\.la/search\.html\?q=([^&#]+)"
    example = "https://nozomi.la/search.html?q=QUERY"

    def __init__(self, match):
        NozomiExtractor.__init__(self, match)
        self.tags = text.unquote(match[1]).split()

    def metadata(self):
        return {"search_tags": self.tags}

    def posts(self):
        result = None
        positive = []
        negative = []

        def nozomi(path):
            url = f"https://j.{self.domain}/{path}.nozomi"
            return decode_nozomi(self.request(url).content)

        for tag in self.tags:
            (negative if tag[0] == "-" else positive).append(
                text.quote(tag.replace("/", "")))

        for tag in positive:
            ids = nozomi("nozomi/" + tag)
            if result is None:
                result = set(ids)
            else:
                result.intersection_update(ids)

        if result is None:
            result = set(nozomi("index"))
        for tag in negative:
            result.difference_update(nozomi("nozomi/" + tag[1:]))

        return sorted(result, reverse=True) if result else ()

================
File: gallery_dl/postprocessor/__init__.py
================
# -*- coding: utf-8 -*-

# Copyright 2018-2025 Mike Fährmann
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 as
# published by the Free Software Foundation.

"""Post-processing modules"""

modules = [
    "classify",
    "compare",
    "directory",
    "exec",
    "hash",
    "metadata",
    "mtime",
    "python",
    "rename",
    "ugoira",
    "zip",
]


def find(name):
    """Return a postprocessor class with the given name"""
    try:
        return _cache[name]
    except KeyError:
        pass

    cls = None
    if name in modules:  # prevent unwanted imports
        try:
            module = __import__(name, globals(), None, None, 1)
        except ImportError:
            pass
        else:
            cls = module.__postprocessor__
    _cache[name] = cls
    return cls


# --------------------------------------------------------------------
# internals

_cache = {}

================
File: gallery_dl/postprocessor/classify.py
================
# -*- coding: utf-8 -*-

# Copyright 2018-2024 Mike Fährmann
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 as
# published by the Free Software Foundation.

"""Categorize files by file extension"""

from .common import PostProcessor
import os


class ClassifyPP(PostProcessor):

    DEFAULT_MAPPING = {
        "Pictures" : ("jpg", "jpeg", "png", "gif", "bmp", "svg", "webp",
                      "avif", "heic", "heif", "ico", "psd"),
        "Video"    : ("flv", "ogv", "avi", "mp4", "mpg", "mpeg", "3gp", "mkv",
                      "webm", "vob", "wmv", "m4v", "mov"),
        "Music"    : ("mp3", "aac", "flac", "ogg", "wma", "m4a", "wav"),
        "Archives" : ("zip", "rar", "7z", "tar", "gz", "bz2"),
        "Documents": ("txt", "pdf"),
    }

    def __init__(self, job, options):
        PostProcessor.__init__(self, job)
        self.directory = self.realdirectory = ""

        mapping = options.get("mapping", self.DEFAULT_MAPPING)
        self.mapping = {
            ext: directory
            for directory, exts in mapping.items()
            for ext in exts
        }

        job.register_hooks({
            "post"   : self.initialize,
            "prepare": self.prepare,
        }, options)

    def initialize(self, pathfmt):
        # store base directory paths
        self.directory = pathfmt.directory
        self.realdirectory = pathfmt.realdirectory

    def prepare(self, pathfmt):
        # extend directory paths depending on file extension
        ext = pathfmt.extension
        if ext in self.mapping:
            extra = self.mapping[ext] + os.sep
            pathfmt.directory = self.directory + extra
            pathfmt.realdirectory = self.realdirectory + extra


__postprocessor__ = ClassifyPP

================
File: gallery_dl/postprocessor/common.py
================
# -*- coding: utf-8 -*-

# Copyright 2018-2025 Mike Fährmann
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 as
# published by the Free Software Foundation.

"""Common classes and constants used by postprocessor modules."""

from .. import archive


class PostProcessor():
    """Base class for postprocessors"""

    def __init__(self, job):
        self.name = self.__class__.__name__[:-2].lower()
        self.log = job.get_logger("postprocessor." + self.name)

    def __repr__(self):
        return self.__class__.__name__

    def _archive_init(self, job, options, prefix=None):
        if archive_path := options.get("archive"):
            extr = job.extractor

            archive_table = options.get("archive-table")
            archive_prefix = options.get("archive-prefix")
            if archive_prefix is None:
                archive_prefix = extr.category if archive_table is None else ""

            archive_format = options.get("archive-format")
            if archive_format is None:
                if prefix is None:
                    prefix = "_" + self.name.upper() + "_"
                archive_format = prefix + extr.archive_fmt

            try:
                self.archive = archive.connect(
                    archive_path,
                    archive_prefix,
                    archive_format,
                    archive_table,
                    "file",
                    options.get("archive-pragma"),
                    job.pathfmt.kwdict,
                    "_archive_" + self.name,
                )
            except Exception as exc:
                self.log.warning(
                    "Failed to open %s archive at '%s' (%s: %s)",
                    self.name, archive_path, exc.__class__.__name__, exc)
            else:
                self.log.debug(
                    "Using %s archive '%s'", self.name, archive_path)
                return True

        self.archive = None
        return False

    def _archive_register(self, job):
        job.register_hooks({"finalize": self._archive_close})

    def _archive_close(self, _):
        self.archive.close()

================
File: gallery_dl/postprocessor/compare.py
================
# -*- coding: utf-8 -*-

# Copyright 2020-2025 Mike Fährmann
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 as
# published by the Free Software Foundation.

"""Compare versions of the same file and replace/enumerate them on mismatch"""

from .common import PostProcessor
from .. import text, util, output, exception
import os


class ComparePP(PostProcessor):

    def __init__(self, job, options):
        PostProcessor.__init__(self, job)
        if options.get("shallow"):
            self._compare = self._compare_size
        self._equal_exc = self._equal_cnt = 0

        if equal := options.get("equal"):
            equal, _, emax = equal.partition(":")
            self._equal_max = text.parse_int(emax)
            if equal == "abort":
                self._equal_exc = exception.StopExtraction
            elif equal == "terminate":
                self._equal_exc = exception.TerminateExtraction
            elif equal == "exit":
                self._equal_exc = SystemExit

        job.register_hooks({"file": (
            self.enumerate
            if options.get("action") == "enumerate" else
            self.replace
        )}, options)

    def replace(self, pathfmt):
        try:
            if self._compare(pathfmt.realpath, pathfmt.temppath):
                return self._equal(pathfmt)
        except OSError:
            pass
        self._equal_cnt = 0

    def enumerate(self, pathfmt):
        num = 1
        try:
            while not self._compare(pathfmt.realpath, pathfmt.temppath):
                pathfmt.prefix = prefix = format(num) + "."
                pathfmt.kwdict["extension"] = prefix + pathfmt.extension
                pathfmt.build_path()
                num += 1
            return self._equal(pathfmt)
        except OSError:
            pass
        self._equal_cnt = 0

    def _compare(self, f1, f2):
        return self._compare_size(f1, f2) and self._compare_content(f1, f2)

    def _compare_size(self, f1, f2):
        return os.stat(f1).st_size == os.stat(f2).st_size

    def _compare_content(self, f1, f2):
        size = 16384
        with open(f1, "rb") as fp1, open(f2, "rb") as fp2:
            while True:
                buf1 = fp1.read(size)
                buf2 = fp2.read(size)
                if buf1 != buf2:
                    return False
                if not buf1:
                    return True

    def _equal(self, pathfmt):
        if self._equal_exc:
            self._equal_cnt += 1
            if self._equal_cnt >= self._equal_max:
                util.remove_file(pathfmt.temppath)
                output.stderr_write("\n")
                raise self._equal_exc()
        pathfmt.delete = True


__postprocessor__ = ComparePP

================
File: gallery_dl/postprocessor/directory.py
================
# -*- coding: utf-8 -*-

# Copyright 2025 Mike Fährmann
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 as
# published by the Free Software Foundation.

"""Trigger directory format string evaluation"""

from .common import PostProcessor


class DirectoryPP(PostProcessor):

    def __init__(self, job, options):
        PostProcessor.__init__(self, job)

        events = options.get("event")
        if events is None:
            events = ("prepare",)
        elif isinstance(events, str):
            events = events.split(",")
        job.register_hooks({event: self.run for event in events}, options)

    def run(self, pathfmt):
        pathfmt.set_directory(pathfmt.kwdict)


__postprocessor__ = DirectoryPP

================
File: gallery_dl/postprocessor/exec.py
================
# -*- coding: utf-8 -*-

# Copyright 2018-2023 Mike Fährmann
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 as
# published by the Free Software Foundation.

"""Execute processes"""

from .common import PostProcessor
from .. import util, formatter
import subprocess
import os


if util.WINDOWS:
    def quote(s):
        s = s.replace('"', '\\"')
        return f'"{s}"'
else:
    from shlex import quote


def trim(args):
    return (args.partition(" ") if isinstance(args, str) else args)[0]


class ExecPP(PostProcessor):

    def __init__(self, job, options):
        PostProcessor.__init__(self, job)

        if cmds := options.get("commands"):
            self.cmds = [self._prepare_cmd(c) for c in cmds]
            execute = self.exec_many
        else:
            execute, self.args = self._prepare_cmd(options["command"])
            if options.get("async", False):
                self._exec = self._popen

        self.verbose = options.get("verbose", True)
        self.session = False
        self.creationflags = 0
        if options.get("session"):
            if util.WINDOWS:
                self.creationflags = subprocess.CREATE_NEW_PROCESS_GROUP
            else:
                self.session = True

        events = options.get("event")
        if events is None:
            events = ("after",)
        elif isinstance(events, str):
            events = events.split(",")
        job.register_hooks({event: execute for event in events}, options)

        if self._archive_init(job, options):
            self._archive_register(job)

    def _prepare_cmd(self, cmd):
        if isinstance(cmd, str):
            self._sub = util.re(
                r"\{(_directory|_filename|_(?:temp)?path|)\}").sub
            return self.exec_string, cmd
        else:
            return self.exec_list, [formatter.parse(arg) for arg in cmd]

    def exec_list(self, pathfmt):
        archive = self.archive
        kwdict = pathfmt.kwdict

        if archive and archive.check(kwdict):
            return

        kwdict["_directory"] = pathfmt.realdirectory
        kwdict["_filename"] = pathfmt.filename
        kwdict["_temppath"] = pathfmt.temppath
        kwdict["_path"] = pathfmt.realpath

        args = [arg.format_map(kwdict) for arg in self.args]
        args[0] = os.path.expanduser(args[0])
        retcode = self._exec(args, False)

        if archive:
            archive.add(kwdict)
        return retcode

    def exec_string(self, pathfmt):
        archive = self.archive
        if archive and archive.check(pathfmt.kwdict):
            return

        self.pathfmt = pathfmt
        args = self._sub(self._replace, self.args)
        retcode = self._exec(args, True)

        if archive:
            archive.add(pathfmt.kwdict)
        return retcode

    def exec_many(self, pathfmt):
        if archive := self.archive:
            if archive.check(pathfmt.kwdict):
                return
            self.archive = False

        retcode = 0
        for execute, args in self.cmds:
            self.args = args
            if retcode := execute(pathfmt):
                # non-zero exit status
                break

        if archive:
            self.archive = archive
            archive.add(pathfmt.kwdict)
        return retcode

    def _exec(self, args, shell):
        if retcode := self._popen(args, shell).wait():
            self.log.warning("'%s' returned with non-zero exit status (%d)",
                             args if self.verbose else trim(args), retcode)
        return retcode

    def _popen(self, args, shell):
        self.log.debug("Running '%s'", args if self.verbose else trim(args))
        return util.Popen(
            args,
            shell=shell,
            creationflags=self.creationflags,
            start_new_session=self.session,
        )

    def _replace(self, match):
        name = match[1]
        if name == "_directory":
            return quote(self.pathfmt.realdirectory)
        if name == "_filename":
            return quote(self.pathfmt.filename)
        if name == "_temppath":
            return quote(self.pathfmt.temppath)
        return quote(self.pathfmt.realpath)


__postprocessor__ = ExecPP

================
File: gallery_dl/postprocessor/hash.py
================
# -*- coding: utf-8 -*-

# Copyright 2024 Mike Fährmann
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 as
# published by the Free Software Foundation.

"""Compute file hash digests"""

from .common import PostProcessor
import hashlib


class HashPP(PostProcessor):

    def __init__(self, job, options):
        PostProcessor.__init__(self, job)

        self.chunk_size = options.get("chunk-size", 32768)
        self.filename = options.get("filename")

        hashes = options.get("hashes")
        if isinstance(hashes, dict):
            self.hashes = list(hashes.items())
        elif isinstance(hashes, str):
            self.hashes = []
            for h in hashes.split(","):
                name, sep, key = h.partition(":")
                self.hashes.append((key if sep else name, name))
        elif hashes:
            self.hashes = hashes
        else:
            self.hashes = (("md5", "md5"), ("sha1", "sha1"))

        events = options.get("event")
        if events is None:
            events = ("file",)
        elif isinstance(events, str):
            events = events.split(",")
        job.register_hooks({event: self.run for event in events}, options)

    def run(self, pathfmt):
        hashes = [
            (key, hashlib.new(name))
            for key, name in self.hashes
        ]

        size = self.chunk_size
        with self._open(pathfmt) as fp:
            while True:
                data = fp.read(size)
                if not data:
                    break
                for _, h in hashes:
                    h.update(data)

        for key, h in hashes:
            pathfmt.kwdict[key] = h.hexdigest()

        if self.filename:
            pathfmt.build_path()

    def _open(self, pathfmt):
        try:
            return open(pathfmt.temppath, "rb")
        except OSError:
            return open(pathfmt.realpath, "rb")


__postprocessor__ = HashPP

================
File: gallery_dl/postprocessor/metadata.py
================
# -*- coding: utf-8 -*-

# Copyright 2019-2025 Mike Fährmann
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 as
# published by the Free Software Foundation.

"""Write metadata to external files"""

from .common import PostProcessor
from .. import util, formatter
import json
import sys
import os


class MetadataPP(PostProcessor):

    def __init__(self, job, options):
        PostProcessor.__init__(self, job)

        mode = options.get("mode")
        cfmt = options.get("content-format") or options.get("format")
        omode = "w"
        filename = None

        if mode == "tags":
            self.write = self._write_tags
            ext = "txt"
        elif mode == "modify":
            self.run = self._run_modify
            self.fields = {
                name: formatter.parse(value, None, util.identity).format_map
                for name, value in options.get("fields").items()
            }
            ext = None
        elif mode == "delete":
            self.run = self._run_delete
            self.fields = options.get("fields")
            ext = None
        elif mode == "custom" or not mode and cfmt:
            self.write = self._write_custom
            if isinstance(cfmt, list):
                cfmt = "\n".join(cfmt) + "\n"
            self._content_fmt = formatter.parse(cfmt).format_map
            ext = "txt"
        elif mode == "print":
            nl = "\n"
            if isinstance(cfmt, list):
                cfmt = f"{nl.join(cfmt)}{nl}"
            if cfmt[-1] != nl and (cfmt[0] != "\f" or cfmt[1] == "F"):
                cfmt = f"{cfmt}{nl}"
            self.write = self._write_custom
            self._content_fmt = formatter.parse(cfmt).format_map
            filename = "-"
        elif mode == "jsonl":
            self.write = self._write_json
            self._json_encode = self._make_encoder(options).encode
            omode = "a"
            filename = "data.jsonl"
        else:
            self.write = self._write_json
            self._json_encode = self._make_encoder(options, 4).encode
            ext = "json"

        if base_directory := options.get("base-directory"):
            if base_directory is True:
                self._base = lambda p: p.basedirectory
            else:
                sep = os.sep
                altsep = os.altsep
                base_directory = util.expand_path(base_directory)
                if altsep and altsep in base_directory:
                    base_directory = base_directory.replace(altsep, sep)
                if base_directory[-1] != sep:
                    base_directory += sep
                self._base = lambda p: base_directory

        directory = options.get("directory")
        if isinstance(directory, list):
            self._directory = self._directory_format
            self._directory_formatters = [
                formatter.parse(dirfmt, util.NONE).format_map
                for dirfmt in directory
            ]
        elif directory:
            self._directory = self._directory_custom
            sep = os.sep + (os.altsep or "")
            self._metadir = util.expand_path(directory).rstrip(sep) + os.sep

        filename = options.get("filename", filename)
        extfmt = options.get("extension-format")
        if filename:
            if filename == "-":
                self.run = self._run_stdout
            else:
                self._filename = self._filename_custom
                self._filename_fmt = formatter.parse(filename).format_map
        elif extfmt:
            self._filename = self._filename_extfmt
            self._extension_fmt = formatter.parse(extfmt).format_map
        else:
            self.extension = options.get("extension", ext)

        events = options.get("event")
        if events is None:
            events = ("file",)
        elif isinstance(events, str):
            events = events.split(",")
        job.register_hooks({event: self.run for event in events}, options)

        if self._archive_init(job, options, "_MD_"):
            self._archive_register(job)

        self.filter = self._make_filter(options)
        self.mtime = options.get("mtime")
        self.omode = options.get("open", omode)
        self.encoding = options.get("encoding", "utf-8")
        self.newline = options.get("newline")
        self.skip = options.get("skip", False)
        self.meta_path = options.get("metadata-path")

    def open(self, path):
        return open(path, self.omode,
                    encoding=self.encoding,
                    newline=self.newline)

    def run(self, pathfmt):
        archive = self.archive
        if archive and archive.check(pathfmt.kwdict):
            return

        if util.WINDOWS and pathfmt.extended:
            directory = pathfmt._extended_path(self._directory(pathfmt))
        else:
            directory = self._directory(pathfmt)
        path = directory + self._filename(pathfmt)

        if self.meta_path is not None:
            pathfmt.kwdict[self.meta_path] = path

        if self.skip and os.path.exists(path):
            return

        try:
            with self.open(path) as fp:
                self.write(fp, pathfmt.kwdict)
        except FileNotFoundError:
            os.makedirs(directory, exist_ok=True)
            with self.open(path) as fp:
                self.write(fp, pathfmt.kwdict)

        if archive:
            archive.add(pathfmt.kwdict)

        if self.mtime:
            pathfmt.set_mtime(path)

    def _run_stdout(self, pathfmt):
        self.write(sys.stdout, pathfmt.kwdict)

    def _run_modify(self, pathfmt):
        kwdict = pathfmt.kwdict
        for key, func in self.fields.items():
            obj = kwdict
            try:
                if "[" in key:
                    obj, key = _traverse(obj, key)
                obj[key] = func(kwdict)
            except Exception:
                pass

    def _run_delete(self, pathfmt):
        kwdict = pathfmt.kwdict
        for key in self.fields:
            obj = kwdict
            try:
                if "[" in key:
                    obj, key = _traverse(obj, key)
                del obj[key]
            except Exception:
                pass

    def _base(self, pathfmt):
        return pathfmt.realdirectory

    def _directory(self, pathfmt):
        return self._base(pathfmt)

    def _directory_custom(self, pathfmt):
        return os.path.join(self._base(pathfmt), self._metadir)

    def _directory_format(self, pathfmt):
        formatters = pathfmt.directory_formatters
        conditions = pathfmt.directory_conditions
        try:
            pathfmt.directory_formatters = self._directory_formatters
            pathfmt.directory_conditions = ()
            if segments := pathfmt.build_directory(pathfmt.kwdict):
                directory = pathfmt.clean_path(os.sep.join(segments) + os.sep)
            else:
                directory = "." + os.sep
            return os.path.join(self._base(pathfmt), directory)
        finally:
            pathfmt.directory_conditions = conditions
            pathfmt.directory_formatters = formatters

    def _filename(self, pathfmt):
        return (pathfmt.filename or "metadata") + "." + self.extension

    def _filename_custom(self, pathfmt):
        return pathfmt.clean_path(pathfmt.clean_segment(
            self._filename_fmt(pathfmt.kwdict)))

    def _filename_extfmt(self, pathfmt):
        kwdict = pathfmt.kwdict
        ext = kwdict.get("extension")
        kwdict["extension"] = pathfmt.extension
        kwdict["extension"] = pathfmt.prefix + self._extension_fmt(kwdict)
        filename = pathfmt.build_filename(kwdict)
        kwdict["extension"] = ext
        return filename

    def _write_custom(self, fp, kwdict):
        fp.write(self._content_fmt(kwdict))

    def _write_tags(self, fp, kwdict):
        tags = kwdict.get("tags") or kwdict.get("tag_string")

        if not tags:
            return

        if isinstance(tags, str):
            taglist = tags.split(", ")
            if len(taglist) < len(tags) / 16:
                taglist = tags.split(" ")
            tags = taglist
        elif isinstance(tags, dict):
            taglists = tags.values()
            tags = []
            extend = tags.extend
            for taglist in taglists:
                extend(taglist)
            tags.sort()
        elif all(isinstance(e, dict) for e in tags):
            taglists = tags
            tags = []
            extend = tags.extend
            for tagdict in taglists:
                extend([x for x in tagdict.values() if isinstance(x, str)])
            tags.sort()

        fp.write("\n".join(tags) + "\n")

    def _write_json(self, fp, kwdict):
        if self.filter:
            kwdict = self.filter(kwdict)
        fp.write(self._json_encode(kwdict) + "\n")

    def _make_filter(self, options):
        if include := options.get("include"):
            if isinstance(include, str):
                include = include.split(",")
            return lambda d: {k: d[k] for k in include if k in d}

        exclude = options.get("exclude")
        private = options.get("private")
        if exclude:
            if isinstance(exclude, str):
                exclude = exclude.split(",")
            exclude = set(exclude)

            if private:
                return lambda d: {k: v for k, v in d.items()
                                  if k not in exclude}
            return lambda d: {k: v for k, v in util.filter_dict(d).items()
                              if k not in exclude}

        if not private:
            return util.filter_dict

    def _make_encoder(self, options, indent=None):
        return json.JSONEncoder(
            ensure_ascii=options.get("ascii", False),
            sort_keys=options.get("sort", False),
            separators=options.get("separators"),
            indent=options.get("indent", indent),
            check_circular=False,
            default=util.json_default,
        )


def _traverse(obj, key):
    name, _, key = key.partition("[")
    obj = obj[name]

    while "[" in key:
        name, _, key = key.partition("[")
        obj = obj[name.strip("\"']")]

    return obj, key.strip("\"']")


__postprocessor__ = MetadataPP

================
File: gallery_dl/postprocessor/python.py
================
# -*- coding: utf-8 -*-

# Copyright 2023-2025 Mike Fährmann
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 as
# published by the Free Software Foundation.

"""Run Python functions"""

from .common import PostProcessor
from .. import util


class PythonPP(PostProcessor):

    def __init__(self, job, options):
        PostProcessor.__init__(self, job)

        mode = options.get("mode")
        if mode == "eval" or not mode and options.get("expression"):
            self.function = util.compile_expression(options["expression"])
        else:
            spec = options["function"]
            module_name, _, function_name = spec.rpartition(":")
            module = util.import_file(module_name)
            self.function = getattr(module, function_name)

        if archive := self._archive_init(job, options):
            self.run = self.run_archive

        events = options.get("event")
        if events is None:
            events = ("file",)
        elif isinstance(events, str):
            events = events.split(",")
        job.register_hooks({event: self.run for event in events}, options)

        if archive:
            self._archive_register(job)

    def run(self, pathfmt):
        self.function(pathfmt.kwdict)

    def run_archive(self, pathfmt):
        kwdict = pathfmt.kwdict
        if self.archive.check(kwdict):
            return
        self.function(kwdict)
        self.archive.add(kwdict)


__postprocessor__ = PythonPP

================
File: gallery_dl/postprocessor/rename.py
================
# -*- coding: utf-8 -*-

# Copyright 2024 Mike Fährmann
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 as
# published by the Free Software Foundation.

"""Rename files"""

from .common import PostProcessor
from .. import formatter
import os


class RenamePP(PostProcessor):

    def __init__(self, job, options):
        PostProcessor.__init__(self, job)

        self.skip = options.get("skip", True)
        old = options.get("from")
        new = options.get("to")

        if old:
            self._old = self._apply_format(old)
            self._new = (self._apply_format(new) if new else
                         self._apply_pathfmt)
            job.register_hooks({
                "prepare": self.rename_from,
            }, options)

        elif new:
            self._old = self._apply_pathfmt
            self._new = self._apply_format(new)
            job.register_hooks({
                "skip"         : self.rename_to_skip,
                "prepare-after": self.rename_to_pafter,
            }, options)

        else:
            raise ValueError("Option 'from' or 'to' is required")

    def rename_from(self, pathfmt):
        name_old = self._old(pathfmt)
        path_old = pathfmt.realdirectory + name_old

        if os.path.exists(path_old):
            name_new = self._new(pathfmt)
            path_new = pathfmt.realdirectory + name_new
            self._rename(path_old, name_old, path_new, name_new)

    def rename_to_skip(self, pathfmt):
        name_old = self._old(pathfmt)
        path_old = pathfmt.realdirectory + name_old

        if os.path.exists(path_old):
            pathfmt.filename = name_new = self._new(pathfmt)
            pathfmt.path = pathfmt.directory + name_new
            pathfmt.realpath = path_new = pathfmt.realdirectory + name_new
            self._rename(path_old, name_old, path_new, name_new)

    def rename_to_pafter(self, pathfmt):
        pathfmt.filename = name_new = self._new(pathfmt)
        pathfmt.path = pathfmt.directory + name_new
        pathfmt.realpath = pathfmt.realdirectory + name_new
        pathfmt.kwdict["_file_recheck"] = True

    def _rename(self, path_old, name_old, path_new, name_new):
        if self.skip and os.path.exists(path_new):
            return self.log.warning(
                "Not renaming '%s' to '%s' since another file with the "
                "same name exists", name_old, name_new)

        self.log.info("'%s' -> '%s'", name_old, name_new)
        os.replace(path_old, path_new)

    def _apply_pathfmt(self, pathfmt):
        return pathfmt.build_filename(pathfmt.kwdict)

    def _apply_format(self, format_string):
        fmt = formatter.parse(format_string).format_map

        def apply(pathfmt):
            return pathfmt.clean_path(pathfmt.clean_segment(fmt(
                pathfmt.kwdict)))

        return apply


__postprocessor__ = RenamePP

================
File: gallery_dl/postprocessor/ugoira.py
================
# -*- coding: utf-8 -*-

# Copyright 2018-2025 Mike Fährmann
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 as
# published by the Free Software Foundation.

"""Convert Pixiv Ugoira to WebM"""

from .common import PostProcessor
from .. import util, output
import subprocess
import tempfile
import zipfile
import shutil
import os

try:
    from math import gcd
except ImportError:
    def gcd(a, b):
        while b:
            a, b = b, a % b
        return a


class UgoiraPP(PostProcessor):

    def __init__(self, job, options):
        PostProcessor.__init__(self, job)
        self.args = options.get("ffmpeg-args") or ()
        self.twopass = options.get("ffmpeg-twopass", False)
        self.output = options.get("ffmpeg-output", "error")
        self.delete = not options.get("keep-files", False)
        self.repeat = options.get("repeat-last-frame", True)
        self.metadata = options.get("metadata", True)
        self.mtime = options.get("mtime", True)
        self.skip = options.get("skip", True)
        self.uniform = self._convert_zip = self._convert_files = False

        ffmpeg = options.get("ffmpeg-location")
        self.ffmpeg = util.expand_path(ffmpeg) if ffmpeg else "ffmpeg"

        mkvmerge = options.get("mkvmerge-location")
        self.mkvmerge = util.expand_path(mkvmerge) if mkvmerge else "mkvmerge"

        ext = options.get("extension")
        mode = options.get("mode") or options.get("ffmpeg-demuxer")
        if mode is None or mode == "auto":
            if ext in (None, "webm", "mkv") and (
                    mkvmerge or shutil.which("mkvmerge")):
                mode = "mkvmerge"
            else:
                mode = "concat"

        if mode == "mkvmerge":
            self._process = self._process_mkvmerge
            self._finalize = self._finalize_mkvmerge
        elif mode == "image2":
            self._process = self._process_image2
            self._finalize = None
        elif mode == "archive":
            if ext is None:
                ext = "zip"
            self._convert_impl = self.convert_to_archive
            self._tempdir = util.NullContext
        else:
            self._process = self._process_concat
            self._finalize = None
        self.extension = "webm" if ext is None else ext
        self.log.debug("using %s demuxer", mode)

        rate = options.get("framerate", "auto")
        if rate == "uniform":
            self.uniform = True
        elif rate != "auto":
            self.calculate_framerate = lambda _: (None, rate)

        if options.get("libx264-prevent-odd", True):
            # get last video-codec argument
            vcodec = None
            for index, arg in enumerate(self.args):
                arg, _, stream = arg.partition(":")
                if arg == "-vcodec" or arg in ("-c", "-codec") and (
                        not stream or stream.partition(":")[0] in ("v", "V")):
                    vcodec = self.args[index + 1]
            # use filter when using libx264/5
            self.prevent_odd = (
                vcodec in ("libx264", "libx265") or
                not vcodec and self.extension.lower() in ("mp4", "mkv"))
        else:
            self.prevent_odd = False

        self.args_pp = args = []
        if isinstance(self.output, str):
            args += ("-hide_banner", "-loglevel", self.output)
        if self.prevent_odd:
            args += ("-vf", "crop=iw-mod(iw\\,2):ih-mod(ih\\,2)")

        job.register_hooks({
            "prepare": self.prepare,
            "file"   : self.convert_from_zip,
            "after"  : self.convert_from_files,
        }, options)

    def prepare(self, pathfmt):
        self._convert_zip = self._convert_files = False
        if "_ugoira_frame_data" not in pathfmt.kwdict:
            self._frames = None
            return

        self._frames = pathfmt.kwdict["_ugoira_frame_data"]
        index = pathfmt.kwdict.get("_ugoira_frame_index")
        if index is None:
            self._convert_zip = True
            if self.delete:
                pathfmt.set_extension(self.extension)
                pathfmt.build_path()
        else:
            pathfmt.build_path()
            frame = self._frames[index].copy()
            frame["index"] = index
            frame["path"] = pathfmt.realpath
            frame["ext"] = pathfmt.extension

            if not index:
                self._files = [frame]
            else:
                self._files.append(frame)
                if len(self._files) >= len(self._frames):
                    self._convert_files = True

    def convert_from_zip(self, pathfmt):
        if not self._convert_zip:
            return
        self._zip_source = True
        self._zip_ext = ext = pathfmt.extension

        with self._tempdir() as tempdir:
            if tempdir:
                try:
                    with zipfile.ZipFile(pathfmt.temppath) as zfile:
                        zfile.extractall(tempdir)
                except FileNotFoundError:
                    pathfmt.realpath = pathfmt.temppath
                    return
                except Exception as exc:
                    pathfmt.realpath = pathfmt.temppath
                    self.log.error(
                        "%s: Unable to extract frames from %s (%s: %s)",
                        pathfmt.kwdict.get("id"), pathfmt.filename,
                        exc.__class__.__name__, exc)
                    return self.log.traceback(exc)

            if self.convert(pathfmt, tempdir):
                if self.delete:
                    pathfmt.delete = True
                elif pathfmt.extension != ext:
                    self.log.info(pathfmt.filename)
                    pathfmt.set_extension(ext)
                    pathfmt.build_path()

    def convert_from_files(self, pathfmt):
        if not self._convert_files:
            return
        self._zip_source = False

        with tempfile.TemporaryDirectory() as tempdir:
            for frame in self._files:

                # update frame filename extension
                frame["file"] = name = \
                    f"{frame['file'].partition('.')[0]}.{frame['ext']}"

                if tempdir:
                    # move frame into tempdir
                    try:
                        self._copy_file(frame["path"], tempdir + "/" + name)
                    except OSError as exc:
                        self.log.debug("Unable to copy frame %s (%s: %s)",
                                       name, exc.__class__.__name__, exc)
                        return

            pathfmt.kwdict["num"] = 0
            self._frames = self._files
            if self.convert(pathfmt, tempdir):
                self.log.info(pathfmt.filename)
                if self.delete:
                    self.log.debug("Deleting frames")
                    for frame in self._files:
                        util.remove_file(frame["path"])

    def convert(self, pathfmt, tempdir):
        pathfmt.set_extension(self.extension)
        pathfmt.build_path()
        if self.skip and pathfmt.exists():
            return True

        return self._convert_impl(pathfmt, tempdir)

    def convert_to_animation(self, pathfmt, tempdir):
        # process frames and collect command-line arguments
        args = self._process(pathfmt, tempdir)
        if self.args_pp:
            args += self.args_pp
        if self.args:
            args += self.args

        # ensure target directory exists
        os.makedirs(pathfmt.realdirectory, exist_ok=True)

        # invoke ffmpeg
        try:
            if self.twopass:
                if "-f" not in self.args:
                    args += ("-f", self.extension)
                args += ("-passlogfile", tempdir + "/ffmpeg2pass", "-pass")
                self._exec(args + ["1", "-y", os.devnull])
                self._exec(args + ["2", pathfmt.realpath])
            else:
                args.append(pathfmt.realpath)
                self._exec(args)
            if self._finalize:
                self._finalize(pathfmt, tempdir)
        except OSError as exc:
            output.stderr_write("\n")
            self.log.error("Unable to invoke FFmpeg (%s: %s)",
                           exc.__class__.__name__, exc)
            self.log.traceback(exc)
            pathfmt.realpath = pathfmt.temppath
        except Exception as exc:
            output.stderr_write("\n")
            self.log.error("%s: %s", exc.__class__.__name__, exc)
            self.log.traceback(exc)
            pathfmt.realpath = pathfmt.temppath
        else:
            if self.mtime:
                pathfmt.set_mtime()
            return True

    def convert_to_archive(self, pathfmt, tempdir):
        frames = self._frames

        if self.metadata:
            if isinstance(self.metadata, str):
                metaname = self.metadata
            else:
                metaname = "animation.json"
            framedata = util.json_dumps([
                {"file": frame["file"], "delay": frame["delay"]}
                for frame in frames
            ]).encode()

        if self._zip_source:
            zpath = pathfmt.temppath
            if self.delete:
                self.delete = False
            elif self._zip_ext != self.extension:
                self._copy_file(zpath, pathfmt.realpath)
                zpath = pathfmt.realpath

            if self.metadata:
                with zipfile.ZipFile(zpath, "a") as zfile:
                    zinfo = zipfile.ZipInfo(metaname)
                    if self.mtime:
                        zinfo.date_time = zfile.infolist()[0].date_time
                    with zfile.open(zinfo, "w") as fp:
                        fp.write(framedata)
        else:
            if self.mtime:
                dt = pathfmt.kwdict["date_url"] or pathfmt.kwdict["date"]
                mtime = (dt.year, dt.month, dt.day,
                         dt.hour, dt.minute, dt.second)
            with zipfile.ZipFile(pathfmt.realpath, "w") as zfile:
                for frame in frames:
                    zinfo = zipfile.ZipInfo.from_file(
                        frame["path"], frame["file"])
                    if self.mtime:
                        zinfo.date_time = mtime
                    with open(frame["path"], "rb") as src, \
                            zfile.open(zinfo, "w") as dst:
                        shutil.copyfileobj(src, dst, 1024*8)
                if self.metadata:
                    zinfo = zipfile.ZipInfo(metaname)
                    if self.mtime:
                        zinfo.date_time = mtime
                    with zfile.open(zinfo, "w") as fp:
                        fp.write(framedata)

        return True

    _convert_impl = convert_to_animation
    _tempdir = tempfile.TemporaryDirectory

    def _exec(self, args):
        self.log.debug(args)
        out = None if self.output else subprocess.DEVNULL
        if retcode := util.Popen(args, stdout=out, stderr=out).wait():
            output.stderr_write("\n")
            self.log.error("Non-zero exit status when running %s (%s)",
                           args, retcode)
            raise ValueError()
        return retcode

    def _copy_file(self, src, dst):
        shutil.copyfile(src, dst)

    def _process_concat(self, pathfmt, tempdir):
        rate_in, rate_out = self.calculate_framerate(self._frames)
        args = [self.ffmpeg, "-f", "concat"]
        if rate_in:
            args += ("-r", str(rate_in))
        args += ("-i", self._write_ffmpeg_concat(tempdir))
        if rate_out:
            args += ("-r", str(rate_out))
        return args

    def _process_image2(self, pathfmt, tempdir):
        tempdir += "/"
        frames = self._frames

        # add extra frame if necessary
        if self.repeat and not self._delay_is_uniform(frames):
            last = frames[-1]
            delay_gcd = self._delay_gcd(frames)
            if last["delay"] - delay_gcd > 0:
                last["delay"] -= delay_gcd

                self.log.debug("non-uniform delays; inserting extra frame")
                last_copy = last.copy()
                frames.append(last_copy)
                name, _, ext = last_copy["file"].rpartition(".")
                last_copy["file"] = f"{int(name) + 1:>06}.{ext}"
                shutil.copyfile(tempdir + last["file"],
                                tempdir + last_copy["file"])

        # adjust frame mtime values
        ts = 0
        for frame in frames:
            os.utime(tempdir + frame["file"], ns=(ts, ts))
            ts += frame["delay"] * 1000000

        return [
            self.ffmpeg,
            "-f", "image2",
            "-ts_from_file", "2",
            "-pattern_type", "sequence",
            "-i", (f"{tempdir.replace('%', '%%')}%06d."
                   f"{frame['file'].rpartition('.')[2]}"),
        ]

    def _process_mkvmerge(self, pathfmt, tempdir):
        self._realpath = pathfmt.realpath
        pathfmt.realpath = tempdir + "/temp." + self.extension

        return [
            self.ffmpeg,
            "-f", "image2",
            "-pattern_type", "sequence",
            "-i", (f"{tempdir.replace('%', '%%')}/%06d."
                   f"{self._frames[0]['file'].rpartition('.')[2]}"),
        ]

    def _finalize_mkvmerge(self, pathfmt, tempdir):
        args = [
            self.mkvmerge,
            "-o", pathfmt.path,  # mkvmerge does not support "raw" paths
            "--timecodes", "0:" + self._write_mkvmerge_timecodes(tempdir),
        ]
        if self.extension == "webm":
            args.append("--webm")
        args += ("=", pathfmt.realpath)

        pathfmt.realpath = self._realpath
        self._exec(args)

    def _write_ffmpeg_concat(self, tempdir):
        content = ["ffconcat version 1.0"]

        for frame in self._frames:
            content.append(f"file '{frame['file']}'\n"
                           f"duration {frame['delay'] / 1000}")
        if self.repeat:
            content.append(f"file '{frame['file']}'")
        content.append("")

        ffconcat = tempdir + "/ffconcat.txt"
        with open(ffconcat, "w", encoding="utf-8") as fp:
            fp.write("\n".join(content))
        return ffconcat

    def _write_mkvmerge_timecodes(self, tempdir):
        content = ["# timecode format v2"]

        delay_sum = 0
        for frame in self._frames:
            content.append(str(delay_sum))
            delay_sum += frame["delay"]
        content.append(str(delay_sum))
        content.append("")

        timecodes = tempdir + "/timecodes.tc"
        with open(timecodes, "w", encoding="utf-8") as fp:
            fp.write("\n".join(content))
        return timecodes

    def calculate_framerate(self, frames):
        if self._delay_is_uniform(frames):
            return (f"1000/{frames[0]['delay']}", None)

        if not self.uniform:
            gcd = self._delay_gcd(frames)
            if gcd >= 10:
                return (None, f"1000/{gcd}")

        return (None, None)

    def _delay_gcd(self, frames):
        result = frames[0]["delay"]
        for f in frames:
            result = gcd(result, f["delay"])
        return result

    def _delay_is_uniform(self, frames):
        delay = frames[0]["delay"]
        for f in frames:
            if f["delay"] != delay:
                return False
        return True


__postprocessor__ = UgoiraPP

================
File: gallery_dl/postprocessor/zip.py
================
# -*- coding: utf-8 -*-

# Copyright 2018-2022 Mike Fährmann
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 as
# published by the Free Software Foundation.

"""Store files in ZIP archives"""

from .common import PostProcessor
from .. import util
import zipfile
import os


class ZipPP(PostProcessor):

    COMPRESSION_ALGORITHMS = {
        "store": zipfile.ZIP_STORED,
        "zip"  : zipfile.ZIP_DEFLATED,
        "bzip2": zipfile.ZIP_BZIP2,
        "lzma" : zipfile.ZIP_LZMA,
    }

    def __init__(self, job, options):
        PostProcessor.__init__(self, job)
        self.delete = not options.get("keep-files", False)
        self.files = options.get("files")
        ext = "." + options.get("extension", "zip")
        algorithm = options.get("compression", "store")
        if algorithm not in self.COMPRESSION_ALGORITHMS:
            self.log.warning(
                "unknown compression algorithm '%s'; falling back to 'store'",
                algorithm)
            algorithm = "store"

        self.zfile = None
        self.path = job.pathfmt.realdirectory[:-1]
        self.args = (self.path + ext, "a",
                     self.COMPRESSION_ALGORITHMS[algorithm], True)

        job.register_hooks({
            "file": (self.write_safe if options.get("mode") == "safe" else
                     self.write_fast),
        }, options)
        job.hooks["finalize"].append(self.finalize)

    def open(self):
        try:
            return zipfile.ZipFile(*self.args)
        except FileNotFoundError:
            os.makedirs(os.path.dirname(self.path))
            return zipfile.ZipFile(*self.args)

    def write(self, pathfmt, zfile):
        # 'NameToInfo' is not officially documented, but it's available
        # for all supported Python versions and using it directly is a lot
        # faster than calling getinfo()
        if self.files:
            self.write_extra(pathfmt, zfile, self.files)
            self.files = None
        if pathfmt.filename not in zfile.NameToInfo:
            zfile.write(pathfmt.temppath, pathfmt.filename)
            pathfmt.delete = self.delete

    def write_fast(self, pathfmt):
        if self.zfile is None:
            self.zfile = self.open()
        self.write(pathfmt, self.zfile)

    def write_safe(self, pathfmt):
        with self.open() as zfile:
            self.write(pathfmt, zfile)

    def write_extra(self, pathfmt, zfile, files):
        for path in map(util.expand_path, files):
            if not os.path.isabs(path):
                path = os.path.join(pathfmt.realdirectory, path)
            try:
                zfile.write(path, os.path.basename(path))
            except OSError as exc:
                self.log.warning(
                    "Unable to write %s to %s", path, zfile.filename)
                self.log.debug("%s: %s", exc, exc.__class__.__name__)
                pass
            else:
                if self.delete:
                    util.remove_file(path)

    def finalize(self, pathfmt):
        if self.zfile:
            self.zfile.close()

        if self.delete:
            util.remove_directory(self.path)

            if self.zfile and not self.zfile.NameToInfo:
                # remove empty zip archive
                util.remove_file(self.zfile.filename)


__postprocessor__ = ZipPP

================
File: gallery_dl/postprocessor/mtime.py
================
# -*- coding: utf-8 -*-

# Copyright 2019-2026 Mike Fährmann
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 as
# published by the Free Software Foundation.

"""Use metadata as file modification time"""

from .common import PostProcessor
from .. import text, util, dt, formatter


class MtimePP(PostProcessor):

    def __init__(self, job, options):
        PostProcessor.__init__(self, job)
        if value := options.get("value"):
            self._get = formatter.parse(value, None, util.identity).format_map
        else:
            key = options.get("key", "date")
            self._get = lambda kwdict: kwdict.get(key)

        events = options.get("event")
        if events is None:
            events = ("file",)
        elif isinstance(events, str):
            events = events.split(",")
        job.register_hooks({event: self.run for event in events}, options)

    def run(self, pathfmt):
        if mtime := self._get(pathfmt.kwdict):
            if isinstance(mtime, dt.datetime):
                mtime = dt.to_ts(mtime)
            else:
                mtime = text.parse_int(mtime)
        else:
            mtime = None
        pathfmt.kwdict["_mtime_meta"] = mtime


__postprocessor__ = MtimePP

================
File: gallery_dl/extractor/hitomi.py
================
# -*- coding: utf-8 -*-
"""Extractors for https://hitomi.la/"""

from .common import GalleryExtractor, Extractor, Message
from .nozomi import decode_nozomi
from ..cache import memcache
from .. import text, util
import string


class HitomiExtractor(Extractor):
    """Base class for hitomi extractors"""
    category = "hitomi"
    root = "https://hitomi.la"
    domain = "gold-usergeneratedcontent.net"

    def load_nozomi(self, query, language="all", headers=None):
        ns, _, tag = query.strip().partition(":")

        if ns == "female" or ns == "male":
            ns = "tag/"
            tag = query
        elif ns == "language":
            ns = ""
            language = tag
            tag = "index"
        else:
            ns += "/"

        url = (f"https://ltn.{self.domain}/n/{ns}"
               f"/{tag.replace('_', ' ')}-{language}.nozomi")
        if headers is None:
            headers = {}
        headers["Origin"] = self.root
        headers["Referer"] = self.root + "/"
        return decode_nozomi(self.request(url, headers=headers).content)


class HitomiGalleryExtractor(HitomiExtractor, GalleryExtractor):
    """Extractor for hitomi.la galleries"""
    pattern = (r"(?:https?://)?hitomi\.la"
               r"/(?:manga|doujinshi|cg|gamecg|imageset|galleries|reader)"
               r"/(?:[^/?#]+-)?(\d+)")
    example = "https://hitomi.la/manga/TITLE-867789.html"

    # CHANGED: Switched {num:>03} to {filename} so your custom naming logic is used
    filename_fmt = "{category}_{gallery_id}_{filename}.{extension}"

    def __init__(self, match):
        GalleryExtractor.__init__(self, match, False)
        self.gid = gid = self.groups[0]
        self.page_url = f"https://ltn.{self.domain}/galleries/{gid}.js"

    def _init(self):
        self.session.headers["Referer"] = f"{self.root}/reader/{self.gid}.html"

    def metadata(self, page):
        self.info = info = util.json_loads(page.partition("=")[2])
        iget = info.get

        if language := iget("language"):
            language = language

        if date := iget("date"):
            date += ":00"

        tags = []
        for tinfo in iget("tags") or ():
            tag = string.capwords(tinfo["tag"])
            tags.append(tag)

        return {
            "gallery_id": text.parse_int(info["id"]),
            "title"     : info["title"],
            "title_jpn" : info.get("japanese_title") or "",
            "type"      : info["type"],
            "language"  : language,
            "lang"      : util.language_to_code(language.capitalize()),
            "date"      : self.parse_datetime_iso(date),
            "tags"      : tags,
            "artist"    : [o["artist"] for o in iget("artists") or ()],
            "group"     : [o["group"] for o in iget("groups") or ()],
            "parody"    : [o["parody"] for o in iget("parodys") or ()],
            "characters": [o["character"] for o in iget("characters") or ()]
        }

    def images(self, _):
        # https://ltn.gold-usergeneratedcontent.net/gg.js
        gg_m, gg_b, gg_default = _parse_gg(self)

        fmt = ext = self.config("format") or "webp"
        check = (fmt != "webp")

        results = []

        # CHANGED: Added enumerate to calculate padding properly based on list index
        for i, image in enumerate(self.info["files"], 1):
            if check:
                ext = fmt if image.get("has" + fmt) else "webp"
            ihash = image["hash"]

            # Calculate padded page number (e.g. "0001", "0002")
            page_str = f"{i:>04}"

            # --- Main Image ---
            idata = text.nameext_from_url(image["name"])

            # CHANGED: Explicitly set filename to the padded number
            idata["filename"] = page_str
            idata["extension_original"] = idata["extension"]
            idata["extension"] = ext

            # https://ltn.gold-usergeneratedcontent.net/common.js
            inum = int(ihash[-1] + ihash[-3:-1], 16)
            url = (f"https://{ext[0]}{gg_m.get(inum, gg_default) + 1}."
                   f"{self.domain}/{gg_b}/{inum}/{ihash}.{ext}")
            results.append((url, idata))

            # Shared parts for thumbnails (tn.{domain}/{dir}/{part1}/{part2}/{hash}.webp)
            tn_part1 = ihash[-1]
            tn_part2 = ihash[-3:-1]

            # --- Small Thumbnail ---
            small_tn_url = (f"https://tn.{self.domain}/webpsmalltn/"
                            f"{tn_part1}/{tn_part2}/{ihash}.{ext}")

            # CHANGED: Explicitly set filename with "thumb_" prefix and padded number
            small_tn_data = {
                "filename": f"thumb_{page_str}",
                "extension": ext
            }
            results.append((small_tn_url, small_tn_data))

        return results


class HitomiTagExtractor(HitomiExtractor):
    """Extractor for galleries from tag searches on hitomi.la"""
    subcategory = "tag"
    pattern = (r"(?:https?://)?hitomi\.la"
               r"/(tag|artist|group|series|type|character)"
               r"/([^/?#]+)\.html")
    example = "https://hitomi.la/tag/TAG-LANG.html"

    def __init__(self, match):
        Extractor.__init__(self, match)
        self.type, self.tag = match.groups()

        tag, _, num = self.tag.rpartition("-")
        if num.isdecimal():
            self.tag = tag

    def items(self):
        data = {
            "_extractor": HitomiGalleryExtractor,
            "search_tags": text.unquote(self.tag.rpartition("-")[0]),
        }
        nozomi_url = f"https://ltn.{self.domain}/{self.type}/{self.tag}.nozomi"
        headers = {
            "Origin": self.root,
            "Cache-Control": "max-age=0",
        }

        offset = 0
        total = None
        while True:
            headers["Referer"] = (f"{self.root}/{self.type}/{self.tag}.html"
                                  f"?page={offset // 100 + 1}")
            headers["Range"] = f"bytes={offset}-{offset + 99}"
            response = self.request(nozomi_url, headers=headers)

            for gallery_id in decode_nozomi(response.content):
                gallery_url = f"{self.root}/galleries/{gallery_id}.html"
                yield Message.Queue, gallery_url, data

            offset += 100
            if total is None:
                total = text.parse_int(
                    response.headers["content-range"].rpartition("/")[2])
            if offset >= total:
                return


class HitomiIndexExtractor(HitomiTagExtractor):
    """Extractor for galleries from index searches on hitomi.la"""
    subcategory = "index"
    pattern = r"(?:https?://)?hitomi\.la/(\w+)-(\w+)\.html"
    example = "https://hitomi.la/index-japanese.html"

    def __init__(self, match):
        Extractor.__init__(self, match)
        self.tag, self.language = match.groups()

    def items(self):
        data = {"_extractor": HitomiGalleryExtractor}
        nozomi_url = (f"https://ltn.{self.domain}"
                      f"/{self.tag}-{self.language}.nozomi")
        headers = {
            "Origin": self.root,
            "Cache-Control": "max-age=0",
        }

        offset = 0
        total = None
        while True:
            headers["Referer"] = (f"{self.root}/{self.tag}-{self.language}"
                                  f".html?page={offset // 100 + 1}")
            headers["Range"] = f"bytes={offset}-{offset + 99}"
            response = self.request(nozomi_url, headers=headers)

            for gallery_id in decode_nozomi(response.content):
                gallery_url = f"{self.root}/galleries/{gallery_id}.html"
                yield Message.Queue, gallery_url, data

            offset += 100
            if total is None:
                total = text.parse_int(
                    response.headers["content-range"].rpartition("/")[2])
            if offset >= total:
                return


class HitomiSearchExtractor(HitomiExtractor):
    """Extractor for galleries from multiple tag searches on hitomi.la"""
    subcategory = "search"
    pattern = r"(?:https?://)?hitomi\.la/search\.html\?([^#]+)"
    example = "https://hitomi.la/search.html?QUERY"

    def items(self):
        tags = text.unquote(self.groups[0])

        data = {
            "_extractor": HitomiGalleryExtractor,
            "search_tags": tags,
        }

        for gallery_id in self.gallery_ids(tags):
            gallery_url = f"{self.root}/galleries/{gallery_id}.html"
            yield Message.Queue, gallery_url, data

    def gallery_ids(self, tags):
        result = None
        positive = []
        negative = []

        for tag in tags.split():
            if tag[0] == "-":
                negative.append(tag[1:])
            else:
                positive.append(tag)

        for tag in positive:
            ids = self.load_nozomi(tag)
            if result is None:
                result = set(ids)
            else:
                result.intersection_update(ids)

        if result is None:
            #  result = set(self.load_nozomi("index"))
            result = set(self.load_nozomi("language:japanese"))
        for tag in negative:
            result.difference_update(self.load_nozomi(tag))

        return sorted(result, reverse=True) if result else ()


@memcache(maxage=1800)
def _parse_gg(extr):
    page = extr.request("https://ltn.gold-usergeneratedcontent.net/gg.js").text

    m = {}

    keys = []
    for match in util.re_compile(
            r"case\s+(\d+):(?:\s*o\s*=\s*(\d+))?").finditer(page):
        key, value = match.groups()
        keys.append(int(key))

        if value:
            value = int(value)
            for key in keys:
                m[key] = value
            keys.clear()

    for match in util.re_compile(
            r"if\s+\(g\s*===?\s*(\d+)\)[\s{]*o\s*=\s*(\d+)").finditer(page):
        m[int(match[1])] = int(match[2])

    d = util.re_compile(r"(?:var\s|default:)\s*o\s*=\s*(\d+)").search(page)
    b = util.re_compile(r"b:\s*[\"'](.+)[\"']").search(page)

    return m, b[1].strip("/"), int(d[1]) if d else 0

================
File: gallery_dl/extractor/common.py
================
# -*- coding: utf-8 -*-

# Copyright 2014-2026 Mike Fährmann
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 as
# published by the Free Software Foundation.

"""Common classes and constants used by extractor modules."""

import os
import re
import ssl
import time
import netrc
import queue
import random
import getpass
import logging
import requests
import threading
from xml.etree import ElementTree
from requests.adapters import HTTPAdapter
from .message import Message
from .. import config, output, text, util, dt, cache, exception
urllib3 = requests.packages.urllib3


class Extractor():

    category = ""
    subcategory = ""
    basecategory = ""
    basesubcategory = ""
    categorytransfer = False
    parent = False
    directory_fmt = ("{category}",)
    filename_fmt = "{filename}.{extension}"
    archive_fmt = ""
    status = 0
    root = ""
    cookies_file = ""
    cookies_index = 0
    cookies_domain = ""
    session = None
    referer = True
    ciphers = None
    tls12 = True
    browser = None
    useragent = util.USERAGENT_FIREFOX
    request_interval = 0.0
    request_interval_min = 0.0
    request_interval_429 = 60.0
    request_timestamp = 0.0

    def __init__(self, match):
        self.log = logging.getLogger(self.category)
        self.url = match.string
        self.match = match
        self.groups = match.groups()
        self.kwdict = {}

        if self.category in CATEGORY_MAP:
            catsub = f"{self.category}:{self.subcategory}"
            if catsub in CATEGORY_MAP:
                self.category, self.subcategory = CATEGORY_MAP[catsub]
            else:
                self.category = CATEGORY_MAP[self.category]

        self.parse_datetime = dt.parse
        self.parse_datetime_iso = dt.parse_iso
        self.parse_timestamp = dt.parse_ts

        self._cfgpath = ("extractor", self.category, self.subcategory)
        self._parentdir = ""

    @classmethod
    def from_url(cls, url):
        if isinstance(cls.pattern, str):
            cls.pattern = util.re_compile(cls.pattern)
        match = cls.pattern.match(url)
        return cls(match) if match else None

    def __iter__(self):
        self.initialize()
        return self.items()

    def initialize(self):
        self._init_options()

        if self.session is None:
            self._init_session()
            self.cookies = self.session.cookies
            if self.cookies_domain is not None:
                self._init_cookies()
        else:
            self.cookies = self.session.cookies

        self._init()
        self.initialize = util.noop

    def finalize(self):
        pass

    def items(self):
        return
        yield

    def skip(self, num):
        return 0

    def config(self, key, default=None):
        return config.interpolate(self._cfgpath, key, default)

    def config2(self, key, key2, default=None, sentinel=util.SENTINEL):
        value = self.config(key, sentinel)
        if value is not sentinel:
            return value
        return self.config(key2, default)

    def config_deprecated(self, key, deprecated, default=None,
                          sentinel=util.SENTINEL, history=set()):
        value = self.config(deprecated, sentinel)
        if value is not sentinel:
            if deprecated not in history:
                history.add(deprecated)
                self.log.warning("'%s' is deprecated. Use '%s' instead.",
                                 deprecated, key)
            default = value

        value = self.config(key, sentinel)
        if value is not sentinel:
            return value
        return default

    def config_accumulate(self, key):
        return config.accumulate(self._cfgpath, key)

    def config_instance(self, key, default=None):
        return default

    def _config_shared(self, key, default=None):
        return config.interpolate_common(
            ("extractor",), self._cfgpath, key, default)

    def _config_shared_accumulate(self, key):
        first = True
        extr = ("extractor",)

        for path in self._cfgpath:
            if first:
                first = False
                values = config.accumulate(extr + path, key)
            elif conf := config.get(extr, path[0]):
                values[:0] = config.accumulate(
                    (self.subcategory,), key, conf=conf)

        return values

    def request(self, url, method="GET", session=None, fatal=True,
                retries=None, retry_codes=None, expected=(), interval=True,
                encoding=None, notfound=None, **kwargs):
        if session is None:
            session = self.session
        if retries is None:
            retries = self._retries
        if retry_codes is None:
            retry_codes = self._retry_codes
        if "proxies" not in kwargs:
            kwargs["proxies"] = self._proxies
        if "timeout" not in kwargs:
            kwargs["timeout"] = self._timeout
        if "verify" not in kwargs:
            kwargs["verify"] = self._verify

        if "json" in kwargs:
            if (json := kwargs["json"]) is not None:
                kwargs["data"] = util.json_dumps(json).encode()
                del kwargs["json"]
                if headers := kwargs.get("headers"):
                    headers["Content-Type"] = "application/json"
                else:
                    kwargs["headers"] = {"Content-Type": "application/json"}

        response = challenge = None
        tries = 1

        if self._interval and interval:
            seconds = (self._interval() -
                       (time.time() - Extractor.request_timestamp))
            if seconds > 0.0:
                self.sleep(seconds, "request")

        while True:
            try:
                response = session.request(method, url, **kwargs)
            except requests.exceptions.ConnectionError as exc:
                try:
                    reason = exc.args[0].reason
                    cls = reason.__class__.__name__
                    pre, _, err = str(reason.args[-1]).partition(":")
                    msg = f" {cls}: {(err or pre).lstrip()}"
                except Exception:
                    msg = exc
                code = 0
            except (requests.exceptions.Timeout,
                    requests.exceptions.ChunkedEncodingError,
                    requests.exceptions.ContentDecodingError) as exc:
                msg = exc
                code = 0
            except (requests.exceptions.RequestException) as exc:
                msg = exc
                break
            else:
                code = response.status_code
                if self._write_pages:
                    self._dump_response(response)
                if (
                    code < 400 or
                    code in expected or
                    code < 500 and (
                        not fatal and code != 429 or fatal is None) or
                    fatal is ...
                ):
                    if encoding:
                        response.encoding = encoding
                    return response
                if notfound is not None and code == 404:
                    if notfound is True:
                        notfound = self.__class__.subcategory
                    self.status |= exception.NotFoundError.code
                    raise exception.NotFoundError(notfound)

                msg = f"'{code} {response.reason}' for '{response.url}'"

                challenge = util.detect_challenge(response)
                if challenge is not None:
                    self.log.warning(challenge)

                if code == 429 and self._handle_429(response):
                    continue
                elif code == 429 and self._interval_429:
                    pass
                elif code not in retry_codes and code < 500:
                    break

            finally:
                if interval:
                    Extractor.request_timestamp = time.time()

            self.log.debug("%s (%s/%s)", msg, tries, retries+1)
            if tries > retries:
                break

            seconds = tries
            if self._interval:
                s = self._interval()
                if seconds < s:
                    seconds = s
            if code == 429 and self._interval_429:
                s = self._interval_429()
                if seconds < s:
                    seconds = s
                self.wait(seconds=seconds, reason="429 Too Many Requests")
            else:
                self.sleep(seconds, "retry")
            tries += 1

        if not fatal or fatal is ...:
            self.log.warning(msg)
            return util.NullResponse(url, msg)

        if challenge is None:
            exc = exception.HttpError(msg, response)
        else:
            exc = exception.ChallengeError(challenge, response)
        self.status |= exc.code
        raise exc

    def request_location(self, url, **kwargs):
        kwargs.setdefault("method", "HEAD")
        kwargs.setdefault("allow_redirects", False)
        kwargs.setdefault("interval", False)
        return self.request(url, **kwargs).headers.get("location", "")

    def request_json(self, url, **kwargs):
        response = self.request(url, **kwargs)

        try:
            return util.json_loads(response.text)
        except Exception as exc:
            fatal = kwargs.get("fatal", True)
            if not fatal or fatal is ...:
                if challenge := util.detect_challenge(response):
                    self.log.warning(challenge)
                else:
                    self.log.warning("%s: %s", exc.__class__.__name__, exc)
                return {}
            raise

    def request_xml(self, url, xmlns=True, **kwargs):
        response = self.request(url, **kwargs)

        if xmlns:
            text = response.text
        else:
            text = response.text.replace(" xmlns=", " ns=")

        parser = ElementTree.XMLParser()
        try:
            parser.feed(text)
            return parser.close()
        except Exception as exc:
            fatal = kwargs.get("fatal", True)
            if not fatal or fatal is ...:
                if challenge := util.detect_challenge(response):
                    self.log.warning(challenge)
                else:
                    self.log.warning("%s: %s", exc.__class__.__name__, exc)
                return ElementTree.Element("")
            raise

    _handle_429 = util.false

    def wait(self, seconds=None, until=None, adjust=1.0,
             reason="rate limit"):
        now = time.time()

        if seconds:
            seconds = float(seconds)
            until = now + seconds
        elif until:
            if isinstance(until, dt.datetime):
                # convert to UTC timestamp
                until = dt.to_ts(until)
            else:
                until = float(until)
            seconds = until - now
        else:
            raise ValueError("Either 'seconds' or 'until' is required")

        seconds += adjust
        if seconds <= 0.0:
            return

        if reason:
            t = dt.datetime.fromtimestamp(until).time()
            isotime = f"{t.hour:02}:{t.minute:02}:{t.second:02}"
            self.log.info("Waiting until %s (%s)", isotime, reason)
        time.sleep(seconds)

    def sleep(self, seconds, reason):
        self.log.debug("Sleeping %.2f seconds (%s)",
                       seconds, reason)
        time.sleep(seconds)

    def input(self, prompt, echo=True):
        self._check_input_allowed(prompt)

        if echo:
            try:
                return input(prompt)
            except (EOFError, OSError):
                return None
        else:
            return getpass.getpass(prompt)

    def _check_input_allowed(self, prompt=""):
        input = self.config("input")
        if input is None:
            input = output.TTY_STDIN
        if not input:
            raise exception.AbortExtraction(
                f"User input required ({prompt.strip(' :')})")

    def _get_auth_info(self, password=None):
        """Return authentication information as (username, password) tuple"""
        username = self.config("username")

        if username or password:
            password = self.config("password")
            if not password:
                self._check_input_allowed("password")
                password = util.LazyPrompt()

        elif self.config("netrc", False):
            try:
                info = netrc.netrc().authenticators(self.category)
                username, _, password = info
            except (OSError, netrc.NetrcParseError) as exc:
                self.log.error("netrc: %s", exc)
            except TypeError:
                self.log.warning("netrc: No authentication info")

        return username, password

    def _init(self):
        pass

    def _init_options(self):
        self._write_pages = self.config("write-pages", False)
        self._retry_codes = self.config("retry-codes")
        self._retries = self.config("retries", 4)
        self._timeout = self.config("timeout", 30)
        self._verify = self.config("verify", True)
        self._proxies = util.build_proxy_map(self.config("proxy"), self.log)
        self._interval = util.build_duration_func(
            self.config("sleep-request", self.request_interval),
            self.request_interval_min,
        )
        self._interval_429 = util.build_duration_func(
            self.config("sleep-429", self.request_interval_429),
        )

        if self._retries < 0:
            self._retries = float("inf")
        if not self._retry_codes:
            self._retry_codes = ()

    def _init_session(self):
        self.session = session = requests.Session()
        headers = session.headers
        headers.clear()
        ssl_options = ssl_ciphers = 0

        # .netrc Authorization headers are alwsays disabled
        session.trust_env = True if self.config("proxy-env", True) else False

        browser = self.config("browser")
        if browser is None:
            browser = self.browser
        if browser and isinstance(browser, str):
            browser, _, platform = browser.lower().partition(":")

            if not platform or platform == "auto":
                platform = ("Windows NT 10.0; Win64; x64"
                            if util.WINDOWS else "X11; Linux x86_64")
            elif platform == "windows":
                platform = "Windows NT 10.0; Win64; x64"
            elif platform == "linux":
                platform = "X11; Linux x86_64"
            elif platform == "macos":
                platform = "Macintosh; Intel Mac OS X 15.5"

            if browser == "chrome":
                if platform.startswith("Macintosh"):
                    platform = platform.replace(".", "_")
            else:
                browser = "firefox"

            for key, value in HEADERS[browser]:
                if value and "{}" in value:
                    headers[key] = value.replace("{}", platform)
                else:
                    headers[key] = value

            ssl_options |= (ssl.OP_NO_SSLv2 | ssl.OP_NO_SSLv3 |
                            ssl.OP_NO_TLSv1 | ssl.OP_NO_TLSv1_1)
            ssl_ciphers = CIPHERS[browser]
        else:
            headers["User-Agent"] = self.useragent
            headers["Accept"] = "*/*"
            headers["Accept-Language"] = "en-US,en;q=0.5"

            ssl_ciphers = self.ciphers
            if ssl_ciphers is not None and ssl_ciphers in CIPHERS:
                ssl_ciphers = CIPHERS[ssl_ciphers]

        if BROTLI:
            headers["Accept-Encoding"] = "gzip, deflate, br"
        else:
            headers["Accept-Encoding"] = "gzip, deflate"
        if ZSTD:
            headers["Accept-Encoding"] += ", zstd"

        if referer := self.config("referer", self.referer):
            if isinstance(referer, str):
                headers["Referer"] = referer
            elif self.root:
                headers["Referer"] = self.root + "/"

        custom_ua = self.config("user-agent")
        if not custom_ua or custom_ua == "auto":
            pass
        elif custom_ua == "browser":
            headers["User-Agent"] = _browser_useragent(None)
        elif custom_ua[0] == "@":
            headers["User-Agent"] = _browser_useragent(custom_ua[1:])
        elif custom_ua[0] == "+":
            custom_ua = custom_ua[1:].lower()
            if custom_ua in {"firefox", "ff"}:
                headers["User-Agent"] = util.USERAGENT_FIREFOX
            elif custom_ua in {"chrome", "cr"}:
                headers["User-Agent"] = util.USERAGENT_CHROME
            elif custom_ua in {"gallery-dl", "gallerydl", "gdl"}:
                headers["User-Agent"] = util.USERAGENT_GALLERYDL
            elif custom_ua in {"google-bot", "googlebot", "bot"}:
                headers["User-Agent"] = "Googlebot-Image/1.0"
            else:
                self.log.warning(
                    "Unsupported User-Agent preset '%s'", custom_ua)
        elif self.useragent is Extractor.useragent and not self.browser or \
                custom_ua is not config.get(("extractor",), "user-agent"):
            headers["User-Agent"] = custom_ua

        if custom_headers := self.config("headers"):
            if isinstance(custom_headers, str):
                if custom_headers in HEADERS:
                    custom_headers = HEADERS[custom_headers]
                else:
                    self.log.error("Invalid 'headers' value '%s'",
                                   custom_headers)
                    custom_headers = ()
            headers.update(custom_headers)

        if custom_ciphers := self.config("ciphers"):
            if isinstance(custom_ciphers, list):
                ssl_ciphers = ":".join(custom_ciphers)
            elif custom_ciphers in CIPHERS:
                ssl_ciphers = CIPHERS[custom_ciphers]
            else:
                ssl_ciphers = custom_ciphers

        if source_address := self.config("source-address"):
            if isinstance(source_address, str):
                source_address = (source_address, 0)
            else:
                source_address = (source_address[0], source_address[1])

        tls12 = self.config("tls12")
        if tls12 is None:
            tls12 = self.tls12
        if not tls12:
            ssl_options |= ssl.OP_NO_TLSv1_2
            self.log.debug("TLS 1.2 disabled.")

        if self.config("truststore"):
            try:
                from truststore import SSLContext as ssl_ctx
            except ImportError as exc:
                self.log.error("%s: %s", exc.__class__.__name__, exc)
                ssl_ctx = None
        else:
            ssl_ctx = None

        adapter = _build_requests_adapter(
            ssl_options, ssl_ciphers, ssl_ctx, source_address)
        session.mount("https://", adapter)
        session.mount("http://", adapter)

    def _init_cookies(self):
        """Populate the session's cookiejar"""
        if cookies := self.config("cookies"):
            if select := self.config("cookies-select"):
                if select == "rotate":
                    cookies = cookies[self.cookies_index % len(cookies)]
                    Extractor.cookies_index += 1
                else:
                    cookies = random.choice(cookies)
            self.cookies_load(cookies)

    def cookies_load(self, cookies_source):
        if isinstance(cookies_source, dict):
            self.cookies_update_dict(cookies_source, self.cookies_domain)

        elif isinstance(cookies_source, str):
            path = util.expand_path(cookies_source)
            try:
                with open(path, encoding="utf-8") as fp:
                    cookies = util.cookiestxt_load(fp)
            except ValueError as exc:
                self.log.warning("cookies: Invalid Netscape cookies.txt file "
                                 "'%s' (%s: %s)",
                                 cookies_source, exc.__class__.__name__, exc)
            except Exception as exc:
                self.log.warning("cookies: Failed to load '%s' (%s: %s)",
                                 cookies_source, exc.__class__.__name__, exc)
            else:
                self.log.debug("cookies: Loading cookies from '%s'",
                               cookies_source)
                set_cookie = self.cookies.set_cookie
                for cookie in cookies:
                    set_cookie(cookie)
                self.cookies_file = path

        elif isinstance(cookies_source, (list, tuple)):
            key = tuple(cookies_source)
            cookies = CACHE_COOKIES.get(key)

            if cookies is None:
                from ..cookies import load_cookies
                try:
                    cookies = load_cookies(cookies_source)
                except Exception as exc:
                    self.log.warning("cookies: %s", exc)
                    cookies = ()
                else:
                    CACHE_COOKIES[key] = cookies
            else:
                self.log.debug("cookies: Using cached cookies from %s", key)

            set_cookie = self.cookies.set_cookie
            for cookie in cookies:
                set_cookie(cookie)

        else:
            self.log.error(
                "cookies: Expected 'dict', 'list', or 'str' value for "
                "'cookies' option, got '%s' instead (%r)",
                cookies_source.__class__.__name__, cookies_source)

    def cookies_store(self):
        """Store the session's cookies in a cookies.txt file"""
        export = self.config("cookies-update", True)
        if not export:
            return

        if isinstance(export, str):
            path = util.expand_path(export)
        else:
            path = self.cookies_file
            if not path:
                return

        path_tmp = path + ".tmp"
        try:
            with open(path_tmp, "w", encoding="utf-8") as fp:
                util.cookiestxt_store(fp, self.cookies)
            os.replace(path_tmp, path)
        except OSError as exc:
            self.log.error("cookies: Failed to write to '%s' "
                           "(%s: %s)", path, exc.__class__.__name__, exc)

    def cookies_update(self, cookies, domain=""):
        """Update the session's cookiejar with 'cookies'"""
        if isinstance(cookies, dict):
            self.cookies_update_dict(cookies, domain or self.cookies_domain)
        else:
            set_cookie = self.cookies.set_cookie
            try:
                cookies = iter(cookies)
            except TypeError:
                set_cookie(cookies)
            else:
                for cookie in cookies:
                    set_cookie(cookie)

    def cookies_update_dict(self, cookiedict, domain):
        """Update cookiejar with name-value pairs from a dict"""
        set_cookie = self.cookies.set
        for name, value in cookiedict.items():
            set_cookie(name, value, domain=domain)

    def cookies_check(self, cookies_names, domain=None, subdomains=False):
        """Check if all 'cookies_names' are in the session's cookiejar"""
        if not self.cookies:
            return False

        if domain is None:
            domain = self.cookies_domain
        names = set(cookies_names)
        now = time.time()

        for cookie in self.cookies:
            if cookie.name not in names:
                continue

            if not domain or cookie.domain == domain:
                pass
            elif not subdomains or not cookie.domain.endswith(domain):
                continue

            if cookie.expires:
                diff = int(cookie.expires - now)

                if diff <= 0:
                    self.log.warning(
                        "cookies: %s/%s expired at %s",
                        cookie.domain.lstrip("."), cookie.name,
                        dt.datetime.fromtimestamp(cookie.expires))
                    continue

                elif diff <= 86400:
                    hours = diff // 3600
                    self.log.warning(
                        "cookies: %s/%s will expire in less than %s hour%s",
                        cookie.domain.lstrip("."), cookie.name,
                        hours + 1, "s" if hours else "")

            names.discard(cookie.name)
            if not names:
                return True
        return False

    def _extract_jsonld(self, page):
        return util.json_loads(
            text.extr(page, '<script type="application/ld+json">',
                      "</script>") or
            text.extr(page, "<script type='application/ld+json'>",
                      "</script>"))

    def _extract_nextdata(self, page):
        return util.json_loads(
            text.extr(page, ' id="__NEXT_DATA__" type="application/json">',
                      "</script>") or
            text.extr(page, " id='__NEXT_DATA__' type='application/json'>",
                      "</script>"))

    def _cache(self, func, maxage, keyarg=None):
        #  return cache.DatabaseCacheDecorator(func, maxage, keyarg)
        return cache.DatabaseCacheDecorator(func, keyarg, maxage)

    def _cache_memory(self, func, maxage=None, keyarg=None):
        return cache.Memcache()

    def _get_date_min_max(self, dmin=None, dmax=None):
        """Retrieve and parse 'date-min' and 'date-max' config values"""
        def get(key, default):
            ts = self.config(key, default)
            if isinstance(ts, str):
                dt_obj = dt.parse_iso(ts) if fmt is None else dt.parse(ts, fmt)
                if dt_obj is dt.NONE:
                    self.log.warning(
                        "Unable to parse '%s': Invalid %s string '%s'",
                        key, "isoformat" if fmt is None else "date", ts)
                    ts = default
                else:
                    ts = int(dt.to_ts(dt_obj))
            return ts
        fmt = self.config("date-format")
        return get("date-min", dmin), get("date-max", dmax)

    @classmethod
    def _dump(cls, obj):
        util.dump_json(obj, ensure_ascii=False, indent=2)

    def _dump_response(self, response, history=True):
        """Write the response content to a .txt file in the current directory.

        The file name is derived from the response url,
        replacing special characters with "_"
        """
        if history:
            for resp in response.history:
                self._dump_response(resp, False)

        if hasattr(Extractor, "_dump_index"):
            Extractor._dump_index += 1
        else:
            Extractor._dump_index = 1
            Extractor._dump_sanitize = util.re_compile(
                r"[\\\\|/<>:\"?*&=#]+").sub

        fname = (f"{Extractor._dump_index:>02}_"
                 f"{Extractor._dump_sanitize('_', response.url)}")

        if util.WINDOWS:
            path = os.path.abspath(fname)[:255]
        else:
            path = fname[:251]

        try:
            with open(path + ".txt", 'wb') as fp:
                util.dump_response(
                    response, fp,
                    headers=(self._write_pages in ("all", "ALL")),
                    hide_auth=(self._write_pages != "ALL")
                )
            self.log.info("Writing '%s' response to '%s'",
                          response.url, path + ".txt")
        except Exception as e:
            self.log.warning("Failed to dump HTTP request (%s: %s)",
                             e.__class__.__name__, e)


class GalleryExtractor(Extractor):

    subcategory = "gallery"
    filename_fmt = "{category}_{gallery_id}_{num:>03}.{extension}"
    directory_fmt = ("{category}", "{gallery_id} {title}")
    archive_fmt = "{gallery_id}_{num}"
    enum = "num"

    def __init__(self, match, url=None):
        Extractor.__init__(self, match)

        if url is None and (path := self.groups[0]) and path[0] == "/":
            self.page_url = self.root + path
        else:
            self.page_url = url

    def items(self):
        self.login()

        if self.page_url:
            page = self.request(
                self.page_url, notfound=self.subcategory).text
        else:
            page = None

        data = self.metadata(page)
        imgs = self.images(page)
        assets = self.assets(page)

        if "count" in data:
            if self.config("page-reverse"):
                images = util.enumerate_reversed(imgs, 1, data["count"])
            else:
                images = zip(
                    range(1, data["count"]+1),
                    imgs,
                )
        else:
            enum = enumerate
            try:
                data["count"] = len(imgs)
            except TypeError:
                pass
            else:
                if self.config("page-reverse"):
                    enum = util.enumerate_reversed
            images = enum(imgs, 1)

        yield Message.Directory, "", data
        enum_key = self.enum

        if assets:
            for asset in assets:
                url = asset["url"]
                asset.update(data)
                asset[enum_key] = 0
                if "extension" not in asset:
                    text.nameext_from_url(url, asset)
                yield Message.Url, url, asset

        for data[enum_key], (url, imgdata) in images:
            if imgdata:
                data.update(imgdata)
                if "extension" not in imgdata:
                    text.nameext_from_url(url, data)
            else:
                text.nameext_from_url(url, data)
            yield Message.Url, url, data

    def login(self):
        """Login and set necessary cookies"""

    def metadata(self, page):
        """Return a dict with general metadata"""

    def images(self, page):
        """Return a list or iterable of all (image-url, metadata)-tuples"""

    def assets(self, page):
        """Return an iterable of additional gallery assets

        Each asset must be a 'dict' containing at least 'url' and 'type'
        """


class ChapterExtractor(GalleryExtractor):

    subcategory = "chapter"
    directory_fmt = (
        "{category}", "{manga}",
        "{volume:?v/ />02}c{chapter:>03}{chapter_minor:?//}{title:?: //}")
    filename_fmt = (
        "{manga}_c{chapter:>03}{chapter_minor:?//}_{page:>03}.{extension}")
    archive_fmt = (
        "{manga}_{chapter}{chapter_minor}_{page}")
    enum = "page"


class MangaExtractor(Extractor):

    subcategory = "manga"
    categorytransfer = True
    chapterclass = None
    reverse = True

    def __init__(self, match, url=None):
        Extractor.__init__(self, match)

        if url is None and (path := self.groups[0]) and path[0] == "/":
            self.page_url = self.root + path
        else:
            self.page_url = url

        if self.config("chapter-reverse", False):
            self.reverse = not self.reverse

    def items(self):
        self.login()

        if self.page_url:
            page = self.request(self.page_url, notfound=self.subcategory).text
        else:
            page = None

        chapters = self.chapters(page)
        if self.reverse:
            chapters.reverse()

        for chapter, data in chapters:
            data["_extractor"] = self.chapterclass
            yield Message.Queue, chapter, data

    def login(self):
        """Login and set necessary cookies"""

    def chapters(self, page):
        """Return a list of all (chapter-url, metadata)-tuples"""


class Dispatch():
    subcategory = "user"
    cookies_domain = None
    finalize = Extractor.finalize
    skip = Extractor.skip

    def __iter__(self):
        return self.items()

    def initialize(self):
        pass

    def _dispatch_extractors(self, extractor_data, default=(), alt=None):
        extractors = {
            data[0].subcategory: data
            for data in extractor_data
        }

        if alt is not None:
            for sub, sub_alt, url in alt:
                if url is None:
                    extractors[sub_alt] = extractors[sub]
                else:
                    extractors[sub_alt] = (extractors[sub][0], url)

        include = self.config("include", default) or ()
        if include == "all":
            include = extractors
        elif isinstance(include, str):
            include = include.replace(" ", "").split(",")

        results = []
        for category in include:
            try:
                extr, url = extractors[category]
            except KeyError:
                self.log.warning("Invalid include '%s'", category)
            else:
                results.append((Message.Queue, url, {"_extractor": extr}))
        return iter(results)


class AsynchronousMixin():
    """Run info extraction in a separate thread"""

    def __iter__(self):
        self.initialize()

        messages = queue.Queue(5)
        thread = threading.Thread(
            target=self.async_items,
            args=(messages,),
            daemon=True,
        )

        thread.start()
        while True:
            msg = messages.get()
            if msg is None:
                thread.join()
                return
            if isinstance(msg, Exception):
                thread.join()
                raise msg
            yield msg
            messages.task_done()

    def async_items(self, messages):
        try:
            for msg in self.items():
                messages.put(msg)
        except Exception as exc:
            messages.put(exc)
        messages.put(None)


class BaseExtractor(Extractor):
    instances = ()

    def __init__(self, match):
        if not self.category:
            self._init_category(match)
        Extractor.__init__(self, match)

    def _init_category(self, match):
        for index, group in enumerate(match.groups()):
            if group is not None:
                if index:
                    self.category, self.root, info = self.instances[index-1]
                    if not self.root:
                        self.root = text.root_from_url(match[0])
                    self.config_instance = info.get
                else:
                    self.root = group
                    self.category = group.partition("://")[2]
                break

    @classmethod
    def update(cls, instances):
        if extra_instances := config.get(("extractor",), cls.basecategory):
            for category, info in extra_instances.items():
                if isinstance(info, dict) and "root" in info:
                    instances[category] = info

        pattern_list = []
        instance_list = cls.instances = []
        for category, info in instances.items():
            if root := info["root"]:
                root = root.rstrip("/")
            instance_list.append((category, root, info))

            pattern = info.get("pattern")
            if not pattern:
                pattern = re.escape(root[root.index(":") + 3:])
            pattern_list.append(pattern + "()")

        return (
            r"(?:" + cls.basecategory + r":(https?://[^/?#]+)|"
            r"(?:https?://)?(?:" + "|".join(pattern_list) + r"))"
        )


class RequestsAdapter(HTTPAdapter):

    def __init__(self, ssl_context=None, source_address=None):
        self.ssl_context = ssl_context
        self.source_address = source_address
        HTTPAdapter.__init__(self)

    def init_poolmanager(self, *args, **kwargs):
        kwargs["ssl_context"] = self.ssl_context
        kwargs["source_address"] = self.source_address
        return HTTPAdapter.init_poolmanager(self, *args, **kwargs)

    def proxy_manager_for(self, *args, **kwargs):
        kwargs["ssl_context"] = self.ssl_context
        kwargs["source_address"] = self.source_address
        return HTTPAdapter.proxy_manager_for(self, *args, **kwargs)


def _build_requests_adapter(
        ssl_options, ssl_ciphers, ssl_ctx, source_address):

    key = (ssl_options, ssl_ciphers, ssl_ctx, source_address)
    try:
        return CACHE_ADAPTERS[key]
    except KeyError:
        pass

    if ssl_options or ssl_ciphers or ssl_ctx:
        if ssl_ctx is None:
            ssl_context = urllib3.connection.create_urllib3_context(
                options=ssl_options or None, ciphers=ssl_ciphers)
            if not requests.__version__ < "2.32":
                # https://github.com/psf/requests/pull/6731
                ssl_context.load_verify_locations(requests.certs.where())
        else:
            ssl_ctx_orig = urllib3.util.ssl_.SSLContext
            try:
                urllib3.util.ssl_.SSLContext = ssl_ctx
                ssl_context = urllib3.connection.create_urllib3_context(
                    options=ssl_options or None, ciphers=ssl_ciphers)
            finally:
                urllib3.util.ssl_.SSLContext = ssl_ctx_orig
        ssl_context.check_hostname = False
    else:
        ssl_context = None

    adapter = CACHE_ADAPTERS[key] = RequestsAdapter(
        ssl_context, source_address)
    return adapter


@cache.cache(maxage=86400, keyarg=0)
def _browser_useragent(browser):
    """Get User-Agent header from default browser"""
    import webbrowser
    try:
        open = webbrowser.get(browser).open
    except webbrowser.Error:
        if not browser:
            raise
        import shutil
        if not (browser := shutil.which(browser)):
            raise

        def open(url):
            util.Popen((browser, url),
                       start_new_session=False if util.WINDOWS else True)

    import socket
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("127.0.0.1", 0))
    server.listen(1)

    host, port = server.getsockname()
    open(f"http://{host}:{port}/user-agent")

    client = server.accept()[0]
    server.close()

    for line in client.recv(1024).split(b"\r\n"):
        key, _, value = line.partition(b":")
        if key.strip().lower() == b"user-agent":
            useragent = value.strip()
            break
    else:
        useragent = b""

    client.send(b"HTTP/1.1 200 OK\r\n\r\n" + useragent)
    client.close()

    return useragent.decode()


CACHE_ADAPTERS = {}
CACHE_COOKIES = {}
CATEGORY_MAP = ()


HEADERS_FIREFOX_140 = (
    ("User-Agent", "Mozilla/5.0 ({}; rv:140.0) Gecko/20100101 Firefox/140.0"),
    ("Accept", "text/html,application/xhtml+xml,"
               "application/xml;q=0.9,*/*;q=0.8"),
    ("Accept-Language", "en-US,en;q=0.5"),
    ("Accept-Encoding", None),
    ("Connection", "keep-alive"),
    ("Content-Type", None),
    ("Content-Length", None),
    ("Referer", None),
    ("Origin", None),
    ("Cookie", None),
    ("Sec-Fetch-Dest", "empty"),
    ("Sec-Fetch-Mode", "cors"),
    ("Sec-Fetch-Site", "same-origin"),
    ("TE", "trailers"),
)
HEADERS_FIREFOX_128 = (
    ("User-Agent", "Mozilla/5.0 ({}; rv:128.0) Gecko/20100101 Firefox/128.0"),
    ("Accept", "text/html,application/xhtml+xml,application/xml;q=0.9,"
               "image/avif,image/webp,image/png,image/svg+xml,*/*;q=0.8"),
    ("Accept-Language", "en-US,en;q=0.5"),
    ("Accept-Encoding", None),
    ("Referer", None),
    ("Connection", "keep-alive"),
    ("Upgrade-Insecure-Requests", "1"),
    ("Cookie", None),
    ("Sec-Fetch-Dest", "empty"),
    ("Sec-Fetch-Mode", "no-cors"),
    ("Sec-Fetch-Site", "same-origin"),
    ("TE", "trailers"),
)
HEADERS_CHROMIUM_138 = (
    ("Connection", "keep-alive"),
    ("sec-ch-ua", '"Not)A;Brand";v="8", "Chromium";v="138"'),
    ("sec-ch-ua-mobile", "?0"),
    ("sec-ch-ua-platform", '"Linux"'),
    ("Upgrade-Insecure-Requests", "1"),
    ("User-Agent", "Mozilla/5.0 ({}) AppleWebKit/537.36 (KHTML, "
                   "like Gecko) Chrome/138.0.0.0 Safari/537.36"),
    ("Accept", "text/html,application/xhtml+xml,application/xml;q=0.9,"
               "image/avif,image/webp,image/apng,*/*;q=0.8,"
               "application/signed-exchange;v=b3;q=0.7"),
    ("Referer", None),
    ("Sec-Fetch-Site", "same-origin"),
    ("Sec-Fetch-Mode", "no-cors"),
    #  ("Sec-Fetch-User", "?1"),
    ("Sec-Fetch-Dest", "empty"),
    ("Accept-Encoding", None),
    ("Accept-Language", "en-US,en;q=0.9"),
)
HEADERS_CHROMIUM_111 = (
    ("Connection", "keep-alive"),
    ("Upgrade-Insecure-Requests", "1"),
    ("User-Agent", "Mozilla/5.0 ({}) AppleWebKit/537.36 (KHTML, "
                   "like Gecko) Chrome/111.0.0.0 Safari/537.36"),
    ("Accept", "text/html,application/xhtml+xml,application/xml;q=0.9,"
               "image/avif,image/webp,image/apng,*/*;q=0.8,"
               "application/signed-exchange;v=b3;q=0.7"),
    ("Referer", None),
    ("Sec-Fetch-Site", "same-origin"),
    ("Sec-Fetch-Mode", "no-cors"),
    ("Sec-Fetch-Dest", "empty"),
    ("Accept-Encoding", None),
    ("Accept-Language", "en-US,en;q=0.9"),
    ("cookie", None),
    ("content-length", None),
)
HEADERS = {
    "firefox"    : HEADERS_FIREFOX_140,
    "firefox/140": HEADERS_FIREFOX_140,
    "firefox/128": HEADERS_FIREFOX_128,
    "chrome"     : HEADERS_CHROMIUM_138,
    "chrome/138" : HEADERS_CHROMIUM_138,
    "chrome/111" : HEADERS_CHROMIUM_111,
}

CIPHERS_FIREFOX = (
    "TLS_AES_128_GCM_SHA256:"
    "TLS_CHACHA20_POLY1305_SHA256:"
    "TLS_AES_256_GCM_SHA384:"
    "ECDHE-ECDSA-AES128-GCM-SHA256:"
    "ECDHE-RSA-AES128-GCM-SHA256:"
    "ECDHE-ECDSA-CHACHA20-POLY1305:"
    "ECDHE-RSA-CHACHA20-POLY1305:"
    "ECDHE-ECDSA-AES256-GCM-SHA384:"
    "ECDHE-RSA-AES256-GCM-SHA384:"
    "ECDHE-ECDSA-AES256-SHA:"
    "ECDHE-ECDSA-AES128-SHA:"
    "ECDHE-RSA-AES128-SHA:"
    "ECDHE-RSA-AES256-SHA:"
    "AES128-GCM-SHA256:"
    "AES256-GCM-SHA384:"
    "AES128-SHA:"
    "AES256-SHA"
)
CIPHERS_CHROMIUM = (
    "TLS_AES_128_GCM_SHA256:"
    "TLS_AES_256_GCM_SHA384:"
    "TLS_CHACHA20_POLY1305_SHA256:"
    "ECDHE-ECDSA-AES128-GCM-SHA256:"
    "ECDHE-RSA-AES128-GCM-SHA256:"
    "ECDHE-ECDSA-AES256-GCM-SHA384:"
    "ECDHE-RSA-AES256-GCM-SHA384:"
    "ECDHE-ECDSA-CHACHA20-POLY1305:"
    "ECDHE-RSA-CHACHA20-POLY1305:"
    "ECDHE-RSA-AES128-SHA:"
    "ECDHE-RSA-AES256-SHA:"
    "AES128-GCM-SHA256:"
    "AES256-GCM-SHA384:"
    "AES128-SHA:"
    "AES256-SHA"
)
CIPHERS = {
    "firefox"    : CIPHERS_FIREFOX,
    "firefox/140": CIPHERS_FIREFOX,
    "firefox/128": CIPHERS_FIREFOX,
    "chrome"     : CIPHERS_CHROMIUM,
    "chrome/138" : CIPHERS_CHROMIUM,
    "chrome/111" : CIPHERS_CHROMIUM,
}


# disable Basic Authorization header injection from .netrc data
try:
    requests.sessions.get_netrc_auth = lambda _: None
except Exception:
    pass

# detect brotli support
try:
    BROTLI = urllib3.response.brotli is not None
except AttributeError:
    BROTLI = False

# detect zstandard support
try:
    ZSTD = urllib3.response.HAS_ZSTD
except AttributeError:
    ZSTD = False

# set (urllib3) warnings filter
action = config.get((), "warnings", "default")
if action:
    try:
        import warnings
        warnings.simplefilter(action, urllib3.exceptions.HTTPWarning)
    except Exception:
        pass
del action

================
File: gallery_dl/extractor/__init__.py
================
# -*- coding: utf-8 -*-

# Copyright 2015-2025 Mike Fährmann
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 as
# published by the Free Software Foundation.

import sys
from ..text import re_compile

modules = [
    "hitomi",
    "nozomi",
    "noop",
    "generic",
]


def find(url):
    """Find a suitable extractor for the given URL"""
    for cls in _list_classes():
        if match := cls.pattern.match(url):
            return cls(match)
    return None


def add(cls):
    """Add 'cls' to the list of available extractors"""
    if isinstance(cls.pattern, str):
        cls.pattern = re_compile(cls.pattern)
    _cache.append(cls)
    return cls


def add_module(module):
    """Add all extractors in 'module' to the list of available extractors"""
    if classes := _get_classes(module):
        if isinstance(classes[0].pattern, str):
            for cls in classes:
                cls.pattern = re_compile(cls.pattern)
        _cache.extend(classes)
    return classes


def extractors():
    """Yield all available extractor classes"""
    return sorted(
        _list_classes(),
        key=lambda x: x.__name__
    )


# --------------------------------------------------------------------
# internals


def _list_classes():
    """Yield available extractor classes"""
    yield from _cache

    for module in _module_iter:
        yield from add_module(module)

    globals()["_list_classes"] = lambda : _cache


def _modules_internal():
    globals_ = globals()
    for module_name in modules:
        yield __import__(module_name, globals_, None, None, 1)


def _modules_path(path, files):
    sys.path.insert(0, path)
    try:
        return [
            __import__(name[:-3])
            for name in files
            if name.endswith(".py")
        ]
    finally:
        del sys.path[0]


def _get_classes(module):
    """Return a list of all extractor classes in a module"""
    return [
        cls for cls in module.__dict__.values() if (
            hasattr(cls, "pattern") and cls.__module__ == module.__name__
        )
    ]


_cache = []
_module_iter = _modules_internal()





================================================================
End of Codebase
================================================================
