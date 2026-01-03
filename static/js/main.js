document.addEventListener('DOMContentLoaded', function() {
    const urlInput = document.getElementById('url');
    const downloadBtn = document.getElementById('downloadBtn');
    const progressSection = document.getElementById('progressSection');
    const progressFill = document.getElementById('progressFill');
    const statusText = document.getElementById('statusText');
    const downloadLink = document.getElementById('downloadLink');
    const fileLink = document.getElementById('fileLink');
    const refreshBtn = document.getElementById('refreshBtn');

    let eventSource = null;

    downloadBtn.addEventListener('click', startDownload);

    urlInput.addEventListener('keypress', function(e) {
        if (e.key === 'Enter') {
            startDownload();
        }
    });

    refreshBtn.addEventListener('click', resetUI);

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
        statusText.textContent = '서버 연결 중...';

        // 이전 SSE 연결 종료
        if (eventSource) {
            eventSource.close();
        }

        // 서버를 통한 다운로드 (TikTok/Instagram)
        await downloadViaServer(url, type);
    }

    async function downloadViaServer(url, type, retryCount = 0) {
        const maxRetries = 3;

        try {
            if (retryCount > 0) {
                statusText.textContent = `재시도 중... (${retryCount}/${maxRetries})`;
            }

            const response = await fetch('/api/download', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ url, type }),
            });

            const data = await response.json();

            if (data.error) {
                if (retryCount < maxRetries) {
                    await new Promise(r => setTimeout(r, 2000));
                    return downloadViaServer(url, type, retryCount + 1);
                }
                showError(data.error);
                return;
            }

            // SSE로 진행률 추적
            trackProgress(data.task_id);

        } catch (error) {
            if (retryCount < maxRetries) {
                await new Promise(r => setTimeout(r, 2000));
                return downloadViaServer(url, type, retryCount + 1);
            }
            showError('서버 연결 실패');
        }
    }

    let sseRetryCount = 0;
    const maxSseRetries = 3;

    function trackProgress(taskId) {
        eventSource = new EventSource(`/api/progress/${taskId}`);

        eventSource.onmessage = function(event) {
            const data = JSON.parse(event.data);

            if (data.error) {
                // Task not found 에러 시 재시도
                if (data.error.includes('not found') && sseRetryCount < maxSseRetries) {
                    sseRetryCount++;
                    eventSource.close();
                    statusText.textContent = `서버 연결 중... (${sseRetryCount}/${maxSseRetries})`;
                    setTimeout(() => trackProgress(taskId), 2000);
                    return;
                }
                showError(data.error);
                eventSource.close();
                sseRetryCount = 0;
                return;
            }

            sseRetryCount = 0; // 성공하면 리셋

            // 진행률 업데이트
            progressFill.style.width = `${data.progress}%`;
            statusText.textContent = data.message;

            if (data.status === 'completed') {
                eventSource.close();
                eventSource = null;
                downloadBtn.disabled = false;
                downloadBtn.innerHTML = '<span class="btn-text">다운로드</span><span class="btn-icon">▼</span>';

                fileLink.href = data.download_url;
                downloadLink.style.display = 'block';

                window.location.href = data.download_url;

            } else if (data.status === 'failed') {
                showError(data.message);
                eventSource.close();
            }
        };

        eventSource.onerror = function() {
            eventSource.close();
            // 다운로드 완료 후에는 에러 무시
            if (downloadLink.style.display === 'block') {
                sseRetryCount = 0;
                return;
            }
            if (sseRetryCount < maxSseRetries) {
                sseRetryCount++;
                statusText.textContent = `재연결 중... (${sseRetryCount}/${maxSseRetries})`;
                setTimeout(() => trackProgress(taskId), 2000);
            } else {
                showError('연결이 끊어졌습니다.');
                sseRetryCount = 0;
            }
        };
    }

    function showError(message) {
        statusText.textContent = message;
        progressFill.style.width = '0%';
        downloadBtn.disabled = false;
        downloadBtn.innerHTML = '<span class="btn-text">다운로드</span><span class="btn-icon">▼</span>';
    }

    function resetUI() {
        urlInput.value = '';
        progressSection.style.display = 'none';
        downloadLink.style.display = 'none';
        progressFill.style.width = '0%';
        statusText.textContent = '대기 중...';
        downloadBtn.disabled = false;
        downloadBtn.innerHTML = '<span class="btn-text">다운로드</span><span class="btn-icon">▼</span>';
        if (eventSource) {
            eventSource.close();
            eventSource = null;
        }
        urlInput.focus();
    }
});
