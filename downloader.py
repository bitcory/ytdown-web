"""웹 버전 다운로더 모듈 - TikTok, Instagram 지원 (cobalt API 사용)"""
import re
import os
import tempfile
import requests
from typing import Callable, Optional


class WebDownloader:
    """웹 서버용 다운로더 클래스 (TikTok/Instagram)"""

    INSTAGRAM_REGEX = re.compile(
        r'(https?://)?(www\.)?instagram\.com/(p|reel|reels|tv)/[\w-]+'
    )

    TIKTOK_REGEX = re.compile(
        r'(https?://)?(www\.|vm\.|vt\.)?tiktok\.com/(@[\w.]+/video/\d+|[\w]+/?)'
    )

    COBALT_API_URL = "https://api.cobalt.tools/api/json"

    def __init__(self):
        self.temp_dir = tempfile.mkdtemp()

    @staticmethod
    def validate_url(url: str) -> bool:
        """URL 유효성 검사 (TikTok/Instagram만)"""
        return bool(
            WebDownloader.INSTAGRAM_REGEX.match(url) or
            WebDownloader.TIKTOK_REGEX.match(url)
        )

    def get_video_info(self, url: str) -> Optional[dict]:
        """비디오 정보 추출"""
        try:
            return {
                'title': 'video',
                'duration': 0,
                'thumbnail': '',
            }
        except Exception as e:
            print(f"정보 추출 실패: {e}")
            return None

    def download_via_cobalt(
        self,
        url: str,
        task_id: str,
        download_type: str,
        progress_callback: Optional[Callable[[float, str], None]] = None
    ) -> Optional[str]:
        """cobalt API를 통한 다운로드"""

        if progress_callback:
            progress_callback(10, "cobalt API 요청 중...")

        try:
            # cobalt API 요청
            headers = {
                "Accept": "application/json",
                "Content-Type": "application/json"
            }

            payload = {
                "url": url,
                "vQuality": "720",
                "filenamePattern": "basic",
            }

            # 음원만 요청할 경우
            if download_type == "audio":
                payload["isAudioOnly"] = True
                payload["aFormat"] = "mp3"

            response = requests.post(
                self.COBALT_API_URL,
                json=payload,
                headers=headers,
                timeout=30
            )

            data = response.json()

            if data.get("status") == "error":
                print(f"cobalt API 에러: {data.get('text', 'Unknown error')}")
                return None

            # 다운로드 URL 추출
            download_url = data.get("url")
            if not download_url:
                # picker 타입인 경우 (여러 미디어)
                if data.get("status") == "picker" and data.get("picker"):
                    download_url = data["picker"][0].get("url")

            if not download_url:
                print("다운로드 URL을 찾을 수 없음")
                return None

            if progress_callback:
                progress_callback(30, "파일 다운로드 중...")

            # 파일 다운로드
            ext = "mp3" if download_type == "audio" else "mp4"
            output_path = os.path.join(self.temp_dir, f"{task_id}.{ext}")

            file_response = requests.get(download_url, stream=True, timeout=120)
            file_response.raise_for_status()

            total_size = int(file_response.headers.get('content-length', 0))
            downloaded = 0

            with open(output_path, 'wb') as f:
                for chunk in file_response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total_size > 0 and progress_callback:
                            percent = 30 + (downloaded / total_size) * 65
                            speed = downloaded / 1024 / 1024
                            progress_callback(percent, f"다운로드 중... {percent:.0f}%")

            if progress_callback:
                progress_callback(100, "완료!")

            return output_path if os.path.exists(output_path) else None

        except requests.exceptions.RequestException as e:
            print(f"cobalt API 요청 실패: {e}")
            return None
        except Exception as e:
            print(f"cobalt 다운로드 실패: {e}")
            return None

    def download_video(
        self,
        url: str,
        task_id: str,
        progress_callback: Optional[Callable[[float, str], None]] = None,
    ) -> Optional[str]:
        """영상 다운로드 - 파일 경로 반환"""
        return self.download_via_cobalt(url, task_id, "video", progress_callback)

    def download_audio(
        self,
        url: str,
        task_id: str,
        progress_callback: Optional[Callable[[float, str], None]] = None,
    ) -> Optional[str]:
        """음원 추출 (MP3) - 파일 경로 반환"""
        return self.download_via_cobalt(url, task_id, "audio", progress_callback)

    def cleanup(self, filepath: str):
        """임시 파일 삭제"""
        try:
            if filepath and os.path.exists(filepath):
                os.remove(filepath)
        except Exception as e:
            print(f"파일 삭제 실패: {e}")
