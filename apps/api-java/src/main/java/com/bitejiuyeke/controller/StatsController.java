package com.bitejiuyeke.controller;

import com.bitejiuyeke.common.Result;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.client.RestTemplate;

import java.util.Map;

@RestController
@RequestMapping("/api/agent")
public class StatsController {

    @Value("${ai-service.base-url:http://127.0.0.1:5000}")
    private String aiServiceBaseUrl;

    private final RestTemplate restTemplate = new RestTemplate();
    private final ObjectMapper objectMapper = new ObjectMapper();

    @GetMapping("/stats")
    public Result<Map<String, Object>> stats(
        @RequestParam(required = false) String sessionId
    ) {
        try {
            String url = aiServiceBaseUrl + "/api/session-stats";
            if (sessionId != null && !sessionId.isEmpty()) {
                url += "?sessionId=" + sessionId;
            }
            String resp = restTemplate.getForObject(url, String.class);
            JsonNode node = objectMapper.readTree(resp);
            JsonNode dataNode = node.get("data");
            Map<String, Object> data = objectMapper.convertValue(dataNode, Map.class);
            return Result.success(data);
        } catch (Exception e) {
            return Result.error("Failed to fetch stats: " + e.getMessage());
        }
    }
}
