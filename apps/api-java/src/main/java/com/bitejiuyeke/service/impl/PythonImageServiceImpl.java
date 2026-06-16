package com.bitejiuyeke.service.impl;

import com.bitejiuyeke.dto.request.ChatRequest;
import com.bitejiuyeke.dto.request.EditImageRequest;
import com.bitejiuyeke.dto.request.MergeImageRequest;
import com.bitejiuyeke.dto.request.PythonUploadImageRequest;
import com.bitejiuyeke.dto.request.SearchImageRequest;
import com.bitejiuyeke.dto.response.ChatResponse;
import com.bitejiuyeke.dto.response.EditImageResponse;
import com.bitejiuyeke.dto.response.MergeImageResponse;
import com.bitejiuyeke.dto.response.PythonUploadImageResponse;
import com.bitejiuyeke.dto.response.SearchImageResponse;
import com.bitejiuyeke.dto.response.WardrobeItemResponse;
import com.bitejiuyeke.service.PythonImageService;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.core.io.FileSystemResource;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Service;
import org.springframework.util.LinkedMultiValueMap;
import org.springframework.util.MultiValueMap;
import org.springframework.web.client.RestTemplate;
import org.springframework.web.multipart.MultipartFile;

import java.io.IOException;
import java.io.InputStream;
import java.net.URI;
import java.net.URL;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.nio.file.StandardCopyOption;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.UUID;

@Slf4j
@Service
public class PythonImageServiceImpl implements PythonImageService {

    @Value("${python.service.base-url:http://127.0.0.1:5000}")
    private String pythonBaseUrl;

    private final HttpClient httpClient;
    private final ObjectMapper objectMapper;

    @Value("${file.upload.dir:uploads}")
    private String uploadBaseDir;

