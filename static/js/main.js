document.addEventListener('DOMContentLoaded', function() {
    const urlInput = document.getElementById('url');
    const downloadBtn = document.getElementById('downloadBtn');
    const progressSection = document.getElementById('progressSection');
    const progressFill = document.getElementById('progressFill');
    const statusText = document.getElementById('statusText');
    const downloadLink = document.getElementById('downloadLink');
    const fileLink = document.getElementById('fileLink');

    let eventSource = null;

    // cobalt 공개 인스턴스 목록 (CORS 지원)
    const COBALT_INSTANCES = [
        'https://api.cobalt.tools',
        'https://cobalt-api.kwiatekmiki.com',
        'https://cobalt.api.timelessnesses.me'
    ];

    downloadBtn.addEventListener('click', startDownload);

    urlInput.addEventListener('keypress', function(e) {
        if (e.key === 'Enter') {
            startDownload();
        }
    });

    // YouTube URL 감지
    function isYouTubeUrl(url) {
        const youtubeRegex = /(https?:\/\/)?(www\.)?(youtube|youtu|youtube-nocookie)\.(com|be)\/(watch\?v=|embed\/|v\/|.+\?v=|shorts\/)?([^&=%\?]{11})/;
        return youtubeRegex.test(url);
    }

    async function startDownload() {
        const url = urlInput.value.trim();
        const type = document.querySelector('input[name="type"]:checked').value;

        if (!url) {
            alert('URL을 입력해주세요.');
            return;
        }

        // UI 초기화
        downloadBtn.disabled = true;
        downloadBtn.textContent = '다운로드 중...';
        progressSection.style.display = 'block';
        downloadLink.style.display = 'none';
        progressFill.style.width = '0%';
        statusText.textContent = '요청 중...';

        // 이전 SSE 연결 종료
        if (eventSource) {
            eventSource.close();
        }

        // YouTube는 클라이언트에서 cobalt API 직접 호출
        if (isYouTubeUrl(url)) {
            await downloadViaCobalt(url, type === 'audio');
        } else {
            // TikTok/Instagram은 서버에서 처리
            await downloadViaServer(url, type);
        }
    }

    // cobalt API로 YouTube 다운로드 (클라이언트 사이드)
    async function downloadViaCobalt(url, audioOnly) {
        statusText.textContent = 'YouTube 처리 중...';
        progressFill.style.width = '20%';

        for (const instance of COBALT_INSTANCES) {
            try {
                statusText.textContent = `cobalt 서버 연결 중...`;
                progressFill.style.width = '30%';

                const response = await fetch(instance, {
                    method: 'POST',
                    headers: {
                        'Accept': 'application/json',
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({
                        url: url,
                        downloadMode: audioOnly ? 'audio' : 'auto',
                        audioFormat: 'mp3',
                        videoQuality: '1080',
                        filenameStyle: 'basic',
                    }),
                });

                if (!response.ok) {
                    console.log(`${instance} 응답 실패: ${response.status}`);
                    continue;
                }

                const data = await response.json();
                console.log('cobalt 응답:', data);

                if (data.status === 'error') {
                    console.log(`${instance} 에러: ${data.error?.code || 'unknown'}`);
                    continue;
                }

                // 다운로드 URL 처리
                let downloadUrl = data.url;

                if (data.status === 'picker' && data.picker) {
                    // 여러 옵션이 있는 경우 첫 번째 선택
                    downloadUrl = data.picker[0]?.url;
                }

                if (downloadUrl) {
                    statusText.textContent = '다운로드 준비 완료!';
                    progressFill.style.width = '100%';

                    // 다운로드 링크 표시
                    fileLink.href = downloadUrl;
                    fileLink.target = '_blank';
                    downloadLink.style.display = 'block';

                    // 새 탭에서 다운로드
                    window.open(downloadUrl, '_blank');

                    downloadBtn.disabled = false;
                    downloadBtn.textContent = '다운로드';
                    return;
                }

            } catch (error) {
                console.log(`${instance} 연결 실패:`, error);
                continue;
            }
        }

        // 모든 인스턴스 실패
        showError('YouTube 다운로드 실패. 나중에 다시 시도해주세요.');
    }

    // 서버를 통한 다운로드 (TikTok/Instagram)
    async function downloadViaServer(url, type) {
        try {
            const response = await fetch('/api/download', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ url, type }),
            });

            const data = await response.json();

            if (data.error) {
                showError(data.error);
                return;
            }

            // SSE로 진행률 추적
            trackProgress(data.task_id);

        } catch (error) {
            showError('서버 연결 실패');
        }
    }

    function trackProgress(taskId) {
        eventSource = new EventSource(`/api/progress/${taskId}`);

        eventSource.onmessage = function(event) {
            const data = JSON.parse(event.data);

            if (data.error) {
                showError(data.error);
                eventSource.close();
                return;
            }

            // 진행률 업데이트
            progressFill.style.width = `${data.progress}%`;
            statusText.textContent = data.message;

            if (data.status === 'completed') {
                eventSource.close();
                downloadBtn.disabled = false;
                downloadBtn.textContent = '다운로드';

                fileLink.href = data.download_url;
                downloadLink.style.display = 'block';

                window.location.href = data.download_url;

            } else if (data.status === 'failed') {
                showError(data.message);
                eventSource.close();
            }
        };

        eventSource.onerror = function() {
            showError('연결이 끊어졌습니다.');
            eventSource.close();
        };
    }

    function showError(message) {
        statusText.textContent = message;
        progressFill.style.width = '0%';
        downloadBtn.disabled = false;
        downloadBtn.textContent = '다운로드';
    }
});
