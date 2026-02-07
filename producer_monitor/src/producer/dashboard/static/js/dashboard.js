class Dashboard {
    constructor(refreshInterval) {
        this.refreshInterval = refreshInterval * 1000; // Convert to ms
        this.eventSource = null;
        window.dashboardInstance = this;
    }

    start() {
        this.connectSSE();
        this.fetchDashboardStatus();
        setInterval(() => this.fetchDashboardStatus(), this.refreshInterval);
    }

    connectSSE() {
        this.eventSource = new EventSource('/api/stream');

        this.eventSource.onmessage = (event) => {
            const data = JSON.parse(event.data);
            this.updateQueues(data.queues);
            this.updateProgress(data.progress);
            this.updateUpdatedGames(data.updated_games);
            this.updateLastUpdate();
            if (data.scheduler) {
                this.updateScheduler(data.scheduler);
            }
        };

        this.eventSource.onerror = (error) => {
            console.error('SSE connection error:', error);
            this.eventSource.close();
            setTimeout(() => this.connectSSE(), 5000); // Reconnect after 5s
        };
    }

    updateQueues(queues) {
        document.getElementById('queue-work').textContent = this.formatNumber(queues.work);
        document.getElementById('queue-processing').textContent = this.formatNumber(queues.processing);
        document.getElementById('queue-result').textContent = this.formatNumber(queues.result);
        document.getElementById('queue-saving').textContent = this.formatNumber(queues.saving);
        document.getElementById('dlq-crawling').textContent = this.formatNumber(queues.crawling_failed);
        document.getElementById('dlq-saving').textContent = this.formatNumber(queues.saving_failed);
    }

    updateProgress(progress) {
        document.getElementById('progress-total').textContent = this.formatNumber(progress.total);
        document.getElementById('progress-completed').textContent = this.formatNumber(progress.completed);
        document.getElementById('progress-remaining').textContent = this.formatNumber(progress.remaining);
        document.getElementById('progress-percent').textContent = progress.percent.toFixed(2);
        document.getElementById('progress-bar').style.width = progress.percent + '%';
    }

    updateUpdatedGames(count) {
        document.getElementById('updated-games').textContent = this.formatNumber(count);
    }

    async fetchDashboardStatus() {
        try {
            const [statusResponse, producerResponse] = await Promise.all([
                fetch('/api/status'),
                fetch('/api/admin/producer/status')
            ]);

            const statusData = await statusResponse.json();
            const producerData = await producerResponse.json();

            this.updateDatabaseStatus(statusData.database);
            this.updateProducerStatus(producerData, statusData.producer_start_time);
        } catch (error) {
            console.error('Failed to fetch dashboard status:', error);
        }
    }

    updateDatabaseStatus(database) {
        const statusBadge = document.getElementById('db-status');
        statusBadge.textContent = database.connected ? 'Connected' : 'Disconnected';
        statusBadge.className = database.connected ? 'badge connected' : 'badge disconnected';

        document.getElementById('db-version').textContent = database.version || 'N/A';

        const tablesDiv = document.getElementById('db-tables');
        if (database.tables && Object.keys(database.tables).length > 0) {
            let html = '<h4>Table Counts:</h4><ul>';
            for (const [table, count] of Object.entries(database.tables)) {
                html += `<li><strong>${table}:</strong> ${this.formatNumber(count)}</li>`;
            }
            html += '</ul>';
            tablesDiv.innerHTML = html;
        }
    }

    updateProducerStatus(data, savedStartTime) {
        const badge = document.getElementById('producer-status-badge');
        const details = document.getElementById('producer-details');
        const btnProd = document.getElementById('btn-producer-prod');
        const btnTest = document.getElementById('btn-producer-test');

        if (data.is_running) {
            badge.textContent = 'Running';
            badge.className = 'badge running';

            const modeText = data.mode === 'production' ? 'Production Mode' : `Test Mode (${data.sample_count} samples)`;
            const startedAt = new Date(data.started_at * 1000).toLocaleString();
            details.textContent = `${modeText} | PID: ${data.pid} | Started: ${startedAt}`;

            // Disable start buttons
            btnProd.disabled = true;
            btnTest.disabled = true;
        } else {
            badge.textContent = 'Stopped';
            badge.className = 'badge stopped';

            let statusText = 'Producer is not running';
            if (savedStartTime) {
                const startedAt = new Date(savedStartTime * 1000).toLocaleString();
                statusText += ` | Started: ${startedAt}`;
            }
            details.textContent = statusText;

            // Enable start buttons
            btnProd.disabled = false;
            btnTest.disabled = false;
        }
    }

    updateLastUpdate() {
        const now = new Date();
        document.getElementById('last-update').textContent = now.toLocaleTimeString();
    }

    updateScheduler(scheduler) {
        const badge = document.getElementById('scheduler-state-badge');
        const details = document.getElementById('scheduler-details');
        const errorDiv = document.getElementById('scheduler-error');
        const btnStart = document.getElementById('btn-scheduler-start');
        const btnStop = document.getElementById('btn-scheduler-stop');

        if (!badge) return;

        // State badge
        const stateLabels = {
            'idle': 'IDLE',
            'waiting_completion': 'WAITING',
            'retrying_failed': 'RETRYING',
            'waiting_retry_completion': 'RETRY WAITING',
            'cloning_db': 'CLONING DB',
            'starting_producer': 'STARTING',
            'error': 'ERROR'
        };
        badge.textContent = stateLabels[scheduler.state] || scheduler.state.toUpperCase();
        badge.className = `badge scheduler-${scheduler.state}`;

        // Details
        let info = `Cycles: ${scheduler.cycle_count}`;
        if (scheduler.config) {
            info += ` | Mode: ${scheduler.config.producer_mode}`;
            if (scheduler.config.producer_mode === 'test') {
                info += ` (${scheduler.config.producer_sample_count} samples)`;
            }
        }
        details.textContent = info;

        // Error display
        if (scheduler.last_error) {
            errorDiv.textContent = scheduler.last_error;
            errorDiv.classList.add('show');
        } else {
            errorDiv.classList.remove('show');
        }

        // Button states
        btnStart.disabled = scheduler.running;
        btnStop.disabled = !scheduler.running;
    }

    formatNumber(num) {
        return num.toLocaleString();
    }
}


