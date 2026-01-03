"""Multi Downloader 웹 서버"""
import os
import uuid
import threading
from flask import Flask, render_template, request, jsonify, Response, send_file
from downloader import WebDownloader

app = Flask(__name__)

# 다운로드 작업 저장소
tasks = {}
downloader = WebDownloader()


@app.route('/')
def index():
    """메인 페이지"""
    return render_template('index.html')


@app.route('/api/validate', methods=['POST'])
def validate_url():
    """URL 유효성 검사"""
    data = request.get_json()
    url = data.get('url', '')

    if not url:
        return jsonify({'valid': False, 'error': 'URL을 입력해주세요.'})

    if not downloader.validate_url(url):
        return jsonify({'valid': False, 'error': '지원하지 않는 URL입니다. (YouTube, TikTok, Instagram 지원)'})

    return jsonify({'valid': True})


@app.route('/api/download', methods=['POST'])
def start_download():
    """다운로드 시작"""
    data = request.get_json()
    url = data.get('url', '')
    download_type = data.get('type', 'video')

    if not url:
        return jsonify({'error': 'URL을 입력해주세요.'}), 400

    if not downloader.validate_url(url):
        return jsonify({'error': '지원하지 않는 URL입니다.'}), 400

    # 작업 ID 생성
    task_id = str(uuid.uuid4())[:8]
    tasks[task_id] = {
        'status': 'pending',
        'progress': 0,
        'message': '대기 중...',
        'url': url,
        'type': download_type,
        'filepath': None,
        'filename': None,
    }

    # 백그라운드에서 다운로드 시작
    thread = threading.Thread(target=run_download, args=(task_id, url, download_type))
    thread.daemon = True
    thread.start()

    return jsonify({'task_id': task_id})


def run_download(task_id: str, url: str, download_type: str):
    """백그라운드 다운로드 실행"""
    def progress_callback(percent: float, message: str):
        tasks[task_id]['progress'] = percent
        tasks[task_id]['message'] = message
        tasks[task_id]['status'] = 'downloading'

    try:
        tasks[task_id]['status'] = 'downloading'
        tasks[task_id]['message'] = '다운로드 시작...'

        if download_type == 'video':
            filepath = downloader.download_video(url, task_id, progress_callback)
            ext = 'mp4'
        else:
            filepath = downloader.download_audio(url, task_id, progress_callback)
            ext = 'mp3'

        if filepath and os.path.exists(filepath):
            # 비디오 정보로 파일명 생성
            info = downloader.get_video_info(url)
            title = info['title'] if info else 'download'
            # 파일명에서 특수문자 제거
            safe_title = "".join(c for c in title if c.isalnum() or c in (' ', '-', '_')).strip()
            safe_title = safe_title[:50] if len(safe_title) > 50 else safe_title

            tasks[task_id]['status'] = 'completed'
            tasks[task_id]['progress'] = 100
            tasks[task_id]['message'] = '다운로드 완료!'
            tasks[task_id]['filepath'] = filepath
            tasks[task_id]['filename'] = f"{safe_title}.{ext}"
        else:
            tasks[task_id]['status'] = 'failed'
            tasks[task_id]['message'] = '다운로드 실패'

    except Exception as e:
        tasks[task_id]['status'] = 'failed'
        tasks[task_id]['message'] = f'오류: {str(e)[:100]}'


@app.route('/api/progress/<task_id>')
def get_progress(task_id: str):
    """SSE로 진행률 스트리밍"""
    def generate():
        import time
        while True:
            if task_id not in tasks:
                yield f"data: {jsonify({'error': 'Task not found'}).get_data(as_text=True)}\n\n"
                break

            task = tasks[task_id]
            data = {
                'status': task['status'],
                'progress': task['progress'],
                'message': task['message'],
            }

            if task['status'] == 'completed':
                data['download_url'] = f'/api/file/{task_id}'
                yield f"data: {jsonify(data).get_data(as_text=True)}\n\n"
                break
            elif task['status'] == 'failed':
                yield f"data: {jsonify(data).get_data(as_text=True)}\n\n"
                break
            else:
                yield f"data: {jsonify(data).get_data(as_text=True)}\n\n"

            time.sleep(0.5)

    return Response(generate(), mimetype='text/event-stream')


@app.route('/api/file/<task_id>')
def download_file(task_id: str):
    """파일 다운로드"""
    if task_id not in tasks:
        return jsonify({'error': 'Task not found'}), 404

    task = tasks[task_id]
    if task['status'] != 'completed' or not task['filepath']:
        return jsonify({'error': 'File not ready'}), 400

    filepath = task['filepath']
    filename = task['filename']

    if not os.path.exists(filepath):
        return jsonify({'error': 'File not found'}), 404

    # 파일 전송 후 정리 예약
    response = send_file(
        filepath,
        as_attachment=True,
        download_name=filename
    )

    # 1분 후 파일 삭제 (별도 스레드에서)
    def cleanup_later():
        import time
        time.sleep(60)
        downloader.cleanup(filepath)
        if task_id in tasks:
            del tasks[task_id]

    cleanup_thread = threading.Thread(target=cleanup_later)
    cleanup_thread.daemon = True
    cleanup_thread.start()

    return response


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
