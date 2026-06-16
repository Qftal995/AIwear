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

public interface PythonImageService {

    void uploadImage(Long userId, String ossUrl);

    boolean validateImage(Path filePath);

    List<SearchImageResponse> search(Long userId, SearchImageRequest searchImageRequest);

    EditImageResponse edit(EditImageRequest editImageRequest);

    MergeImageResponse merge(MergeImageRequest mergeImageRequest);

    ChatResponse chat(Long userId, ChatRequest chatRequest);

    List<WardrobeItemResponse> getWardrobe(Long userId);
}
