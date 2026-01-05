"""웹 버전 다운로더 모듈 - Instagram, TikTok 지원 (yt-dlp 사용)"""
import re
import os
import tempfile
from typing import Callable, Optional
import yt_dlp


class WebDownloader:
    """웹 서버용 다운로더 클래스 (YouTube/TikTok/Instagram)"""

    INSTAGRAM_REGEX = re.compile(
        r'(https?://)?(www\.)?instagram\.com/(p|reel|reels|tv)/[\w-]+'
    )

    TIKTOK_REGEX = re.compile(
        r'(https?://)?(www\.|vm\.|vt\.)?tiktok\.com/(@[\w.]+/video/\d+|[\w]+/?)'
    )

    YOUTUBE_REGEX = re.compile(
        r'(https?://)?(www\.|m\.)?(youtube\.com/(watch\?v=|shorts/)|youtu\.be/)[\w-]+'
    )

    def __init__(self):
        self.temp_dir = tempfile.mkdtemp()

    def _is_youtube(self, url: str) -> bool:
        """YouTube URL인지 확인"""
        return bool(self.YOUTUBE_REGEX.match(url))

    @staticmethod
    def validate_url(url: str) -> bool:
        """URL 유효성 검사 (TikTok/Instagram)"""
        return bool(
            WebDownloader.INSTAGRAM_REGEX.match(url) or
            WebDownloader.TIKTOK_REGEX.match(url)
        )

    def get_video_info(self, url: str) -> Optional[dict]:
        """비디오 정보 추출"""
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
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

        is_youtube = self._is_youtube(url)

        if _retry >= 2:
            video_format = 'best[ext=mp4]/best'
        else:
            # H.264 코덱 우선 선택 (iOS 호환)
            video_format = 'bestvideo[vcodec^=avc1]+bestaudio[acodec^=mp4a]/bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best'

        output_template = os.path.join(self.temp_dir, f'{task_id}.%(ext)s')

        ydl_opts = {
            'format': video_format,
            'outtmpl': output_template,
            'progress_hooks': [progress_hook],
            'merge_output_format': 'mp4',
            'quiet': False,
            'no_warnings': False,
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36',
                'Referer': 'https://www.instagram.com/',
            },
        }

        # YouTube 전용 우회 옵션
        if is_youtube:
            # 클라이언트 목록: android, ios, web, tv 등을 시도
            clients = ['android', 'ios', 'tv_embedded', 'web']
            client_to_use = clients[_retry % len(clients)]
            ydl_opts['extractor_args'] = {
                'youtube': {
                    'player_client': [client_to_use],
                    'player_skip': ['webpage', 'configs'],
                }
            }
            ydl_opts['http_headers']['User-Agent'] = 'com.google.android.youtube/19.09.37 (Linux; U; Android 11) gzip'

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                filename = ydl.prepare_filename(info)
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

            # YouTube 및 기타 에러 시 재시도
            retry_keywords = ['403', 'Forbidden', 'rate-limit', 'Sign in', 'bot', 'unavailable']
            should_retry = any(kw.lower() in error_str.lower() for kw in retry_keywords)

            if should_retry and _retry < 3:
                if progress_callback:
                    progress_callback(0, f"재시도 중... ({_retry + 1}/4)")
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

        is_youtube = self._is_youtube(url)

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
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36',
                'Referer': 'https://www.instagram.com/',
            },
        }

        # YouTube 전용 우회 옵션
        if is_youtube:
            clients = ['android', 'ios', 'tv_embedded', 'web']
            client_to_use = clients[_retry % len(clients)]
            ydl_opts['extractor_args'] = {
                'youtube': {
                    'player_client': [client_to_use],
                    'player_skip': ['webpage', 'configs'],
                }
            }
            ydl_opts['http_headers']['User-Agent'] = 'com.google.android.youtube/19.09.37 (Linux; U; Android 11) gzip'

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])

                mp3_file = os.path.join(self.temp_dir, f'{task_id}.mp3')
                if os.path.exists(mp3_file):
                    if progress_callback:
                        progress_callback(100, "완료!")
                    return mp3_file

                for f in os.listdir(self.temp_dir):
                    if f.startswith(task_id) and f.endswith('.mp3'):
                        if progress_callback:
                            progress_callback(100, "완료!")
                        return os.path.join(self.temp_dir, f)

                return None

        except Exception as e:
            error_str = str(e)
            print(f"다운로드 실패: {e}")

            # YouTube 및 기타 에러 시 재시도
            retry_keywords = ['403', 'Forbidden', 'rate-limit', 'Sign in', 'bot', 'unavailable']
            should_retry = any(kw.lower() in error_str.lower() for kw in retry_keywords)

            if should_retry and _retry < 3:
                if progress_callback:
                    progress_callback(0, f"재시도 중... ({_retry + 1}/4)")
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
