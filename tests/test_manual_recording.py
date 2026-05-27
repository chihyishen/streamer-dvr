from __future__ import annotations

import base64
import io
import threading
import unittest
import urllib.error
from http.cookiejar import Cookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory

from app.domain import AppConfig
from app.services.manual_recording import MISSAV_OUTPUT_BASE_DIR, MissavRecordingService


class _Cookie:
    def __init__(self, name: str, value: str) -> None:
        self.name = name
        self.value = value


class _Response:
    def __init__(self, body: str) -> None:
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        return None

    def read(self) -> bytes:
        return self.body.encode("utf-8")


class _CurlResponse:
    def __init__(
        self,
        body: str,
        status_code: int = 200,
        reason: str = "OK",
        cookies: dict[str, str] | None = None,
    ) -> None:
        self.text = body
        self.status_code = status_code
        self.reason = reason
        self.cookies = cookies or {}


class _Opener:
    def __init__(self, bodies: list[str]) -> None:
        self.bodies = bodies
        self.addheaders = []
        self.opened: list[str] = []

    def open(self, url: str):
        self.opened.append(url)
        return _Response(self.bodies.pop(0))


class _Process:
    pid = 4321


class _CompletedProcess:
    def __init__(self, stdout: str, stderr: str = "", returncode: int = 1) -> None:
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


class _WaitableProcess:
    pid = 9876

    def __init__(self) -> None:
        self.waited = threading.Event()

    def wait(self) -> int:
        self.waited.set()
        return 0


class _TextHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path == "/forbidden":
            self.send_response(403)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, *_args) -> None:
        return None


def _cookie(name: str, value: str) -> Cookie:
    return Cookie(
        version=0,
        name=name,
        value=value,
        port=None,
        port_specified=False,
        domain="127.0.0.1",
        domain_specified=True,
        domain_initial_dot=False,
        path="/",
        path_specified=True,
        secure=False,
        expires=None,
        discard=True,
        comment=None,
        comment_url=None,
        rest={},
        rfc2109=False,
    )


