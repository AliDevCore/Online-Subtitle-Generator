# OnlineSub Architecture

```mermaid
flowchart TD
    subgraph UI ["PySide6 Graphical Interface"]
        MainWindow["MainWindow (English UI)"]
        PerfDialog["PerformanceDialog"]
        CredDialog["CredentialsDialog"]
        BatchDialog["BatchDialog"]
        LogViewer["LogViewerDialog"]
    end

    subgraph Workers ["Asynchronous Workers (QThread)"]
        ASRWorker["ASRWorker (Pipeline A)"]
        TransWorker["TranslationWorker (Pipeline B)"]
        BatchWorker["BatchWorker (Queue)"]
    end

    subgraph CoreServices ["Core Services"]
        FFmpegSvc["FFmpegService (Probe & Audio Slice)"]
        ASRSvc["ASRService (Pipeline A)"]
        TransSvc["TranslationService (Pipeline B)"]
        Chunker["AudioChunker (Overlap & Reconcile)"]
        SRTParser["SRTParser (Validate & Serialize)"]
        ResCtrl["ResourceController (CPU & Priority)"]
        CredMgr["CredentialManager (Windows Credential Manager)"]
        DB["Database (SQLite Resumability)"]
    end

    subgraph Providers ["AI Providers & Adapters"]
        GeminiASR["GeminiASRProvider"]
        GeminiTrans["GeminiTranslationProvider"]
        CF_ASR["CloudflareASRProvider"]
        CF_Trans["CloudflareTranslationProvider"]
        HF_ASR["HuggingFaceASRProvider"]
        HF_Trans["HuggingFaceTranslationProvider"]
        LocalWhisper["LocalWhisperASRProvider"]
    end

    MainWindow --> ASRWorker
    MainWindow --> TransWorker
    MainWindow --> BatchWorker
    MainWindow --> PerfDialog
    MainWindow --> CredDialog
    MainWindow --> LogViewer

    ASRWorker --> ASRSvc
    TransWorker --> TransSvc
    BatchWorker --> ASRSvc
    BatchWorker --> TransSvc

    ASRSvc --> FFmpegSvc
    ASRSvc --> Chunker
    ASRSvc --> SRTParser
    ASRSvc --> ResCtrl
    ASRSvc --> DB
    ASRSvc --> Providers

    TransSvc --> SRTParser
    TransSvc --> DB
    TransSvc --> Providers

    Providers --> CredMgr
```

## Architectural Design Principles

1. **Independent Pipelines**: ASR and Translation are completely decoupled. Translation operates directly on `.srt` files and never requires media files or rerunning speech recognition.
2. **Local vs Cloud Resource Separation**: CPU Usage Target and Process Priority are applied strictly to local FFmpeg extraction and local Faster-Whisper inference. Cloud API network requests are never throttled.
3. **Zero Plaintext Credentials**: API keys are routed through Windows Credential Manager and redacted from all logs and diagnostics.
4. **Resumability**: Multi-chunk operations and batch queues persist their state in SQLite (`onlinesub.db`).
