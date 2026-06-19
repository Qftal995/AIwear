package com.bitejiuyeke.service;

import com.bitejiuyeke.dto.request.EditImageRequest;
import com.bitejiuyeke.dto.request.MergeImageRequest;
import com.bitejiuyeke.dto.request.SearchImageRequest;
import com.bitejiuyeke.dto.response.EditImageResponse;
import com.bitejiuyeke.dto.response.MergeImageResponse;
import com.bitejiuyeke.dto.response.SearchImageResponse;
import com.bitejiuyeke.dto.response.UploadImageResponse;
import com.bitejiuyeke.entity.ImageFile;
import org.springframework.web.multipart.MultipartFile;

import java.util.List;

public interface FileService {

    UploadImageResponse uploadImage(MultipartFile file, Long userId);

    List<ImageFile> myImages(Long userId);

    List<SearchImageResponse> search(Long userId, SearchImageRequest searchImageRequest);

    EditImageResponse edit(Long userId, EditImageRequest editImageRequest);

    MergeImageResponse merge(Long userId, MergeImageRequest mergeImageRequest);

    void deleteImage(Long userId, Long imageId);
}