class MissavRecordingServiceTests(unittest.TestCase):
    def test_extract_m3u8_from_packed_script(self) -> None:
        html = """
<script>
eval(function(p,a,c,k,e,d){return p;}('0://1/2.3',4,4,'https|surrit.com|key/playlist|m3u8'.split('|')))
</script>
"""

        links = MissavRecordingService.extract_m3u8_from_html(html)

        self.assertEqual(links, ["https://surrit.com/key/playlist.m3u8"])

    def test_extract_m3u8_from_packed_script_with_extra_arguments_and_escaped_payload(self) -> None:
        html = r"""
<script>
eval(function(p,a,c,k,e,d){return p;}('e=\'8://7.6/5-4-3-2-1/d.0\';c=\'8://7.6/5-4-3-2-1/a/9.0\';b=\'8://7.6/5-4-3-2-1/a/9.0\';',15,15,'m3u8|23627e385e72|802e|4fe1|fb95|952e46ed|com|surrit|https|video|720p|source1280|source842|playlist|source'.split('|'),0,{}))
</script>
"""

        links = MissavRecordingService.extract_m3u8_from_html(html)

        self.assertEqual(
            links,
            [
                "https://surrit.com/952e46ed-fb95-4fe1-802e-23627e385e72/playlist.m3u8",
                "https://surrit.com/952e46ed-fb95-4fe1-802e-23627e385e72/720p/video.m3u8",
            ],
        )

    def test_start_validates_missav_url(self) -> None:
        service = MissavRecordingService()

        with TemporaryDirectory() as tmpdir, self.assertRaises(ValueError):
            service.start("https://example.com/not-missav", AppConfig(organized_dir=tmpdir))

    def test_start_extracts_best_playlist_and_launches_ytdlp(self) -> None:
        launched: list[dict[str, object]] = []
        html = "<html><body>player source https://surrit.com/video-key/playlist.m3u8</body></html>"
        playlist = """#EXTM3U
#EXT-X-STREAM-INF:BANDWIDTH=1,RESOLUTION=640x360
640x360/video.m3u8
#EXT-X-STREAM-INF:BANDWIDTH=2,RESOLUTION=1920x1080
1920x1080/video.m3u8
"""
        openers = [_Opener([html]), _Opener([playlist])]

        def opener_factory(*_args, **_kwargs):
            return openers.pop(0)

        def launch(command, **kwargs):
            launched.append({"command": command, **kwargs})
            return _Process()

        with TemporaryDirectory() as fixed_dir:
            fixed_base = Path(fixed_dir) / "camrecs" / "av"
            service = MissavRecordingService(
                cookie_loader=lambda _domain: [_Cookie("sess", "abc")],
                opener_factory=opener_factory,
                process_launcher=launch,
                output_base_dir=fixed_base,
            )

            job = service.start(
                "https://missav.ai/dm421/sample-123",
                AppConfig(organized_dir="/ignored/config/path"),
            )

            expected_output = (fixed_base / "MissAV" / "sample-123.mp4").resolve(strict=False)
            self.assertEqual(job.pid, 4321)
            self.assertEqual(job.output_path, str(expected_output))
            self.assertEqual(job.log_path, str(expected_output.with_suffix(".log")))

        command = launched[0]["command"]
        self.assertIsInstance(command, list)
        self.assertIn("yt_dlp", command)
        self.assertIn("--impersonate", command)
        self.assertIn("https://surrit.com/video-key/1920x1080/video.m3u8", command)
        self.assertIn(str(expected_output), command)
        self.assertIsInstance(launched[0]["stdout"], io.TextIOBase)
        self.assertTrue(launched[0]["stdout"].closed)
        self.assertIs(launched[0]["stderr"], launched[0]["stdout"])

    def test_start_uses_fixed_output_base_instead_of_config_organized_dir(self) -> None:
        launched = []
        html = "<html><body>player source https://surrit.com/video-key/playlist.m3u8</body></html>"
        playlist = """#EXTM3U
#EXT-X-STREAM-INF:BANDWIDTH=2,RESOLUTION=1280x720
720p/video.m3u8
"""
        openers = [_Opener([html]), _Opener([playlist])]

        def launch(command, **kwargs):
            launched.append({"command": command, **kwargs})
            return _Process()

        with TemporaryDirectory() as tmpdir:
            fixed_base = Path(tmpdir) / "camrecs" / "av"
            service = MissavRecordingService(
                cookie_loader=lambda _domain: [_Cookie("sess", "abc")],
                opener_factory=lambda *_args, **_kwargs: openers.pop(0),
                process_launcher=launch,
                output_base_dir=fixed_base,
            )
            job = service.start(
                "https://missav.ai/dm421/abc-123",
                AppConfig(organized_dir=str(Path(tmpdir) / "ignored")),
            )

            expected_output = (fixed_base / "MissAV" / "abc-123.mp4").resolve(strict=False)
            self.assertEqual(job.pid, 4321)
            self.assertEqual(job.output_path, str(expected_output))
            self.assertEqual(job.log_path, str(expected_output.with_suffix(".log")))

        command = launched[0]["command"]
        self.assertIn(str(expected_output), command)

    def test_default_output_base_is_camrecs_av(self) -> None:
        self.assertEqual(MISSAV_OUTPUT_BASE_DIR, Path("/Volumes/Storage/Camrecs/av"))

    def test_start_reaps_background_process_when_it_exits(self) -> None:
        process = _WaitableProcess()
        html = "<html><body>player source https://surrit.com/video-key/playlist.m3u8</body></html>"
        playlist = """#EXTM3U
#EXT-X-STREAM-INF:BANDWIDTH=2,RESOLUTION=1280x720
720p/video.m3u8
"""
        openers = [_Opener([html]), _Opener([playlist])]

        with TemporaryDirectory() as tmpdir:
            service = MissavRecordingService(
                cookie_loader=lambda _domain: [_Cookie("sess", "abc")],
                opener_factory=lambda *_args, **_kwargs: openers.pop(0),
                process_launcher=lambda *_args, **_kwargs: process,
                output_base_dir=Path(tmpdir) / "camrecs" / "av",
            )
            service.start("https://missav.ai/sample-403", AppConfig(organized_dir=tmpdir))

        self.assertTrue(process.waited.wait(timeout=1))

    def test_start_falls_back_to_ytdlp_dump_when_page_fetch_is_forbidden(self) -> None:
        launched: list[dict[str, object]] = []
        commands: list[list[str]] = []
        html = "<html><body>player source https://surrit.com/video-key/playlist.m3u8</body></html>"
        dump = base64.b64encode(html.encode("utf-8")).decode("ascii")
        playlist = """#EXTM3U
#EXT-X-STREAM-INF:BANDWIDTH=2,RESOLUTION=1280x720
720p/video.m3u8
"""
        playlist_opener = _Opener([playlist])

        class ForbiddenOpener:
            def open(self, _url: str):
                raise RuntimeError("MissAV fetch failed with HTTP 403: Forbidden")

        def opener_factory(_cookies, headers):
            if ("Origin", "https://missav.ai") in headers:
                return playlist_opener
            return ForbiddenOpener()

        def launch(command, **kwargs):
            launched.append({"command": command, **kwargs})
            return _Process()

        def yt_dlp_runner(command, **_kwargs):
            commands.append(command)
            return _CompletedProcess(stdout=f"[generic] Dumping request\n{dump}\n", stderr="ERROR: Unsupported URL")

        with TemporaryDirectory() as tmpdir:
            service = MissavRecordingService(
                cookie_loader=lambda _domain: [_Cookie("sess", "abc")],
                opener_factory=opener_factory,
                process_launcher=launch,
                yt_dlp_runner=yt_dlp_runner,
                output_base_dir=Path(tmpdir) / "camrecs" / "av",
            )
            service.start("https://missav.ai/sample-fallback", AppConfig(organized_dir=tmpdir))

        self.assertEqual(len(commands), 1)
        self.assertIn("--extractor-args", commands[0])
        self.assertIn("https://surrit.com/video-key/720p/video.m3u8", launched[0]["command"])

    def test_start_uses_ytdlp_dump_when_browser_cookies_are_unavailable(self) -> None:
        launched: list[dict[str, object]] = []
        html = "<html><body>player source https://surrit.com/video-key/playlist.m3u8</body></html>"
        dump = base64.b64encode(html.encode("utf-8")).decode("ascii")
        playlist = """#EXTM3U
#EXT-X-STREAM-INF:BANDWIDTH=2,RESOLUTION=1280x720
720p/video.m3u8
"""
        openers = [_Opener([playlist])]

        with TemporaryDirectory() as tmpdir:
            service = MissavRecordingService(
                cookie_loader=lambda _domain: [],
                opener_factory=lambda *_args, **_kwargs: openers.pop(0),
                process_launcher=lambda command, **kwargs: launched.append({"command": command, **kwargs}) or _Process(),
                yt_dlp_runner=lambda *_args, **_kwargs: _CompletedProcess(stdout=f"{dump}\n", stderr="ERROR: Unsupported URL"),
                output_base_dir=Path(tmpdir) / "camrecs" / "av",
            )
            service.start("https://missav.ai/sample-fallback", AppConfig(organized_dir=tmpdir))

        self.assertIn("https://surrit.com/video-key/720p/video.m3u8", launched[0]["command"])

    def test_fetch_text_falls_back_to_impersonated_request_after_urllib_403(self) -> None:
        class ForbiddenOpener:
            def open(self, _url: str):
                raise urllib.error.HTTPError(_url, 403, "Forbidden", {}, None)

        service = MissavRecordingService(
            opener_factory=lambda *_args, **_kwargs: ForbiddenOpener(),
            curl_fetcher=lambda _url, **_kwargs: _CurlResponse("#EXTM3U"),
        )

        body = service._fetch_text(
            "https://surrit.com/video-key/playlist.m3u8",
            [],
            [("Referer", "https://missav.ai/")],
        )

        self.assertEqual(body, "#EXTM3U")

    def test_impersonated_playlist_fetch_still_downloads_with_ytdlp(self) -> None:
        launched: list[dict[str, object]] = []
        html = "<html><body>player source https://surrit.com/video-key/playlist.m3u8</body></html>"
        dump = base64.b64encode(html.encode("utf-8")).decode("ascii")
        playlist = """#EXTM3U
#EXT-X-STREAM-INF:BANDWIDTH=2,RESOLUTION=1280x720
720p/video.m3u8
"""

        class ForbiddenOpener:
            def open(self, _url: str):
                raise urllib.error.HTTPError(_url, 403, "Forbidden", {}, None)

        with TemporaryDirectory() as tmpdir:
            service = MissavRecordingService(
                cookie_loader=lambda _domain: [],
                opener_factory=lambda *_args, **_kwargs: ForbiddenOpener(),
                process_launcher=lambda command, **kwargs: launched.append({"command": command, **kwargs}) or _Process(),
                yt_dlp_runner=lambda *_args, **_kwargs: _CompletedProcess(stdout=f"{dump}\n", stderr="ERROR: Unsupported URL"),
                curl_fetcher=lambda _url, **_kwargs: _CurlResponse(playlist, cookies={"__cf_bm": "token"}),
                output_base_dir=Path(tmpdir) / "camrecs" / "av",
            )
            service.start("https://missav.ai/sample-fallback", AppConfig(organized_dir=tmpdir))

        command = launched[0]["command"]
        self.assertIn("yt_dlp", command)
        self.assertIn("--impersonate", command)
        self.assertIn("https://surrit.com/video-key/720p/video.m3u8", command)

    def test_fetch_text_accepts_cookie_iterables(self) -> None:
        server = ThreadingHTTPServer(("127.0.0.1", 0), _TextHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)

        service = MissavRecordingService()
        body = service._fetch_text(
            f"http://127.0.0.1:{server.server_port}/",
            [_cookie("sess", "abc")],
            [("User-Agent", "test")],
        )

        self.assertEqual(body, "ok")

    def test_fetch_text_reports_http_errors_as_runtime_errors(self) -> None:
        server = ThreadingHTTPServer(("127.0.0.1", 0), _TextHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)

        service = MissavRecordingService()
        with self.assertRaisesRegex(RuntimeError, "MissAV fetch failed with HTTP 403"):
            service._fetch_text(
                f"http://127.0.0.1:{server.server_port}/forbidden",
                [_cookie("sess", "abc")],
                [("User-Agent", "test")],
            )


if __name__ == "__main__":
    unittest.main()
