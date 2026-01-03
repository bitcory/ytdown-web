document.addEventListener('DOMContentLoaded', function() {
    const urlInput = document.getElementById('url');
    const downloadBtn = document.getElementById('downloadBtn');
    const progressSection = document.getElementById('progressSection');
    const progressFill = document.getElementById('progressFill');
    const statusText = document.getElementById('statusText');
    const downloadLink = document.getElementById('downloadLink');
    const fileLink = document.getElementById('fileLink');

    let eventSource = null;

    downloadBtn.addEventListener('click', startDownload);

    urlInput.addEventListener('keypress', function(e) {
        if (e.key === 'Enter') {
            startDownload();
        }
    });

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

        try {
            // 다운로드 시작 요청
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
                // 다운로드 완료
                eventSource.close();
                downloadBtn.disabled = false;
                downloadBtn.textContent = '다운로드';

                // 파일 다운로드 링크 표시
                fileLink.href = data.download_url;
                downloadLink.style.display = 'block';

                // 자동 다운로드
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