// ========================================
// Admin Controls - Reset Functionality
// ========================================

let currentResetAction = null;

function showResetModal(action) {
    currentResetAction = action;

    const actionText = {
        'redis': 'clear all Redis queues',
        'database': 'truncate all PostgreSQL tables',
        'all': 'reset both Redis AND PostgreSQL'
    };

    document.getElementById('reset-action-text').textContent = actionText[action];
    document.getElementById('confirmation-phrase').value = '';
    document.getElementById('reset-error').classList.remove('show');
    document.getElementById('reset-modal').style.display = 'block';
}

function closeResetModal() {
    document.getElementById('reset-modal').style.display = 'none';
    currentResetAction = null;
}

async function executeReset() {
    const confirmationInput = document.getElementById('confirmation-phrase').value;
    const errorDiv = document.getElementById('reset-error');
    const confirmBtn = document.getElementById('btn-confirm-reset');

    // Clear previous errors
    errorDiv.classList.remove('show');

    // Validate confirmation phrase
    if (confirmationInput !== 'DELETE ALL DATA') {
        errorDiv.textContent = 'Incorrect confirmation phrase. Please type exactly: DELETE ALL DATA';
        errorDiv.classList.add('show');
        return;
    }

    // Disable button during request
    confirmBtn.disabled = true;
    confirmBtn.textContent = 'Resetting...';

    try {
        const response = await fetch('/api/admin/reset', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                action: currentResetAction,
                confirmation_phrase: confirmationInput
            })
        });

        const data = await response.json();

        if (response.ok && data.success) {
            closeResetModal();
            showToast(data.message, 'success');

            // Show stats before reset
            if (data.stats_before) {
                console.log('Stats before reset:', data.stats_before);
            }
        } else {
            errorDiv.textContent = data.error || 'Reset failed. Please try again.';
            errorDiv.classList.add('show');
        }
    } catch (error) {
        errorDiv.textContent = 'Network error. Please check your connection.';
        errorDiv.classList.add('show');
    } finally {
        confirmBtn.disabled = false;
        confirmBtn.textContent = 'Confirm Reset';
    }
}


