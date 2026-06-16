package com.bitejiuyeke.dto.response;

import lombok.Data;

@Data
public class SearchImageResponse {

    private String filePath;

    private String fileName;

    private String imageId;

    private Double similarity;

    private String description;
}
