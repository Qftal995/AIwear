package com.bitejiuyeke.service;

import java.io.InputStream;

public interface OssService {

    /**
     * Upload a file to OSS.
     * @param objectName object key (e.g., "aiwear/images/uuid.png")
     * @param inputStream file content
     * @param contentType MIME type
     * @return public OSS URL, or null if OSS is disabled
     */
    String upload(String objectName, InputStream inputStream, String contentType);

    boolean isEnabled();
}