// ========================================
// Admin Controls - Producer Functionality
// ========================================

let currentProducerMode = null;
let currentProducerResetAction = null;

function showProducerModal(mode) {
    currentProducerMode = mode;

    const modeText = mode === 'production' ? 'Production (All Games)' : 'Test Mode';
    document.getElementById('producer-mode-text').textContent = modeText;

    const sampleInput = document.getElementById('sample-count-input');
    sampleInput.style.display = mode === 'test' ? 'block' : 'none';

    // Reset checkboxes to default
    document.getElementById('reset-redis-before-start').checked = true;
    document.getElementById('reset-db-before-start').checked = false;

    document.getElementById('producer-error').classList.remove('show');
    document.getElementById('producer-modal').style.display = 'block';
}

function closeProducerModal() {
    document.getElementById('producer-modal').style.display = 'none';
    // Don't reset currentProducerMode here - it's needed for reset+start flow
}

function executeProducerStart() {
    const resetRedis = document.getElementById('reset-redis-before-start').checked;
    const resetDb = document.getElementById('reset-db-before-start').checked;

    if (resetDb) {
        // Reset DB implies Reset Redis too (action='all')
        currentProducerResetAction = 'all';
        document.getElementById('producer-modal').style.display = 'none';
        showProducerResetConfirmModal();
    } else if (resetRedis) {
        // Only Reset Redis
        currentProducerResetAction = 'redis';
        document.getElementById('producer-modal').style.display = 'none';
        showProducerResetConfirmModal();
    } else {
        // No reset, start directly
        startProducerDirect();
    }
}

function showProducerResetConfirmModal() {
    document.getElementById('producer-reset-phrase').value = '';
    document.getElementById('producer-reset-error').classList.remove('show');
    document.getElementById('producer-reset-confirm-modal').style.display = 'block';
}

function closeProducerResetConfirmModal() {
    document.getElementById('producer-reset-confirm-modal').style.display = 'none';
    // Reset mode when user cancels or completes the flow
    currentProducerMode = null;
    currentProducerResetAction = null;
}

async function confirmProducerReset() {
    const confirmationInput = document.getElementById('producer-reset-phrase').value;
    const errorDiv = document.getElementById('producer-reset-error');
    const confirmBtn = document.getElementById('btn-confirm-producer-reset');

    // Clear previous errors
    errorDiv.classList.remove('show');

    // Validate confirmation phrase
    if (confirmationInput !== 'DELETE ALL DATA') {
        errorDiv.textContent = 'Incorrect confirmation phrase. Please type exactly: DELETE ALL DATA';
        errorDiv.classList.add('show');
        return;
    }

    // Disable button during request
    confirmBtn.disabled = true;
    confirmBtn.textContent = 'Resetting & Starting...';

    try {
        // Step 1: Reset
        const resetResponse = await fetch('/api/admin/reset', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                action: currentProducerResetAction,
                confirmation_phrase: confirmationInput
            })
        });

        const resetData = await resetResponse.json();

        if (!resetResponse.ok || !resetData.success) {
            errorDiv.textContent = resetData.error || 'Reset failed. Producer not started.';
            errorDiv.classList.add('show');
            confirmBtn.disabled = false;
            confirmBtn.textContent = 'Confirm and Start';
            return;
        }

        showToast(resetData.message, 'success');

        // Step 2: Start Producer
        const producerStarted = await startProducerDirect();

        // Only close modal if producer started successfully
        if (producerStarted) {
            closeProducerResetConfirmModal();
        } else {
            // Producer start failed, keep modal open to show error
            confirmBtn.disabled = false;
            confirmBtn.textContent = 'Confirm and Start';
        }

    } catch (error) {
        errorDiv.textContent = 'Network error. Please check your connection.';
        errorDiv.classList.add('show');
        confirmBtn.disabled = false;
        confirmBtn.textContent = 'Confirm and Start';
    }
}

