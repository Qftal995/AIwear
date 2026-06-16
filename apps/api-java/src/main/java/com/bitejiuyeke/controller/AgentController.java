package com.bitejiuyeke.controller;

import com.bitejiuyeke.common.Result;
import com.bitejiuyeke.dto.request.ChatRequest;
import com.bitejiuyeke.dto.response.ChatResponse;
import com.bitejiuyeke.dto.response.WardrobeItemResponse;
import com.bitejiuyeke.service.PythonImageService;
import com.bitejiuyeke.util.JwtUtil;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
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
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

import com.fasterxml.jackson.databind.ObjectMapper;

@Slf4j
@RestController
@RequestMapping("/api/agent")
public class AgentController {

    @Autowired
    private PythonImageService pythonImageService;

    @Autowired
    private JwtUtil jwtUtil;

    @Autowired
    private ObjectMapper objectMapper;

    @Value("${python.service.base-url:http://127.0.0.1:5000}")
    private String pythonBaseUrl;

    private final ExecutorService sseExecutor = Executors.newCachedThreadPool();

    @PostMapping("/chat")
    public Result<ChatResponse> chat(
            @RequestBody ChatRequest chatRequest,
            @RequestHeader(value = "Authorization") String authorization
    ) {
        String token = jwtUtil.parseToken(authorization);
        Long userId = jwtUtil.getUserId(token);

        if (chatRequest.getSessionId() == null || chatRequest.getSessionId().isBlank()) {
            chatRequest.setSessionId(UUID.randomUUID().toString().replace("-", ""));
        }

        ChatResponse response = pythonImageService.chat(userId, chatRequest);
        return Result.success("对话完成", response);
    }

    @GetMapping(value = "/chat/stream", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public SseEmitter chatStream(
            @RequestParam("message") String message,
            @RequestParam(value = "sessionId", required = false) String sessionId,
            @RequestHeader(value = "Authorization") String authorization
    ) {
        String token = jwtUtil.parseToken(authorization);
        Long userId = jwtUtil.getUserId(token);

        if (sessionId == null || sessionId.isBlank()) {
            sessionId = UUID.randomUUID().toString().replace("-", "");
        }

        SseEmitter emitter = new SseEmitter(300000L);

        String finalSessionId = sessionId;
        sseExecutor.execute(() -> {
            try {
                String url = pythonBaseUrl + "/api/chat/stream"
                        + "?message=" + java.net.URLEncoder.encode(message, StandardCharsets.UTF_8)
                        + "&userId=" + userId
                        + "&sessionId=" + finalSessionId;

                HttpClient client = HttpClient.newBuilder()
                        .connectTimeout(Duration.ofSeconds(30))
                        .build();

                HttpRequest request = HttpRequest.newBuilder()
                        .uri(URI.create(url))
                        .header("Accept", "text/event-stream")
                        .timeout(Duration.ofSeconds(300))
                        .GET()
                        .build();

                HttpResponse<java.io.InputStream> response = client.send(request,
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
    public Result<List<WardrobeItemResponse>> wardrobe(
            @RequestHeader(value = "Authorization") String authorization
    ) {
        String token = jwtUtil.parseToken(authorization);
        Long userId = jwtUtil.getUserId(token);

        List<WardrobeItemResponse> items = pythonImageService.getWardrobe(userId);
        return Result.success("查询成功", items);
    }
}