    @Autowired
    public PythonImageServiceImpl(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
        this.httpClient = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(30))
                .build();
    }

    @Override
    public void uploadImage(Long userId, String ossUrl) {
        PythonUploadImageRequest req = new PythonUploadImageRequest();
        req.setUserId(userId);
        req.setOssUrl(ossUrl);

        String requestJson;
        try {
            requestJson = objectMapper.writeValueAsString(req);
        } catch (Exception e) {
            throw new RuntimeException("构造请求体失败");
        }

        String url = pythonBaseUrl + "/api/upload-image";
        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create(url))
                .header("Content-Type", "application/json")
                .timeout(Duration.ofSeconds(60))
                .POST(HttpRequest.BodyPublishers.ofString(requestJson, StandardCharsets.UTF_8))
                .build();

        HttpResponse<String> response;
        try {
            response = httpClient.send(request, HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
        } catch (Exception e) {
            log.error("Python /api/upload-image 失败: {}", e.getMessage());
            throw new RuntimeException("Python 服务调用失败");
        }

        if (response.statusCode() < 200 || response.statusCode() >= 300) {
            log.error("Python 非 2xx: status={}", response.statusCode());
            throw new RuntimeException("Python 服务返回错误");
        }

        try {
            JsonNode root = objectMapper.readTree(response.body());
            boolean success = root.path("success").asBoolean(false);
            if (!success) {
                String error = root.path("error").asText("unknown");
                throw new RuntimeException("Python 上传失败: " + error);
            }
        } catch (RuntimeException e) {
            throw e;
        } catch (Exception e) {
            log.error("解析 Python 响应失败: {}", e.getMessage());
        }
    }

    @Override
    public boolean validateImage(Path filePath) {
        try {
            String url = pythonBaseUrl + "/api/validate-image";
            HttpHeaders headers = new HttpHeaders();
            headers.setContentType(MediaType.MULTIPART_FORM_DATA);

            MultiValueMap<String, Object> body = new LinkedMultiValueMap<>();
            body.add("file", new FileSystemResource(filePath));
            HttpEntity<MultiValueMap<String, Object>> entity = new HttpEntity<>(body, headers);
            RestTemplate rest = new RestTemplate();
            ResponseEntity<String> resp = rest.postForEntity(url, entity, String.class);
            return objectMapper.readTree(resp.getBody()).path("allow").asBoolean(false);
        } catch (Exception e) {
            log.error("validateImage 失败: {}", e.getMessage());
            return false;
        }
    }

    @Override
    public List<SearchImageResponse> search(Long userId, SearchImageRequest req) {
        String url = pythonBaseUrl + "/api/search-image";
        String query = req.getQuery();
        MultipartFile file = req.getFile();

        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.MULTIPART_FORM_DATA);

        try {
            MultiValueMap<String, Object> body = new LinkedMultiValueMap<>();
            body.add("userId", userId);
            if (query != null && !query.isBlank()) {
                body.add("query", query);
            }
            if (file != null && !file.isEmpty()) {
                byte[] bytes = file.getBytes();
                String filename = file.getOriginalFilename();
                ByteArrayResource fileResource = new ByteArrayResource(bytes) {
                    @Override
                    public String getFilename() {
                        return filename;
                    }
                };
                body.add("file", fileResource);
            }

            HttpEntity<MultiValueMap<String, Object>> entity = new HttpEntity<>(body, headers);
            RestTemplate rest = new RestTemplate();
            ResponseEntity<String> resp = rest.postForEntity(url, entity, String.class);
            JsonNode root = objectMapper.readTree(resp.getBody());
            JsonNode data = root.path("data");

            List<SearchImageResponse> list = new ArrayList<>();
            for (JsonNode node : data) {
                SearchImageResponse item = new SearchImageResponse();
                item.setFilePath(node.path("filePath").asText(""));
                item.setImageId(node.path("imageId").asText(""));
                item.setSimilarity(node.path("similarity").asDouble(0));
                item.setDescription(node.path("description").asText(""));
                list.add(item);
            }
            return list;
        } catch (Exception e) {
            log.error("search 失败: {}", e.getMessage());
            return List.of();
        }
    }

    @Override
    public EditImageResponse edit(EditImageRequest req) {
        String sourceUrl = req.getImage();
        String instruction = req.getInstruction();
        Path sourceTemp = null;
        Path editTemp = null;

        try {
            sourceTemp = downloadToTempFile(sourceUrl);
            String url = pythonBaseUrl + "/api/tool/image";
            HttpHeaders headers = new HttpHeaders();
            headers.setContentType(MediaType.MULTIPART_FORM_DATA);

            MultiValueMap<String, Object> body = new LinkedMultiValueMap<>();
            body.add("file", new FileSystemResource(sourceTemp.toFile()));
            body.add("instruction", instruction);

            HttpEntity<MultiValueMap<String, Object>> entity = new HttpEntity<>(body, headers);
            RestTemplate rest = new RestTemplate();
            ResponseEntity<String> resp = rest.postForEntity(url, entity, String.class);

            JsonNode root = objectMapper.readTree(resp.getBody());
            String pythonUrl = root.path("url").asText("");
            if (pythonUrl.isEmpty()) {
                throw new RuntimeException("Python 编辑未返回 URL");
            }

            editTemp = downloadToTempFile(pythonUrl);
            String localFileName = saveLocalFile(editTemp, "edited_");
            String saveUrl = "http://localhost:8081/uploads/images/" + localFileName;

            EditImageResponse result = new EditImageResponse();
            result.setUrl(pythonUrl);
            result.setSaveUrl(saveUrl);
            return result;
        } catch (Exception e) {
            log.error("edit 失败: {}", e.getMessage());
            throw new RuntimeException("图片编辑失败: " + e.getMessage());
        } finally {
            deleteTempFiles(sourceTemp, editTemp);
        }
    }

    @Override
    public MergeImageResponse merge(MergeImageRequest req) {
        String url1 = req.getImage1();
        String url2 = req.getImage2();
        String instruction = req.getInstruction();
        Path temp1 = null;
        Path temp2 = null;
        Path mergeTemp = null;

        try {
            temp1 = downloadToTempFile(url1);
            temp2 = downloadToTempFile(url2);
            String pyUrl = pythonBaseUrl + "/api/tool/image";
            HttpHeaders headers = new HttpHeaders();
            headers.setContentType(MediaType.MULTIPART_FORM_DATA);

            MultiValueMap<String, Object> body = new LinkedMultiValueMap<>();
            body.add("file1", new FileSystemResource(temp1.toFile()));
            body.add("file2", new FileSystemResource(temp2.toFile()));
            body.add("image_url1", url1);
            body.add("image_url2", url2);
            body.add("instruction", instruction);

            HttpEntity<MultiValueMap<String, Object>> entity = new HttpEntity<>(body, headers);
            RestTemplate rest = new RestTemplate();
            ResponseEntity<String> resp = rest.postForEntity(pyUrl, entity, String.class);

            JsonNode root = objectMapper.readTree(resp.getBody());
            String pythonUrl = root.path("url").asText("");
            if (pythonUrl.isEmpty()) {
                throw new RuntimeException("Python 合并未返回 URL");
            }

            mergeTemp = downloadToTempFile(pythonUrl);
            String localFileName = saveLocalFile(mergeTemp, "merged_");
            String saveUrl = "http://localhost:8081/uploads/images/" + localFileName;

            MergeImageResponse result = new MergeImageResponse();
            result.setUrl(pythonUrl);
            result.setSaveUrl(saveUrl);
            return result;
        } catch (Exception e) {
            log.error("merge 失败: {}", e.getMessage());
            throw new RuntimeException("图片合并失败: " + e.getMessage());
        } finally {
            deleteTempFiles(temp1, temp2, mergeTemp);
        }
    }

    @Override
    public ChatResponse chat(Long userId, ChatRequest chatRequest) {
        String message = chatRequest.getMessage();
        if (message == null || message.isBlank()) {
            message = chatRequest.getQuery();
        }
        if (message == null || message.isBlank()) {
            throw new RuntimeException("message 不能为空");
        }

        String sessionId = chatRequest.getSessionId();
        if (sessionId == null || sessionId.isBlank()) {
            sessionId = UUID.randomUUID().toString().replace("-", "");
        }

        try {
            Map<String, Object> reqBody = new java.util.LinkedHashMap<>();
            reqBody.put("message", message);
            reqBody.put("userId", userId);
            reqBody.put("sessionId", sessionId);
            String requestJson = objectMapper.writeValueAsString(reqBody);

            String url = pythonBaseUrl + "/api/chat";
            HttpRequest request = HttpRequest.newBuilder()
                    .uri(URI.create(url))
                    .header("Content-Type", "application/json")
                    .timeout(Duration.ofSeconds(120))
                    .POST(HttpRequest.BodyPublishers.ofString(requestJson, StandardCharsets.UTF_8))
                    .build();

            HttpResponse<String> response = httpClient.send(request,
                    HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));

            JsonNode root = objectMapper.readTree(response.body());
            ChatResponse result = new ChatResponse();
            result.setSessionId(root.path("sessionId").asText(sessionId));
            result.setReply(root.path("reply").asText(""));

            JsonNode stepsNode = root.path("steps");
            if (stepsNode.isArray()) {
                result.setSteps(objectMapper.convertValue(stepsNode,
                        new TypeReference<List<Map<String, Object>>>() {}));
            }

            JsonNode subNode = root.path("subResults");
            if (subNode.isArray()) {
                result.setSubResults(objectMapper.convertValue(subNode,
                        new TypeReference<List<Map<String, Object>>>() {}));
            }

            return result;
        } catch (Exception e) {
            log.error("chat 失败: {}", e.getMessage());
            throw new RuntimeException("Agent 对话失败: " + e.getMessage());
        }
    }

    @Override
    public List<WardrobeItemResponse> getWardrobe(Long userId) {
        try {
            String url = pythonBaseUrl + "/api/wardrobe/" + userId;
            HttpRequest request = HttpRequest.newBuilder()
                    .uri(URI.create(url))
                    .header("Accept", "application/json")
                    .timeout(Duration.ofSeconds(30))
                    .GET()
                    .build();

            HttpResponse<String> response = httpClient.send(request,
                    HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));

            JsonNode root = objectMapper.readTree(response.body());
            JsonNode data = root.path("data");
            List<WardrobeItemResponse> list = new ArrayList<>();
            for (JsonNode node : data) {
                WardrobeItemResponse item = new WardrobeItemResponse();
                item.setImageId(node.path("imageId").asText(""));
                item.setOssUrl(node.path("ossUrl").asText(""));
                item.setDescription(node.path("description").asText(""));

                JsonNode tagsNode = node.path("tags");
                if (tagsNode.isObject()) {
                    Map<String, String> tags = objectMapper.convertValue(tagsNode,
                            new TypeReference<Map<String, String>>() {});
                    item.setTags(tags);
                }
                list.add(item);
            }
            return list;
        } catch (Exception e) {
            log.error("getWardrobe 失败: {}", e.getMessage());
            return List.of();
        }
    }

    private Path downloadToTempFile(String fileUrl) {
        try {
            URL url = URI.create(fileUrl).toURL();
            Path tempFile = Files.createTempFile("aiwear-", ".tmp");
            try (InputStream is = url.openStream()) {
                Files.copy(is, tempFile, StandardCopyOption.REPLACE_EXISTING);
            }
            return tempFile;
        } catch (Exception e) {
            throw new RuntimeException("下载文件失败: " + e.getMessage());
        }
    }

    private String saveLocalFile(Path source, String prefix) throws IOException {
        String contentType = Files.probeContentType(source);
        if (contentType == null) contentType = "image/png";
        String ext = switch (contentType) {
            case "image/jpeg", "image/jpg" -> ".jpg";
            case "image/gif" -> ".gif";
            case "image/webp" -> ".webp";
            default -> ".png";
        };
        String fileName = prefix + UUID.randomUUID().toString().replace("-", "") + ext;
        Path localDir = Paths.get(uploadBaseDir, "images");
        Files.createDirectories(localDir);
        Path localFile = localDir.resolve(fileName);
        Files.copy(source, localFile, StandardCopyOption.REPLACE_EXISTING);
        return fileName;
    }

    private void deleteTempFiles(Path... paths) {
        for (Path p : paths) {
            if (p != null) {
                try {
                    Files.deleteIfExists(p);
                } catch (IOException ignored) {
                }
            }
        }
    }
}
