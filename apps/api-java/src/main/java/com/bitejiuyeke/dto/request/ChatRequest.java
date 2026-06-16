package com.bitejiuyeke.dto.request;

import lombok.Data;

@Data
public class ChatRequest {

    private String message;

    private String query;

    private String sessionId;

    private String imageUrl;
}
