from __future__ import annotations

import base64
import re
import subprocess
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from http.cookiejar import CookieJar
from pathlib import Path
from typing import Callable, Iterable

import browser_cookie3
from curl_cffi import requests as curl_requests

from app.common import safe_join, safe_segment
from app.domain import AppConfig


USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
MISSAV_HOSTS = {"missav.ai", "www.missav.ai"}
MISSAV_OUTPUT_BASE_DIR = Path("/Volumes/Storage/Camrecs/av")


@dataclass(frozen=True)
class ManualRecordingJob:
    pid: int
    output_path: str
    log_path: str


class MissavRecordingService:
    def __init__(
        self,
        *,
        cookie_loader: Callable[[str], Iterable] | None = None,
        opener_factory: Callable[[CookieJar | Iterable, list[tuple[str, str]]], object] | None = None,
        process_launcher: Callable[..., object] | None = None,
        yt_dlp_runner: Callable[..., object] | None = None,
        curl_fetcher: Callable[..., object] | None = None,
        output_base_dir: Path | str = MISSAV_OUTPUT_BASE_DIR,
    ) -> None:
        self._cookie_loader = cookie_loader or self._load_browser_cookies
        self._opener_factory = opener_factory or self._build_opener
        self._process_launcher = process_launcher or subprocess.Popen
        self._yt_dlp_runner = yt_dlp_runner or subprocess.run
        self._curl_fetcher = curl_fetcher or curl_requests.get
        self._output_base_dir = Path(output_base_dir)

    def start(self, url: str, config: AppConfig) -> ManualRecordingJob:
        parsed = urllib.parse.urlparse(url.strip())
        if parsed.scheme not in {"http", "https"} or parsed.netloc.lower() not in MISSAV_HOSTS:
            raise ValueError("Enter a missav.ai URL")
        video_id = self._extract_video_id(parsed)
        output_path = self._output_path(video_id)
        log_path = output_path.with_suffix(".log")

        missav_cookies = self._load_cookies("missav.ai")
        page_html = self._fetch_missav_page(url, missav_cookies, config)
        master_playlist = self._select_master_playlist(self.extract_m3u8_from_html(page_html))
        stream_domain = urllib.parse.urlparse(master_playlist).netloc
        stream_cookies = self._load_cookies(stream_domain) or missav_cookies
        playlist = self._fetch_text(
            master_playlist,
            stream_cookies,
            [
                ("User-Agent", USER_AGENT),
                ("Referer", "https://missav.ai/"),
                ("Origin", "https://missav.ai"),
            ],
        )
        target_stream = self._select_best_stream(master_playlist, playlist)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        command = [
            sys.executable,
            "-m",
            "yt_dlp",
            "--impersonate",
            "chrome",
            "--newline",
            "--concurrent-fragments",
            "4",
            "--add-header",
            "Referer: https://missav.ai/",
            "--add-header",
            "Origin: https://missav.ai",
            "-o",
            str(output_path),
            target_stream,
        ]
        log_file = log_path.open("a", encoding="utf-8")
        try:
            process = self._process_launcher(command, stdout=log_file, stderr=log_file, text=True)
        except Exception:
            log_file.close()
            raise
        log_file.close()
        self._reap_process(process)
        return ManualRecordingJob(pid=int(process.pid), output_path=str(output_path), log_path=str(log_path))

    @staticmethod
    def extract_m3u8_from_html(html: str) -> list[str]:
        packed_pattern = re.compile(
            r"eval\(function\(p,a,c,k,e,d\).*?\}\('((?:\\.|[^'])*)',\s*(\d+),\s*(\d+),\s*'((?:\\.|[^'])*)'\.split\('\|'\)",
            re.DOTALL,
        )
        for payload, _radix, _count, words in packed_pattern.findall(html):
            unpacked = MissavRecordingService._unpack_packer_payload(payload, words)
            links = re.findall(r"https?://[^\s'\"\\]+\.m3u8", unpacked)
            if links:
                return list(dict.fromkeys(links))
        return re.findall(r"https?://[^\s'\"\\]+\.m3u8", html)

    @staticmethod
    def _unpack_packer_payload(payload: str, words: str) -> str:
        payload = payload.replace("\\'", "'").replace('\\"', '"').replace("\\/", "/").replace("\\\\", "\\")
        words = words.replace("\\'", "'").replace('\\"', '"').replace("\\/", "/").replace("\\\\", "\\")
        word_map = {
            MissavRecordingService._base36(index): word or MissavRecordingService._base36(index)
            for index, word in enumerate(words.split("|"))
        }
        return re.sub(r"\b[0-9a-z]+\b", lambda match: word_map.get(match.group(0), match.group(0)), payload)

    @staticmethod
    def _base36(value: int) -> str:
        if value == 0:
            return "0"
        chars = "0123456789abcdefghijklmnopqrstuvwxyz"
        digits: list[str] = []
        while value:
            value, remainder = divmod(value, 36)
            digits.append(chars[remainder])
        return "".join(reversed(digits))

    def _fetch_text(self, url: str, cookies, headers: list[tuple[str, str]]) -> str:
        opener = self._opener_factory(cookies, headers)
        try:
            with opener.open(url) as response:
                return response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            if exc.code == 403:
                try:
                    return self._fetch_text_with_impersonation(url, headers)
                except RuntimeError:
                    pass
            raise RuntimeError(f"MissAV fetch failed with HTTP {exc.code}: {exc.reason}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"MissAV fetch failed: {exc.reason}") from exc

    def _fetch_missav_page(self, url: str, cookies, config: AppConfig) -> str:
        if not cookies:
            return self._fetch_missav_page_with_yt_dlp(url, config)
        try:
            return self._fetch_text(
                url,
                cookies,
                [
                    ("User-Agent", USER_AGENT),
                    ("Accept", "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8"),
                    ("Accept-Language", "en-US,en;q=0.5"),
                ],
            )
        except RuntimeError as exc:
            if "HTTP 403" not in str(exc):
                raise
            return self._fetch_missav_page_with_yt_dlp(url, config)

    def _fetch_text_with_impersonation(self, url: str, headers: list[tuple[str, str]]) -> str:
        response = self._curl_fetcher(
            url,
            impersonate="chrome",
            headers={name: value for name, value in headers},
            timeout=60,
        )
        status_code = int(getattr(response, "status_code", 0))
        if status_code >= 400:
            reason = getattr(response, "reason", "")
            raise RuntimeError(f"MissAV impersonated fetch failed with HTTP {status_code}: {reason}")
        return str(getattr(response, "text", ""))

    def _fetch_missav_page_with_yt_dlp(self, url: str, config: AppConfig) -> str:
        command = [
            sys.executable,
            "-m",
            "yt_dlp",
            "--extractor-args",
            "generic:impersonate",
            "--cookies-from-browser",
            config.cookies_from_browser,
            "--dump-pages",
            "--skip-download",
            url,
        ]
        result = self._yt_dlp_runner(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        for line in sorted(str(getattr(result, "stdout", "")).splitlines(), key=len, reverse=True):
            try:
                html = base64.b64decode(line, validate=True).decode("utf-8", "replace")
            except Exception:
                continue
            if "<html" in html.lower():
                return html
        stderr = str(getattr(result, "stderr", "")).strip()
        raise RuntimeError(f"MissAV yt-dlp page fallback failed: {stderr or 'no HTML dump found'}")

    def _extract_video_id(self, parsed: urllib.parse.ParseResult) -> str:
        segments = [segment for segment in parsed.path.split("/") if segment]
        if not segments:
            raise ValueError("MissAV URL must include a video id")
        return safe_segment(segments[-1], field="video id")

    def _output_path(self, video_id: str) -> Path:
        output_dir = safe_join(self._output_base_dir, "MissAV")
        output = safe_join(output_dir, f"{video_id}.mp4")
        if not output.exists():
            return output
        index = 1
        while True:
            candidate = safe_join(output_dir, f"{video_id}__{index}.mp4")
            if not candidate.exists():
                return candidate
            index += 1

    def _select_master_playlist(self, links: list[str]) -> str:
        if not links:
            raise RuntimeError("Could not find any HLS playlist on the MissAV page")
        for link in links:
            if "playlist.m3u8" in link:
                return link
        return links[0]

    def _select_best_stream(self, master_playlist: str, playlist: str) -> str:
        variants = re.findall(r"RESOLUTION=\d+x(\d+).*?\n([^\n]+)", playlist)
        if not variants:
            return master_playlist
        _height, relative_path = sorted(variants, key=lambda item: int(item[0]), reverse=True)[0]
        return urllib.parse.urljoin(master_playlist.rsplit("/", 1)[0] + "/", relative_path.strip())

    def _load_cookies(self, domain: str) -> list:
        try:
            return list(self._cookie_loader(domain))
        except Exception:
            return []

    def _load_browser_cookies(self, domain: str):
        try:
            return browser_cookie3.edge(domain_name=domain)
        except Exception:
            return browser_cookie3.chrome(domain_name=domain)

    def _build_opener(self, cookies, headers: list[tuple[str, str]]):
        cookie_jar = cookies if isinstance(cookies, CookieJar) else CookieJar()
        if cookie_jar is not cookies:
            for cookie in cookies:
                cookie_jar.set_cookie(cookie)
        opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookie_jar))
        opener.addheaders = headers
        return opener

    def _reap_process(self, process) -> None:
        wait = getattr(process, "wait", None)
        if not callable(wait):
            return
        threading.Thread(target=wait, daemon=True).start()
