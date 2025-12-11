import types
from pathlib import Path

import pytest

import downloader
from downloader import DownloadResult, FileTooLargeError, UnsupportedURLError


class DummyDL:
    def __init__(self, opts, tmp_file: Path):
        self.opts = opts
        self.tmp_file = tmp_file
        self._info_calls = 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def extract_info(self, url, download=False):
        self._info_calls += 1
        if not download:
            return {"title": "Sample", "filesize": 1024}
        return {
            "requested_downloads": [
                {
                    "filepath": str(self.tmp_file),
                    "filesize": 1024,
                    "title": "Sample",
                    "ext": "mp4",
                }
            ]
        }


@pytest.fixture
def patch_ytdlp(monkeypatch, tmp_path):
    tmp_file = tmp_path / "video.mp4"
    tmp_file.write_bytes(b"0" * 1024)

    def factory(opts):
        return DummyDL(opts, tmp_file)

    monkeypatch.setattr(downloader, "yt_dlp", types.SimpleNamespace(YoutubeDL=factory))
    return tmp_file


def test_download_video_success(patch_ytdlp, tmp_path):
    result: DownloadResult = downloader.download_video(
        url="https://youtu.be/test",
        quality_key="360p",
        tmp_dir=tmp_path,
        max_file_bytes=2 * 1024,
        progress_cb=None,
        user_agent=None,
        cookies_path=None,
    )

    assert result.file_path.exists()
    assert result.title == "Sample"
    assert result.ext == "mp4"
    assert result.size == 1024


def test_download_video_too_large(monkeypatch, tmp_path):
    # Ensure pre-download size check triggers
    def factory(opts):
        class TooLargeDL(DummyDL):
            def extract_info(self, url, download=False):
                if not download:
                    return {"title": "Sample", "filesize": 10_000_000}
                return super().extract_info(url, download)

        return TooLargeDL(opts, tmp_path / "video.mp4")

    monkeypatch.setattr(downloader, "yt_dlp", types.SimpleNamespace(YoutubeDL=factory))

    with pytest.raises(FileTooLargeError):
        downloader.download_video(
            url="https://youtu.be/test",
            quality_key="360p",
            tmp_dir=tmp_path,
            max_file_bytes=1024,
            progress_cb=None,
            user_agent=None,
            cookies_path=None,
        )


def test_download_video_unsupported(tmp_path):
    with pytest.raises(UnsupportedURLError):
        downloader.download_video(
            url="https://example.com/video",
            quality_key="360p",
            tmp_dir=tmp_path,
            max_file_bytes=1024,
        )