// ========================================
// Job Management - Retry Modal
// ========================================

function retryFailedJobs() {
    document.getElementById('retry-error').classList.remove('show');
    document.getElementById('retry-modal').style.display = 'block';
}

function closeRetryModal() {
    document.getElementById('retry-modal').style.display = 'none';
}

async function executeRetryJobs() {
    const errorDiv = document.getElementById('retry-error');
    const confirmBtn = document.getElementById('btn-confirm-retry');

    // Disable button
    confirmBtn.disabled = true;
    confirmBtn.textContent = 'Processing...';
    errorDiv.classList.remove('show');

    try {
        const response = await fetch('/api/admin/jobs/retry', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            }
        });

        const data = await response.json();

        if (response.ok && data.success) {
            closeRetryModal();
            showToast('Successfully requeued failed jobs.', 'success');
        } else {
            errorDiv.textContent = data.error || 'Failed to retry jobs.';
            errorDiv.classList.add('show');
        }
    } catch (error) {
        errorDiv.textContent = 'Network error. Please check your connection.';
        errorDiv.classList.add('show');
    } finally {
        confirmBtn.disabled = false;
        confirmBtn.textContent = 'Confirm';
    }
}

// ========================================
// Job Management - Retry Processing Jobs
// ========================================

function retryProcessingJobs() {
    document.getElementById('retry-processing-error').classList.remove('show');
    document.getElementById('retry-processing-modal').style.display = 'block';
}

function closeRetryProcessingModal() {
    document.getElementById('retry-processing-modal').style.display = 'none';
}

async function executeRetryProcessingJobs() {
    const errorDiv = document.getElementById('retry-processing-error');
    const confirmBtn = document.getElementById('btn-confirm-retry-processing');

    // Disable button
    confirmBtn.disabled = true;
    confirmBtn.textContent = 'Processing...';
    errorDiv.classList.remove('show');

    try {
        const response = await fetch('/api/admin/jobs/retry-processing', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            }
        });

        const data = await response.json();

        if (response.ok && data.success) {
            closeRetryProcessingModal();
            showToast('Successfully requeued processing jobs.', 'success');
        } else {
            errorDiv.textContent = data.error || 'Failed to retry processing jobs.';
            errorDiv.classList.add('show');
        }
    } catch (error) {
        errorDiv.textContent = 'Network error. Please check your connection.';
        errorDiv.classList.add('show');
    } finally {
        confirmBtn.disabled = false;
        confirmBtn.textContent = 'Confirm';
    }
}

