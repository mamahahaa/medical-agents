let sessionId = null;
let isProcessing = false;
let currentImageFile = null;

// Make sure DOM is fully loaded before adding event listeners
document.addEventListener('DOMContentLoaded', function() {
    let activeMode = 'chat'; // Track current active mode
    const interfaces = {
        'chat': {
            button: document.getElementById('chat-mode-btn'),
            interface: document.getElementById('chat-interface'),
            data: { messages: [] }
        },
        'image': {
            button: document.getElementById('image-mode-btn'),
            interface: document.getElementById('image-analysis-interface'),
            data: { lastAnalysis: null }
        },
        'diagnosis': {
            button: document.getElementById('diagnosis-mode-btn'),
            interface: document.getElementById('diagnosis-interface'),
            data: {
                basicInfo: '',
                symptoms: '',
                medicalHistory: '',
                medications: '',
                vitalSigns: '',
                diagnosisResults: []
            }
        },
        'browser': {
            button: document.getElementById('browser-mode-btn'),
            interface: document.getElementById('browser-interface'),
            data: { lastResult: null }
        },
        'deep-search': {
            button: document.getElementById('deep-search-mode-btn'),
            interface: document.getElementById('deep-search-interface'),
            data: { lastResult: null }
        }
    };

    // Function to switch modes
    function switchMode(mode) {
        // Save current interface data
        saveInterfaceData(activeMode);
        
        // Hide all interfaces with fade out
        Object.values(interfaces).forEach(({ interface }) => {
            interface.style.opacity = '0';
            setTimeout(() => {
                interface.style.display = 'none';
            }, 300);
        });

        // Remove active class from all buttons
        Object.values(interfaces).forEach(({ button }) => {
            button.classList.remove('active');
        });

        // Show selected interface with fade in
        setTimeout(() => {
            interfaces[mode].interface.style.display = 'flex';
            setTimeout(() => {
                interfaces[mode].interface.style.opacity = '1';
            }, 50);
        }, 300);

        interfaces[mode].button.classList.add('active');
        activeMode = mode;

        // Restore interface data
        restoreInterfaceData(mode);
    }

    // Save interface data
    function saveInterfaceData(mode) {
        switch(mode) {
            case 'chat':
                interfaces.chat.data.messages = Array.from(document.querySelectorAll('.chat-messages .message'))
                    .map(msg => ({
                        type: msg.className.split(' ')[1],
                        content: msg.textContent
                    }));
                break;
            case 'diagnosis':
                interfaces.diagnosis.data = {
                    basicInfo: document.getElementById('basic-info').value,
                    symptoms: document.getElementById('symptoms').value,
                    medicalHistory: document.getElementById('medical-history').value,
                    medications: document.getElementById('medications').value,
                    vitalSigns: document.getElementById('vital-signs').value,
                    diagnosisResults: Array.from(document.querySelectorAll('.diagnosis-entry'))
                        .map(entry => ({
                            specialist: entry.querySelector('.specialist-name').textContent,
                            message: entry.querySelector('.diagnosis-message').textContent
                        }))
                };
                break;
        }
    }

    // Restore interface data
    function restoreInterfaceData(mode) {
        switch(mode) {
            case 'chat':
                const messagesDiv = document.getElementById('chat-messages');
                messagesDiv.innerHTML = ''; // Clear existing messages
                interfaces.chat.data.messages.forEach(msg => {
                    addMessage(msg.content, msg.type);
                });
                break;
            case 'diagnosis':
                const data = interfaces.diagnosis.data;
                document.getElementById('basic-info').value = data.basicInfo;
                document.getElementById('symptoms').value = data.symptoms;
                document.getElementById('medical-history').value = data.medicalHistory;
                document.getElementById('medications').value = data.medications;
                document.getElementById('vital-signs').value = data.vitalSigns;
                
                const diagnosisLog = document.getElementById('diagnosis-log');
                diagnosisLog.innerHTML = '';
                data.diagnosisResults.forEach(result => {
                    addDiagnosisEntry(result.specialist, result.message);
                });
                break;
        }
    }

    // Add mode switch event listeners
    Object.entries(interfaces).forEach(([mode, { button }]) => {
        button.addEventListener('click', () => switchMode(mode));
    });

    // Chat functionality
    const messageInput = document.getElementById('message-input');
    const sendButton = document.getElementById('send-button');
    const imageUpload = document.getElementById('image-upload');

    function addMessage(content, type) {
        const messagesDiv = document.getElementById('chat-messages');
        const messageDiv = document.createElement('div');
        messageDiv.className = `message ${type}`;
        messageDiv.textContent = content;
        messagesDiv.appendChild(messageDiv);
        messagesDiv.scrollTop = messagesDiv.scrollHeight;
    }

    function setLoading(loading) {
        const button = document.getElementById('send-button');
        const buttonText = button.querySelector('.button-text');
        const spinner = button.querySelector('.loading-spinner');
        
        isProcessing = loading;
        button.disabled = loading;
        messageInput.disabled = loading;
        
        if (loading) {
            buttonText.style.display = 'none';
            spinner.style.display = 'block';
        } else {
            buttonText.style.display = 'block';
            spinner.style.display = 'none';
        }
    }

    async function sendMessage() {
        const message = messageInput.value.trim();
        
        if (!message || isProcessing) return;
        
        addMessage(message, 'user');
        messageInput.value = '';
        
        setLoading(true);
        
        try {
            const response = await fetch('/chat', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    message: message,
                    session_id: sessionId
                })
            });
            
            const data = await response.json();
            
            if (!sessionId) {
                sessionId = data.session_id;
            }
            
            if (data.error) {
                addMessage(data.error, 'system');
            } else {
                data.responses.forEach(response => {
                    addMessage(response, 'assistant');
                });
            }
        } catch (error) {
            addMessage('Sorry, an error occurred. Please try again.', 'system');
            console.error('Error:', error);
        } finally {
            setLoading(false);
        }
    }

    // Add event listeners for chat functionality
    if (sendButton) {
        sendButton.addEventListener('click', sendMessage);
    }

    if (messageInput) {
        messageInput.addEventListener('keypress', function(e) {
            if (e.key === 'Enter' && !isProcessing) {
                sendMessage();
            }
        });
    }

    // Debug logging
    console.log('Event listeners initialized');

    // Add diagnosis mode button handler
    const diagnosisModeBtn = document.getElementById('diagnosis-mode-btn');
    const diagnosisInterface = document.getElementById('diagnosis-interface');

    diagnosisModeBtn.addEventListener('click', function() {
        console.log('Diagnosis mode clicked');
        diagnosisModeBtn.classList.add('active');
        chatModeBtn.classList.remove('active');
        imageModeBtn.classList.remove('active');
        diagnosisInterface.style.display = 'flex';
        chatInterface.style.display = 'none';
        imageAnalysisInterface.style.display = 'none';
    });

    // Handle diagnosis submission
    const startDiagnosisBtn = document.getElementById('start-diagnosis');
    if (startDiagnosisBtn) {
        startDiagnosisBtn.addEventListener('click', startDiagnosis);
    }

    async function startDiagnosis() {
        const diagnosisLog = document.getElementById('diagnosis-log');
        const patientCase = {
            basic_info: document.getElementById('basic-info').value,
            symptoms: document.getElementById('symptoms').value,
            medical_history: document.getElementById('medical-history').value,
            medications: document.getElementById('medications').value,
            vital_signs: document.getElementById('vital-signs').value
        };

        // Clear previous diagnosis
        diagnosisLog.innerHTML = '<div class="diagnosis-entry">Starting diagnosis process...</div>';

        try {
            const response = await fetch('/run_diagnosis', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(patientCase)
            });

            const data = await response.json();

            if (data.error) {
                addDiagnosisEntry('System', data.error, 'error');
            } else {
                // Process and display each specialist's response
                data.diagnosis_process.forEach(entry => {
                    addDiagnosisEntry(entry.specialist, entry.message);
                });
            }
        } catch (error) {
            addDiagnosisEntry('System', 'An error occurred during diagnosis. Please try again.', 'error');
            console.error('Error:', error);
        }
    }

    function addDiagnosisEntry(specialist, message, type = 'normal') {
        const diagnosisLog = document.getElementById('diagnosis-log');
        const entry = document.createElement('div');
        entry.className = `diagnosis-entry ${type}`;
        entry.innerHTML = `
            <div class="specialist-name">${specialist}</div>
            <div class="diagnosis-message">${message}</div>
        `;
        diagnosisLog.appendChild(entry);
        diagnosisLog.scrollTop = diagnosisLog.scrollHeight;
    }

    // Add browser task functionality
    const startBrowserTaskBtn = document.getElementById('start-browser-task');
    if (startBrowserTaskBtn) {
        startBrowserTaskBtn.addEventListener('click', startBrowserTask);
    }

    // Add file upload handling
    function initializeFileUpload() {
        const dropZone = document.getElementById('file-drop-zone');
        const fileInput = document.getElementById('browser-file');
        const fileNameDisplay = document.getElementById('file-name');

        // Prevent default drag behaviors
        ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
            dropZone.addEventListener(eventName, preventDefaults, false);
            document.body.addEventListener(eventName, preventDefaults, false);
        });

        // Highlight drop zone when item is dragged over it
        ['dragenter', 'dragover'].forEach(eventName => {
            dropZone.addEventListener(eventName, highlight, false);
        });

        ['dragleave', 'drop'].forEach(eventName => {
            dropZone.addEventListener(eventName, unhighlight, false);
        });

        // Handle dropped files
        dropZone.addEventListener('drop', handleDrop, false);
        
        // Handle file selection
        fileInput.addEventListener('change', handleFileSelect, false);

        function preventDefaults (e) {
            e.preventDefault();
            e.stopPropagation();
        }

        function highlight(e) {
            dropZone.classList.add('dragover');
        }

        function unhighlight(e) {
            dropZone.classList.remove('dragover');
        }

        function handleDrop(e) {
            const dt = e.dataTransfer;
            const files = dt.files;
            handleFiles(files);
        }

        function handleFileSelect(e) {
            const files = e.target.files;
            handleFiles(files);
        }

        function handleFiles(files) {
            if (files.length > 0) {
                const file = files[0];
                const validTypes = ['.pdf', '.doc', '.docx', '.txt'];
                const fileExtension = '.' + file.name.split('.').pop().toLowerCase();
                
                if (validTypes.includes(fileExtension)) {
                    fileNameDisplay.textContent = file.name;
                    dropZone.style.borderColor = '#28a745';
                } else {
                    fileNameDisplay.textContent = 'Invalid file type. Please use PDF, DOC, DOCX, or TXT files.';
                    dropZone.style.borderColor = '#dc3545';
                    fileInput.value = '';
                }
            }
        }
    }

    // Update startBrowserTask function
    async function startBrowserTask() {
        const browserLog = document.getElementById('browser-log');
        const task = document.getElementById('browser-task').value;
        const model = document.getElementById('browser-model').value;
        const headless = document.getElementById('browser-headless').checked;
        const fileInput = document.getElementById('browser-file');
        
        if (!task.trim()) {
            browserLog.textContent = 'Please enter a task description.';
            return;
        }
        
        const button = document.getElementById('start-browser-task');
        button.disabled = true;
        browserLog.textContent = 'Running task...';
        
        try {
            const formData = new FormData();
            formData.append('task', task);
            formData.append('model', model);
            formData.append('headless', headless);
            
            if (fileInput.files.length > 0) {
                formData.append('file', fileInput.files[0]);
            }
            
            const response = await fetch('/run_browser_task', {
                method: 'POST',
                body: formData
            });
            
            const data = await response.json();
            
            if (data.error) {
                browserLog.textContent = `Error: ${data.error}`;
            } else {
                browserLog.textContent = data.result;
                interfaces.browser.data.lastResult = data.result;
            }
        } catch (error) {
            browserLog.textContent = `Error: ${error.message}`;
            console.error('Error:', error);
        } finally {
            button.disabled = false;
        }
    }

    // Initialize file upload functionality
    initializeFileUpload();

    // Add deep search functionality
    const deepSearchModeBtn = document.getElementById('deep-search-mode-btn');
    const deepSearchInterface = document.getElementById('deep-search-interface');

    // Add deep search functionality
    async function startDeepSearch() {
        const researchLog = document.getElementById('research-log');
        const topic = document.getElementById('research-topic').value;
        const llmModel = document.getElementById('llm-model').value;
        const searchApi = document.getElementById('search-api').value;
        const loops = document.getElementById('research-loops').value;
        
        if (!topic.trim()) {
            researchLog.textContent = 'Please enter a research topic.';
            return;
        }
        
        const button = document.getElementById('start-research');
        button.disabled = true;
        researchLog.textContent = 'Starting research...';
        
        try {
            const response = await fetch('/deep_search', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    research_topic: topic,
                    llm_provider: llmModel,
                    search_api: searchApi,
                    max_loops: parseInt(loops)
                })
            });
            
            const data = await response.json();
            
            if (data.error) {
                researchLog.textContent = `Error: ${data.error}`;
            } else {
                researchLog.textContent = data.result;
                interfaces['deep-search'].data.lastResult = data.result;
            }
        } catch (error) {
            researchLog.textContent = `Error: ${error.message}`;
            console.error('Error:', error);
        } finally {
            button.disabled = false;
        }
    }

    // Add event listeners
    document.getElementById('start-research')?.addEventListener('click', startDeepSearch);
});

// Log any errors that occur
window.onerror = function(msg, url, lineNo, columnNo, error) {
    console.error('Error: ' + msg + '\nURL: ' + url + '\nLine: ' + lineNo + '\nColumn: ' + columnNo + '\nError object: ' + JSON.stringify(error));
    return false;
}; 