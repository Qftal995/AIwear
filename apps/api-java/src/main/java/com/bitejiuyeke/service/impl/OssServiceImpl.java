package com.bitejiuyeke.service.impl;

import com.aliyun.oss.OSS;
import com.aliyun.oss.OSSClientBuilder;
import com.bitejiuyeke.service.OssService;
import jakarta.annotation.PostConstruct;
import jakarta.annotation.PreDestroy;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import java.io.InputStream;

@Slf4j
@Service
public class OssServiceImpl implements OssService {

    @Value("${oss.endpoint:}")
    private String endpoint;

    @Value("${oss.access-key-id:}")
    private String accessKeyId;

    @Value("${oss.access-key-secret:}")
    private String accessKeySecret;

    @Value("${oss.bucket:}")
    private String bucketName;

    @Value("${oss.cname-domain:}")
    private String cnameDomain;

    private OSS client;

    @PostConstruct
    public void init() {
        if (endpoint == null || endpoint.isBlank()
                || accessKeyId == null || accessKeyId.isBlank()) {
            log.info("OSS 未配置（endpoint/accessKeyId 为空），使用本地存储");
            return;
        }
        try {
            client = new OSSClientBuilder().build(endpoint, accessKeyId, accessKeySecret);
            log.info("OSS 客户端初始化成功: endpoint={}, bucket={}", endpoint, bucketName);
        } catch (Exception e) {
            log.error("OSS 客户端初始化失败: {}", e.getMessage());
            client = null;
        }
    }

    @Override
    public boolean isEnabled() {
        return client != null;
    }

    @Override
    public String upload(String objectName, InputStream inputStream, String contentType) {
        if (client == null) {
            log.debug("OSS 未启用，跳过上传: {}", objectName);
            return null;
        }
        try {
            var metadata = new com.aliyun.oss.model.ObjectMetadata();
            if (contentType != null && !contentType.isBlank()) {
                metadata.setContentType(contentType);
            }
            client.putObject(bucketName, objectName, inputStream, metadata);

            String domain = (cnameDomain != null && !cnameDomain.isBlank())
                    ? cnameDomain
                    : "https://" + bucketName + "." + endpoint;
            return domain + "/" + objectName;
        } catch (Exception e) {
            log.error("OSS 上传失败: objectName={}, error={}", objectName, e.getMessage());
            throw new RuntimeException("OSS 上传失败: " + e.getMessage());
        }
    }

    @PreDestroy
    public void destroy() {
        if (client != null) {
            client.shutdown();
        }
    }
}
