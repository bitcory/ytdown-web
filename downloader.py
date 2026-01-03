"""웹 버전 다운로더 모듈 - YouTube, TikTok, Instagram 지원"""
import re
import os
import tempfile
import requests
from typing import Callable, Optional
import yt_dlp


class WebDownloader:
    """웹 서버용 다운로더 클래스"""

    YOUTUBE_REGEX = re.compile(
        r'(https?://)?(www\.)?(youtube|youtu|youtube-nocookie)\.(com|be)/'
        r'(watch\?v=|embed/|v/|.+\?v=|shorts/)?([^&=%\?]{11})'
    )

    INSTAGRAM_REGEX = re.compile(
        r'(https?://)?(www\.)?instagram\.com/(p|reel|reels|tv)/[\w-]+'
    )

    TIKTOK_REGEX = re.compile(
        r'(https?://)?(www\.|vm\.|vt\.)?tiktok\.com/(@[\w.]+/video/\d+|[\w]+/?)'
    )

    COBALT_API = "https://api.cobalt.tools/api/json"

    def __init__(self):
        self.temp_dir = tempfile.mkdtemp()

    def is_youtube_url(self, url: str) -> bool:
        """YouTube URL인지 확인"""
        return bool(self.YOUTUBE_REGEX.match(url))

    def download_via_cobalt(
        self,
        url: str,
        task_id: str,
        audio_only: bool = False,
        progress_callback: Optional[Callable[[float, str], None]] = None
    ) -> Optional[str]:
        """cobalt.tools API를 통한 다운로드"""
        if progress_callback:
            progress_callback(10, "cobalt API 요청 중...")

        try:
            # cobalt API 요청
            headers = {
                "Accept": "application/json",
                "Content-Type": "application/json",
            }
            payload = {
                "url": url,
                "isAudioOnly": audio_only,
                "aFormat": "mp3",
                "filenamePattern": "basic",
            }

            response = requests.post(
                self.COBALT_API,
                json=payload,
                headers=headers,
                timeout=30
            )

            print(f"[cobalt] Status: {response.status_code}, Response: {response.text[:500]}")

            if response.status_code != 200:
                if progress_callback:
                    progress_callback(0, f"API 오류: {response.status_code}")
                return None

            data = response.json()

            if data.get("status") == "error":
                error_text = data.get("text", "unknown error")
                if progress_callback:
                    progress_callback(0, f"오류: {error_text[:50]}")
                return None

            # 다운로드 URL 추출 (status가 redirect 또는 stream일 때)
            download_url = data.get("url")
            if not download_url:
                if progress_callback:
                    progress_callback(0, "다운로드 URL을 찾을 수 없습니다")
                return None

            if progress_callback:
                progress_callback(30, "파일 다운로드 중...")

            # 파일 다운로드
            ext = "mp3" if audio_only else "mp4"
            output_path = os.path.join(self.temp_dir, f"{task_id}.{ext}")

            file_response = requests.get(download_url, stream=True, timeout=300)
            total_size = int(file_response.headers.get('content-length', 0))
            downloaded = 0

            with open(output_path, 'wb') as f:
                for chunk in file_response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total_size > 0 and progress_callback:
                            percent = 30 + (downloaded / total_size) * 65
                            progress_callback(percent, f"다운로드 중... {percent:.0f}%")

            if progress_callback:
                progress_callback(100, "완료!")

            return output_path if os.path.exists(output_path) else None

        except Exception as e:
            print(f"cobalt 다운로드 실패: {e}")
            if progress_callback:
                progress_callback(0, f"오류: {str(e)[:50]}")
            return None

    @staticmethod
    def validate_url(url: str) -> bool:
        """URL 유효성 검사"""
        return bool(
            WebDownloader.YOUTUBE_REGEX.match(url) or
            WebDownloader.INSTAGRAM_REGEX.match(url) or
            WebDownloader.TIKTOK_REGEX.match(url)
        )

    def get_video_info(self, url: str) -> Optional[dict]:
        """비디오 정보 추출"""
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
            'extractor_args': {'youtube': {'player_client': ['android', 'web']}},
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            },
        }
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                return {
                    'title': info.get('title', 'video'),
                    'duration': info.get('duration', 0),
                    'thumbnail': info.get('thumbnail', ''),
                }
        except Exception as e:
            print(f"정보 추출 실패: {e}")
            return None

    def download_video(
        self,
        url: str,
        task_id: str,
        progress_callback: Optional[Callable[[float, str], None]] = None,
        _retry: int = 0
    ) -> Optional[str]:
        """영상 다운로드 - 파일 경로 반환"""

        # YouTube는 cobalt API 사용
        if self.is_youtube_url(url):
            return self.download_via_cobalt(url, task_id, audio_only=False, progress_callback=progress_callback)

        def progress_hook(d):
            if d['status'] == 'downloading':
                total = d.get('total_bytes') or d.get('total_bytes_estimate', 0)
                downloaded = d.get('downloaded_bytes', 0)
                if total > 0:
                    percent = (downloaded / total) * 100
                    speed = d.get('speed', 0)
                    speed_str = f"{speed / 1024 / 1024:.1f} MB/s" if speed else "계산 중..."
                    if progress_callback:
                        progress_callback(percent, f"다운로드 중... {percent:.1f}% ({speed_str})")
            elif d['status'] == 'finished':
                if progress_callback:
                    progress_callback(95, "처리 중...")

        if _retry >= 2:
            video_format = 'best[ext=mp4]/best'
        else:
            video_format = 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best'

        output_template = os.path.join(self.temp_dir, f'{task_id}.%(ext)s')

        ydl_opts = {
            'format': video_format,
            'outtmpl': output_template,
            'progress_hooks': [progress_hook],
            'merge_output_format': 'mp4',
            'quiet': True,
            'no_warnings': True,
            'extractor_args': {'youtube': {'player_client': ['android', 'web']}},
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            },
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                filename = ydl.prepare_filename(info)
                # mp4로 변환된 경우 확장자 수정
                if not filename.endswith('.mp4'):
                    base = os.path.splitext(filename)[0]
                    if os.path.exists(base + '.mp4'):
                        filename = base + '.mp4'

                if progress_callback:
                    progress_callback(100, "완료!")

                return filename if os.path.exists(filename) else None

        except Exception as e:
            error_str = str(e)
            print(f"다운로드 실패: {e}")

            if '403' in error_str or 'Forbidden' in error_str:
                if _retry < 2:
                    if progress_callback:
                        progress_callback(0, "다른 포맷으로 재시도 중...")
                    return self.download_video(url, task_id, progress_callback, _retry + 1)

            if progress_callback:
                progress_callback(0, f"오류: {error_str[:100]}")
            return None

    def download_audio(
        self,
        url: str,
        task_id: str,
        progress_callback: Optional[Callable[[float, str], None]] = None,
        _retry: int = 0
    ) -> Optional[str]:
        """음원 추출 (MP3) - 파일 경로 반환"""

        # YouTube는 cobalt API 사용
        if self.is_youtube_url(url):
            return self.download_via_cobalt(url, task_id, audio_only=True, progress_callback=progress_callback)

        def progress_hook(d):
            if d['status'] == 'downloading':
                total = d.get('total_bytes') or d.get('total_bytes_estimate', 0)
                downloaded = d.get('downloaded_bytes', 0)
                if total > 0:
                    percent = (downloaded / total) * 100
                    speed = d.get('speed', 0)
                    speed_str = f"{speed / 1024 / 1024:.1f} MB/s" if speed else "계산 중..."
                    if progress_callback:
                        progress_callback(percent * 0.8, f"다운로드 중... {percent:.1f}% ({speed_str})")
            elif d['status'] == 'finished':
                if progress_callback:
                    progress_callback(85, "MP3 변환 중...")

        if _retry >= 2:
            audio_format = 'best'
        else:
            audio_format = 'bestaudio/best'

        output_template = os.path.join(self.temp_dir, f'{task_id}.%(ext)s')

        ydl_opts = {
            'format': audio_format,
            'outtmpl': output_template,
            'progress_hooks': [progress_hook],
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '320',
            }],
            'quiet': True,
            'no_warnings': True,
            'extractor_args': {'youtube': {'player_client': ['android', 'web']}},
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            },
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])

                # mp3 파일 찾기
                mp3_file = os.path.join(self.temp_dir, f'{task_id}.mp3')
                if os.path.exists(mp3_file):
                    if progress_callback:
                        progress_callback(100, "완료!")
                    return mp3_file

                # 다른 확장자로 저장된 경우 찾기
                for f in os.listdir(self.temp_dir):
                    if f.startswith(task_id) and f.endswith('.mp3'):
                        if progress_callback:
                            progress_callback(100, "완료!")
                        return os.path.join(self.temp_dir, f)

                return None

        except Exception as e:
            error_str = str(e)
            print(f"다운로드 실패: {e}")

            if '403' in error_str or 'Forbidden' in error_str:
                if _retry < 2:
                    if progress_callback:
                        progress_callback(0, "다른 포맷으로 재시도 중...")
                    return self.download_audio(url, task_id, progress_callback, _retry + 1)

            if progress_callback:
                progress_callback(0, f"오류: {error_str[:100]}")
            return None

    def cleanup(self, filepath: str):
        """임시 파일 삭제"""
        try:
            if filepath and os.path.exists(filepath):
                os.remove(filepath)
        except Exception as e:
            print(f"파일 삭제 실패: {e}")