async function startProducerDirect() {
    const errorDiv = document.getElementById('producer-error');
    const startBtn = document.getElementById('btn-start-producer');

    errorDiv.classList.remove('show');

    const payload = {
        mode: currentProducerMode
    };

    if (currentProducerMode === 'test') {
        const sampleCount = parseInt(document.getElementById('sample-count').value);

        if (isNaN(sampleCount) || sampleCount < 1 || sampleCount > 10000) {
            errorDiv.textContent = 'Sample count must be between 1 and 10000.';
            errorDiv.classList.add('show');
            return false;  // Return false on validation failure
        }

        payload.sample_count = sampleCount;
    }

    // Disable button if in modal context
    if (startBtn) {
        startBtn.disabled = true;
        startBtn.textContent = 'Starting...';
    }

    try {
        const response = await fetch('/api/admin/producer/start', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(payload)
        });

        const data = await response.json();

        if (response.ok && data.success) {
            if (document.getElementById('producer-modal').style.display === 'block') {
                closeProducerModal();
                currentProducerMode = null;  // Reset mode after closing modal
            }
            showToast(data.message, 'success');

            // Immediately update producer status
            if (window.dashboardInstance) {
                window.dashboardInstance.fetchDashboardStatus();
            }
            return true;  // Return true on success
        } else {
            const targetErrorDiv = document.getElementById('producer-modal').style.display === 'block'
                ? document.getElementById('producer-error')
                : document.getElementById('producer-reset-error');

            targetErrorDiv.textContent = data.error || 'Failed to start producer.';
            targetErrorDiv.classList.add('show');
            return false;  // Return false on failure
        }
    } catch (error) {
        const targetErrorDiv = document.getElementById('producer-modal').style.display === 'block'
            ? document.getElementById('producer-error')
            : document.getElementById('producer-reset-error');

        targetErrorDiv.textContent = 'Network error. Please check your connection.';
        targetErrorDiv.classList.add('show');
        return false;  // Return false on error
    } finally {
        if (startBtn) {
            startBtn.disabled = false;
            startBtn.textContent = 'Start Producer';
        }
        const confirmBtn = document.getElementById('btn-confirm-producer-reset');
        if (confirmBtn) {
            confirmBtn.disabled = false;
            confirmBtn.textContent = 'Confirm and Start';
        }
    }
}


// ========================================
// Scheduler Controls
// ========================================

async function startScheduler() {
    const btn = document.getElementById('btn-scheduler-start');
    btn.disabled = true;
    btn.textContent = 'Starting...';

    try {
        const response = await fetch('/api/admin/scheduler/start', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({})
        });
        const data = await response.json();
        if (data.success) {
            showToast(data.message, 'success');
        } else {
            showToast(data.error, 'error');
        }
    } catch (e) {
        showToast('Network error', 'error');
    } finally {
        btn.textContent = 'Start Scheduler';
        // Button state will be updated by SSE
    }
}

async function stopScheduler() {
    const btn = document.getElementById('btn-scheduler-stop');
    btn.disabled = true;
    btn.textContent = 'Stopping...';

    try {
        const response = await fetch('/api/admin/scheduler/stop', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });
        const data = await response.json();
        if (data.success) {
            showToast(data.message, 'success');
        } else {
            showToast(data.error, 'error');
        }
    } catch (e) {
        showToast('Network error', 'error');
    } finally {
        btn.textContent = 'Stop Scheduler';
        // Button state will be updated by SSE
    }
}

// ========================================
// Producer Status Polling
// ========================================




// ========================================
// Toast Notifications
// ========================================

function showToast(message, type = 'info') {
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.textContent = message;

    const container = document.getElementById('toast-container');
    container.appendChild(toast);

    setTimeout(() => {
        toast.classList.add('fade-out');
        setTimeout(() => toast.remove(), 300);
    }, 5000);
}


// ========================================
// Modal Event Listeners
// ========================================

// Close modal on Escape key
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
        closeResetModal();
        closeProducerModal();
        closeProducerResetConfirmModal();
        closeRetryModal();
        closeRetryProcessingModal();
    }
});

// Close modal on background click
window.addEventListener('click', (e) => {
    if (e.target.id === 'reset-modal') {
        closeResetModal();
    }
    if (e.target.id === 'producer-modal') {
        closeProducerModal();
    }
    if (e.target.id === 'producer-reset-confirm-modal') {
        closeProducerResetConfirmModal();
    }
    if (e.target.id === 'retry-modal') {
        closeRetryModal();
    }
    if (e.target.id === 'retry-processing-modal') {
        closeRetryProcessingModal();
    }
});
