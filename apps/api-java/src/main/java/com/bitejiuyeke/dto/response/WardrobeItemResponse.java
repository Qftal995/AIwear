package com.bitejiuyeke.dto.response;

import lombok.Data;
import java.util.Map;

@Data
public class WardrobeItemResponse {

    private String imageId;

    private String ossUrl;

    private String description;

    private Map<String, String> tags;
}
