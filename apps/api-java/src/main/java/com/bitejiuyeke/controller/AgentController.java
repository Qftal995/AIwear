package com.bitejiuyeke.controller;

import com.bitejiuyeke.common.Result;
import com.bitejiuyeke.dto.request.ChatRequest;
import com.bitejiuyeke.dto.response.ChatResponse;
import com.bitejiuyeke.dto.response.WardrobeItemResponse;
import com.bitejiuyeke.service.PythonImageService;
import jakarta.servlet.http.HttpServletRequest;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import jakarta.annotation.PreDestroy;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.ThreadFactory;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

@Slf4j
@RestController
@RequestMapping("/api/agent")
public class AgentController {

    @Autowired
    private PythonImageService pythonImageService;

    @Value("${python.service.base-url:http://127.0.0.1:5001}")
    private String pythonBaseUrl;

    @Autowired
    private HttpClient sharedHttpClient;

    private final ExecutorService sseExecutor = new ThreadPoolExecutor(
            2, 8, 60L, TimeUnit.SECONDS,
            new LinkedBlockingQueue<>(32),
            new ThreadFactory() {
                private final AtomicInteger counter = new AtomicInteger(1);
                @Override
                public Thread newThread(Runnable r) {
                    Thread t = new Thread(r, "sse-agent-" + counter.getAndIncrement());
                    t.setDaemon(true);
                    return t;
                }
            },
            new ThreadPoolExecutor.CallerRunsPolicy()
    );

    @PostMapping("/chat")
    public Result<ChatResponse> chat(
            @RequestBody ChatRequest chatRequest,
            HttpServletRequest request
    ) {
        Long userId = (Long) request.getAttribute("userId");

        if (chatRequest.getSessionId() == null || chatRequest.getSessionId().isBlank()) {
            chatRequest.setSessionId(UUID.randomUUID().toString().replace("-", ""));
        }

        ChatResponse response = pythonImageService.chat(userId, chatRequest);
        return Result.success("对话完成", response);
    }

    @GetMapping(value = "/chat/stream", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public SseEmitter chatStream(
            @RequestParam(value = "message", required = false) String message,
            @RequestParam(value = "sessionId", required = false) String sessionId,
            HttpServletRequest request
    ) {
        Long userId = (Long) request.getAttribute("userId");

        if (sessionId == null || sessionId.isBlank()) {
            sessionId = UUID.randomUUID().toString().replace("-", "");
        }

        SseEmitter emitter = new SseEmitter(300000L);

        String finalSessionId = sessionId;
        sseExecutor.execute(() -> {
            try {
                StringBuilder urlBuilder = new StringBuilder(pythonBaseUrl)
                        .append("/api/chat/stream")
                        .append("?userId=").append(userId)
                        .append("&sessionId=").append(java.net.URLEncoder.encode(finalSessionId, StandardCharsets.UTF_8));
                if (message != null && !message.isBlank()) {
                    urlBuilder.append("&message=").append(java.net.URLEncoder.encode(message, StandardCharsets.UTF_8));
                }
                String url = urlBuilder.toString();

                HttpRequest pyRequest = HttpRequest.newBuilder()
                        .uri(URI.create(url))
                        .header("Accept", "text/event-stream")
                        .timeout(Duration.ofSeconds(300))
                        .GET()
                        .build();

                HttpResponse<java.io.InputStream> response = sharedHttpClient.send(pyRequest,
                        HttpResponse.BodyHandlers.ofInputStream());

                try (java.io.BufferedReader reader = new java.io.BufferedReader(
                        new java.io.InputStreamReader(response.body(), StandardCharsets.UTF_8))) {
                    String line;
                    while ((line = reader.readLine()) != null) {
                        if (line.startsWith("data: ")) {
                            String data = line.substring(6);
                            if ("[DONE]".equals(data)) {
                                emitter.complete();
                                return;
                            }
                            emitter.send(SseEmitter.event().data(data));
                        }
                    }
                }
                emitter.complete();
            } catch (Exception e) {
                log.error("SSE stream error: {}", e.getMessage());
                try {
                    emitter.send(SseEmitter.event()
                            .data("{\"type\":\"error\",\"error\":\"" + e.getMessage() + "\"}"));
                    emitter.complete();
                } catch (IOException ex) {
                    emitter.completeWithError(ex);
                }
            }
        });

        return emitter;
    }

    @GetMapping("/wardrobe")
    public Result<List<WardrobeItemResponse>> wardrobe(HttpServletRequest request) {
        Long userId = (Long) request.getAttribute("userId");
        List<WardrobeItemResponse> items = pythonImageService.getWardrobe(userId);
        return Result.success("查询成功", items);
    }

    @PostMapping("/tool/image/async")
    public Result<Map<String, Object>> submitImageAsync(
            @RequestParam("file") org.springframework.web.multipart.MultipartFile file,
            @RequestParam("instruction") String instruction
    ) {
        Map<String, Object> result = pythonImageService.submitAsyncTask(file, instruction);
        return Result.success("异步任务已提交", result);
    }

    @GetMapping("/tool/image/status/{taskId}")
    public Result<Map<String, Object>> getImageTaskStatus(@PathVariable String taskId) {
        Map<String, Object> result = pythonImageService.getTaskStatus(taskId);
        return Result.success("查询成功", result);
    }

    @GetMapping("/session-stats")
    public Result<Map<String, Object>> sessionStats(
            @RequestParam(value = "sessionId", required = false) String sessionId
    ) {
        Map<String, Object> result = pythonImageService.getSessionStats(sessionId);
        return Result.success("查询成功", result);
    }

    @PreDestroy
    public void destroy() {
        sseExecutor.shutdown();
        try {
            if (!sseExecutor.awaitTermination(10, TimeUnit.SECONDS)) {
                sseExecutor.shutdownNow();
            }
        } catch (InterruptedException e) {
            sseExecutor.shutdownNow();
            Thread.currentThread().interrupt();
        }
    }
}
