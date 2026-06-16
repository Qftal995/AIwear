package com.bitejiuyeke.dto.response;

import lombok.Data;
import java.util.List;
import java.util.Map;

@Data
public class ChatResponse {

    private String sessionId;

    private String reply;

    private List<Map<String, Object>> steps;

    private List<Map<String, Object>> subResults;
}
