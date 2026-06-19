package com.bitejiuyeke.service;

import com.bitejiuyeke.dto.request.ChatRequest;
import com.bitejiuyeke.dto.request.EditImageRequest;
import com.bitejiuyeke.dto.request.MergeImageRequest;
import com.bitejiuyeke.dto.request.SearchImageRequest;
import com.bitejiuyeke.dto.response.ChatResponse;
import com.bitejiuyeke.dto.response.EditImageResponse;
import com.bitejiuyeke.dto.response.MergeImageResponse;
import com.bitejiuyeke.dto.response.SearchImageResponse;
import com.bitejiuyeke.dto.response.WardrobeItemResponse;

import java.nio.file.Path;
import java.util.List;
import java.util.Map;

import org.springframework.web.multipart.MultipartFile;

public interface PythonImageService {

    void uploadImage(Long userId, String ossUrl);

    boolean validateImage(Path filePath);

    List<SearchImageResponse> search(Long userId, SearchImageRequest searchImageRequest);

    EditImageResponse edit(EditImageRequest editImageRequest);

    MergeImageResponse merge(MergeImageRequest mergeImageRequest);

    ChatResponse chat(Long userId, ChatRequest chatRequest);

    List<WardrobeItemResponse> getWardrobe(Long userId);

    /** Submit an image editing task asynchronously to the Python service. */
    Map<String, Object> submitAsyncTask(MultipartFile file, String instruction);

    /** Poll the status of an async image task by its task ID. */
    Map<String, Object> getTaskStatus(String taskId);

    /** Get session-level or global stats from the Python service. */
    Map<String, Object> getSessionStats(String sessionId);

    /** Delete a wardrobe item by its OSS URL. */
    void deleteByUrl(String ossUrl);
}
